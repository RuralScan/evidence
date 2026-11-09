import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from check import read_export


class BrowserExportTests(unittest.TestCase):
    def test_private_values_preserved_and_ambiguous_envelope_refused(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "export.json"
            archive = {"entries": [["vfNotes", '{ "text" : "café" }']]}
            path.write_text(json.dumps(archive), encoding="utf-8")
            self.assertEqual(read_export(path, "source"), archive)
            path.write_text('{"entries":[],"entries":[["private","text"]]}')
            with self.assertRaisesRegex(
                ValueError, "^Cannot read source backup as UTF-8 JSON$"
            ):
                read_export(path, "source")

    def test_refuse_link_and_git_checkout_copy(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            backup = root / "export.json"
            backup.write_text("{}")
            link = root / "link"
            link.symlink_to(backup)
            with self.assertRaisesRegex(ValueError, "outside Git"):
                read_export(link, "destination")
            (root / ".git").write_text("gitdir: elsewhere")
            with self.assertRaisesRegex(ValueError, "outside Git"):
                read_export(backup, "destination")
