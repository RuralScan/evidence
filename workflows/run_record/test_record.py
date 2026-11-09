import copy
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import record


class RunRecordTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workbench = self.base / "workbench"
        self.run = self.base / "private"
        self.run.mkdir()
        (self.workbench / "rulesets").mkdir(parents=True)
        (self.workbench / "rulesets/catalog.json").write_text(
            json.dumps({"format_version": 1, "entries": {"rule": {"version": "1"}}})
        )
        (self.workbench / "guide.md").write_bytes(b"Read the source page.\n")
        (self.run / "input.txt").write_bytes(b"original\r\n")
        (self.run / "proposal.json").write_bytes(b"[]\n")
        (self.run / "prompt.txt").write_bytes("Café\n".encode())
        self.stage = {
            "name": "extract",
            "mode": "ai-assisted",
            "provider": "example",
            "model": "example-model",
            "settings": {"temperature": 0},
            "prompt": "run/prompt.txt",
            "rulesets": ["rule"],
            "instructions": ["workbench/guide.md", "run/prompt.txt"],
            "inputs": ["run/input.txt"],
            "outputs": ["run/proposal.json"],
        }
        self.description = {
            "run_id": "example",
            "scope": "One candidate",
            "limits": "Synthetic example only",
            "stages": [self.stage],
        }
        self.addCleanup(patch.stopall)
        patch.object(record, "WORKBENCH", self.workbench).start()

    def make(self):
        return record.make_record(self.description, self.workbench, self.run)

    def save(self):
        return record.save_record(self.make(), self.run)

    def test_receipt_preserves_slots_exact_hashes_and_moves_with_run(self):
        path = self.save()
        receipt = json.loads(path.read_bytes())
        self.assertEqual(receipt["run"], self.description)
        self.assertEqual(
            set(receipt["sha256"]),
            {
                "workbench/rulesets/catalog.json",
                "workbench/guide.md",
                "run/input.txt",
                "run/prompt.txt",
                "run/proposal.json",
            },
        )
        self.assertEqual(
            receipt["sha256"]["run/input.txt"],
            hashlib.sha256(b"original\r\n").hexdigest(),
        )
        self.assertNotIn(str(self.base), path.read_text())
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        relocated = self.base / "relocated"
        self.run.rename(relocated)
        other_workbench = self.base / "other-workbench"
        shutil.copytree(self.workbench, other_workbench)
        with patch.object(record, "WORKBENCH", other_workbench):
            self.assertEqual(record.verify(relocated, expected), relocated / path.name)

    def test_missing_changed_and_redirected_inputs_outputs_and_instructions(self):
        self.save()
        for path in [
            self.run / "input.txt",
            self.run / "proposal.json",
            self.run / "prompt.txt",
            self.workbench / "guide.md",
            self.workbench / "rulesets/catalog.json",
        ]:
            with self.subTest(file=path.name):
                original = path.read_bytes()
                # Changing whitespace remains valid JSON for the catalog.
                path.write_bytes(original + b" ")
                with self.assertRaises(ValueError):
                    record.verify(self.run)
                path.unlink()
                with self.assertRaises((OSError, ValueError)):
                    record.verify(self.run)
                external = self.base / ("copy-" + path.name)
                external.write_bytes(original)
                path.symlink_to(external)
                with self.assertRaises(ValueError):
                    record.verify(self.run)
                path.unlink()
                path.write_bytes(original)
        record.verify(self.run)

    def test_reject_missing_model_metadata_and_uncaptured_prompt(self):
        for key in ("provider", "model", "prompt"):
            with self.subTest(field=key):
                with patch.dict(self.stage, {key: "   "}):
                    with self.assertRaises(ValueError):
                        self.make()
        for ref in ("run/input.txt", "workbench/guide.md"):
            with self.subTest(prompt=ref):
                with patch.dict(self.stage, {"prompt": ref}):
                    with self.assertRaises(ValueError):
                        self.make()
        for mode in ("manual", "replay"):
            with patch.dict(self.stage, {"mode": mode}):
                with self.assertRaises(ValueError):
                    self.make()

    def test_invalid_stage_declarations_and_paths(self):
        for field, value in (
            ("mode", "other"),
            ("rulesets", ["unknown-rule"]),
            ("instructions", []),
            ("inputs", []),
            ("outputs", []),
            ("inputs", ["/tmp/input"]),
            ("outputs", ["run/../run/input.txt"]),
            ("outputs", ["run/.Git/config"]),
        ):
            with self.subTest(field=field, value=value):
                with patch.dict(self.stage, {field: value}):
                    with self.assertRaises(ValueError):
                        self.make()
        self.description["stages"].append(copy.deepcopy(self.stage))
        with self.assertRaises(ValueError):
            self.make()

    def test_repeat_save_cannot_overwrite_or_leave_temporary_file(self):
        path = self.save()
        original = path.read_bytes()
        members = set(self.run.iterdir())
        self.description["limits"] = "Replacement"
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(set(self.run.iterdir()), members)

    def test_missing_extra_or_changed_checksums_and_changed_metadata(self):
        path = self.save()
        receipt = json.loads(path.read_bytes())
        modifications = [
            lambda r: r["sha256"].pop("run/input.txt"),
            lambda r: r["sha256"].update({"run/unknown": None}),
            lambda r: r["sha256"].update({"run/input.txt": "0" * 64}),
        ]
        for change in modifications:
            altered = copy.deepcopy(receipt)
            change(altered)
            path.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):
                record.verify(self.run)
        path.write_text(json.dumps(receipt))
        trusted = record.digest(path)
        receipt["run"]["scope"] = "Different scope"
        path.write_text(json.dumps(receipt))
        with self.assertRaises(ValueError):
            record.verify(self.run, trusted)

    def test_symlink_receipt_rejected_even_with_matching_content(self):
        path = self.save()
        original = self.base / "outside.json"
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaises(ValueError):
            record.verify(self.run, record.digest(original))
