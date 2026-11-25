import copy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import priority_store as store


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.git("config", "user.name", "Synthetic fixture")
        self.git("config", "user.email", "fixture@example.org")
        data = b'<html><head><title>Test water index</title></head><body><h1>Test water index</h1></body></html>'
        original = self.root / "original.html"; original.write_bytes(data)
        self.candidate = {"candidate_id": "fixture", "title": "Test water index", "citation": "Test water index", "doi": "", "url": "https://example.org/index"}
        self.plan = {"candidate_id": "fixture", "kind": "website", "publisher_hosts": ["example.org"], "expected_sha256": sha256(data).hexdigest()}
        tool = store.acquisition()
        receipt, body = tool.acquire(self.candidate, self.plan, original)
        self.bundle = self.root / "bundle"; tool.publish(self.bundle, receipt, body)
        self.source = store.prepare_source(self.bundle, self.plan, self.candidate)
        self.packet = json.loads((store.ROOT / "workflows/priority_classification/packets/landmark_completeness.json").read_text())
        self.packet["source"]["artifact_sha256"] = sha256(data).hexdigest()
        relative = "workflows/priority_classification/packets/fixture.json"
        path = self.root / relative; path.parent.mkdir(parents=True); path.write_bytes(store.encoded(self.packet))
        self.git("add", relative); self.git("commit", "-qm", "Fixture packet")
        self.packet_revision = self.head()
        self.ref = {"revision": self.packet_revision, "path": relative, "sha256": sha256(path.read_bytes()).hexdigest()}
        self.finding = store.finding(self.packet, self.source, self.ref)
        store.write_object(self.root, "sources", self.source)
        store.write_object(self.root, "findings", self.finding)
        self.git("add", store.STORE); self.git("commit", "-qm", "Fixture unreviewed source and finding")
        self.base = self.head()

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root).decode().strip()

    def head(self): return self.git("rev-parse", "HEAD")

    def event(self, receipt=1, actor="reviewer", decision="keep", created="2026-11-25T12:00:00Z"):
        return {"finding_sha256": store.digest(self.finding), "finding_revision": self.base,
                "decision": decision, "reason": "Synthetic source review", "receipt": receipt,
                "actor": actor, "created_at": created, "body_sha256": "0" * 64}

    def test_actual_acquisition_replay_and_unreviewed_registration(self):
        result = store.verify(self.root, self.packet_revision)
        self.assertEqual(result, {store.digest(self.finding): "unreviewed"})
        self.assertFalse((self.root / "registers").exists())

    def test_changed_source_bytes_rejected_before_staging(self):
        (self.bundle / "cache/fixture.html").write_text("wrong source")
        with self.assertRaises(ValueError): store.prepare_source(self.bundle, self.plan, self.candidate)

    def test_packet_must_identify_acquired_edition(self):
        self.packet["source"]["artifact_sha256"] = "a" * 64
        with self.assertRaises(ValueError): store.finding(self.packet, self.source, self.ref)

    def test_pdf_cannot_claim_library_accession(self):
        source = copy.deepcopy(self.source); source["receipt"]["kind"] = "pdf"
        with patch.object(store, "acquisition") as get:
            get.return_value.check_provenance.return_value = None
            with self.assertRaises(ValueError): store.validate_source(source)

    def test_exact_retry_then_reopen_and_conflict(self):
        event = self.event()
        with patch.object(store, "fetch_review", return_value=event):
            self.assertTrue(store.record_review(self.root, 1, self.base))
            self.assertFalse(store.record_review(self.root, 1, self.base))
        self.assertEqual(store.status(store.reviews(self.root), store.digest(self.finding)), "kept")
        dissent = self.event(2, "other", "reject", "2026-11-25T12:01:00Z")
        with patch.object(store, "fetch_review", return_value=dissent): store.record_review(self.root, 2, self.base)
        self.assertEqual(store.status(store.reviews(self.root), store.digest(self.finding)), "conflict")
        reopened = self.event(3, "reviewer", "reopen", "2026-11-25T12:02:00Z")
        with patch.object(store, "fetch_review", return_value=reopened): store.record_review(self.root, 3, self.base)
        self.assertNotEqual(store.status(store.reviews(self.root), store.digest(self.finding)), "kept")

    def test_altered_receipt_and_older_vote_fail(self):
        with patch.object(store, "fetch_review", return_value=self.event()): store.record_review(self.root, 1, self.base)
        for event in [self.event(decision="reject"), self.event(2, created="2026-11-25T11:00:00Z")]:
            with patch.object(store, "fetch_review", return_value=event):
                with self.assertRaises(ValueError): store.record_review(self.root, event["receipt"], self.base)

    def test_cannot_rewrite_published_source_or_delete_history(self):
        path = store.write_object(self.root, "sources", self.source)
        path.unlink()
        with self.assertRaises(ValueError): store.verify(self.root, self.base)

    def test_review_authentication_rejects_edits_bots_and_ineligible_authors(self):
        import sys
        body = store.HEADER + "\n```json\n" + json.dumps({k: self.event()[k] for k in
            ("finding_sha256", "finding_revision", "decision", "reason")}) + "\n```"
        issue = {"node_id": "fixture", "body": body, "user": {"login": "reviewer", "type": "User"},
                 "created_at": "2026-11-25T12:00:00Z", "author_association": "MEMBER"}
        info = {"body": body, "author": {"login": "reviewer"}, "lastEditedAt": None}
        for changes, graph in [({}, info), ({}, {**info, "lastEditedAt": "2026-11-25T12:01:00Z"}),
                               ({"user": {"login": "reviewer", "type": "Bot"}}, info),
                               ({"author_association": "NONE"}, info)]:
            with patch.dict(sys.modules, {"intake": object()}), patch("subprocess.check_output", side_effect=[json.dumps({**issue, **changes}).encode(), json.dumps({"data": {"node": graph}}).encode()]):
                if not changes and graph == info:
                    self.assertEqual(store.fetch_review(1)["actor"], "reviewer")
                else:
                    with self.assertRaises(ValueError): store.fetch_review(1)

    def test_source_resolver_rejects_unreviewed_and_newer_hold(self):
        ref = {"repository": "RuralScan/evidence", "revision": self.base, "path": self.ref["path"],
               "sha256": self.ref["sha256"], "source_id": "psrc_" + store.digest(self.source),
               "finding_ids": ["pfind_" + store.digest(self.finding)]}
        with self.assertRaises(ValueError): store.resolve(self.root, ref, self.base)
        with patch.object(store, "fetch_review", return_value=self.event()): store.record_review(self.root, 1, self.base)
        self.git("add", store.REVIEWS); self.git("commit", "-qm", "Fixture keep")
        ref["revision"] = self.head()
        self.assertEqual(len(store.resolve(self.root, ref, self.head())), 1)
        event = self.event(2, decision="hold", created="2026-11-25T12:01:00Z")
        with patch.object(store, "fetch_review", return_value=event): store.record_review(self.root, 2, self.head())
        self.git("add", store.REVIEWS); self.git("commit", "-qm", "Fixture hold")
        with self.assertRaises(ValueError): store.resolve(self.root, ref, self.head())


if __name__ == "__main__": unittest.main()
