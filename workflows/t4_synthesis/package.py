"""Package exact accepted mappings; no historical fallback or runtime implementation."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from .core import TABLE, digest, encoded, require


def build(queue, destination):
    statuses = queue.get("t4_synthesis", {}).get("rows", [])
    require(statuses, "No accepted T4 proposals to package")
    require(
        all(s["status"] == "accepted" for s in statuses),
        "Held or stale T4 output blocks packaging",
    )
    grouped = {}
    for state in statuses:
        practice, rid = state["practice"], state["record_id"]
        rows = [r for r in queue["recipes"][practice][TABLE] if r["mapping_id"] == rid]
        grouped.setdefault(practice, [])
        if state["action"] == "withdraw":
            require(
                not rows and state["row_sha256"] is None, "Withdrawn mapping reappeared"
            )
        else:
            require(
                len(rows) == 1 and digest(rows[0]) == state["row_sha256"],
                "Accepted mapping bytes differ",
            )
            grouped[practice].append(rows[0])
    files = {
        f"{practice}/T4.json": encoded(sorted(rows, key=lambda r: r["mapping_id"]))
        for practice, rows in grouped.items()
    }
    manifest = dict(
        format="ruralscan.accepted-t4.v1",
        scientific_synthesis="ai_authored_human_accepted",
        partial_mapping_package=True,
        runtime_implemented=False,
        files={name: digest(raw) for name, raw in sorted(files.items())},
        provenance=statuses,
    )
    require(not destination.exists(), "Select a new output directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temp:
        stage = Path(temp) / "package"
        stage.mkdir()
        for name, raw in files.items():
            p = stage / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        (stage / "manifest.json").write_bytes(encoded(manifest))
        os.rename(stage, destination)
    return digest(encoded(manifest))
