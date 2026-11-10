"""Rehearse rejecting and correcting an unsupported terrace suitability limit."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
EXTRACT = ROOT / "workflows/extraction"
REJECTION = "Observed-use excerpt cannot establish a source-defined limit"


def read_json(path):
    return json.loads(path.read_bytes())


def worksheet_for_limit(worksheet, excerpt):
    """Recast the observed values as limits and retain the source sentence for checking."""
    invalid = deepcopy(worksheet)
    draft = next(
        row["draft"] for row in invalid["inventory"] if row["disposition"] == "extract"
    )
    observed = draft["context"]["reported_values"]
    draft["relationship"].update(
        abs_min=observed["low"], abs_max=observed["high"], unit=observed["unit"]
    )
    draft["context"]["source_check"] = {"parameters": excerpt}
    return invalid


def correct_worksheet(invalid):
    """Remove the unsupported limits and retain the range in its observed-use role."""
    fixed = deepcopy(invalid)
    draft = next(
        row["draft"] for row in fixed["inventory"] if row["disposition"] == "extract"
    )
    for key in ("abs_min", "abs_max", "unit"):
        del draft["relationship"][key]
    del draft["context"]["source_check"]
    return fixed


def run(run_dir, work, offline):
    """Use the caller's verified terrace replay, writing exercises into a new claim directory."""
    run_dir = Path(run_dir).resolve(strict=True)
    lesson = Path(work).resolve(strict=True) / "claim"
    if lesson.is_relative_to(run_dir):
        raise ValueError(
            "Choose a challenge directory outside the original terrace run"
        )
    lesson.mkdir(mode=0o700)
    worksheet = read_json(EXTRACT / "example/terrace-rainfall.json")
    reference = run_dir / "extraction"
    excerpt = read_json(reference / "inventory.json")["source_purpose"]["quote"]
    invalid = worksheet_for_limit(worksheet, excerpt)
    command = ["uv", "run"]
    if offline:
        command.append("--offline")
    command.extend(
        [
            "--python",
            "3.12",
            "--locked",
            "--script",
            str(EXTRACT / "extract.py"),
            "stage",
            "--candidates",
            str(run_dir / "screening/candidates.json"),
            "--plan",
            str(ROOT / "workflows/acquisition/example/terrace-manual.json"),
            "--bundle",
            str(run_dir / "manual"),
        ]
    )

    def stage(spec, name):
        path = lesson / f"{name}-worksheet.json"
        path.write_text(
            json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return subprocess.run(
            [*command, "--worksheet", str(path), "--out", str(lesson / name)],
            cwd=lesson,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
        )

    rejected = stage(invalid, "invalid")
    if (
        rejected.returncode != 1
        or f"Extraction stopped: {REJECTION}" not in rejected.stderr.splitlines()
        or (lesson / "invalid").exists()
    ):
        raise ValueError("Expected the observed-use gate to stop staging before output")

    corrected = stage(correct_worksheet(invalid), "corrected")
    if corrected.returncode:
        raise RuntimeError(
            f"Could not stage the corrected worksheet: {corrected.stderr.strip()}"
        )
    for name in ("staging.json", "inventory.json"):
        if (lesson / "corrected" / name).read_bytes() != (
            reference / name
        ).read_bytes():
            raise ValueError(f"Corrected {name} differs from the verified terrace run")
    (unit,) = read_json(lesson / "corrected/staging.json")
    if not unit["context"].get("calibration_hold") or unit["relationship"] != {
        "direction": "unclear"
    }:
        raise ValueError("Expected a calibration hold with no scored rainfall limits")
    return {
        "rejection": REJECTION,
        "evidence_id": unit["evidence_id"],
        "pdf_page": unit["page"],
        "ruleset": unit["ruleset_version"],
        "calibration_held": True,
        "staging_byte_identical": True,
        "inventory_byte_identical": True,
    }
