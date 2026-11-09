# /// script
# requires-python = ">=3.12"
# dependencies = ["pymupdf==1.27.2.3"]
# ///

"""Inspect a verified PDF and stage source-anchored proposals for evidence review."""

import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acquisition"))
try:
    import run as acquisition
finally:
    sys.path.pop(0)
from claims import build_unit  # noqa: E402


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique_fields(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"Duplicate JSON field: {key}")
        obj[key] = value
    return obj


def clean_text(value):
    require(isinstance(value, str) and value.strip(), "Expected nonempty text")
    return " ".join(value.split())


def page_text(pdf, number):
    require(
        type(number) is int and 1 <= number <= len(pdf), "Page outside verified PDF"
    )
    return pdf[number - 1].get_text()


def passage(pdf, anchor):
    number = anchor["page"]
    page = " ".join(page_text(pdf, number).split())
    first, last = clean_text(anchor["start"]), clean_text(anchor["end"])
    require(
        page.count(first) == 1,
        f"Opening anchor missing or ambiguous on PDF page {number}",
    )
    start = page.index(first)
    if first == last:
        return first
    tail = page[start + len(first) :]
    require(
        tail.count(last) == 1,
        f"Closing anchor missing or ambiguous on PDF page {number}",
    )
    return page[start : start + len(first) + tail.index(last) + len(last)]


def checked_source(args):
    plan = acquisition.read_plan(args.plan)
    candidate = acquisition.selected(args.candidates, plan["candidate_id"])
    receipt = acquisition.check(args.bundle, plan, candidate)
    require(
        receipt["status"] == "acquired" and receipt["kind"] == "pdf",
        "Page extraction requires a verified acquired PDF",
    )
    sid = receipt["source_id"]
    data = (args.bundle / "cache" / (sid + ".pdf")).read_bytes()
    require(
        hashlib.sha256(data).hexdigest() == receipt["artifact"]["sha256"],
        "Artifact changed after verification",
    )
    return pymupdf.open(stream=data, filetype="pdf"), receipt, candidate


def screened_practice(candidate, path):
    if candidate.get("nbs_id"):
        return candidate["nbs_id"]
    # Earlier discovery bundles kept practice only in the report scope line.
    report = path.with_name("report.md")
    require(
        report.is_file(),
        "Missing legacy discovery scope. Supply the original report.md or restage discovery.",
    )
    pattern = r"^([A-Za-z0-9_.-]+) / (.+?) / (T[346]) / (stock|updated_lit|grey|tool)\nSearch closed "
    matches = re.findall(
        pattern,
        report.read_text(encoding="utf-8").split("## Verbatim queries")[0],
        re.M,
    )
    require(len(matches) == 1, "Missing or ambiguous legacy discovery scope")
    practice, family, table, process = matches[0]
    require(
        table == candidate["tables"]
        and process == candidate["process"]
        and (family == "whole practice" or family in candidate["families"]),
        "Legacy report and candidate disagree",
    )
    return practice


def inspect(pdf, args):
    if args.page is not None:
        print(f"PDF page {args.page} of {len(pdf)}")
        print(page_text(pdf, args.page))
        return
    terms = clean_text(args.find).casefold()
    hits = [
        i + 1
        for i, page in enumerate(pdf)
        if terms in " ".join(page.get_text().casefold().split())
    ]
    print(
        "Matching PDF pages:",
        ", ".join(map(str, hits)) if hits else "none in text layer",
    )


def stage(pdf, receipt, candidate, spec):
    sid = receipt["source_id"]
    require(
        spec["source_id"] == sid
        and spec["artifact_sha256"] == receipt["artifact"]["sha256"],
        "Extraction worksheet targets a different source or edition",
    )
    scope = spec["scope"]
    require(scope["nbs_id"] == candidate["nbs_id"], "Practice outside screened scope")
    role_tables = {
        "structural_suitability": {"T4"},
        "asset_vulnerability": {"T3"},
        "nbs_effect": {"T3", "T6"},
        "operational_risk": {"T3"},
    }
    require(
        role_tables[scope["use_role"]] & set(candidate["tables"].split("|")),
        "Role outside screened table scope",
    )
    require(
        not candidate["families"]
        or scope["suitability_family_id"] in candidate["families"],
        "Family outside screened scope",
    )
    for key in ("nbs_id", "suitability_family_id", "variable", "use_role"):
        clean_text(scope[key])
    clean_text(spec["coverage"])
    pages = spec["inspected_pdf_pages"]
    require(
        isinstance(pages, list)
        and pages
        and all(type(p) is int and 1 <= p <= len(pdf) for p in pages)
        and len(set(pages)) == len(pages),
        "Invalid inspected PDF pages",
    )
    purpose = spec["source_purpose"]
    require(
        purpose["disposition"] in ("pass", "hold", "exclude"),
        "Invalid source-purpose decision",
    )
    clean_text(purpose["reason"])

    def locate(anchor):
        require(anchor["page"] in pages, "Anchor outside inspected pages")
        return passage(pdf, anchor)

    require(
        set(purpose) <= {"disposition", "reason", "anchor"},
        "Source purpose accepts only disposition, reason and anchor",
    )
    gate = dict(purpose)
    if "anchor" in gate:
        gate["quote"] = locate(gate["anchor"])
    require(
        gate["disposition"] != "pass" or "quote" in gate,
        "Purpose pass needs a located source passage",
    )
    items = spec["inventory"]
    require(
        isinstance(items, list) and items,
        "List inspected claims or explicit holds/exclusions",
    )
    units, inventory, ids = [], [], set()
    for item in items:
        disposition = item["disposition"]
        require(
            disposition in ("extract", "hold", "exclude", "referral"),
            "Invalid inventory disposition",
        )
        clean_text(item["reason"])
        require(
            type(item["page"]) is int and item["page"] in pages,
            "Inventory page outside scope",
        )
        entry = {
            "page": item["page"],
            "disposition": disposition,
            "reason": item["reason"],
        }
        if disposition == "extract":
            require(
                gate["disposition"] == "pass"
                and item["anchor"]["page"] == item["page"],
                "Extraction requires a passed purpose gate and the specified page",
            )
            quote = locate(item["anchor"])
            unit = build_unit(item["draft"], scope, sid, quote, item["page"])
            eid = unit["evidence_id"]
            require(eid not in ids, "Duplicate evidence ID")
            ids.add(eid)
            entry["evidence_id"] = eid
            units.append(unit)
        else:
            require(
                "draft" not in item,
                "Unresolved or excluded item cannot carry a staged draft",
            )
        inventory.append(entry)
    record = {
        "source_id": sid,
        "artifact_sha256": spec["artifact_sha256"],
        "scope": scope,
        "coverage": spec["coverage"],
        "inspected_pdf_pages": pages,
        "source_purpose": gate,
        "inventory": inventory,
        "worksheet_sha256": acquisition.input_hash(spec),
        "unit_count": len(units),
    }
    return units, record


def save(out, units, record):
    out.mkdir(mode=0o700)
    try:
        for name, value in (("staging.json", units), ("inventory.json", record)):
            (out / name).write_text(acquisition.json_text(value), encoding="utf-8")
    except BaseException:
        shutil.rmtree(out)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="action", required=True)
    read = subs.add_parser("inspect")
    write = subs.add_parser("stage")
    for cmd in (read, write):
        cmd.add_argument("--candidates", required=True, type=Path)
        cmd.add_argument("--plan", required=True, type=Path, help="Acquisition plan")
        cmd.add_argument(
            "--bundle", required=True, type=Path, help="Verified acquisition bundle"
        )
    loc = read.add_mutually_exclusive_group(required=True)
    loc.add_argument("--find")
    loc.add_argument("--page", type=int)
    write.add_argument("--worksheet", required=True, type=Path)
    write.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    pdf, receipt, candidate = checked_source(args)
    with pdf:
        if args.action == "inspect":
            inspect(pdf, args)
            return
        spec = json.loads(args.worksheet.read_bytes(), object_pairs_hook=unique_fields)
        acquisition.input_hash(
            spec
        )  # Reject non-finite numbers throughout the worksheet.
        candidate = dict(
            candidate, nbs_id=screened_practice(candidate, args.candidates)
        )
        units, record = stage(pdf, receipt, candidate, spec)
        save(args.out, units, record)
        print(
            f"{len(units)} proposed evidence unit(s) staged for {receipt['source_id']} in {args.out}"
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as exc:
        sys.exit(f"Extraction stopped: {exc}")
