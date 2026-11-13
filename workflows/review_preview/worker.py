"""Measure the effects of the pinned replay on disposable record copies."""

import csv
import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare import batch_changes, evidence_rows  # noqa: E402
from preview import (
    EV,
    HISTORY,
    LOG,
    PENDING,
    load_inputs,
    load_records,
    read_copy,
    require,
)  # noqa: E402


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


def measure(root, *, check_csv=False):
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
    if check_csv:
        from nbs_ruralscan.schema_tools.review import REASON_CODES

        require(
            not ((set(agreed) | set(conflicts)) - before.keys()),
            "Unknown pending evidence ID",
        )
        require(
            not split_reclassification_targets(store),
            "Conflicting reclassification targets",
        )
        for votes in store.values():
            for vote in votes.values():
                if vote.get("csv_sources") and vote["decision"] == "drop":
                    require(
                        vote.get("reason") in REASON_CODES, "Invalid rejection reason"
                    )
        with (root / LOG).open(encoding="utf-8", newline="") as stream:
            initial_events = list(csv.DictReader(stream))
        recorded = {row["evidence_id"] for row in initial_events}
        require(
            all(
                eid in recorded
                or (
                    before[eid].get("review_state", "") == ""
                    and before[eid].get("reviewer_ok", "").lower() == "false"
                )
                for eid in agreed
            ),
            "Effective prior state without matching history; reconcile privately",
        )
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
    if check_csv:
        with (root / LOG).open(encoding="utf-8", newline="") as stream:
            new_events = list(csv.DictReader(stream))
        # An old vote must not replace a later verdict, correction or reopening,
        # even when the pinned replay would consider it eligible to apply.
        initial_count = len(initial_events)
        require(
            not any(
                row["evidence_id"] in recorded for row in new_events[initial_count:]
            ),
            "Prior applied history would change. Restore the earlier pending votes or reconcile privately.",
        )
        require(
            not any(eid in recorded and after[eid] != before[eid] for eid in agreed),
            "Existing reviewed evidence would change",
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
    result = {
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
    if check_csv:
        result["pending_challenges_with_prior_events"] = len(
            recorded.intersection(conflicts)
        )
    return result


def stage(root, inputs):
    for name, data in inputs.items():
        if data is not None:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def example_advance(root, earlier):
    """Commit one independent decision and clarification to the later example."""
    from nbs_ruralscan.schema_tools.submit_review import replay
    from recovery_fault import RECORDS, SAVED

    later_vote = {"example_conflict": {"example_reader": {"decision": "ok"}}}
    later_event = [
        {
            "issue_id": "example_question",
            "date": "2026-01-03",
            "note": "Later example clarification.",
        }
    ]
    stage(
        root,
        {
            **earlier,
            SAVED[0]: json.dumps(later_vote).encode(),
            SAVED[1]: json.dumps(later_event).encode(),
        },
    )
    replay(root)
    return {name: read_copy(root, name) for name in RECORDS}


def main():
    arguments = sys.argv[1:]
    check_csv = arguments[:1] == ["--check-csv"]
    if check_csv:
        arguments = arguments[1:]
    recovery = arguments[:1] == ["--rehearse-recovery"]
    engine, records, pending, *source = arguments[1:] if recovery else arguments
    sys.path.insert(0, engine)
    repo, pin = source[:2] if source else (None, None)
    inputs = load_inputs(Path(records), Path(pending), repo, pin)
    with TemporaryDirectory(prefix="review-records-") as temp:
        root = Path(temp) / "target"
        from recovery_fault import RECORDS, SAVED

        target = {name: inputs[name] for name in RECORDS}
        saved = {name: inputs[name] for name in SAVED}
        if recovery and not source:
            old = target
            target = example_advance(Path(temp) / "advance", old)
        stage(root, {**target, **saved})
        comparison = None
        if source[2:]:
            previous, old_pin = source[2:]
            old_root = Path(temp) / "previous"
            old = load_records(Path(previous), repo, old_pin)
            stage(old_root, {**old, **saved})
            from nbs_ruralscan.schema_tools.clarifications import read_events
            from nbs_ruralscan.schema_tools.review_local import read_decisions
            from nbs_ruralscan.schema_tools.submit_review import consensus_decisions

            store, _ = read_decisions(root / "pipeline/review/decisions.json")
            agreed, conflicts = consensus_decisions(store)
            comparison = batch_changes(
                old_root,
                root,
                set(agreed) | set(conflicts),
                read_events(root / "pipeline/review/clarifications.json"),
                read_events(old_root / HISTORY),
                read_events(root / HISTORY),
            )
            comparison.update(
                previous_revision=old_pin, previous_preview=measure(old_root)
            )
        result = measure(root, check_csv=check_csv)
        if recovery:
            from shipping_rehearsal import rehearse_shipping

            expected = {name: read_copy(root, name) for name in RECORDS}
            result["recovery_rehearsal"] = rehearse_shipping(
                Path(temp) / "shipping", old, target, saved, expected
            )
        if comparison is not None:
            result["comparison"] = comparison
    result["pending_files"] = [
        name for name in PENDING if inputs["pipeline/review/" + name] is not None
    ]
    print(json.dumps(result))


if __name__ == "__main__":
    main()
