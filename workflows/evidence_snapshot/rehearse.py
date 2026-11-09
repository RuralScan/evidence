"""Rehearse read-only transfer of committed evidence tables between two Git revisions."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from git_snapshot import git as run_git, require, revision  # noqa: E402

TABLES = (
    "schema/registers/SRC_source_register.csv",
    "schema/registers/EV_evidence_register.csv",
    "schema/registers/SRCH_search_register.csv",
    "pipeline/progress_ledger.csv",
    "pipeline/acquisition_queue.csv",
    "pipeline/metrics/review_log.csv",
    "pipeline/metrics/row_review_log.csv",
)
REVIEW_SUPPORT = (
    "pipeline/metrics/clarification_log.json",
    "pipeline/metrics/gaps.csv",
    "pipeline/cited_originals.csv",
    "pipeline/review_priorities.csv",
)
PROFILES = {"core": TABLES, "review-support": TABLES + REVIEW_SUPPORT}


def git(*args, cwd):
    # Do not fetch missing objects into a partial clone or honour replacement
    # refs that give pinned commits different bytes in this working copy.
    return run_git("--no-lazy-fetch", "--no-replace-objects", *args, cwd=cwd)


def inventory(repo, commit, profile="core"):
    paths = PROFILES[profile]
    entries = git("ls-tree", "--full-tree", "-z", commit, "--", *paths, cwd=repo)
    files = {}
    for entry in entries.split(b"\0"):
        if entry:
            meta, path = entry.decode().split("\t", 1)
            mode, kind, oid = meta.split()
            require(
                mode == "100644" and kind == "blob",
                f"Expected a regular file at {path}",
            )
            files[path] = oid
    require(set(TABLES) <= files.keys(), f"Required tables missing at {commit}")
    # Support records can be introduced or retired between revisions. A null
    # entry denotes absence; an existing empty file has its own blob ID.
    return {path: files.get(path) for path in paths}


def history(repo, base, target, profile="core"):
    # Follow what landed on the branch, including the result of each merge.
    base, target = revision(base), revision(target)
    for commit in {base, target}:
        require(
            git("cat-file", "-t", commit, cwd=repo).strip() == b"commit",
            "Expected a Git commit",
        )
    initial = inventory(repo, base, profile)
    current = initial.copy()
    previous = base
    changes = []
    git_log = git(
        "rev-list",
        "--first-parent",
        "--parents",
        "--reverse",
        f"{base}..{target}",
        cwd=repo,
    )
    for line in git_log.decode().splitlines():
        commit, *parents = line.split()
        require(
            parents and parents[0] == previous,
            "Base is outside target's first-parent history",
        )
        files = inventory(repo, commit, profile)
        delta = {path: oid for path, oid in files.items() if current[path] != oid}
        current.update(delta)
        require(current == files, f"Delta inventory differs at {commit}")
        changes.append({"revision": commit, "updates": delta})
        previous = commit
    require(previous == target, "Base is outside target's first-parent history")
    manifest = {
        "format_version": 1,
        "base": base,
        "target": target,
        "initial": initial,
        "changes": changes,
    }
    if profile != "core":
        manifest.update(format_version=2, profile=profile)
    return manifest


def object_ids(records):
    ids = set(records["initial"].values())
    for step in records["changes"]:
        ids.update(step["updates"].values())
    ids.discard(None)
    return sorted(ids)


def destination(path, repo):
    parent = path.parent.resolve(strict=True)
    require(parent.is_dir(), "The destination parent must be a directory")
    path = parent / path.name
    require(not os.path.lexists(path), f"Choose a new destination: {path}")
    require(
        not any(
            (p / ".git").exists() or p.name == ".git" for p in (parent, *parent.parents)
        ),
        "Keep private evidence files outside Git working copies",
    )
    git_dir = Path(
        git("rev-parse", "--absolute-git-dir", cwd=repo).decode().strip()
    ).resolve()
    require(
        not path.is_relative_to(git_dir),
        "Keep private evidence files outside Git storage",
    )
    return path


def check_bundle(bundle, records, repo):
    # Derive the trusted manifest independently from both caller-supplied Git pins.
    # Comparing bytes preserves duplicate events, CSV quoting, row order and blanks.
    ids = object_ids(records)
    members = ["manifest.json", *("objects/" + oid for oid in ids)]
    require(
        sorted(bundle.namelist()) == sorted(members), "Snapshot file inventory differs"
    )
    compare_member(bundle, "manifest.json", manifest_bytes(records))
    for oid in ids:
        compare_member(bundle, "objects/" + oid, git("cat-file", "blob", oid, cwd=repo))


def manifest_bytes(records):
    return (json.dumps(records, indent=2, sort_keys=True) + "\n").encode("utf-8")


def compare_member(bundle, name, expected):
    require(
        bundle.getinfo(name).file_size == len(expected)
        and bundle.read(name) == expected,
        f"Snapshot member differs from Git: {name}",
    )


def create(repo, records, out):
    out = destination(out, repo)
    with TemporaryDirectory(dir=out.parent) as temp:
        stage = Path(temp) / "snapshot.zip"
        with ZipFile(stage, "x", compression=ZIP_DEFLATED, compresslevel=4) as bundle:
            bundle.writestr("manifest.json", manifest_bytes(records))
            for oid in object_ids(records):
                bundle.writestr(
                    "objects/" + oid, git("cat-file", "blob", oid, cwd=repo)
                )
        stage.chmod(0o600)
        with ZipFile(stage) as bundle:
            check_bundle(bundle, records, repo)
        # Exclusive publication, including concurrent retries. Temporary and
        # final locations share a filesystem, so readers see a complete bundle.
        os.link(stage, out)


def export_tables(bundle, records, commit, out, repo):
    files = records["initial"].copy()
    current = records["base"]
    for step in records["changes"]:
        if current == commit:
            break
        files.update(step["updates"])
        current = step["revision"]
    require(current == commit, "Requested revision is outside this snapshot")
    out = destination(out, repo)
    # Publish the entire revision directory in one rename. Reserving its
    # parent with mkdir also protects unrelated empty directories on retries.
    with TemporaryDirectory(dir=out.parent) as tmp:
        stage = Path(tmp) / "tables"
        stage.mkdir(mode=0o700)
        for name, oid in files.items():
            if oid is None:
                continue
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle.read("objects/" + oid))
            path.chmod(0o400)
        out.mkdir(mode=0o700)
        try:
            stage.rename(out / commit)
        except OSError:
            out.rmdir()
            raise


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="action", required=True)
    build = commands.add_parser(
        "create", help="Create and verify a new private snapshot"
    )
    check = commands.add_parser("verify", help="Compare an existing snapshot with Git")
    for command in (build, check):
        command.add_argument(
            "--profile",
            choices=PROFILES,
            default="core",
            help="Select the same record set when creating and verifying",
        )
        command.add_argument(
            "--ciat-repo",
            required=True,
            type=Path,
            help="Local clone with both pinned revisions",
        )
        command.add_argument("--base", required=True, help="Full baseline commit")
        command.add_argument("--target", required=True, help="Full target commit")
        command.add_argument(
            "--bundle", required=True, type=Path, help="Private snapshot file"
        )
    check.add_argument(
        "--export-to",
        type=Path,
        help="Write read-only tables into a new private directory",
    )
    check.add_argument(
        "--at", help="Export this first-parent revision; default is the target"
    )
    args = cli.parse_args()
    if getattr(args, "at", None) and not args.export_to:
        cli.error("--at requires --export-to")
    records = history(args.ciat_repo, args.base, args.target, args.profile)
    if args.action == "create":
        create(args.ciat_repo, records, args.bundle)
    else:
        with ZipFile(args.bundle) as bundle:
            check_bundle(bundle, records, args.ciat_repo)
            if args.export_to:
                export_tables(
                    bundle,
                    records,
                    args.at or args.target,
                    args.export_to,
                    args.ciat_repo,
                )
    changed = {path for step in records["changes"] for path in step["updates"]}
    noun = "tables" if args.profile == "core" else "paths"
    print(
        f"Verified {len(PROFILES[args.profile])} {noun}, {len(records['changes'])} first-parent steps, "
        f"{len(changed)} changed {noun}, {len(object_ids(records))} distinct file versions."
    )


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        sys.exit(f"Snapshot check failed: {error}")
