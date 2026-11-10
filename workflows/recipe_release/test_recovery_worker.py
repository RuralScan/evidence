"""Verify how the historical workbook rehearsal reconstructs committed decisions."""

import unittest

from recovery_worker import training_votes


HEADER = b"evidence_id,decision,reason,note,reviewer\n"


class TrainingVoteTests(unittest.TestCase):
    def test_only_latest_eligible_decisions_survive(self):
        earlier = HEADER + b"historic,ok,,,reader\n"
        target = earlier + (
            b"one,ok,,,first\n"
            b'two,drop,scope,"line one\nline two",second\n'
            b"one,query,,reopened,first\n"
            b"three,drop,scope,,third\n"
            b"three,ok,,,fourth\n"
        )
        votes, events = training_votes(earlier, target)
        self.assertEqual(events, 5)
        self.assertEqual(
            votes,
            {
                "two": {
                    "second": {
                        "decision": "drop",
                        "reason": "scope",
                        "note": "line one\nline two",
                    }
                },
                "three": {"fourth": {"decision": "ok", "reason": "", "note": ""}},
            },
        )

    def test_rejects_rewritten_history_and_missing_or_ineligible_votes(self):
        cases = (
            (HEADER + b"one,ok,,,a\n", HEADER + b"one,ok,,,b\n"),
            (HEADER, HEADER),
            (HEADER, HEADER + b"one,query,,new question,a\n"),
            (HEADER, HEADER + b"one,ok,,,\n"),
        )
        for earlier, target in cases:
            with self.subTest(target=target), self.assertRaises(ValueError):
                training_votes(earlier, target)
