import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import screen

HERE = Path(__file__).resolve().parent


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(HERE / "example", self.root / "run")
        self.run_dir = self.root / "run"
        self.plan = self.run_dir / "plan.json"
        self.capture = self.run_dir / "stock.json"
        self.sheet = self.run_dir / "decisions.json"
        self.bundle = self.root / "bundle"

    def cli(self, *args, success=True):
        p = subprocess.run(
            [sys.executable, str(HERE / "screen.py"), *args],
            capture_output=True,
            text=True,
        )
        self.assertEqual(p.returncode == 0, success, p.stderr)
        return p

    def stage(self, success=True):
        return self.cli(
            "stage", self.plan, self.sheet, "--out", self.bundle, success=success
        )

    def replace_records(self, rows):
        capture = json.loads(self.capture.read_bytes())
        capture["records"] = rows
        self.capture.write_text(screen.encode(capture))
        self.sheet.unlink()
        self.cli("worksheet", self.plan, "--out", self.sheet)

    def decide(self, changes):
        sheet = json.loads(self.sheet.read_bytes())
        for d in sheet["records"]:
            d.update(changes.get(d["record_id"], {}))
        self.sheet.write_text(screen.encode(sheet))

    def check_counts(self, expected):
        (protocol,) = json.loads((self.bundle / "protocols.json").read_bytes())
        self.assertEqual(
            tuple(protocol[k] for k in ("n_retrieved", "n_screened", "n_included")),
            expected,
        )
        return protocol

    def test_terrace_replay_and_retry(self):
        self.stage()
        self.check_counts((3, 3, 1))
        (candidate,) = json.loads((self.bundle / "candidates.json").read_bytes())
        self.assertEqual(candidate["reuse_source_id"], "wocat_wh_guidelines_2013")
        self.assertEqual(candidate["families"], ["water_harvesting__terracing"])
        original = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        self.stage(success=False)
        self.assertEqual(
            original, {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        )
        self.bundle = self.root / "rerun"
        self.stage()
        self.assertEqual(
            original, {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        )

    def test_unavailable_channel_is_not_zero_records(self):
        capture = json.loads(self.capture.read_bytes())
        del capture["records"]
        self.capture.write_text(screen.encode(capture))
        self.stage(success=False)
        self.assertFalse(self.bundle.exists())

    def test_observed_zero(self):
        self.replace_records([])
        self.stage()
        self.check_counts((0, 0, 0))
        self.assertEqual(json.loads((self.bundle / "candidates.json").read_bytes()), [])

    def test_search_and_table_scope_changes_invalidate_decisions(self):
        for key, value in (("table", "T3"), ("family", "")):
            old = self.plan.read_bytes()
            plan = json.loads(old)
            plan[key] = value
            self.plan.write_text(screen.encode(plan))
            self.assertIn("regenerate worksheet", self.stage(success=False).stderr)
            self.assertFalse(self.bundle.exists())
            self.plan.write_bytes(old)
        capture = json.loads(self.capture.read_bytes())
        capture["query"] = "new query"
        self.capture.write_text(screen.encode(capture))
        self.assertIn("regenerate worksheet", self.stage(success=False).stderr)

    def test_capture_cannot_change_process(self):
        plan = json.loads(self.plan.read_bytes())
        plan["process"] = "updated_lit"
        self.plan.write_text(screen.encode(plan))
        self.assertIn("capture process differs", self.stage(success=False).stderr)

    def test_repeated_identity_and_unscreened(self):
        row = json.loads(self.capture.read_bytes())["records"][0]
        same = dict(
            row,
            record_id="other",
            doi="https://doi.org/" + row["doi"].upper(),
            citation=row["citation"] + " Alternative provider format.",
        )
        # First paper appears twice in the same capture and once under another ID.
        self.replace_records([row, row, same, {"record_id": "unknown"}])
        self.decide(
            {
                row["record_id"]: {
                    "disposition": "include",
                    "reason": "Relevant methods.",
                }
            }
        )
        self.assertIn("reconcile repeated DOI", self.stage(success=False).stderr)
        self.decide(
            {
                "other": {
                    "disposition": "duplicate",
                    "reason": "Same paper and DOI.",
                    "duplicate_of": row["record_id"],
                }
            }
        )
        self.stage()
        self.check_counts((2, 1, 1))
        audit = json.loads((self.bundle / "screening.json").read_bytes())
        self.assertEqual(
            [r["disposition"] for r in audit], ["include", "duplicate", "unscreened"]
        )

    def test_multiple_queries_one_primary_and_positive_access_metadata(self):
        cap = json.loads(self.capture.read_bytes())
        row = cap["records"][0]
        cap["records"] = [
            dict(row, doi="https://doi.org/" + row["doi"], oa_status="unknown")
        ]
        self.capture.write_text(screen.encode(cap))
        cap.update(query="citation lookup", records=[dict(row, oa_status="oa")])
        (self.run_dir / "second.json").write_text(screen.encode(cap))
        plan = json.loads(self.plan.read_bytes())
        plan["captures"].append("second.json")
        self.plan.write_text(screen.encode(plan))
        self.sheet.unlink()
        self.cli("worksheet", self.plan, "--out", self.sheet)
        self.decide(
            {row["record_id"]: {"disposition": "include", "reason": "Relevant input."}}
        )
        self.stage()
        protocol = self.check_counts((1, 1, 1))
        self.assertIn("citation lookup", protocol["search_terms"])
        (candidate,) = json.loads((self.bundle / "candidates.json").read_bytes())
        self.assertEqual((candidate["doi"], candidate["oa_status"]), (row["doi"], "oa"))
        (audit,) = json.loads((self.bundle / "screening.json").read_bytes())
        self.assertEqual(audit["captures"], ["stock.json", "second.json"])

    def test_duplicate_cannot_hide_conflicting_titles(self):
        row = json.loads(self.capture.read_bytes())["records"][0]
        other = dict(
            row,
            record_id="other",
            title="Unrelated work",
            citation="Unrelated work.",
            doi="doi:" + row["doi"],
        )
        self.replace_records([row, other])
        self.decide(
            {
                "other": {
                    "disposition": "duplicate",
                    "reason": "Shared DOI.",
                    "duplicate_of": row["record_id"],
                }
            }
        )
        self.assertIn("conflicting titles", self.stage(success=False).stderr)
        self.assertFalse(self.bundle.exists())

    def test_practice_wide_effect_search_retains_candidate_tags(self):
        plan = json.loads(self.plan.read_bytes())
        plan.update(family="", table="T6")
        self.plan.write_text(screen.encode(plan))
        row = json.loads(self.capture.read_bytes())["records"][0]
        self.replace_records([row])
        self.decide(
            {
                row["record_id"]: {
                    "disposition": "include",
                    "reason": "Teaching example.",
                    "families": ["water_harvesting__terracing"],
                    "t6_targets": ["water_quality_risk"],
                }
            }
        )
        self.stage()
        (candidate,) = json.loads((self.bundle / "candidates.json").read_bytes())
        self.assertEqual(candidate["tables"], "T6")
        self.assertEqual(candidate["families"], ["water_harvesting__terracing"])
        self.assertEqual(candidate["t6_targets"], ["water_quality_risk"])

    def test_incomplete_identity_can_be_held(self):
        self.replace_records([{"record_id": "unidentified"}])
        self.decide(
            {"unidentified": {"disposition": "include", "reason": "May be relevant."}}
        )
        self.stage(success=False)
        self.assertFalse(self.bundle.exists())
        self.decide(
            {"unidentified": {"disposition": "hold", "reason": "Missing source title."}}
        )
        self.stage()
        self.check_counts((1, 1, 0))


if __name__ == "__main__":
    unittest.main()
