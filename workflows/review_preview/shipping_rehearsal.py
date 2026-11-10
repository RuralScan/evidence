"""Exercise the pinned submission workflow with isolated, local Git repositories."""

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

from preview import read_copy, require
from recovery_fault import RECORDS, SAVED, interrupt_replay


def _install(root, records):
    for name, body in records.items():
        path = root / name
        if body is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)


def rehearse_shipping(
    work: Path, earlier: dict, target: dict, pending: dict, expected: dict
):
    """Fail, advance local main, retry, and compare remote Git blobs to clean replay."""
    from nbs_ruralscan.schema_tools import submit_review as submit

    names = set(RECORDS)
    require(
        all(set(records) == names for records in (earlier, target, expected)),
        "Rehearsal requires three canonical record paths",
    )
    require(
        set(pending) == set(SAVED),
        "Rehearsal requires the saved input pair",
    )
    work = Path(work).resolve()
    work.mkdir(mode=0o700, exist_ok=True)
    require(not any(work.iterdir()), "Shipping rehearsal requires an empty workspace")
    home, empty, origin, reviewer = (
        work / n for n in ("home", "empty", "origin", "reviewer")
    )
    home.mkdir()
    empty.mkdir()
    origin.mkdir()
    env = {
        key: os.environ[key]
        for key in ("PATH", "SystemRoot", "WINDIR")
        if key in os.environ
    }
    env.update(
        HOME=str(home),
        USERPROFILE=str(home),
        TMPDIR=str(work),
        TEMP=str(work),
        TMP=str(work),
        GIT_CONFIG_GLOBAL=str(home / ".gitconfig"),
        GIT_CONFIG_NOSYSTEM="1",
        GIT_ATTR_NOSYSTEM="1",
        GIT_TEMPLATE_DIR=str(empty),
        GIT_ALLOW_PROTOCOL="file",
        GIT_TERMINAL_PROMPT="0",
    )
    real_run = subprocess.run

    def git(cwd, *args):
        result = real_run(["git", *args], cwd=cwd, capture_output=True)
        require(result.returncode == 0, f"Local rehearsal git {args[0]} failed")
        return result.stdout

    def remember_refs():
        return git(origin, "for-each-ref", "--format=%(refname) %(objectname)")

    def check_copy(root, records):
        require(
            all(read_copy(root, name) == data for name, data in records.items()),
            "Rehearsal record copy differs",
        )

    checkouts, pr_heads = [], []
    interrupted = False
    gate = "Simulated rehearsal gate failure"

    def dispatch(args, **kwargs):
        nonlocal interrupted
        checkout = Path(kwargs["cwd"]).resolve()
        require(checkout.is_relative_to(work), "Submission left rehearsal workspace")
        if args[0] == "git":
            return real_run(args, **kwargs)
        if args == [sys.executable, "-m", "nbs_ruralscan.schema_tools.submit_review"]:
            checkouts.append(checkout)
            check_copy(checkout, pending)
            if len(checkouts) == 1:
                require(
                    git(checkout, "rev-parse", "HEAD") == old_head,
                    "Wrong first revision",
                )
                interrupted = interrupt_replay(checkout)
                return subprocess.CompletedProcess(args, 1, "", gate)
            require(
                len(checkouts) == 2 and git(checkout, "rev-parse", "HEAD") == new_head,
                "Retry used the wrong revision",
            )
            submit.replay(checkout)
            check_copy(checkout, expected)
        elif args[:3] == ["gh", "pr", "create"]:
            pr_heads.append(args[args.index("--head") + 1])
        else:
            require(
                args == ["gh", "auth", "status"], "Unexpected submission subprocess"
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    def ship():
        with patch.object(subprocess, "run", dispatch), redirect_stdout(io.StringIO()):
            return submit.ship("rehearsal", root=reviewer)

    with (
        patch.dict(os.environ, env, clear=True),
        patch.object(tempfile, "tempdir", str(work)),
    ):
        for key, value in (
            ("user.name", "Rehearsal"),
            ("user.email", "rehearsal@invalid"),
            ("core.hooksPath", str(empty)),
            ("core.autocrlf", "false"),
        ):
            git(work, "config", "--global", key, value)
        git(origin, "init", "-b", "main")
        (origin / ".gitignore").write_text(
            "/.cache/\n/pipeline/review/\n", encoding="ascii"
        )
        _install(origin, earlier)
        git(origin, "add", "-A")
        git(origin, "commit", "-m", "Earlier records")
        old_head = git(origin, "rev-parse", "HEAD")
        git(work, "clone", "--no-local", str(origin), str(reviewer))
        (reviewer / ".cache/corpus").mkdir(parents=True)
        _install(reviewer, pending)
        before = remember_refs()
        try:
            ship()
        except RuntimeError as exc:
            if str(exc) != gate:
                raise
        else:
            raise ValueError("Expected the simulated submission failure")
        lock = reviewer / ".cache/review-submit.lock"
        require(
            len(checkouts) == 1 and checkouts[0].is_dir() and not lock.exists(),
            "Failed submission did not retain its checkout and release its lock",
        )
        require(
            before == remember_refs() and not pr_heads,
            "Failed submission published changes",
        )
        check_copy(checkouts[0], {**earlier, **pending})
        check_copy(reviewer, {**earlier, **pending})

        _install(origin, target)
        git(origin, "add", "-A")
        git(origin, "commit", "--allow-empty", "-m", "Later records")
        new_head = git(origin, "rev-parse", "HEAD")
        before_retry = remember_refs()
        require(
            ship() == 0 and len(checkouts) == 2 and not checkouts[1].exists(),
            "Retry failed to finish and clean up",
        )
        require(
            not lock.exists() and git(origin, "rev-parse", "main") == new_head,
            "Retry changed main or left the submission locked",
        )
        check_copy(reviewer, {**earlier, **pending})
        require(
            git(reviewer, "rev-parse", "HEAD") == old_head,
            "Shipping moved the reviewer checkout",
        )
        changed = {name for name in names if target[name] != expected[name]}
        require(
            len(pr_heads) == int(bool(changed)), "Unexpected retry pull-request count"
        )
        revision = "main"
        if changed:
            revision = pr_heads[0]
            require(
                git(origin, "rev-parse", revision + "^") == new_head,
                "Retry commit is not based on the later target",
            )
            paths = (
                git(origin, "diff", "--name-only", "main", revision)
                .decode()
                .splitlines()
            )
            require(set(paths) == changed, "Unexpected paths in retry commit")
        else:
            require(remember_refs() == before_retry, "No-op retry published a ref")
        for name, data in expected.items():
            listed = git(origin, "ls-tree", "--name-only", revision, "--", name)
            body = git(origin, "show", f"{revision}:{name}") if listed else None
            require(body == data, "Committed records differ from clean replay")

    return {
        "record_install_interrupted": interrupted,
        "failed_checkout_retained": True,
        "failed_submission_preserved_remote_refs": True,
        "submission_lock_released": True,
        "pending_pair_preserved": True,
        "retry_based_on_later_main": True,
        "retry_branch_pushed_locally": bool(changed),
        "retry_changed_records": len(changed),
        "retry_matches_clean_replay": True,
    }
