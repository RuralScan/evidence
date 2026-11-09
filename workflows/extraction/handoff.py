"""Check staged units against a private copy of the CIAT intake registers."""

import argparse
import csv
from collections import defaultdict
from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

EV = "schema/registers/EV_evidence_register.csv"
INPUTS = (
    EV,
    "schema/registers/SRC_source_register.csv",
    "pipeline/acquisition_queue.csv",
    "schema/registers/FAM_family_registry.csv",
    "schema/registers/VONT_variable_ontology.csv",
    "schema/registers/BANDS_magnitude_bands.csv",
    "schema/T7_geographic_context.csv",
    "schema/lookups/variable_direction_sense.csv",
    "schema/lookups/m2b_variable_policy.csv",
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def invalid_number(value):
    raise ValueError(f"Non-finite number: {value}")


def finite_float(text):
    value = float(text)
    if not math.isfinite(value):
        invalid_number(text)
    return value


def anchor(unit):
    """Identify exact reuse of a passage for the same source, variable and scope."""
    fields = (
        "source_id",
        "nbs_id",
        "suitability_family_id",
        "variable",
        "use_role",
        "claim_scope",
        "taxon",
        "locator_type",
        "page",
        "locator",
    )
    return tuple(str(unit.get(k) or "") for k in fields)


def overlap(a, b):
    """Distinguish an exact quote from substantial contiguous shared wording."""
    a, b = a.split(), b.split()
    if a == b:
        return "same passage"
    shared = SequenceMatcher(None, a, b, autojunk=False).find_longest_match().size
    shorter = min(len(a), len(b))
    if (shared >= 4 and shared == shorter) or (shared >= 12 and shared * 2 >= shorter):
        return "overlapping passage"
    return None


def scientific_fields(row):
    """Decode stored CSV values to intake types, leaving live review ownership in CIAT."""
    values = {}
    for key, value in row.items():
        if value == "" or key in {"reviewer_ok", "review_state"}:
            continue
        if key in {"context", "relationship"}:
            value = json.loads(value)
        if key in {"page", "justification_page", "selection_justification_page"}:
            value = int(value)
        values[key] = value
    return values


def same_value(left, right):
    """Compare JSON fields, distinguishing booleans from numbers at every depth."""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            same_value(v, right[k]) for k, v in left.items()
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            same_value(a, b) for a, b in zip(left, right)
        )
    return left == right


def changed_fields(historical, unit):
    proposed = {
        k: v
        for k, v in unit.items()
        if v is not None and v != "" and k not in {"reviewer_ok", "review_state"}
    }
    return sorted(
        k
        for k in historical.keys() | proposed.keys()
        if not same_value(historical.get(k), proposed.get(k))
    )


def check_replays(register, units, *, check_existing=False):
    """A renamed duplicate or a changed/omitted scientific field needs reconciliation."""
    with register.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    known = {row["evidence_id"]: row for row in rows}
    anchors = defaultdict(list)
    for row in rows:
        anchors[anchor(row)].append((row["evidence_id"], row["quote"]))
    archived = []
    for unit in units:
        eid = unit["evidence_id"]
        old = known.get(eid)
        if old is None:
            if check_existing:
                raise ValueError(f"{eid}: no stored row for archived identity check")
            neighbours = anchors[anchor(unit)]
            for prior, prior_quote in neighbours:
                reason = overlap(unit["quote"], prior_quote)
                if reason:
                    raise ValueError(
                        f"{eid}: {reason} and scope as {prior}; hold for claim reconciliation in CIAT"
                    )
            neighbours.append((eid, unit["quote"]))
            continue
        historical = scientific_fields(old)
        differences = changed_fields(historical, unit)
        if differences:
            msg = f"{eid}: existing {', '.join(differences)} differs; proposed change held for the CIAT correction process"
            if not check_existing:
                raise ValueError(msg)
            print(msg, flush=True)
        archived.append(historical)
    return archived


GATE_ONLY = """
import json
from pathlib import Path
import sys
from nbs_ruralscan.schema_tools import evidence_intake
staging, root, corpus, *roles = sys.argv[1:]
paths = evidence_intake.EvidenceIntakePaths.from_root(Path(root), corpus=Path(corpus))
problems = evidence_intake.gate(json.loads(Path(staging).read_bytes()), set(roles), paths=paths)
for problem in problems:
    print(problem)
if not problems:
    print("Proposal content gates passed. Append eligibility and human review are separate checks.")
sys.exit(1 if problems else 0)
"""


def check(
    ciat, staging, corpus, flags=(), *, check_existing=False, validate_only=False
):
    if check_existing and validate_only:
        raise ValueError("Choose one check mode")
    ciat = ciat.resolve()
    corpus = corpus.resolve()
    script = ciat / "scripts/ingest-effects-staging.py"
    if not script.is_file() or not corpus.is_dir():
        raise ValueError(
            "Supply a CIAT checkout with evidence intake and an acquired corpus directory"
        )
    payload = staging.read_bytes()
    units = json.loads(
        payload,
        object_pairs_hook=unique_object,
        parse_constant=invalid_number,
        parse_float=finite_float,
    )
    if (
        not isinstance(units, list)
        or not units
        or not all(
            isinstance(unit, dict)
            and isinstance(unit.get("evidence_id"), str)
            and isinstance(unit.get("quote"), str)
            for unit in units
        )
    ):
        raise ValueError(
            "Staging must contain a nonempty list of evidence units with IDs and quotes"
        )
    if any(flag not in {"--allow-structural", "--allow-operational"} for flag in flags):
        raise ValueError("Unknown scope option")
    with TemporaryDirectory(prefix="evidence-intake-") as temp:
        data = Path(temp)
        for relative in INPUTS:
            target = data / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ciat / relative, target)
        input_file = data / "units.json"
        env = {**os.environ, "PYTHONPATH": str(ciat / "src")}
        if validate_only:
            input_file.write_bytes(payload)
            roles = ["nbs_effect", "asset_vulnerability"]
            if "--allow-structural" in flags:
                roles.append("structural_suitability")
            if "--allow-operational" in flags:
                roles.append("operational_risk")
            args = [
                sys.executable,
                "-B",
                "-c",
                GATE_ONLY,
                str(input_file),
                str(data),
                str(corpus),
                *roles,
            ]
            return subprocess.run(args, cwd=data, env=env).returncode
        if check_existing:
            print(
                "Archived identity check: validating stored CIAT scientific fields. This mode does not validate a changed proposal.",
                flush=True,
            )
        archived = check_replays(data / EV, units, check_existing=check_existing)
        if check_existing:
            input_file.write_text(
                json.dumps(archived, allow_nan=False), encoding="utf-8"
            )
        else:
            input_file.write_bytes(payload)
        args = [
            sys.executable,
            "-B",
            str(script),
            str(input_file),
            "--root",
            str(data),
            "--corpus-dir",
            str(corpus),
            "--dry-run",
            *flags,
        ]
        return subprocess.run(args, cwd=data, env=env).returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ciat", type=Path, required=True)
    p.add_argument("--staging", type=Path, required=True)
    p.add_argument("--corpus-dir", type=Path, required=True)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument(
        "--validate-only",
        action="store_true",
        help="Run CIAT content gates against the staged proposal without evaluating append eligibility",
    )
    modes.add_argument(
        "--check-existing",
        action="store_true",
        help="Test stored versions of the proposed evidence IDs",
    )
    p.add_argument("--allow-structural", action="store_true")
    p.add_argument("--allow-operational", action="store_true")
    args = p.parse_args()
    flags = []
    if args.allow_structural:
        flags.append("--allow-structural")
    if args.allow_operational:
        flags.append("--allow-operational")
    try:
        return check(
            args.ciat,
            args.staging,
            args.corpus_dir,
            flags,
            check_existing=args.check_existing,
            validate_only=args.validate_only,
        )
    except (KeyError, OSError, ValueError) as error:
        print(f"Handoff held: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
