"""Prepare AI synthesis inputs, validate proposals, record reviewed decisions and package outputs."""

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
from synthesis.core import (
    ROOT,
    PROPOSALS,
    FORMAT,
    ID,
    TABLES,
    inputs,
    policy,
    validate,
    proposal_digest,
    digest,
    encoded,
    require,
    write_rows,
    entries,
    JOURNAL,
    group_definition,
    prior_rows,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--practice", required=True)
    prepare.add_argument("--table", required=True, choices=TABLES)
    prepare.add_argument(
        "--group",
        help="Optional pinned evidence group; summary is excluded from runtime recipes",
    )
    prepare.add_argument("--id", required=True)
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--out", required=True, type=Path)
    prepare.add_argument("--ciat-repo", required=True, type=Path)
    for name in ("validate", "stage"):
        p = sub.add_parser(name)
        p.add_argument("proposal", type=Path)
        p.add_argument("--ciat-repo", required=True, type=Path)
    decision = sub.add_parser("decision")
    decision.add_argument("receipt", type=int)
    decision.add_argument("--ciat-repo", required=True, type=Path)
    package = sub.add_parser("package")
    package.add_argument("--out", type=Path, required=True)
    package.add_argument("--ciat-repo", required=True, type=Path)
    args = parser.parse_args()
    from synthesis.contract_pin import verify as verify_contract

    verify_contract(ROOT)
    import configuration
    from queue_view import compile_candidate, publish_files

    with TemporaryDirectory() as tmp:
        producer = Path(tmp) / "producer"
        configuration.engine(args.ciat_repo, producer)
        sys.path.insert(0, str(producer / "src"))
        queue, _ = compile_candidate(producer, ROOT)
        if args.command == "prepare":
            require(
                ID.fullmatch(args.id) and args.practice in queue["recipes"],
                "Invalid proposal identity or practice",
            )
            require(not args.out.exists(), "Select a new proposal directory")
            packet = inputs(ROOT, producer, args.practice, queue["registers"])
            if args.group:
                group_definition(
                    {"practice": args.practice, "evidence_group_id": args.group}, packet
                )
            args.out.mkdir(parents=True)
            (args.out / "inputs.json").write_bytes(encoded(packet))
            skill = ROOT / ".agents/skills/source-command-t3t6-synthesise/SKILL.md"
            shutil.copyfile(skill, args.out / "skill.md")
            write_rows(args.out / "rows.csv", args.table, [])
            proposal = {
                "format": FORMAT,
                "id": args.id,
                "practice": args.practice,
                "table": args.table,
                "task": args.task,
                "action": "replace",
                "inputs_sha256": digest(packet),
                "skill_sha256": digest(skill.read_bytes()),
                "rows_sha256": digest((args.out / "rows.csv").read_bytes()),
                "agent": {
                    k: "" for k in ("model", "skill_version", "prompt", "settings")
                },
                "reasoning": {k: "" for k in policy()["reasoning"]},
                "comparison": "",
                "replaces": {},
                "candidates": [
                    {
                        "evidence_id": r["evidence_id"],
                        "disposition": "pending",
                        "reason": "",
                        "origin": "",
                    }
                    for r in packet["evidence"]
                ],
            }
            if args.group:
                proposal["evidence_group_id"] = args.group
            (args.out / "proposal.json").write_bytes(encoded(proposal))
            print(
                "Prepared inputs and unscored worksheet. AI must author judgments and candidate dispositions."
            )
        elif args.command in {"validate", "stage"}:
            raw = json.loads((args.proposal / "proposal.json").read_bytes())
            packet = inputs(ROOT, producer, raw["practice"], queue["registers"])
            prior = prior_rows(queue, raw)
            p, _ = validate(args.proposal, packet, prior)
            if args.command == "stage":
                destination = ROOT / PROPOSALS / p["id"]
                require(
                    not destination.exists(), "Proposal IDs are immutable; use a new ID"
                )
                shutil.copytree(args.proposal, destination)
            print(
                "Validated proposal",
                proposal_digest(args.proposal),
                "— not scientific acceptance",
            )
        elif args.command == "decision":
            from synthesis.acceptance import record, fetch

            event = fetch(args.receipt)
            folder = ROOT / PROPOSALS / event["proposal_id"]
            raw = json.loads((folder / "proposal.json").read_bytes())
            if event["decision"] == "accept" and event not in entries(ROOT):
                validate(
                    folder,
                    inputs(ROOT, producer, raw["practice"], queue["registers"]),
                    prior_rows(queue, raw),
                )
            from registers import LIVE
            from recipe_rows import CANDIDATE

            previous = {
                name: (ROOT / name).read_bytes() if (ROOT / name).exists() else None
                for name in (JOURNAL, LIVE, CANDIDATE)
            }
            try:
                record(ROOT, args.receipt)
                publish_files(producer, ROOT)
            except Exception:
                for name, data in previous.items():
                    path = ROOT / name
                    if data is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(data)
                raise
            print(
                "Recorded scientific decision; review and commit the generated diff in a protected PR."
            )
        else:
            from synthesis.package import build
            from synthesis.acceptance import verify

            verify(ROOT)
            print("Trusted manifest SHA-256:", build(queue, args.out))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        sys.exit(f"Synthesis workflow: {error}")
