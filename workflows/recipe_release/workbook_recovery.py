"""Prepare verified recovery inputs for the normal six-practice workbook builder."""

import json
import os
from pathlib import Path
import subprocess
import sys

from git_snapshot import git, require, revision, snapshot
from review_preview.preview import (
    ENGINE,
    EV,
    HISTORY,
    LOG,
    REPO,
    load_records,
    read_copy,
)


def recover(work, source, repo, earlier, target):
    """Install only recovered record blobs proven to belong to the selected pin."""
    earlier = revision(earlier)
    ancestors = (
        git("--no-replace-objects", "rev-list", "--first-parent", target, cwd=repo)
        .decode()
        .splitlines()
    )
    require(earlier in ancestors[1:], "Select a strictly earlier first-parent commit")
    previous = work / "previous"
    records = (EV, LOG, HISTORY)
    snapshot(previous, REPO, earlier, ["/" + s for s in records], repo)
    load_records(previous, repo, earlier)
    pinned = load_records(source, repo, target)
    engine = work / "review-engine"
    snapshot(engine, REPO, ENGINE, ["/src/"], repo)
    home = work / "private-home"
    home.mkdir(mode=0o700)
    recovered = work / "recovered"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(Path(__file__).with_name("recovery_worker.py")),
            str(engine / "src"),
            str(previous),
            str(source),
            str(recovered),
        ],
        cwd=work,
        env={**os.environ, "HOME": str(home), "USERPROFILE": str(home)},
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    )
    for name in records:
        blob = read_copy(recovered, name)
        require(
            blob == pinned[name],
            f"Recovered record differs from release input: {name}",
        )
        if blob is not None:
            (source / name).write_bytes(blob)

    # The public reader links each record to its exact line in the immutable
    # producer JSON. Regenerate that file from the recovered CSV before checking it.
    sys.path.insert(0, str(source / "src"))
    from nbs_ruralscan.schema_tools.generate import refresh_review_state

    typed = (source / EV).with_suffix(".json")
    typed.unlink()
    refresh_review_state(source / "schema")
    return {
        **json.loads(result.stdout),
        "earlier_revision": earlier,
        "review_engine_revision": ENGINE,
    }, typed.read_bytes()
