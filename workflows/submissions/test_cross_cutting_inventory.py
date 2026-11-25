import json
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from cross_cutting_inventory import CONTROL_FILES, STORES, verify_inventory

class CrossCuttingInventory(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.expected={'manifest.json','legacy.csv'}
    def proposal(self):
        schema=self.root/'workflows/priority_classification/candidate-schema.json';schema.parent.mkdir(parents=True);schema.write_text('{}\n')
        self.path=self.root/'registers/cross_cutting/manifest.json';self.path.parent.mkdir(parents=True)
        self.value={'format':'ruralscan.cross-cutting-register-proposal.v1','status':'proposed_not_activated','activation':'disabled','canonical_record_count':0,'proposed_stores':STORES,'registration':'not_implemented_pending_protected_review_adapter','candidate_schema':{'path':str(schema.relative_to(self.root)),'sha256':sha256(schema.read_bytes()).hexdigest()}}
        self.save()
    def save(self):self.path.write_text(json.dumps(self.value))
    def test_historical_inventory_stays_exact(self):
        verify_inventory(self.root,self.expected,self.expected)
        with self.assertRaises(ValueError):verify_inventory(self.root,self.expected,self.expected|{'extra.csv'})
    def test_only_two_control_files_are_admitted(self):
        self.proposal();verify_inventory(self.root,self.expected,self.expected|CONTROL_FILES)
        for extra in ['cross_cutting/sources.jsonl','cross_cutting/findings.jsonl','cross_cutting/arbitrary.json']:
            with self.assertRaises(ValueError):verify_inventory(self.root,self.expected,self.expected|CONTROL_FILES|{extra})
    def test_no_activation_or_records(self):
        self.proposal()
        for key,value in [('activation','enabled'),('canonical_record_count',1),('canonical_record_count',False)]:
            old=self.value[key];self.value[key]=value;self.save()
            with self.assertRaises(ValueError):verify_inventory(self.root,self.expected,self.expected|CONTROL_FILES)
            self.value[key]=old
    def test_schema_tampering_rejected(self):
        self.proposal();self.value['candidate_schema']['sha256']='0'*64;self.save()
        with self.assertRaises(ValueError):verify_inventory(self.root,self.expected,self.expected|CONTROL_FILES)
    def test_cannot_remove_legacy_register(self):
        self.proposal()
        with self.assertRaises(ValueError):verify_inventory(self.root,self.expected,CONTROL_FILES|{'manifest.json'})
if __name__=='__main__':unittest.main()
