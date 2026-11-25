import copy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import consolidation
import priority_store as store
from preparation import BATCH


class Candidates(unittest.TestCase):
    def setUp(self):
        self.ref = json.loads((store.ROOT / BATCH / 'manifest.json').read_bytes())['candidate_bundle']
        self.ref = {k: self.ref[k] for k in ('revision','path','sha256')}
        self.bundle = json.loads((store.ROOT / self.ref['path']).read_bytes())
        self.sources = store.objects(store.ROOT / BATCH, 'sources')

    def test_all_eight_observations_survive_without_votes_or_registration(self):
        result = consolidation.check()
        self.assertEqual(result['distinct_candidate_findings'], 8)
        self.assertEqual(result['review_routes'], 1)
        wrappers = store.candidate_objects(self.bundle, self.sources, self.ref)
        self.assertEqual([w['candidate_finding'] for w in wrappers], self.bundle['findings'])
        self.assertEqual(len({store.digest(w) for w in wrappers}), 8)
        self.assertTrue(all(store.status([], store.digest(w)) == 'unreviewed' for w in wrappers))
        old = store.objects(store.ROOT / BATCH, 'findings')
        self.assertFalse(set(old) & {store.digest(w) for w in wrappers})

    def test_wrong_source_edition_or_candidate_vote_fails(self):
        sources = dict(self.sources); sources.pop(next(iter(sources)))
        with self.assertRaisesRegex(ValueError, 'not prepared'):
            store.candidate_objects(self.bundle, sources, self.ref)
        bad = copy.deepcopy(self.bundle); bad['findings'][0]['review_state'] = 'kept'
        with self.assertRaises(Exception): store.candidate_objects(bad, self.sources, self.ref)
        bad = copy.deepcopy(self.bundle); bad['review_events'] = [{'decision':'keep'}]
        with self.assertRaises(Exception): store.candidate_objects(bad, self.sources, self.ref)

    def test_preserved_bytes_and_duplicate_route_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            shutil.copytree(store.ROOT / 'workflows/priority_classification', root / 'workflows/priority_classification')
            path = root / self.ref['path']; path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'Preserved proposal bytes changed'):
                consolidation.check(root)
            path.write_bytes((store.ROOT / self.ref['path']).read_bytes())
            (root / 'registers/cross_cutting').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'Retired register/adapter'):
                consolidation.check(root)

    def test_stage_and_resolve_use_existing_authenticated_review_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); repo = root / 'repo'; repo.mkdir()
            def git(*args): return subprocess.check_output(['git', *args], cwd=repo).decode().strip()
            git('init', '-q'); git('config', 'user.name', 'Synthetic fixture'); git('config', 'user.email', 'fixture@example.org')
            path = repo / self.ref['path']; path.parent.mkdir(parents=True); path.write_bytes((store.ROOT / self.ref['path']).read_bytes())
            git('add', '.'); git('commit', '-qm', 'Synthetic candidate'); revision = git('rev-parse','HEAD')
            out = root / 'stage'
            result = store.stage_candidates(repo, revision, self.ref['path'], revision, store.ROOT / BATCH, out)
            self.assertEqual(result['findings_prepared'], 8)
            self.assertFalse((out / store.REVIEWS).exists())
            shutil.copytree(out / store.STORE, repo / store.STORE)
            git('add','.'); git('commit','-qm','Synthetic registration'); base = git('rev-parse','HEAD')
            self.assertEqual(set(store.verify(repo, revision).values()), {'unreviewed'})
            key, finding = next(iter(store.objects(repo,'findings').items()))
            ref = {'repository':'RuralScan/evidence', 'revision':base, 'path':self.ref['path'],
                   'sha256':self.ref['sha256'], 'source_id':'psrc_' + finding['source_sha256'], 'finding_ids':['pfind_' + key]}
            with self.assertRaisesRegex(ValueError,'unreviewed'): store.resolve(repo, ref, base)
            def event(number, decision):
                return {'finding_sha256':key, 'finding_revision':base, 'decision':decision,
                        'reason':'Synthetic test', 'receipt':number, 'actor':'fixture',
                        'created_at':f'2026-11-25T12:0{number}:00Z', 'body_sha256':'0'*64}
            with patch.object(store,'fetch_review',return_value=event(1,'keep')):
                store.record_review(repo,1,base)
            git('add','.');git('commit','-qm','Synthetic keep'); kept=git('rev-parse','HEAD');ref['revision']=kept
            self.assertEqual(len(store.resolve(repo,ref,kept)),1)
            # A second finding from the same source does not inherit this keep.
            other=next(k for k,f in store.objects(repo,'findings').items() if k!=key and f['source_sha256']==finding['source_sha256']) if sum(f['source_sha256']==finding['source_sha256'] for f in store.objects(repo,'findings').values())>1 else None
            if other:
                with self.assertRaisesRegex(ValueError,'unreviewed'): store.resolve(repo,{**ref,'finding_ids':['pfind_'+other]},kept)
            with patch.object(store,'fetch_review',return_value=event(2,'reopen')):
                store.record_review(repo,2,kept)
            git('add','.');git('commit','-qm','Synthetic reopen')
            with self.assertRaisesRegex(ValueError,'reopened'): store.resolve(repo,ref,git('rev-parse','HEAD'))


if __name__ == '__main__': unittest.main()
