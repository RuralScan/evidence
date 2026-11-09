"""Materialize an immutable, sparse Git checkout without changing a working copy."""

import os
import re
import subprocess


def require(ok, message):
    if not ok:
        raise ValueError(message)


def revision(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
        "Expected a full Git commit",
    )
    return value


def git(*args, cwd=None, stdin=None):
    env = os.environ.copy()
    # CI jobs and Git hooks can export a working tree or index. Each Git call
    # must operate on the explicit checkout, including when launched from CIAT.
    for key in (
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        input=stdin,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout


def snapshot(destination, repository, commit, patterns, local):
    """Check out only the required paths in a private temporary directory."""
    revision(commit)
    if local:
        git(
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(local.resolve()),
            str(destination),
        )
    else:
        git("init", "--quiet", str(destination))
        git("remote", "add", "origin", repository, cwd=destination)
        git("config", "remote.origin.promisor", "true", cwd=destination)
        git("config", "remote.origin.partialclonefilter", "blob:none", cwd=destination)
        git(
            "fetch",
            "--quiet",
            "--depth=1",
            "--filter=blob:none",
            "origin",
            commit,
            cwd=destination,
        )
    git(
        "sparse-checkout",
        "set",
        "--no-cone",
        "--stdin",
        cwd=destination,
        stdin=("\n".join(patterns) + "\n").encode(),
    )
    git("checkout", "--quiet", "--detach", commit, cwd=destination)
    require(
        git("rev-parse", "HEAD", cwd=destination).decode().strip() == commit,
        "Wrong checkout revision",
    )
