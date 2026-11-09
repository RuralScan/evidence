"""Offline checks for the fixture's contribution to the authored hold."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from replay import EXAMPLE, apply_fixture_support, csv_rows, revision


class FixtureSupportTests(unittest.TestCase):
    def test_scope_drives_authored_membership(self):
        case = json.loads((EXAMPLE / "reviewed-claims.json").read_bytes())
        profiles = [{"evidence_id": c["evidence_id"]} for c in case["claims"]]
        supporting = [
            c for c in case["claims"] if c["included_in_annual_terrace_support"]
        ]
        ids = [claim["evidence_id"] for claim in supporting]
        sources = {claim["source_id"] for claim in supporting}
        calibration = {
            "scope": case["mapping_id"],
            "status": "held",
            "retained_source_profiles": profiles,
            "excluded_from_annual_terrace_support_and_scoring": [],
        }
        row = {
            "mapping_id": case["mapping_id"],
            "evidence_ids": "[]",
            "n_sources": "0",
            "relationship_params": json.dumps(
                {"reviewed_adaptation": {"numerical_calibration": calibration}}
            ),
        }
        other = {**row, "mapping_id": "another_mapping"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holds.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=row.keys())
                writer.writeheader()
                writer.writerows([row, other])
            apply_fixture_support(path, case, ids, sources)
            rebuilt, untouched = csv_rows(path)
            self.assertEqual(untouched, other)
            self.assertEqual(
                json.loads(rebuilt["evidence_ids"]),
                ["ev_wh_precip_wocatgl13_benchterraces"],
            )
            self.assertEqual(rebuilt["n_sources"], "1")
            hold = json.loads(rebuilt["relationship_params"])["reviewed_adaptation"][
                "numerical_calibration"
            ]
            self.assertEqual(hold["status"], "held")
            self.assertEqual(hold["retained_source_profiles"], profiles)
            self.assertEqual(
                hold["excluded_from_annual_terrace_support_and_scoring"],
                [p["evidence_id"] for p in profiles[:2]],
            )
            with self.assertRaisesRegex(ValueError, "different profiles"):
                apply_fixture_support(
                    path, {**case, "claims": case["claims"][1:]}, ids, sources
                )
            self.assertEqual(csv_rows(path), [rebuilt, other])

    def test_branch_names_are_not_pins(self):
        with self.assertRaisesRegex(ValueError, "full Git commit"):
            revision("main")
