"""End-to-end checks for private screening → acquisition handoffs."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

import run


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.title = "Terrace construction guidance for dryland farms"
        self.candidate = {
            "candidate_id": "teaching_manual",
            "title": self.title,
            "citation": f"Technical manual (2000). {self.title}.",
            "url": "https://publisher.example/manual.pdf",
        }
        self.out = self.root / "handoff"
        self.file = self.root / "example.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text((20, 50), self.title)
            doc.save(self.file)
        self.plan = {
            "candidate_id": "teaching_manual",
            "kind": "pdf",
            "publisher_hosts": ["publisher.example"],
            "expected_sha256": hashlib.sha256(self.file.read_bytes()).hexdigest(),
        }

    def write_bundle(self, candidate=None):
        candidate = candidate or self.candidate
        receipt, body = run.acquire(candidate, self.plan, self.file)
        run.publish(self.out, receipt, body)
        return receipt

    def test_immutable_copies_and_detected_library_drift(self):
        receipt = self.write_bundle()
        with patch(
            "identity._crossref", side_effect=AssertionError("check must run offline")
        ):
            self.assertEqual(run.check(self.out, self.plan, self.candidate), receipt)
        library = self.out / "library/teaching_manual.pdf"
        cache = self.out / "cache/teaching_manual.pdf"
        self.assertEqual(cache.read_bytes(), library.read_bytes())
        self.assertFalse(cache.samefile(library))
        with self.assertRaises(FileExistsError):
            run.publish(self.out, receipt, b"other")
        library.write_bytes(b"incorrect")
        with self.assertRaisesRegex(ValueError, "checksum"):
            run.check(self.out, self.plan, self.candidate)

    def test_corrupted_receipt_cannot_rewrite_verification(self):
        receipt = self.write_bundle()
        path = self.out / "receipt.json"
        receipt["metadata"]["status"] = "service_unavailable"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "metadata"):
            run.check(self.out, self.plan, self.candidate)
        receipt["metadata"]["status"] = "title_required"
        receipt["document"]["pages"] += 1
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "Document identity"):
            run.check(self.out, self.plan, self.candidate)

    def test_pin_and_publisher_holds_only_publish_receipt(self):
        for field, value in (
            ("expected_sha256", "0" * 64),
            ("publisher_hosts", ["other.example"]),
        ):
            with self.subTest(field=field):
                plan = self.plan | {field: value}
                receipt, body = run.acquire(self.candidate, plan, self.file)
                out = self.root / field
                run.publish(out, receipt, body)
                self.assertEqual(receipt["status"], "held")
                self.assertEqual([p.name for p in out.iterdir()], ["receipt.json"])
                self.assertEqual(run.check(out, plan, self.candidate), receipt)

    def test_screened_reuse_alias_needs_known_source_identity(self):
        candidate = self.candidate | {"reuse_source_id": "known_manual"}
        with self.assertRaisesRegex(ValueError, "canonical"):
            run.reuse_identity(candidate, self.plan, None)
        path = self.root / "sources.csv"
        data = {
            "source_id": "known_manual",
            "citation": candidate["citation"],
            "doi": "",
        }

        def write(row):
            with path.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=data)
                writer.writeheader()
                writer.writerow(row)

        write(data | {"citation": "Unrelated manual (2001). Another publication."})
        with self.assertRaisesRegex(ValueError, "different citation title"):
            run.reuse_identity(candidate, self.plan, path)
        write(data)
        canonical = run.reuse_identity(candidate, self.plan, path)
        receipt, body = run.acquire(candidate, self.plan, self.file, canonical)
        run.publish(self.out, receipt, body)
        self.assertEqual(
            run.check(self.out, self.plan, candidate, path)["source_id"], "known_manual"
        )
        self.assertTrue((self.out / "cache/known_manual.pdf").is_file())
        self.assertFalse((self.out / "cache/teaching_manual.pdf").exists())

    def test_real_legacy_screening_shape_preserves_structured_title(self):
        title = "Dryland terraces. Part II: water harvesting"
        old = self.candidate | {"citation": f"Researcher (1999). {title}. Bulletin."}
        old.pop("title")
        path = self.root / "candidates.json"
        path.write_text(json.dumps([old]))
        with self.assertRaisesRegex(ValueError, "Full screened title"):
            run.selected(path, old["candidate_id"])
        audit = [
            {
                "record_id": old["candidate_id"],
                "title": title,
                "url": old["url"],
                "disposition": "include",
            }
        ]
        (self.root / "screening.json").write_text(json.dumps(audit))
        self.assertEqual(run.selected(path, old["candidate_id"])["title"], title)
        audit[0]["disposition"] = "hold"
        (self.root / "screening.json").write_text(json.dumps(audit))
        with self.assertRaisesRegex(ValueError, "disagree"):
            run.selected(path, old["candidate_id"])

    def test_outage_cannot_switch_to_title_route(self):
        candidate = self.candidate | {"doi": "10.9999/demo"}
        plan = self.plan | {"retry_by_title": True, "artifact_url": candidate["url"]}
        with (
            patch("identity._crossref", return_value=("unavailable", {})),
            patch("run.fetch", side_effect=AssertionError),
        ):
            receipt, body = run.acquire(candidate, plan, None)
        self.assertEqual(
            (receipt["metadata"]["status"], receipt["status"], body),
            ("service_unavailable", "held", None),
        )
        self.assertEqual(candidate["doi"], "10.9999/demo")

    def test_confirmed_doi_mismatch_can_recover_by_publisher_title(self):
        candidate = self.candidate | {"doi": "10.9999/demo"}
        plan = self.plan | {"retry_by_title": True, "artifact_url": candidate["url"]}
        with patch("identity._crossref", return_value=("missing", {})):
            receipt, body = run.acquire(candidate, plan, self.file)
        run.publish(self.out, receipt, body)
        with patch("identity._crossref", side_effect=AssertionError):
            saved = run.check(self.out, plan, candidate)
        self.assertEqual(
            (saved["status"], saved["metadata"]["status"], saved["metadata"]["doi"]),
            ("acquired", "doi_rejected", ""),
        )

    def test_bibliographic_identity_does_not_replace_artifact_check(self):
        candidate = self.candidate | {"doi": "10.9999/demo"}
        record = {
            "DOI": candidate["doi"],
            "title": [self.title],
            "author": [{"family": "Researcher"}],
        }
        with (
            patch("identity._crossref", return_value=("ok", record)),
            patch(
                "run.fetch",
                return_value=(b"unrelated", candidate["url"], "application/pdf"),
            ),
            patch("run.pdf_routes", return_value=([], ["Additional search needed."])),
        ):
            receipt, body = run.acquire(candidate, {"kind": "pdf"}, None)
        self.assertEqual(receipt["metadata"]["status"], "doi_verified")
        self.assertEqual((receipt["status"], body), ("held", None))
        self.assertIn("Additional search", receipt["recovery_notes"][0])

    def test_verified_doi_acquired_and_checked_entirely_offline(self):
        candidate = self.candidate | {"doi": "10.9999/demo"}
        record = {
            "DOI": candidate["doi"],
            "title": [self.title],
            "author": [{"family": "Researcher"}],
        }
        with patch("identity._crossref", return_value=("ok", record)):
            receipt, body = run.acquire(candidate, self.plan, self.file)
        self.assertEqual(receipt["metadata"]["status"], "doi_verified")
        run.publish(self.out, receipt, body)
        with patch("identity._crossref", side_effect=AssertionError):
            self.assertEqual(run.check(self.out, self.plan, candidate), receipt)

    def test_pinned_code_cannot_swap_screened_file(self):
        sha = "1" * 40
        candidate = self.candidate | {
            "url": f"https://github.com/example/project/blob/{sha}/model.py"
        }
        plan = {
            "candidate_id": candidate["candidate_id"],
            "kind": "code",
            "commit": sha,
            "artifact_url": f"https://raw.githubusercontent.com/example/project/{sha}/other.py",
        }
        with self.assertRaisesRegex(ValueError, "full commit"):
            run.acquire(candidate, plan, None)
        plan["artifact_url"] = plan["artifact_url"].replace("other.py", "model.py")
        with patch(
            "run.fetch",
            return_value=(b"print('demo')", plan["artifact_url"], "text/plain"),
        ):
            receipt, body = run.acquire(candidate, plan, None)
        run.publish(self.out, receipt, body)
        self.assertEqual(run.check(self.out, plan, candidate)["status"], "acquired")

    def test_partial_publication_is_rolled_back(self):
        receipt, body = run.acquire(self.candidate, self.plan, self.file)
        with (
            patch("run.shutil.copyfile", side_effect=OSError("simulated full disk")),
            self.assertRaises(OSError),
        ):
            run.publish(self.out, receipt, body)
        self.assertFalse(self.out.exists())
        run.publish(self.out, receipt, body)
        self.assertEqual(run.check(self.out, self.plan, self.candidate), receipt)


if __name__ == "__main__":
    unittest.main()
