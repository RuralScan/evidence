"""Validate or evaluate pending profile candidates; never stage accepted T4 rows."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from t4_synthesis import profiles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "evaluate"])
    parser.add_argument("path", type=Path, help="One candidate or candidate directory")
    parser.add_argument("--inputs", type=Path, help="JSON object with values and context")
    parser.add_argument("--committed", action="store_true", help="Require exact HEAD blobs; no scientific approval implied")
    args = parser.parse_args()
    paths = sorted(args.path.rglob("*.json")) if args.path.is_dir() else [args.path]
    profiles.require(bool(paths), "No candidate JSON files found")
    ids = set()
    for path in paths:
        profiles.require(path.is_file() and not path.is_symlink(), "Candidate must be a regular file")
        if args.committed:
            root = Path(subprocess.check_output(["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"], text=True).strip())
            raw = subprocess.check_output(["git", "-C", str(root), "show", "HEAD:" + path.resolve().relative_to(root.resolve()).as_posix()])
            profiles.require(raw == path.read_bytes(), "Candidate differs from committed bytes")
        record = profiles.validate_candidate(json.loads(path.read_bytes()))
        profiles.require(record["id"] not in ids, "Duplicate candidate ID")
        ids.add(record["id"])
        if args.command == "evaluate":
            profiles.require(len(paths) == 1 and args.inputs is not None, "Evaluate one candidate with --inputs")
            sample = json.loads(args.inputs.read_bytes())
            profiles.exact(sample, "values context", "Sample needs values and context")
            result = profiles.evaluate_candidate(record, sample["values"], sample["context"])
            print(json.dumps(dict(id=record["id"], status="pending", activate=False, result=result), indent=2, allow_nan=False))
        else:
            print(f"Valid pending representation: {record['id']} — no scientific acceptance")


if __name__ == "__main__":
    main()
