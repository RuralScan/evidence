import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import check


class InclusionTests(unittest.TestCase):
    def setUp(self):
        self.policy = check.load(check.POLICY.read_bytes())
        self.record = {
            "ruleset": self.policy["id"], "source_id": "synthetic",
            "nbs_id": "water_harvesting_conservation",
            "suitability_family_id": "water_harvesting__in_situ",
            "component_scope": "Rainwater capture and soil storage package",
            "source_sha256": check.digest(b"source"),
            "practice_fit": {"status": "pass", "rationale": "Primary rainwater capture", "source_locator": "p1"},
            "water_harvesting_purpose": "primary",
            "definition": {"available": True, "kind": "authorised_project_catalogue", "access": "restricted",
                           "edition": "synthetic test edition", "sha256": check.digest(b"definition"),
                           "general_locator": "definition", "practice_locator": "practice",
                           "chapter_mapping_rationale": "Direct practice match"},
            "conditions": [], "material_conflicts": [],
            "criteria": {name: {"status": "pass", "rationale": "Synthetic supported pathway",
                                 "source_locator": "p2", "definition_locator": "criterion"}
                         for name in self.policy["core_criteria"] + self.policy["context_criteria"]},
        }

    def result(self):
        return check.assess(self.record, self.policy)

    def test_secondary_water_benefit_fails_despite_nbs_passes(self):
        self.record["water_harvesting_purpose"] = "secondary"
        self.assertEqual(self.result(), "exclude_wrong_practice")

    def test_in_situ_primary_capture_can_pass(self):
        self.assertEqual(self.result(), "include_for_scoping")

    def test_unclear_primary_purpose_holds(self):
        self.record["water_harvesting_purpose"] = "unclear"
        self.assertEqual(self.result(), "hold")

    def test_definition_unavailable_is_not_public_definition_substitution(self):
        self.record["definition"] = {"available": False, "access_note": "No authorised copy"}
        self.assertEqual(self.result(), "hold")

    def test_no_biodiversity_pathway_holds_despite_crop_benefit(self):
        self.record["criteria"]["biodiversity_pathway"]["status"] = "unknown"
        self.assertEqual(self.result(), "hold")

    def test_supported_pathway_with_monitoring_condition_is_conditional(self):
        self.record["criteria"]["durability_management"]["status"] = "unknown"
        self.record["conditions"] = ["Specify monitoring and maintenance at site design"]
        self.assertEqual(self.result(), "conditional_include")

    def test_material_conflict_cannot_be_erased_by_conditions(self):
        self.record["material_conflicts"] = ["Unresolved donor-strip erosion"]
        self.record["conditions"] = ["Protect soils"]
        self.assertEqual(self.result(), "hold")

    def test_evidenced_ecosystem_failure_excludes(self):
        self.record["criteria"]["baseline_habitat"]["status"] = "fail"
        self.assertEqual(self.result(), "exclude_nbs")

    def test_water_rule_does_not_apply_to_forest_restoration(self):
        self.record["nbs_id"] = "forest_restoration"
        self.record["suitability_family_id"] = "forest_restoration__regeneration"
        self.record.pop("water_harvesting_purpose")
        self.assertEqual(self.result(), "include_for_scoping")

    def test_unanchored_positive_is_invalid(self):
        self.record["criteria"]["natural_process"]["source_locator"] = ""
        with self.assertRaisesRegex(ValueError, "source locator"):
            self.result()

    def test_stale_source_and_definition_rejected(self):
        data = json.dumps(self.record).encode()
        for source, definition, expected in [(b"changed", b"definition", "Source bytes"),
                                              (b"source", b"changed", "Definition bytes")]:
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, expected):
                check.check_bytes(data, source, definition)

    def test_duplicate_and_nonfinite_json_rejected(self):
        for data in [b'{"x":1,"x":2}', b'{"x":NaN}']:
            with self.subTest(data=data), self.assertRaises(ValueError):
                check.load(data)

    def test_cli_hold_writes_private_receipt_and_never_approves(self):
        self.record["material_conflicts"] = ["Unresolved ecological impact"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.json").write_text(json.dumps(self.record))
            (root / "source").write_bytes(b"source")
            (root / "definition").write_bytes(b"definition")
            args = [sys.executable, str(Path(check.__file__)), str(root / "input.json"),
                    "--source", str(root / "source"), "--definition", str(root / "definition"),
                    "--out", str(root / "receipt.json")]
            result = subprocess.run(args, capture_output=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["decision"], "hold")
            self.assertFalse(receipt["human_approval"])
            self.assertNotIn(str(root), json.dumps(receipt))
            before = (root / "receipt.json").read_bytes()
            self.assertEqual(subprocess.run(args, capture_output=True).returncode, 1)
            self.assertEqual((root / "receipt.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
