"""Prepare and replay a bounded discovery screening worksheet (Python 3.10+)."""

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

from capture import bare_doi, save_new

RULESET = "v1.8.1"
PROCESSES = {"stock", "updated_lit", "grey", "tool"}
TABLES = {"T3", "T4", "T6"}
BIB_FIELDS = ("doi", "language", "method_subtype", "report_number_or_handle")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(row, key):
    value = row.get(key)
    require(isinstance(value, str) and value.strip(), f"Missing text: {key}")
    return value.strip()


def identifier(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value),
        f"Invalid identifier: {value!r}",
    )
    return value


def iso_date(value):
    require(
        date.fromisoformat(value).isoformat() == value, f"Expected YYYY-MM-DD: {value}"
    )
    return value


def read(path, kind):
    data = json.loads(path.read_bytes())
    require(isinstance(data, kind), f"Unexpected JSON type: {path.name}")
    return data


def encode(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def fingerprint(value):
    data = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(data.encode()).hexdigest()


def normalized(value):
    return " ".join(value.casefold().split()).rstrip(".")


def title_key(value):
    return " ".join(re.findall(r"[^\W_]+", value.casefold()))


def load_run(path):
    plan = read(path, dict)
    for key in ("nbs_id", "run_id"):
        identifier(text(plan, key))
    if plan["family"] != "":
        identifier(plan["family"])
    require(
        plan["table"] in TABLES and plan["process"] in PROCESSES,
        "Unknown table or process",
    )
    for key in (
        "purpose",
        "inclusion_criteria",
        "limits",
        "stop_reason",
        "omissions",
        "searched_by",
        "screened_by",
    ):
        text(plan, key)
    closed = iso_date(text(plan, "date"))
    names = plan["captures"]
    require(
        isinstance(names, list) and names and all(isinstance(n, str) for n in names),
        "List actual captures",
    )
    require(len(names) == len(set(names)), "Repeated capture filename")
    captures, records, origins = [], {}, {}
    for name in names:
        capture = read(path.parent / name, dict)
        require(
            capture.get("process") == plan["process"],
            f"{name}: capture process differs from plan",
        )
        for key in ("channel", "query", "limits"):
            text(capture, key)
        require(iso_date(text(capture, "date")) <= closed, "Capture postdates run")
        rows = capture["records"]
        require(
            isinstance(rows, list),
            "Each capture needs its observed records (empty list for zero results)",
        )
        for row in rows:
            require(isinstance(row, dict), "Invalid capture record")
            rid = identifier(text(row, "record_id"))
            for key in ("title", "citation", "url", *BIB_FIELDS):
                require(isinstance(row.get(key, ""), str), f"{rid}: invalid {key}")
            row = dict(row, doi=bare_doi(row.get("doi", "")))
            require(
                row.get("oa_status", "unknown") in {"oa", "unknown"},
                f"{rid}: unknown access status",
            )
            if rid in records:
                for key, normalize in (("title", title_key), ("doi", str.casefold)):
                    old, new = records[rid].get(key), row.get(key)
                    require(
                        not (old and new) or normalize(old) == normalize(new),
                        f"{rid}: conflicting {key}",
                    )
            else:
                records[rid] = {}
                origins[rid] = []
            records[rid].update(
                {k: v for k, v in row.items() if v and not records[rid].get(k)}
            )
            if row.get("oa_status") == "oa":
                records[rid]["oa_status"] = "oa"
            if name not in origins[rid]:
                origins[rid].append(name)
        captures.append(capture)
    return plan, captures, records, origins


def worksheet(plan, captures, records):
    return {
        "input_sha256": fingerprint([plan, captures]),
        "records": [
            {
                "record_id": rid,
                "title": row.get("title", ""),
                "disposition": "unscreened",
                "reason": "",
            }
            for rid, row in records.items()
        ],
    }


def screen(plan, captures, records, origins, sheet):
    require(
        sheet.get("input_sha256") == fingerprint([plan, captures]),
        "Scope or capture changed; regenerate worksheet",
    )
    rows = sheet["records"]
    require(
        isinstance(rows, list) and all(isinstance(d, dict) for d in rows),
        "Invalid worksheet records",
    )
    by_id = {identifier(text(d, "record_id")): d for d in rows}
    require(
        len(by_id) == len(rows) and by_id.keys() == records.keys(),
        "Worksheet must cover each captured ID exactly once",
    )
    # Explicit aliases account for different provider IDs for the same work. All
    # occurrences remain in the audit; each distinct work counts once in this lane.
    dois, doi_titles, canonical_dois, citations = {}, {}, {}, {}
    audit, candidates = [], []
    retrieved = screened = 0
    for rid, rec in records.items():
        d = by_id[rid]
        require(
            d.get("title") == rec.get("title", ""),
            f"{rid}: worksheet title differs from capture",
        )
        outcome = d["disposition"]
        require(
            outcome
            in {"unscreened", "duplicate", "hold", "exclude", "include", "reuse"},
            f"{rid}: unknown disposition",
        )
        reason = "" if outcome == "unscreened" else text(d, "reason")
        canonical = rid
        if outcome == "duplicate":
            canonical = text(d, "duplicate_of")
            require(
                canonical in by_id and by_id[canonical]["disposition"] != "duplicate",
                f"{rid}: select a primary record",
            )
        else:
            retrieved += 1
            if outcome != "unscreened":
                screened += 1
        citation_key = normalized(rec.get("citation", ""))
        if citation_key:
            previous = citations.setdefault(citation_key, canonical)
            require(
                previous == canonical,
                f"{rid}: reconcile identical citations with duplicate_of",
            )
        doi = rec.get("doi", "").casefold()
        if doi:
            title = title_key(rec.get("title", ""))
            if title:
                require(
                    doi_titles.setdefault(doi, title) == title,
                    f"{rid}: same DOI has conflicting titles; verify identity before staging",
                )
            require(
                dois.setdefault(doi, canonical) == canonical,
                f"{rid}: reconcile repeated DOI with duplicate_of",
            )
            require(
                canonical_dois.setdefault(canonical, doi) == doi,
                f"{rid}: conflicting DOIs for one work",
            )
        entry = {
            "record_id": rid,
            "title": rec.get("title", ""),
            "url": rec.get("url", ""),
            "captures": origins[rid],
            "disposition": outcome,
            "reason": reason,
        }
        if outcome != "reuse":
            require(
                "reuse_source_id" not in d,
                f"{rid}: reuse_source_id requires reuse disposition",
            )
        if outcome != "duplicate":
            require(
                "duplicate_of" not in d,
                f"{rid}: duplicate_of requires duplicate disposition",
            )
        if outcome == "duplicate":
            entry["duplicate_of"] = canonical
        if outcome in {"include", "reuse"}:
            citation, url = text(rec, "citation"), text(rec, "url")
            text(rec, "title")
            require(
                urlsplit(url).scheme in {"https", "http"} and urlsplit(url).hostname,
                f"{rid}: source URL missing",
            )
            candidate = {
                "candidate_id": rid,
                "nbs_id": plan["nbs_id"],
                "title": rec["title"],
                "citation": citation,
                "url": url,
                "process": plan["process"],
                "tables": plan["table"],
                "families": [plan["family"]] if plan["family"] else [],
                "relevance_note": reason,
            }
            candidate.update(
                {k: rec[k] for k in (*BIB_FIELDS, "oa_status") if rec.get(k)}
            )
            for key in ("families", "hazards", "t6_targets"):
                if key in d:
                    tags = d[key]
                    require(
                        isinstance(tags, list) and all(identifier(tag) for tag in tags),
                        f"{rid}: expected a list of IDs in {key}",
                    )
                    candidate[key] = tags
                    entry[key] = tags
            require(
                not plan["family"] or plan["family"] in candidate["families"],
                f"{rid}: candidate must cover targeted family",
            )
            if outcome == "reuse":
                candidate["reuse_source_id"] = identifier(text(d, "reuse_source_id"))
                candidate["reuse_reason"] = reason
                entry["reuse_source_id"] = candidate["reuse_source_id"]
            if "proposed_benchmark_tier" in d:
                candidate["proposed_benchmark_tier"] = text(
                    d, "proposed_benchmark_tier"
                )
                candidate["tier_rationale"] = text(d, "tier_rationale")
            candidates.append(candidate)
        for key in (
            "lineage",
            "referral",
            "parent_source_id",
            "credibility",
            "proposed_benchmark_tier",
            "tier_rationale",
        ):
            if key in d:
                entry[key] = text(d, key)
        audit.append(entry)
    return audit, candidates, (retrieved, screened, len(candidates))


def render(plan, captures, audit, candidates, counts, digest):
    queries = [
        f"{name} — {c['channel']} ({c['date']}): {c['query']}"
        for name, c in zip(plan["captures"], captures)
    ]
    limits = [f"{c['channel']}: {c['limits']}" for c in captures]
    protocol = {
        "table": plan["table"],
        "category": plan["process"],
        "search_terms": "\n".join(queries),
        "inclusion_criteria": plan["inclusion_criteria"],
        "limits": "\n".join([plan["limits"], *limits]),
        "n_retrieved": counts[0],
        "n_screened": counts[1],
        "n_included": counts[2],
    }
    lines = [
        f"# {plan['run_id']}",
        "",
        plan["purpose"],
        "",
        f"{plan['nbs_id']} / {plan['family'] or 'whole practice'} / {plan['table']} / {plan['process']}",
        f"Search closed {plan['date']} · discovery {RULESET}. Searched by {plan['searched_by']}. Screened by {plan['screened_by']}.",
        "",
        "## Verbatim queries",
        "",
        *queries,
        "",
        "## Coverage",
        "",
        protocol["limits"],
        f"Inclusion: {plan['inclusion_criteria']}",
        f"Stop: {plan['stop_reason']}",
        f"Omissions: {plan['omissions']}",
        "",
        f"Observed {counts[0]} distinct records; screened {counts[1]}; included {counts[2]} before queue deduplication.",
        "",
        "## Screening decisions",
        "",
    ]
    for row in audit:
        details = [
            row.get(key)
            for key in (
                "reason",
                "duplicate_of",
                "reuse_source_id",
                "lineage",
                "parent_source_id",
                "referral",
                "credibility",
                "proposed_benchmark_tier",
                "tier_rationale",
            )
        ]
        lines.append(
            " · ".join(
                filter(
                    None,
                    [
                        row["record_id"],
                        row["title"],
                        row["url"],
                        row["disposition"],
                        *details,
                    ],
                )
            )
        )
    lines.extend(["", f"Scope and capture SHA-256: `{digest}`", ""])
    return {
        "screening.json": encode(audit),
        "candidates.json": encode(candidates),
        "protocols.json": encode([protocol]),
        "report.md": "\n".join(lines),
    }


def stage(out, files):
    require(not out.exists(), f"Output already exists: {out}")
    # Resolve all inputs and render in memory first; reserve destination atomically
    # so concurrent runs cannot overwrite another run. Roll back a failed write.
    out.mkdir()
    try:
        for name, content in files.items():
            (out / name).write_text(content, encoding="utf-8")
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    make = sub.add_parser("worksheet", help="Create a blank screening worksheet")
    replay = sub.add_parser(
        "stage", help="Replay screening decisions and write registrar inputs"
    )
    for action in (make, replay):
        action.add_argument("plan", type=Path)
        action.add_argument("--out", type=Path, required=True)
    replay.add_argument("decisions", type=Path)
    args = parser.parse_args()
    plan, captures, records, origins = load_run(args.plan)
    if args.action == "worksheet":
        save_new(args.out, worksheet(plan, captures, records))
        print(f"{len(records)} recorded IDs in {args.out}")
        return
    decisions = read(args.decisions, dict)
    audit, candidates, counts = screen(plan, captures, records, origins, decisions)
    stage(
        args.out,
        render(plan, captures, audit, candidates, counts, decisions["input_sha256"]),
    )
    print(
        f"{counts[0]} distinct records retrieved, {counts[1]} screened, {counts[2]} included (before queue deduplication)"
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, TypeError, KeyError, ValueError) as error:
        sys.exit(f"Screening stopped: {error}")
