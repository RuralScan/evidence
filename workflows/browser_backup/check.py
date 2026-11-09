"""Rehearse CIAT browser draft restoration with an in-memory destination."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from git_snapshot import git, require, revision, snapshot  # noqa: E402

ENGINE = "ece8d8226fed4a0b04d155888a8b4925d8f35386"
REPO = "https://github.com/CIAT/nbs_ruralscan.git"

MODULE = "docs/review/browser-backup.js"
INDEX = "docs/review/index.json"
TEST = "tests/js/browser_review_backup.test.cjs"


def unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("Repeated backup field")
        fields[key] = value
    return fields


def read_export(path, label):
    folder = path.resolve().parent
    require(
        not path.is_symlink()
        and path.is_file()
        and not any(
            p.name.casefold() == ".git" or (p / ".git").exists()
            for p in (folder, *folder.parents)
        ),
        f"Use a private, regular {label} JSON export outside Git",
    )
    try:
        backup = json.loads(
            path.read_bytes().decode("utf-8"), object_pairs_hook=unique_fields
        )
    except (OSError, ValueError, RecursionError):
        raise ValueError(f"Cannot read {label} backup as UTF-8 JSON") from None
    require(isinstance(backup, dict), f"Invalid {label} backup")
    return backup


def materialize(work, local, index_pin, self_test):
    paths = [MODULE, INDEX] + ([TEST] if self_test else [])
    if local is None:
        snapshot(work / "ciat", REPO, ENGINE, paths, None)
        return work / "ciat"
    # Read committed blobs. Local edits and replacement refs must not substitute
    # different code for the pinned implementation.
    literal = ("--no-lazy-fetch", "--no-replace-objects")
    require(
        git(*literal, "cat-file", "-t", index_pin, cwd=local).strip() == b"commit",
        "Expected a receiving index commit",
    )
    for name in paths:
        pin = index_pin if name == INDEX else ENGINE
        data = git(*literal, "show", f"{pin}:{name}", cwd=local)
        dest = work / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return work


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--example", action="store_true", help="Use synthetic browser drafts"
    )
    mode.add_argument(
        "--backup", type=Path, help="Private copy of the source browser backup"
    )
    mode.add_argument(
        "--self-test",
        action="store_true",
        help="Run the native and rehearsal regression tests",
    )
    cli.add_argument(
        "--destination", type=Path, help="Private copy of the receiving browser backup"
    )
    cli.add_argument(
        "--ciat-repo", type=Path, help="Use existing local CIAT Git objects offline"
    )
    cli.add_argument(
        "--index-revision",
        type=revision,
        default=ENGINE,
        help="Full receiving CIAT commit for the review batch index",
    )
    args = cli.parse_args()
    if args.destination and not args.backup:
        cli.error("--destination requires --backup")
    if not args.ciat_repo and (args.backup or args.index_revision != ENGINE):
        cli.error("Private backups and alternate batch indexes require --ciat-repo")

    with TemporaryDirectory() as directory:
        root = materialize(
            Path(directory), args.ciat_repo, args.index_revision, args.self_test
        )
        module, index = root / MODULE, root / INDEX
        env = dict(os.environ)
        for name in ("NODE_OPTIONS", "NODE_PATH", "NODE_V8_COVERAGE"):
            env.pop(name, None)
        if args.self_test:
            subprocess.run(
                [sys.executable, "-IB", "-m", "unittest", "discover", "-s", str(HERE)],
                check=True,
            )
            subprocess.run(["node", str(root / TEST)], check=True, env=env)
            env.update(
                RURALSCAN_BACKUP_ENGINE=str(module), RURALSCAN_REVIEW_INDEX=str(index)
            )
            subprocess.run(
                ["node", "--test", str(HERE / "test_replay.cjs")], check=True, env=env
            )
            return 0
        payload = (
            {"example": True}
            if args.example
            else {"backup": read_export(args.backup, "source")}
        )
        if args.destination:
            payload["destination"] = read_export(args.destination, "destination")
        result = subprocess.run(
            ["node", str(HERE / "replay.cjs"), str(module), str(index)],
            input=json.dumps(payload, allow_nan=False).encode(),
            capture_output=True,
            env=env,
        )
        # Native exceptions can include raw draft contents. Forward only the
        # worker's aggregate receipt, including its sanitized failure category.
        require(
            result.returncode in (0, 1) and result.stdout,
            "Browser rehearsal could not run",
        )
        report = json.loads(result.stdout)
        print(
            json.dumps(
                {
                    "engine_revision": ENGINE,
                    "index_revision": args.index_revision,
                    **report,
                },
                indent=2,
            )
        )
        return result.returncode


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(
            str(error)
            if isinstance(error, ValueError)
            else "Could not load the required Git objects or run Node.js."
        )
