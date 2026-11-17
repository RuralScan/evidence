"""Source previews must be matched to acquired bytes, a cited page and a public source."""

import json
import tempfile
import unittest
from pathlib import Path

import fitz
from source_previews import build, signature


class PreviewTests(unittest.TestCase):
    def test_page_match_and_restricted_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            passage = "Wetlands can reduce flood damage under these conditions."
            for sid in ("public", "restricted"):
                with fitz.open() as doc:
                    doc.new_page().insert_text((50, 80), "Different page")
                    doc.new_page().insert_text((50, 80), passage)
                    doc.save(root / (sid + ".pdf"))
            sources = [
                {"source_id": "public", "access_status": "open_access"},
                {"source_id": "restricted", "access_status": "paywalled"},
            ]
            finding = {
                "evidence_id": "table",
                "source_id": "public",
                "page": 2,
                "quote": passage,
                "locator_type": "page",
                "claim_basis": "table",
            }
            findings = [
                finding,
                dict(finding, evidence_id="wrong_page", page=1),
                dict(finding, evidence_id="restricted", source_id="restricted"),
            ]
            queue = {
                "registers": {
                    "EV_evidence_register": findings,
                    "SRC_source_register": sources,
                }
            }
            dest = root / "published"
            self.assertEqual(build(queue, root, dest), 1)
            item = json.loads((dest / "index.json").read_text())["table"]
            self.assertEqual(item["match"], passage)
            self.assertTrue(item["boxes"])
            self.assertTrue((dest / "pages" / item["image"]).is_file())
            self.assertNotEqual(
                item["key"], signature(dict(finding, page=1), sources[0])
            )
            self.assertNotEqual(
                item["key"],
                signature(finding, dict(sources[0], access_status="unknown")),
            )
