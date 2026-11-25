"""Adopt a pinned method release and maintain evidence-owned compiler configuration."""

import argparse
import csv
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory

from registers import ROOT, SEED, EV, SRC, blob, git, require, rows, snapshot
from git_snapshot import revision

PIN = "configuration/method-pin.json"
JOURNAL = "configuration/changes.json"
METHOD = "https://github.com/RuralScan/method.git"
RELEASE = "configuration/release.json"
TRANSITION = "method/family-transition.json"
TOOL = "schema/registers/TOOL_tool_registry.csv"
OWN = {
    TOOL: ("tool_id",),
    "schema/lookups/direction_cue_exceptions.csv": ("evidence_id",),
    "schema/lookups/wocat_hazard_map.csv": ("wocat_group", "wocat_key"),
    "schema/lookups/wocat_impact_map.csv": ("wocat_group", "wocat_field"),
}
METHOD_REGISTERS = {
    "schema/registers/" + name + ".csv"
    for name in (
        "BANDS_magnitude_bands",
        "BIND_dataset_binding",
        "FAM_family_registry",
        "VONT_variable_ontology",
        "XW_target_crosswalk",
    )
}
EXTERNAL = {
    "ipcc_confidence_matrix",
    "wb_income_groups",
    "searched_no_evidence",
    "t4_numeric_compilation_policy",
}


def digest(data):
    return sha256(data).hexdigest()


def encoded(obj):
    return (
        json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()


def cache_path(target):
    if target == TRANSITION:
        return Path("configuration/family-transition.json")
    if target in METHOD_REGISTERS or target == TOOL:
        return Path("registers") / target
    require(
        re.fullmatch(r"schema/lookups/[a-z0-9_]+\.csv", target),
        "Unsupported method target",
    )
    return (
        Path("configuration")
        / ("lookups" if target in OWN else "method-lookups")
        / Path(target).name
    )


def local_method():
    value = os.environ.get("RURALSCAN_METHOD_REPO")
    return Path(value).resolve() if value else None


def pinned_release(sha, local=None):
    with TemporaryDirectory() as tmp:
        revision(sha)
        root = local or Path(tmp) / "method"
        if local is None:
            snapshot(
                root,
                METHOD,
                sha,
                ["/configuration/", "/data-model/configuration/"],
                None,
            )
        manifest = blob(root, sha, RELEASE)
        edition = json.loads(manifest)
        require(
            edition["format"] == "ruralscan.compiler-definitions.v1",
            "Unknown definition format",
        )
        files = {}
        for target, meta in edition["files"].items():
            cache_path(target)
            require(
                target not in OWN and Path(target).stem not in EXTERNAL,
                "Evidence or external input in method release",
            )
            expected_dir = (
                "data-model/configuration"
                if target in METHOD_REGISTERS
                else "configuration/lookups"
            )
            source = f"{expected_dir}/{Path(target).name}"
            require(meta["file"] == source, "Unexpected method release source")
            data = blob(root, sha, source)
            require(digest(data) == meta["sha256"], f"Method hash mismatch: {target}")
            files[target] = data
        require(METHOD_REGISTERS <= files.keys(), "Incomplete register release")
        transition = edition.get("family_transition")
        if transition:
            source = transition["file"]
            require(
                re.fullmatch(
                    r"configuration/family-transitions/[a-z0-9-]+\.json", source
                ),
                "Unexpected family transition source",
            )
            data = blob(root, sha, source)
            require(
                digest(data) == transition["sha256"], "Family transition hash mismatch"
            )
            from family_hierarchy import validate_transition

            validate_transition(
                json.loads(data),
                rows(files["schema/registers/FAM_family_registry.csv"]),
            )
            files[TRANSITION] = data
        archive = edition["archive"]
        require(
            archive["repository"] == "CIAT/nbs_ruralscan"
            and archive["revision"] == SEED
            and set(archive["lookups"]) == EXTERNAL,
            "Incompatible archival dependencies",
        )
        lock = dict(
            repository=METHOD,
            revision=sha,
            release_sha256=digest(manifest),
            files={p: digest(data) for p, data in files.items()},
            archival_lookups=archive["lookups"],
        )
        return lock, files


def pin(root, sha, local=None):
    lock, files = pinned_release(sha, local)
    for target, data in files.items():
        path = root / cache_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / PIN).write_bytes(encoded(lock))
    if TRANSITION not in files:
        (root / cache_path(TRANSITION)).unlink(missing_ok=True)
    from family_hierarchy import record_adoption

    record_adoption(root)


def owned_history(root):
    return json.loads((root / JOURNAL).read_bytes())


def verify_method(root, local=None):
    lock = json.loads((root / PIN).read_bytes())
    trusted, files = pinned_release(lock["revision"], local)
    require(lock == trusted, "Pin differs from selected method release")
    for target, data in files.items():
        require(
            (root / cache_path(target)).read_bytes() == data,
            f"Edited method mirror: {target}",
        )
    from family_hierarchy import verify_adoption

    verify_adoption(root)
    expected = {
        cache_path(k).name
        for k in files
        if k not in METHOD_REGISTERS and k != TRANSITION
    }
    require(
        {p.name for p in (root / "configuration/method-lookups").iterdir()} == expected,
        "Unexpected method policy inventory",
    )


def overlay(producer, root):
    """Install exact configuration into the isolated engine used by intake and synthesis."""
    if not (root / PIN).exists():
        return {}  # Historical evidence editions used their CIAT seed.
    lock = json.loads((root / PIN).read_bytes())
    inputs = {}
    if TRANSITION not in lock["files"]:
        (producer / TRANSITION).unlink(missing_ok=True)
    for target in (*lock["files"], *OWN):
        data = (root / cache_path(target)).read_bytes()
        checksum = digest(data)
        if target in lock["files"]:
            require(checksum == lock["files"][target], f"Stale method mirror: {target}")
        if target == TRANSITION:
            inputs[target] = checksum
            (producer / target).parent.mkdir(parents=True, exist_ok=True)
            (producer / target).write_bytes(data)
            continue  # Compatibility metadata, not an analytical compiler table.
        (producer / target).write_bytes(data)
        inputs[target] = checksum
    for name, expected in lock["archival_lookups"].items():
        require(
            digest((producer / f"schema/lookups/{name}.csv").read_bytes()) == expected,
            f"Incompatible archival lookup: {name}",
        )
    configured = vocabulary(root)
    engine_rules = json.loads(
        (producer / "schema/structure/columns.json").read_bytes()
    )["tables"]
    for (table, field), codes in configured.items():
        require(
            codes
            <= set(engine_rules.get(table, {}).get("enum_values", {}).get(field, [])),
            f"Pinned engine cannot interpret {table}.{field}",
        )
    return dict(
        method_revision=lock["revision"],
        method_release_sha256=lock["release_sha256"],
        evidence_changes_sha256=digest((root / JOURNAL).read_bytes()),
        inputs=inputs,
    )


def vocabulary(root):
    result = {}
    for row in rows(
        (root / cache_path("schema/lookups/configuration_vocabulary.csv")).read_bytes()
    ):
        result.setdefault((row["table"], row["field"]), set()).add(row["code"])
    return result


def pieces(value):
    return [part.strip() for part in value.split("|") if part.strip()]


def validate(root, producer, target, row, proof, *, check_locator=False):
    require(
        set(proof) == {"source_id", "locator", "evidence_ids"}
        and isinstance(proof["evidence_ids"], list)
        and isinstance(proof["locator"], str)
        and proof["locator"].strip(),
        "Source ID, finding list and locator required",
    )

    def records(path, key):
        return {r[key]: r for r in rows((root / "registers" / path).read_bytes())}

    sources = records(SRC, "source_id")
    findings = records(EV, "evidence_id")
    sid = proof["source_id"]
    ids = proof["evidence_ids"]
    require(
        sid in sources and all(i in findings for i in ids),
        "Missing source or finding reference",
    )
    require(
        all(findings[i]["source_id"] == sid for i in ids),
        "Supporting finding belongs to another source",
    )
    if ids and check_locator:

        def locators(finding):
            page = finding["page"]
            return {finding["locator"].strip().casefold()} | (
                {page, "p. " + page, "page " + page} if page else set()
            )

        require(
            any(
                proof["locator"].strip().casefold() in locators(findings[i])
                for i in ids
            ),
            "Locator differs from supporting finding",
        )
    variables = records(
        "schema/registers/VONT_variable_ontology.csv", "canonical_variable_id"
    )
    rules = json.loads((producer / "schema/structure/columns.json").read_bytes())[
        "tables"
    ]
    vocab = vocabulary(root)
    if target == TOOL:
        spec = rules["TOOL"]
        require(
            all(row.get(k) for k in spec["required"]), "Missing required tool field"
        )
        require(
            row["source_id"] == sid
            and all(i in findings for i in pieces(row["evidence_ids"])),
            "Unresolved tool source or findings",
        )
        require(
            all(i in pieces(row["evidence_ids"]) for i in ids),
            "Tool omits supporting findings",
        )
        require(
            all(not row[k] or row[k] in vocab["TOOL", k] for k in spec["enum_values"]),
            "Unknown tool vocabulary",
        )
        practices = {
            r["nbs_id"]
            for r in records(
                "schema/registers/FAM_family_registry.csv", "subpractice_id"
            ).values()
        }
        require(
            set(pieces(row["nbs_ids"])) <= practices
            and set(pieces(row["variables_used"])) <= variables.keys(),
            "Unknown tool practice or variable",
        )
    elif target.endswith("direction_cue_exceptions.csv"):
        require(
            ids == [row["evidence_id"]]
            and row["why"].strip()
            and row["checked_by"]
            and row["checked_date"],
            "Direction exception needs its own finding and rationale",
        )
    else:
        require(
            "wocat" in (sid + " " + sources[sid]["url"]).lower(),
            "Expected a WOCAT source",
        )
        if "hazard_type" in row:
            require(
                row["hazard_type"] in vocab["T3", "hazard_type"],
                "Unknown hazard in method vocabulary",
            )
        else:
            require(
                row["canonical_variable_id"] in variables
                and variables[row["canonical_variable_id"]]["review_status"]
                != "rejected"
                and row["use_role"] in vocab["EV", "use_role"],
                "Unknown WOCAT variable or role",
            )
            require(
                row["requires_comment"] in {"true", "false"},
                "Unknown WOCAT comment flag",
            )


def edit(target, data, event):
    require(
        set(event)
        == {
            "id",
            "table",
            "key",
            "before_sha256",
            "changes",
            "provenance",
            "reason",
            "method_revision",
        },
        "Unknown configuration change fields",
    )
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9._-]*", event["id"]) and event["reason"].strip(),
        "Change ID and reason required",
    )
    fields = OWN[target]
    key = event["key"]
    require(
        set(key) == set(fields)
        and all(isinstance(v, str) and v.strip() for v in key.values()),
        "Invalid row key",
    )
    lines = io.StringIO(data.decode(), newline="").readlines()
    reader = csv.DictReader(lines, strict=True)
    columns = reader.fieldnames
    start = reader.line_num
    bounds = None
    old = None
    for record in reader:
        if all(record[k] == key[k] for k in fields):
            require(old is None, "Duplicate configuration key")
            old, bounds = record, (start, reader.line_num)
        start = reader.line_num
    require(
        event["before_sha256"] == (digest(encoded(old)) if old else None),
        "Stale configuration row",
    )
    changes = event["changes"]
    require(
        isinstance(changes, dict)
        and changes
        and changes.keys() <= set(columns) - set(fields)
        and all(isinstance(v, str) for v in changes.values()),
        "Unknown or invalid changed column",
    )
    row = (old or dict.fromkeys(columns, "")) | key | changes
    require(row != old, "Empty configuration change")
    # Replace only this physical CSV record, including quoted multiline values.
    out = io.StringIO(newline="")
    ending = "\r\n" if data.partition(b"\n")[0].endswith(b"\r") else "\n"
    csv.DictWriter(out, fieldnames=columns, lineterminator=ending).writerow(row)
    if bounds:
        lines[bounds[0] : bounds[1]] = [out.getvalue()]
    else:
        if not lines[-1].endswith(("\r", "\n")):
            lines.append(ending)
        lines.append(out.getvalue())
    return "".join(lines).encode(), row


def replay(root, producer, events, new_from):
    material = {table: blob(producer, SEED, table) for table in OWN}
    seen = set()
    effective = {}
    pin_revision = json.loads((root / PIN).read_bytes())["revision"]
    for position, event in enumerate(events):
        table = event["table"]
        require(
            table in OWN and event["id"] not in seen,
            "Unknown table or repeated change ID",
        )
        seen.add(event["id"])
        material[table], row = edit(table, material[table], event)
        if position >= new_from:
            require(
                event["method_revision"] == pin_revision,
                "Event targets a different method revision",
            )
            validate(
                root, producer, table, row, event["provenance"], check_locator=True
            )
        key = tuple(row[k] for k in OWN[table])
        effective[table, key] = (row, event["provenance"])
    for (table, _), (row, proof) in effective.items():
        validate(root, producer, table, row, proof)
    return material


def verify_owned(root, producer, base):
    events = owned_history(root)
    prior = []
    if git("ls-tree", base, "--", JOURNAL, cwd=root):
        prior = json.loads(blob(root, base, JOURNAL))
        require(events[: len(prior)] == prior, "Configuration history was rewritten")
    for target, data in replay(root, producer, events, len(prior)).items():
        require(
            (root / cache_path(target)).read_bytes() == data,
            f"Unrecorded configuration change: {target}",
        )
    require(
        {p.name for p in (root / "configuration/lookups").iterdir()}
        == {Path(p).name for p in OWN if p != TOOL},
        "Unexpected evidence lookup inventory",
    )


def record(root, producer, event):
    history = owned_history(root)
    match = next((e for e in history if e["id"] == event["id"]), None)
    if match:
        require(match == event, "Change ID already used for different content")
    updated = history if match else history + [event]
    material = replay(root, producer, updated, len(history))
    # Keep the journal authoritative. A repeated command repairs an interrupted materialization.
    (root / JOURNAL).write_bytes(encoded(updated))
    (root / cache_path(event["table"])).write_bytes(material[event["table"]])


def engine(repo, dest, root=ROOT):
    snapshot(
        dest,
        "",
        SEED,
        ["/src/", "/schema/", "/pipeline/", "/docs/review/*.json", "!/docs/review/*/"],
        repo,
    )
    for p in (root / "registers").rglob("*"):
        to = dest / p.relative_to(root / "registers")
        if p.is_file() and to.is_file():
            shutil.copyfile(p, to)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pin_cmd = sub.add_parser("pin")
    pin_cmd.add_argument("method_revision")
    pin_cmd.add_argument("--method-repo", type=Path)
    for cmd in ("row", "record", "build", "checkout"):
        p = sub.add_parser(cmd)
        if cmd == "row":
            p.add_argument("table", choices=OWN)
            p.add_argument("key", help="JSON object containing the row key")
        elif cmd == "checkout":
            p.add_argument(
                "destination",
                type=Path,
                help="New directory for a pinned extraction or QA engine",
            )
        elif cmd == "record":
            p.add_argument("event", type=Path)
        if cmd != "row":
            p.add_argument("--ciat-repo", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "pin":
        pin(ROOT, args.method_revision, args.method_repo or local_method())
        return
    if args.command == "row":
        key = json.loads(args.key)
        require(set(key) == set(OWN[args.table]), "Invalid key columns")
        matches = [
            r
            for r in rows((ROOT / cache_path(args.table)).read_bytes())
            if all(r[k] == v for k, v in key.items())
        ]
        require(len(matches) <= 1, "Ambiguous key")
        print(
            json.dumps(
                dict(row=matches[0], before_sha256=digest(encoded(matches[0])))
                if matches
                else dict(row=None, before_sha256=None),
                indent=2,
            )
        )
        return
    if args.command == "checkout":
        dest = args.destination.resolve()
        require(not dest.exists(), "Select a new directory for the compiler checkout")
        require(
            not git(
                "status", "--porcelain", "--", "configuration", "registers", cwd=ROOT
            ),
            "Commit configuration and registers before exporting an edition",
        )
        engine(args.ciat_repo, dest)
        receipt = overlay(dest, ROOT)
        receipt["evidence_revision"] = (
            git("rev-parse", "HEAD", cwd=ROOT).decode().strip()
        )
        (dest / "configuration-inputs.json").write_bytes(encoded(receipt))
        return
    with TemporaryDirectory() as tmp:
        producer = Path(tmp).resolve() / "engine"
        engine(args.ciat_repo, producer)
        if args.command == "record":
            record(ROOT, producer, json.loads(args.event.read_bytes()))
        else:
            from queue_view import publish_files

            sys.path.insert(0, str(producer / "src"))
            publish_files(producer, ROOT)


if __name__ == "__main__":
    main()
