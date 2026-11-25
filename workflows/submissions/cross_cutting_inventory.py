"""Admit only disabled cross-cutting proposal metadata beside frozen registers."""
from hashlib import sha256
import json

CONTROL_FILES = {'cross_cutting/README.md', 'cross_cutting/manifest.json'}
STORES = {'XCS':'registers/cross_cutting/sources.jsonl',
          'XCE':'registers/cross_cutting/findings.jsonl',
          'XSRCH':'registers/cross_cutting/searches.jsonl',
          'review_events':'registers/cross_cutting/review_events.jsonl'}

def require(ok, message):
    if not ok: raise ValueError(message)


def verify_inventory(root, expected, actual):
    """No open-ended directory allowlist and no change to the migration manifest."""
    path=root/'registers/cross_cutting/manifest.json'
    additions=set()
    if path.exists():
        proposal=json.loads(path.read_text())
        require(proposal['format']=='ruralscan.cross-cutting-register-proposal.v1'
                and proposal['status']=='proposed_not_activated'
                and proposal['activation']=='disabled'
                and type(proposal['canonical_record_count']) is int
                and proposal['canonical_record_count']==0,
                'Cross-cutting registration is not activated')
        require(proposal['proposed_stores']==STORES, 'Unexpected prospective stores')
        require(proposal['registration']=='not_implemented_pending_protected_review_adapter',
                'Canonical registration needs its own reviewed adapter')
        ref=proposal['candidate_schema']
        require(ref['path']=='workflows/priority_classification/candidate-schema.json',
                'Unexpected cross-cutting candidate schema')
        require(sha256((root/ref['path']).read_bytes()).hexdigest()==ref['sha256'],
                'Cross-cutting candidate schema digest changed')
        additions=CONTROL_FILES
    require(expected | additions == actual, 'Unexpected register inventory')
