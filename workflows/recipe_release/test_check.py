"""Check the distinction between analytical mappings and function options."""

import json
import unittest
import io
from contextlib import redirect_stderr
from unittest.mock import patch
import check

from check import practice_counts


class Release:
    def __init__(self, identifiers):
        self.identifiers = identifiers

    def table(self, practice, table):
        return (
            [{"mapping_id": "first"}, {"mapping_id": "second"}] if table == "T4" else []
        )

    def read_bytes(self, path):
        return json.dumps(
            {
                "rows": [
                    {
                        "rule_id": identifier,
                        "functions": {"a": "hash-a", "b": "hash-b"},
                        "readiness": {
                            "effective_function_id": "a",
                            "execution_ready": False,
                        },
                    }
                    for identifier in self.identifiers
                ]
            }
        ).encode()


class CountTests(unittest.TestCase):
    def test_multiple_options_and_reference_rows(self):
        counts = practice_counts(Release(["first", "second", "reference"]), "practice")
        self.assertEqual(counts["T4 with options"], 2)
        self.assertEqual(counts["T4 with selected function"], 2)
        self.assertEqual(counts["Spatially validated T4"], 0)

    def test_duplicate_readiness_cannot_hide_missing_mapping(self):
        with self.assertRaisesRegex(ValueError, "inventories differ"):
            practice_counts(Release(["first", "first"]), "practice")


class RetiredBuildTests(unittest.TestCase):
    def test_store_required_before_fetch_or_synthesis(self):
        error = io.StringIO()
        with patch("sys.argv", ["check.py"]), patch.object(check, "snapshot") as fetch:
            with redirect_stderr(error), self.assertRaises(SystemExit) as result:
                check.main()
        self.assertEqual(result.exception.code, 2)
        self.assertIn("--store", error.getvalue())
        fetch.assert_not_called()
