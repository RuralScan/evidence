from hashlib import sha256
import json
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
import unittest

from check import verify


class RulesetCatalogTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.repo = Path(folder.name)
        self.path = ".agents/skills/_versions/v1.5.1/extract-evidence_SKILL.md"
        data = b'---\nversion: "v1.4.1"\n---\n'
        entrypoint = self.repo / self.path
        entrypoint.parent.mkdir(parents=True)
        entrypoint.write_bytes(data)
        self.git("init", "-q")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Archive",
        )
        self.entry = {
            "version": "v1.5.1",
            "declared_version": "v1.4.1",
            "revision": self.git("rev-parse", "HEAD"),
            "entrypoint": self.path,
            "files": {self.path: sha256(data).hexdigest()},
        }

    def git(self, *args):
        return run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    def check(self):
        catalog = {
            "format_version": 1,
            "repository": "https://github.com/CIAT/nbs_ruralscan.git",
            "entries": {"historical": self.entry},
        }
        return verify(json.dumps(catalog).encode(), self.repo)["entries"]["historical"]

    def test_committed_bytes_and_distinct_header_and_stamp(self):
        (self.repo / self.path).write_text("edited locally")
        entry = self.check()
        self.assertEqual(
            (entry["version"], entry["declared_version"]), ("v1.5.1", "v1.4.1")
        )
        self.assertEqual(entry["verified_files"], 1)
        self.entry["declared_version"] = "v1.5.1"
        with self.assertRaisesRegex(ValueError, "declaration"):
            self.check()

    def test_modified_member_and_missing_companion(self):
        self.entry["files"][self.path] = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksums"):
            self.check()
        del self.entry["files"][self.path]
        with self.assertRaisesRegex(ValueError, "paths"):
            self.check()
