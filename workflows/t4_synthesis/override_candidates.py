"""Generate typed pending override records from their authoritative CSV."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t4_synthesis.profiles import validate_candidate

COLUMNS = ['format', 'id', 'status', 'activate', 'profile', 'justification', 'evidence_refs']
JSON_FIELDS = {'activate', 'profile', 'justification', 'evidence_refs'}
DEFAULT = Path(__file__).resolve().parents[2] / 'suitability/overrides'


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def records(folder):
    with (folder / 'overrides.csv').open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Use the exact pending override CSV header')
        seen, result = set(), []
        for raw in reader:
            if None in raw or None in raw.values():
                raise ValueError('Malformed pending override CSV row')
            row = {k: json.loads(v) if k in JSON_FIELDS else v for k, v in raw.items()}
            name = row['id']
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name) or name in seen:
                raise ValueError('Invalid or duplicate pending override ID')
            validate_candidate(row)
            seen.add(name)
            result.append(row)
    if not result:
        raise ValueError('No pending override records')
    return sorted(result, key=lambda row: row['id'])


def generate(folder=DEFAULT, check=False):
    items = records(folder)
    expected = {row['id'] + '.json': encoded(row) for row in items}
    dest = folder / 'candidates'
    present = {p.name for p in dest.iterdir()} if dest.exists() else set()
    if present - set(expected):
        raise ValueError('Unexpected candidate file; preserve history explicitly, do not silently remove it')
    if check:
        if present != set(expected) or any((dest/name).is_symlink() or (dest/name).read_bytes() != data for name, data in expected.items()):
            raise ValueError('Stale generated candidates; regenerate from overrides.csv')
    else:
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in expected.items():
            if (dest/name).is_symlink():
                raise ValueError('Linked candidate output refused')
            (dest/name).write_bytes(data)
    return [{'id': row['id'], 'sha256': hashlib.sha256(expected[row['id'] + '.json']).hexdigest(),
             'status': 'pending', 'activate': False} for row in items]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=DEFAULT)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps({'candidates': generate(args.folder, args.check), 'accepted': False}, indent=2))
