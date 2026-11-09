"""Record or verify the files used in a private evidence run."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
from tempfile import NamedTemporaryFile

WORKBENCH = Path(__file__).resolve().parents[2]
CATALOG = "workbench/rulesets/catalog.json"
FORMAT = "ruralscan-evidence-run/1"


def require(value, message):
    if not value:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as handle:
        checksum = hashlib.sha256()
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
        return checksum.hexdigest()


def file_path(ref, workspace, run):
    require(isinstance(ref, str), "Expected a file reference")
    path = PurePosixPath(ref)
    parts = path.parts
    require(
        len(parts) > 1
        and ref == path.as_posix()
        and parts[0] in {"workbench", "run"}
        and not any(
            p in {".", ".."} or p.lower() == ".git" or ":" in p or "\\" in p
            for p in parts
        ),
        "Use a relative workbench/ or run/ file reference",
    )
    root = workspace if parts[0] == "workbench" else run
    entry = root.joinpath(*parts[1:])
    require(
        entry.resolve() == root.resolve().joinpath(*parts[1:]) and entry.is_file(),
        f"Missing or redirected file: {ref}",
    )
    return entry


def make_record(declaration, workspace, run):
    require(isinstance(declaration, dict), "Expected a run description")
    for field in ("run_id", "scope", "limits"):
        require(
            isinstance(declaration.get(field), str) and declaration[field].strip(),
            f"Missing {field}",
        )
    stages = declaration.get("stages")
    require(isinstance(stages, list) and stages, "Declare at least one stage")
    names = set()
    refs = {CATALOG}
    catalog = read_json(file_path(CATALOG, workspace, run))["entries"]
    for stage in stages:
        require(isinstance(stage, dict), "Expected a stage description")
        name = stage.get("name")
        require(
            isinstance(name, str) and name.strip() and name not in names,
            "Stage names must be unique",
        )
        names.add(name)
        mode = stage.get("mode")
        require(mode in ("manual", "ai-assisted", "replay"), "Unknown stage mode")
        for field in ("instructions", "inputs", "outputs"):
            files = stage.get(field)
            require(
                isinstance(files, list)
                and files
                and all(isinstance(v, str) for v in files),
                f"Declare {name} {field}",
            )
            if field == "outputs":
                require(
                    all(v.startswith("run/") for v in files),
                    "Outputs must be run files",
                )
            refs.update(files)
        rules = stage.get("rulesets")
        require(
            isinstance(rules, list)
            and all(isinstance(k, str) and k in catalog for k in rules),
            f"Unknown or missing ruleset list for {name}",
        )
        if mode == "ai-assisted":
            for field in ("provider", "model", "prompt"):
                require(
                    isinstance(stage.get(field), str) and stage[field].strip(),
                    f"AI-assisted stage requires {field}",
                )
            require(
                stage["prompt"].startswith("run/")
                and stage["prompt"] in stage["instructions"],
                "List the actual private prompt under instructions",
            )
        else:
            require(
                not {"provider", "model", "prompt"}.intersection(stage),
                "Only AI-assisted stages declare a model or private prompt",
            )
    return {
        "format": FORMAT,
        "run": declaration,
        "sha256": {ref: digest(file_path(ref, workspace, run)) for ref in sorted(refs)},
    }


def save_record(record, run):
    # Install only a complete receipt. Concurrent runs cannot overwrite an earlier one.
    out = run / "run-record.json"
    pending = NamedTemporaryFile(dir=run, prefix=".run-record-", delete=False)
    try:
        with pending:
            pending.write(
                (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode()
            )
        os.link(pending.name, out)
    finally:
        Path(pending.name).unlink(missing_ok=True)
    return out


def verify(run, expected_digest=None):
    path = file_path("run/run-record.json", WORKBENCH, run)
    payload = path.read_bytes()
    if expected_digest is not None:
        require(
            hashlib.sha256(payload).hexdigest() == expected_digest,
            "Run record differs from saved digest",
        )
    old = json.loads(payload)
    require(
        isinstance(old, dict) and old.get("format") == FORMAT, "Unsupported run record"
    )
    observed = make_record(old["run"], WORKBENCH, run)
    require(
        observed.keys() == old.keys() and isinstance(old.get("sha256"), dict),
        "Invalid run record",
    )
    require(observed["sha256"].keys() == old["sha256"].keys(), "File inventory differs")
    for ref in observed["sha256"]:
        require(
            observed["sha256"][ref] == old["sha256"][ref],
            f"File digest differs: {ref}",
        )
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--description", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("--sha256", help="Previously saved receipt digest")
    for sub in (create, check):
        sub.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        root = args.run_dir.resolve()
        require(
            not any(
                p.name.casefold() == ".git" or (p / ".git").exists()
                for p in (root, *root.parents)
            ),
            "Create private run records outside Git",
        )
        record = make_record(read_json(args.description), WORKBENCH, args.run_dir)
        path = save_record(record, args.run_dir)
    else:
        path = verify(args.run_dir, args.sha256)
    print(
        json.dumps(
            {
                "run_record_sha256": digest(path),
                "verified_files": len(read_json(path)["sha256"]),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(f"Run record check stopped: {exc}")
