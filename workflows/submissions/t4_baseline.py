"""Read frozen T4 records; scientific synthesis belongs to the agent proposal route."""

import json
from registers import blob, content_digest
from git_snapshot import require

REVISION = "97dd21060d931b16464155d770c7eb7dd71c385a"
PATH = "publication/review-queue.json"
SHA256 = "cb3cd472a895a527049c1a783fcc5f0499259df29ce7ee30fe64f287f6b3ae16"
TABLE = "T4_suitability_mappings"


def load(root):
    data = blob(root, REVISION, PATH)
    require(content_digest(data) == SHA256, "T4 baseline checksum differs")
    recipes = json.loads(data)["recipes"]
    status = {
        "status": "historical_baseline",
        "repository": "RuralScan/evidence",
        "revision": REVISION,
        "path": PATH,
        "sha256": SHA256,
        "current_evidence_applied": False,
        "needs_agent_synthesis": True,
    }
    return {name: tables[TABLE] for name, tables in recipes.items()}, status
