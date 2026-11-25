"""Verify a registration preparation without activating sources or findings."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from priority_store import ROOT, STORE, REVIEWS, blob, digest, objects, require, verify

BATCH = Path('workflows/priority_classification/preparations/2026-11-25')


def check(root=ROOT, relative=BATCH, library_project=None):
    folder = root / relative
    manifest = json.loads((folder / 'manifest.json').read_bytes())
    require(manifest['format'] == 'ruralscan.priority-registration-preparation.v1' and
            manifest['status'] == 'proposed_not_registered' and manifest['registered_sources'] == 0 and
            manifest['registered_findings'] == 0, 'Preparation cannot claim registration')
    require(not (folder / REVIEWS).exists(), 'Preparation cannot contain review votes')
    states = verify(folder, authenticate=False)
    require(set(states.values()) <= {'unreviewed'}, 'Preparation cannot claim source review')
    sources = objects(folder, 'sources'); findings = objects(folder, 'findings')
    ref = manifest['candidate_bundle']
    require(ref['repository'] == 'RuralScan/evidence', 'Wrong candidate repository')
    raw = blob(root, ref['revision'], ref['path'])
    require(sha256(raw).hexdigest() == ref['sha256'], 'T5 candidate bundle changed')
    bundle = json.loads(raw)
    candidates = {s['candidate_source_id']: s for s in bundle['sources']}
    rows = manifest['sources']
    require(len(rows) == len(candidates) == len(sources) and
            {r['candidate_source_id'] for r in rows} == set(candidates), 'Incomplete or duplicated source reconciliation')
    used_sources = set(); used_findings = set()
    for row in rows:
        key = row['proposed_source_id']
        require(re.fullmatch(r'psrc_[0-9a-f]{64}', key), 'Invalid staged source identity')
        key = key[5:]; require(key in sources and key not in used_sources, 'Duplicate/missing staged source')
        used_sources.add(key)
        receipt = sources[key]['receipt']; candidate = candidates[row['candidate_source_id']]
        require(receipt['artifact']['sha256'] == row['artifact_sha256'] == candidate['artifact']['sha256'],
                'Crosswalk must identify the exact same source bytes')
        require(receipt['artifact']['bytes'] == row['bytes'], 'Source size differs')
        path = Path(row['library_path'])
        require(not path.is_absolute() and '..' not in path.parts and 'library' in path.parts, 'Unsafe accession path')
        require(row['accession_state'] == 'local_synced_folder_copy_verified_remote_access_unconfirmed', 'Unsupported access claim')
        if library_project is not None:
            data = (library_project / path).read_bytes()
            require(len(data) == row['bytes'] and sha256(data).hexdigest() == row['artifact_sha256'], 'Library copy differs')
        if receipt['kind'] == 'pdf':
            require(sources[key]['shared_copy']['library_path'] == row['library_path'], 'PDF accession mismatch')
        expected = [f['candidate_finding_id'] for f in bundle['findings'] if f['candidate_source_id'] == row['candidate_source_id']]
        require(row['candidate_finding_ids'] == expected and row['relationship'] == 'same_source_bytes_not_equivalent_findings',
                'Candidate observations must remain distinct')
        fid = row['proposed_finding_id']
        if fid is not None:
            require(re.fullmatch(r'pfind_[0-9a-f]{64}', fid) and fid[6:] in findings, 'Missing staged finding')
            require(findings[fid[6:]]['source_sha256'] == key, 'Finding points to another source')
            used_findings.add(fid[6:])
    require(used_findings == set(findings), 'Unmapped staged finding')
    return {'sources_prepared': len(sources), 'packet_findings_prepared': len(findings),
            't5_candidate_findings_preserved': len(bundle['findings']), 'registered_sources': 0,
            'registered_findings': 0, 'remote_access_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library-project', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(library_project=args.library_project), sort_keys=True))
