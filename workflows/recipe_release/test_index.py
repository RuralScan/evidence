"""Protect publication boundaries, scope, and read-only regeneration."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check import write_index
from recipe_index import label, scope, table_lines


class IndexTests(unittest.TestCase):
    def test_scope_preserves_family_and_income(self):
        self.assertEqual(
            scope(
                {
                    "suitability_family_id": "example__terracing",
                    "scope_type": "income_group",
                    "scope_id": "lic_lmic",
                }
            ),
            "Terracing / Income group · Low and lower-middle income",
        )
        with self.assertRaisesRegex(ValueError, "Incomplete context"):
            scope({"scope_id": "upper_middle"})

    def test_missing_enum_and_free_text(self):
        self.assertEqual(label(None), "Unspecified")
        self.assertEqual(label("none"), "None")
        with self.assertRaisesRegex(ValueError, "classification"):
            label("Unreviewed prose from source")

    def test_host_crops_visible_without_republishing_private_notes(self):
        crops = ("coffee", "cocoa", "tea")
        records = [
            {
                "mapping_id": crop,
                "variable": "land_cover",
                "suitability_family_id": "example__shaded_perennial",
                "relationship_params": {
                    "host_crop": crop,
                    "crop_authority": "internal note",
                },
            }
            for crop in crops
        ]

        records[0]["relationship_params"]["reviewed_adaptation"] = {
            "numerical_calibration": {"status": "held", "reviewer": "private reviewer"}
        }

        class Release:
            def table(self, practice, table):
                return records

            def read_bytes(self, filename):
                return json.dumps(records, indent=2).encode()

        readiness = {
            crop: {
                "role": "eligibility_gate",
                "functions": {},
                "readiness": {"effective_function_id": None, "execution_ready": False},
            }
            for crop in crops
        }
        text = "\n".join(
            table_lines(Release(), "example", "T4", "rows.json", "revision", readiness)
        )
        for crop in crops:
            self.assertIn(f"Host crop · {crop.capitalize()} |", text)
        self.assertIn("| Held | 0 | No | No |", text)
        self.assertIn("| Not recorded | 0 | No | No |", text)
        self.assertNotIn("private reviewer", text)
        self.assertNotIn("internal note", text)

    def test_existing_index_survives_retry(self):
        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "recipes"
            write_index(destination, {"README.md": "original"})
            with self.assertRaisesRegex(ValueError, "new directory"):
                write_index(destination, {"README.md": "replacement"})
            self.assertEqual((destination / "README.md").read_text(), "original")
