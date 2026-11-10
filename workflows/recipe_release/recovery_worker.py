"""Recover a workbook's committed review inputs in a disposable local submission."""

import csv
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

REVIEW = Path(__file__).resolve().parents[1] / "review_preview"
sys.path.insert(0, str(REVIEW))

from preview import LOG, read_copy, require  # noqa: E402
from recovery_fault import RECORDS, SAVED  # noqa: E402
from shipping_rehearsal import rehearse_shipping  # noqa: E402
from worker import stage  # noqa: E402


def training_votes(earlier, target):
    require(
        target.startswith(earlier), "Earlier review log is not an exact byte prefix"
    )
    before, after = (
        list(csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")))
        for data in (earlier, target)
    )
    require(after[: len(before)] == before, "Earlier review log entries changed")
    events = after[len(before) :]
    votes = {}
    for event in events:
        eid = event["evidence_id"]
        if event["decision"] in {"ok", "drop"} and eid:
            require(event["reviewer"], "Approval or drop lacks its recorded reviewer")
            votes[eid] = {
                event["reviewer"]: {k: event[k] for k in ("decision", "reason", "note")}
            }
        else:
            # An intervening reopening or query supersedes an earlier training vote.
            votes.pop(eid, None)
    require(votes, "No appended approvals or drops to rehearse")
    return votes, len(events)


def main():
    engine, previous, target_root, result_dir = map(Path, sys.argv[1:])
    sys.path.insert(0, str(engine))
    from nbs_ruralscan.schema_tools.submit_review import replay

    earlier = {name: read_copy(previous, name) for name in RECORDS}
    target = {name: read_copy(target_root, name) for name in RECORDS}
    votes, event_count = training_votes(earlier[LOG], target[LOG])
    pending = {SAVED[0]: json.dumps(votes).encode("utf-8"), SAVED[1]: None}
    with TemporaryDirectory(prefix="workbook-replay-") as temp:
        root = Path(temp)
        clean = root / "clean"
        stage(clean, {**target, **pending})
        replay(clean)
        expected = {name: read_copy(clean, name) for name in RECORDS}
        require(
            expected == target, "Training votes do not reproduce the pinned records"
        )
        receipt = rehearse_shipping(
            root / "submission",
            earlier,
            target,
            pending,
            expected,
            recovered_dir=result_dir,
        )
        require(
            receipt["record_install_interrupted"]
            and receipt["retry_matches_clean_replay"],
            "Workbook recovery requires an interrupted record write and matching retry",
        )
    print(
        json.dumps(
            {
                "training_vote_ids": len(votes),
                "appended_review_events": event_count,
                **receipt,
            }
        )
    )


if __name__ == "__main__":
    main()
