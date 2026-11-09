"""Verify immutable definitions and exact T0 matches without network access."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check import load_definitions, match_identities
from git_snapshot import git


class Release:
    practices = ("terraces",)

    def setting(self, practice, filename):
        assert practice == "terraces"
        assert filename == "T0_nbs_registry.csv"
        return b"nbs_id,name\nterraces,Terraces\n"


class PairTests(unittest.TestCase):
    def test_inventory_and_identity_bytes_must_match(self):
        with TemporaryDirectory() as tmp:
            model = Path(tmp)
            target = model / "configuration/recipes/terraces/T0_nbs_registry.csv"
            target.parent.mkdir(parents=True)
            target.write_bytes(Release().setting("terraces", target.name))
            match_identities(Release(), model)
            target.write_text("nbs_id,name\nterraces,Different definition\n")
            with self.assertRaisesRegex(ValueError, "bytes differ for terraces"):
                match_identities(Release(), model)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "inventories differ"):
                match_identities(Release(), model)

    def test_reject_changed_manifest_bytes_or_omitted_content(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "source"
            git("init", "--quiet", str(repo))
            model = repo / "data-model"
            (model / "structure").mkdir(parents=True)
            columns = model / "structure/columns.json"
            columns.write_text('{"manifest_version":"0.4.0-structure-frozen"}')
            (model / "spec.md").write_text("Definition")
            git("add", "data-model", cwd=repo)

            def commit():
                git(
                    "-c",
                    "user.name=test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                    cwd=repo,
                )
                return git("rev-parse", "HEAD", cwd=repo).decode().strip()

            content_revision = commit()
            manifest_file = model / "definition-snapshot.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "format_version": 1,
                        "kind": "method_definitions",
                        "structure_version": "0.4.0-structure-frozen",
                        "source_revision": content_revision,
                        "sha256": {
                            "data-model/structure/columns.json": sha256(
                                columns.read_bytes()
                            ).hexdigest()
                        },
                    }
                )
            )
            git("add", "data-model/definition-snapshot.json", cwd=repo)
            lock = {
                "repository": "https://github.com/RuralScan/method.git",
                "revision": commit(),
                "manifest": "data-model/definition-snapshot.json",
                "sha256": "0" * 64,
            }
            with self.assertRaisesRegex(ValueError, "manifest checksum mismatch"):
                load_definitions(root / "manifest-mismatch", lock, repo)
            lock["sha256"] = sha256(manifest_file.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "inventory or checksum mismatch"):
                load_definitions(root / "inventory-mismatch", lock, repo)
