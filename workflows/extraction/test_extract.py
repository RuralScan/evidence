"""Checks for page provenance, lane boundaries and private staging."""

from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf

import extract


class PassageTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(
            (Path(__file__).parent / "example/terrace-rainfall.json").read_bytes()
        )
        self.spec["inspected_pdf_pages"] = [1]
        for item in [self.spec["source_purpose"], *self.spec["inventory"]]:
            if "page" in item:
                item["page"] = 1
            if "anchor" in item:
                item["anchor"]["page"] = 1
        self.pdf = pymupdf.open()
        self.addCleanup(self.pdf.close)
        self.pdf.new_page().insert_textbox(
            pymupdf.Rect(25, 25, 480, 350),
            "Contour forward sloping bench terraces are constructed in this design. "
            "This type of terraces is used in areas with annual rainfall between 200-600 mm/y "
            "and is mainly used for trees and bushes and less for field crops.",
        )
        self.receipt = {
            "source_id": self.spec["source_id"],
            "artifact": {"sha256": self.spec["artifact_sha256"]},
        }
        self.candidate = {
            "nbs_id": self.spec["scope"]["nbs_id"],
            "tables": "T4",
            "families": [],
        }

    def stage(self):
        return extract.stage(self.pdf, self.receipt, self.candidate, self.spec)

    def inclusion(self):
        policy = json.loads((Path(__file__).resolve().parents[2] / "rulesets/nbs-inclusion.json").read_text())
        self.spec["artifact_sha256"] = hashlib.sha256(b"source").hexdigest()
        self.receipt["artifact"]["sha256"] = self.spec["artifact_sha256"]
        return {
            "ruleset": policy["id"], "source_id": self.spec["source_id"],
            "source_sha256": self.spec["artifact_sha256"],
            "nbs_id": self.spec["scope"]["nbs_id"],
            "suitability_family_id": self.spec["scope"]["suitability_family_id"],
            "component_scope": "Synthetic rainwater harvesting package",
            "water_harvesting_purpose": "primary",
            "practice_fit": {"status": "pass", "rationale": "Primary harvesting", "source_locator": "p1"},
            "definition": {"available": True, "kind": "authorised_project_catalogue", "access": "restricted",
                           "edition": "synthetic", "sha256": hashlib.sha256(b"definition").hexdigest(),
                           "general_locator": "general", "practice_locator": "practice",
                           "chapter_mapping_rationale": "Same practice"},
            "criteria": {name: {"status": "pass", "rationale": "Synthetic supported pathway",
                                 "source_locator": "p1", "definition_locator": "criterion"}
                         for name in policy["core_criteria"] + policy["context_criteria"]},
            "conditions": [], "material_conflicts": [],
        }

    def gate(self, assessment):
        return extract.inclusion_gate(self.spec, json.dumps(assessment).encode(), b"source", b"definition")

    def test_current_stamp_and_historical_replay_remain_distinct(self):
        assessment = self.inclusion()
        gate = self.gate(assessment)
        units, inventory = extract.stage(self.pdf, self.receipt, self.candidate, self.spec, inclusion=gate)
        self.assertEqual(units[0]["ruleset_version"], "v1.10.2")
        self.assertEqual(inventory["inclusion"]["decision"], "include_for_scoping")
        old_units, old_inventory = self.stage()
        self.assertEqual(old_units[0]["ruleset_version"], "v1.9.9")
        self.assertNotIn("inclusion", old_inventory)

    def test_other_source_or_family_cannot_borrow_inclusion(self):
        assessment = self.inclusion()
        for key in ("source_id", "suitability_family_id"):
            changed = deepcopy(assessment)
            changed[key] = "other"
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "differs"):
                self.gate(changed)

    def test_secondary_purpose_and_conflict_block_current_staging(self):
        assessment = self.inclusion()
        for changes in ({"water_harvesting_purpose": "secondary"},
                        {"material_conflicts": ["Unresolved ecological harm"]}):
            changed = {**assessment, **changes}
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "Inclusion blocked"):
                self.gate(changed)

    def test_conditional_scope_requires_public_note_without_copying_private_conditions(self):
        assessment = self.inclusion()
        assessment["conditions"] = ["PRIVATE_DEFINITION_DETAIL"]
        gate = self.gate(assessment)
        draft = self.spec["inventory"][0]["draft"]
        draft["context"].pop("note", None)
        with self.assertRaisesRegex(ValueError, "publication-safe"):
            extract.stage(self.pdf, self.receipt, self.candidate, self.spec, inclusion=gate)
        draft["context"]["note"] = "Protect existing habitat and retain vegetation management."
        units, inventory = extract.stage(self.pdf, self.receipt, self.candidate, self.spec, inclusion=gate)
        self.assertNotIn("PRIVATE_DEFINITION_DETAIL", json.dumps(units))
        self.assertIn("PRIVATE_DEFINITION_DETAIL", json.dumps(inventory))

    def test_cli_requires_explicit_current_or_historical_mode(self):
        result = subprocess.run([sys.executable, str(Path(extract.__file__)), "stage",
                                 "--candidates", "missing", "--plan", "missing", "--bundle", "missing",
                                 "--worksheet", "missing", "--out", "missing"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--inclusion-review", result.stderr)
        self.assertIn("--historical-replay", result.stderr)

    def test_replay_and_private_save(self):
        first = self.stage()
        self.assertEqual(first, self.stage())
        (unit,) = first[0]
        self.assertEqual(unit["page"], 1)
        self.assertIn("200-600 mm/y", unit["quote"])
        self.assertFalse(unit["reviewer_ok"])
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "bundle"
            extract.save(out, *first)
            with self.assertRaises(FileExistsError):
                extract.save(out, *first)
            self.assertEqual(json.loads((out / "staging.json").read_bytes()), first[0])

    def test_missing_anchor_or_invented_purpose_rejected(self):
        self.spec["source_purpose"].pop("anchor")
        self.spec["source_purpose"]["quote"] = "made up"
        with self.assertRaises(ValueError):
            self.stage()
        del self.spec["source_purpose"]["quote"]
        with self.assertRaisesRegex(ValueError, "located"):
            self.stage()

    def test_held_purpose_and_no_units(self):
        self.spec["source_purpose"]["disposition"] = "hold"
        with self.assertRaisesRegex(ValueError, "passed purpose"):
            self.stage()
        self.spec["inventory"] = self.spec["inventory"][1:]
        self.assertEqual(self.stage()[0], [])

    def test_edition_and_screened_scope_checked(self):
        for key, value in (
            ("nbs_id", "unrelated"),
            ("tables", "T6"),
            ("families", ["other"]),
        ):
            orig = deepcopy(self.candidate)
            self.candidate[key] = value
            with self.assertRaises(ValueError):
                self.stage()
            self.candidate = orig
        self.spec["artifact_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "edition"):
            self.stage()

    def test_ambiguous_or_nonexistent_page_and_excerpts(self):
        for anchor in (
            {"page": 1, "start": "terraces", "end": "field crops."},
            {"page": 1, "start": "UNKNOWN", "end": "field crops."},
            {"page": 2, "start": "field", "end": "crops."},
        ):
            with self.assertRaises(ValueError):
                extract.passage(self.pdf, anchor)

    def test_legacy_whole_practice_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidates.json"
            report = path.with_name("report.md")
            report.write_text(
                "agroforestry / whole practice / T4 / stock\nSearch closed today\n## Verbatim queries"
            )
            candidate = {"families": [], "tables": "T4", "process": "stock"}
            self.assertEqual(extract.screened_practice(candidate, path), "agroforestry")
            candidate["process"] = "tool"
            with self.assertRaises(ValueError):
                extract.screened_practice(candidate, path)
