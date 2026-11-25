"""Validate technical inspection packets; this cannot register or approve evidence."""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent / 'binding_checks' / '2026-11-25'


def check(root=ROOT, raw_root=None):
    raw_roots = ([raw_root] if isinstance(raw_root, Path) else raw_root) or []
    manifest = json.loads((root / 'manifest.json').read_text())
    if (manifest['status'] != 'technical_observations_not_binding_acceptance'
            or any(manifest[k] != 0 for k in ('scientific_reviews', 'canonical_registrations', 'runtime_releases'))):
        raise ValueError('Technical inspections cannot claim acceptance or registration')
    ids = set()
    paths = set()
    for entry in manifest['records']:
        key = entry['observation_id']
        if not re.fullmatch(r'[a-z][a-z0-9_]+', key) or key in ids:
            raise ValueError('Invalid or duplicate observation ID')
        ids.add(key)
        if entry['path'] != f'observations/{key}.json':
            raise ValueError('Observation path does not match ID')
        paths.add(root / entry['path'])
        body = (root / entry['path']).read_bytes()
        if sha256(body).hexdigest() != entry['sha256']:
            raise ValueError('Observation hash mismatch')
        value = json.loads(body)
        if (value['observation_id'] != key or value['human_review'] is not None
                or value['kind'] != 'technical_inspection_not_scientific_review'):
            raise ValueError('Observation cannot supply a scientific vote')
        if not value['requests'] or not value['facts'] or not value['limits'] or not value['input_sha256']:
            raise ValueError('Missing requests, facts, limits or raw input provenance')
        for name, digest in value['input_sha256'].items():
            if Path(name).name != name or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('Invalid raw input reference')
            if raw_roots and not any((folder / name).is_file()
                                     and sha256((folder / name).read_bytes()).hexdigest() == digest
                                     for folder in raw_roots):
                raise ValueError('Raw input missing or hash mismatch: ' + name)
    if paths != set((root / 'observations').glob('*.json')):
        raise ValueError('Unmanifested or missing observation')
    return len(ids)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, action='append', help='Repeat for separate dated library folders')
    args = parser.parse_args()
    print(f'{check(raw_root=args.raw_root)} technical observations checked; no approvals created')
