"""Check the identity of archived instructions against a local CIAT Git clone."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "workflows"))
from git_snapshot import git, require, revision  # noqa: E402


def archived_files(repo, commit, version):
    """Read regular files from the archive tree. Ignore working-copy edits."""
    prefix = f".agents/skills/_versions/{version}/"
    options = ("--no-replace-objects", "--no-lazy-fetch")
    require(
        git(*options, "cat-file", "-t", commit, cwd=repo).strip() == b"commit",
        f"Expected commit {commit}",
    )
    tree = git(
        *options, "ls-tree", "-r", "-z", "--full-tree", commit, "--", prefix, cwd=repo
    )
    files = {}
    for record in tree.split(b"\0"):
        if not record:
            continue
        info, name = record.split(b"\t", 1)
        mode, kind, oid = info.split()
        require(mode == b"100644" and kind == b"blob", "Expected regular archive file")
        files[name.decode()] = git(*options, "cat-file", "blob", oid.decode(), cwd=repo)
    require(files, f"Missing archive for {version} at {commit}")
    return files


def verify(catalog_bytes, repo):
    catalog = json.loads(catalog_bytes)
    require(
        catalog["format_version"] == 1
        and catalog["repository"] == "https://github.com/CIAT/nbs_ruralscan.git"
        and catalog["entries"],
        "Unsupported or empty ruleset catalog",
    )
    entries = {}
    for name, entry in catalog["entries"].items():
        version = entry["version"]
        require(re.fullmatch(r"v\d+\.\d+\.\d+", version), "Invalid ruleset version")
        commit = revision(entry["revision"])
        files = archived_files(repo, commit, version)
        hashes = {path: sha256(data).hexdigest() for path, data in files.items()}
        require(hashes == entry["files"], f"{name}: archive paths or checksums differ")
        entrypoint = entry["entrypoint"]
        require(entrypoint in files, f"{name}: missing entrypoint")
        header = files[entrypoint].decode("utf-8").split("---", 2)
        require(len(header) == 3 and header[0] == "", f"{name}: missing front matter")
        declared = re.findall(
            r'^\s*(?:ruleset_version|version):\s*"?([\w.]+)"?\s*$', header[1], re.M
        )
        require(declared == [entry["declared_version"]], f"{name}: declaration differs")
        entries[name] = {
            "version": version,
            "declared_version": declared[0],
            "revision": commit,
            "verified_files": len(files),
        }
    return {"catalog_sha256": sha256(catalog_bytes).hexdigest(), "entries": entries}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--ciat-repo", type=Path, required=True, help="Local CIAT clone")
    args = cli.parse_args()
    print(
        json.dumps(
            verify((HERE / "catalog.json").read_bytes(), args.ciat_repo), indent=2
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Ruleset verification failed: {exc}")
