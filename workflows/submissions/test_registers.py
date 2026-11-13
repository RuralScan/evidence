"""Run authenticated-receipt fixtures against the real register schema and reducer."""

import hashlib
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import registers as reg


@unittest.skipUnless(
    os.environ.get("CIAT_TEST_REPO"),
    "Set CIAT_TEST_REPO to the pinned producer history",
)
class RegisterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.root = Path(cls.temp.name).resolve()
        cls.engine = cls.root / "engine"
        cls.ciat = Path(os.environ["CIAT_TEST_REPO"]).resolve()
        reg.snapshot(
            cls.engine,
            "",
            reg.SEED,
            ["/src/", "/schema/", "/scripts/", "/pipeline/"],
            cls.ciat,
        )
        sys.path.insert(0, str(cls.engine / "src"))
        cls.ev, cls.src = reg.cohort(reg.ROOT, reg.FIRST, cls.ciat, reg.SEED)
        cls.original_corpus = cls.root / "corpus"
        cls.original_corpus.mkdir()
        log = {r["evidence_id"] for r in reg.rows((cls.engine / reg.LOG).read_bytes())}

        def first(role):
            return next(
                e
                for e, r in cls.ev.items()
                if r["use_role"] == role
                and not r["review_state"]
                and str(r["reviewer_ok"]).lower() in {"false", ""}
                and e not in log
            )

        cls.t4 = first("structural_suitability")
        cls.effect = first("nbs_effect")

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(str(cls.engine / "src"))
        cls.temp.cleanup()

    def setUp(self):
        for path in (reg.EV, reg.LOG, reg.SRC):
            (self.engine / path).write_bytes(reg.blob(self.ciat, reg.SEED, path))
        self.items = {}
        self.journal = {}
        mock = patch.object(reg, "cohort", return_value=(self.ev, self.src))
        mock.start()
        self.addCleanup(mock.stop)

    def receipt(self, n, actor, kind, lane, payload, labels=()):
        self.items[n] = dict(
            actor=actor,
            digest=hashlib.sha256(str(payload).encode()).hexdigest(),
            labels=set(labels),
            entry=dict(
                test=False, revision=reg.SEED, kind=kind, lane=lane, payload=payload
            ),
        )

    def apply(self, *numbers):
        return reg.apply_batch(
            reg.ROOT,
            self.ciat,
            reg.FIRST,
            self.engine,
            self.items,
            numbers,
            self.journal,
            self.original_corpus,
        )

    def test_dashboard_csv_hold_reject_and_retry(self):
        self.receipt(
            1,
            "reader_a",
            "vote",
            "T4",
            dict(evidence_id=self.t4, decision="hold", note="Check rainfall"),
        )
        self.receipt(
            2,
            "reader_b",
            "csv",
            "T3/T6",
            f"evidence_id,reviewer,decision,reason\n{self.effect},reader_b,reject,wrong_practice\n",
        )
        self.assertEqual(self.apply(1, 2), [1, 2])
        latest = reg.index(reg.rows((self.engine / reg.EV).read_bytes()), "evidence_id")
        self.assertEqual(
            (latest[self.t4]["review_state"], latest[self.t4]["reviewer_ok"]),
            ("", "false"),
        )
        self.assertEqual(latest[self.effect]["review_state"], "dropped")
        before = (self.engine / reg.LOG).read_bytes()
        self.assertEqual(self.apply(1, 2), [])
        self.assertEqual((self.engine / reg.LOG).read_bytes(), before)

    def test_opposition_before_or_after_first_application(self):
        self.receipt(
            1, "reader_a", "vote", "T4", dict(evidence_id=self.t4, decision="approve")
        )
        self.receipt(
            2,
            "reader_b",
            "vote",
            "T4",
            dict(evidence_id=self.t4, decision="reject", reason="wrong_practice"),
        )
        before = (self.engine / reg.LOG).read_bytes()
        with self.assertRaisesRegex(ValueError, "Include all"):
            self.apply(1)
        with self.assertRaisesRegex(ValueError, "Opposing"):
            self.apply(1, 2)
        self.assertEqual(before, (self.engine / reg.LOG).read_bytes())
        b = self.items.pop(2)
        self.apply(1)
        self.items[2] = b
        after = (self.engine / reg.LOG).read_bytes()
        with self.assertRaisesRegex(ValueError, "(changed|Opposing)"):
            self.apply(2)
        self.assertEqual(after, (self.engine / reg.LOG).read_bytes())

    def test_changed_locator_rejected(self):
        ev = self.ev[self.t4]
        self.receipt(
            1, "reader", "vote", "T4", dict(evidence_id=self.t4, decision="approve")
        )
        with patch.object(
            reg,
            "cohort",
            return_value=(
                {self.t4: {**ev, "locator": "different source section"}},
                self.src,
            ),
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.apply(1)

    def test_extraction_approval_required(self):
        self.receipt(1, "agent", "extraction", "T4", [])
        with self.assertRaisesRegex(ValueError, "awaits scientific approval"):
            self.apply(1)
        self.assertFalse(self.journal)
