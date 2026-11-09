# /// script
# requires-python = ">=3.12"
# dependencies = ["pymupdf==1.27.2.3"]
# ///

"""Verify and acquire one screened source in a new private handoff directory."""

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlsplit

from identity import citation_title, replay_metadata, verify_document, verify_metadata
from retrieval import (
    MAX_ARTIFACT_BYTES,
    fetch,
    pdf_routes,
    screened_code_url,
    public_url,
)

EXTENSIONS = {
    "pdf": ".pdf",
    "website": ".html",
    "markdown": ".md",
    "text": ".txt",
    "code": ".txt",
}
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def input_hash(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def source_url(value):
    parts = urlsplit(value)
    require(
        parts.scheme in {"http", "https"}
        and parts.hostname
        and not parts.username
        and not parts.password,
        "Expected a public HTTP(S) source URL without credentials",
    )
    return parts


def selected(path, candidate_id):
    rows = json.loads(path.read_bytes())
    require(
        isinstance(rows, list) and all(isinstance(x, dict) for x in rows),
        "Expected discovery candidates.json",
    )
    matches = [r for r in rows if r.get("candidate_id") == candidate_id]
    require(
        len(matches) == 1,
        "Candidate ID must occur exactly once in the screening output",
    )
    row = matches[0]
    for key in ("candidate_id", "reuse_source_id"):
        if key in row:
            require(
                isinstance(row[key], str) and SOURCE_ID.fullmatch(row[key]),
                f"Invalid {key}",
            )
    require(
        isinstance(row.get("citation"), str) and row["citation"].strip(),
        "Candidate needs a citation",
    )
    require(isinstance(row.get("doi", ""), str), "Invalid DOI field")
    source_url(row["url"])
    # First released screening bundles carry the full title in their audit only.
    # Parsing a title from a formatted citation can discard a volume or subtitle.
    audit_path = path.with_name("screening.json")
    if audit_path.is_file():
        audit = json.loads(audit_path.read_bytes())
        found = [r for r in audit if r["record_id"] == candidate_id]
        require(len(found) == 1, "Candidate missing or ambiguous in screening audit")
        screened = found[0]
        require(
            screened["disposition"]
            == ("reuse" if "reuse_source_id" in row else "include")
            and screened.get("reuse_source_id") == row.get("reuse_source_id")
            and screened["url"] == row["url"]
            and screened["title"] == row.get("title", screened["title"]),
            "Candidate and screening audit disagree",
        )
        row = dict(row, title=screened["title"])
    require(
        isinstance(row.get("title"), str) and row["title"].strip(),
        "Full screened title required. For older candidate lists, supply the adjacent screening.json.",
    )
    return row


def read_plan(path):
    plan = json.loads(path.read_bytes())
    require(isinstance(plan, dict), "Expected an acquisition plan")
    supported = {
        "candidate_id",
        "kind",
        "publisher_hosts",
        "artifact_url",
        "expected_sha256",
        "commit",
        "retry_by_title",
    }
    require(not set(plan) - supported, "Unknown acquisition plan field")
    require(
        SOURCE_ID.fullmatch(plan["candidate_id"]) and plan["kind"] in EXTENSIONS,
        "Expected a screened ID and a supported artifact kind",
    )
    if "artifact_url" in plan:
        source_url(plan["artifact_url"])
    if "expected_sha256" in plan:
        require(
            re.fullmatch(r"[a-f0-9]{64}", plan["expected_sha256"]),
            "Invalid expected SHA-256",
        )
    hosts = plan.get("publisher_hosts", [])
    require(
        isinstance(hosts, list)
        and all(
            isinstance(h, str) and re.fullmatch(r"[a-z0-9][a-z0-9.-]*", h)
            for h in hosts
        ),
        "Use lowercase publisher hostnames without paths",
    )
    require(
        isinstance(plan.get("retry_by_title", False), bool),
        "retry_by_title must be boolean",
    )
    require(
        ("commit" in plan) == (plan["kind"] == "code"), "Supply commit only for code"
    )
    return plan


def reuse_identity(candidate, plan, sources):
    reuse = candidate.get("reuse_source_id")
    if not reuse:
        return None
    if not sources:
        require(
            reuse == candidate["candidate_id"] and plan.get("expected_sha256"),
            "Supply read-only --sources SRC_source_register.csv to confirm the canonical reuse identity",
        )
        return None
    with sources.open(encoding="utf-8-sig", newline="") as stream:
        hits = [r for r in csv.DictReader(stream) if r["source_id"] == reuse]
    require(len(hits) == 1, "Expected one matching canonical source in --sources")
    record = {k: hits[0][k] for k in ("source_id", "citation", "doi")}
    validate_reuse(candidate, record)
    return record


def validate_reuse(candidate, record):
    def norm(value):
        return " ".join(re.findall(r"[^\W_]+", value.casefold()))

    def doi(value):
        return re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip().casefold()
        )

    require(
        record["source_id"] == candidate["reuse_source_id"],
        "Canonical source ID differs",
    )
    require(
        norm(record["citation"]) == norm(candidate["citation"])
        or norm(citation_title(record["citation"])) == norm(candidate["title"]),
        "Canonical source has a different citation title",
    )
    if candidate.get("doi") and record["doi"]:
        require(
            doi(candidate["doi"]) == doi(record["doi"]),
            "Canonical source has a different DOI",
        )


def check_canonical(candidate, plan, record):
    if record is not None:
        require(
            "reuse_source_id" in candidate,
            "Unexpected canonical identity for a new candidate",
        )
        validate_reuse(candidate, record)
    elif "reuse_source_id" in candidate:
        require(
            candidate["reuse_source_id"] == candidate["candidate_id"]
            and plan.get("expected_sha256"),
            "Missing canonical reuse identity",
        )


def local_bytes(path, expected):
    require(
        expected, "A local replay requires expected_sha256 from an independent source"
    )
    with path.open("rb") as stream:
        body = stream.read(MAX_ARTIFACT_BYTES + 1)
    require(
        0 < len(body) <= MAX_ARTIFACT_BYTES,
        "Local artifact is empty or exceeds the size limit",
    )
    return body


def acquire(candidate, plan, local_file, canonical=None):
    check_canonical(candidate, plan, canonical)
    metadata = verify_metadata(candidate)
    kind = plan["kind"]
    attempts = []
    receipt = {
        "format_version": 1,
        "status": "held",
        "candidate_id": candidate["candidate_id"],
        "source_id": candidate.get("reuse_source_id", candidate["candidate_id"]),
        "kind": kind,
        "candidate_sha256": input_hash(candidate),
        "plan_sha256": input_hash(plan),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "canonical_source": canonical,
        "attempts": attempts,
    }
    allow_title_retry = (
        metadata["status"] == "doi_rejected"
        and plan.get("retry_by_title")
        and plan.get("artifact_url")
        and plan.get("publisher_hosts")
    )
    if (
        metadata["status"] in {"service_unavailable", "doi_rejected"}
        and not allow_title_retry
    ):
        receipt["reason"] = metadata["reason"]
        return receipt, None
    url = plan.get("artifact_url", candidate["url"])
    pin = plan.get("expected_sha256")
    commit = plan.get("commit")
    hosts = tuple(plan.get("publisher_hosts", []))
    if kind == "code":
        require(
            screened_code_url(candidate["url"], url, commit),
            "Code must name a file at a full commit in the screened GitHub repository",
        )
    elif metadata["status"] != "doi_verified":
        require(hosts, "Supply publisher_hosts for title-only acquisition")
    if local_file:
        require(pin, "A local replay needs an independently recorded expected_sha256")

    def try_copy(route, origin):
        final = origin
        try:
            if local_file:
                require(
                    not hosts or source_url(origin).hostname in hosts,
                    "Local origin is outside publisher_hosts",
                )
                data, content_type = local_bytes(local_file, pin), None
            else:
                data, final, content_type = fetch(origin, kind, publisher_hosts=hosts)
            digest = hashlib.sha256(data).hexdigest()
            require(not pin or digest == pin, "File differs from the pinned SHA-256")
            if kind == "code":
                require(
                    screened_code_url(candidate["url"], final, commit)
                    and final == origin,
                    "Code response does not identify the requested repository, commit and file",
                )
                require(
                    b"\x00" not in data and bool(data.decode("utf-8-sig").strip()),
                    "Expected a text code snapshot",
                )
                document = {
                    "verified": True,
                    "reason": "File bound to screened repository, full commit and path",
                }
            else:
                document = verify_document(data, kind, metadata["title"])
            if not document["verified"]:
                attempts.append(
                    {
                        "route": route,
                        "url": public_url(origin),
                        "result": document["reason"],
                        "document": document,
                    }
                )
                return None
            sid = receipt["source_id"]
            artifact = {
                "source_id": sid,
                "kind": kind,
                "url": public_url(final),
                "requested_url": public_url(origin),
                "route": route,
                "fetched_at": None if local_file else receipt["checked_at"],
                "http_status": None if local_file else 200,
                "content_type": content_type,
                "commit_sha": commit,
                "bytes": len(data),
                "sha1": hashlib.sha1(data).hexdigest(),
                "sha256": digest,
            }
            attempts.append(
                {"route": route, "url": public_url(origin), "result": "verified"}
            )
            receipt.update(status="acquired", document=document, artifact=artifact)
            return data
        except (ValueError, OSError) as exc:
            problem = (
                "Local copy could not be read" if isinstance(exc, OSError) else str(exc)
            )
            attempts.append(
                {"route": route, "url": public_url(origin), "result": problem}
            )
            return None

    body = try_copy("local_hash_replay" if local_file else "direct", url)
    if body is None and kind == "pdf" and not local_file:
        verified_doi = metadata["doi"] if metadata["status"] == "doi_verified" else ""
        routes, notes = pdf_routes(
            url, verified_doi, contact=os.environ.get("UNPAYWALL_EMAIL")
        )
        receipt["recovery_notes"] = notes
        tried = {url}
        for label, alternate in routes:
            if alternate not in tried:
                tried.add(alternate)
                body = try_copy(label, alternate)
                if body is not None:
                    break
    if body is None:
        receipt["reason"] = (
            "No copy passed file and identity checks. Inspect attempts before retrying."
        )
    return receipt, body


def publish(out, receipt, body):
    # Reserve a new directory exclusively. The receipt is the completion marker.
    # On a caught write error remove only this attempt's private directory.
    out.mkdir(mode=0o700)
    try:
        if body is not None:
            sid, kind = receipt["source_id"], receipt["kind"]
            cache = out / "cache"
            cache.mkdir()
            artifact = cache / (sid + EXTENSIONS[kind])
            artifact.write_bytes(body)
            (cache / (sid + ".meta.json")).write_text(
                json_text(receipt["artifact"]), encoding="utf-8"
            )
            if kind == "pdf":
                library = out / "library"
                library.mkdir()
                shutil.copyfile(artifact, library / artifact.name)
        pending = out / ".receipt.tmp"
        pending.write_text(json_text(receipt), encoding="utf-8")
        pending.replace(out / "receipt.json")
    except BaseException:
        shutil.rmtree(out)
        raise


def check(out, plan, candidate, sources=None):
    receipt = json.loads((out / "receipt.json").read_bytes())
    sid, kind = (
        candidate.get("reuse_source_id", candidate["candidate_id"]),
        plan["kind"],
    )
    require(
        receipt["format_version"] == 1
        and receipt["candidate_id"] == candidate["candidate_id"]
        and receipt["candidate_sha256"] == input_hash(candidate)
        and receipt["plan_sha256"] == input_hash(plan)
        and receipt["source_id"] == sid
        and receipt["kind"] == kind,
        "Receipt does not match selected source and plan",
    )
    canonical = receipt["canonical_source"]
    check_canonical(candidate, plan, canonical)
    if sources:
        require(
            reuse_identity(candidate, plan, sources) == canonical or canonical is None,
            "Current source register differs from recorded canonical identity",
        )
    if receipt["status"] == "held":
        require(
            not (out / "cache").exists() and not (out / "library").exists(),
            "Held bundle contains artifacts",
        )
        return receipt
    meta = json.loads((out / "cache" / (sid + ".meta.json")).read_bytes())
    require(
        receipt["status"] == "acquired"
        and receipt["document"]["verified"]
        and meta == receipt["artifact"]
        and meta["source_id"] == sid
        and meta["kind"] == kind,
        "Invalid acquired receipt or provenance",
    )
    identity = receipt["metadata"]
    require(
        replay_metadata(candidate, identity) == identity,
        "Recorded metadata disagrees with source identity",
    )
    allow_retry = (
        identity["status"] == "doi_rejected"
        and plan.get("retry_by_title")
        and plan.get("artifact_url")
        and plan.get("publisher_hosts")
    )
    require(
        identity["status"] in {"title_required", "doi_verified"} or allow_retry,
        "Recorded metadata has no eligible acquisition route",
    )
    if kind == "code":
        require(
            meta["commit_sha"] == plan["commit"]
            and meta["url"] == plan.get("artifact_url", candidate["url"])
            and screened_code_url(candidate["url"], meta["url"], plan["commit"]),
            "Recorded code artifact differs from the screened repository, revision or file",
        )
    if plan.get("publisher_hosts"):
        require(
            source_url(meta["url"]).hostname in plan["publisher_hosts"],
            "Recorded origin is outside publisher hosts",
        )
    name = sid + EXTENSIONS[kind]
    copies = [out / "cache" / name]
    if kind == "pdf":
        copies.append(out / "library" / name)
    for path in copies:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        require(
            digest == meta["sha256"] == plan.get("expected_sha256", digest)
            and hashlib.sha1(data).hexdigest() == meta["sha1"]
            and len(data) == meta["bytes"],
            f"File checksum or size differs: {path.name}",
        )
    if kind != "code":
        require(
            verify_document(data, kind, identity["title"]) == receipt["document"],
            "Document identity differs from receipt",
        )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parsers = parser.add_subparsers(dest="command", required=True)
    verify = parsers.add_parser(
        "verify", help="Check a screened candidate's Crossref metadata"
    )
    get = parsers.add_parser(
        "acquire", help="Stage a verified artifact or an identity/access hold"
    )
    audit = parsers.add_parser(
        "check", help="Recheck a saved receipt and every file copy offline"
    )
    for sub in (verify, get, audit):
        sub.add_argument("--candidates", required=True, type=Path)
    verify.add_argument("--id", required=True)
    for sub in (get, audit):
        sub.add_argument("--plan", required=True, type=Path)
        sub.add_argument(
            "--sources",
            type=Path,
            help="Read-only canonical source CSV for reuse identity",
        )
    get.add_argument("--out", required=True, type=Path)
    get.add_argument(
        "--local-file",
        type=Path,
        help="Replay private bytes against an independent checksum",
    )
    audit.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "verify":
        result = verify_metadata(selected(args.candidates, args.id))
        print(json_text(result), end="")
        return 2 if result["status"] in {"service_unavailable", "doi_rejected"} else 0
    plan = read_plan(args.plan)
    candidate = selected(args.candidates, plan["candidate_id"])
    if args.command == "check":
        receipt = check(args.bundle, plan, candidate, args.sources)
    else:
        require(
            not os.path.lexists(args.out),
            "Output exists. Use check to inspect it or choose a new directory.",
        )
        canonical = reuse_identity(candidate, plan, args.sources)
        receipt, body = acquire(candidate, plan, args.local_file, canonical)
        publish(args.out, receipt, body)
    if receipt["status"] == "held":
        print(f"Held {receipt['source_id']}: {receipt['reason']}", file=sys.stderr)
        return 2
    print(
        f"Verified {receipt['source_id']} ({receipt['kind']}, {receipt['artifact']['bytes']:,} bytes)"
    )
    print(f"SHA-256 {receipt['artifact']['sha256']}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, KeyError) as exc:
        sys.exit(f"Acquisition stopped: {exc}")
