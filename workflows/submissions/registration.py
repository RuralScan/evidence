"""Replay discovery, source promotion and progress operations on selected register copies."""

from dataclasses import replace
from datetime import date
import json
from pathlib import Path, PurePosixPath
import re
import sys
from tempfile import TemporaryDirectory

from registers import (
    EV,
    SRC,
    JOURNAL,
    ROOT,
    index,
    rows,
    write_csv,
    require,
    content_digest,
)

sys.path.extend(str(ROOT / "workflows" / lane) for lane in ("discovery", "acquisition"))
import screen
import run as acquisition

SEARCH = "schema/registers/SRCH_search_register.csv"
QUEUE = "pipeline/acquisition_queue.csv"
LEDGER = "pipeline/progress_ledger.csv"
FAMILIES = "schema/registers/FAM_family_registry.csv"
CROSSWALK = "schema/registers/XW_target_crosswalk.csv"
RECORDS = "operations"
REPORTS = "methodology/discovery_logs"
TRACKED = (SEARCH, QUEUE, LEDGER, SRC)


def records(root, name):
    return rows((root / "registers" / name).read_bytes())


def stem(op):
    if op["kind"] == "source":
        return "source-" + screen.identifier(op["receipt"]["source_id"])
    scope = op["plan"] if op["kind"] == "discovery" else op
    require(op["kind"] in {"discovery", "verification"}, "Unknown register operation")
    parts = [scope[k] for k in ("nbs_id", "family", "table", "process", "run_id")]
    for value in parts:
        if value != "":
            screen.identifier(value)
    return f"{op['kind']}-{screen.identifier(scope['run_id'])[:80]}-{screen.fingerprint(parts)[:16]}"


def capture_names(plan):
    names = plan["captures"]
    require(
        isinstance(names, list)
        and all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.json", n) for n in names),
        "Use simple JSON filenames for public discovery captures",
    )
    return names


def stamp(root, plan, updates, operator, when, proof):
    from nbs_ruralscan.schema_tools.ledger import mark

    path = root / "registers" / LEDGER
    key = dict(
        nbs_id=plan["nbs_id"],
        table=plan["table"],
        category=plan["process"],
        family=plan["family"],
    )

    def matches(row):
        return all(row[k] == v for k, v in key.items())

    require(
        sum(matches(r) for r in records(root, LEDGER)) <= 1,
        "Ambiguous progress ledger scope",
    )
    for stage, status in updates.items():
        mark(
            key["nbs_id"],
            key["table"],
            key["category"],
            stage,
            status,
            family=key["family"],
            run_id=plan["run_id"],
            by=operator,
            note=proof,
            path=path,
        )
    # Replay keeps the producing step's date even when CI runs on a later day.
    ledger = records(root, LEDGER)
    next(row for row in ledger if matches(row))["updated"] = screen.iso_date(when)
    write_csv(path, ledger)


def discover(root, op):
    from nbs_ruralscan.schema_tools import discovery_registration as registrar

    plan = op["plan"]
    names = capture_names(plan)
    require(len(names) == len(op["captures"]), "Capture count differs from plan")
    require(op["ruleset"] == screen.RULESET, "Wrong screening ruleset")
    require(type(op["stamp"]) is bool, "Progress stamp must be requested explicitly")
    name = stem(op)
    with TemporaryDirectory() as tmp:
        inputs = Path(tmp)
        captures = inputs / "captures"
        captures.mkdir()
        for filename, value in zip(names, op["captures"], strict=True):
            (captures / filename).write_text(screen.encode(value))
        path = captures / "plan.input"
        path.write_text(screen.encode(plan))
        args = screen.load_run(path)
        audit, candidates, counts = screen.screen(*args, op["decisions"])
        files = screen.render(
            plan, args[1], audit, candidates, counts, op["decisions"]["input_sha256"]
        )
        bundle = inputs / "bundle"
        screen.stage(bundle, files)
        lane = plan["process"]
        paths = registrar.DiscoveryRegistrationPaths.from_root(root / "registers")

        paths = replace(paths, logs=root / REPORTS)
        for item in records(root, SEARCH):
            require(
                (
                    item["run_id"],
                    item["nbs_id"],
                    item["suitability_family_id"],
                    item["table"],
                    item["category"],
                )
                != (
                    f"{plan['run_id']}_{lane}",
                    plan["nbs_id"],
                    plan["family"],
                    plan["table"],
                    lane,
                ),
                "Run already registered for this scope",
            )
        argv = [
            plan["nbs_id"],
            "--family",
            plan["family"],
            "--date",
            plan["date"],
            "--ruleset",
            op["ruleset"],
            "--run-prefix",
            plan["run_id"],
            "--searched-by",
            plan["searched_by"],
            "--assigned",
            "",
            "--candidates",
            f"{lane}={bundle}/candidates.json",
            "--protocols",
            f"{lane}={bundle}/protocols.json",
            "--reports",
            f"{lane}={bundle}/report.md",
            "--log-names",
            f"{lane}={name}.md",
            "--reuse-log",
            name + ".json",
        ]
        require(registrar.main(argv, paths=paths) == 0, "Discovery registrar failed")
    if op["stamp"]:
        complete = counts[0] == counts[1]
        stamp(
            root,
            plan,
            {"searched": "done", "screened": "done" if complete else "in_progress"},
            plan["screened_by"],
            plan["date"],
            f"SRCH {plan['run_id']}_{lane}; {REPORTS}/{name}.md",
        )


def promote(root, op, engine):
    receipt, candidate, plan = op["receipt"], op["candidate"], op["plan"]
    acquisition.validate_plan(plan)
    acquisition.check_provenance(receipt, plan, candidate)
    require(receipt["status"] == "acquired", "Source still held")
    sid, artifact = receipt["source_id"], receipt["artifact"]
    require(acquisition.SOURCE_ID.fullmatch(sid), "Invalid source ID")
    queue, sources = records(root, QUEUE), records(root, SRC)
    known = index(sources, "source_id")
    if sid in known:
        acquisition.validate_reuse(candidate | {"reuse_source_id": sid}, known[sid])
        require(
            len(known[sid]["artifact_sha1"]) in (16, 40)
            and artifact["sha1"].startswith(known[sid]["artifact_sha1"]),
            "Known source edition differs",
        )
        return False
    queue_row = index(queue, "source_id").get(sid)
    require(
        queue_row
        and sid == candidate["candidate_id"]
        and not candidate.get("reuse_source_id"),
        "Expected a screened, queued new source",
    )
    require(
        not queue_row["duplicate_of"]
        and queue_row["status"] in {"pending", "acquired"},
        "Queue record cannot be promoted",
    )
    acquisition.validate_reuse(candidate | {"reuse_source_id": sid}, queue_row)
    title = screen.title_key(candidate["title"])
    queued_citation = screen.title_key(queue_row["citation"])
    require(
        title and f" {title} " in f" {queued_citation} ",
        "Screened title differs from queued citation",
    )
    require(
        candidate["url"] == queue_row["url"]
        and candidate.get("doi", "").casefold() == queue_row["doi"].casefold(),
        "Candidate differs from queued source URL or DOI",
    )
    identity = receipt["metadata"]
    for source in known.values():
        require(
            not (
                identity["doi"]
                and source["doi"].casefold() == identity["doi"].casefold()
            )
            and screen.title_key(acquisition.citation_title(source["citation"]))
            != title
            and screen.normalized(source["citation"])
            not in {
                screen.normalized(candidate["citation"]),
                screen.normalized(identity["citation"]),
            }
            and not (
                len(source["artifact_sha1"]) in (16, 40)
                and artifact["sha1"].startswith(source["artifact_sha1"])
            ),
            f"Source already registered under {source['source_id']}",
        )
    assessment = op["assessment"]
    require(
        set(assessment)
        <= {
            "benchmark_tier",
            "venue_type",
            "method_type",
            "region",
            "study_income_group",
            "study_country",
            "license",
        },
        "Unknown source assessment field",
    )
    for key in ("benchmark_tier", "method_type", "venue_type"):
        screen.text(assessment, key)
    require(
        all(isinstance(v, str) for v in assessment.values()),
        "Source assessment requires text fields",
    )
    spec = json.loads((engine / "schema/structure/columns.json").read_bytes())
    enums = spec["tables"]["SRC"]["enum_values"]
    for key in assessment.keys() & enums.keys():
        require(assessment[key] in enums[key], f"Unknown source assessment {key}")
    process = candidate["process"]
    require(
        process in screen.PROCESSES
        and candidate["nbs_id"] in queue_row["nbs_id"].split("|")
        and set(candidate["tables"].split("|")) <= set(queue_row["tables"].split("|")),
        "Wrong source scope",
    )
    queued_process = re.search(
        r"(?:^|[. ;])process=([a-z_]+)(?:;|$)", queue_row["note"]
    )
    require(
        not queued_process or queued_process[1] == process,
        "Wrong source discovery process",
    )
    kind = receipt["kind"]
    library = op["library_path"]
    if kind == "pdf" or library:
        parts = PurePosixPath(library)
        require(
            library
            and not parts.is_absolute()
            and ".." not in parts.parts
            and "\\" not in library
            and "library" in parts.parts,
            "Supply the team library path",
        )
        require(
            parts.suffix.lower() == acquisition.EXTENSIONS[kind],
            "Library locator has wrong file type",
        )
    require(
        not queue_row["target_library_path"]
        or queue_row["target_library_path"] == library,
        "Shared locator differs from queue",
    )
    require(
        queue_row["doi_verified"] != "true" or identity["status"] == "doi_verified",
        "Previously verified DOI changed; reconcile identity",
    )
    queue_row.update(
        status="acquired",
        citation=identity["citation"],
        doi=identity["doi"],
        doi_verified="true" if identity["status"] == "doi_verified" else "",
        title_verified="true" if kind != "code" else "",
        target_library_path=library,
        blocker="",
    )
    when = date.fromisoformat(receipt["checked_at"][:10]).isoformat()
    source_kind = {
        "code": "codebase",
        "pdf": "paper" if process == "updated_lit" else "grey_lit",
    }.get(kind, "website")
    source = (
        {k: "" for k in sources[0]}
        | assessment
        | dict(
            source_id=sid,
            citation=identity["citation"],
            doi=identity["doi"],
            nbs_ids=queue_row["nbs_id"],
            artifact_sha1=artifact["sha1"],
            source_kind=source_kind,
            source_category=process,
            library_path=library,
            url=artifact["url"] if kind != "pdf" else queue_row["url"],
            extraction_status="pending",
            retrieved_at=when,
            access_status={
                "oa": "open_access",
                "paywalled": "paywalled",
                "open_access": "open_access",
            }.get(queue_row["access_status"], "unknown"),
        )
    )
    write_csv(root / "registers" / QUEUE, queue)
    write_csv(root / "registers" / SRC, [*sources, source])
    return True


def verification(root, op, repo):
    """Attribute the stamp to applied extractions that actually passed the content gates."""
    from nbs_ruralscan.schema_tools.ledger import tables_for, xw_routes
    from registers import intake, scientific_fields_dict, same_value
    from corrections import content
    from registers import blob

    journal = json.loads((root / JOURNAL).read_bytes())
    ev = index(records(root, EV), "evidence_id")
    sources = index(records(root, SRC), "source_id")
    routes = xw_routes(root / "registers/schema")
    expected = {
        eid
        for eid, row in ev.items()
        if row["review_state"] != "dropped"
        and row["nbs_id"] == op["nbs_id"]
        and (not op["family"] or row["suitability_family_id"] == op["family"])
        and sources[row["source_id"]]["source_category"] == op["process"]
        and op["table"] in tables_for(row["use_role"], row["variable"], routes)
    }
    require(expected, "No active evidence in this scope")
    require(
        any(
            r["searched"] == r["screened"] == "done"
            and (r["nbs_id"], r["family"], r["table"], r["category"])
            == (op["nbs_id"], op["family"], op["table"], op["process"])
            for r in records(root, LEDGER)
        ),
        "Complete search and screening in this scope first",
    )
    checked = set()
    for record in op["receipts"]:
        n = record["number"]
        require(type(n) is int and n > 0, "Expected a receipt number")
        applied = journal.get(str(n))
        require(
            applied and applied["kind"] == "extraction",
            f"Missing applied extraction #{n}",
        )
        issue = {"body": record["body"]}
        at_verification = index(
            rows(blob(repo, applied["base"], "registers/" + SRC)), "source_id"
        )
        require(
            content_digest(issue["body"].encode()) == applied["digest"],
            "Receipt content changed",
        )
        scoped = set()
        for unit in intake.decode(issue)["payload"]:
            eid = unit["evidence_id"]
            if eid in expected:
                sid = unit["source_id"]
                identity = (
                    "source_id",
                    "doi",
                    "citation",
                    "artifact_sha1",
                    "url",
                    "library_path",
                )
                require(
                    all(at_verification[sid][k] == sources[sid][k] for k in identity),
                    f"Source changed since verification: {sid}",
                )
                normalized = scientific_fields_dict(unit)
                # Compare original science including unstamped attribution; review stamps are handled by content().
                row = {
                    k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
                    for k, v in normalized.items()
                }
                require(
                    same_value(content(ev[eid]), content(row)),
                    f"Finding changed since verification: {eid}",
                )
                scoped.add(eid)
        require(scoped, f"Receipt #{n} did not verify this scope")
        checked |= scoped
    require(checked, "Supply an applied verification record")
    status = op["status"]
    require(
        status in {"done", "in_progress"} and (status != "done" or checked == expected),
        "Completion needs verified evidence for the full current scope",
    )
    stamp(
        root,
        op,
        {"verified": status},
        screen.text(op, "by"),
        op["date"],
        "Applied extraction receipts "
        + ", ".join(f"#{record['number']}" for record in op["receipts"]),
    )


def apply(root, op, engine, repo):
    if op["kind"] == "discovery":
        discover(root, op)
    elif op["kind"] == "source":
        return promote(root, op, engine)
    elif op["kind"] == "verification":
        verification(root, op, repo)
    else:
        raise ValueError("Unknown operation")
    return True


def checked_source_base(repo, base, engine):
    """Replay each new operation against the trusted PR base. Compare exact output bytes."""
    from registers import blob, git

    def inventory(root):
        files = {}
        for folder in (RECORDS, REPORTS):
            start = root / folder
            require(
                start.resolve() == root.resolve() / folder,
                "Redirected operation directory",
            )
            for p in start.rglob("*"):
                require(not p.is_symlink(), "Linked operation record")
                if p.is_file():
                    files[p.relative_to(root).as_posix()] = p.read_bytes()
        return files

    names = (
        git("ls-tree", "-r", "--name-only", base, "--", RECORDS, REPORTS, cwd=repo)
        .decode()
        .splitlines()
    )
    previous = {name: blob(repo, base, name) for name in names}
    current = inventory(repo)
    require(
        all(current.get(k) == v for k, v in previous.items()),
        "Historical operation or report changed",
    )
    added = current.keys() - previous.keys()
    ops = sorted(p for p in added if p.startswith(RECORDS + "/"))
    before = blob(repo, base, "registers/" + SRC)
    if not ops:
        require(not added, "Report lacks its discovery operation")
        for name in (SEARCH, QUEUE, LEDGER):
            require(
                (repo / "registers" / name).read_bytes()
                == blob(repo, base, "registers/" + name),
                f"{name} changed without an operation",
            )
        return before
    with TemporaryDirectory() as folder:
        root = Path(folder).resolve()
        for name in (*TRACKED, EV, FAMILIES, CROSSWALK):
            path = root / "registers" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob(repo, base, "registers/" + name))
        (root / JOURNAL).write_bytes(blob(repo, base, JOURNAL))
        for name, data in previous.items():
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        for path in ops:
            record = json.loads(current[path])
            op = record["operation"]
            require(record["base"] == base, "Stale operation. Rebuild on current main.")
            require(
                path == f"{RECORDS}/{stem(op)}.json",
                "Operation ID differs from recorded scope",
            )
            require(apply(root, op, engine, repo), "Operation already applied")
        for name in (SEARCH, QUEUE, LEDGER):
            require(
                (repo / "registers" / name).read_bytes()
                == (root / "registers" / name).read_bytes(),
                f"{name} differs from replay",
            )
        require(
            inventory(root) == {k: v for k, v in current.items() if k not in ops},
            "Discovery report differs from replay",
        )
        return (root / "registers" / SRC).read_bytes()
