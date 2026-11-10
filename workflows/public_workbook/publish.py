"""Package the public record projection as one portable HTML file."""

import hashlib
import json
from pathlib import Path

from git_snapshot import require
from recipe_index import write_index

from .data import build_data


HERE = Path(__file__).resolve().parent
PUBLISHED = HERE.parents[1] / "publication" / "workbook"


def render(template, data):
    marker = "@@DATA@@"
    require(template.count(marker) == 1, "Expected one publication data element")
    encoded = json.dumps(
        data, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    # A citation containing HTML is text, including inside a script data block.
    encoded = (
        encoded.replace("&", r"\u0026").replace("<", r"\u003c").replace(">", r"\u003e")
    )
    return template.replace(marker, encoded)


def publish(source, release, summary, output, check):
    data = build_data(source, release, summary)
    html = render((HERE / "workbook.html").read_text(encoding="utf-8"), data)
    encoded = html.encode("utf-8")
    if check:
        require(
            (PUBLISHED / "index.html").read_bytes() == encoded,
            "Public workbook differs from pinned inputs or template",
        )
    else:
        write_index(output, {"index.html": html})
    rows = data["rows"]
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "analytical_rows": len(rows),
        "rows_without_direct_evidence": sum(not row["evidence_ids"] for row in rows),
        "direct_links": sum(len(row["evidence_ids"]) for row in rows),
        "distinct_direct_claims": len(
            {eid for row in rows for eid in row["evidence_ids"]}
        ),
        "additional_mapping_links": sum(len(row["context_ids"]) for row in rows),
        "active_claims": len(data["claims"]),
        "registered_sources": len(data["sources"]),
        "search_records": len(data["searches"]),
    }
