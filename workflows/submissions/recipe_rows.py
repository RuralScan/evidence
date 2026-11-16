"""Submit and replay revision-pinned wording and rating reviews for compiled recipe rows."""

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

import intake
from registers import LIVE, ROOT, blob, content_digest, git, json_bytes, require

TABLES = {
    "T3": "T3_nbs_hazard_farming",
    "T4": "T4_suitability_mappings",
    "T6": "T6_nbs_scorecard",
    "T6E": "T6E_economic_profile",
}
HEADER = "RuralScan recipe row v1"
LOG = "pipeline/metrics/row_review_log.csv"
RECORDS = {
    "rating": "row-reviews/receipts.jsonl",
    "wording": "recipe-inputs/wording.jsonl",
}
CANDIDATE = "publication/recipe-candidate.json"
REASONS = {
    "wrong_class",
    "wrong_confidence",
    "prose_misleading",
    "evidence_misrouted",
    "should_be_split",
    "other",
}
DECISIONS = ("approve", "hold", "reject")


def digest(value):
    return content_digest(json_bytes(value))


def ident(row):
    return row.get("record_id") or row["mapping_id"]


def lookup(queue, practice, table, record):
    require(table in TABLES, "Unknown table")
    matches = [
        r
        for r in queue["recipes"].get(practice, {}).get(TABLES[table], [])
        if ident(r) == record
    ]
    require(
        len(matches) == 1,
        "Unknown or ambiguous compiled row in this practice and table",
    )
    return matches[0]


SOURCE_PROGRESS = {
    "extraction_status",
    "extraction_date",
    "extraction_run_id",
    "extractor",
    "vars_extracted",
}


def evidence_index(registers):
    sources = {
        s["source_id"]: digest({k: v for k, v in s.items() if k not in SOURCE_PROGRESS})
        for s in registers["SRC_source_register"]
    }
    return {
        e["evidence_id"]: digest([e, sources[e["source_id"]]])
        for e in registers["EV_evidence_register"]
    }


def basis(row, table, ev):
    ids = sorted(row.get("evidence_ids") or [])
    require(all(i in ev for i in ids), "Unresolved evidence in compiled row")
    science = dict(row)
    if table == "T4":
        science.pop("justification", None)
    else:
        for key in (
            "effect_mechanism",
            "mitigation_mechanism",
            "conditionality",
            "caveats",
        ):
            science.pop(key, None)
        science["justification"] = {
            k: v
            for k, v in (row.get("justification") or {}).items()
            if k
            not in {
                "mechanism",
                "conditionality",
                "agreement_note",
                "evidence_summary",
                "prose_written",
                "prose_pending",
            }
        }
    return digest([science, [(i, ev[i]) for i in ids]])


def target(queue, practice, table, record):
    row = lookup(queue, practice, table, record)
    return dict(
        practice=practice,
        table=table,
        record=record,
        evidence_ids=sorted(row.get("evidence_ids") or []),
        row_sha256=digest(row),
        basis_sha256=basis(row, table, evidence_index(queue["registers"])),
    )


def validate(entry, queue, revision):
    require(
        isinstance(entry, dict)
        and entry.get("revision") == revision
        and re.fullmatch("[0-9a-f]{40}", revision),
        "Stale or invalid revision. Inspect the current row before resubmitting.",
    )
    kind = entry.get("kind")
    require(kind in RECORDS, "Unknown row submission type")
    expected = target(queue, entry["practice"], entry["table"], entry["record"])
    require(
        all(entry.get(k) == v for k, v in expected.items()), "Stale row or evidence pin"
    )
    keys = {"revision", "kind", *expected}

    def string(key, limit, allow_empty=False):
        v = entry.get(key)
        require(
            isinstance(v, str)
            and len(v) <= limit
            and (allow_empty or v.strip())
            and "\0" not in v,
            f"Invalid {key}",
        )

    if kind == "rating":
        keys.update(["decision", "reason", "note"])
        require(entry.get("decision") in DECISIONS, "Unknown rating decision")
        string("reason", 500, True)
        string("note", 4000, True)
        require(
            entry["decision"] == "approve" or entry["reason"].strip(),
            "Hold or reject requires a reason",
        )
        require(
            entry["decision"] != "reject" or entry["reason"] in REASONS,
            "Reject requires a coded reason",
        )
    else:
        keys.add("wording")
        fields = (
            {"justification"}
            if entry["table"] == "T4"
            else {"mechanism", "conditionality"}
        )
        words = entry.get("wording")
        require(
            isinstance(words, dict)
            and set(words) == fields
            and all(
                isinstance(v, str) and len(v) <= 6000 and "\0" not in v
                for v in words.values()
            ),
            "Invalid wording fields",
        )
        require(
            words.get("justification", words.get("mechanism", "")).strip(),
            "Wording must be nonempty",
        )
    require(set(entry) == keys, "Unexpected submission fields")


def fetch(number):
    issue = intake.gh(f"repos/{intake.INBOX}/issues/{number}")
    require(
        issue["number"] == number
        and "pull_request" not in issue
        and issue["state"] == "open"
        and intake.reviewer_eligible(issue),
        "Row receipt must be open and from an eligible contributor",
    )
    actor = intake.original(issue)
    tag, sep, raw = issue["body"].partition("\n")
    require(
        sep and tag.rstrip("\r") == HEADER, "Expected an original recipe-row receipt"
    )
    return dict(
        receipt=number,
        actor=actor,
        created_at=issue["created_at"],
        body_sha256=content_digest(issue["body"].encode()),
        entry=json.loads(raw),
    )


def lines(data):
    return [json.loads(line) for line in data.splitlines()]


def local(root, path):
    p = root / path
    return p.read_bytes() if p.exists() else b""


def prior(root, base, path):
    return blob(root, base, path) if git("ls-tree", base, "--", path, cwd=root) else b""


def csv_event(event):
    e = event["entry"]
    data = io.StringIO(newline="")
    csv.writer(data, lineterminator="\r\n").writerow(
        [
            event["created_at"],
            e["record"],
            e["practice"],
            e["table"],
            e["decision"],
            e["reason"],
            e["note"],
            event["actor"],
        ]
    )
    return data.getvalue().encode()


def additions(event, history, queue, base, root):
    for old in history:
        if old["receipt"] == event["receipt"]:
            require(old == event, "Receipt changed")
            return False
        if (
            old["actor"].casefold() == event["actor"].casefold()
            and old["entry"] == event["entry"]
        ):
            return False
    entry = event["entry"]
    pin = entry["revision"]
    if pin != base:
        from registers import member

        require(
            isinstance(pin, str)
            and re.fullmatch("[0-9a-f]{40}", pin)
            and member(root, pin, base),
            "Stale or unknown baseline",
        )
        validate(entry, json.loads(blob(root, pin, LIVE)), pin)
    validate(dict(entry, revision=base), queue, base)
    return True


def append(root, event, base):
    kind = event["entry"]["kind"]
    history = [e for path in RECORDS.values() for e in lines(local(root, path))]
    if not additions(
        event, history, json.loads((root / LIVE).read_bytes()), base, root
    ):
        return False
    path = root / RECORDS[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(json_bytes(event))
    if kind == "rating":
        with (root / "registers" / LOG).open("ab") as stream:
            stream.write(csv_event(event))
    return True


def verify(root, base):
    old_bytes = {k: prior(root, base, p) for k, p in RECORDS.items()}
    history = [e for data in old_bytes.values() for e in lines(data)]
    queue = None
    count = 0
    expected_log = blob(root, base, "registers/" + LOG)
    for kind, path in RECORDS.items():
        data = local(root, path)
        require(data.startswith(old_bytes[kind]), "Historical row receipts changed")
        new = data[len(old_bytes[kind]) :]
        records = lines(new)
        require(new == b"".join(map(json_bytes, records)), "Noncanonical row receipts")
        for event in records:
            count += 1
            require(count == 1, "Use one protected PR per row receipt")
            queue = queue or json.loads(blob(root, base, LIVE))
            require(
                event == fetch(event["receipt"])
                and event["entry"]["kind"] == kind
                and additions(event, history, queue, base, root),
                "Duplicate or misattributed row event",
            )
            history.append(event)
            if kind == "rating":
                expected_log += csv_event(event)
    require(
        (root / "registers" / LOG).read_bytes() == expected_log,
        "Rating log differs from authenticated append-only events",
    )
    if queue is not None:
        require(
            not git(
                "diff", base, "--", "registers", ":(exclude)registers/" + LOG, cwd=root
            ),
            "Submit row decisions separately from register changes",
        )


def published_reviews(root, rows):
    events = lines(local(root, RECORDS["rating"]))
    if events:
        require(len(rows) >= len(events), "Missing applied rating history")
        for row, event in zip(rows[-len(events) :], events, strict=True):
            e = event["entry"]
            require(
                (row["record_id"], row["reviewer"], row["decision"])
                == (e["record"], event["actor"], e["decision"]),
                "Inconsistent rating history",
            )
            row.update(revision=e["revision"], receipt=event["receipt"])
    return rows


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("kind", choices=["inspect", "wording", "rating"])
    for field in ["revision", "practice", "table", "record"]:
        p.add_argument("--" + field, required=True)
    p.add_argument("--decision", choices=DECISIONS)
    p.add_argument("--reason", default="")
    p.add_argument("--note", default="")
    p.add_argument(
        "--wording", type=Path, help="JSON containing only the authored fields"
    )
    p.add_argument(
        "--submit",
        action="store_true",
        help="Create a public receipt as your signed-in GitHub account",
    )
    args = p.parse_args()
    require(
        re.fullmatch("[0-9a-f]{40}", args.revision), "Use a full RuralScan/evidence SHA"
    )
    q = json.loads(blob(ROOT, args.revision, LIVE))
    pin = target(q, args.practice, args.table, args.record)
    if args.kind == "inspect":
        print(
            json.dumps(
                lookup(q, args.practice, args.table, args.record),
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    e = dict(kind=args.kind, revision=args.revision, **pin)
    if args.kind == "rating":
        e.update(decision=args.decision, reason=args.reason, note=args.note)
    else:
        require(args.wording, "Supply --wording FILE")
        e["wording"] = json.loads(args.wording.read_bytes())
    validate(e, q, args.revision)
    body = HEADER + "\n" + json.dumps(e, ensure_ascii=False)
    if not args.submit:
        print(body)
        return
    print(send(e))


def send(entry, expected_actor=None):
    actor = intake.signed_in()
    require(
        expected_actor is None or actor == expected_actor,
        "Signed-in GitHub account changed; restart the desk",
    )
    require(
        intake.gh("repos/" + intake.INBOX + "/commits/main")["sha"]
        == entry["revision"],
        "Stale revision. Inspect current main.",
    )
    return intake.gh(
        "repos/" + intake.INBOX + "/issues",
        data={
            "title": f"{entry['table']} {entry['kind']}: {entry['record']}",
            "body": HEADER + "\n" + json.dumps(entry, ensure_ascii=False),
        },
    )["html_url"]


if __name__ == "__main__":
    try:
        cli()
    except (ValueError, KeyError, OSError) as exc:
        sys.exit(f"Row submission stopped: {exc}")
