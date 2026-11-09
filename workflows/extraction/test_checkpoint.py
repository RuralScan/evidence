"""Exercise capture, reconciliation and exact restoration of pending batches."""

from argparse import Namespace
import csv
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import checkpoint as cp
from handoff import changed_fields


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        ev = self.repo / cp.EV
        ev.parent.mkdir(parents=True)
        self.stored = {
            "evidence_id": "one",
            "source_id": "source",
            "variable": "rain",
            "quote": "The measured seasonal rainfall.",
            "page": 2,
        }
        with ev.open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=[*self.stored, "review_state", "reviewer_ok"]
            )
            writer.writeheader()
            writer.writerow(
                {**self.stored, "review_state": "dropped", "reviewer_ok": "false"}
            )
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.pin = self.git("rev-parse", "HEAD")
        self.stage = self.root / "inputs"
        self.stage.mkdir()
        (self.stage / "staging.json").write_text(
            json.dumps([self.stored, self.stored | {"evidence_id": "two"}])
        )
        (self.stage / "inventory.json").write_bytes(b'{"unit_count":2}\r\n')
        (self.stage / "another.json").write_text(
            json.dumps(
                [
                    self.stored | {"page": 3, "review_state": "dropped"},
                    {"quote": "No ID"},
                ]
            )
        )
        (self.stage / "empty.json").write_text("[]")
        (self.stage / "broken.json").write_text('[{"value":1e999}]')
        self.args = Namespace(
            ciat_repo=self.repo,
            revision=self.pin,
            staging_dir=self.stage,
            units=["staging.json", "another.json", "empty.json", "broken.json"],
            companion=[],
            bundle=self.root / "private.zip",
            details=True,
            at=None,
            export_to=self.root / "restored",
        )

    def git(self, *args):
        return subprocess.check_output(
            [
                "git",
                "-C",
                self.repo,
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            text=True,
        ).strip()

    def test_mixed_batch_roundtrip(self):
        result = cp.capture(self.args)
        self.assertEqual(
            result["unit_statuses"],
            {
                "registered_fields_match": 1,
                "registered_fields_differ": 1,
                "unregistered_id": 1,
                "invalid_identity": 1,
            },
        )
        self.assertEqual(
            result["file_statuses"],
            {"inspected": 2, "malformed_json": 1, "empty_unit_list": 1},
        )
        self.assertEqual(result["distinct_repeated_ids"], 1)
        self.assertEqual(result["occurrences_setting_review_fields"], 1)
        self.args.sha256 = result["archive_sha256"]
        receipt = cp.verify(self.args)
        self.assertEqual(receipt["unit_file_order"], self.args.units)
        exact, new = receipt["files"]["staging.json"]["units"]
        self.assertTrue(exact["stored_as_dropped"])
        self.assertTrue(exact["repeated_id"])
        self.assertEqual(new["other_registered_passage_ids"], ["one"])
        self.assertEqual(
            receipt["files"]["another.json"]["units"][0]["changed_fields"], ["page"]
        )
        for path in self.stage.iterdir():
            out = self.args.export_to / "staging" / path.name
            self.assertEqual(out.read_bytes(), path.read_bytes())
            self.assertEqual(out.stat().st_mode & 0o222, 0)
        with self.assertRaisesRegex(ValueError, "new destination"):
            cp.verify(self.args)

    def test_change_after_capture_or_checksum_failure(self):
        self.args.sha256 = cp.capture(self.args)["archive_sha256"]
        (self.stage / "staging.json").write_text("[]")
        self.assertEqual(cp.verify(self.args)["captured"]["unit_occurrences"], 4)
        self.args.sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum differs"):
            cp.verify(self.args)

    def test_reject_path_escape_and_aliases(self):
        for path in [
            "../outside.json",
            "/absolute.json",
            ".GiT/config.json",
            "drive:relative.json",
            "a/./b.json",
        ]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                cp.filename(path)
        (self.stage / "link.json").symlink_to(self.stage / "staging.json")
        with self.assertRaisesRegex(ValueError, "regular file"):
            cp.select(self.stage, ["link.json"], [])
        with self.assertRaisesRegex(ValueError, "more than once"):
            cp.select(self.stage, ["staging.json", "staging.json"], [])

    def test_nested_json_field_types(self):
        self.assertEqual(
            changed_fields({"context": {"x": [1]}}, {"context": {"x": [True]}}),
            ["context"],
        )
        self.assertEqual(
            changed_fields({"context": {"x": [1]}}, {"context": {"x": [1.0]}}), []
        )
