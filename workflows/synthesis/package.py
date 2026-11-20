"""Export only current accepted effects. Historical and held rows are never a fallback."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .core import TABLES, digest, encoded, policy, require


def build(queue, destination):
    status = queue.get("effect_synthesis", {}).get("rows", [])
    active = [s for s in status if s["status"] == "accepted"]
    require(active, "No current accepted AI synthesis outputs to package")
    # No partly stale/held release: the caller must resolve or explicitly replace those decisions.
    require(
        all(s["status"] == "accepted" for s in status),
        "Held or stale accepted outputs prevent publication",
    )
    grouped, provenance = {}, []
    for entry in active:
        p, t, rid = entry["practice"], entry["table"], entry["record_id"]
        matches = [r for r in queue["recipes"][p][TABLES[t]] if r["record_id"] == rid]
        grouped.setdefault((p, t), [])
        if entry.get("action") == "withdraw":
            require(
                not matches and entry["row_sha256"] is None,
                "Withdrawn row has reappeared",
            )
        else:
            require(
                len(matches) == 1 and digest(matches[0]) == entry["row_sha256"],
                "Accepted output differs from scientific decision",
            )
            grouped[(p, t)].append(matches[0])
        provenance.append(entry)
    # Validate authored weighting completeness, never calculate missing weights.
    groups = {}
    for (practice, table), rows in grouped.items():
        if table != "T3":
            continue
        for r in rows:
            if r.get("asset_risk_weight") is not None:
                key = (
                    practice,
                    r.get("suitability_family_id"),
                    r.get("farming_system"),
                    r.get("scope_type"),
                    r.get("scope_id"),
                )
                groups.setdefault(key, []).append(r)
    for rows in groups.values():
        hazards = [r["hazard_type"] for r in rows]
        require(
            len(hazards) == len(set(hazards))
            and set(hazards) == set(policy()["asset_weight_hazards"]),
            "Authored asset weights need the complete hazard set",
        )
        require(
            abs(sum(r["asset_risk_weight"] for r in rows) - 1) <= 1e-6,
            "Authored asset weights must sum to one",
        )
    require(not destination.exists(), "Select a new output directory")
    files = {
        f"{p}/{t}.json": encoded(sorted(rows, key=lambda r: r["record_id"]))
        for (p, t), rows in grouped.items()
    }
    manifest = {
        "format": "ruralscan.accepted-effects.v1",
        "files": {name: digest(data) for name, data in sorted(files.items())},
        "provenance": provenance,
        "scientific_synthesis": "ai_authored_human_accepted",
    }
    with TemporaryDirectory(dir=destination.parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        for name, data in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (stage / "manifest.json").write_bytes(encoded(manifest))
        os.rename(stage, destination)
    return digest(encoded(manifest))
