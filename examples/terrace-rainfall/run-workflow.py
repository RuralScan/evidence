"""Replay the terrace example from screening through a pinned historical recipe row."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True
from replay import EXAMPLE, PRODUCER, git, snapshot  # noqa: E402

ROOT = EXAMPLE.parents[1]
WORKFLOWS = ROOT / "workflows"
INTAKE_REVISION = "157a26c2729c05cccf2b1d9374a63e28c97acac6"
INTAKE_PATHS = [
    "/scripts/ingest-effects-staging.py",
    "/src/",
    "/schema/",
    "/pipeline/acquisition_queue.csv",
]


def read(path):
    return json.loads(path.read_bytes())


def execute(label, command):
    print(f"\n{label}", flush=True)
    try:
        subprocess.run(command, cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"{label} failed: {exc}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        required=True,
        type=Path,
        help="New private directory in an existing parent",
    )
    parser.add_argument(
        "--local-pdf", type=Path, help="Existing copy of the pinned WOCAT manual"
    )
    parser.add_argument(
        "--ciat-repo",
        type=Path,
        help="Local Git objects for both pinned CIAT revisions",
    )
    parser.add_argument(
        "--method-repo",
        type=Path,
        help="Local Git objects for the pinned method definitions",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local sources, Git objects and cached uv dependencies",
    )
    args = parser.parse_args()
    if args.offline and not (args.local_pdf and args.ciat_repo and args.method_repo):
        parser.error("--offline requires --local-pdf, --ciat-repo and --method-repo")
    if args.local_pdf and not args.local_pdf.is_file():
        parser.error("--local-pdf must name an existing file")
    for repo in (args.ciat_repo, args.method_repo):
        if repo and not repo.is_dir():
            parser.error(f"Git checkout does not exist: {repo}")

    if args.offline:
        os.environ["GIT_ALLOW_PROTOCOL"] = "file"
    if args.ciat_repo:
        historical = read(EXAMPLE / "reviewed-claims.json")["producer_revision"]
        for commit in (INTAKE_REVISION, historical):
            try:
                git("cat-file", "-e", f"{commit}^{{commit}}", cwd=args.ciat_repo)
            except subprocess.CalledProcessError:
                parser.error(f"--ciat-repo must contain pinned CIAT revision {commit}")

    out = args.out.absolute()
    out.mkdir(mode=0o700)
    # Bytecode and local example outputs should never dirty an input checkout.
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    uv = ["uv", "run"]
    if args.offline:
        uv.append("--offline")
    uv += ["--python", "3.12"]
    locked = [*uv, "--locked", "--script"]

    discovery = WORKFLOWS / "discovery"
    screen = out / "screening"
    execute(
        "Replay the recorded stock search and screening decisions",
        [
            *uv,
            "--no-project",
            "python",
            discovery / "screen.py",
            "stage",
            discovery / "example/plan.json",
            discovery / "example/decisions.json",
            "--out",
            screen,
        ],
    )
    acquisition = WORKFLOWS / "acquisition"
    plan = acquisition / "example/terrace-manual.json"
    candidates = ["--candidates", screen / "candidates.json"]
    bundle = out / "manual"
    acquire = [*locked, acquisition / "run.py"]
    source = [*candidates, "--plan", plan]
    execute(
        "Check source metadata",
        [*acquire, "verify", *candidates, "--id", read(plan)["candidate_id"]],
    )
    pdf = ["--local-file", args.local_pdf.resolve()] if args.local_pdf else []
    execute(
        "Acquire the pinned manual",
        [*acquire, "acquire", *source, *pdf, "--out", bundle],
    )
    execute(
        "Verify acquired bytes and title",
        [*acquire, "check", *source, "--bundle", bundle],
    )

    extraction = WORKFLOWS / "extraction"
    staging = out / "extraction"
    execute(
        "Extract the terrace passage and stage its interpretation",
        [
            *locked,
            extraction / "extract.py",
            "stage",
            *source,
            "--bundle",
            bundle,
            "--worksheet",
            extraction / "example/terrace-rainfall.json",
            "--out",
            staging,
        ],
    )
    with TemporaryDirectory(prefix="terrace-intake-") as temporary:
        intake = Path(temporary) / "ciat"
        snapshot(intake, PRODUCER, INTAKE_REVISION, INTAKE_PATHS, args.ciat_repo)
        handoff = [
            *uv,
            "--no-project",
            "--with",
            "pymupdf==1.27.2.3",
            "python",
            extraction / "handoff.py",
            "--ciat",
            intake,
            "--staging",
            staging / "staging.json",
            "--corpus-dir",
            bundle / "cache",
            "--allow-structural",
        ]
        execute(
            "Check the proposal against pinned CIAT content gates",
            [*handoff, "--validate-only"],
        )
        execute(
            "Check the historical evidence record and compare changes",
            [*handoff, "--check-existing"],
        )

    row = out / "published-row.json"
    compiler = [*locked, EXAMPLE / "replay.py", "--row-output", row]
    if args.method_repo:
        compiler += ["--method-repo", args.method_repo.resolve()]
    if args.ciat_repo:
        compiler += ["--producer-repo", args.ciat_repo.resolve()]
    execute("Independently rebuild the historically published row", compiler)

    (protocol,) = read(screen / "protocols.json")
    (unit,) = read(staging / "staging.json")
    receipt = read(bundle / "receipt.json")
    published = read(row)
    report = {
        "screening": {
            key: protocol[key] for key in ("n_retrieved", "n_screened", "n_included")
        },
        "source_id": receipt["source_id"],
        "source_sha256": receipt["artifact"]["sha256"],
        "staged_proposal": {
            "evidence_id": unit["evidence_id"],
            "pdf_page": unit["page"],
            "ruleset": unit["ruleset_version"],
        },
        "content_checks": {
            "intake_revision": INTAKE_REVISION,
            "proposal_validated": True,
            "archived_record_checked": True,
        },
        "historical_recipe": {
            "mapping_id": published["mapping_id"],
            "sha256": hashlib.sha256(row.read_bytes()).hexdigest(),
            "producer_revision": read(EXAMPLE / "reviewed-claims.json")[
                "producer_revision"
            ],
        },
    }
    # A failed run retains its private diagnostic files; only a complete run has this receipt.
    pending = out / ".summary.tmp"
    pending.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    pending.rename(out / "summary.json")
    print(f"\nComplete. See {out / 'summary.json'}. Live review continues in CIAT.")


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        sys.exit(f"Replay stopped: {exc}")
