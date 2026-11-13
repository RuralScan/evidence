# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.4.6", "requests==2.34.2"]
# ///

"""Build the immutable public review-status companion to the pinned workbook."""

import argparse
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from git_snapshot import git, require, snapshot

PUBLISHED = HERE.parents[1] / "publication/workbook"
PIN = HERE.parent / "recipe_release/pin.json"
LIVE = "e930734c0705406f14757ee3e62e90537e8d4095"
FLOOD = "ev_flood_hazard_roose17_2"
DROUGHT = "ev_drought_hazard_ieg20_4"
DROP = "27d844fef193291f27af690e5f300f2e1b625593"
HEADLINE = "agroforestry__drought__all"
FINDING_LOG = "pipeline/metrics/review_log.csv"
ROW_LOG = "pipeline/metrics/row_review_log.csv"
METHOD_LOG = "methodology/decisions/open_decisions.csv"
TABLE_FILES = {"T3": "T3_nbs_hazard_farming", "T6": "T6_nbs_scorecard"}
STATES = ("signed_off", "held", "unreviewed", "rejected")
REASONS = {
    "accepted_correction",
    "confirmed_pass",
    "other",
    "off_scope",
    "wrong_practice",
    "insufficient_context",
    "species_envelope",
    "speculative_evidence",
    "wrong_variable",
    "unusable_value",
    "constrained_aoi",
    "wrong_table",
    "relationship_missed",
    "smuggled_number",
    "quote_too_narrow",
    "table_error",
    "false_flag",
}
SCHEMA = 1


def blob(repo, rev, path):
    return git("show", f"{rev}:{path}", cwd=repo)


def read(repo, rev, path):
    return json.loads(blob(repo, rev, path))


def logged(repo, rev, path):
    # Real first-parent introduction on main, including records appended with
    # the same date. Preserve the start line of quoted multiline CSV records.
    blame = git(
        "blame", "--first-parent", "--line-porcelain", rev, "--", path, cwd=repo
    )
    commits = {
        int(m[2]): m[1].decode()
        for m in re.finditer(rb"(?m)^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$", blame)
    }
    reader = csv.DictReader(io.StringIO(blob(repo, rev, path).decode(), newline=""))
    _ = reader.fieldnames
    while True:
        line = reader.line_num + 1
        row = next(reader, None)
        if row is None:
            return
        yield row, {"commit": commits[line], "line": line}


def actor_kind(raw):
    names = {name.strip().casefold() for name in raw.split(",")}
    if names and names <= {"pete", "peter", "pete steward", "peetmate", "namita-j"}:
        return "human"
    if names and all(
        n == "orchestrator" or n.startswith(("ai_", "codex ")) for n in names
    ):
        return "automated"
    return "unverified"


def public_event(row, origin):
    return {
        **origin,
        "date": row["date"],
        "actor_kind": actor_kind(row["reviewer"]),
        "decision": row["decision"],
        "reason": row["reason"] if row["reason"] in REASONS else None,
    }


def finding_state(ev, events):
    """Separate applied updates from evidence of a human's effective sign-off."""
    event = events[-1] if events else None
    disposition = None
    for entry in events:
        decision = entry["decision"]
        if decision in ("drop", "reopen", "flag", "query"):
            disposition = entry
        elif (
            decision in ("ok", "keep", "reclassify") and entry["actor_kind"] == "human"
        ):
            disposition = entry

    signed = ev.get("reviewer_ok") is True
    excluded = ev.get("review_state") == "dropped"
    decision = disposition["decision"] if disposition else None
    if excluded:
        status = "rejected"
    elif decision in ("flag", "query"):
        status = "held"
    elif signed and decision in ("ok", "keep", "reclassify"):
        status = "signed_off"
    else:
        status = "unreviewed"
    expected = {
        "drop": "rejected",
        "ok": "signed_off",
        "keep": "signed_off",
        "reclassify": "signed_off",
        "flag": "held",
        "query": "held",
        "reopen": "unreviewed",
    }.get(decision)
    return {
        "source_id": ev["source_id"],
        "excluded": excluded,
        "status": status,
        "latest_event": event,
        "status_event": disposition,
        "reconciliation_required": (expected is not None and status != expected)
        or (signed and status in ("held", "unreviewed")),
    }


def coverage(tested, setters, findings, complete=False):
    ids = sorted(setters)
    counts = Counter(findings[i]["status"] for i in ids)
    unresolved = [i for i in ids if findings[i]["status"] in ("unreviewed", "held")]
    return {
        "coverage": "assessed"
        if complete
        else ("partial" if tested else "unavailable"),
        "tested_ids": sorted(tested),
        "setter_ids": ids,
        "unresolved_setter_ids": unresolved,
        "status_counts": {s: counts[s] for s in STATES} if tested or complete else None,
        "provisional": True if unresolved else (False if complete else None),
    }


def navigation(repo):
    batches = read(repo, LIVE, "docs/review/index.json")["batches"]
    # Prefer the verified Top 60 card when a unit is also in an older batch.
    batches.sort(
        key=lambda b: (b["id"] == "ratings_top60_2026-11-12", b["date"], b["id"])
    )
    result = {}
    for batch in batches:
        content = read(repo, LIVE, "docs/" + batch["file"])
        require(content["batch"]["id"] == batch["id"], "Review batch ID mismatch")
        for item in content["units"]:
            result[item["evidence_id"]] = batch["id"]
    return result


@lru_cache(maxsize=64)
def table_rows(repo, rev, practice, table):
    path = f"schema/recipes/{practice}/{TABLE_FILES[table]}.json"
    return {r["record_id"]: r for r in read(repo, rev, path)}


def result(row):
    return {
        "rating": row.get("effect_direction")
        or row.get("asset_sensitivity")
        or row.get("mitigation_potential"),
        "confidence": row.get("effect_confidence") or row.get("confidence"),
        "evidence_ids": row["evidence_ids"],
    }


def history(repo, rev, events):
    practice = "agroforestry"
    before = git("rev-parse", DROP + "^1", cwd=repo).decode().strip()

    def at(commit):
        registered = {}
        for table in TABLE_FILES:
            registered.update(table_rows(repo, commit, practice, table))
        return sorted(
            i for i, r in registered.items() if DROUGHT in r["evidence_ids"]
        ), result(registered[HEADLINE])

    old, a = at(before)
    applied, b = at(DROP)
    current, c = at(rev)
    require(
        any(e["commit"] == DROP and e["decision"] == "drop" for e in events[DROUGHT]),
        "Unverified historical drop",
    )
    verdict = (
        "recompiled, unchanged"
        if (a["rating"], a["confidence"]) == (b["rating"], b["confidence"])
        else "attribution unverified"
    )
    return {
        DROUGHT: {
            "before_revision": before,
            "applied_revision": DROP,
            "recompiled_revision": DROP,
            "edition_revision": rev,
            "citations_before": old,
            "citations_after": applied,
            "citations_in_edition": current,
            "headline_id": HEADLINE,
            "before": a,
            "after": b,
            "edition": c,
            "result": verdict,
            "later_change_attribution": "unverified",
            "finding_events": events[DROUGHT],
        }
    }


def roose_replay(repo, rev, rows):
    practice = "water_harvesting_conservation"
    with TemporaryDirectory() as temp:
        source = Path(temp) / "snapshot"
        snapshot(source, str(repo), rev, ["/src/", "/schema/"], local=repo)
        run = subprocess.run(
            [
                sys.executable,
                "-IB",
                str(HERE / "replay.py"),
                str(source),
                practice,
                FLOOD,
            ],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
        data = json.loads(run.stdout)
    affected = {}
    for key, r in rows.items():
        if r["practice"] != practice:
            continue
        baseline = [r["rating"], r["confidence"]]
        require(
            data["baseline"][key] == baseline,
            f"Replay disagrees with published baseline: {key}",
        )
        if FLOOD in r["evidence_ids"]:
            affected[key] = {"before": baseline, "without": data["without"].get(key)}
    return affected


def build(repo, workbook, assessed):
    pin = json.loads(PIN.read_bytes())
    rev = pin["source_revision"]
    require(
        git("rev-parse", "--is-shallow-repository", cwd=repo).strip() == b"false",
        "Review provenance requires full Git history",
    )
    match = re.search(
        rb'<script type="application/json" id="publication">(.+?)</script>',
        workbook,
        re.S,
    )
    data = json.loads(match[1])
    require(
        data["source_revision"] == rev and data["release_id"] == pin["release_id"],
        "Workbook release mismatch",
    )
    events = defaultdict(list)
    for r, origin in logged(repo, rev, FINDING_LOG):
        events[r["evidence_id"]].append(public_event(r, origin))
    cards = navigation(repo)
    live_register = read(repo, LIVE, "docs/dashboard_data.json")["registers"][
        "EV_evidence_register"
    ]
    live_active = {
        r["evidence_id"] for r in live_register if r.get("review_state") != "dropped"
    }
    findings = {}
    for ev in read(repo, rev, "schema/registers/EV_evidence_register.json"):
        key = ev["evidence_id"]
        findings[key] = {
            **finding_state(ev, events[key]),
            "live_queue_available": key in live_active,
            "live_batch": cards.get(key),
        }
    require(
        {k for k, r in findings.items() if not r["excluded"]}
        == {c["id"] for c in data["claims"]},
        "EV inclusion differs from workbook",
    )
    deferred_path = "schema/registers/_deferred/EV_T3_T6_deferred_2026-09.csv"
    deferred = {
        r["evidence_id"]: r
        for r in csv.DictReader(
            io.StringIO(blob(repo, rev, deferred_path).decode(), newline="")
        )
    }
    unmatched = {}
    for key in sorted(events.keys() - findings.keys()):
        archived = deferred.get(key)
        unmatched[key] = {
            "latest_event": events[key][-1],
            "deferred_register": deferred_path if archived else None,
            "deferred_review_state": archived.get("review_state") if archived else None,
        }
    rows = {}
    for item in data["rows"]:
        table, practice, key = item["table"], item["practice"], item["id"]
        if table not in TABLE_FILES:
            continue
        r = result(table_rows(repo, rev, practice, table)[key])
        require(r["evidence_ids"] == item["evidence_ids"], "Direct evidence IDs differ")
        rows[key] = {
            "practice": practice,
            "table": table,
            **r,
            "producer_revision": rev,
            "rating_reviews": [],
            **coverage([], [], findings),
        }
    reviews = []
    for r, origin in logged(repo, rev, ROW_LOG):
        event = public_event(r, origin)
        # Export dates can predate a batch commit. The exact version seen in a
        # review browser is unavailable unless the log identifies it.
        event.update(
            record_id=r["record_id"],
            table=r["table"],
            row_revision=None,
            rating=None,
            confidence=None,
        )
        reviews.append(event)
        if r["record_id"] in rows and rows[r["record_id"]]["table"] == r["table"]:
            rows[r["record_id"]]["rating_reviews"].append(event)
    traces = roose_replay(repo, rev, rows)
    for key, obs in traces.items():
        setter = obs["before"] != obs["without"]
        rows[key].update(coverage([FLOOD], [FLOOD] if setter else [], findings))
    require(
        assessed["producer_revision"] == rev
        and assessed["release_id"] == pin["release_id"],
        "Setter replay pin mismatch",
    )
    headlines = set()
    table_pools = defaultdict(set)
    for key, r in rows.items():
        table_pools[r["practice"], r["table"]].update(r["evidence_ids"])
        native = table_rows(repo, rev, r["practice"], r["table"])[key]
        if (
            not native.get("scope_type")
            and not native.get("suitability_family_id")
            and native.get("farming_system") in (None, "", "all")
        ):
            headlines.add(key)
    require(
        headlines == assessed["by_record"].keys(),
        "Setter replay headline inventory differs",
    )
    for key, ids in assessed["by_record"].items():
        require(
            len(ids) == len(set(ids))
            and all(i in findings and not findings[i]["excluded"] for i in ids),
            "Invalid setter IDs",
        )
        practice, table = rows[key]["practice"], rows[key]["table"]
        require(
            set(ids) <= table_pools[practice, table],
            "Setter outside assessed practice/table population",
        )
        union = table_pools[practice, "T3"] | table_pools[practice, "T6"]
        require(
            len(union) == assessed["tested_findings_per_practice"][practice],
            "Practice replay count differs from pinned population",
        )
        if key in traces:
            obs = traces[key]
            require(
                (FLOOD in ids) == (obs["before"] != obs["without"]),
                "Independent Roose assessment disagrees",
            )
        rows[key].update(coverage([], ids, findings, complete=True))
        rows[key]["practice_removal_count"] = assessed["tested_findings_per_practice"][
            practice
        ]
        rows[key]["tested_count"] = len(table_pools[(practice, table)])
        # Complete assessments use a practice-wide universe; listing [] as the
        # tested IDs would incorrectly imply an empty universe.
        rows[key].pop("tested_ids")
    methods = [
        {
            **origin,
            "decision_id": r["decision_id"],
            "date": r["decided_on"],
            "implementation_commit": None,
        }
        for r, origin in logged(repo, rev, METHOD_LOG)
        if r["status"] == "decided"
    ]
    return {
        "schema_version": SCHEMA,
        "producer_revision": rev,
        "release_id": pin["release_id"],
        "live_navigation_revision": LIVE,
        "findings": findings,
        "rows": rows,
        "rating_reviews": reviews,
        "unmatched_finding_reviews": unmatched,
        "method_decisions": methods,
        "history": history(repo, rev, events),
        "setter_assessment": {
            "assessment_revision": assessed["assessment_revision"],
            "complete_headlines": len(headlines),
            "producer_revision": rev,
            "finding_id": FLOOD,
            "scope": "one finding, its directly citing T3/T6 records",
            "results": traces,
        },
    }


def encode(obj):
    return (
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def files(repo, workbook, replayed):
    status = build(repo, workbook, json.loads(replayed))
    encoded = encode(status)
    meta = {k: status[k] for k in ("schema_version", "producer_revision", "release_id")}
    meta.update(
        replayed_setters_sha256=hashlib.sha256(replayed).hexdigest(),
        workbook_sha256=hashlib.sha256(workbook).hexdigest(),
        status_sha256=hashlib.sha256(encoded).hexdigest(),
    )
    return {"review-status.json": encoded, "review-status-manifest.json": encode(meta)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciat-repo", required=True, type=Path)
    parser.add_argument("--directory", type=Path, default=PUBLISHED)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, content in files(
        args.ciat_repo.resolve(),
        (args.directory / "index.html").read_bytes(),
        (args.directory / "replayed-setters.json").read_bytes(),
    ).items():
        path = args.directory / name
        if args.check:
            require(path.read_bytes() == content, f"Stale {name}")
        else:
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(content)
            tmp.replace(path)
        print(name, hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    main()
