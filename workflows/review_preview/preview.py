# /// script
# requires-python = ">=3.12"
# dependencies = ["requests==2.34.2"]
# ///

"""Preview a saved review batch using the pinned CIAT replay on temporary copies."""

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
EV = "schema/registers/EV_evidence_register.csv"
LOG = "pipeline/metrics/review_log.csv"
HISTORY = "pipeline/metrics/clarification_log.json"
PENDING = ("decisions.json", "clarifications.json")


def read_copy(root, name):
    path = root / name
    require(
        path.resolve().is_relative_to(root.resolve()) and not path.is_symlink(),
        f"Expected an input inside the selected copy: {name}",
    )
    if not path.exists():
        return None
    require(path.is_file(), f"Expected a regular file: {name}")
    return path.read_bytes()


def load_records(records, repo, record_pin):
    tables = {name: read_copy(records, name) for name in (EV, LOG, HISTORY)}
    require(
        tables[EV] is not None and tables[LOG] is not None,
        "Evidence and review log are required",
    )
    if record_pin:
        args = ("--no-lazy-fetch", "--no-replace-objects")
        require(
            git(*args, "cat-file", "-t", record_pin, cwd=repo).strip() == b"commit",
            "Expected a commit",
        )
        names = set(
            git(
                *args,
                "ls-tree",
                "--full-tree",
                "--name-only",
                "-z",
                record_pin,
                "--",
                *tables,
                cwd=repo,
            )
            .decode()
            .split("\0")
        )
        for name, data in tables.items():
            expected = (
                git(*args, "show", f"{record_pin}:{name}", cwd=repo)
                if name in names
                else None
            )
            require(data == expected, f"Export differs from pinned CIAT record: {name}")
    return tables


def load_inputs(records, pending, repo, record_pin):
    tables = load_records(records, repo, record_pin)
    entries = {name: read_copy(pending, name) for name in PENDING}
    require(
        any(data is not None for data in entries.values()),
        "Saved decision or clarification file required",
    )
    for name, data in entries.items():
        require(
            data == read_copy(pending, name),
            "Saved review inputs changed while reading",
        )
        tables["pipeline/review/" + name] = data
    return tables


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--example",
        action="store_true",
        help="Use the bundled synthetic records and decisions",
    )
    mode.add_argument(
        "--records",
        type=Path,
        help="Private exported revision directory, named by its full CIAT commit",
    )
    cli.add_argument(
        "--previous-records",
        type=Path,
        help="Compare the same saved batch against this earlier private export.",
    )
    cli.add_argument(
        "--pending-dir", type=Path, help="Stable private copy of pending review files"
    )
    cli.add_argument(
        "--ciat-repo",
        type=Path,
        help="Local Git objects for the engine and record revisions",
    )
    cli.add_argument(
        "--rehearse-recovery",
        action="store_true",
        help="Interrupt a disposable local submission, advance its records and retry.",
    )
    args = cli.parse_args()
    if args.rehearse_recovery and args.records and not args.previous_records:
        cli.error("Private recovery requires --previous-records and --records")
    if (
        args.example
        and (args.pending_dir or args.previous_records)
        or args.records
        and not (args.pending_dir and args.ciat_repo)
    ):
        cli.error(
            "Use --example, or supply --records, --pending-dir and --ciat-repo together"
        )
    records = args.records or HERE / "example/records"
    pending = args.pending_dir or HERE / "example/pending"
    pin = revision(records.name) if args.records else None
    if pin:
        folders = [records, pending]
        if args.previous_records:
            folders.append(args.previous_records)
            previous = revision(args.previous_records.name)
            history = (
                git(
                    "--no-lazy-fetch",
                    "--no-replace-objects",
                    "rev-list",
                    "--first-parent",
                    pin,
                    cwd=args.ciat_repo,
                )
                .decode()
                .splitlines()
            )
            require(
                previous in history,
                "Previous revision is outside the target's first-parent history",
            )
        for folder in folders:
            root = folder.resolve(strict=True)
            require(
                root.is_dir()
                and all(
                    not (p / ".git").exists() and p.name != ".git"
                    for p in (root, *root.parents)
                ),
                "Select private copies outside a Git checkout",
            )
    with TemporaryDirectory(prefix="ruralscan-review-preview-") as tmp:
        work = Path(tmp)
        code = work / "engine"
        snapshot(code, REPO, ENGINE, ["/src/"], args.ciat_repo)
        home = work / "user"
        home.mkdir()
        # A separate interpreter keeps compiler imports, bytecode and the
        # per-user SQLite lock away from the operator's review session.
        command = [
            sys.executable,
            "-I",
            "-B",
            str(HERE / "worker.py"),
            *(["--rehearse-recovery"] if args.rehearse_recovery else []),
            str(code / "src"),
            str(records.resolve()),
            str(pending.resolve()),
        ]
        if pin:
            command.extend([str(args.ciat_repo.resolve()), pin])
        if args.previous_records:
            command.extend([str(args.previous_records.resolve()), previous])
        result = subprocess.run(
            command,
            cwd=work,
            env={**os.environ, "HOME": str(home), "USERPROFILE": str(home)},
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        )
    report = {
        "review_engine_revision": ENGINE,
        "records_revision": pin,
        "example": args.example,
        **json.loads(result.stdout),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Preview failed: {error}")
