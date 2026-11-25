import json
from hashlib import sha256
from pathlib import Path
import shutil
import tempfile
import unittest
import binding_checks


class BindingInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'packet'
        shutil.copytree(binding_checks.ROOT, self.root)

    def test_real_packet(self):
        self.assertEqual(binding_checks.check(self.root), 10)

    def test_changed_observation_rejected(self):
        p = self.root / 'observations/fao_di_live.json'
        p.write_text(p.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            binding_checks.check(self.root)

    def test_rehashed_vote_still_rejected(self):
        p = self.root / 'observations/landmark_access.json'
        value = json.loads(p.read_text()); value['human_review'] = 'keep'
        p.write_text(json.dumps(value))
        m = self.root / 'manifest.json'; manifest = json.loads(m.read_text())
        for r in manifest['records']:
            if r['observation_id'] == 'landmark_access':
                r['sha256'] = sha256(p.read_bytes()).hexdigest()
        m.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'scientific vote'):
            binding_checks.check(self.root)

    def test_no_runtime_release_claim(self):
        p = self.root / 'manifest.json'; m = json.loads(p.read_text()); m['runtime_releases'] = 1
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'cannot claim acceptance'):
            binding_checks.check(self.root)
