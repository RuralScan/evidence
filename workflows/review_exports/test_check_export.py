"""Check file classification, scoped identity and multi-reviewer collision reporting."""

from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from check_export import (
    HERE,
    evidence_checks,
    export_rows,
    missing_compiled_ids,
    private_file,
)


class ExportTests(unittest.TestCase):
    def test_browser_formats_and_wrong_shape(self):
        for filename, expected in (("evidence.csv", "evidence"), ("rows.csv", "rows")):
            kind, rows = export_rows((HERE / "example" / filename).read_bytes())
            self.assertEqual(kind, expected)
            self.assertTrue(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            export_rows(b"evidence_id,evidence_id\na,a\n")
        with self.assertRaisesRegex(ValueError, "Malformed"):
            export_rows(b"batch,record_id\nb,x,extra\n")
        with self.assertRaisesRegex(ValueError, "browser CSV"):
            export_rows(b"decision,evidence_id\napprove,a\n")

    def test_bom_preserves_native_importer_semantics(self):
        bom = b"\xef\xbb\xbf"
        example = (HERE / "example/evidence.csv").read_bytes()
        self.assertEqual(export_rows(bom + example)[0], "evidence")
        with self.assertRaisesRegex(ValueError, "BOM must start"):
            export_rows(bom + b"evidence_id,batch,decision,reason,note,reviewer,date\n")
        reordered_rows = (
            bom + b"record_id,batch,nbs_id,table,decision,reason,note,reviewer,date\n"
        )
        self.assertEqual(export_rows(reordered_rows)[0], "rows")

    def test_last_valid_vote_and_missing_id(self):
        _, rows = export_rows((HERE / "example/evidence.csv").read_bytes())
        rows += [
            {**rows[0], "decision": "hold"},
            {**rows[0], "reason": "invalid", "decision": "reject"},
            {**rows[0], "evidence_id": "unknown"},
        ]
        fixture = b"evidence_id\nexample_keep\nexample_drop\nexample_conflict\n"
        counts = evidence_checks(
            rows,
            {
                "MAP": {"hold": "flag", "approve": "ok", "reject": "drop"},
                "REASON_CODES": {"off_scope"},
            },
            fixture,
        )
        self.assertEqual(
            counts,
            {
                "evidence_ids_with_disagreeing_reviewers": 1,
                "skipped_input_rows": 1,
                "superseded_reviewer_rows": 1,
                "target_ids_missing_from_register": 1,
            },
        )

    def test_row_id_must_match_practice_and_table_at_commit(self):
        with TemporaryDirectory() as temp:
            repo = Path(temp)
            table = repo / "schema/recipes/one/T3_nbs_hazard_farming.csv"
            table.parent.mkdir(parents=True)
            table.write_text("record_id\nfound\n")

            def git(*args):
                return subprocess.check_output(
                    [
                        "git",
                        "-C",
                        repo,
                        "-c",
                        "user.email=fixture@example.invalid",
                        "-c",
                        "user.name=Fixture",
                        *args,
                    ]
                )

            git("init", "-q")
            git("add", ".")
            git("commit", "-qm", "Fixture")
            pin = git("rev-parse", "HEAD").decode().strip()
            table.write_text("record_id\nlocal_only\n")
            base = {"record_id": "found", "table": "T3", "nbs_id": "one"}
            variants = [
                base,
                {**base, "nbs_id": "two"},
                {**base, "table": "T6"},
                {**base, "record_id": "local_only"},
                {**base, "record_id": "local_only"},
            ]
            self.assertEqual(missing_compiled_ids(variants, repo, pin), 3)
            with self.assertRaisesRegex(ValueError, "outside Git"):
                private_file(table)
