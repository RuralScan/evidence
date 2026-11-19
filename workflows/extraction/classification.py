"""Separate knowledge basis from source presentation without guessing historical science."""

import csv
import io
import json
from pathlib import Path

CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "rulesets/evidence-classification.json").read_text())
FIELDS = tuple(CONTRACT["fields"])


def normalize(row):
    """Add only deterministic metadata. Preserve every original key/value."""
    out = dict(row)
    inferred = CONTRACT["legacy_mapping"].get(row.get("claim_basis"), {})
    for key in FIELDS:
        if key not in out:
            out[key] = inferred.get(key, "unknown")
    return out


def validate(row):
    for key in FIELDS:
        if row.get(key) not in CONTRACT["fields"][key]["values"]:
            raise ValueError(f"Invalid {key}: {row.get(key)!r}")


def new_claim(row):
    """Current proposals must never obtain credibility from format-only legacy tags."""
    validate(row)
    if row["knowledge_basis"] == "unknown":
        raise ValueError("Unknown knowledge basis: retain proposal in staging for source review")
    if row.get("claim_basis") != row["knowledge_basis"]:
        raise ValueError("claim_basis must match knowledge_basis for new or reclassified claims; format is separate")


def proposal(row, previous=None):
    """Permit unchanged historical classifications on corrections, never invented upgrades."""
    validate(row)
    if previous and all(row.get(k) == normalize(previous).get(k) for k in (*FIELDS, "claim_basis")):
        return
    new_claim(row)


def equivalent(left, right):
    if left is None or right is None:
        return left is right
    return normalize(left) == normalize(right)


def compiler_record(row):
    """Pinned compiler fingerprint excludes additive, non-calibrating metadata."""
    return {k: v for k, v in row.items() if k not in FIELDS}


def migrate_csv(data):
    reader = csv.DictReader(io.StringIO(data.decode(), newline=""), strict=True)
    columns = reader.fieldnames
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("Invalid evidence header")
    records = list(reader)
    seen = set()
    for row in records:
        if None in row or None in row.values() or not row.get("evidence_id") or row["evidence_id"] in seen:
            raise ValueError("Malformed or duplicate evidence row")
        seen.add(row["evidence_id"])
    if any(k in columns for k in FIELDS):
        if not all(k in columns for k in FIELDS):
            raise ValueError("Partial evidence classification migration")
        for row in records:
            validate(row)
        return data
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=columns + list(FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(normalize(row) for row in records)
    return out.getvalue().encode()
