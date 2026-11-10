"""Match the Haiti notebook's scoring package to its rows in the candidate workbook."""

import csv
import hashlib
import io
import json

from git_snapshot import git, require, revision


def handoff(source, release, source_revision, lock):
    raw = git(
        "show",
        f"{source_revision}:handoff/{lock['package']}/run_contract.json",
        cwd=source,
    )
    require(
        hashlib.sha256(raw).hexdigest() == lock["contract_sha256"],
        "Haiti runtime scoring contract differs from its pin",
    )
    policy_id = lock["policy_id"]
    policies = json.loads(raw)["approved_policies"]
    (policy,) = (p for p in policies if p["policy_id"] == policy_id)
    settings = csv.DictReader(
        io.StringIO(release.setting("agroforestry", "T4_run_policy.csv").decode())
    )
    criteria = match_criteria(
        [r for r in settings if r["policy_id"] == policy_id], policy["criteria"]
    )
    runtime = "https://github.com/RuralScan/runtime/blob/" + revision(
        lock["runtime_revision"]
    )
    method = "https://github.com/RuralScan/method/blob/" + revision(
        lock["guide_revision"]
    )
    return {
        "criteria": criteria,
        "package": lock["package"],
        "guide": method + "/handbook/implement-a-scan.md",
        "notebook": runtime + "/notebooks/01_agroforestry.ipynb",
    }


def match_criteria(settings, criteria):
    indexed = {r["rule_id"]: r for r in settings}
    require(
        len(indexed) == len(settings) == len(criteria)
        and indexed
        and set(indexed) == {c["rule_id"] for c in criteria},
        "Haiti and candidate criterion inventories differ",
    )
    for criterion in criteria:
        row = indexed[criterion["rule_id"]]
        require(
            row["function_id"] == criterion["function_id"]
            and row["function_fingerprint"] == criterion["function_fingerprint"]
            and float(row["criterion_weight"]) == criterion["weight"],
            f"Haiti function or weight differs for {row['rule_id']}",
        )
    return [{"id": c["rule_id"], "weight": c["weight"]} for c in criteria]
