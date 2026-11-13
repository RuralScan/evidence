"""Export or verify RuralScan's starting registers at the CIAT #691 merge."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from rehearse import PROFILES, git, require
from git_snapshot import snapshot

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://github.com/CIAT/nbs_ruralscan"
REVISION = "e43c42bd581dba791ce1f1697b6b41952ab0cfe3"
PREVIOUS = "69f53985799719aa87bd1e4c26d1f1555bfde349"
METHOD = "methodology/decisions/open_decisions.csv"
PUBLISHED_METHOD = "methodology/decisions/method_decisions.csv"

# Keep producer paths so existing validators can read a destination overlay.
PATHS = (
    *PROFILES["review-support"],
    "schema/registers/BANDS_magnitude_bands.csv",
    "schema/registers/BIND_dataset_binding.csv",
    "schema/registers/FAM_family_registry.csv",
    "schema/registers/TOOL_tool_registry.csv",
    "schema/registers/VONT_variable_ontology.csv",
    "schema/registers/XW_target_crosswalk.csv",
    "pipeline/metrics/benchmark_divergence_log.csv",
    "pipeline/metrics/learnings_log.csv",
    "pipeline/metrics/learnings_log.feedback.json",
    "pipeline/metrics/learnings_log.feedback.scoped.csv",
    "pipeline/metrics/sweep_log.csv",
    "pipeline/metrics/rating_setters.json",
    "pipeline/metrics/review_flags.csv",
    "pipeline/metrics/review_ranking.csv",
    METHOD,
)
# Release dependencies stay with their producers. A Git tree ID pins every member.
REFERENCES = (
    "schema",
    "scripts",
    "src/nbs_ruralscan",
    "pipeline/t4_audit",
    "docs/review",
    "methodology/RULESET_VERSIONS.md",
    "methodology/discovery_logs",
    ".agents/skills",
)


def csv_reader(data):
    return csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)


def method_records(data):
    reader = csv_reader(data)
    columns = list(reader.fieldnames)
    columns.remove("owner")  # Task assignments stay in the original method ledger.
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(reader)
    return output.getvalue().encode()


def seed(repo):
    manifest = {
        "format_version": 1,
        "source_repository": SOURCE,
        "source_revision": REVISION,
        "previous_checkpoint": PREVIOUS,
        "source_pull_request": 691,
        "files": {},
        "external_inputs": {
            path: git("rev-parse", f"{REVISION}:{path}", cwd=repo).decode().strip()
            for path in REFERENCES
        },
    }
    files = {}
    for source_path in PATHS:
        data = git("show", f"{REVISION}:{source_path}", cwd=repo)
        path = source_path
        metadata = {
            "source_path": source_path,
            "source_sha256": hashlib.sha256(data).hexdigest(),
        }
        if source_path == METHOD:
            path = PUBLISHED_METHOD
            data = method_records(data)
            metadata["omitted_columns"] = ["owner"]
        metadata["sha256"] = hashlib.sha256(data).hexdigest()
        metadata["bytes"] = len(data)
        if path.endswith(".csv"):
            metadata["rows"] = sum(1 for _ in csv_reader(data))
        manifest["files"][path] = metadata
        files[path] = data
    files["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    ).encode()
    return files


def verify(folder, files):
    paths = {
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if p.is_file() or p.is_symlink()
    }
    require(
        paths == set(files), f"Register inventory differs: {sorted(paths ^ set(files))}"
    )
    for path, expected in files.items():
        member = folder / path
        require(member.resolve() == folder.resolve() / path, f"Linked register: {path}")
        require(
            member.read_bytes() == expected, f"Register differs from source: {path}"
        )


def rebuild(repo, folder):
    with TemporaryDirectory() as tmp:
        source = Path(tmp) / "producer"
        snapshot(
            source, SOURCE + ".git", REVISION, ["/src/", "/schema/", "/pipeline/"], repo
        )
        for path in PATHS:
            if path != METHOD:
                shutil.copyfile(folder / path, source / path)
        env = {**os.environ, "PYTHONPATH": str(source / "src")}
        subprocess.run(
            [
                sys.executable,
                "-m",
                "nbs_ruralscan.recipe.publish_release",
                "check",
                "--source-root",
                str(source),
            ],
            cwd=source,
            env=env,
            check=True,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciat-repo", type=Path, required=True)
    parser.add_argument(
        "--export-to", type=Path, help="Write the verified seed to a new directory"
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Recompile all practices with the migrated register bytes",
    )
    args = parser.parse_args()
    files = seed(args.ciat_repo)
    folder = ROOT / "registers"
    if args.export_to:
        folder = args.export_to
        require(
            not folder.exists() and not folder.is_symlink(),
            f"Destination already exists: {folder}",
        )
        with TemporaryDirectory(dir=folder.parent) as tmp:
            stage = Path(tmp) / "registers"
            for path, data in files.items():
                member = stage / path
                member.parent.mkdir(parents=True, exist_ok=True)
                member.write_bytes(data)
            verify(stage, files)
            stage.rename(folder)
    verify(folder, files)
    print(
        f"Verified {len(files) - 1} register and support files at {REVISION}.",
        flush=True,
    )
    if args.rebuild:
        rebuild(args.ciat_repo, folder)


if __name__ == "__main__":
    main()
