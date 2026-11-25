import json
from pathlib import Path
import shutil
import tempfile
import unittest
import preparation
from priority_store import ROOT


class Preparation(unittest.TestCase):
    def fixture(self):
        # Keep Git history readable while mutations stay in a disposable folder.
        temp = tempfile.TemporaryDirectory(prefix='.priority-preparation-test-', dir=ROOT)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        shutil.copytree(ROOT / preparation.BATCH, root / preparation.BATCH)
        path = root / preparation.BATCH / 'manifest.json'
        return root, path, json.loads(path.read_bytes())

    def test_all_sources_preserve_distinct_candidate_observations(self):
        result = preparation.check()
        self.assertEqual((result['sources_prepared'], result['packet_findings_prepared'],
                          result['t5_candidate_findings_preserved']), (6, 5, 8))
        self.assertEqual(result['registered_findings'], 0)
        self.assertFalse(result['remote_access_verified'])

    def test_hash_crosswalk_cannot_claim_another_source_or_remote_access(self):
        for field, value in [('artifact_sha256', '0' * 64), ('accession_state', 'remote_verified'),
                             ('relationship', 'equivalent_findings')]:
            root, path, manifest = self.fixture()
            manifest['sources'][0][field] = value
            path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): preparation.check(root)

    def test_preparation_cannot_claim_registration_or_contain_votes(self):
        root, path, manifest = self.fixture()
        manifest['registered_sources'] = 6; path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError): preparation.check(root)
        manifest['registered_sources'] = 0; path.write_text(json.dumps(manifest))
        (root / preparation.BATCH / 'priority-evidence/reviews.jsonl').write_text('{}\n')
        with self.assertRaises(ValueError): preparation.check(root)


if __name__ == '__main__': unittest.main()
