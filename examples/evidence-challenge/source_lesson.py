"""Screen and verify one fictional source in the training directory."""

import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parents[1] / "workflows"
FIXTURE = HERE / "source"


def run(work: Path, offline: bool) -> dict:
    lesson = work / "source-lesson"
    lesson.mkdir(mode=0o700)
    screening = lesson / "screening"
    acquired = lesson / "acquired"
    subprocess.run(
        [
            sys.executable,
            "-B",
            TOOLS / "discovery/screen.py",
            "stage",
            FIXTURE / "plan.json",
            FIXTURE / "decisions.json",
            "--out",
            screening,
        ],
        check=True,
    )
    (candidate,) = json.loads((screening / "candidates.json").read_bytes())
    (decision,) = json.loads((screening / "screening.json").read_bytes())
    (protocol,) = json.loads((screening / "protocols.json").read_bytes())
    counts = [protocol[key] for key in ("n_retrieved", "n_screened", "n_included")]
    if (
        counts != [1, 1, 1]
        or decision["disposition"] != "include"
        or candidate["candidate_id"] != "training_riparian_field_sheet"
        or candidate.get("doi")
        or candidate["url"]
        != "https://example.invalid/training/riparian-field-sheet.md"
    ):
        raise ValueError("Expected one new DOI-less training candidate")

    tool = ["uv", "run"]
    if offline:
        tool.append("--offline")
    tool.extend(
        ["--python", "3.12", "--locked", "--script", TOOLS / "acquisition/run.py"]
    )
    args = [
        "--candidates",
        screening / "candidates.json",
        "--plan",
        FIXTURE / "acquisition.json",
    ]
    subprocess.run(
        [
            *tool,
            "acquire",
            *args,
            "--local-file",
            FIXTURE / "field-sheet.md",
            "--out",
            acquired,
        ],
        check=True,
    )
    subprocess.run([*tool, "check", *args, "--bundle", acquired], check=True)
    receipt = json.loads((acquired / "receipt.json").read_bytes())
    artifact = receipt["artifact"]
    if (
        receipt["source_id"] != candidate["candidate_id"]
        or not receipt["document"]["verified"]
        or artifact["route"] != "local_hash_replay"
        or artifact["http_status"] is not None
    ):
        raise ValueError("Expected an identity-checked replay of the bundled edition")
    return {
        "source_id": receipt["source_id"],
        "retrieved": counts[0],
        "screened": counts[1],
        "included": counts[2],
        "disposition": decision["disposition"],
        "artifact_sha256": artifact["sha256"],
        "title_verified": receipt["document"]["verified"],
        "route": artifact["route"],
    }
