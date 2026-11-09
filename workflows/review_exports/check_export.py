"""Rehearse a browser review CSV against disposable copies of committed records."""

import argparse
from collections import Counter, defaultdict
from contextlib import redirect_stdout
import csv
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from git_snapshot import git, require, revision, snapshot  # noqa: E402
from review_preview.preview import ENGINE, EV, LOG, REPO, read_copy  # noqa: E402

ROW_LOG = "pipeline/metrics/row_review_log.csv"
SCRIPTS = {
    "evidence": "scripts/apply-review-export.py",
    "rows": "scripts/apply-row-review-export.py",
}
TABLES = {
    "T3": "T3_nbs_hazard_farming.csv",
    "T6": "T6_nbs_scorecard.csv",
    "T6E": "T6E_economic_profile.csv",
}
PUBLIC_FIXTURE = HERE.parent / "review_preview/example/records"


def csv_rows(raw):
    reader = csv.DictReader(
        io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True
    )
    header = reader.fieldnames or []
    require(len(set(header)) == len(header), "Duplicate CSV column names")
    rows = list(reader)
    require(
        all(None not in row and None not in row.values() for row in rows),
        "Malformed CSV row",
    )
    return set(header), rows


def export_rows(raw):
    header, rows = csv_rows(raw)
    common = {"batch", "decision", "reason", "note", "reviewer", "date"}
    if header in (common | {"evidence_id"}, common | {"evidence_id", "picos_flags"}):
        if raw.startswith(b"\xef\xbb\xbf"):
            # The native evidence importer uses plain UTF-8 and ignores batch.
            # A BOM on any other header could change how it interprets a row.
            native_header = next(
                csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
            )
            require(
                native_header[0] == "batch",
                "Evidence CSV with a BOM must start with the batch column",
            )
        return "evidence", rows
    require(
        header == common | {"record_id", "nbs_id", "table"},
        "Expected an evidence or compiled-row browser CSV",
    )
    return "rows", rows


def pinned(repo, *args):
    return git("--no-lazy-fetch", "--no-replace-objects", *args, cwd=repo)


def missing_compiled_ids(rows, repo, pin):
    requested = defaultdict(set)
    for row in rows:
        requested[(row["nbs_id"].strip(), row["table"].strip())].add(
            row["record_id"].strip()
        )
    missing = 0
    for (practice, table), ids in requested.items():
        available = set()
        if re.fullmatch(r"[a-z0-9_]+", practice) and table in TABLES:
            name = f"schema/recipes/{practice}/{TABLES[table]}"
            if pinned(repo, "ls-tree", "--full-tree", pin, "--", name):
                _, compiled = csv_rows(pinned(repo, "show", f"{pin}:{name}"))
                available = {row["record_id"] for row in compiled}
        missing += len(ids - available)
    return missing


def evidence_checks(rows, api, register):
    known = {row["evidence_id"] for row in csv_rows(register)[1]}
    votes = {}
    skipped = 0
    valid = 0
    for row in rows:
        decision = api["MAP"].get(row["decision"].strip().lower())
        if (
            decision is None
            or decision == "drop"
            and row["reason"].strip() not in api["REASON_CODES"]
        ):
            skipped += 1
            continue
        valid += 1
        votes[(row["evidence_id"], row["reviewer"].strip() or "reviewer")] = decision
    by_id = defaultdict(set)
    for (eid, _), decision in votes.items():
        by_id[eid].add(decision)
    return {
        "skipped_input_rows": skipped,
        "superseded_reviewer_rows": valid - len(votes),
        "target_ids_missing_from_register": len(by_id.keys() - known),
        "evidence_ids_with_disagreeing_reviewers": sum(
            len(values) > 1 for values in by_id.values()
        ),
    }


def private_file(path):
    require(path.is_file() and not path.is_symlink(), "Choose a regular CSV export")
    folder = path.resolve().parent
    require(
        all(
            not (p / ".git").exists() and p.name != ".git"
            for p in (folder, *folder.parents)
        ),
        "Use a private copy of the export outside Git",
    )
    return path.read_bytes()


def rehearse(code, raw, records, repo, pin, work, example):
    kind, rows = export_rows(raw)
    api = runpy.run_path(str(code / SCRIPTS[kind]))
    files = [EV, LOG] if kind == "evidence" else [ROW_LOG]
    state = work / kind
    for name in files:
        if example and name == ROW_LOG:
            data = (",".join(api["LOG_COLS"]) + "\n").encode()
        else:
            data = read_copy(records, name)
        require(data is not None, f"Required snapshot file missing: {name}")
        if not example:
            require(
                data == pinned(repo, "show", f"{pin}:{name}"),
                f"Snapshot differs from Git: {name}",
            )
        path = state / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    export = work / f"{kind}.csv"
    export.write_bytes(raw)
    log = state / files[-1]
    start = log.read_bytes()
    report = {"kind": kind, "input_rows": len(rows)}
    if kind == "evidence":
        report.update(evidence_checks(rows, api, (state / EV).read_bytes()))

        def run():
            # Native importer prints reviewer labels and notes; the receipt contains counts only.
            with open(os.devnull, "w") as quiet, redirect_stdout(quiet):
                require(
                    api["main"]([str(export), "--root", str(state)]) == 0,
                    "Evidence import failed",
                )
    else:
        report["target_ids_missing_from_recipe_tables"] = missing_compiled_ids(
            rows, repo, pin
        )

        def run():
            return api["apply_export"](export, log)

    first = run()
    first_bytes = {name: (state / name).read_bytes() for name in files}
    after = first_bytes[files[-1]]
    require(after.startswith(start), "Original review log changed")
    before_rows, after_rows = csv_rows(start)[1], csv_rows(after)[1]
    added = after_rows[len(before_rows) :]
    report["first_pass_events"] = dict(Counter(row["decision"] for row in added))
    if kind == "rows":
        report["skipped_input_rows"] = len(first["skipped"])
        report["duplicate_event_keys"] = len(rows) - len(added) - len(first["skipped"])
    run()
    require(log.read_bytes().startswith(after), "First-pass history changed on retry")
    report["retry_new_events"] = len(csv_rows(log.read_bytes())[1]) - len(after_rows)
    report["retry_byte_identical"] = all(
        (state / name).read_bytes() == old for name, old in first_bytes.items()
    )
    return report


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    group = cli.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--example", action="store_true", help="Rehearse both example CSVs"
    )
    group.add_argument("--csv", type=Path, help="Private copy of one browser export")
    cli.add_argument(
        "--records",
        type=Path,
        help="Exported seven-table or review-support revision directory",
    )
    cli.add_argument(
        "--ciat-repo", type=Path, help="Local Git clone for the pinned engine and data"
    )
    args = cli.parse_args()
    if (
        args.example
        and args.records
        or args.csv
        and not (args.records and args.ciat_repo)
    ):
        cli.error("Use --example, or supply --csv, --records and --ciat-repo together")
    if args.example:
        records = PUBLIC_FIXTURE
        pin = ENGINE
        inputs = [
            (HERE / "example" / filename).read_bytes()
            for filename in ("evidence.csv", "rows.csv")
        ]
    else:
        records = args.records.resolve(strict=True)
        require(
            records.is_dir()
            and all(
                not (p / ".git").exists() and p.name != ".git"
                for p in (records, *records.parents)
            ),
            "Select a private snapshot outside Git",
        )
        pin = revision(records.name)
        require(
            pinned(args.ciat_repo, "cat-file", "-t", pin).strip() == b"commit",
            "Expected a committed revision",
        )
        inputs = [private_file(args.csv)]
    with TemporaryDirectory(prefix="ruralscan-browser-export-") as directory:
        work = Path(directory).resolve()
        code = work / "ciat"
        patterns = ["/src/", *("/" + path for path in SCRIPTS.values())]
        if args.example:
            patterns += [
                "/schema/recipes/agroforestry/" + TABLES["T3"],
                "/schema/recipes/wetland_management/" + TABLES["T6"],
            ]
        snapshot(code, REPO, ENGINE, patterns, args.ciat_repo)
        reports = [
            rehearse(
                code, raw, records, args.ciat_repo or code, pin, work, args.example
            )
            for raw in inputs
        ]
    print(
        json.dumps(
            {
                "engine_revision": ENGINE,
                "records_revision": None if args.example else pin,
                "example": args.example,
                "exports": reports,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        OSError,
        KeyError,
        csv.Error,
        subprocess.CalledProcessError,
    ) as exc:
        sys.exit(f"Export preview failed: {exc}")
