# /// script
# requires-python = ">=3.12"
# dependencies = ["requests==2.34.2"]
# ///

"""Practice source intake, evidence correction, review and an independent candidate rebuild."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "workflows"))
from git_snapshot import require, snapshot  # noqa: E402
from review_preview.preview import ENGINE, REPO  # noqa: E402
from run_record.record import digest, read_json, verify  # noqa: E402
import claim_lesson  # noqa: E402
import source_lesson  # noqa: E402

TERRACE = HERE.parent / "terrace-rainfall"


def check_terrace(run_dir, checksum):
    path = verify(run_dir, checksum)
    description = read_json(path)["run"]
    template = read_json(TERRACE / "run-description.json")
    require(
        all(description.get(k) == v for k, v in template.items()),
        "Expected a completed terrace rainfall run",
    )
    mapping = read_json(TERRACE / "reviewed-claims.json")
    row_digest = digest(run_dir / "published-row.json")
    require(
        row_digest == mapping["expected_row_sha256"],
        "Historical terrace row differs from the reference",
    )
    return {
        "record_sha256": checksum,
        "mapping_id": mapping["mapping_id"],
        "row_sha256": row_digest,
    }


def new_directory(out, run_dir):
    dest = out.parent.resolve(strict=True) / out.name
    require(
        not dest.is_relative_to(run_dir.resolve()),
        "Choose an output outside the terrace run",
    )
    require(
        not any(
            p.name.casefold() == ".git" or (p / ".git").exists()
            for p in (dest, *dest.parents)
        ),
        "Choose a private output directory outside Git",
    )
    dest.mkdir(mode=0o700)
    return dest


def review(ciat_repo, answers):
    with TemporaryDirectory(prefix="ruralscan-challenge-") as tmp:
        engine = Path(tmp) / "engine"
        snapshot(engine, REPO, ENGINE, ["/src/"], ciat_repo)
        command = [
            sys.executable,
            "-IB",
            str(HERE / "review_lesson.py"),
            str(engine / "src"),
        ]
        if answers is not None:
            command.append(str(answers.resolve(strict=True)))
        result = subprocess.run(command, cwd=tmp, stdout=subprocess.PIPE, text=True)
        require(
            result.returncode == 0,
            "Review exercise failed. See the review feedback above.",
        )
    return {
        "engine_revision": ENGINE,
        "answer_sheet": "operator copy" if answers else "worked example",
        **json.loads(result.stdout),
    }


def rebuild(offline, ciat_repo, method_repo):
    command = ["uv", "run"]
    if offline:
        command.append("--offline")
    command.extend(
        [
            "--python",
            "3.12",
            "--locked",
            "--script",
            str(ROOT / "workflows/recipe_release/check.py"),
            "--check-method",
            "--json",
        ]
    )
    for flag, repo in (("--ciat-repo", ciat_repo), ("--method-repo", method_repo)):
        if repo is not None:
            command.extend([flag, str(repo.resolve())])
    return json.loads(subprocess.check_output(command, cwd=ROOT, text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--terrace-run", required=True, type=Path, help="Private completed example run"
    )
    parser.add_argument(
        "--sha256", required=True, help="Saved digest of its run-record.json"
    )
    parser.add_argument(
        "--out", required=True, type=Path, help="New private folder for exercise files"
    )
    parser.add_argument(
        "--ciat-repo",
        type=Path,
        help="Local clone with pinned review and producer commits",
    )
    parser.add_argument(
        "--method-repo", type=Path, help="Local clone with pinned definition commits"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use local Git objects and cached environments",
    )
    parser.add_argument(
        "--review-answers", type=Path, help="Private completed exercise answer sheet"
    )
    args = parser.parse_args()
    if args.offline:
        if not (args.ciat_repo and args.method_repo):
            parser.error("--offline requires --ciat-repo and --method-repo")
        os.environ["GIT_ALLOW_PROTOCOL"] = "file"
        os.environ["UV_OFFLINE"] = "true"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    run_dir = args.terrace_run.resolve(strict=True)
    historical = check_terrace(run_dir, args.sha256)
    work = new_directory(args.out, run_dir)
    print(
        "Staging a training source and checking the proposed rainfall correction.",
        flush=True,
    )
    source_result = source_lesson.run(work, args.offline)
    claim_result = claim_lesson.run(run_dir, work, args.offline)
    print("Replaying a synthetic review with the pinned CIAT engine.", flush=True)
    review_result = review(args.ciat_repo, args.review_answers)
    print("Rebuilding the candidate from its pinned inputs.", flush=True)
    release = rebuild(args.offline, args.ciat_repo, args.method_repo)
    verify(run_dir, args.sha256)
    receipt = {
        "terrace_reference": historical,
        "training_source": source_result,
        "terrace_correction": claim_result,
        "synthetic_review": review_result,
        "independent_candidate_release": release,
    }
    pending = work / ".result.tmp"
    with pending.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    pending.rename(work / "result.json")
    print(f"Exercise complete. See {work / 'result.json'}.")


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        sys.exit(f"Exercise stopped: {exc}")
