import copy
import json
from pathlib import Path
import tempfile
import unittest
import jsonschema
from intake import ROOT, digest, validate, stage, review_projection
class CrossCuttingIntake(unittest.TestCase):
    def setUp(self):self.bundle=json.loads((ROOT/'workflows/priority_classification/batches/t5-2026-11-25/candidate.json').read_text())
    def invalid(self):
        with self.assertRaises((ValueError,jsonschema.ValidationError)):validate(self.bundle)
    def test_six_sources_eight_findings_zero_acceptance(self):
        r=validate(self.bundle);self.assertEqual((r['sources'],r['findings'],r['accepted_classifications']),(6,8,0))
    def test_no_fabricated_nbs_lane(self):self.bundle['findings'][0]['nbs_id']='agroforestry';self.invalid()
    def test_no_hidden_scores(self):self.bundle['findings'][0]['reported']['values']['class_scores']={'low':.33};self.invalid()
    def test_no_claimed_registration(self):self.bundle['sources'][0]['canonical_source_ref']='src_fake';self.invalid()
    def test_no_finding_vote_in_candidate(self):self.bundle['findings'][0]['review_state']='kept';self.invalid()
    def test_receipt_tampering(self):self.bundle['sources'][0]['identity_receipt']['sha256']='0'*64;self.invalid()
    def test_stale_packet(self):
        path=next(iter(self.bundle['packet_dependencies']));self.bundle['packet_dependencies'][path]='0'*64;self.invalid()
    def test_unknown_source(self):self.bundle['findings'][0]['candidate_source_id']='xcs_unknown';self.invalid()
    def test_no_path_escape(self):self.bundle['sources'][0]['identity_receipt']['path']='../outside.json';self.invalid()
    def test_stale_search(self):self.bundle['search_sha256']='0'*64;self.invalid()
    def test_stale_instructions(self):self.bundle['instruction_sha256']='0'*64;self.invalid()
    def test_no_t2_scope(self):self.bundle['findings'][0]['variables']=['drought_spei12_baseline'];self.invalid()
    def test_retry_is_content_addressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            one=stage(self.bundle,Path(tmp));two=stage(self.bundle,Path(tmp));self.assertEqual(one,two);self.assertEqual(len(list(Path(tmp).iterdir())),1)
    def test_source_review_does_not_accept_classification(self):
        f=self.bundle['findings'][0];e={'event_id':'synthetic_1','finding_id':f['candidate_finding_id'],'finding_sha256':digest(f),'sequence':1,'action':'keep','reviewer':'synthetic-human','reason':'fixture only','review_ref':'https://github.com/RuralScan/evidence/pull/1'}
        self.assertEqual(review_projection([f],[e,e]),{f['candidate_finding_id']:'kept'});self.assertEqual(validate(self.bundle)['accepted_classifications'],0)
        changed=copy.deepcopy(f);changed['reported']['statement']='Changed'
        with self.assertRaises(ValueError):review_projection([changed],[e])
    def test_drop_reopen_preserves_finding(self):
        f=self.bundle['findings'][0];before=copy.deepcopy(f);events=[]
        for n,action in enumerate(['drop','reopen'],1):events.append({'event_id':f'synthetic_{n}','finding_id':f['candidate_finding_id'],'finding_sha256':digest(f),'sequence':n,'action':action,'reviewer':'synthetic-human','reason':'fixture only','review_ref':'https://github.com/RuralScan/evidence/pull/1'})
        self.assertEqual(review_projection([f],events),{f['candidate_finding_id']:'unreviewed'});self.assertEqual(f,before)
if __name__=='__main__':unittest.main()
