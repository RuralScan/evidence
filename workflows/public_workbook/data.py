"""Project verified release records and their pinned evidence into a public workbook."""

import csv
from io import StringIO
import json
import re
from urllib.parse import quote, urlsplit

from git_snapshot import git, require, revision
from recipe_index import SOURCE, TABLES, record_locations, table_cells


def register(source, commit, stem, key, recovered=None):
    """Return records and line links from one immutable Git blob."""
    path = f"schema/registers/{stem}.json"
    pinned = git("show", f"{commit}:{path}", cwd=source)
    if recovered is not None:
        require(recovered == pinned, "Recovered register differs from linked Git blob")
    raw = (pinned if recovered is None else recovered).decode("utf-8")
    rows = json.loads(raw)
    ids = [r[key] for r in rows]
    pattern = re.compile(rf'^    "{key}": "([A-Za-z0-9_.-]+)",?$')
    locations = {
        match[1]: f"{SOURCE}/blob/{commit}/{path}#L{number}"
        for number, line in enumerate(raw.splitlines(), 1)
        if (match := pattern.fullmatch(line))
    }
    require(
        len(ids) == len(set(ids)) and set(ids) == locations.keys(),
        f"Cannot uniquely locate all {stem} records",
    )
    return rows, locations


# Stable document collections used for title-verified, DOI-less publications.
# Omit sharing links, query parameters and local copies from the public reader.
DOCUMENT_COLLECTIONS = {
    "wocat.net": "/documents/",
    "documents1.worldbank.org": "/curated/",
    "documents.worldbank.org": "/curated/",
    "cgspace.cgiar.org": "/",
    "openknowledge.fao.org": "/",
    "www.fao.org": "/",
}


def is_document_url(url):
    parts = urlsplit(url)
    prefix = DOCUMENT_COLLECTIONS.get(parts.netloc)
    return (
        parts.scheme == "https"
        and prefix is not None
        and parts.path.startswith(prefix)
        and not parts.query
        and not parts.fragment
    )


def publication_links(source, commit):
    raw = git("show", f"{commit}:pipeline/acquisition_queue.csv", cwd=source)
    dois, documents = {}, {}
    for row in csv.DictReader(StringIO(raw.decode("utf-8"))):
        sid = row["source_id"]
        doi = row["doi"].strip().lower()
        if doi and row["doi_verified"] == "true":
            dois[sid] = doi
        if not doi and row["title_verified"] == "true" and is_document_url(row["url"]):
            documents[sid] = row["url"]
    return dois, documents


def bibliography(source, commit):
    rows, urls = register(source, commit, "SRC_source_register", "source_id")
    dois, documents = publication_links(source, commit)
    result = []
    for row in rows:
        sid = row["source_id"]
        doi = (row.get("doi") or "").strip().lower()
        verified = dois.get(sid) == doi and re.fullmatch(r"10\.\d{4,9}/\S+", doi)
        result.append(
            {
                "id": sid,
                "citation": row["citation"],
                "kind": row["source_kind"],
                "category": row["source_category"],
                "publication_url": "https://doi.org/" + quote(doi, safe="/")
                if verified
                else None,
                "publisher_url": documents.get(sid)
                if not doi and row.get("url") == documents.get(sid)
                else None,
                "url": urls[sid],
            }
        )
    return result


def claims(source, commit, source_ids, recovered=None):
    rows, urls = register(
        source, commit, "EV_evidence_register", "evidence_id", recovered
    )
    result = []
    for row in rows:
        if row.get("review_state") == "dropped":
            continue
        eid = row["evidence_id"]
        require(row["source_id"] in source_ids, f"Unknown source for {eid}")
        result.append(
            {
                "id": eid,
                "source_id": row["source_id"],
                "practice": row["nbs_id"],
                "family": row.get("suitability_family_id"),
                "variable": row.get("variable"),
                "role": row["use_role"],
                "scope": row.get("claim_scope"),
                "basis": row.get("claim_basis"),
                "type": row.get("evidence_type"),
                "confidence": row.get("extraction_confidence"),
                "locator_type": row.get("locator_type"),
                "locator": row.get("locator"),
                "page": row.get("page"),
                "url": urls[eid],
            }
        )
    return result


def searches(source, commit):
    rows, urls = register(source, commit, "SRCH_search_register", "search_id")
    # Keep a qualified tally such as '64 shared' intact. Only the operator who
    # ran the search can deduplicate results across overlapping search records.
    return [
        {
            "id": row["search_id"],
            "practice": row["nbs_id"],
            "family": row.get("suitability_family_id"),
            "table": row["table"],
            "category": row["category"],
            "retrieved": row.get("n_retrieved"),
            "screened": row.get("n_screened"),
            "included": row.get("n_included"),
            "url": urls[row["search_id"]],
        }
        for row in rows
    ]


def nested_references(value, evidence, sources):
    """Find structured links in calibration profiles and evidence justifications."""
    if isinstance(value, list):
        for member in value:
            nested_references(member, evidence, sources)
    if isinstance(value, dict):
        for key, member in value.items():
            if key in {
                "evidence_ids",
                "key_evidence_ids",
                "source_ids",
                "parameter_source_ids",
            }:
                require(isinstance(member, list), f"Expected a list for {key}")
                target = evidence if "evidence" in key else sources
                target.update(member)
            elif key in {"evidence_id", "source_id"}:
                require(isinstance(member, str), f"Expected an identifier for {key}")
                (evidence if key == "evidence_id" else sources).add(member)
            else:
                nested_references(member, evidence, sources)


def analytical_rows(release, summary, claim_ids, source_ids):
    from nbs_ruralscan.runtime.schema_loader import TABLE_STEMS

    rows = []
    counts = {}
    for practice in release.practices:
        report = json.loads(release.read_bytes(f"tables/{practice}/T4_readiness.json"))
        readiness = {row["rule_id"]: row for row in report["rows"]}
        counts[practice] = {}
        for table, (_, headers) in TABLES.items():
            filename = TABLE_STEMS[table] + ".json"
            links = record_locations(
                release, practice, table, filename, summary["source_revision"]
            )
            records = release.table(practice, table)
            counts[practice][table] = len(records)
            require(
                len(records) == summary["practices"][practice][table],
                "Recipe row count differs",
            )
            for row in records:
                identifier = row["mapping_id" if table == "T4" else "record_id"]
                direct = row.get("evidence_ids", [])
                require(
                    isinstance(direct, list) and len(direct) == len(set(direct)),
                    f"Invalid evidence IDs in {identifier}",
                )
                evidence, sources = set(), set()
                nested_references(row, evidence, sources)
                require(
                    evidence <= claim_ids,
                    f"Unknown or dropped evidence in {identifier}: {sorted(evidence - claim_ids)}",
                )
                require(
                    sources <= source_ids,
                    f"Unknown sources in {identifier}: {sorted(sources - source_ids)}",
                )
                cells = table_cells(row, table, readiness)
                rows.append(
                    {
                        "id": identifier,
                        "practice": practice,
                        "table": table,
                        "family": row.get("suitability_family_id"),
                        "subject": cells[0],
                        "fields": dict(zip(headers, cells, strict=True)),
                        "evidence_ids": direct,
                        "context_ids": sorted(evidence.difference(direct)),
                        "context_source_ids": sorted(sources),
                        "url": links[identifier],
                    }
                )
    require(len(rows) == len({r["id"] for r in rows}), "Analytical row IDs collide")
    return rows, counts


def build_data(source, release, summary, *, recovered_evidence=None):
    """Build a read-only public projection after the recipe release checker passes."""
    commit = revision(summary["source_revision"])
    require(release.release_id == summary["release_id"], "Workbook release differs")
    provenance = json.loads(release.read_bytes("provenance.json"))
    require(
        provenance["source_revision"] == commit, "Register and recipe revisions differ"
    )
    sources = bibliography(source, commit)
    source_ids = {r["id"] for r in sources}
    active = claims(source, commit, source_ids, recovered_evidence)
    rows, counts = analytical_rows(
        release, summary, {r["id"] for r in active}, source_ids
    )
    totals = {table: sum(c[table] for c in counts.values()) for table in TABLES}
    require(
        all(total == summary["totals"][table] for table, total in totals.items()),
        "Workbook totals differ",
    )
    return {
        "release_id": release.release_id,
        "source_revision": commit,
        "counts": counts,
        "totals": totals,
        "rows": rows,
        "claims": active,
        "sources": sources,
        "searches": searches(source, commit),
    }
