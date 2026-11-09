"""Measure the effects of the pinned replay on disposable record copies."""

from collections import Counter
import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview import EV, HISTORY, LOG, PENDING, load_inputs, read_copy, require  # noqa: E402


def evidence_rows(root):
    with (root / EV).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row["evidence_id"]: row for row in rows}
    require(
        len(rows) == len(by_id) and "" not in by_id,
        "Evidence IDs must be present and unique",
    )
    return by_id


def split_reclassification_targets(store):
    count = 0
    for votes in store.values():
        active = [v for v in votes.values() if v.get("decision", "").strip()]
        if active and all(
            v["decision"].strip().lower() == "reclassify" for v in active
        ):
            for field in ("claim_scope", "taxon"):
                targets = {v[field].strip() for v in active if v.get(field, "").strip()}
                if len(targets) > 1:
                    count += 1
                    break
    return count


def measure(root):
    # The worker imports only the pinned engine. All records and its user lock
    # are under the temporary workspace created by the caller.
    from nbs_ruralscan.schema_tools.clarifications import event_key, read_events
    from nbs_ruralscan.schema_tools.review_local import read_decisions
    from nbs_ruralscan.schema_tools.submit_review import consensus_decisions, replay

    pending = root / "pipeline/review"
    saved = {name: read_copy(pending, name) for name in PENDING}
    store, _ = read_decisions(pending / PENDING[0])
    allowed = {"ok", "drop", "flag", "query", "reclassify"}
    require(
        all(
            v["decision"].strip().lower() in allowed
            for votes in store.values()
            for v in votes.values()
            if v.get("decision", "").strip()
        ),
        "Unsupported saved verdict",
    )
    agreed, conflicts = consensus_decisions(store)
    before = evidence_rows(root)
    original_log = (root / LOG).read_bytes()
    known_events = Counter(event_key(e) for e in read_events(root / HISTORY))
    outcome = replay(root)
    after = evidence_rows(root)
    require(list(before) == list(after), "Evidence row inventory or order changed")
    require(
        all(after[e] == row for e, row in before.items() if e not in agreed),
        "Undecided or conflicted evidence changed",
    )
    require(set(outcome.conflicts) == set(conflicts), "Conflict inventory changed")
    require(
        (root / LOG).read_bytes().startswith(original_log), "Earlier review log changed"
    )
    events = Counter(event_key(e) for e in read_events(root / HISTORY))
    require(
        known_events.keys() <= events.keys(), "An earlier clarification disappeared"
    )
    first = {name: read_copy(root, name) for name in (EV, LOG, HISTORY)}
    replay(root)
    require(
        first == {name: read_copy(root, name) for name in first},
        "Second replay changed the records",
    )
    require(
        saved == {name: read_copy(pending, name) for name in saved},
        "Replay altered pending inputs",
    )
    applied = outcome.applied or {}
    counts = {
        key: applied.get(key, 0) for key in ("ok", "dropped", "queried", "reclassified")
    }
    return {
        "evidence_rows": len(before),
        "agreed_verdict_ids": len(agreed),
        "divergent_reclassification_targets": split_reclassification_targets(store),
        "conflicted_ids": len(conflicts),
        "decision_ids_missing_from_evidence": len(
            (set(agreed) | set(conflicts)) - before.keys()
        ),
        "applied": counts,
        "new_distinct_clarification_events": len(events.keys() - known_events.keys()),
        "existing_duplicate_clarifications_coalesced": sum(
            (known_events - events).values()
        ),
        "second_replay_byte_identical": True,
    }


def main():
    engine, records, pending, *source = sys.argv[1:]
    sys.path.insert(0, engine)
    repo, pin = source if source else (None, None)
    inputs = load_inputs(Path(records), Path(pending), repo, pin)
    with TemporaryDirectory(prefix="review-records-") as temp:
        root = Path(temp)
        for name, data in inputs.items():
            if data is not None:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        result = measure(root)
    result["pending_files"] = [
        name for name in PENDING if inputs["pipeline/review/" + name] is not None
    ]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
