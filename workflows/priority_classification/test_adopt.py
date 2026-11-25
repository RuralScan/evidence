import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
import adopt
from priority_store import digest, encoded


class Adoption(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.method = self.root / 'method'; self.evidence = self.root / 'evidence'
        for root in (self.method, self.evidence):
            root.mkdir(); self.git(root, 'init', '-q'); self.git(root, 'config', 'user.name', 'Fixture')
            self.git(root, 'config', 'user.email', 'fixture@example.org')
            self.git(root, 'commit', '--allow-empty', '-qm', 'Start fixture')
        self.evidence_base = self.head(self.evidence)
        self.verify = Mock()

    def git(self, root, *args): return subprocess.check_output(['git', *args], cwd=root).decode().strip()
    def head(self, root): return self.git(root, 'rev-parse', 'HEAD')

    def release(self, edition):
        payload = {'format': 'ruralscan.priority-release.v1', 'synthetic_edition': edition}
        key = digest(payload); path = f'priority/releases/{key}.json'
        target = self.method / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(encoded(payload))
        self.git(self.method, 'add', '.'); self.git(self.method, 'commit', '-qm', 'Synthetic release')
        return {'repository': 'RuralScan/method', 'revision': self.head(self.method), 'path': path, 'sha256': key}

    def apply(self, pin, operation, action='adopt'):
        return adopt.adopt(self.evidence, self.method, pin, self.head(self.method), self.evidence_base, operation, action, self.verify)

    def test_adoption_retry_rollback_preserve_bytes_and_compiler_lock(self):
        compiler = self.evidence / 'compiler.lock'; compiler.write_text('unchanged fixture')
        first = self.release(1)
        self.assertTrue(self.apply(first, 'one')); self.assertFalse(self.apply(first, 'one'))
        second = self.release(2); self.assertTrue(self.apply(second, 'two'))
        self.assertTrue(self.apply(first, 'rollback-one', 'rollback'))
        events = adopt.load_events(self.evidence)
        self.assertEqual(adopt.validate_events(self.evidence, events), first['sha256'])
        self.assertEqual(len(events), 3); self.assertEqual(self.verify.call_count, 3)
        self.assertEqual(compiler.read_text(), 'unchanged fixture')
        self.assertEqual(len(list((self.evidence / adopt.CACHE).glob('*.json'))), 2)
        self.git(self.evidence, 'add', '.'); self.git(self.evidence, 'commit', '-qm', 'Adopt fixtures')
        base = self.head(self.evidence)
        self.assertEqual(adopt.check(self.evidence, self.method, base, self.head(self.method), base, self.verify), first['sha256'])
        journal = self.evidence / adopt.JOURNAL; journal.write_text('')
        with self.assertRaisesRegex(ValueError, 'history rewritten'):
            adopt.check(self.evidence, self.method, base, self.head(self.method), base, self.verify)

    def test_bad_pin_unmerged_or_held_release_never_records_receipt(self):
        pin = self.release(1)
        wrong = {**pin, 'sha256': '0' * 64}
        with self.assertRaises(ValueError): self.apply(wrong, 'bad-hash')
        self.verify.side_effect = ValueError('Finding is held')
        with self.assertRaisesRegex(ValueError, 'held'): self.apply(pin, 'held')
        self.assertEqual(adopt.load_events(self.evidence), [])
        parent = self.git(self.method, 'rev-parse', 'HEAD^')
        with self.assertRaises(ValueError): adopt.resolve(self.method, pin, parent)

    def test_conflicting_retry_and_never_adopted_rollback_fail(self):
        first = self.release(1); self.apply(first, 'one')
        second = self.release(2)
        with self.assertRaisesRegex(ValueError, 'identity already used'): self.apply(second, 'one')
        with self.assertRaisesRegex(ValueError, 'never adopted'): self.apply(second, 'two', 'rollback')
        self.assertEqual(len(adopt.load_events(self.evidence)), 1)

    def test_verifier_executes_pinned_producer_not_checkout(self):
        pin = self.release(1)
        folder = self.method / "priority"
        (folder / "catalogue.py").write_text("# Synthetic pinned dependency\n")
        (folder / "package.py").write_text("def verify(method, package, method_base, evidence, evidence_base):\n    assert package['synthetic_edition'] == 1\n")
        self.git(self.method, "add", "."); self.git(self.method, "commit", "-qm", "Synthetic producer")
        pin["revision"] = self.head(self.method)
        (folder / "package.py").write_text("raise RuntimeError('Mutable checkout must not run')\n")
        payload = adopt.resolve(self.method, pin, self.head(self.method))
        adopt.producer_verify(self.method, pin, payload, self.head(self.method), self.evidence, self.evidence_base)

    def test_altered_cache_fails(self):
        pin = self.release(1); self.apply(pin, 'one')
        (self.evidence / adopt.CACHE / f"{pin['sha256']}.json").write_text('{}')
        with self.assertRaisesRegex(ValueError, 'cache altered'): adopt.validate_events(self.evidence, adopt.load_events(self.evidence))


if __name__ == '__main__': unittest.main()
