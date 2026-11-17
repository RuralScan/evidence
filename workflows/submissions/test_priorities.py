"""Shared priority status is reversible triage, not scientific approval."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import priorities as p
from registers import LIVE, json_bytes


class Priorities(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.q = dict(registers={"EV_evidence_register":[dict(evidence_id="ev",source_id="s",reviewer_ok=False)],
                    "SRC_source_register":[dict(source_id="s",url="https://example.org/source")]},
                    review_log=[],row_reviews=[],recipes={},membership={},corrections={})
        self.requests = [dict(batch_id="wetland",batch_label="Source checks",evidence_id="ev",priority="high")]
        self.pin = "a" * 40
        self.refresh()

    def refresh(self):
        self.q["priority_requests"] = p.publish(self.q,self.requests,self.root)

    def entry(self, action="deprioritize"):
        return dict(kind="priority",revision=self.pin,action=action,reason="Superseded by a new request.",
                    targets=[{k:self.q['priority_requests'][0][k] for k in p.TARGET_FIELDS}])

    def event(self, n=501, action="deprioritize"):
        return dict(receipt=n,actor="fixture",created_at="2026-11-17T12:00:00Z",body_sha256="b"*64,entry=self.entry(action))

    def seed_git(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args],stderr=subprocess.DEVNULL)
        self.git=git
        git("init","-q");git("config","user.name","Fixture");git("config","user.email","fixture@example.invalid")
        (self.root/LIVE).parent.mkdir(parents=True)
        (self.root/LIVE).write_bytes(json_bytes(self.q))
        git("add",".");git("-c","commit.gpgsign=false","commit","-qm","Fixture base")
        self.pin=git("rev-parse","HEAD").decode().strip()

    def test_states_are_conservative_and_corrections_still_need_review(self):
        ev=self.q['registers']['EV_evidence_register'][0]
        self.q['corrections']['ev']=[dict(receipt=29,date='2026-11-14')]
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'recheck')
        ev['reviewer_ok']=True
        self.q['review_log']=[dict(evidence_id='ev',reviewer='human',decision='ok',date='2026-11-16')]
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'reviewed')
        for verdict in ['flag','query','drop']:
            self.q['review_log'].append(dict(evidence_id='ev',reviewer='second',decision=verdict,date='2026-11-17'))
            self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'active')
        self.q['review_log']=self.q['review_log'][:1]
        self.requests[0]['requested_date']='2026-11-16'
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'active')
        self.requests[0]['requested_date']='2026-11-15'
        self.requests[0]['mapping_id']='mapping'
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'active')
        self.q['row_reviews']=[dict(record_id='mapping',date='2026-11-17',decision='approve')]
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'reviewed')

    def test_reject_forgery_missing_reason_unknown_target_and_stale_basis(self):
        entry=self.entry()
        p.validate(entry,self.q,self.pin)
        for update in [dict(reason=''),dict(action='approve'),dict(reviewer='somebody'),dict(revision='b'*40),dict(targets=[]),dict(targets=entry['targets']*2)]:
            with self.subTest(update=update),self.assertRaises(ValueError):p.validate(dict(entry,**update),self.q,self.pin)
        for change in ['request','source','finding','review','rating']:
            before=copy.deepcopy(self.q);req=copy.deepcopy(self.requests)
            if change=='request': self.requests[0]['batch_label']='New question'
            elif change=='source':self.q['registers']['SRC_source_register'][0]['url']='https://example.org/new'
            elif change=='finding':self.q['registers']['EV_evidence_register'][0]['page']=4
            elif change=='review':self.q['review_log'].append(dict(evidence_id='ev',reviewer='human',decision='flag',date='2026-11-17'))
            else:
                self.requests[0]['mapping_id']='row'
                self.q['recipes']={'wetland':{'T4':[dict(mapping_id='row',weight=3)]}}
            self.refresh()
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'changed'):p.validate(entry,self.q,self.pin)
            self.q,self.requests=before,req

    def test_apply_retry_restore_history_and_changed_evidence_reactivation(self):
        self.seed_git()
        old=copy.deepcopy(self.q)
        event=self.event()
        self.assertTrue(p.append(self.root,event,self.pin))
        self.assertFalse(p.append(self.root,event,self.pin))
        self.assertFalse(p.append(self.root,dict(event,receipt=502),self.pin))
        self.refresh()
        row=self.q['priority_requests'][0]
        self.assertEqual((row['status'],row['history'][0]['actor']),('deprioritized','fixture'))
        for k in old.keys()-{'priority_requests'}:self.assertEqual(self.q[k],old[k])
        (self.root/LIVE).write_bytes(json_bytes(self.q))
        with patch.object(p,'fetch',return_value=event):p.verify(self.root,self.pin)
        # A second contributor cannot overwrite a decision they have not seen.
        with self.assertRaisesRegex(ValueError,'changed'):
            p.append(self.root,dict(event,receipt=503,actor='second'),self.pin)
        restored=self.event(504,'restore')
        self.assertTrue(p.append(self.root,restored,self.pin))
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'active')
        (self.root/LIVE).write_bytes(json_bytes(self.q))
        addressed=self.event(505,'addressed')
        self.assertTrue(p.append(self.root,addressed,self.pin))
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'addressed')
        self.q['registers']['EV_evidence_register'][0]['quote']='New source text'
        self.refresh();self.assertEqual(self.q['priority_requests'][0]['status'],'recheck')
        self.assertFalse(self.q['priority_requests'][0]['history'][-1]['current'])
        self.assertEqual(len(self.q['priority_requests'][0]['history']),3)

    def test_authentication_eligibility_edits_and_reason_are_auditable(self):
        body=p.HEADER+'\n'+json.dumps(self.entry())
        issue=dict(number=501,node_id='N',state='open',author_association='MEMBER',user={'login':'fixture'},body=body,created_at='2026-11-17T12:00:00Z')
        info={'data':{'node':{'body':body,'author':{'login':'fixture'},'lastEditedAt':None}}}
        with patch.object(p.intake,'gh',side_effect=[issue,info]):self.assertEqual(p.fetch(501)['actor'],'fixture')
        with patch.object(p.intake,'gh',return_value=dict(issue,author_association='NONE')),self.assertRaisesRegex(ValueError,'eligible'):p.fetch(501)
        info['data']['node']['lastEditedAt']='later'
        with patch.object(p.intake,'gh',side_effect=[issue,info]),self.assertRaisesRegex(ValueError,'Edited'):p.fetch(501)

    def test_verify_rejects_tampering_and_unauthenticated_events(self):
        self.seed_git();event=self.event();p.append(self.root,event,self.pin);self.refresh()
        (self.root/LIVE).write_bytes(json_bytes(self.q))
        with patch.object(p,'fetch',return_value=dict(event,actor='another')),self.assertRaisesRegex(ValueError,'misattributed'):p.verify(self.root,self.pin)
        self.q['review_log'].append(dict(evidence_id='ev',decision='ok'))
        (self.root/LIVE).write_bytes(json_bytes(self.q))
        with patch.object(p,'fetch',return_value=event),self.assertRaisesRegex(ValueError,'scientific'):p.verify(self.root,self.pin)


@unittest.skipUnless(__import__('os').environ.get('CIAT_TEST_REPO'), 'Requires pinned compiler history')
class WetlandRehearsal(unittest.TestCase):
    def test_real_wetland_requests_apply_restore_and_rebuild_without_science_changes(self):
        import os
        import shutil
        import sys
        import registers as reg
        from queue_view import publish_files
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp).resolve();dest=folder/'evidence';engine=folder/'engine'
            base='cd90e45ea26fec558859bb0d643effb779bc0bac'
            reg.snapshot(dest,'',base,['/*'],reg.ROOT)
            reg.snapshot(engine,'',reg.SEED,['/src/','/schema/','/pipeline/','/docs/review/*.json','!/docs/review/*/'],Path(os.environ['CIAT_TEST_REPO']))
            previous={k:v for k,v in sys.modules.items() if k.split('.')[0]=='nbs_ruralscan'}
            for name in previous:del sys.modules[name]
            sys.path.insert(0,str(engine/'src'))
            try:
                for file in (dest/'registers').rglob('*'):
                    target=engine/file.relative_to(dest/'registers')
                    if file.is_file() and target.is_file():shutil.copyfile(file,target)
                publish_files(engine,dest)
                subprocess.run(['git','-C',str(dest),'add','-A'],check=True)
                reg.git('-c','commit.gpgsign=false','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Fixture priority edition',cwd=dest)
                base=reg.git('rev-parse','HEAD',cwd=dest).decode().strip()
                before=json.loads((dest/LIVE).read_bytes())
                ids={'ev_wet_protected_area_status_qiu20_1','ev_wet_water_table_depth_brouwer26_1','ev_wet_flood_hazard_ramsar18_1'}
                chosen=[r for r in before['priority_requests'] if r['evidence_id'] in ids]
                self.assertEqual({r['evidence_id'] for r in chosen},ids)
                event=dict(receipt=900001,actor='fixture-reviewer',created_at='2026-11-17T12:00:00Z',body_sha256='f'*64,
                    entry=dict(kind='priority',revision=base,action='addressed',reason='Synthetic rehearsal only.',targets=[{k:r[k] for k in p.TARGET_FIELDS} for r in chosen]))
                self.assertTrue(p.append(dest,event,base));self.assertFalse(p.append(dest,event,base))
                publish_files(engine,dest)
                after=json.loads((dest/LIVE).read_bytes())
                for k in before.keys()-{'priority_requests'}:self.assertEqual(before[k],after[k])
                marked=[r for r in after['priority_requests'] if r['evidence_id'] in ids]
                self.assertTrue(all(r['status']=='addressed' for r in marked))
                with patch.object(p,'fetch',return_value=event):p.verify(dest,base)
                reg.git('add','-A',cwd=dest)
                reg.git('-c','commit.gpgsign=false','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Fixture addressed requests',cwd=dest)
                base=reg.git('rev-parse','HEAD',cwd=dest).decode().strip()
                restore=copy.deepcopy(event);restore['receipt']=900002
                restore['entry'].update(revision=base,action='restore',reason='Synthetic restore.',targets=[{k:r[k] for k in p.TARGET_FIELDS} for r in marked])
                self.assertTrue(p.append(dest,restore,base));publish_files(engine,dest)
                final=json.loads((dest/LIVE).read_bytes())
                self.assertTrue(all(r['status']=='active' for r in final['priority_requests'] if r['evidence_id'] in ids))
                with patch.object(p,'fetch',return_value=restore):p.verify(dest,base)
                for k in before.keys()-{'priority_requests'}:self.assertEqual(before[k],final[k])
            finally:
                for name in list(sys.modules):
                    if name.split('.')[0]=='nbs_ruralscan':del sys.modules[name]
                sys.modules.update(previous);sys.path.remove(str(engine/'src'))
