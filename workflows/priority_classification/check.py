"""Validate staging packets, without registering sources, voting or accepting rules."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

FIELDS = {"format", "packet_id", "status", "scope", "variables", "source", "reported",
          "interpretation_limit", "registration_blocker", "canonical_source_id", "canonical_evidence_ids"}
SOURCE = {"url", "title", "retrieved_on", "artifact_sha256", "media_type", "locator_type", "locator"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate(packet):
    require(set(packet) == FIELDS, "Unexpected packet fields; decisions and scores belong in method")
    require(packet["format"] == "ruralscan.priority-source-packet.v1", "Unknown format")
    require(packet["status"] == "unreviewed_staging", "Staging cannot assert review or acceptance")
    require(packet["scope"] == "cross_cutting_priority_classification", "Wrong scope")
    require(re.fullmatch(r"[a-z][a-z0-9_]*", packet["packet_id"]), "Invalid packet ID")
    require(isinstance(packet["variables"], list) and packet["variables"] and
            len(set(packet["variables"])) == len(packet["variables"]) and
            all(re.fullmatch(r"[a-z][a-z0-9_]*", v) for v in packet["variables"]), "Invalid variables")
    source = packet["source"]
    require(set(source) == SOURCE, "Invalid source fields")
    require(all(isinstance(v, str) and v.strip() for v in source.values()), "Missing source identity or locator")
    require(source["url"].startswith("https://"), "Source needs HTTPS URL")
    require(re.fullmatch(r"[0-9a-f]{64}", source["artifact_sha256"]), "Invalid source digest")
    require(source["media_type"] in {"application/pdf", "text/html"}, "Unsupported source adapter")
    require(source["locator_type"] == ("pdf_page" if source["media_type"] == "application/pdf" else "section"), "Wrong locator semantics")
    require(isinstance(packet["reported"], dict) and packet["reported"], "No source observations")
    require(packet["interpretation_limit"] and packet["registration_blocker"], "Missing limits")
    require(packet["canonical_source_id"] is None and packet["canonical_evidence_ids"] == [], "Staged IDs must not impersonate SRC/EV records")
    return sha256((json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=Path(__file__).parent / "packets")
    args = parser.parse_args()
    seen = set()
    for path in sorted(args.directory.glob("*.json")):
        packet = json.loads(path.read_text())
        digest = validate(packet)
        require(packet["packet_id"] not in seen, "Duplicate packet ID")
        seen.add(packet["packet_id"])
        print(packet["packet_id"], digest)
    require(seen, "No packets")


if __name__ == "__main__":
    main()
