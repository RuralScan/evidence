"""Test an uncommitted register application, merge, subsequent review and second correction."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from corrections import REGISTER, changes, content, correction_history
from registers import JOURNAL, git, write_csv


class CorrectionTests(unittest.TestCase):
    def test_differences_preserve_types_and_meaningful_attribution(self):
        before = content(
            {
                "relationship": '{"value":true,"extra":null}',
                "page": "3",
                "attribution": "[reviewed 2026-11-10 by fixture] Original source",
            }
        )
        after = content(
            {
                "relationship": '{"value":1}',
                "page": "4",
                "reviewer_ok": "false",
                "attribution": "[VERIFY-FLAG mismatch: re-opened for review] Corrected source",
            }
        )
        self.assertEqual(
            changes(before, after),
            [
                {
                    "path": ["attribution"],
                    "before": "Original source",
                    "after": "Corrected source",
                },
                {"path": ["page"], "before": 3, "after": 4},
                {"path": ["relationship", "extra"], "before": None},
                {"path": ["relationship", "value"], "before": True, "after": 1},
            ],
        )

    def test_history_uses_receipt_versions_after_later_changes(self):
        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git("init", "-q", cwd=repo)
            (repo / REGISTER).parent.mkdir(parents=True)
            register = [
                dict(
                    evidence_id="site",
                    use_role="structural_suitability",
                    relationship='{"observed_max":750,"unit":"mm"}',
                    quote="rain",
                    locator="",
                ),
                dict(
                    evidence_id="effect",
                    use_role="nbs_effect",
                    relationship="{}",
                    quote="old",
                    locator="section 2",
                ),
            ]
            journal, log = {}, []

            def save():
                write_csv(repo / REGISTER, register)
                (repo / JOURNAL).write_text(json.dumps(journal))

            def commit(message):
                git("add", ".", cwd=repo)
                git(
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-qm",
                    message,
                    cwd=repo,
                )
                return git("rev-parse", "HEAD", cwd=repo).decode().strip()

            def reopen(eid, n):
                return dict(
                    evidence_id=eid,
                    reviewer=f"RuralScan receipt #{n}",
                    decision="reopen",
                    date="2026-11-16",
                )

            save()
            base = commit("Initial register")
            register[0]["relationship"] = '{"observed_max":1000,"unit":"mm"}'
            register[1].update(quote="new", locator="table 3")
            # New units and ordinary votes have no receipt-owned reopen.
            register.append({**register[1], "evidence_id": "new"})
            journal.update({str(n): dict(base=base, kind="extraction") for n in (5, 6)})
            log.extend(
                [
                    reopen("site", 5),
                    reopen("effect", 6),
                    {**reopen("new", 6), "reviewer": "fixture", "decision": "flag"},
                ]
            )
            save()
            staged = correction_history(repo, log)
            self.assertEqual(set(staged), {"site", "effect"})
            self.assertEqual(
                staged["site"][0]["changes"],
                [
                    dict(
                        path=["relationship", "observed_max"],
                        before=750,
                        after=1000,
                        before_unit="mm",
                        after_unit="mm",
                    )
                ],
            )
            self.assertEqual(
                staged["effect"][0]["changes"],
                [
                    dict(path=["locator"], before="section 2", after="table 3"),
                    dict(path=["quote"], before="old", after="new"),
                ],
            )

            commit("First corrections")
            log.append({**reopen("effect", 6), "reviewer": "fixture", "decision": "ok"})
            self.assertEqual(correction_history(repo, log), staged)
            base = git("rev-parse", "HEAD", cwd=repo).decode().strip()
            register[1]["quote"] = "later"
            journal["7"] = dict(base=base, kind="extraction")
            log.append(reopen("effect", 7))
            save()
            next_history = correction_history(repo, log)
            commit("Second correction")
            self.assertEqual(correction_history(repo, log), next_history)
            self.assertEqual(
                next_history["effect"],
                [
                    staged["effect"][0],
                    dict(
                        receipt=7,
                        date="2026-11-16",
                        changes=[dict(path=["quote"], before="new", after="later")],
                    ),
                ],
            )

    def test_receipt_history_is_identical_on_branch_and_ci_merge(self):
        """A metadata branch must not take credit for a receipt on its other parent."""
        from classification import migrate_csv
        import subprocess

        with TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git("init", "-q", "-b", "main", cwd=repo)
            git("config", "user.name", "Fixture", cwd=repo)
            git("config", "user.email", "fixture@example.invalid", cwd=repo)
            (repo / REGISTER).parent.mkdir(parents=True)
            row = dict(evidence_id="finding", claim_basis="modelled", quote="before")
            write_csv(repo / REGISTER, [row])
            (repo / JOURNAL).write_text("{}")

            def commit(message):
                git("add", ".", cwd=repo)
                git("commit", "-qm", message, cwd=repo)
                return git("rev-parse", "HEAD", cwd=repo).decode().strip()

            base = commit("Base")
            git("switch", "-qc", "classification", cwd=repo)
            (repo / REGISTER).write_bytes(migrate_csv((repo / REGISTER).read_bytes()))
            commit("Add classification metadata")
            git("switch", "-q", "main", cwd=repo)
            write_csv(repo / REGISTER, [row | {"quote": "after"}])
            (repo / JOURNAL).write_text(json.dumps({"41": dict(base=base, kind="extraction")}))
            applied = commit("Apply receipt 41")
            log = [dict(evidence_id="finding", reviewer="RuralScan receipt #41", decision="reopen", date="2026-11-19")]
            expected = correction_history(repo, log)
            self.assertEqual(expected["finding"][0]["changes"], [dict(path=["quote"], before="before", after="after")])
            git("switch", "-q", "classification", cwd=repo)
            try:
                git("merge", "--no-commit", "--no-ff", "main", cwd=repo)
            except subprocess.CalledProcessError:
                self.assertEqual(git("diff", "--name-only", "--diff-filter=U", cwd=repo).decode().strip(), REGISTER)
            (repo / REGISTER).write_bytes(migrate_csv(git("show", applied + ":" + REGISTER, cwd=repo)))
            commit("Resolve metadata migration against main")
            branch_history = correction_history(repo, log)
            git("switch", "-q", "main", cwd=repo)
            git("merge", "--no-ff", "classification", "-m", "Synthetic PR test merge", cwd=repo)
            self.assertEqual(correction_history(repo, log), expected)
            self.assertEqual(branch_history, expected)
