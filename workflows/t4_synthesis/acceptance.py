"""Bind scientific acceptance to an original, authenticated reviewer issue receipt."""

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "submissions"))
import intake
from .core import (
    JOURNAL,
    PROPOSALS,
    digest,
    encoded,
    entries,
    git,
    require,
    proposal_digest,
    validate,
    ID,
)

HEADER = "RuralScan T4 scientific acceptance v1"


def fetch(number):
    issue = intake.gh(f"repos/{intake.INBOX}/issues/{number}")
    actor = intake.original(issue)
    require(
        "pull_request" not in issue and issue.get("user", {}).get("type") == "User",
        "Scientific decision requires a human issue receipt",
    )
    require(intake.reviewer_eligible(issue), "Scientific reviewer is not eligible")
    match = re.fullmatch(
        re.escape(HEADER) + r"\s*```json\s*(\{.*\})\s*```\s*", issue["body"], re.S
    )
    require(match, "Invalid scientific decision receipt")
    entry = json.loads(match[1])
    require(
        set(entry)
        == {
            "proposal_id",
            "proposal_sha256",
            "proposal_revision",
            "decision",
            "reason",
        },
        "Unexpected decision fields",
    )
    require(
        entry["decision"] in {"accept", "hold"} and entry["reason"].strip(),
        "Explicit scientific decision and reason required",
    )
    require(
        ID.fullmatch(entry["proposal_id"])
        and re.fullmatch(r"[a-f0-9]{64}", entry["proposal_sha256"]),
        "Invalid proposal pin",
    )
    require(
        re.fullmatch(r"[a-f0-9]{40}", entry["proposal_revision"]),
        "Full proposal Git revision required",
    )
    return {
        **entry,
        "receipt": number,
        "actor": actor,
        "created_at": issue["created_at"],
        "body_sha256": digest(issue["body"].encode()),
    }


def pinned(root, event):
    folder = root / PROPOSALS / event["proposal_id"]
    require(
        proposal_digest(folder) == event["proposal_sha256"],
        "Receipt names different proposal bytes",
    )
    for name in ("proposal.json", "rows.csv", "inputs.json", "skill.md"):
        relative = f"{PROPOSALS}/{event['proposal_id']}/{name}"
        require(
            (folder / name).read_bytes()
            == git(root, "show", f"{event['proposal_revision']}:{relative}"),
            "Receipt does not identify the committed proposal",
        )
    proposal, _ = validate(folder)
    require(
        proposal["id"] == event["proposal_id"], "Receipt names a different proposal ID"
    )


def record(root, number):
    event = fetch(number)
    pinned(root, event)
    old = entries(root)
    if any(e == event for e in old):
        return False
    require(
        not any(e["receipt"] == number for e in old), "Receipt already used differently"
    )
    prior = [e for e in old if e["proposal_id"] == event["proposal_id"]]
    require(
        (not prior and event["decision"] in {"accept", "hold"})
        or (
            prior and prior[-1]["decision"] == "accept" and event["decision"] == "hold"
        ),
        "Accept once; use a new proposal after a hold",
    )
    path = root / JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(encoded(event))
    return True


def verify(root, base=None):
    current = (root / JOURNAL).read_bytes() if (root / JOURNAL).exists() else b""
    previous = b""
    if base:
        names = (
            git(root, "ls-tree", "-r", "--name-only", base, "--", "suitability")
            .decode()
            .splitlines()
        )
        for name in names:
            old = git(root, "show", f"{base}:{name}")
            path = root / name
            require(path.is_file(), f"Scientific history removed: {name}")
            if name == JOURNAL:
                previous = old
                require(
                    current.startswith(old), "Scientific acceptance history rewritten"
                )
            else:
                require(
                    path.read_bytes() == old,
                    f"Scientific proposal rewritten: {name}; create a new proposal",
                )
    accepted = {
        e["receipt"] for e in (json.loads(line) for line in previous.splitlines())
    }
    receipts, states = set(), {}
    for event in entries(root):
        require(event["receipt"] not in receipts, "Duplicate scientific receipt")
        receipts.add(event["receipt"])
        state = states.get(event["proposal_id"])
        require(
            (state is None and event["decision"] in {"accept", "hold"})
            or (state == "accept" and event["decision"] == "hold"),
            "Invalid scientific decision order",
        )
        states[event["proposal_id"]] = event["decision"]
        pinned(root, event)
        if event["receipt"] not in accepted:
            require(
                event == fetch(event["receipt"]),
                "Scientific receipt differs from authenticated original",
            )
