"""Exercise committed-table transfer independently of local review state."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from rehearse import TABLES, check_bundle, create, export_tables, history


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "-q")
        for path in TABLES:
            member = self.repo / path
            member.parent.mkdir(parents=True, exist_ok=True)
            member.write_bytes(b"id,value\n1,initial\n")
        self.log = self.repo / "pipeline/metrics/review_log.csv"
        self.original = self.log.read_bytes()
        (self.repo / "unrelated.txt").write_text("private unrelated file")
        self.base = self.commit()
        self.changed = b"id,value\r\n1,drop\r\n1,drop\r\n"
        self.log.write_bytes(self.changed)
        self.middle = self.commit()
        self.log.write_bytes(self.original)
        self.target = self.commit()
        self.bundle = self.root / "seed.zip"
        self.records = history(self.repo, self.base, self.target)

    def git(self, *args):
        return (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-C",
                    self.repo,
                    *args,
                ]
            )
            .decode()
            .strip()
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def test_intermediate_state_and_dirty_checkout(self):
        self.log.write_text("pending local decisions")
        create(self.repo, self.records, self.bundle)
        self.assertEqual(len(self.records["changes"]), 2)
        with ZipFile(self.bundle) as archive:
            check_bundle(archive, self.records, self.repo)
            for rev, expected in [
                (self.base, self.original),
                (self.middle, self.changed),
                (self.target, self.original),
            ]:
                directory = self.root / rev
                export_tables(archive, self.records, rev, directory, self.repo)
                tree = directory / rev
                self.assertEqual(
                    (tree / "pipeline/metrics/review_log.csv").read_bytes(), expected
                )
                self.assertEqual(
                    {
                        f.relative_to(tree).as_posix()
                        for f in tree.rglob("*")
                        if f.is_file()
                    },
                    set(TABLES),
                )
            self.assertEqual(
                len(archive.namelist()), 3
            )  # Manifest and two distinct file versions.
        self.assertEqual(self.log.read_text(), "pending local decisions")

    def test_reject_existing_and_git_destinations(self):
        create(self.repo, self.records, self.bundle)
        with self.assertRaisesRegex(ValueError, "new destination"):
            create(self.repo, self.records, self.bundle)
        with self.assertRaisesRegex(ValueError, "outside Git"):
            create(self.repo, self.records, self.repo / "seed.zip")
        with ZipFile(self.bundle) as archive:
            existing = self.root / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(ValueError, "new destination"):
                export_tables(archive, self.records, self.base, existing, self.repo)
            self.assertEqual(list(existing.iterdir()), [])

    def test_tamper_rejected_before_export(self):
        create(self.repo, self.records, self.bundle)
        other = self.root / "modified.zip"
        with ZipFile(self.bundle) as original, ZipFile(other, "w") as changed:
            for name in original.namelist():
                data = original.read(name)
                changed.writestr(
                    name, data if name == "manifest.json" else b"x" * len(data)
                )
        with (
            ZipFile(other) as archive,
            self.assertRaisesRegex(ValueError, "differs from Git"),
        ):
            check_bundle(archive, self.records, self.repo)

    def test_unexpected_member_and_incomplete_export(self):
        create(self.repo, self.records, self.bundle)
        out = self.root / "restored"
        with ZipFile(self.bundle) as archive:
            with patch.object(
                archive, "read", side_effect=[self.original, OSError("read failed")]
            ):
                with self.assertRaisesRegex(OSError, "read failed"):
                    export_tables(archive, self.records, self.target, out, self.repo)
        self.assertFalse(out.exists())
        with ZipFile(self.bundle, "a") as archive:
            archive.writestr("unrelated.txt", b"not part of the snapshot")
        with (
            ZipFile(self.bundle) as archive,
            self.assertRaisesRegex(ValueError, "inventory differs"),
        ):
            check_bundle(archive, self.records, self.repo)

    def test_review_support_replays_absent_empty_and_deleted_files(self):
        gap = "pipeline/metrics/gaps.csv"
        path = self.repo / gap
        path.write_bytes(b"")
        empty = self.commit()
        path.write_bytes(b"id,status\r\n1,reported\r\n")
        reported = self.commit()
        path.unlink()
        retired = self.commit()
        state = history(self.repo, self.target, retired, "review-support")
        self.assertIsNone(state["initial"][gap])
        self.assertEqual(state["changes"][-1]["updates"], {gap: None})
        create(self.repo, state, self.bundle)
        with ZipFile(self.bundle) as archive:
            check_bundle(archive, state, self.repo)
            for revision, content in [
                (self.target, None),
                (empty, b""),
                (reported, b"id,status\r\n1,reported\r\n"),
                (retired, None),
            ]:
                out = self.root / revision
                export_tables(archive, state, revision, out, self.repo)
                copy = out / revision / gap
                if content is None:
                    self.assertFalse(copy.exists())
                else:
                    self.assertEqual(copy.read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "differs"):
                check_bundle(
                    archive, history(self.repo, self.target, retired), self.repo
                )

    def test_profiles_are_distinct_even_without_support_records(self):
        core = history(self.repo, self.base, self.base)
        support = history(self.repo, self.base, self.base, "review-support")
        self.assertEqual(
            set(core), {"format_version", "initial", "base", "target", "changes"}
        )
        self.assertEqual(core["format_version"], 1)
        self.assertEqual(support["format_version"], 2)
        self.assertEqual(support["profile"], "review-support")
        create(self.repo, core, self.bundle)
        with (
            ZipFile(self.bundle) as archive,
            self.assertRaisesRegex(ValueError, "differs"),
        ):
            check_bundle(archive, support, self.repo)

    def test_core_required_and_linked_support_paths_rejected(self):
        link = self.repo / "pipeline/review_priorities.csv"
        link.symlink_to(self.repo / "unrelated.txt")
        commit = self.commit()
        with self.assertRaisesRegex(ValueError, "regular file"):
            history(self.repo, commit, commit, "review-support")
        link.unlink()
        self.log.unlink()
        missing = self.commit()
        with self.assertRaisesRegex(ValueError, "Required tables missing"):
            history(self.repo, missing, missing, "review-support")

    def test_only_literal_first_parent_commits(self):
        self.assertEqual(history(self.repo, self.base, self.base)["changes"], [])
        with self.assertRaisesRegex(ValueError, "first-parent"):
            history(self.repo, self.target, self.base)
        self.git("replace", self.middle, self.target)
        self.assertEqual(history(self.repo, self.base, self.target), self.records)
        tree = self.git("rev-parse", "HEAD^{tree}")
        with self.assertRaisesRegex(ValueError, "Expected a Git commit"):
            history(self.repo, tree, tree)
