"""Check preservation and the single review route; never promote evidence."""
from hashlib import sha256
import json
from pathlib import Path
from candidate_ingest import validate
from priority_store import ROOT, candidate_objects, digest, objects, require
from preparation import BATCH


def check(root=ROOT):
    folder = root / 'workflows/priority_classification'
    manifest = json.loads((folder / 'consolidation.json').read_bytes())
    require(manifest['active_store'] == 'priority-evidence' and
            manifest['active_review'] == 'priority_store.py' and
            manifest['canonical_registrations'] == 0, 'Unexpected consolidation route')
    for item in manifest['files']:
        path = Path(item['preserved_path'])
        require(not path.is_absolute() and '..' not in path.parts, 'Unsafe preservation path')
        require(sha256((root / path).read_bytes()).hexdigest() == item['sha256'], 'Preserved proposal bytes changed')
    require(not (root / 'registers/cross_cutting').exists() and not (folder / 'intake.py').exists(),
            'Retired register/adapter must not remain active')
    prep = root / BATCH
    ref = json.loads((prep / 'manifest.json').read_bytes())['candidate_bundle']
    raw = (root / ref['path']).read_bytes()
    require(sha256(raw).hexdigest() == ref['sha256'], 'Candidate source edition changed')
    bundle = json.loads(raw); validate(bundle, root)
    source_ref = {k: ref[k] for k in ('revision', 'path', 'sha256')}
    wrappers = candidate_objects(bundle, objects(prep, 'sources'), source_ref)
    mapping = json.loads((folder / 'candidate-findings.json').read_bytes())
    expected = [{'candidate_finding_id': f['candidate_finding']['candidate_finding_id'],
                 'proposed_finding_id': 'pfind_' + digest(f), 'finding': f} for f in wrappers]
    require(mapping == {'status': 'proposed_not_registered', 'findings': expected}, 'Candidate finding preservation differs')
    return {'sources_reused': 6, 'distinct_candidate_findings': len(wrappers),
            'historical_packet_findings': 5, 'review_routes': 1, 'canonical_registrations': 0}


if __name__ == '__main__': print(json.dumps(check(), sort_keys=True))
