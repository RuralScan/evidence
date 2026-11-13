"""Private worker running only the producer's own compiler against its pinned inputs."""

import json
from pathlib import Path
import sys

source = Path(sys.argv[1])
sys.path.insert(0, str(source / "src"))
from nbs_ruralscan.recipe import t3t6_build as build

practice, evidence_id = sys.argv[2:]
inputs = build.load_inputs(
    practice, [], inputs=build.T3T6BuildInputs.from_root(source, practice)
)


def run(units):
    tables = build.synthesise(practice, dict(inputs, units=units))
    return {
        r["record_id"]: [
            r.get("effect_direction")
            or r.get("asset_sensitivity")
            or r.get("mitigation_potential")
            or None,
            r.get("effect_confidence") or r.get("confidence") or None,
        ]
        for table in ("T3", "T6")
        for r in tables[table]
    }


all_units = inputs["units"]
subset = [u for u in all_units if u.evidence_id != evidence_id]
if len(subset) + 1 != len(all_units):
    raise ValueError("Expected exactly one removed unit")
print(json.dumps({"baseline": run(all_units), "without": run(subset)}))
