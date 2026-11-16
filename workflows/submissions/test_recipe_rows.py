"""Replay synthetic row receipts against disposable copies. No GitHub writes."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import recipe_rows as rr
import recipe_candidate as rc
import registers as reg
from queue_view import compile_candidate
from serve import Desk


class RowContract(unittest.TestCase):
    def setUp(self):
        self.queue = {
            "recipes": {
                "practice": {
                    rr.TABLES["T4"]: [
                        {"mapping_id": "gate", "evidence_ids": ["ev"], "weight": 1}
                    ]
                }
            },
            "registers": {
                "EV_evidence_register": [
                    {"evidence_id": "ev", "source_id": "s", "locator": "p3"}
                ],
                "SRC_source_register": [{"source_id": "s"}],
            },
        }
        self.pin = "b" * 40
        self.entry = dict(
            revision=self.pin,
            kind="rating",
            **rr.target(self.queue, "practice", "T4", "gate"),
            decision="hold",
            reason="other",
            note="Check scope",
        )

    def test_reject_unknown_stale_or_forged_payload(self):
        for change in (
            {"table": "T3"},
            {"practice": "elsewhere"},
            {"record": "absent"},
            {"revision": "a" * 40},
            {"decision": "drop"},
            {"evidence_ids": []},
            {"reviewer": "another person"},
            {"reason": ""},
            {"decision": "reject", "reason": "invented"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                rr.validate(dict(self.entry, **change), self.queue, self.pin)
        self.queue["registers"]["EV_evidence_register"][0]["locator"] = "p4"
        with self.assertRaisesRegex(ValueError, "Stale row"):
            rr.validate(self.entry, self.queue, self.pin)

    def test_wording_cannot_change_gate(self):
        e = {
            k: v
            for k, v in self.entry.items()
            if k not in {"decision", "reason", "note"}
        }
        e.update(kind="wording", wording={"weight": 2, "justification": "No change."})
        with self.assertRaisesRegex(ValueError, "wording fields"):
            rr.validate(e, self.queue, self.pin)

    def test_original_author_and_eligibility(self):
        issue = {
            "node_id": "N",
            "number": 77,
            "state": "open",
            "author_association": "MEMBER",
            "user": {"login": "fixture"},
            "created_at": "2026-11-16T12:00:00Z",
            "body": rr.HEADER + "\n" + json.dumps(self.entry),
        }
        info = {
            "data": {
                "node": {
                    "body": issue["body"],
                    "author": issue["user"],
                    "lastEditedAt": None,
                }
            }
        }
        with patch.object(rr.intake, "gh", side_effect=[issue, info]):
            self.assertEqual(rr.fetch(77)["actor"], "fixture")
        info["data"]["node"]["lastEditedAt"] = "later"
        with (
            patch.object(rr.intake, "gh", side_effect=[issue, info]),
            self.assertRaisesRegex(ValueError, "Edited"),
        ):
            rr.fetch(77)
        with (
            patch.object(
                rr.intake, "gh", return_value=dict(issue, author_association="NONE")
            ),
            self.assertRaisesRegex(ValueError, "eligible"),
        ):
            rr.fetch(77)

    def test_test_desk_never_sends_real_row(self):
        desk = Desk.__new__(Desk)
        desk.test = True
        with (
            patch.object(rr, "send") as send,
            self.assertRaisesRegex(ValueError, "official"),
        ):
            desk.submit_row(self.entry)
        send.assert_not_called()


@unittest.skipUnless(
    os.environ.get("CIAT_TEST_REPO"), "Requires pinned compiler history"
)
class CompiledRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.engine = Path(cls.temp.name).resolve() / "engine"
        reg.snapshot(
            cls.engine,
            "",
            reg.SEED,
            [
                "/src/",
                "/schema/",
                "/pipeline/",
                "/docs/review/*.json",
                "!/docs/review/*/",
            ],
            Path(os.environ["CIAT_TEST_REPO"]),
        )
        sys.path.insert(0, str(cls.engine / "src"))
        cls.base = (
            "a6089348100e8b9ca168ab7695b55ba5ee6a4482"  # immutable pre-route edition
        )

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.engine / "src"))
        cls.temp.cleanup()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.dest = Path(self.dir.name).resolve() / "evidence"
        reg.snapshot(self.dest, "", self.base, ["/*"], reg.ROOT)
        for f in (self.dest / "registers").rglob("*"):
            p = self.engine / f.relative_to(self.dest / "registers")
            if f.is_file() and p.is_file():
                shutil.copyfile(f, p)
        self.q = json.loads((self.dest / reg.LIVE).read_bytes())

    def event(self, kind, table, number=444, **fields):
        rows = self.q["recipes"]["agroforestry"][rr.TABLES[table]]
        row = next(
            r
            for r in rows
            if (
                table != "T4"
                or (r.get("relationship_params") or {}).get("mapping_role")
                == "hard_exclusion"
            )
        )
        entry = dict(
            revision=self.base,
            kind=kind,
            **rr.target(self.q, "agroforestry", table, rr.ident(row)),
            **fields,
        )
        return {
            "receipt": number,
            "actor": "fixture-reviewer",
            "created_at": "2026-11-16T12:00:00Z",
            "body_sha256": "a" * 64,
            "entry": entry,
        }

    def test_protected_rating_append_render_input_retry_and_tamper(self):
        log = self.dest / "registers" / rr.LOG
        old = log.read_bytes()
        e = self.event(
            "rating",
            "T3",
            decision="hold",
            reason="other",
            note="Fixture note, with a comma.",
        )
        self.assertTrue(rr.append(self.dest, e, self.base))
        self.assertFalse(rr.append(self.dest, e, self.base))
        self.assertFalse(rr.append(self.dest, dict(e, receipt=445), self.base))
        with patch.object(rr, "fetch", return_value=e):
            rr.verify(self.dest, self.base)
        shutil.copyfile(log, self.engine / rr.LOG)
        q, c = compile_candidate(self.engine, self.dest)
        self.assertEqual(q["registers"], self.q["registers"])
        self.assertEqual(q["review_log"], self.q["review_log"])
        self.assertEqual(q["recipes"], self.q["recipes"])
        self.assertTrue(log.read_bytes().startswith(old))
        r = q["row_reviews"][-1]
        self.assertEqual(
            (r["reviewer"], r["receipt"], r["revision"], r["decision"], r["note"]),
            ("fixture-reviewer", 444, self.base, "hold", e["entry"]["note"]),
        )
        self.assertEqual(len([t for ts in c["tables"].values() for t in ts]), 24)
        reg.git("add", "-A", cwd=self.dest)
        reg.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@invalid.test",
            "commit",
            "-qm",
            "fixture rating",
            cwd=self.dest,
        )
        next_base = reg.git("rev-parse", "HEAD", cwd=self.dest).decode().strip()
        self.assertTrue(
            rr.append(
                self.dest, dict(e, receipt=447, actor="second-fixture"), next_base
            )
        )
        (self.dest / "registers" / rr.LOG).write_bytes(old + b"edited")
        with (
            patch.object(
                rr, "fetch", return_value=dict(e, receipt=447, actor="second-fixture")
            ),
            self.assertRaisesRegex(ValueError, "log differs"),
        ):
            rr.verify(self.dest, next_base)

    def test_wording_four_tables_gate_staleness_and_historical_edition(self):
        events = []
        for n, table in enumerate(rr.TABLES, 700):
            words = (
                {"justification": "Fixture gate description."}
                if table == "T4"
                else {
                    "mechanism": "Fixture description.",
                    "conditionality": "Check the source.",
                }
            )
            e = self.event("wording", table, number=n, wording=words)
            self.assertTrue(rr.append(self.dest, e, self.base))
            events.append(e)
        q, c = compile_candidate(self.engine, self.dest)
        diffs = list(rc.changes(self.q["recipes"], q["recipes"]))
        self.assertEqual(len(diffs), 4)
        self.assertFalse(c["stale_wording"].get("agroforestry"))
        self.assertEqual(q["row_reviews"], self.q["row_reviews"])
        self.assertEqual(q["registers"], self.q["registers"])
        for event in events:
            e = event["entry"]
            table = e["table"]
            row = rr.lookup(q, e["practice"], table, e["record"])
            field = {"T4": "justification", "T3": "mitigation_mechanism"}.get(
                table, "effect_mechanism"
            )
            self.assertEqual(
                row[field],
                e["wording"].get("justification", e["wording"].get("mechanism")),
            )
            self.assertEqual(
                e["basis_sha256"],
                rr.basis(row, table, rr.evidence_index(q["registers"])),
            )
        for table, rows in q["recipes"]["agroforestry"].items():
            self.assertEqual(
                c["tables"]["agroforestry"][table]["sha256"], rr.digest(rows)
            )
        old = json.loads(reg.blob(self.dest, self.base, reg.LIVE))
        self.assertEqual(old["recipes"], self.q["recipes"])
        # Same evidence ID, amended locator. New wording must not be reused.
        target = events[0]["entry"]
        eid = target["evidence_ids"][0]
        f = self.engine / reg.EV
        rs = reg.rows(f.read_bytes())
        next(r for r in rs if r["evidence_id"] == eid)["locator"] = (
            "Fixture corrected locator"
        )
        reg.write_csv(f, rs)
        q2, c2 = compile_candidate(self.engine, self.dest)
        self.assertTrue(
            any(w.get("receipt") == 700 for w in c2["stale_wording"]["agroforestry"])
        )
        self.assertNotEqual(
            rr.lookup(q2, "agroforestry", "T3", target["record"])[
                "mitigation_mechanism"
            ],
            "Fixture description.",
        )
        self.assertNotEqual(c["inputs"][reg.EV], c2["inputs"][reg.EV])
