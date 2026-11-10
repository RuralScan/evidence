"""Verify that a saved batch is compared by claim and by ordered history."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compare import batch_changes
from preview import EV, LOG


class BatchComparisonTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.before = Path(temp.name) / "before"
        self.after = Path(temp.name) / "after"

    def records(self, root, rows, log=""):
        for path, body in [(EV, rows), (LOG, log)]:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("evidence_id,value\n" + body, encoding="utf-8")

    def test_equal_totals_can_hide_added_removed_modified_and_missing_claims(self):
        self.records(self.before, "edited,1\nremoved,1\nunrelated,1\n")
        self.records(self.after, "edited,2\nadded,1\nunrelated,2\n")
        pending = [{"issue_id": "pending", "evidence_ids": ["added", "edited"]}]
        result = batch_changes(
            self.before, self.after, ["edited", "removed", "missing"], pending, [], []
        )
        self.assertEqual(result["batch_evidence_ids"], 4)
        self.assertEqual(
            result["evidence_row_changes"],
            {
                "added": ["added"],
                "modified": ["edited"],
                "removed": ["removed"],
                "missing_at_both": ["missing"],
            },
        )

    def test_history_keeps_per_claim_order_duplicates_and_event_contents(self):
        rows = "reordered,1\nduplicate,1\nedited,1\nunrelated,1\n"
        self.records(
            self.before, rows, "reordered,A\nduplicate,B\nreordered,C\nedited,X\n"
        )
        self.records(
            self.after,
            rows,
            "reordered,C\nduplicate,B\nduplicate,B\nreordered,A\nedited,Y\nunrelated,Z\n",
        )
        result = batch_changes(
            self.before, self.after, ["reordered", "duplicate", "edited"], [], [], []
        )
        self.assertEqual(
            result["review_history_changed_ids"], ["duplicate", "edited", "reordered"]
        )
        self.assertFalse(any(result["evidence_row_changes"].values()))

    def test_thread_replies_follow_issue_ids_without_inventing_claim_ids(self):
        self.records(self.before, "linked,1\nother,1\n")
        self.records(self.after, "linked,1\nother,1\n")
        original = [{"issue_id": "linked-issue", "evidence_ids": ["linked"]}]
        updated = original + [
            {"issue_id": "linked-issue", "action": "reply"},
            {"issue_id": "open-issue", "action": "reply"},
            {"issue_id": "unrelated", "evidence_ids": ["other"]},
        ]
        pending = [{"issue_id": "open-issue"}]
        result = batch_changes(
            self.before, self.after, ["linked"], pending, original, updated
        )
        self.assertEqual(result["clarification_history_changed_ids"], ["linked"])
        self.assertEqual(result["pending_issues_without_linked_claims"], 1)
        self.assertEqual(result["pending_issues_with_changed_history"], 1)
        self.assertEqual(result["batch_evidence_ids"], 1)

        unchanged = batch_changes(
            self.after, self.after, ["linked"], pending, updated, updated
        )
        self.assertFalse(any(unchanged["evidence_row_changes"].values()))
        self.assertEqual(unchanged["review_history_changed_ids"], [])
        self.assertEqual(unchanged["clarification_history_changed_ids"], [])
        self.assertEqual(unchanged["pending_issues_with_changed_history"], 0)

    def test_pending_issue_only_inherits_its_explicit_historical_claim(self):
        self.records(self.before, "linked,first\nunrelated,first\n")
        self.records(self.after, "linked,corrected\nunrelated,corrected\n")
        history = [{"issue_id": "thread", "evidence_ids": ["linked"]}]
        changes = batch_changes(
            self.before, self.after, [], [{"issue_id": "thread"}], history, history
        )
        self.assertEqual(changes["evidence_row_changes"]["modified"], ["linked"])
        self.assertEqual(changes["pending_issues_without_linked_claims"], 0)
