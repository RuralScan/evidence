"""Exercise interrupted replacements on a disposable set of review records."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from preview import EV, HISTORY, LOG
from recovery_fault import interrupt_replay


class RecoveryFaultTests(unittest.TestCase):
    def setUp(self):
        checkout = TemporaryDirectory()
        self.addCleanup(checkout.cleanup)
        self.root = Path(checkout.name).resolve()
        self.before = {
            EV: b"evidence_id,value\r\ne1,10\r\n",
            LOG: b"evidence_id,action\ne1,keep\n",
            HISTORY: None,
            "pipeline/review/decisions.json": b'{"e1":"keep"}\n',
            "pipeline/review/clarifications.json": None,
        }
        for name, data in self.before.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if data is not None:
                path.write_bytes(data)

    def replay_with_rollback(self, target, corrupt_after=None):
        def replay(root):
            destination = root / target
            incoming = root / "incoming"
            incoming.write_bytes(b"changed")
            try:
                os.replace(incoming, destination)
            except OSError:
                self.assertFalse(incoming.exists())
                self.assertEqual(destination.read_bytes(), b"changed")
                original = self.before[target]
                if original is None:
                    destination.unlink()
                else:
                    incoming.write_bytes(original)
                    os.replace(incoming, destination)
                if corrupt_after:
                    (root / corrupt_after).write_bytes(b"")
                raise

        return replay

    def test_interrupts_after_installation_at_each_record_and_allows_rollback(self):
        for name in (EV, LOG, HISTORY):
            with self.subTest(record=name):
                self.assertTrue(
                    interrupt_replay(self.root, self.replay_with_rollback(name))
                )
                for path, original in self.before.items():
                    restored = self.root / path
                    if original is None:
                        self.assertFalse(restored.exists())
                    else:
                        self.assertEqual(restored.read_bytes(), original)

    def test_checks_every_record_and_pending_input_including_absence(self):
        for name, original in self.before.items():
            with self.subTest(damaged=name):
                with self.assertRaises(ValueError) as raised:
                    interrupt_replay(self.root, self.replay_with_rollback(EV, name))
                self.assertIn(name, str(raised.exception))
                if original is None:
                    (self.root / name).unlink()
                else:
                    (self.root / name).write_bytes(original)

    def test_identity_preserving_replace_is_a_no_op(self):
        def unchanged(root):
            incoming = root / "incoming"
            incoming.write_bytes(self.before[LOG])
            os.replace(incoming, root / LOG)

        self.assertFalse(interrupt_replay(self.root, unchanged))

    def test_surfaces_unrelated_error(self):
        problem = PermissionError("Unable to open register")

        def failed(_root):
            raise problem

        with self.assertRaises(PermissionError) as raised:
            interrupt_replay(self.root, failed)
        self.assertIs(raised.exception, problem)

    def test_rejects_replay_that_suppresses_the_injected_failure(self):
        def suppress(root):
            try:
                self.replay_with_rollback(EV)(root)
            except OSError:
                pass

        with self.assertRaisesRegex(ValueError, "suppressed"):
            interrupt_replay(self.root, suppress)
