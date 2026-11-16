"""Prepare a protected data PR for an executed workflow step. Default is preview."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import registration as reg
from registers import (
    ROOT,
    SEED,
    LIVE,
    SRC,
    git,
    snapshot,
    require,
    content_digest,
    intake,
    json_bytes,
)


def read(path):
    return json.loads(path.read_bytes())


def operation(args, dest):
    if args.kind == "discovery":
        plan = read(args.plan)
        reg.capture_names(plan)
        loaded = reg.screen.load_run(args.plan)
        decisions = read(args.decisions)
        reg.screen.screen(*loaded, decisions)

        # The private worksheet binds the entire provider capture, including abstracts.
        # Reproduce the screening from public bibliographic fields and retain both pins.
        def select(row, keys):
            return {k: row[k] for k in keys if k in row}

        plan = select(
            plan,
            (
                "nbs_id",
                "family",
                "table",
                "process",
                "run_id",
                "date",
                "purpose",
                "searched_by",
                "screened_by",
                "limits",
                "stop_reason",
                "omissions",
                "captures",
                "inclusion_criteria",
            ),
        )
        captures = []
        for capture in loaded[1]:
            public = select(capture, ("channel", "process", "date", "limits", "query"))
            public["records"] = [
                select(
                    row,
                    (
                        "record_id",
                        "title",
                        "citation",
                        "url",
                        "oa_status",
                        *reg.screen.BIB_FIELDS,
                    ),
                )
                for row in capture["records"]
            ]
            captures.append(public)
        dispositions = (
            "record_id",
            "title",
            "disposition",
            "reason",
            "duplicate_of",
            "reuse_source_id",
            "families",
            "hazards",
            "t6_targets",
            "lineage",
            "referral",
            "parent_source_id",
            "credibility",
            "proposed_benchmark_tier",
            "tier_rationale",
        )
        return dict(
            kind="discovery",
            plan=plan,
            captures=captures,
            original_sha256=decisions["input_sha256"],
            decisions={
                "input_sha256": reg.screen.fingerprint([plan, captures]),
                "records": [select(row, dispositions) for row in decisions["records"]],
            },
            ruleset=reg.screen.RULESET,
            stamp=args.stamp,
        )
    if args.kind == "verification":
        return dict(
            kind=args.kind,
            nbs_id=args.practice,
            table=args.table,
            family=args.family,
            process=args.process,
            date=args.date,
            by=args.operator,
            status=args.status,
            run_id=args.run_id,
            receipts=[
                {
                    "number": n,
                    "body": intake.gh(f"repos/{intake.INBOX}/issues/{n}")["body"],
                }
                for n in sorted(set(args.receipts))
            ],
        )
    plan = reg.acquisition.read_plan(args.plan)
    candidate = reg.acquisition.selected(args.candidates, plan["candidate_id"])
    receipt = reg.acquisition.check(
        args.bundle, plan, candidate, dest / "registers" / SRC
    )
    require(
        receipt["status"] == "acquired",
        "Resolve the acquisition hold before registration",
    )
    if plan["kind"] == "pdf" or args.library_path:
        require(
            args.library_root and args.library_path,
            "Select the synchronized team library and shared path",
        )
        path = Path(args.library_path)
        require(
            "library" in path.parts
            and not path.is_absolute()
            and ".." not in path.parts,
            "Invalid library path",
        )
        shared = args.library_root.joinpath(
            *path.parts[path.parts.index("library") + 1 :]
        ).resolve()
        require(
            shared.is_relative_to(args.library_root.resolve())
            and content_digest(shared.read_bytes()) == receipt["artifact"]["sha256"],
            "Shared library edition differs from acquired copy",
        )
    # Publish bibliographic identity and artifact fingerprints only. Network attempt
    # logs and the acquired files stay in the operator's bundle.
    public = {
        k: receipt[k]
        for k in (
            "format_version",
            "status",
            "candidate_id",
            "candidate_sha256",
            "source_id",
            "kind",
            "plan_sha256",
            "checked_at",
            "canonical_source",
            "metadata",
            "artifact",
            "document",
        )
    }
    return dict(
        kind="source",
        plan=plan,
        candidate=candidate,
        receipt=public,
        assessment=read(args.assessment),
        library_path=args.library_path,
    )


def install(dest, base, op, engine):
    path = dest / reg.RECORDS / (reg.stem(op) + ".json")
    if path.exists():
        require(
            read(path)["operation"] == op, "Same run or source ID has different inputs"
        )
        return False
    if not reg.apply(dest, op, engine, dest):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(reg.screen.encode(dict(base=base, operation=op)), encoding="utf-8")
    return True


def prepare(args):
    remote = (
        git("remote", "get-url", "origin", cwd=ROOT)
        .decode()
        .strip()
        .lower()
        .removesuffix(".git")
    )
    require(
        remote
        in {
            "https://github.com/ruralscan/evidence",
            "git@github.com:ruralscan/evidence",
        },
        "Expected RuralScan/evidence checkout",
    )
    git("fetch", "--quiet", "origin", "main", cwd=ROOT)
    base = git("rev-parse", "origin/main", cwd=ROOT).decode().strip()
    require(
        args.base == base,
        "Stale register base. Inspect changes before preparing a new proposal.",
    )
    with TemporaryDirectory() as folder:
        tmp = Path(folder).resolve()
        dest, engine = tmp / "evidence", tmp / "engine"
        snapshot(dest, "", base, ["/*"], ROOT)
        snapshot(
            engine,
            "",
            SEED,
            [
                "/src/",
                "/schema/",
                "/pipeline/",
                "/docs/review/*.json",
                "!/docs/review/*/",
            ],
            args.ciat_repo,
        )
        sys.path.insert(0, str(engine / "src"))
        op = operation(args, dest)
        if not install(dest, base, op, engine):
            print("Already registered. No change.")
            return
        if op["kind"] == "source":
            from queue_view import build

            for path in (dest / "registers").rglob("*"):
                target = engine / path.relative_to(dest / "registers")
                if path.is_file() and target.is_file():
                    shutil.copyfile(path, target)
            (dest / LIVE).write_bytes(json_bytes(build(engine, dest)))
        git("add", "-A", cwd=dest)
        print(git("diff", "--cached", "--stat", cwd=dest).decode(), flush=True)
        if not args.open_pr:
            return
        require(
            git("merge-base", "HEAD", base, cwd=ROOT)
            == git("rev-parse", "HEAD", cwd=ROOT)
            and not git("status", "--porcelain", cwd=ROOT),
            "Use the merged writer from a clean checkout",
        )
        intake.check_destination()
        name = reg.stem(op)
        branch = f"registers/{base[:12]}-{name}"
        title = f"Register {name}"
        git("commit", "-qm", title, cwd=dest)
        git(
            "remote",
            "set-url",
            "origin",
            "https://github.com/RuralScan/evidence.git",
            cwd=dest,
        )
        if git("ls-remote", "--heads", "origin", "refs/heads/" + branch, cwd=dest):
            git("fetch", "--quiet", "origin", branch, cwd=dest)
            require(
                git("rev-parse", "FETCH_HEAD^{tree}", cwd=dest)
                == git("rev-parse", "HEAD^{tree}", cwd=dest),
                "An existing proposal differs. Inspect its inputs.",
            )
            existing = intake.gh(
                f"repos/{intake.INBOX}/pulls?state=all&head=RuralScan:{branch}&base=main"
            )
            if existing:
                print(existing[0]["html_url"])
                return
        else:
            git("push", "origin", "HEAD:refs/heads/" + branch, cwd=dest)
        body = tmp / "pr.md"
        body.write_text(
            f"Apply the recorded {op['kind']} operation against RuralScan/evidence revision `{base}`.\n"
        )
        subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "-R",
                intake.INBOX,
                "--head",
                branch,
                "--base",
                "main",
                "--title",
                title,
                "--body-file",
                str(body),
            ],
            cwd=dest,
            check=True,
        )


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciat-repo", required=True, type=Path)
    parser.add_argument(
        "--base", required=True, help="Full RuralScan revision examined by the operator"
    )
    parser.add_argument("--open-pr", action="store_true")
    sub = parser.add_subparsers(dest="kind", required=True)
    discovery = sub.add_parser("discovery")
    discovery.add_argument("--plan", type=Path, required=True)
    discovery.add_argument("--decisions", type=Path, required=True)
    discovery.add_argument("--stamp", action="store_true")
    source = sub.add_parser("source")
    for field in ("candidates", "plan", "bundle", "assessment"):
        source.add_argument("--" + field, type=Path, required=True)
    source.add_argument("--library-path", default="")
    source.add_argument("--library-root", type=Path)
    verification = sub.add_parser("verification")
    for field in ("practice", "table", "process", "run-id", "date", "operator"):
        verification.add_argument("--" + field, required=True)
    verification.add_argument(
        "--status", choices=("in_progress", "done"), required=True
    )
    verification.add_argument("--family", default="")
    verification.add_argument("--receipts", nargs="+", type=int, required=True)
    prepare(parser.parse_args())


if __name__ == "__main__":
    try:
        cli()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.exit(f"Registration stopped: {exc}")
