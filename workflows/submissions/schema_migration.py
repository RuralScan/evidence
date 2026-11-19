"""One deterministic additive EV schema migration, verified separately from scientific receipts."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
import subprocess

import registers as reg
from classification import FIELDS, migrate_csv, validate

JOURNAL = "configuration/evidence-classification-migration.json"
CONTRACT = "rulesets/evidence-classification.json"
PIN = "rulesets/evidence-classification-pin.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_contract(root):
    from configuration import local_method
    pin = json.loads((root / PIN).read_bytes())
    if pin["repository"] != "RuralScan/method" or pin["path"] != "data-model/evidence-classification.json":
        raise ValueError("Invalid classification contract location")
    import re
    if not re.fullmatch("[0-9a-f]{40}", pin["revision"]):
        raise ValueError("Classification contract needs immutable method SHA")
    local = local_method()
    if local:
        data = subprocess.check_output(["git", "-C", str(local), "show", f"{pin['revision']}:{pin['path']}"])
    else:
        with urlopen(f"https://raw.githubusercontent.com/{pin['repository']}/{pin['revision']}/{pin['path']}", timeout=30) as response:
            data = response.read()
    if data != (root / CONTRACT).read_bytes() or digest(data) != pin["sha256"]:
        raise ValueError("Classification contract differs from pinned method bytes")


def expected_previous(root, base):
    """Return exact expected base EV bytes, allowing only the recorded migration."""
    original = reg.blob(root, base, "registers/" + reg.EV)
    exists = bool(reg.git("ls-tree", base, "--", JOURNAL, cwd=root))
    current = root / JOURNAL
    if exists:
        if not current.exists() or current.read_bytes() != reg.blob(root, base, JOURNAL):
            raise ValueError("Classification migration history changed")
        return original
    if not current.exists():
        return original
    receipt = json.loads(current.read_bytes())
    migrated = migrate_csv(original)
    expected = dict(version=1, base=base, input_sha256=digest(original), output_sha256=digest(migrated), contract_sha256=digest((root / CONTRACT).read_bytes()), rows=len(reg.rows(original)))
    if receipt != expected:
        raise ValueError("Migration receipt does not reproduce the exact additive transformation")
    return migrated


def apply(root, base):
    verify_contract(root)
    original = reg.blob(root, base, "registers/" + reg.EV)
    migrated = migrate_csv(original)
    path = root / "registers" / reg.EV
    if path.read_bytes() not in (original, migrated):
        raise ValueError("Concurrent evidence changes: migrate a clean current base")
    receipt = dict(version=1, base=base, input_sha256=digest(original), output_sha256=digest(migrated), contract_sha256=digest((root / CONTRACT).read_bytes()), rows=len(reg.rows(original)))
    history = root / JOURNAL
    if history.exists() and json.loads(history.read_bytes()) != receipt:
        raise ValueError("Migration already recorded with different inputs")
    history.write_text(json.dumps(receipt, indent=2) + "\n")
    path.write_bytes(migrated)
    print(json.dumps(dict(rows=receipt["rows"], knowledge_basis=dict(Counter(r["knowledge_basis"] for r in reg.rows(migrated)))), indent=2))


def check_rows(data):
    for row in reg.rows(data):
        validate(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args()
    apply(reg.ROOT, args.base)
