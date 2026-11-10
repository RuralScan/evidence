"""Check that notebook criteria continue to identify the same workbook functions."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from public_workbook.haiti import match_criteria  # noqa: E402


class CriteriaTests(unittest.TestCase):
    def test_match_in_runtime_order_and_reject_changed_functions_or_weights(self):
        row = dict(
            rule_id="slope",
            function_id="curve",
            function_fingerprint="hash",
            criterion_weight="0.5",
        )
        criterion = dict(
            rule_id="slope",
            function_id="curve",
            function_fingerprint="hash",
            weight=0.5,
        )
        self.assertEqual(
            match_criteria([row], [criterion]), [{"id": "slope", "weight": 0.5}]
        )
        for key, value in (
            ("rule_id", "soil"),
            ("function_id", "other"),
            ("function_fingerprint", "changed"),
            ("weight", 1.0),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                match_criteria([row], [dict(criterion, **{key: value})])
        with self.assertRaises(ValueError):
            match_criteria([row, row], [criterion, criterion])
