"""Exercise CSV identity, lossless merging, and the actual pinned consensus replay."""

import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from csv_votes import FIELDS, publish_copy, stage_votes, write_copy
from preview import ENGINE, EV, HERE, LOG, REPO, snapshot


class CsvVotesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.pending = self.root / "pending"
        self.pending.mkdir()
        self.mapping = self.root / "identities.json"
        self.mapping.write_text('{"A":"reader_a","B":"reader_b"}')
        self.a = self.export("a", "A", "approve", "")
        self.b = self.export("b", "B", "reject", "off_scope")

    def export(self, name, reviewer, decision, reason):
        path = self.root / (name + ".csv")
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerow(
                [
                    "batch",
                    "example_conflict",
                    decision,
                    reason,
                    "two\nlines",
                    reviewer,
                    "2026-01-01",
                    "I;C",
                ]
            )
        return path

    def test_separate_votes_and_retries(self):
        first = stage_votes(self.pending, [self.a], self.mapping)
        dest = self.root / "first"
        dest.mkdir()
        write_copy(dest, first)
        second = stage_votes(dest, [self.b], self.mapping)
        third = self.root / "second"
        third.mkdir()
        write_copy(third, second)
        self.assertEqual(second, stage_votes(third, [self.b, self.a], self.mapping))
        votes = json.loads(second["decisions.json"])["example_conflict"]
        self.assertEqual(set(votes), {"reader_a", "reader_b"})
        vote = votes["reader_b"]
        self.assertEqual(vote["note"], "two\nlines [PICOS fails: I,C]")
        self.assertEqual(vote["csv_sources"][0]["values"]["reviewer"], "B")
        self.assertEqual(vote["csv_sources"][0]["file"], "b.csv")
        self.assertEqual(len(vote["csv_sources"][0]["sha256"]), 64)

    def test_identity_mapping_changes_cannot_clone_an_existing_vote(self):
        publish_copy(
            self.root / "first", stage_votes(self.pending, [self.a], self.mapping)
        )
        self.mapping.write_text('{"A":"other","reader_a":"reader_a"}')
        with self.assertRaisesRegex(ValueError, "different reviewer"):
            stage_votes(self.root / "first", [self.a], self.mapping)
        with self.assertRaisesRegex(ValueError, "fresh output"):
            publish_copy(self.root / "first", {})
        self.assertEqual(
            (self.root / "first" / "decisions.json").stat().st_mode & 0o077, 0
        )

    def test_ambiguous_input_retains_original(self):
        for item in [
            self.export("changed", "A", "hold", ""),
            self.export("unknown", "C", "approve", ""),
        ]:
            with self.assertRaises(ValueError):
                stage_votes(self.pending, [self.a, item], self.mapping)
        (self.pending / "decisions.json").write_text('{"x":{}, "x":{}}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            stage_votes(self.pending, [self.a], self.mapping)

    @unittest.skipUnless(
        os.environ.get("CIAT_TEST_REPO"), "needs pinned CIAT Git objects"
    )
    def test_applied_and_unapplied_conflicts_in_real_engine(self):
        import sys
        from shutil import copytree

        # Use a child interpreter with the pinned engine and a disposable lock.
        code = self.root / "engine"
        snapshot(code, REPO, ENGINE, ["/src/"], Path(os.environ["CIAT_TEST_REPO"]))
        records = self.root / "records"
        copytree(HERE / "example/records", records)
        pending = records / "pipeline/review"
        pending.mkdir()
        first = stage_votes(self.pending, [self.a], self.mapping)
        write_copy(pending, first)
        combined = stage_votes(pending, [self.b, self.b], self.mapping)

        def run(statement, ok=True):
            script = (
                "import sys; sys.path[:0]=sys.argv[1:3]; from pathlib import Path; root=Path(sys.argv[3]); "
                + statement
            )
            p = subprocess.run(
                [
                    sys.executable,
                    "-IB",
                    "-c",
                    script,
                    str(code / "src"),
                    str(HERE),
                    str(records),
                ],
                text=True,
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    "HOME": str(self.root),
                    "USERPROFILE": str(self.root),
                },
            )
            self.assertEqual(p.returncode == 0, ok, p.stderr)
            return p.stdout

        never_reviewed = (records / LOG).read_bytes()
        ev_before = (records / EV).read_bytes()
        (pending / "decisions.json").write_bytes(combined["decisions.json"])
        measure = "from worker import measure; import json; print(json.dumps(measure(root, check_csv=True)))"
        for _ in range(2):
            result = json.loads(run(measure))
            self.assertEqual(result["conflicted_ids"], 1)
            self.assertEqual(sum(result["applied"].values()), 0)
        self.assertEqual((records / LOG).read_bytes(), never_reviewed)
        self.assertEqual((records / EV).read_bytes(), ev_before)
        (pending / "decisions.json").write_bytes(first["decisions.json"])
        self.assertEqual(json.loads(run(measure))["applied"]["ok"], 1)
        previous = ((records / LOG).read_bytes(), (records / EV).read_bytes())
        (pending / "decisions.json").write_bytes(combined["decisions.json"])
        result = json.loads(run(measure))
        self.assertEqual(result["pending_challenges_with_prior_events"], 1)
        self.assertEqual(sum(result["applied"].values()), 0)
        self.assertEqual(
            previous, ((records / LOG).read_bytes(), (records / EV).read_bytes())
        )
        # An isolated export lacks the prior reviewer's ballot.
        (pending / "decisions.json").write_bytes(
            stage_votes(self.pending, [self.b], self.mapping)["decisions.json"]
        )
        run(measure, ok=False)


if __name__ == "__main__":
    unittest.main()
