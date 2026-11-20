"""T4 retirement preserves historical records without invoking scientific synthesis."""
import json
import unittest
from unittest.mock import patch

import t4_baseline as baseline
from registers import content_digest


class HistoricalT4(unittest.TestCase):
    def test_exact_pin_checksum_and_explicit_status(self):
        rows = [{"mapping_id": "held", "evidence_ids": ["dropped-later"], "weight": 0.5}]
        data = json.dumps({"recipes": {"practice": {baseline.TABLE: rows}}}).encode()
        with patch.object(baseline, "blob", return_value=data) as read, patch.object(
            baseline, "SHA256", content_digest(data)
        ):
            tables, status = baseline.load("repo")
        read.assert_called_once_with("repo", baseline.REVISION, baseline.PATH)
        self.assertEqual(tables["practice"], rows)
        self.assertEqual(status["status"], "historical_baseline")
        self.assertTrue(status["needs_agent_synthesis"])
        self.assertFalse(status["current_evidence_applied"])

    def test_tampered_baseline_fails_closed(self):
        with patch.object(baseline, "blob", return_value=b"{}"):
            with self.assertRaisesRegex(ValueError, "checksum differs"):
                baseline.load("repo")
