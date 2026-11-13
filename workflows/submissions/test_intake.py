import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import intake

PIN = "16e76d3e76bf9695cf5cda1ef9027e54a121d1f1"


def issue(number, actor, lane, kind, payload, test=True):
    return dict(
        number=number,
        node_id=str(number),
        author_association="MEMBER",
        user=dict(login=actor),
        body=intake.encode(kind, lane, PIN, payload, test=test),
    )


class IntakeTests(unittest.TestCase):
    def test_refuse_wrong_destination(self):
        for name, private in [(intake.INBOX, True), ("elsewhere/public", False)]:
            with patch(
                "intake.gh",
                return_value=dict(
                    private=private,
                    full_name=name,
                    visibility="private" if private else "public",
                    has_issues=True,
                ),
            ) as api:
                with self.assertRaises(ValueError):
                    intake.receive("vote", "T4", PIN, {})
                self.assertEqual(api.call_count, 1)

    def test_retry_recovers_original_remote_receipt(self):
        payload = dict(evidence_id="test_bench_terrace", decision="hold")
        item = issue(17, "reader_a", "T4", "vote", payload)
        item["html_url"] = "https://github.com/RuralScan/evidence/issues/17"
        with (
            patch("intake.signed_in", return_value="reader_a"),
            patch("intake.submissions", return_value=[item]),
            patch("intake.original", return_value="reader_a"),
            patch("intake.gh") as post,
        ):
            self.assertEqual(
                intake.receive("vote", "T4", PIN, payload, test=True), item["html_url"]
            )
            post.assert_not_called()

    def test_public_access_does_not_establish_reviewer_authority(self):
        public = {"author_association": "NONE", "labels": []}
        self.assertFalse(intake.reviewer_eligible(public))
        self.assertTrue(
            intake.reviewer_eligible(
                {**public, "labels": [{"name": "confirmed-reviewer"}]}
            )
        )
        self.assertTrue(
            intake.reviewer_eligible({"author_association": "COLLABORATOR"})
        )

    def test_desk_and_github_line_endings(self):
        row = issue(1, "a", "T4", "vote", {})
        self.assertEqual(
            intake.decode(row),
            intake.decode({**row, "body": row["body"].replace("\n", "\r\n")}),
        )

    def test_cli_refuses_another_reviewers_csv_before_publication(self):
        with (
            patch("intake.signed_in", return_value="reader_a"),
            patch("intake.gh") as post,
        ):
            with self.assertRaisesRegex(ValueError, "signed-in"):
                intake.receive(
                    "csv",
                    "T4",
                    PIN,
                    "evidence_id,reviewer,decision\ntest_bench_terrace,b,approve",
                    test=True,
                )
            post.assert_not_called()

    def test_edited_or_misattributed_body(self):
        item = issue(1, "a", "T4", "vote", {})
        for author, edited in [("b", None), ("a", "yesterday")]:
            with patch(
                "intake.gh",
                return_value={
                    "data": {
                        "node": {
                            "author": {"login": author},
                            "body": item["body"],
                            "lastEditedAt": edited,
                        }
                    }
                },
            ):
                with self.assertRaisesRegex(ValueError, "Edited"):
                    intake.original(item)

    @unittest.skipUnless(os.getenv("CIAT_TEST_REPO"), "Requires pinned Git objects")
    def test_signed_csv_dashboard_conflict_and_retry(self):
        repo = Path(os.environ["CIAT_TEST_REPO"])
        cohort = intake.Cohort(repo, PIN)
        rows = [
            issue(
                1,
                "reader_a",
                "T4",
                "vote",
                dict(evidence_id="test_bench_terrace", decision="approve"),
            ),
            issue(
                2,
                "reader_b",
                "T4",
                "csv",
                "evidence_id,reviewer,decision,reason\ntest_bench_terrace,reader_b,reject,wrong_variable",
            ),
            issue(
                3,
                "reader_a",
                "T3/T6",
                "vote",
                dict(evidence_id="test_hazard_scorecard", decision="hold"),
            ),
        ]
        rows.extend(
            [
                {
                    **issue(
                        5,
                        "guest",
                        "T4",
                        "vote",
                        dict(
                            evidence_id="test_bench_terrace",
                            decision="reject",
                            reason="other",
                        ),
                    ),
                    "author_association": "NONE",
                },
                {**rows[0], "number": 6, "body": intake.HEADER + "\n{malformed"},
            ]
        )
        for index, actor in [(1, "impostor")]:
            with self.assertRaisesRegex(ValueError, "signed-in"):
                intake.vote_rows(intake.decode(rows[index]), actor, cohort)
        with self.assertRaisesRegex(ValueError, "outside"):
            intake.vote_rows(
                {**intake.decode(rows[0]), "test": False}, "reader_a", cohort
            )
        with self.assertRaisesRegex(ValueError, "outside"):
            intake.vote_rows(
                {**intake.decode(rows[0]), "lane": "T3/T6"}, "reader_a", cohort
            )
        with (
            TemporaryDirectory() as directory,
            patch("intake.original", side_effect=lambda i: i["user"]["login"]),
        ):
            for count, items in enumerate((rows, [*rows, {**rows[0], "number": 4}])):
                out = Path(directory) / str(count)
                intake.collect(items, repo, PIN, out, test=True)
                result = json.loads((out / "consensus.json").read_bytes())
                self.assertEqual(result["conflicted_ids"], 1)
                self.assertEqual(sum(result["applied"].values()), 1)
                self.assertTrue(result["second_replay_byte_identical"])
                statuses = {
                    r["number"]: r["status"]
                    for r in json.loads((out / "receipts.json").read_bytes())[
                        "receipts"
                    ]
                }
                self.assertEqual(statuses[5], "pending reviewer confirmation")
                self.assertEqual(statuses[6], "held")

    def test_extraction_keeps_roles_and_prevents_signoff(self):
        for lane, role in [("T4", "structural_suitability"), ("T3/T6", "nbs_effect")]:
            row = dict(
                use_role=role,
                reviewer_ok=False,
                evidence_id="test",
                quote="from source",
            )
            with (
                TemporaryDirectory() as tmp,
                patch("intake.check", return_value=0) as gate,
            ):
                folder = Path(tmp)
                entry = {"lane": lane, "payload": [row]}
                self.assertEqual(
                    intake.extraction(entry, folder, folder, folder)["status"],
                    "validated",
                )
                self.assertEqual(gate.call_count, 2)
                with self.assertRaisesRegex(ValueError, "lane"):
                    intake.extraction(
                        {**entry, "lane": "T4" if lane != "T4" else "T3/T6"},
                        folder,
                        folder,
                        folder,
                    )
                with self.assertRaisesRegex(ValueError, "review state"):
                    intake.extraction(
                        {**entry, "payload": [{**row, "reviewer_ok": True}]},
                        folder,
                        folder,
                        folder,
                    )


if __name__ == "__main__":
    unittest.main()
