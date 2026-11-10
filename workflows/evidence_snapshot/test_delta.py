"""Exercise changed-only archive transfer against a real Git history."""

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from rehearse import TABLES, apply_delta, create, delta_history, export_tables, history


class DeltaTests(unittest.TestCase):
    log = "pipeline/metrics/review_log.csv"
    gap = "pipeline/metrics/gaps.csv"
    priority = "pipeline/review_priorities.csv"

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "-q")
        initial = {name: (name + "\r\n").encode() for name in TABLES}
        self.initial = {**initial, self.gap: b""}
        for name, contents in self.initial.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        self.base = self.commit()

        self.changed_log = b"evidence_id,state\r\nclaim,drop\r\nclaim,drop\r\n"
        (self.repo / self.log).write_bytes(self.changed_log)
        # Content can move to a different path without requiring a new blob.
        (self.repo / self.priority).write_bytes(self.initial[self.log])
        self.middle = self.commit()

        (self.repo / self.log).write_bytes(self.initial[self.log])
        (self.repo / self.priority).write_bytes(b"claim,priority\n")
        (self.repo / self.gap).unlink()
        self.target = self.commit()
        self.records = delta_history(
            self.repo, self.base, self.target, "review-support"
        )
        self.delta = self.root / "delta.zip"
        create(self.repo, self.records, self.delta)

        full = history(self.repo, self.base, self.base, "review-support")
        self.full = self.root / "full.zip"
        create(self.repo, full, self.full)
        out = self.root / "initial"
        with ZipFile(self.full) as archive:
            export_tables(archive, full, self.base, out, self.repo)
        self.seed = out / self.base

    def git(self, *args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=self.repo,
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD").decode().strip()

    def tree(self, root):
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    def test_replay_stores_only_new_blobs_and_preserves_intermediate_history(self):
        with ZipFile(self.delta) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["kind"], "delta")
            self.assertEqual(manifest["format_version"], 3)
            middle, target = manifest["changes"]
            self.assertEqual(
                (middle["revision"], target["revision"]), (self.middle, self.target)
            )
            old_log = manifest["initial"][self.log]
            self.assertEqual(middle["updates"][self.priority], old_log)
            self.assertEqual(target["updates"][self.log], old_log)
            self.assertIsNone(target["updates"][self.gap])
            new_log = middle["updates"][self.log]
            priority = target["updates"][self.priority]
            self.assertEqual(
                set(archive.namelist()),
                {"manifest.json", f"objects/{new_log}", f"objects/{priority}"},
            )
            self.assertEqual(archive.read(f"objects/{new_log}"), self.changed_log)
            for name in ("first", "again"):
                out = self.root / name
                apply_delta(archive, self.records, self.seed, out, self.repo)
                tree = out / self.target
                expected = {
                    path: self.git("show", f"{self.target}:{path}")
                    for path in (*TABLES, self.priority)
                }
                self.assertEqual(self.tree(tree), expected)
                for path in expected:
                    self.assertEqual((tree / path).stat().st_mode & 0o222, 0)
            with self.assertRaises((ValueError, FileExistsError)):
                apply_delta(archive, self.records, self.seed, out, self.repo)
            self.assertEqual(self.tree(tree), expected)
        self.assertEqual(self.tree(self.seed), self.initial)

    def assert_rejected(self, bundle, seed=None):
        out = self.root / "rejected"
        with ZipFile(bundle) as archive, self.assertRaises((ValueError, OSError)):
            apply_delta(archive, self.records, seed or self.seed, out, self.repo)
        self.assertFalse(out.exists())

    def test_edited_missing_and_extra_seed_members(self):
        path = self.seed / self.log
        path.chmod(0o600)
        path.write_bytes(b"newer local decision")
        path.chmod(0o400)
        self.assert_rejected(self.delta)
        self.assertEqual(path.read_bytes(), b"newer local decision")
        path.unlink()
        self.assert_rejected(self.delta)
        path.write_bytes(self.initial[self.log])
        path.chmod(0o400)
        (self.seed / "untracked.csv").write_bytes(b"private")
        self.assert_rejected(self.delta)

    def test_symlinked_seed_file_and_directory(self):
        member = self.seed / self.log
        moved = self.root / "moved.csv"
        member.rename(moved)
        member.symlink_to(moved)
        self.assert_rejected(self.delta)
        member.unlink()
        moved.rename(member)
        directory = self.seed / "schema"
        moved = self.root / "moved"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        self.assert_rejected(self.delta)

    def test_wrong_archive_kind_and_tampered_intermediate_bytes(self):
        self.assert_rejected(self.full)
        baseline = history(self.repo, self.base, self.base, "review-support")
        with ZipFile(self.full) as archive, self.assertRaisesRegex(ValueError, "delta"):
            apply_delta(archive, baseline, self.seed, self.root / "invalid", self.repo)
        changed = self.root / "changed.zip"
        with ZipFile(self.delta) as archive, ZipFile(changed, "w") as altered:
            for name in archive.namelist():
                data = archive.read(name)
                if data == self.changed_log:
                    data = b"x" * len(data)
                altered.writestr(name, data)
        self.assert_rejected(changed)

    def test_empty_increment_still_verifies_seed(self):
        same = delta_history(self.repo, self.base, self.base, "review-support")
        empty = self.root / "empty.zip"
        create(self.repo, same, empty)
        out = self.root / "copy"
        with ZipFile(empty) as archive:
            self.assertEqual(archive.namelist(), ["manifest.json"])
            apply_delta(archive, same, self.seed, out, self.repo)
            nested = self.seed / "out"
            with self.assertRaisesRegex(ValueError, "seed"):
                apply_delta(archive, same, self.seed, nested, self.repo)
            self.assertFalse(nested.exists())
        self.assertEqual(self.tree(out / self.base), self.initial)
