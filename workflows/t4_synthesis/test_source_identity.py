"""Source admission is provenance, never scientific approval or synthetic EV intake."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t4_synthesis import core, source_identity

REPO = Path(__file__).resolve().parents[2]
SOURCE_ID = "tree_climate_paulsen_korner2014"


class SourceIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        queue = json.loads((REPO / "publication/review-queue.json").read_bytes())
        self.source = next(r for r in queue["registers"]["SRC_source_register"]
                           if r["source_id"] == SOURCE_ID)
        self.path = self.root / "operations" / f"source-{SOURCE_ID}.json"
        self.path.parent.mkdir()
        shutil.copyfile(REPO / self.path.relative_to(self.root), self.path)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.commit()

    def commit(self):
        core.git(self.root, "add", ".")
        core.git(self.root, "-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-qm", "Fixture provenance")

    def basis(self):
        return source_identity.project(self.root, [self.source])[SOURCE_ID]

    def test_admitted_doi_source_without_src_flags_has_frozen_verified_basis(self):
        original = copy.deepcopy(self.source)
        self.assertNotIn("doi_verified", self.source)
        basis = self.basis()
        self.assertEqual(basis["basis"], "admitted_acquisition")
        self.assertTrue(source_identity.verified(self.source, basis))
        self.assertEqual(self.source, original)
        self.assertEqual(self.source["extraction_status"], original["extraction_status"])
        self.assertEqual(basis["operation_sha256"], core.digest(self.path.read_bytes()))

    def test_all_six_protected_admissions_have_eligible_identity_only(self):
        queue = json.loads((REPO / "publication/review-queue.json").read_bytes())
        expected = {
            "tree_climate_zomer2022", "tree_climate_paulsen_korner2014",
            "tree_climate_brun2022", "tree_climate_urquiaga2026",
            "fmnr_kenya_wanjira2020", "tree_climate_csfd2011",
        }
        rows = [r for r in queue["registers"]["SRC_source_register"]
                if r["source_id"] in expected]
        self.assertEqual({r["source_id"] for r in rows}, expected)
        for source in rows:
            with self.subTest(source=source["source_id"]):
                original = copy.deepcopy(source)
                basis = source_identity.project(REPO, [source])[source["source_id"]]
                self.assertTrue(source_identity.verified(source, basis))
                self.assertEqual(source, original)

    def test_changed_source_identity_or_edition_rejected(self):
        for changes in ({"doi": "10.0000/wrong"}, {"citation": "Different paper"},
                        {"artifact_sha1": "a" * 40}, {"library_path": "other/file.pdf"},
                        {"url": "https://example.invalid/other.pdf"}):
            with self.subTest(changes=changes):
                changed = self.source | changes
                with self.assertRaisesRegex(ValueError, "differs from current source"):
                    source_identity.project(self.root, [changed])

    def test_uncommitted_or_deleted_record_cannot_fall_back_to_a_flag(self):
        self.source["doi_verified"] = True
        self.path.write_text(self.path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "committed verification record"):
            self.basis()
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing or linked"):
            self.basis()

    def test_committed_deletion_cannot_restore_legacy_flag_eligibility(self):
        self.source["doi_verified"] = True
        core.git(self.root, "rm", "--", str(self.path.relative_to(self.root)))
        self.commit()
        with self.assertRaisesRegex(ValueError, "Deleted source admission"):
            self.basis()

    def test_missing_document_verification_cannot_be_rescued_by_metadata(self):
        op = json.loads(self.path.read_bytes())
        op["operation"]["receipt"]["document"]["verified"] = False
        self.path.write_text(json.dumps(op))
        self.commit()
        with self.assertRaisesRegex(ValueError, "Invalid acquired receipt"):
            self.basis()

    def test_forged_crossref_doi_rejected_even_when_hashes_recalculated(self):
        op = json.loads(self.path.read_bytes())
        op["operation"]["receipt"]["metadata"]["crossref"]["record"]["DOI"] = "10.0000/wrong"
        self.path.write_text(json.dumps(op))
        self.commit()
        with self.assertRaisesRegex(ValueError, "metadata disagrees"):
            self.basis()

    def test_basis_is_bound_to_source_and_operation_bytes(self):
        basis = self.basis()
        with self.assertRaisesRegex(ValueError, "source snapshot"):
            source_identity.verified(self.source | {"citation": "changed"}, basis)
        basis["operation_json"] += "\n"
        with self.assertRaisesRegex(ValueError, "recorded hash"):
            source_identity.verified(self.source, basis)

    def test_literal_legacy_verification_compatibility_has_no_inferred_stamp(self):
        source = {"source_id": "legacy", "title_verified": True}
        basis = source_identity.project(self.root, [source])["legacy"]
        self.assertEqual(basis["basis"], "legacy_source_flag")
        self.assertTrue(source_identity.verified(source, basis))
        self.assertTrue(source_identity.verified(source, None))
        self.assertFalse(source_identity.verified({"title_verified": "true"}, None))
        unverified = {"source_id": "unverified"}
        self.assertFalse(source_identity.verified(unverified, source_identity.project(
            self.root, [unverified])["unverified"]))

    def test_uncommitted_hand_written_source_record_is_not_identity_proof(self):
        core.git(self.root, "rm", "--", str(self.path.relative_to(self.root)))
        self.commit()
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_bytes((REPO / self.path.relative_to(self.root)).read_bytes())
        with self.assertRaisesRegex(ValueError, "must be committed"):
            self.basis()


if __name__ == "__main__":
    unittest.main()
