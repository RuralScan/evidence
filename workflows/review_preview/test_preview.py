"""Guard the public example and private-copy input boundary."""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from preview import EV, HERE, HISTORY, load_inputs, read_copy
from worker import split_reclassification_targets


class PreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.records = root / "records"
        self.pending = root / "pending"
        self.repo = root / "git"
        shutil.copytree(HERE / "example/records", self.records)
        shutil.copytree(HERE / "example/pending", self.pending)
        shutil.copytree(self.records, self.repo)
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "Example")
        self.pin = self.git("rev-parse", "HEAD")

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

    def test_partial_pending_pair_and_changed_export(self):
        (self.pending / "decisions.json").unlink()
        data = load_inputs(self.records, self.pending, self.repo, self.pin)
        self.assertIsNone(data["pipeline/review/decisions.json"])
        (self.records / EV).write_text("changed")
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            load_inputs(self.records, self.pending, self.repo, self.pin)

    def test_missing_clarification_history_is_not_assumed_empty(self):
        (self.records / HISTORY).unlink()
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            load_inputs(self.records, self.pending, self.repo, self.pin)

    def test_empty_directory_and_symlink_refused(self):
        for name in ("decisions.json", "clarifications.json"):
            (self.pending / name).unlink()
        with self.assertRaisesRegex(ValueError, "file required"):
            load_inputs(self.records, self.pending, self.repo, self.pin)
        (self.pending / "decisions.json").symlink_to(self.records / EV)
        with self.assertRaisesRegex(ValueError, "inside the selected copy"):
            read_copy(self.pending, "decisions.json")

    def test_same_verdict_can_have_divergent_targets(self):
        store = json.loads((self.pending / "decisions.json").read_bytes())
        self.assertEqual(split_reclassification_targets(store), 0)
        store["extra"] = {
            "a": {"decision": "reclassify", "taxon": "crop A"},
            "b": {"decision": "reclassify", "taxon": "crop B"},
        }
        self.assertEqual(split_reclassification_targets(store), 1)
