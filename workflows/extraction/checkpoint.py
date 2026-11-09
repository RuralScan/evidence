"""Preserve selected staged extraction files and reconcile their IDs against pinned Git."""

import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import sys
import unicodedata
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from handoff import (
    EV,
    anchor,
    changed_fields,
    finite_float,
    invalid_number,
    overlap,
    scientific_fields,
    unique_object,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_snapshot.rehearse import destination, git  # noqa: E402
from git_snapshot import require, revision  # noqa: E402


def parse(raw):
    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_constant=invalid_number,
        parse_float=finite_float,
    )


def filename(value):
    path = PurePosixPath(value)
    require(
        bool(path.parts)
        and path.as_posix() == value
        and not path.is_absolute()
        and "\\" not in value
        and not re.search(r'[<>:"|?*\x00-\x1f]', value)
        and all(
            part.casefold() not in {"..", ".git"}
            and not part.endswith((".", " "))
            and not PureWindowsPath(part).is_reserved()
            for part in path.parts
        )
        and path.suffix.lower() == ".json",
        "Use relative JSON filenames inside the staging directory",
    )
    return value


def select(root, units, companions):
    root = root.resolve(strict=True)
    require(root.is_dir(), "Staging directory required")
    kinds = {}
    for kind, names in (("units", units), ("companion", companions)):
        for name in names:
            name = filename(name)
            require(name not in kinds, f"File selected more than once: {name}")
            kinds[name] = kind
    for name in units:
        if PurePosixPath(name).name == "staging.json":
            sibling = str(PurePosixPath(name).with_name("inventory.json"))
            if os.path.lexists(root / sibling):
                require(
                    kinds.get(sibling, "companion") == "companion",
                    "Inventory is a companion file",
                )
                kinds[sibling] = "companion"
    require(
        len({unicodedata.normalize("NFC", name).casefold() for name in kinds})
        == len(kinds),
        "Ambiguous case in filenames",
    )
    data = {}
    for name in kinds:
        path = root / name
        require(
            path.resolve(strict=True) == path and stat.S_ISREG(path.stat().st_mode),
            f"Expected a regular file inside staging directory: {name}",
        )
        data[name] = path.read_bytes()
    return kinds, data


def register(repo, pin):
    revision(pin)
    require(
        git("cat-file", "-t", pin, cwd=repo).strip() == b"commit", "Expected a commit"
    )
    raw = git("show", f"{pin}:{EV}", cwd=repo)
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""))
    known = {}
    passages = defaultdict(list)
    for row in reader:
        eid = row["evidence_id"]
        require(
            eid and eid not in known,
            "Duplicate or empty evidence ID in pinned register",
        )
        known[eid] = row
        passages[anchor(row)].append((eid, row["quote"]))
    return known, passages


def inspect(repo, pin, kinds, data):
    known, passages = register(repo, pin)
    files = {}
    proposals = []
    for name, kind in kinds.items():
        info = {
            "kind": kind,
            "sha256": sha256(data[name]).hexdigest(),
            "bytes": len(data[name]),
        }
        files[name] = info
        if kind == "companion":
            continue
        try:
            items = parse(data[name])
        except (ValueError, RecursionError):
            info["status"] = "malformed_json"
            continue
        if not isinstance(items, list):
            info["status"] = "expected_unit_list"
            continue
        info["status"] = "inspected" if items else "empty_unit_list"
        info["units"] = []
        for i, unit in enumerate(items, 1):
            entry = {"position": i}
            info["units"].append(entry)
            if isinstance(unit, dict):
                entry["staged_review_fields"] = []
                if (
                    unit.get("reviewer_ok") is not None
                    and unit.get("reviewer_ok") is not False
                ):
                    entry["staged_review_fields"].append("reviewer_ok")
                if unit.get("review_state"):
                    entry["staged_review_fields"].append("review_state")
            eid = unit.get("evidence_id") if isinstance(unit, dict) else None
            if not isinstance(eid, str) or not eid.strip():
                entry["status"] = "invalid_identity"
                continue
            entry["evidence_id"] = eid
            proposals.append((unit, entry))
    frequencies = Counter(entry["evidence_id"] for _, entry in proposals)
    staged_passages = defaultdict(list)
    for unit, entry in proposals:
        if isinstance(unit.get("quote"), str) and unit["quote"].strip():
            staged_passages[anchor(unit)].append((entry["evidence_id"], unit["quote"]))
    for unit, entry in proposals:
        eid = entry["evidence_id"]
        entry["repeated_id"] = frequencies[eid] > 1
        if not isinstance(unit.get("quote"), str) or not unit["quote"].strip():
            entry["status"] = "missing_quote"
            continue
        row = known.get(eid)
        if row is None:
            entry["status"] = "unregistered_id"
        else:
            differences = changed_fields(scientific_fields(row), unit)
            entry["status"] = (
                "registered_fields_differ" if differences else "registered_fields_match"
            )
            entry["changed_fields"] = differences
            entry["stored_as_dropped"] = row.get("review_state") == "dropped"
        scope = anchor(unit)

        def neighbours(candidates):
            return sorted(
                {
                    other
                    for other, text in candidates
                    if other != eid and overlap(text, unit["quote"])
                }
            )

        entry["other_registered_passage_ids"] = neighbours(passages[scope])
        entry["other_staged_passage_ids"] = neighbours(staged_passages[scope])
    return {
        "format_version": 1,
        "revision": pin,
        "unit_file_order": [n for n, k in kinds.items() if k == "units"],
        "files": files,
    }


def summary(report):
    unit_files = [v for v in report["files"].values() if v["kind"] == "units"]
    entries = [e for f in unit_files for e in f.get("units", [])]
    return {
        "revision": report["revision"],
        "unit_files": len(unit_files),
        "companions": len(report["files"]) - len(unit_files),
        "file_statuses": dict(Counter(f["status"] for f in unit_files)),
        "unit_occurrences": len(entries),
        "distinct_ids": len({e["evidence_id"] for e in entries if "evidence_id" in e}),
        "unit_statuses": dict(Counter(e["status"] for e in entries)),
        "occurrences_setting_review_fields": sum(
            bool(e.get("staged_review_fields")) for e in entries
        ),
        "distinct_repeated_ids": len(
            {e["evidence_id"] for e in entries if e.get("repeated_id")}
        ),
        "occurrences_with_other_passage_ids": sum(
            bool(
                e.get("other_registered_passage_ids")
                or e.get("other_staged_passage_ids")
            )
            for e in entries
        ),
    }


def capture(args):
    bundle = destination(args.bundle, args.ciat_repo)
    kinds, data = select(args.staging_dir, args.units, args.companion)
    report = inspect(args.ciat_repo, args.revision, kinds, data)
    with TemporaryDirectory(dir=bundle.parent) as temp:
        stage = Path(temp) / "checkpoint.zip"
        with ZipFile(stage, "x", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "receipt.json", json.dumps(report, indent=2, sort_keys=True) + "\n"
            )
            for name, raw in data.items():
                archive.writestr("staging/" + name, raw)
        require(
            (kinds, data) == select(args.staging_dir, args.units, args.companion),
            "Staging changed while capturing",
        )
        stage.chmod(0o400)
        digest = sha256(stage.read_bytes()).hexdigest()
        os.link(stage, bundle)
    return {"archive_sha256": digest, **summary(report)}


def verify(args):
    require(
        re.fullmatch("[0-9a-f]{64}", args.sha256), "Supply the SHA-256 from capture"
    )
    with args.bundle.open("rb") as handle:
        digest = sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
        require(digest.hexdigest() == args.sha256, "Archive checksum differs")
        handle.seek(0)
        with ZipFile(handle) as archive:
            receipt = parse(archive.read("receipt.json"))
            require(receipt["format_version"] == 1, "Unsupported checkpoint")
            kinds = {filename(name): v["kind"] for name, v in receipt["files"].items()}
            require(
                set(kinds.values()) <= {"units", "companion"}
                and "units" in kinds.values(),
                "Invalid checkpoint file roles",
            )
            order = receipt["unit_file_order"]
            require(
                len(order) == len(set(order))
                and set(order) == {n for n, k in kinds.items() if k == "units"},
                "Invalid unit-file order",
            )
            kinds = {
                **{n: "units" for n in order},
                **{n: k for n, k in kinds.items() if k == "companion"},
            }
            names = ["receipt.json", *("staging/" + n for n in kinds)]
            require(
                sorted(archive.namelist()) == sorted(names), "Archive inventory differs"
            )
            data = {n: archive.read("staging/" + n) for n in kinds}
    pinned = inspect(args.ciat_repo, receipt["revision"], kinds, data)
    require(pinned == receipt, "Pinned checkpoint receipt differs")
    result = {"captured": summary(pinned)}
    current = inspect(args.ciat_repo, args.at, kinds, data) if args.at else pinned
    if args.at:
        result["compared"] = summary(current)
    if args.details:
        result["unit_file_order"] = current["unit_file_order"]
        result["files"] = current["files"]
    if args.export_to:
        out = destination(args.export_to, args.ciat_repo)
        with TemporaryDirectory(dir=out.parent) as temp:
            stage = Path(temp) / "staging"
            stage.mkdir(mode=0o700)
            for name, raw in data.items():
                p = stage / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                p.chmod(0o400)
            out.mkdir(mode=0o700)
            try:
                stage.rename(out / "staging")
            except OSError:
                out.rmdir()
                raise
    return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cmds = cli.add_subparsers(dest="action", required=True)
    build = cmds.add_parser("capture")
    check = cmds.add_parser("verify")
    for cmd in (build, check):
        cmd.add_argument("--ciat-repo", type=Path, required=True)
        cmd.add_argument("--bundle", type=Path, required=True)
    build.add_argument(
        "--revision", required=True, help="Full CIAT commit for comparison"
    )
    build.add_argument("--staging-dir", required=True, type=Path)
    build.add_argument(
        "--units", nargs="+", required=True, help="Relative paths to staged unit lists"
    )
    build.add_argument(
        "--companion",
        nargs="+",
        default=[],
        help="Additional JSON receipts to preserve",
    )
    check.add_argument("--sha256", required=True)
    check.add_argument("--at", help="Also compare against this full CIAT commit")
    check.add_argument(
        "--export-to",
        type=Path,
        help="Restore exact inputs under a new private directory",
    )
    check.add_argument(
        "--details",
        action="store_true",
        help="Report per-file and per-position results",
    )
    args = cli.parse_args()
    print(
        json.dumps(
            capture(args) if args.action == "capture" else verify(args), indent=2
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (
        KeyError,
        OSError,
        ValueError,
        BadZipFile,
        subprocess.CalledProcessError,
    ) as error:
        sys.exit(f"Checkpoint failed: {error}")
