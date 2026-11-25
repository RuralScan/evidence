"""Check authored suitability mappings; never derive curves or scientific weights."""

import csv
import io
import json
import math
from pathlib import Path

from synthesis.core import digest, encoded, git, require, ID, SHA, nonempty, strings

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path(__file__).with_name("contract.json")
FORMAT = "ruralscan.agent-t4.v1"
PROPOSALS = "suitability/proposals"
JOURNAL = "suitability/acceptances.jsonl"
TABLE = "T4_suitability_mappings"
MEMBERS = {"proposal.json", "inputs.json", "rows.csv", "skill.md"}


def policy():
    return json.loads(CONTRACT.read_bytes())


def inputs(root, producer, practice, registers):
    # Deliberately include operational and broader findings for explicit disposition.
    evidence = [
        r
        for r in registers["EV_evidence_register"]
        if practice in strings(r.get("nbs_id"))
        and r.get("use_role") in {"structural_suitability", "operational_risk"}
    ]
    ids = {r["source_id"] for r in evidence}
    definitions = {}
    hashes = {}
    for rel in policy()["definition_inputs"]:
        raw = (producer / rel).read_bytes()
        hashes[rel] = digest(raw)
        definitions[rel] = list(csv.DictReader(io.StringIO(raw.decode(), newline="")))
    for p in sorted((root / "configuration").rglob("*")):
        if p.is_file() and p.suffix in {".json", ".csv"}:
            hashes[p.relative_to(root).as_posix()] = digest(p.read_bytes())
    ev_ids = {r["evidence_id"] for r in evidence}
    with (producer / "pipeline/metrics/review_log.csv").open(newline="") as stream:
        reviews = [r for r in csv.DictReader(stream) if r["evidence_id"] in ev_ids]
    return dict(
        practice=practice,
        evidence=sorted(evidence, key=lambda r: r["evidence_id"]),
        sources=sorted(
            [r for r in registers["SRC_source_register"] if r["source_id"] in ids],
            key=lambda r: r["source_id"],
        ),
        review_log=reviews,
        definitions=definitions,
        configuration=hashes,
        contract_sha256=digest(CONTRACT.read_bytes()),
        skill_sha256=digest(
            (root / ".agents/skills/source-command-t4-synthesise/SKILL.md").read_bytes()
        ),
    )


def families(packet):
    return {
        r["suitability_family_id"]
        for r in packet["definitions"]["schema/registers/FAM_family_registry.csv"]
        if r["nbs_id"] == packet["practice"]
        and r.get("spatial_product_type") != "qualitative_only"
        and not r["suitability_family_id"].endswith("__cross_family")
    }


def entries(root):
    p = root / JOURNAL
    return (
        [json.loads(line) for line in p.read_text().splitlines() if line]
        if p.exists()
        else []
    )


def proposal_digest(folder):
    return digest(
        {name: digest((folder / name).read_bytes()) for name in sorted(MEMBERS)}
    )


def read_rows(path):
    reader = csv.DictReader(io.StringIO(path.read_text(), newline=""))
    require(
        reader.fieldnames == policy()["columns"], "Use the exact T4 contract CSV header"
    )
    rows = []
    for raw in reader:
        require(None not in raw and None not in raw.values(), "Malformed T4 CSV row")
        row = {
            k: None if v == "" else json.loads(v) if k in policy()["json_fields"] else v
            for k, v in raw.items()
        }
        if row["weight_default"] is not None:
            row["weight_default"] = float(row["weight_default"])
        rows.append(row)
    return rows


def write_rows(path, rows):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, policy()["columns"], lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                k: (
                    ""
                    if row.get(k) is None
                    else (
                        json.dumps(row[k], allow_nan=False)
                        if k in policy()["json_fields"]
                        else row[k]
                    )
                )
                for k in writer.fieldnames
            }
        )
    path.write_text(out.getvalue())


def number(value):
    return type(value) in {int, float} and math.isfinite(value)


def score(value):
    return number(value) and 0 <= value <= 1


def evaluate(kind, params, value):
    """Evaluate an explicit authored boundary example, not a raster or derived curve."""
    if value is None or kind == "qualitative":
        return None
    if kind == "ranked_classes":
        return params["classes"].get(value)
    require(number(value), "Numeric boundary input required")
    if kind == "threshold":
        t = params["threshold"]
        passed = {"lt": value < t, "le": value <= t, "gt": value > t, "ge": value >= t}[
            params["operator"]
        ]
        return params["pass"] if passed else params["fail"]
    points = params["points"]
    if value < points[0][0]:
        return params["below"]
    if value > points[-1][0]:
        return params["above"]
    for x, y in points:
        if value == x:
            return y
    for (a, x), (b, y) in zip(points, points[1:]):
        if a < value < b:
            return x + (y - x) * ((value - a) / (b - a))
    raise ValueError("Boundary outside declared representation")


def representation(row):
    kind, p = row["relationship_type"], row["relationship_params"]
    require(
        kind in policy()["relationship_types"] and isinstance(p, dict),
        "Unsupported representation",
    )
    common = {"unit", "missing"}
    extra = {
        "piecewise": {"points", "below", "above"},
        "threshold": {"operator", "threshold", "pass", "fail"},
        "ranked_classes": {"classes"},
        "qualitative": {"note"},
    }[kind]
    require(
        set(p) == common | extra and nonempty(p["unit"]) and p["missing"] is None,
        "Explicit unit and unknown missing-value behavior required; no undeclared parameters",
    )
    if kind == "qualitative":
        require(
            nonempty(p["note"]) and row["readiness"] == "calibration_hold",
            "Qualitative mapping must remain held",
        )
        return
    if kind == "piecewise":
        points = p["points"]
        require(
            isinstance(points, list)
            and len(points) >= 2
            and all(
                isinstance(v, list) and len(v) == 2 and number(v[0]) and score(v[1])
                for v in points
            ),
            "Piecewise points need finite inputs and scores in [0,1]",
        )
        require(
            all(a[0] < b[0] for a, b in zip(points, points[1:])),
            "Piecewise endpoints must increase strictly",
        )
        require(
            all(p[k] is None or score(p[k]) for k in ("below", "above")),
            "Explicit tail values required",
        )
    elif kind == "threshold":
        require(
            p["operator"] in {"lt", "le", "gt", "ge"}
            and number(p["threshold"])
            and score(p["pass"])
            and score(p["fail"]),
            "Invalid threshold parameters",
        )
    else:
        require(
            isinstance(p["classes"], dict)
            and p["classes"]
            and all(nonempty(k) and score(v) for k, v in p["classes"].items()),
            "Invalid class scores",
        )

    cases = row["justification"].get("boundary_cases")
    require(isinstance(cases, list) and cases, "Boundary examples required")
    values = []
    for case in cases:
        require(
            isinstance(case, dict)
            and set(case) == {"input", "expected", "reason"}
            and nonempty(case["reason"]),
            "Boundary example needs input, expected output and rationale",
        )
        actual = evaluate(kind, p, case["input"])
        require(
            (actual is None and case["expected"] is None)
            or (
                number(actual)
                and number(case["expected"])
                and abs(actual - case["expected"]) < 1e-9
            ),
            "Boundary example disagrees with authored representation",
        )
        values.append(case["input"])
    require(None in values, "Check missing input explicitly")
    if kind == "ranked_classes":
        require(
            set(p["classes"]) <= {v for v in values if isinstance(v, str)}
            and any(isinstance(v, str) and v not in p["classes"] for v in values),
            "Check every class and an unknown class",
        )
    else:
        bounds = (
            [x[0] for x in p["points"]] if kind == "piecewise" else [p["threshold"]]
        )
        numeric = [v for v in values if number(v)]
        require(
            all(
                b in numeric
                and any(v < b for v in numeric)
                and any(v > b for v in numeric)
                for b in bounds
            ),
            "Check every endpoint and both sides",
        )


def validate(folder, current_inputs=None, prior=None):
    require(
        folder.is_dir()
        and not folder.is_symlink()
        and {p.name for p in folder.iterdir()} == MEMBERS,
        "Invalid T4 proposal inventory",
    )
    require(
        all(p.is_file() and not p.is_symlink() for p in folder.iterdir()),
        "Linked T4 proposal member",
    )
    p = json.loads((folder / "proposal.json").read_bytes())
    packet = json.loads((folder / "inputs.json").read_bytes())
    require(
        p.get("format") == FORMAT
        and isinstance(p.get("id"), str)
        and ID.fullmatch(p["id"]),
        "Invalid T4 proposal ID",
    )
    require(
        p.get("practice") == packet.get("practice")
        and p.get("family") in families(packet),
        "Unknown current family",
    )
    require(
        packet["contract_sha256"] == digest(CONTRACT.read_bytes()),
        "T4 contract changed",
    )
    require(p.get("inputs_sha256") == digest(packet), "Input snapshot changed")
    if current_inputs is not None:
        require(
            digest(current_inputs) == p["inputs_sha256"],
            "Stale T4 inputs; new proposal required",
        )
    require(
        p.get("skill_sha256")
        == packet.get("skill_sha256")
        == digest((folder / "skill.md").read_bytes())
        and p.get("rows_sha256") == digest((folder / "rows.csv").read_bytes()),
        "Authored bytes changed",
    )
    require(
        all(nonempty(p.get(k)) for k in ("task", "comparison")),
        "Task and before/after comparison required",
    )
    require(
        all(
            nonempty(p.get("agent", {}).get(k))
            for k in ("model", "prompt", "settings", "skill_version")
        ),
        "Agent provenance required",
    )
    require(
        set(p.get("reasoning", {})) == set(policy()["reasoning"])
        and all(nonempty(v) for v in p["reasoning"].values()),
        "Complete T4 reasoning required",
    )
    ev = {r["evidence_id"]: r for r in packet["evidence"]}
    src = {r["source_id"]: r for r in packet["sources"]}
    latest = {e["evidence_id"]: e.get("decision") for e in packet["review_log"]}
    candidates = p.get("candidates", [])
    ids = [d.get("evidence_id") for d in candidates]
    require(
        len(ids) == len(set(ids)) and set(ids) == set(ev),
        "Account for every candidate exactly once",
    )
    included = set()
    for d in candidates:
        require(
            d.get("disposition") in policy()["candidate_dispositions"]
            and nonempty(d.get("reason"))
            and nonempty(d.get("origin")),
            "Candidate needs disposition, reason and origin",
        )
        if d["disposition"] != "include":
            continue
        unit = ev[d["evidence_id"]]
        require(
            unit.get("use_role") == "structural_suitability",
            "Operational evidence cannot set structural suitability",
        )
        require(
            unit.get("reviewer_ok") is True
            and unit.get("review_state") not in {"dropped", "held", "flagged", "query"}
            and latest.get(d["evidence_id"]) not in {"flag", "query", "reopen", "drop"},
            "Unreviewed or held evidence cannot support T4",
        )
        require(
            nonempty(unit.get("quote"))
            and (unit.get("page") is not None or nonempty(unit.get("locator"))),
            "Passage and locator required",
        )
        source = src.get(unit["source_id"], {})
        require(
            source.get("doi_verified" if source.get("doi") else "title_verified")
            is True,
            "Source identity unverified",
        )
        require(
            unit.get("claim_scope") != "species_specific",
            "Species envelope cannot define practice suitability",
        )
        context = unit.get("context") or {}
        require(
            not any(
                context.get(k)
                for k in (
                    "calibration_hold",
                    "applicability_hold",
                    "transfer_hold",
                    "canonical_mapping_hold",
                )
            ),
            "Recorded calibration/applicability hold needs a reviewed finding correction",
        )
        require(
            (unit.get("relationship") or {}).get("type")
            not in {"observed_presence", "site_descriptor", "model_importance"},
            "Observed setting or importance is context, not a suitability boundary",
        )
        declared = strings(unit.get("suitability_family_id"))
        broad = {
            r["suitability_family_id"]
            for r in packet["definitions"]["schema/registers/FAM_family_registry.csv"]
            if r["nbs_id"] == p["practice"]
            and r["suitability_family_id"].endswith("__cross_family")
        }
        require(
            not declared
            or (p["family"] in declared and set(declared) <= families(packet))
            or set(declared) <= broad,
            "Sibling or unresolved historical family requires source-scope review",
        )
        require(
            unit.get("knowledge_basis", unit.get("claim_basis"))
            not in {"site_descriptor", "observed_presence", "model_importance"},
            "Context/importance alone cannot calibrate suitability",
        )
        if unit.get("claim_scope") == "crop_specific":
            rules = packet["definitions"]["schema/lookups/crop_scope_policy.csv"]
            require(
                any(
                    r.get("nbs_id") == p["practice"]
                    and r.get("suitability_family_id") in {"", p["family"]}
                    and r.get("allow_crop_scope", "").lower() == "true"
                    for r in rules
                ),
                "Crop scope not admitted by pinned policy",
            )
        included.add(d["evidence_id"])
    replacements = p.get("replaces")
    require(
        isinstance(replacements, dict)
        and all(
            nonempty(k) and isinstance(v, str) and SHA.fullmatch(v)
            for k, v in replacements.items()
        ),
        "Explicit replacement hashes required",
    )
    old = {r["mapping_id"]: r for r in prior or []}
    if prior is not None:
        require(
            all(
                k in old
                and digest(old[k]) == v
                and old[k].get("suitability_family_id") == p["family"]
                for k, v in replacements.items()
            ),
            "Stale replacement or different family",
        )
    rows = read_rows(folder / "rows.csv")
    require(
        p.get("action") in {"replace", "withdraw"}
        and (
            bool(rows) if p["action"] == "replace" else bool(replacements) and not rows
        ),
        "Invalid replace/withdraw action",
    )
    definitions = packet["definitions"]
    variables = {
        r["canonical_variable_id"]: r
        for r in definitions["schema/registers/VONT_variable_ontology.csv"]
    }
    datasets = {r["dataset_id"] for r in definitions["schema/T1_data_registry.csv"]}
    contexts = {
        r["context_id"]: r["context_type"]
        for r in definitions["schema/T7_geographic_context.csv"]
    }
    used, seen, cells = set(), set(), set()
    for r in rows:
        rid = r["mapping_id"]
        require(
            isinstance(rid, str) and ID.fullmatch(rid) and rid not in seen,
            "Invalid or duplicate mapping ID",
        )
        seen.add(rid)
        require(
            prior is None or rid not in old or rid in replacements,
            "Existing mapping needs explicit replacement",
        )
        require(
            r["nbs_id"] == p["practice"] and r["suitability_family_id"] == p["family"],
            "Mapping outside proposal family",
        )
        require(
            r["variable"] in variables
            and (
                r["dataset_id"] in datasets
                or (r["dataset_id"] is None and r["readiness"] == "calibration_hold")
            ),
            "Unresolved variable or dataset",
        )
        require(
            r["suitability_dimension"] in policy()["dimensions"]
            and r["readiness"] in policy()["readiness"],
            "Invalid dimension/readiness",
        )
        refs = r["evidence_ids"]
        require(
            isinstance(refs, list)
            and len(refs) == len(set(refs))
            and set(refs) <= included,
            "Mapping cites ineligible evidence",
        )
        require(
            refs or r["readiness"] == "calibration_hold",
            "Calibrated mapping requires evidence",
        )
        used.update(refs)
        j, a = r["justification"], r["applicability"]
        require(
            isinstance(j, dict)
            and all(
                nonempty(j.get(k))
                for k in (
                    "rationale",
                    "binding",
                    "transfer",
                    "weight",
                    "exclusion",
                    "variable_use",
                    "direction",
                    "calibration",
                    "precision",
                    "mechanism",
                )
            ),
            "Mapping needs separate use, direction, calibration, precision and scientific rationales",
        )
        require(
            isinstance(j.get("evidence_applicability"), dict)
            and set(j["evidence_applicability"]) == set(refs)
            and all(nonempty(v) for v in j["evidence_applicability"].values()),
            "Explain applicability of each supporting finding",
        )
        require(
            isinstance(a, dict)
            and set(a) == {"scope_type", "scope_id", "spatial_support", "limitations"}
            and nonempty(a["spatial_support"])
            and nonempty(a["limitations"]),
            "Explicit context and spatial limits required",
        )
        require(
            (a["scope_type"] == "global" and a["scope_id"] == "")
            or (
                a["scope_id"] in contexts and contexts[a["scope_id"]] == a["scope_type"]
            ),
            "Unresolved spatial context",
        )
        cell = (
            r["suitability_family_id"],
            r["variable"],
            a["scope_type"],
            a["scope_id"],
        )
        require(cell not in cells, "Duplicate proposed family/variable/context")
        cells.add(cell)
        if prior is not None:
            collisions = [
                o["mapping_id"]
                for o in prior
                if o.get("suitability_family_id") == r["suitability_family_id"]
                and o.get("variable") == r["variable"]
                and (
                    not o.get("applicability")
                    or (
                        o["applicability"].get("scope_type"),
                        o["applicability"].get("scope_id"),
                    )
                    == (a["scope_type"], a["scope_id"])
                )
            ]
            require(
                set(collisions) <= set(replacements),
                "Existing scientific cell needs explicit replacement, even with a new ID",
            )
        bindings = [
            b
            for b in definitions["schema/registers/BIND_dataset_binding.csv"]
            if b["variable"] == r["variable"]
            and (
                b.get("scope_type") == "global"
                or (b.get("scope_type"), b.get("scope_id"))
                == (a["scope_type"], a["scope_id"])
            )
        ]
        exact = [
            b
            for b in bindings
            if (b.get("scope_type"), b.get("scope_id"))
            == (a["scope_type"], a["scope_id"])
        ]
        choices = exact or bindings
        if r["dataset_id"] is not None:
            require(choices, "No pinned binding for context")
            rank = min(int(b["preference_rank"]) for b in choices)
            require(
                any(
                    b["dataset_id"] == r["dataset_id"]
                    and int(b["preference_rank"]) == rank
                    and b.get("status") in {"catalogued", "community"}
                    for b in choices
                ),
                "No usable preferred pinned dataset binding for context; retain a calibration hold",
            )
        representation(r)
        require(
            r["relationship_params"]["unit"]
            == variables[r["variable"]]["canonical_unit"],
            "Representation unit must match canonical quantity; convert explicitly before proposing",
        )
        require(
            r["weight_default"] is None
            or (score(r["weight_default"]) and r["relationship_type"] != "qualitative"),
            "Invalid authored criterion weight",
        )
        if r["suitability_dimension"] == "operational_constraint":
            params = r["relationship_params"]
            mask = (
                r["relationship_type"] == "threshold"
                and {params["pass"], params["fail"]} == {0, 1}
            ) or (
                r["relationship_type"] == "ranked_classes"
                and set(params["classes"].values()) <= {0, 1}
            )
            require(
                mask and r["weight_default"] is None,
                "Only explicit hard operational masks belong in T4",
            )
    require(used == included, "Every included candidate must support a mapping")
    return p, rows


def apply(root, producer, registers, baseline, historical):
    """Replay immutable mappings; never silently fall back when an accepted mapping is held."""
    events = entries(root)
    if not events:
        return baseline, historical
    rows = json.loads(json.dumps(baseline))
    states, seen, packets, held_proposals = {}, set(), {}, []
    for event in events:
        pid = event["proposal_id"]
        require(
            isinstance(pid, str) and ID.fullmatch(pid),
            "Invalid accepted T4 proposal ID",
        )
        folder = root / PROPOSALS / pid
        require(
            proposal_digest(folder) == event["proposal_sha256"],
            "Accepted T4 bytes changed",
        )
        p, authored = validate(folder)
        require(p["id"] == pid, "Accepted proposal identity differs")
        practice = p["practice"]
        if event["decision"] == "hold":
            if pid not in seen:
                seen.add(pid)
                held_proposals.append(
                    dict(
                        proposal_id=pid,
                        practice=practice,
                        status="held",
                        proposal_sha256=event["proposal_sha256"],
                        receipt=event["receipt"],
                        reason=event["reason"],
                        outputs_applied=False,
                    )
                )
                continue
            for state in states.values():
                if state["proposal_id"] == pid:
                    state["status"] = "held"
            continue
        require(
            event["decision"] == "accept" and pid not in seen,
            "Duplicate/invalid T4 acceptance",
        )
        seen.add(pid)
        before = rows[practice][TABLE]
        validate(folder, prior=before)
        if practice not in packets:
            packets[practice] = inputs(root, producer, practice, registers)
        fresh = digest(packets[practice]) == p["inputs_sha256"]
        replaced = set(p["replaces"])
        for rid in replaced:
            states.pop((practice, rid), None)
        rows[practice][TABLE] = [
            r for r in before if r["mapping_id"] not in replaced
        ] + authored
        # Historical mappings have no explicit applicability object; do not infer their context.
        keys = [
            (
                r["suitability_family_id"],
                r["variable"],
                r["applicability"]["scope_type"],
                r["applicability"]["scope_id"],
            )
            for r in rows[practice][TABLE]
            if "readiness" in r
        ]
        require(
            len(keys) == len(set(keys)), "Duplicate accepted family/variable/context"
        )
        provenance = dict(
            proposal_id=pid,
            proposal_sha256=event["proposal_sha256"],
            receipt=event["receipt"],
            accepted_at=event["created_at"],
            proposal_revision=event["proposal_revision"],
            inputs_sha256=p["inputs_sha256"],
            contract_sha256=digest(CONTRACT.read_bytes()),
        )
        if p["action"] == "withdraw":
            for rid in replaced:
                states[(practice, rid)] = dict(
                    provenance,
                    status="accepted" if fresh else "stale",
                    action="withdraw",
                    row_sha256=None,
                    previous_sha256=p["replaces"][rid],
                )
        for row in authored:
            states[(practice, row["mapping_id"])] = dict(
                provenance,
                action="replace",
                row_sha256=digest(row),
                status=(
                    "stale"
                    if not fresh
                    else (
                        "held" if row["readiness"] == "calibration_hold" else "accepted"
                    )
                ),
            )
    # A later rating hold/rejection challenges these exact bytes, not an older version.
    from submissions.recipe_rows import digest as review_digest

    path = root / "row-reviews/receipts.jsonl"
    votes = {}
    for event in (
        [json.loads(line) for line in path.read_text().splitlines() if line]
        if path.exists()
        else []
    ):
        e = event["entry"]
        if e["table"] != "T4":
            continue
        key = (e["practice"], e["record"])
        state = states.get(key)
        row = next(
            (
                r
                for r in rows.get(key[0], {}).get(TABLE, [])
                if r["mapping_id"] == key[1]
            ),
            None,
        )
        if (
            state
            and row
            and e["row_sha256"] == review_digest(row)
            and event["created_at"] >= state["accepted_at"]
        ):
            votes[(key, event["actor"])] = event
    for (key, _), event in votes.items():
        if event["entry"]["decision"] in {"hold", "reject"}:
            states[key]["status"] = "held"
            states[key].setdefault("row_review_holds", []).append(event["receipt"])
    return rows, {
        "mode": "ai_led",
        "historical_rows_are_accepted": False,
        "runtime_implemented": False,
        "baseline": historical,
        "held_proposals": held_proposals,
        "rows": [
            {"practice": k[0], "table": "T4", "record_id": k[1], **v}
            for k, v in sorted(states.items())
        ],
    }
