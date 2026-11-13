"""Release regressions plus disposable conflicting-vote and applied-hold exercises."""

import csv
import json
import os
from pathlib import Path
import tempfile
import unittest

from build import (
    DROUGHT,
    FLOOD,
    HEADLINE,
    PIN,
    PUBLISHED,
    coverage,
    finding_state,
    snapshot,
)


class StatusTests(unittest.TestCase):
    def test_published_traces(self):
        status = json.loads((PUBLISHED / "review-status.json").read_bytes())
        f = status["findings"][FLOOD]
        self.assertEqual(
            (f["status"], f["live_batch"], f["latest_event"]),
            ("unreviewed", "ratings_top60_2026-11-12", None),
        )
        observations = status["setter_assessment"]["results"]
        self.assertEqual(len(observations), 7)
        self.assertTrue(
            all(obs["before"] == obs["without"] for obs in observations.values())
        )
        headline = status["rows"]["water_harvesting_conservation__flood__all"]
        self.assertEqual(
            (
                headline["rating"],
                headline["confidence"],
                headline["coverage"],
                headline["provisional"],
            ),
            ("moderate", "high", "assessed", True),
        )
        self.assertNotIn(FLOOD, headline["setter_ids"])
        history = status["history"][DROUGHT]
        self.assertEqual(
            (
                len(history["citations_before"]),
                history["citations_after"],
                history["citations_in_edition"],
            ),
            (12, [], []),
        )
        self.assertEqual(history["result"], "recompiled, unchanged")
        self.assertEqual(
            [history[k]["rating"] for k in ("before", "after", "edition")],
            ["moderate", "moderate", "conflicting_evidence"],
        )
        self.assertEqual(
            [len(history[k]["evidence_ids"]) for k in ("before", "after")], [44, 39]
        )
        drop = status["findings"][DROUGHT]
        self.assertTrue(drop["excluded"])
        self.assertEqual(
            (drop["latest_event"]["reason"], drop["latest_event"]["line"]),
            ("wrong_practice", 2571),
        )
        self.assertTrue(status["rows"][HEADLINE]["rating_reviews"])

    def test_unknown_and_empty_coverage(self):
        self.assertIsNone(coverage([], [], {})["provisional"])
        self.assertIsNone(coverage(["A"], [], {})["provisional"])
        self.assertFalse(coverage([], [], {}, complete=True)["provisional"])
        self.assertEqual(
            finding_state(
                {"source_id": "s", "reviewer_ok": False},
                [{"decision": "reopen", "actor_kind": "human"}],
            )["status"],
            "unreviewed",
        )
        contradictory = finding_state(
            {"source_id": "s", "reviewer_ok": True},
            [{"decision": "flag", "actor_kind": "human"}],
        )
        self.assertTrue(contradictory["reconciliation_required"])
        self.assertEqual(contradictory["status"], "held")

    def test_automation_cannot_grant_human_signoff(self):
        ev = {"source_id": "test", "reviewer_ok": True}
        auto = {"decision": "ok", "actor_kind": "automated"}
        human = {"decision": "ok", "actor_kind": "human"}
        flag = {"decision": "flag", "actor_kind": "human"}
        for history, expected in [
            ([auto], "unreviewed"),
            ([flag, auto], "held"),
            ([human, auto], "signed_off"),
            ([flag, human], "signed_off"),
        ]:
            self.assertEqual(finding_state(ev, history)["status"], expected)
        s = json.loads((PUBLISHED / "review-status.json").read_bytes())
        for key in ["ev_wet_assetflood_budi20_1", "ev_fire_hazard_tauf23_1"]:
            self.assertEqual(s["findings"][key]["status"], "unreviewed")
        self.assertTrue(s["findings"][FLOOD]["live_queue_available"])
        self.assertFalse(s["findings"][DROUGHT]["live_queue_available"])
        row = s["rows"]["water_harvesting_conservation__flood__all"]
        self.assertLess(row["tested_count"], row["practice_removal_count"])
        self.assertIn(
            "ev_t6_carbon_mitigation_potential_zomer14_5",
            s["unmatched_finding_reviews"],
        )

    @unittest.skipUnless(
        os.environ.get("CIAT_TEST_REPO"), "Set CIAT_TEST_REPO to a full CIAT clone"
    )
    def test_conflict_then_hold_with_real_engine(self):
        import sys

        practice = "water_harvesting_conservation"
        rid = practice + "__flood__all"
        key = "ev_flood_hazard_heusch95_1"
        repo = Path(os.environ["CIAT_TEST_REPO"]).resolve()
        revision = json.loads(PIN.read_bytes())["source_revision"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve() / "snapshot"
            snapshot(
                root,
                str(repo),
                revision,
                ["/src/", "/schema/", "/pipeline/metrics/review_log.csv"],
                local=repo,
            )
            sys.path.insert(0, str(root / "src"))
            from nbs_ruralscan.schema_tools.review_exports import write_decisions
            from nbs_ruralscan.schema_tools.submit_review import consensus_decisions
            from nbs_ruralscan.schema_tools.review import ReviewFiles, apply_decisions
            from nbs_ruralscan.schema_tools.generate import _csv_to_rows
            from nbs_ruralscan.recipe import t3t6_build as compiler

            exports = root / "docs/review/exports"
            exports.mkdir(parents=True)
            pending = exports.parent / "decisions.json"
            for name, vote in (("A", "approve"), ("B", "reject")):
                with (exports / (name + ".csv")).open("w", newline="") as stream:
                    w = csv.writer(stream)
                    w.writerow(["evidence_id", "reviewer", "batch", "decision"])
                    w.writerow([key, name, "fixture", vote])
            files = ReviewFiles.from_root(root)
            previous = files.log.read_bytes()
            write_decisions(dest=pending, exports_dir=exports, batch_dir=exports.parent)
            votes = json.loads(pending.read_text())["decisions"]["fixture"][key]
            self.assertEqual(
                {v["decision"] for v in votes.values()}, {"approve", "reject"}
            )
            agreed, conflicts = consensus_decisions(
                {
                    key: {
                        name: {
                            "decision": {"approve": "ok", "reject": "drop"}[
                                v["decision"]
                            ]
                        }
                        for name, v in votes.items()
                    }
                }
            )
            self.assertEqual((agreed, conflicts), ({}, [key]))
            self.assertEqual(previous, files.log.read_bytes())
            self.assertEqual(
                finding_state({"source_id": "s", "reviewer_ok": False}, [])["status"],
                "unreviewed",
            )

            def compiled():
                inputs = compiler.load_inputs(
                    practice,
                    [],
                    inputs=compiler.T3T6BuildInputs.from_root(root, practice),
                )
                return next(
                    r
                    for r in compiler.synthesise(practice, inputs)["T3"]
                    if r["record_id"] == rid
                )

            before = compiled()
            self.assertIn(
                key,
                json.loads((PUBLISHED / "replayed-setters.json").read_bytes())[
                    "by_record"
                ][rid],
            )
            self.assertIn(
                key,
                json.loads(before["evidence_ids"])
                if isinstance(before["evidence_ids"], str)
                else before["evidence_ids"],
            )
            apply_decisions(
                {key: {"decision": "flag", "reason": "insufficient_context"}},
                "fixture",
                files=files,
            )
            regenerated = _csv_to_rows(files.evidence)
            files.evidence.with_suffix(".json").write_text(json.dumps(regenerated))
            with files.log.open(newline="") as stream:
                event = list(csv.DictReader(stream))[-1]
            event["actor_kind"] = "human"
            held = finding_state(
                next(ev for ev in regenerated if ev["evidence_id"] == key), [event]
            )
            self.assertEqual(
                (event["decision"], held["status"], held["excluded"]),
                ("flag", "held", False),
            )
            self.assertTrue(coverage([key], [key], {key: held})["provisional"])
            after = compiled()
            for k in ("mitigation_potential", "confidence", "evidence_ids"):
                self.assertEqual(before[k], after[k])
            self.assertFalse((root / "pipeline/metrics/row_review_log.csv").exists())
            self.assertFalse(
                (root / "methodology/decisions/open_decisions.csv").exists()
            )


if __name__ == "__main__":
    unittest.main()
