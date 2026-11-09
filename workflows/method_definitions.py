"""Verify a Rural Scan method definition snapshot against a trusted lock."""

from hashlib import sha256
import json
from urllib.request import urlopen

from git_snapshot import git, require, revision, snapshot

METHOD = "https://github.com/RuralScan/method.git"


def load_definitions(destination, lock, local=None):
    """Materialize and validate every member of the pinned definition inventory."""
    require(
        lock["repository"] == METHOD
        and lock["manifest"] == "data-model/definition-snapshot.json",
        "Unknown method publisher or manifest",
    )
    commit = revision(lock["revision"])
    if local:
        data = git("show", f"{commit}:{lock['manifest']}", cwd=local)
    else:
        url = f"https://raw.githubusercontent.com/RuralScan/method/{commit}/{lock['manifest']}"
        with urlopen(url, timeout=30) as response:
            data = response.read()
    require(
        sha256(data).hexdigest() == lock["sha256"], "Method manifest checksum mismatch"
    )
    manifest = json.loads(data)
    require(
        (manifest["format_version"], manifest["kind"], manifest["structure_version"])
        == (1, "method_definitions", "0.4.0-structure-frozen"),
        "Unsupported method definition format",
    )
    snapshot(destination, METHOD, manifest["source_revision"], ["/data-model/"], local)
    model = destination / "data-model"
    members = {
        model / "spec.md",
        model / "structure/columns.json",
        *(model / "configuration").rglob("*.csv"),
    }
    actual = {
        p.relative_to(destination).as_posix(): sha256(p.read_bytes()).hexdigest()
        for p in members
    }
    require(
        actual == manifest["sha256"], "Method definition inventory or checksum mismatch"
    )
    require(
        json.loads((model / "structure/columns.json").read_bytes())["manifest_version"]
        == manifest["structure_version"],
        "Definition structure version mismatch",
    )
    return model, manifest
