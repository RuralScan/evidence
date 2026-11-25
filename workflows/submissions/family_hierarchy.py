"""Read versioned family attribution and deduplicated evidence coverage; never migrate votes."""

import argparse
from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess

TRANSITION = "configuration/family-transition.json"
ADOPTION = "configuration/family-adoption.json"
PIN = "configuration/method-pin.json"
FAM = "registers/schema/registers/FAM_family_registry.csv"
EV = "registers/schema/registers/EV_evidence_register.csv"
LOG = "registers/pipeline/metrics/review_log.csv"
TARGET = "method/family-transition.json"
LANES = {
    "structural_suitability": "T4",
    "operational_risk": "M2b",
    "nbs_effect": "T3/T6",
    "asset_vulnerability": "T3/T6",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def table(data):
    return list(csv.DictReader(io.StringIO(data.decode(), newline="")))


def validate_transition(data, families):
    require(
        data.get("format") == "ruralscan.family-transition.v1",
        "Unsupported family transition",
    )
    current = {(r["nbs_id"], r["suitability_family_id"]) for r in families}
    old = {r["subpractice_id"]: r for r in data["historical_definitions"]}
    new = {r["subpractice_id"]: r for r in families if r["nbs_id"] == data["nbs_id"]}
    require(set(old) == set(new), "Transition lost subpractice identities")
    expected = {
        k
        for k in old
        if old[k]["suitability_family_id"] != new[k]["suitability_family_id"]
    }
    changes = data["subpractice_reassignments"]
    require(
        len(changes) == len(expected)
        and {c["subpractice_id"] for c in changes} == expected,
        "Incomplete family transition",
    )
    for c in changes:
        require(
            c["previous_family"] == old[c["subpractice_id"]]["suitability_family_id"]
            and c["new_family"] == new[c["subpractice_id"]]["suitability_family_id"]
            and c["existing_evidence_action"] == "source_review_required",
            "Unsafe family reassignment",
        )
    policy = data["evidence_migration"]
    require(
        policy["automatic_reassignment"] is False
        and policy["preserve_evidence_ids"] is True
        and policy["preserve_review_and_receipt_history"] is True
        and policy["reuse_approval_for_changed_scope"] is False,
        "Unsafe migration policy",
    )
    aggregation = data["evidence_aggregation"]
    require(
        aggregation["parent_count"] == "union_of_evidence_ids"
        and aggregation["specific_to_broad"] is True
        and aggregation["automatic_downward_inheritance"] is False
        and aggregation["pool_placement_rules"] is False,
        "Unsupported aggregation policy",
    )
    for gid, group in aggregation["groups"].items():
        require(
            (group["nbs_id"], gid) not in current
            and gid not in data["legacy_families"],
            "Evidence group collides with family",
        )
        require(
            set((group["nbs_id"], f) for f in group["families"]) <= current,
            "Unknown group member",
        )


def load(root):
    root = Path(root)
    pin = json.loads((root / PIN).read_bytes()) if (root / PIN).exists() else {}
    expected = pin.get("files", {}).get(TARGET)
    if not expected:
        require(not (root / TRANSITION).exists(), "Unpinned family transition")
        return None
    raw = (root / TRANSITION).read_bytes()
    require(
        sha256(raw).hexdigest() == expected, "Family transition differs from method pin"
    )
    data = json.loads(raw)
    validate_transition(data, table((root / FAM).read_bytes()))
    return {"method_revision": pin["revision"], "sha256": expected, "definition": data}


def adoption(root, transition, revision):
    raw = subprocess.check_output(["git", "-C", str(root), "show", revision + ":" + EV])
    changed = {c["previous_family"] for c in transition["subpractice_reassignments"]}
    records = {
        r["evidence_id"]: r["suitability_family_id"]
        for r in table(raw)
        if r["nbs_id"] == transition["nbs_id"] and r["suitability_family_id"] in changed
    }
    return {
        "format": "ruralscan.family-adoption.v1",
        "evidence_base": revision,
        "ev_sha256": sha256(raw).hexdigest(),
        "pending_at_adoption": records,
    }


def record_adoption(root):
    root = Path(root)
    packet = load(root)
    if not packet:
        return
    path = root / ADOPTION
    if path.exists():
        verify_adoption(root)
        return
    revision = (
        subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    path.write_bytes(encoded(adoption(root, packet["definition"], revision)))


def verify_adoption(root, base=None):
    if base:
        names = (
            subprocess.check_output(
                ["git", "-C", str(root), "ls-tree", "--name-only", base, "--", ADOPTION]
            )
            .decode()
            .splitlines()
        )
        if ADOPTION in names:
            previous = subprocess.check_output(
                ["git", "-C", str(root), "show", base + ":" + ADOPTION]
            )
            require(
                (Path(root) / ADOPTION).read_bytes() == previous,
                "Family adoption history rewritten",
            )
    packet = load(root)
    if not packet:
        return
    saved = json.loads((Path(root) / ADOPTION).read_bytes())
    require(
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                saved["evidence_base"],
                "HEAD",
            ]
        ).returncode
        == 0,
        "Family adoption basis is not an ancestor",
    )
    require(
        saved == adoption(root, packet["definition"], saved["evidence_base"]),
        "Family adoption basis changed",
    )


def object_value(value):
    return (
        json.loads(value) if isinstance(value, str) and value.strip() else value or {}
    )


def intake_family_bytes(producer, units):
    """Permit source corrections to existing legacy findings, never new legacy attribution."""
    raw = (Path(producer) / "schema/registers/FAM_family_registry.csv").read_bytes()
    metadata = Path(producer) / TARGET
    if not metadata.exists():
        return raw
    transition = json.loads(metadata.read_bytes())
    legacy = set(transition["legacy_families"])
    requested = [u for u in units if u.get("suitability_family_id") in legacy]
    if not requested:
        return raw
    old = {
        r["evidence_id"]: r
        for r in table(
            (Path(producer) / "schema/registers/EV_evidence_register.csv").read_bytes()
        )
    }
    for unit in requested:
        previous = old.get(unit["evidence_id"], {})
        require(
            previous.get("suitability_family_id") == unit["suitability_family_id"]
            and previous.get("nbs_id") == unit["nbs_id"],
            "New findings cannot use a retired family; source review must establish current scope",
        )
    rows = table(raw)
    known = {r["suitability_family_id"] for r in rows}
    for historical in transition["historical_definitions"]:
        fid = historical["suitability_family_id"]
        if fid in {u["suitability_family_id"] for u in requested} and fid not in known:
            rows.append(historical)
            known.add(fid)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def graph(families, transition):
    nodes = {}
    groups = transition["evidence_aggregation"]["groups"] if transition else {}
    for row in families:
        practice, family = row["nbs_id"], row["suitability_family_id"]
        nodes.setdefault(
            "practice:" + practice,
            {
                "level": "practice",
                "id": practice,
                "nbs_id": practice,
                "label": practice.replace("_", " "),
                "parents": [],
            },
        )
        parents = [
            "group:" + gid
            for gid, g in groups.items()
            if g["nbs_id"] == practice and family in g["families"]
        ]
        nodes.setdefault(
            "family:" + family,
            {
                "level": "family",
                "id": family,
                "nbs_id": practice,
                "label": family,
                "parents": parents or ["practice:" + practice],
                "spatial_product_type": row["spatial_product_type"],
            },
        )
        if row["subpractice_id"] != "cross_cutting_envelope":
            nodes["subpractice:" + row["subpractice_id"]] = {
                "level": "subpractice",
                "id": row["subpractice_id"],
                "nbs_id": practice,
                "label": row["name"],
                "parents": ["family:" + family],
            }
    for gid, g in groups.items():
        nodes["group:" + gid] = {
            "level": "group",
            "id": gid,
            "label": g["label"],
            "nbs_id": g["nbs_id"],
            "parents": ["practice:" + g["nbs_id"]],
        }
    if transition:
        old = {r["suitability_family_id"] for r in transition["historical_definitions"]}
        for family in old:
            successors = [
                c["new_family"]
                for c in transition["subpractice_reassignments"]
                if c["previous_family"] == family
            ]
            if not successors:
                continue
            parent = "practice:" + transition["nbs_id"]
            if family in transition["legacy_families"]:
                for gid, g in groups.items():
                    if set(successors) <= set(g["families"]):
                        parent = "group:" + gid
            nodes["legacy_family:" + family] = {
                "level": "legacy_family",
                "id": family,
                "nbs_id": transition["nbs_id"],
                "label": family + " (original scope; review pending)",
                "parents": [parent],
            }
    return nodes


def ancestors(nodes, key):
    result, todo = set(), list(nodes[key]["parents"])
    while todo:
        parent = todo.pop()
        require(parent != key and parent in nodes, "Invalid family hierarchy")
        if parent not in result:
            result.add(parent)
            todo.extend(nodes[parent]["parents"])
    return result


def coverage(root, evidence, review_log, *, lane=None):
    packet = load(root)
    if not packet:
        return None
    transition = packet["definition"]
    families = table((Path(root) / FAM).read_bytes())
    nodes = graph(families, transition)
    pending = json.loads((Path(root) / ADOPTION).read_bytes())["pending_at_adoption"]
    latest = {r["evidence_id"]: r.get("decision") for r in review_log}
    direct = {key: set() for key in nodes}
    findings = {}
    for row in evidence:
        eid, practice = row["evidence_id"], row["nbs_id"]
        if lane and LANES.get(row.get("use_role")) != lane:
            continue
        require(eid not in findings, "Duplicate finding in hierarchy")
        family = row.get("suitability_family_id") or ""
        key, status = "family:" + family, "recorded_family"
        if family == "cross_family":
            key = "family:" + practice + "__cross_family"
        scope = object_value(row.get("context")).get("evidence_scope")
        if scope:
            require(
                scope.get("level") in {"subpractice", "family", "group", "practice"}
                and isinstance(scope.get("rationale"), str)
                and scope["rationale"].strip(),
                "Incomplete evidence scope",
            )
            key = scope["level"] + ":" + scope.get("id", "")
            require(
                key in nodes and nodes[key]["nbs_id"] == practice,
                "Unknown evidence scope",
            )
            if scope["level"] in {"family", "subpractice"}:
                actual_family = (
                    key if scope["level"] == "family" else nodes[key]["parents"][0]
                )
                require(
                    actual_family == "family:" + family,
                    "Evidence scope contradicts recorded family",
                )
            else:
                require(
                    family in {"", "cross_family", practice + "__cross_family"},
                    "Broader evidence scope must retain broad family attribution",
                )
            status = "explicit_scope"
        elif family in transition["legacy_families"] or pending.get(eid) == family:
            key, status = "legacy_family:" + family, "source_scope_review_required"
        elif not family or key.endswith("__cross_family"):
            key, status = "practice:" + practice, "broad_or_unspecified_scope"
        require(
            key in nodes and nodes[key]["nbs_id"] == practice,
            "Unresolved finding family",
        )
        decision = latest.get(eid)
        state = "pending"
        if row.get("review_state") == "dropped" or decision in {"drop", "reject"}:
            state = "rejected"
        elif decision in {"flag", "hold", "query"} or row.get("review_state") in {
            "held",
            "flagged",
            "query",
        }:
            state = "held"
        elif decision != "reopen" and str(row.get("reviewer_ok")).lower() == "true":
            state = "reviewed_kept"
        findings[eid] = {
            "source_id": row["source_id"],
            "recorded_family": family,
            "node": key,
            "scope_status": status,
            "review_status": state,
            "lane": LANES.get(row.get("use_role"), "other"),
        }
        direct[key].add(eid)
    totals = {key: set(values) for key, values in direct.items()}
    for key, ids in direct.items():
        for parent in ancestors(nodes, key):
            totals[parent].update(ids)
    views = {}
    for key in nodes:
        parents = ancestors(nodes, key)
        broader = set().union(*(direct[parent] for parent in parents)) - totals[key]
        legacy = (
            set().union(
                *(
                    direct[n]
                    for n in nodes
                    if nodes[n]["level"] == "legacy_family"
                    and set(nodes[n]["parents"]) & parents
                )
            )
            - totals[key]
        )
        counts = Counter(findings[eid]["review_status"] for eid in totals[key])
        views[key] = {
            "direct_evidence_ids": sorted(direct[key]),
            "descendant_evidence_ids": sorted(totals[key] - direct[key]),
            "broader_evidence_ids": sorted(broader),
            "total": len(totals[key]),
            "legacy_scope_evidence_ids": sorted(legacy),
            "reviewed_kept": counts["reviewed_kept"],
            "pending": counts["pending"],
            "held": counts["held"],
            "rejected": counts["rejected"],
            "retained_total": len(totals[key]) - counts["rejected"],
        }
    return {
        "format": "ruralscan.evidence-hierarchy.v1",
        "method_revision": packet["method_revision"],
        "transition_sha256": packet["sha256"],
        "nodes": nodes,
        "findings": findings,
        "coverage": views,
        "note": "Coverage preserves review state; counts are not synthesis eligibility or independent-study counts.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--scope",
        required=True,
        help="practice:, family:, subpractice:, group: or legacy_family: ID",
    )
    parser.add_argument("--lane", choices=sorted(set(LANES.values())))
    args = parser.parse_args()
    verify_adoption(args.root)
    result = coverage(
        args.root,
        table((args.root / EV).read_bytes()),
        table((args.root / LOG).read_bytes()),
        lane=args.lane,
    )
    require(result and args.scope in result["nodes"], "Unknown or unavailable scope")
    view = result["coverage"][args.scope]
    ids = set(
        view["direct_evidence_ids"]
        + view["descendant_evidence_ids"]
        + view["broader_evidence_ids"]
        + view["legacy_scope_evidence_ids"]
    )
    print(
        json.dumps(
            {
                "scope": result["nodes"][args.scope],
                "coverage": view,
                "findings": {eid: result["findings"][eid] for eid in sorted(ids)},
                "method_revision": result["method_revision"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
