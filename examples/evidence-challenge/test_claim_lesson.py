import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import claim_lesson as lesson


class ClaimLessonTests(unittest.TestCase):
    def test_correct_only_the_invented_limits_and_keep_the_original_worksheet(self):
        original = lesson.read_json(lesson.EXTRACT / "example/terrace-rainfall.json")
        saved = json.dumps(original)
        bad = lesson.worksheet_for_limit(original, "Example observation sentence")
        draft = bad["inventory"][0]["draft"]
        self.assertEqual(
            draft["relationship"]["abs_min"], draft["context"]["reported_values"]["low"]
        )
        self.assertEqual(
            draft["relationship"]["abs_max"],
            draft["context"]["reported_values"]["high"],
        )
        self.assertEqual(
            draft["context"]["source_check"]["parameters"],
            "Example observation sentence",
        )
        self.assertEqual(json.dumps(lesson.correct_worksheet(bad)), saved)
        self.assertEqual(json.dumps(original), saved)

    def test_other_extractor_failures_cannot_count_as_the_intended_rejection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / "terrace/extraction"
            inputs.mkdir(parents=True)
            (inputs / "inventory.json").write_text(
                '{"source_purpose":{"quote":"example"}}'
            )
            error = subprocess.CompletedProcess([], 1, "", "Cannot open PDF")
            with patch.object(lesson.subprocess, "run", return_value=error) as stage:
                with self.assertRaisesRegex(
                    ValueError, "Expected the observed-use gate"
                ):
                    lesson.run(inputs.parent, root, True)
            self.assertEqual(stage.call_count, 1)
            self.assertFalse((root / "claim/corrected-worksheet.json").exists())

    def test_original_run_cannot_be_the_output_directory(self):
        with TemporaryDirectory() as directory:
            run = Path(directory)
            with self.assertRaisesRegex(ValueError, "outside"):
                lesson.run(run, run, True)
            self.assertEqual(list(run.iterdir()), [])
