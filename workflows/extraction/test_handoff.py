import csv
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

import handoff


class HandoffTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.temp = Path(t.name)
        self.unit = {
            "evidence_id": "old",
            "source_id": "paper",
            "variable": "rain",
            "page": 2,
            "quote": "Rainfall at example site.",
            "relationship": {"unit": "mm"},
            "reviewer_ok": False,
        }
        self.ev = self.temp / "ev.csv"
        with self.ev.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.unit)
            writer.writeheader()
            writer.writerow(
                self.unit | {"relationship": '{"unit":"mm"}', "reviewer_ok": "true"}
            )

    def test_registered_source_replay_keeps_live_review(self):
        before = self.ev.read_bytes()
        handoff.check_replays(self.ev, [self.unit])
        self.assertEqual(before, self.ev.read_bytes())

    def test_changed_or_missing_scientific_field_is_held(self):
        for changed in (
            self.unit | {"quote": "Changed"},
            {k: v for k, v in self.unit.items() if k != "relationship"},
        ):
            with self.assertRaisesRegex(ValueError, "correction"):
                handoff.check_replays(self.ev, [changed])

    def test_archived_check_returns_only_original_fields_and_reports_changes(self):
        message = io.StringIO()
        with redirect_stdout(message):
            (stored,) = handoff.check_replays(
                self.ev,
                [self.unit | {"relationship": None, "page": 3}],
                check_existing=True,
            )
        self.assertEqual(
            stored, {k: v for k, v in self.unit.items() if k != "reviewer_ok"}
        )
        self.assertIn("page, relationship", message.getvalue())
        self.assertIn("held", message.getvalue())
        with self.assertRaisesRegex(ValueError, "no stored row"):
            handoff.check_replays(
                self.ev, [self.unit | {"evidence_id": "new"}], check_existing=True
            )

    def test_renamed_duplicate_held(self):
        with self.assertRaisesRegex(ValueError, "same passage"):
            handoff.check_replays(self.ev, [self.unit | {"evidence_id": "invented"}])

    def test_quote_extension_and_shortening_hold_renamed_unit(self):
        long_quote = "Rainfall at example site. Bench terraces can trap sediment."
        changed = self.unit | {"evidence_id": "invented", "quote": long_quote}
        with self.assertRaisesRegex(ValueError, "overlapping passage"):
            handoff.check_replays(self.ev, [changed])
        self.assertEqual(
            handoff.overlap(long_quote, self.unit["quote"]), "overlapping passage"
        )
        handoff.check_replays(self.ev, [changed | {"page": 3}])
        handoff.check_replays(
            self.ev,
            [changed | {"quote": "Water availability was measured twice annually."}],
        )

    def test_dry_run_isolated_from_supplied_checkout(self):
        ciat = self.temp / "ciat"
        for path in handoff.INPUTS:
            target = ciat / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                self.ev.read_bytes() if path == handoff.EV else b"untouched"
            )
        script = ciat / "scripts/ingest-effects-staging.py"
        script.parent.mkdir()
        script.write_text(
            "import sys\nfrom pathlib import Path\n"
            "assert '--dry-run' in sys.argv and '--allow-structural' in sys.argv\n"
            "root = Path(sys.argv[sys.argv.index('--root') + 1])\n"
            "assert root.resolve() == Path.cwd().resolve()\n"
            f"(root / {handoff.EV!r}).write_text('mutated scratch')\n"
            "raise SystemExit(7)\n"
        )
        staging = self.temp / "staged.json"
        staging.write_text(json.dumps([self.unit]))
        corpus = self.temp / "cache"
        corpus.mkdir()
        result = handoff.check(ciat, staging, corpus, ["--allow-structural"])
        self.assertEqual(result, 7)
        self.assertEqual((ciat / handoff.EV).read_bytes(), self.ev.read_bytes())
        self.assertEqual(json.loads(staging.read_bytes()), [self.unit])
        self.assertEqual(list(corpus.iterdir()), [])
        # The content-only mode calls gate(), never the intake writer script.
        package = ciat / "src/nbs_ruralscan/schema_tools"
        package.mkdir(parents=True)
        (package.parent / "__init__.py").touch()
        (package / "__init__.py").touch()
        (package / "evidence_intake.py").write_text(
            "class EvidenceIntakePaths:\n"
            "    @staticmethod\n    def from_root(root, *, corpus): return root\n"
            "def gate(units, roles, *, paths):\n"
            "    assert 'structural_suitability' in roles and units[0]['quote'] == 'Changed.'\n"
            "    return []\n"
        )
        staging.write_text(json.dumps([self.unit | {"quote": "Changed."}]))
        self.assertEqual(
            handoff.check(
                ciat, staging, corpus, ["--allow-structural"], validate_only=True
            ),
            0,
        )
        with self.assertRaisesRegex(ValueError, "scope option"):
            handoff.check(ciat, staging, corpus, ["--run-id=bad"])


if __name__ == "__main__":
    unittest.main()
