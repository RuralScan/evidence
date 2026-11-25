"""Prepare, validate, stage, accept and package AI-authored T4 mappings."""

import argparse
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

sys.path[:0] = [
    str(Path(__file__).resolve().parents[1]),
    str(Path(__file__).resolve().parents[1] / "submissions"),
]
from t4_synthesis import core, acceptance, package


def prepare(root, queue, producer, args):
    core.require(
        core.ID.fullmatch(args.id) and args.practice in queue["recipes"],
        "Invalid proposal identity/practice",
    )
    packet = core.inputs(root, producer, args.practice, queue["registers"])
    core.require(
        args.family in core.families(packet), "Select a current suitability family"
    )
    core.require(not args.out.exists(), "Select a new proposal directory")
    args.out.mkdir(parents=True)
    (args.out / "inputs.json").write_bytes(core.encoded(packet))
    skill = root / ".agents/skills/source-command-t4-synthesise/SKILL.md"
    shutil.copyfile(skill, args.out / "skill.md")
    core.write_rows(args.out / "rows.csv", [])
    p = dict(
        format=core.FORMAT,
        id=args.id,
        practice=args.practice,
        family=args.family,
        action="replace",
        task=args.task,
        comparison="",
        replaces={},
        inputs_sha256=core.digest(packet),
        skill_sha256=core.digest(skill.read_bytes()),
        rows_sha256=core.digest((args.out / "rows.csv").read_bytes()),
        agent={k: "" for k in ("model", "skill_version", "prompt", "settings")},
        reasoning={k: "" for k in core.policy()["reasoning"]},
        candidates=[
            dict(
                evidence_id=r["evidence_id"],
                disposition="pending",
                reason="",
                origin="",
            )
            for r in packet["evidence"]
        ],
    )
    (args.out / "proposal.json").write_bytes(core.encoded(p))
    print(
        "Prepared frozen inputs and unscored worksheet; no mapping or acceptance created."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    for key in ("practice", "family", "id", "task"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ciat-repo", type=Path, required=True)
    for name in ("validate", "stage"):
        p = sub.add_parser(name)
        p.add_argument("proposal", type=Path)
        p.add_argument("--ciat-repo", type=Path, required=True)
    p = sub.add_parser("decision")
    p.add_argument("receipt", type=int)
    p.add_argument("--ciat-repo", type=Path, required=True)
    p = sub.add_parser("package")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--ciat-repo", type=Path, required=True)
    args = parser.parse_args()
    root = core.ROOT
    from t4_synthesis.contract_pin import verify
    from submissions import configuration
    from submissions.queue_view import compile_candidate, publish_files

    verify(root)
    with TemporaryDirectory() as temp:
        producer = Path(temp) / "producer"
        configuration.engine(args.ciat_repo, producer, root=root)
        sys.path.insert(0, str(producer / "src"))
        queue, _ = compile_candidate(producer, root)
        if args.command == "prepare":
            prepare(root, queue, producer, args)
        elif args.command in {"validate", "stage"}:
            p = json.loads((args.proposal / "proposal.json").read_bytes())
            core.validate(
                args.proposal,
                core.inputs(root, producer, p["practice"], queue["registers"]),
                queue["recipes"][p["practice"]][core.TABLE],
            )
            if args.command == "stage":
                dest = root / core.PROPOSALS / p["id"]
                core.require(
                    not dest.exists(), "Proposal IDs are immutable; use a new ID"
                )
                shutil.copytree(args.proposal, dest)
            print(
                "Validated proposal",
                core.proposal_digest(args.proposal),
                "— not scientific acceptance",
            )
        elif args.command == "decision":
            event = acceptance.fetch(args.receipt)
            folder = root / core.PROPOSALS / event["proposal_id"]
            p = json.loads((folder / "proposal.json").read_bytes())
            if event["decision"] == "accept" and event not in core.entries(root):
                core.validate(
                    folder,
                    core.inputs(root, producer, p["practice"], queue["registers"]),
                    queue["recipes"][p["practice"]][core.TABLE],
                )
            from submissions.registers import LIVE
            from submissions.recipe_rows import CANDIDATE

            previous = {
                name: (root / name).read_bytes() if (root / name).exists() else None
                for name in (core.JOURNAL, LIVE, CANDIDATE)
            }
            try:
                acceptance.record(root, args.receipt)
                publish_files(producer, root)
            except Exception:
                for name, raw in previous.items():
                    path = root / name
                    if raw is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(raw)
                raise
            print(
                "Recorded decision and queue diff. Commit through a protected PR; do not merge automatically."
            )
        else:
            acceptance.verify(root)
            print("Trusted T4 manifest SHA-256:", package.build(queue, args.out))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        sys.exit(f"T4 synthesis workflow: {error}")
