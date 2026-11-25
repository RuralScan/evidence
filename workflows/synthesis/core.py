"""Validate authored effect decisions without deriving a scientific rating."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path(__file__).with_name("contract.json")
FORMAT = "ruralscan.agent-effects.v1"
TABLES = {"T3": "T3_nbs_hazard_farming", "T6": "T6_nbs_scorecard"}
JOURNAL = "synthesis/acceptances.jsonl"
PROPOSALS = "synthesis/proposals"
ID = re.compile(r"[a-z][a-z0-9_-]{0,100}")
SHA = re.compile(r"[a-f0-9]{64}")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(
        value if isinstance(value, bytes) else encoded(value)
    ).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def policy():
    return json.loads(CONTRACT.read_bytes())


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def strings(values):
    if isinstance(values, list):
        return values
    return [v.strip() for v in str(values or "").split("|") if v.strip()]


def inputs(root, producer, practice, registers):
    """Select a broad practice corpus; AI accounts for every included/excluded claim."""
    ev = [
        r
        for r in registers["EV_evidence_register"]
        if practice in strings(r.get("nbs_id"))
        and r.get("use_role") in {"nbs_effect", "asset_vulnerability"}
    ]
    source_ids = {r["source_id"] for r in ev}
    src = [r for r in registers["SRC_source_register"] if r["source_id"] in source_ids]
    files, definitions = {}, {}
    for folder in (root / "configuration",):
        if folder.exists():
            for p in sorted(folder.rglob("*")):
                if p.is_file() and p.suffix in {".csv", ".json"}:
                    files[p.relative_to(root).as_posix()] = digest(p.read_bytes())
    for rel in policy()["definition_inputs"]:
        p = producer / rel
        require(p.is_file(), f"Missing definition: {rel}")
        files[rel] = digest(p.read_bytes())
        definitions[rel] = list(csv.DictReader(io.StringIO(p.read_text(), newline="")))
    review_path = producer / "pipeline/metrics/review_log.csv"
    reviews = (
        list(csv.DictReader(io.StringIO(review_path.read_text(), newline="")))
        if review_path.exists()
        else []
    )
    candidate_ids = {r["evidence_id"] for r in ev}
    reviews = [r for r in reviews if r.get("evidence_id") in candidate_ids]
    packet = {
        "practice": practice,
        "definitions": definitions,
        "review_log": reviews,
        "evidence": sorted(ev, key=lambda r: r["evidence_id"]),
        "sources": sorted(src, key=lambda r: r["source_id"]),
        "configuration": files,
        "contract_sha256": digest(CONTRACT.read_bytes()),
    }
    from submissions.family_hierarchy import coverage, load

    hierarchy = coverage(root, ev, reviews)
    if hierarchy is not None:
        hierarchy["groups"] = load(root)["definition"]["evidence_aggregation"]["groups"]
        hierarchy["nodes"] = {
            k: v for k, v in hierarchy["nodes"].items() if v["nbs_id"] == practice
        }
        hierarchy["coverage"] = {
            k: v for k, v in hierarchy["coverage"].items() if k in hierarchy["nodes"]
        }
        packet["family_hierarchy"] = hierarchy
    return packet


def group_definition(proposal, packet):
    gid = proposal.get("evidence_group_id")
    if gid is None:
        return None
    groups = packet.get("family_hierarchy", {}).get("groups", {})
    require(
        isinstance(gid, str)
        and gid in groups
        and groups[gid]["nbs_id"] == proposal["practice"],
        "Unknown evidence group in pinned inputs",
    )
    return groups[gid]


def prior_rows(queue, proposal):
    gid = proposal.get("evidence_group_id")
    if gid is None:
        return queue["recipes"][proposal["practice"]][TABLES[proposal["table"]]]
    matches = [
        g
        for g in queue["effect_synthesis"].get("groups", [])
        if g["evidence_group_id"] == gid and g["practice"] == proposal["practice"]
    ]
    return matches[0]["recipes"][TABLES[proposal["table"]]] if matches else []


def validate_aggregation(proposal, row, packet):
    """Demand explicit applicability, including missing children; never infer a pooled score."""
    group = group_definition(proposal, packet)
    hierarchy = packet.get("family_hierarchy")
    if hierarchy is None:
        return  # Replaying an immutable historical proposal.
    from submissions.family_hierarchy import ancestors

    nodes = hierarchy["nodes"]
    family = row.get("suitability_family_id")
    require(
        not group or not family,
        "Group summary cannot masquerade as a suitability family",
    )
    target = (
        "group:" + proposal["evidence_group_id"]
        if group
        else ("family:" + family if family else "practice:" + proposal["practice"])
    )
    members = (
        set(group["families"])
        if group
        else (
            {family}
            if family
            else {
                n["id"]
                for n in nodes.values()
                if n["level"] == "family"
                and n.get("spatial_product_type") != "qualitative_only"
                and not n["id"].endswith("__cross_family")
            }
        )
    )
    refs = row["evidence_ids"]
    known = {}
    allowed = {}
    for eid in refs:
        node = hierarchy["findings"][eid]["node"]
        lineage = {node} | ancestors(nodes, node)
        require(
            not any(
                nodes[n].get("spatial_product_type") == "qualitative_only"
                for n in lineage
            ),
            "Qualitative-only evidence cannot support landscape outputs",
        )
        known[eid] = {nodes[n]["id"] for n in lineage if nodes[n]["level"] == "family"}
        level = nodes[node]["level"]
        if level == "legacy_family":
            require(
                target in lineage,
                "Historical scope needs a finding correction before child attribution",
            )
            allowed[eid] = set()
        elif level == "group":
            allowed[eid] = set(hierarchy["groups"][nodes[node]["id"]]["families"])
            require(
                bool(allowed[eid] & members),
                "Evidence belongs to a different group scope",
            )
        else:
            allowed[eid] = known[eid] or members
        require(
            not known[eid] or known[eid] <= members,
            "Evidence belongs to a different family scope",
        )
    if family and all(
        target
        in (
            {hierarchy["findings"][eid]["node"]}
            | ancestors(nodes, hierarchy["findings"][eid]["node"])
        )
        for eid in refs
    ):
        return  # Exact-family evidence, no upward or cross-scope claim.
    a = row["justification"].get("aggregation", {})
    require(
        isinstance(a, dict)
        and all(nonempty(a.get(k)) for k in ("scope_rationale", "conflict_note")),
        "Aggregation needs scope rationale and conflict note",
    )
    for key in ("covered_families", "unresolved_families"):
        require(
            isinstance(a.get(key), list)
            and all(isinstance(v, str) for v in a[key])
            and len(a[key]) == len(set(a[key])),
            "Aggregation needs unique child coverage lists",
        )
    covered, unresolved = set(a["covered_families"]), set(a["unresolved_families"])
    require(
        not covered & unresolved and covered | unresolved == members,
        "Aggregation must account for every child family",
    )
    claims = a.get("evidence_applicability", {})
    require(
        isinstance(claims, dict) and set(claims) == set(refs),
        "Aggregation must explain each supporting finding",
    )
    supported = set()
    for eid, claim in claims.items():
        require(
            isinstance(claim, dict)
            and nonempty(claim.get("rationale"))
            and isinstance(claim.get("families"), list)
            and all(isinstance(v, str) for v in claim["families"]),
            "Finding applicability needs families and source rationale",
        )
        targets = set(claim["families"])
        require(
            targets <= covered and targets <= allowed[eid],
            "Finding cannot inherit support for sibling families",
        )
        supported.update(targets)
    require(supported == covered, "Covered family has no justified supporting finding")


def replacement_digest(row):
    """Scientific fingerprint excludes legacy editorial fields, not scientific rationale."""
    science = dict(row)
    for key in (
        "effect_mechanism",
        "mitigation_mechanism",
        "conditionality",
        "caveats",
    ):
        science.pop(key, None)
    if isinstance(science.get("justification"), dict):
        science["justification"] = {
            k: v
            for k, v in science["justification"].items()
            if k
            not in {
                "mechanism",
                "conditionality",
                "agreement_note",
                "evidence_summary",
                "prose_written",
                "prose_pending",
            }
        }
    return digest(science)


def read_rows(path, table):
    contract = policy()
    spec = contract["tables"][table]
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline=""))
    require(
        reader.fieldnames == spec["columns"],
        "Use the exact ordered CSV columns in the synthesis contract",
    )
    rows = []
    for raw in reader:
        require(None not in raw and None not in raw.values(), "Malformed row CSV")
        row = {}
        for key, value in raw.items():
            if value == "":
                row[key] = None
            elif key in contract["json_fields"]:
                row[key] = json.loads(value)
            elif key in contract["boolean_fields"]:
                require(value in {"true", "false"}, f"Invalid boolean: {key}")
                row[key] = value == "true"
            elif key in contract["number_fields"]:
                row[key] = float(value)
                require(math.isfinite(row[key]), f"Non-finite {key}")
            else:
                row[key] = value
        rows.append(row)
    return rows


def write_rows(path, table, rows):
    contract = policy()
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, contract["tables"][table]["columns"], lineterminator="\n"
    )
    writer.writeheader()
    for row in rows:
        cooked = {}
        for key in writer.fieldnames:
            value = row.get(key)
            cooked[key] = (
                ""
                if value is None
                else (
                    json.dumps(
                        value,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    )
                    if key in contract["json_fields"] or isinstance(value, bool)
                    else value
                )
            )
        writer.writerow(cooked)
    path.write_text(stream.getvalue(), encoding="utf-8")


def proposal_digest(folder):
    return digest(
        {
            name: digest((folder / name).read_bytes())
            for name in ("proposal.json", "rows.csv", "inputs.json", "skill.md")
        }
    )


def validate(folder, current_inputs=None, prior=None):
    """Check completeness, types, provenance and holds. Never assign scientific values."""
    contract = policy()
    require(
        folder.is_dir() and not folder.is_symlink(), "Linked/missing proposal directory"
    )
    require(
        {f.name for f in folder.iterdir()}
        == {"proposal.json", "rows.csv", "inputs.json", "skill.md"},
        "Unexpected proposal file inventory",
    )
    require(
        all(f.is_file() and not f.is_symlink() for f in folder.iterdir()),
        "Linked proposal member",
    )
    p = json.loads((folder / "proposal.json").read_bytes())
    require(
        p.get("format") == FORMAT and ID.fullmatch(p.get("id", "")),
        "Invalid proposal identity",
    )
    require(
        p.get("table") in TABLES and ID.fullmatch(p.get("practice", "")),
        "Invalid practice/table",
    )
    packet = json.loads((folder / "inputs.json").read_bytes())
    require(packet.get("practice") == p["practice"], "Wrong input practice")
    group_definition(p, packet)
    require(
        packet.get("contract_sha256") == digest(CONTRACT.read_bytes()),
        "Synthesis contract differs",
    )
    require(p.get("inputs_sha256") == digest(packet), "Input snapshot changed")
    if current_inputs is not None:
        require(
            digest(current_inputs) == p["inputs_sha256"],
            "Stale synthesis inputs; new proposal required",
        )
    require(
        p.get("skill_sha256") == digest((folder / "skill.md").read_bytes()),
        "Skill snapshot changed",
    )
    require(
        p.get("rows_sha256") == digest((folder / "rows.csv").read_bytes()),
        "Authored rows changed",
    )
    for key in ("task", "comparison"):
        require(nonempty(p.get(key)), f"Missing {key}")
    agent = p.get("agent", {})
    for key in ("model", "skill_version", "prompt", "settings"):
        require(nonempty(agent.get(key)), f"Missing agent provenance: {key}")
    reasoning = p.get("reasoning", {})
    require(
        set(reasoning) == set(contract["reasoning"]), "Incomplete scientific reasoning"
    )
    require(all(nonempty(v) for v in reasoning.values()), "Empty scientific reasoning")
    ev = {r["evidence_id"]: r for r in packet["evidence"]}
    src = {r["source_id"]: r for r in packet["sources"]}
    latest = {}
    for event in packet.get("review_log", []):
        latest[event["evidence_id"]] = event.get("decision")
    definitions = packet["definitions"]
    fam = definitions["schema/registers/FAM_family_registry.csv"]
    priorities = {
        r["variable_id"]: r for r in definitions["schema/T5_opportunity_space.csv"]
    }
    contexts = {
        r["context_id"]: r.get("context_type")
        for r in definitions["schema/T7_geographic_context.csv"]
    }
    dispositions = p.get("candidates", [])
    ids = [d.get("evidence_id") for d in dispositions]
    require(
        len(ids) == len(set(ids)) and set(ids) == set(ev),
        "Account for every candidate exactly once",
    )
    included = set()
    for d in dispositions:
        require(
            d.get("disposition") in {"include", "exclude", "context", "hold"},
            "Unresolved candidate disposition",
        )
        require(
            nonempty(d.get("reason")) and nonempty(d.get("origin")),
            "Candidate needs reason and origin accounting",
        )
        unit = ev[d["evidence_id"]]
        require(unit["source_id"] in src, "Unresolved source")
        if d["disposition"] == "include":
            require(
                unit.get("review_state") not in {"dropped", "held", "flagged", "query"},
                "Held/dropped evidence cannot support accepted science",
            )
            require(
                latest.get(unit["evidence_id"])
                not in {"flag", "query", "reopen", "drop"},
                "Unresolved evidence review hold",
            )
            require(
                unit.get("reviewer_ok") is True,
                "Supporting evidence needs scientific review",
            )
            require(
                nonempty(unit.get("quote"))
                and (unit.get("page") is not None or nonempty(unit.get("locator"))),
                "Supporting evidence needs source passage and locator",
            )
            source = src[unit["source_id"]]
            identity = "doi_verified" if source.get("doi") else "title_verified"
            require(
                source.get(identity) is True,
                "Supporting source identity is not verified",
            )
            included.add(d["evidence_id"])
    replacements = p.get("replaces")
    require(isinstance(replacements, dict), "Declare exact replaced row hashes")
    require(
        all(
            nonempty(k) and isinstance(v, str) and SHA.fullmatch(v)
            for k, v in replacements.items()
        ),
        "Invalid replaced row hashes",
    )
    if prior is not None:
        old = {r["record_id"]: r for r in prior}
        require(
            all(
                k in old and replacement_digest(old[k]) == v
                for k, v in replacements.items()
            ),
            "Stale replacement basis",
        )
    rows = read_rows(folder / "rows.csv", p["table"])
    require(
        rows or (replacements and p.get("action") == "withdraw"),
        "Empty output requires explicit withdrawal",
    )
    require(p.get("action") in {"replace", "withdraw"}, "Declare replace or withdraw")
    require(p["action"] != "withdraw" or not rows, "Withdrawal cannot add rows")
    record_ids = set()
    used = set()
    spec = contract["tables"][p["table"]]
    for row in rows:
        require(row["nbs_id"] == p["practice"], "Wrong practice in output")
        rid = row["record_id"]
        require(
            nonempty(rid) and rid not in record_ids, "Duplicate or missing record ID"
        )
        record_ids.add(rid)
        if prior is not None:
            require(
                rid not in old or rid in replacements,
                "Existing row needs explicit replacement",
            )
        for key in spec["required"]:
            require(
                row.get(key) is not None and row[key] != "",
                f"Missing required field: {key}",
            )
        for key, choices in spec["enum_values"].items():
            require(row.get(key) in (None, "") or row[key] in choices, f"Invalid {key}")
        for key in contract["boolean_fields"]:
            if key in row and row[key] is not None:
                require(type(row[key]) is bool, f"Invalid {key}")
        refs = row.get("evidence_ids")
        require(
            isinstance(refs, list)
            and len(set(refs)) == len(refs)
            and set(refs) <= included,
            "Output cites unaccounted or held evidence",
        )
        used.update(refs)
        justification = row.get("justification")
        require(
            isinstance(justification, dict)
            and nonempty(justification.get("rationale")),
            "Row needs AI scientific rationale",
        )
        for key in ("applicability", "magnitude_summary"):
            if row.get(key) is not None:
                require(isinstance(row[key], dict), f"Invalid {key}")
        require(
            bool(row.get("scope_type")) == bool(row.get("scope_id")), "Incomplete scope"
        )
        if row.get("scope_type"):
            allowed = (
                contract["income_scopes"]
                if row["scope_type"] == "income_group"
                else contexts
            )
            require(row["scope_id"] in allowed, "Unresolved scope reference")
            if row["scope_type"] != "income_group":
                require(
                    contexts[row["scope_id"]] == row["scope_type"],
                    "Scope type differs from its context",
                )
        family = row.get("suitability_family_id")
        if family:
            families = [
                r
                for r in fam
                if r["suitability_family_id"] == family and r["nbs_id"] == p["practice"]
            ]
            require(
                families
                and all(
                    r.get("spatial_product_type") != "qualitative_only"
                    for r in families
                ),
                "Unknown or qualitative-only family",
            )
        if p["table"] == "T3":
            require(
                row["farming_system"] == "all"
                or contexts.get(row["farming_system"]) == "farming_system",
                "Unresolved farming system",
            )
        else:
            require(
                row["variable_id"] in priorities
                and priorities[row["variable_id"]].get("mcda_role") == "priority",
                "T6 must reference a T5 priority",
            )
        validate_aggregation(p, row, packet)
        deficient = justification.get("data_deficient") is True
        if not refs:
            require(deficient, "No supporting evidence: record data deficiency")
        fields = (
            ["effect_direction"]
            if p["table"] == "T6"
            else ["mitigation_potential", "asset_sensitivity"]
        )
        if deficient:
            require(
                all(row.get(k) is None for k in fields)
                and row.get("asset_risk_weight") is None,
                "Unknown effect cannot become a class or zero weight",
            )
        elif p["table"] == "T6":
            require(row.get("effect_direction") is not None, "Missing effect judgment")
        else:
            role = row["risk_role"]
            require(
                row["hazard_type"] in contract["asset_weight_hazards"]
                or role == "asset_threat",
                "Asset-only hazard cannot be livelihood mitigation",
            )
            require(
                role != "asset_threat" or row.get("mitigation_potential") is None,
                "Asset row has a mitigation judgment",
            )
            require(
                role != "livelihood_mitigation" or row.get("asset_sensitivity") is None,
                "Livelihood row has an asset judgment",
            )
            if role in {"livelihood_mitigation", "both"}:
                require(
                    row.get("mitigation_potential") is not None,
                    "Missing mitigation judgment",
                )
            if role in {"asset_threat", "both"}:
                require(
                    row.get("asset_sensitivity") is not None, "Missing asset judgment"
                )
            weight = row.get("asset_risk_weight")
            require(
                weight is None
                or (role in {"asset_threat", "both"} and 0 <= weight <= 1),
                "Invalid authored asset weight",
            )
        if p["table"] == "T6":
            require(
                row.get("variable_type") != "economic_indicator"
                and row.get("economic_value_range") is None
                and row.get("economic_indicator_type") is None,
                "T6E is outside this proposal contract",
            )
        if row.get("magnitude_summary") is not None:
            origins = {d["origin"] for d in dispositions if d["evidence_id"] in refs}
            require(
                len(origins) >= contract["minimum_numeric_origins"],
                "Numerical summaries need independent compatible origins",
            )
    require(used == included, "Every included candidate must support an output row")
    return p, rows


def entries(root):
    path = root / JOURNAL
    return (
        [json.loads(line) for line in path.read_text().splitlines() if line]
        if path.exists()
        else []
    )


def apply(root, producer, registers, baseline):
    """Replay accepted values exactly; stale decisions stay visible but cannot be packaged."""
    rows = json.loads(json.dumps(baseline))
    status, packets, groups = {}, {}, {}
    seen = set()
    for event in entries(root):
        pid = event["proposal_id"]
        require(ID.fullmatch(pid), "Invalid accepted proposal ID")
        folder = root / PROPOSALS / pid
        require(
            event["proposal_sha256"] == proposal_digest(folder),
            "Accepted proposal changed",
        )
        p, authored = validate(folder)
        gid = p.get("evidence_group_id")
        if gid is not None:
            group = groups.setdefault(
                gid,
                {
                    "practice": p["practice"],
                    "recipes": {name: [] for name in TABLES.values()},
                    "status": {},
                },
            )
            require(group["practice"] == p["practice"], "Group changed practice")
            destination, scope_status = group["recipes"], group["status"]
        else:
            destination, scope_status = rows[p["practice"]], status
        if event["decision"] == "hold":
            require(pid in seen, "Cannot hold an unaccepted proposal")
            for rid in scope_status:
                if scope_status[rid]["proposal_id"] == pid:
                    scope_status[rid]["status"] = "held"
            continue
        require(
            event["decision"] == "accept" and pid not in seen,
            "Duplicate/invalid acceptance",
        )
        seen.add(pid)
        name = TABLES[p["table"]]
        before = destination[name]
        validate(folder, prior=before)
        if p["practice"] not in packets:
            packets[p["practice"]] = inputs(root, producer, p["practice"], registers)
        current = digest(packets[p["practice"]]) == p["inputs_sha256"]
        replaced = set(p["replaces"])
        for rid in replaced:
            scope_status.pop((p["practice"], p["table"], rid), None)
        destination[name] = [
            r for r in before if r["record_id"] not in replaced
        ] + authored
        cell_keys = policy()["tables"][p["table"]]["cell_fields"]
        cells = [tuple(r.get(k) or None for k in cell_keys) for r in destination[name]]
        require(
            len(cells) == len(set(cells)),
            "Multiple rows define the same scientific cell",
        )
        if p["action"] == "withdraw":
            for rid in replaced:
                scope_status[(p["practice"], p["table"], rid)] = {
                    "status": "accepted" if current else "stale",
                    "action": "withdraw",
                    "proposal_id": pid,
                    "proposal_sha256": event["proposal_sha256"],
                    "receipt": event["receipt"],
                    "accepted_at": event["created_at"],
                    "inputs_sha256": p["inputs_sha256"],
                    "row_sha256": None,
                    "previous_sha256": p["replaces"][rid],
                }
        for r in authored:
            scope_status[(p["practice"], p["table"], r["record_id"])] = {
                "status": "accepted" if current else "stale",
                "proposal_id": pid,
                "proposal_sha256": event["proposal_sha256"],
                "receipt": event["receipt"],
                "accepted_at": event["created_at"],
                "inputs_sha256": p["inputs_sha256"],
                "row_sha256": digest(r),
            }
    # Rating approval is not scientific acceptance; a subsequent hold still blocks release.
    reviews = root / "row-reviews/receipts.jsonl"
    latest_votes = {}
    if reviews.exists():
        for raw in reviews.read_text().splitlines():
            review = json.loads(raw)
            e = review["entry"]
            key = (e["practice"], e["table"], e["record"])
            current = status.get(key)
            if (
                current
                and e["row_sha256"] == current["row_sha256"]
                and review["created_at"] >= current["accepted_at"]
            ):
                latest_votes[(key, review["actor"])] = review
    for (key, actor), review in latest_votes.items():
        if review["entry"]["decision"] in {"hold", "reject"}:
            status[key]["status"] = "held"
            status[key].setdefault("row_review_holds", []).append(review["receipt"])
    published = [
        {"practice": k[0], "table": k[1], "record_id": k[2], **v}
        for k, v in sorted(status.items())
    ]
    return rows, {
        "mode": "ai_led",
        "historical_rows_are_accepted": False,
        "rows": published,
        **(
            {
                "groups": [
                    {
                        "evidence_group_id": gid,
                        "practice": g["practice"],
                        "recipes": g["recipes"],
                        "runtime_eligible": False,
                        "rows": [
                            {"practice": k[0], "table": k[1], "record_id": k[2], **v}
                            for k, v in sorted(g["status"].items())
                        ],
                    }
                    for gid, g in sorted(groups.items())
                ]
            }
            if groups
            else {}
        ),
    }
