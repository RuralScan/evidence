"""Validate a private NbS inclusion assessment; never edit evidence or cast votes."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "rulesets/nbs-inclusion.json"

def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, list) and all(text(item) for item in value)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, f"Duplicate key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def load(data):
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)


def judgment(value, name, statuses):
    require(isinstance(value, dict), f"Missing judgment: {name}")
    require(value.get("status") in statuses, f"Invalid status: {name}")
    require(text(value.get("rationale")), f"Missing rationale: {name}")
    if value["status"] in {"pass", "fail"}:
        require(text(value.get("source_locator")), f"Missing source locator: {name}")


def assess(record, policy):
    require(isinstance(record, dict), "Assessment must be an object")
    require(record.get("ruleset") == policy["id"], "Wrong inclusion ruleset")
    require(text(record.get("source_id")), "Missing source_id")
    require(record.get("nbs_id") in policy["nbs_ids"], "Unknown NbS")
    require(text(record.get("suitability_family_id")), "Missing family")
    require(text(record.get("component_scope")), "Missing component scope")
    require(re.fullmatch(r"[0-9a-f]{64}", record.get("source_sha256", "")) is not None,
            "Invalid source SHA-256")
    require(strings(record.get("conditions")), "Conditions must be a list of text")
    require(strings(record.get("material_conflicts")), "Conflicts must be a list of text")

    fit = record.get("practice_fit")
    judgment(fit, "practice_fit", {"pass", "fail", "unknown"})
    if record["nbs_id"] == policy["water_harvesting_nbs_id"]:
        purpose = record.get("water_harvesting_purpose")
        require(purpose in {"primary", "secondary", "unclear"},
                "Record water-harvesting purpose separately from demonstration")
        demonstration = record.get("water_harvesting_demonstration")
        require(isinstance(demonstration, dict), "Missing water-harvesting demonstration")
        strength = demonstration.get("strength")
        require(strength in {"strong", "weak", "unclear"}, "Invalid harvesting demonstration strength")
        require(text(demonstration.get("rationale")), "Missing harvesting demonstration rationale")
        if strength in {"strong", "weak"}:
            require(text(demonstration.get("source_locator")), "Harvesting demonstration needs a source locator")
        if strength == "strong":
            for key in ("capture_storage", "water_use"):
                require(text(demonstration.get(key)), f"Strong harvesting demonstration needs {key}")
        elif strength == "weak" and purpose == "secondary":
            return "exclude_wrong_practice"
        else:
            return "hold"
    if fit["status"] == "fail":
        return "exclude_wrong_practice"
    if fit["status"] == "unknown":
        return "hold"

    definition = record.get("definition")
    require(isinstance(definition, dict), "Missing definition record")
    require(type(definition.get("available")) is bool, "Definition availability must be Boolean")
    if not definition["available"]:
        require(text(definition.get("access_note")), "Missing definition access-hold reason")
        return "hold"
    require(definition.get("kind") == "authorised_project_catalogue", "Use the authorised project catalogue")
    require(definition.get("access") in {"restricted", "public"}, "Missing definition access terms")
    for key in ("edition", "general_locator", "practice_locator", "chapter_mapping_rationale"):
        require(text(definition.get(key)), f"Missing definition {key}")
    require(re.fullmatch(r"[0-9a-f]{64}", definition.get("sha256", "")) is not None,
            "Invalid definition SHA-256")

    criteria = record.get("criteria")
    required = policy["core_criteria"] + policy["context_criteria"]
    require(isinstance(criteria, dict) and set(criteria) == set(required),
            "Provide exactly the required inclusion criteria")
    for name in required:
        item = criteria[name]
        judgment(item, name, set(policy["criterion_statuses"]))
        if item["status"] in {"pass", "fail"}:
            require(text(item.get("definition_locator")), f"Missing definition locator: {name}")
        if name in policy["core_criteria"]:
            require(item["status"] != "not_applicable", f"Core criterion cannot be omitted: {name}")
        if name == "landscape_hydrology" and record["nbs_id"] == policy["water_harvesting_nbs_id"]:
            require(item["status"] != "not_applicable", "Water-harvesting hydrology cannot be omitted")
    if any(item["status"] == "fail" for item in criteria.values()):
        return "exclude_nbs"
    if record["material_conflicts"] or any(criteria[n]["status"] == "unknown" for n in policy["core_criteria"]):
        return "hold"
    uncertain = any(criteria[n]["status"] == "unknown" for n in policy["context_criteria"])
    if uncertain and not record["conditions"]:
        return "hold"
    if uncertain or record["conditions"]:
        return "conditional_include"
    return "include_for_scoping"


def check_bytes(record_data, source_data, definition_data=None):
    policy_data = POLICY.read_bytes()
    policy = load(policy_data)
    record = load(record_data)
    decision = assess(record, policy)
    require(record["source_sha256"] == digest(source_data), "Source bytes changed; reassess")
    definition = record.get("definition", {})
    require(isinstance(definition, dict), "Definition record must be an object")
    definition_verified = False
    if definition.get("available") is True:
        require(definition_data is not None, "Supply the reviewed definition file")
        require(definition.get("sha256") == digest(definition_data), "Definition bytes changed; reassess")
        definition_verified = True
    return {
        "ruleset": policy["id"], "ruleset_sha256": digest(policy_data),
        "assessment_sha256": digest(record_data), "source_id": record["source_id"],
        "source_sha256": digest(source_data), "definition_bytes_verified": definition_verified,
        "definition_sha256": digest(definition_data) if definition_verified else None,
        "decision": decision, "human_approval": False,
        "scope": "Private judgment-consistency check; no register or analytical writes",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assessment", type=Path)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--definition", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = check_bytes(args.assessment.read_bytes(), args.source.read_bytes(),
                              args.definition.read_bytes() if args.definition else None)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2)
            stream.write("\n")
        print(receipt["decision"])
        return 0 if receipt["decision"] in {"include_for_scoping", "conditional_include"} else 2
    except (ValueError, TypeError, OSError) as error:
        print(f"Invalid inclusion assessment: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
