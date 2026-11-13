"""Receive finding votes and extraction proposals in the private RuralScan inbox."""

import ast
import argparse
import csv
import hashlib
import io
import os
import shutil
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "review_preview"), str(HERE.parent / "extraction")]
from csv_votes import FIELDS, VERDICT, private_path, stage_votes, unique_object  # noqa: E402
from handoff import check, invalid_number  # noqa: E402
from git_snapshot import snapshot  # noqa: E402
from preview import ENGINE, EV, HISTORY, LOG, require  # noqa: E402

INBOX = "RuralScan/evidence-intake"
PRODUCER = "https://github.com/CIAT/nbs_ruralscan.git"
HEADER = "RuralScan submission v1"
LANES = {"T4", "T3/T6"}
FIXTURES = {"T4": "test_bench_terrace", "T3/T6": "test_hazard_scorecard"}


def gh(*args, data=None):
    cmd = ["gh", "api", "--hostname", "github.com", *args]
    if data is not None:
        cmd.extend(["--input", "-"])
    return json.loads(
        subprocess.check_output(
            cmd, input=json.dumps(data).encode() if data is not None else None
        )
    )


def signed_in():
    repo = gh("repos/" + INBOX)
    require(
        repo["private"]
        and repo["visibility"] == "private"
        and repo["full_name"].lower() == INBOX.lower()
        and repo["has_issues"],
        "The configured RuralScan inbox must be private and accept issues",
    )
    return gh("user")["login"]


def encode(kind, lane, pin, payload, *, test=False):
    require(
        kind in {"vote", "csv", "extraction"} and lane in LANES,
        "Unknown submission type or lane",
    )
    require(re.fullmatch("[0-9a-f]{40}", pin), "Supply the full source revision")
    return (
        HEADER
        + "\n"
        + json.dumps(
            dict(kind=kind, lane=lane, revision=pin, test=test, payload=payload),
            ensure_ascii=False,
            allow_nan=False,
        )
    )


def receive(kind, lane, pin, payload, *, test=False, expected_actor=None):
    actor = signed_in()
    require(
        not expected_actor or actor == expected_actor,
        "GitHub account changed. Restart the desk.",
    )
    body = encode(kind, lane, pin, payload, test=test)
    require(len(body.encode()) <= 65000, "Split this batch into smaller submissions")
    title = f"{'TEST · ' if test else ''}{lane} · {kind} submission"
    issue = gh("repos/" + INBOX + "/issues", data={"title": title, "body": body})
    require(issue["user"]["login"] == actor, "Authenticated receipt identity differs")
    return issue["html_url"]


def submissions(actor=None):
    repo = gh("repos/" + INBOX)
    require(
        repo["private"]
        and repo["visibility"] == "private"
        and repo["full_name"].lower() == INBOX.lower(),
        "Expected private RuralScan inbox",
    )
    result = []
    page = 1
    while True:
        suffix = f"&creator={actor}" if actor else ""
        items = gh(
            f"repos/{INBOX}/issues?state=all&sort=created&direction=asc&per_page=100&page={page}{suffix}"
        )
        for issue in items:
            if issue.get("pull_request") or not (issue.get("body") or "").startswith(
                HEADER + "\n"
            ):
                continue
            result.append(issue)
        if len(items) < 100:
            return result
        page += 1


def decode(issue):
    body = issue["body"]
    require(body.startswith(HEADER + "\n"), "Unknown submission format")
    entry = json.loads(
        body.split("\n", 1)[1],
        object_pairs_hook=unique_object,
        parse_constant=invalid_number,
    )
    require(
        isinstance(entry, dict)
        and set(entry) == {"kind", "lane", "revision", "test", "payload"},
        "Malformed submission",
    )
    require(type(entry["test"]) is bool, "Invalid test flag")
    encode(
        entry["kind"],
        entry["lane"],
        entry["revision"],
        entry["payload"],
        test=entry["test"],
    )
    # GitHub allows maintainers to edit other people's issue bodies. Such an edit
    # cannot inherit the original author's identity. Check via GraphQL in collect.
    return entry


def original(issue):
    info = gh(
        "graphql",
        data={
            "query": """query($id: ID!) {
      node(id: $id) { ... on Issue { body lastEditedAt author { login } } }
    }""",
            "variables": {"id": issue["node_id"]},
        },
    )["data"]["node"]
    require(
        info
        and info["author"]
        and info["author"]["login"] == issue["user"]["login"]
        and info["body"] == issue["body"]
        and info["lastEditedAt"] is None,
        "Edited or unattributable submission. Return a fresh original.",
    )
    return issue["user"]["login"]


class Cohort:
    def __init__(self, repo, pin):
        require(re.fullmatch("[0-9a-f]{40}", pin), "Invalid cohort revision")
        self.pin = pin
        self.repo = repo
        self.blob = lambda path: subprocess.check_output(
            ["git", "-C", repo, "show", f"{pin}:{path}"]
        )
        records = json.loads(self.blob("docs/dashboard_data.json"))
        source = ast.parse(self.blob("src/nbs_ruralscan/schema_tools/review.py"))
        self.reasons = next(
            ast.literal_eval(n.value)
            for n in source.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "REASON_CODES" for t in n.targets
            )
        )
        self.evidence = {
            row["evidence_id"]: row
            for row in records["registers"]["EV_evidence_register"]
        }
        self.lanes = {
            "T4": {
                eid
                for eid, row in self.evidence.items()
                if row["use_role"] == "structural_suitability"
            },
            "T3/T6": {
                eid
                for recipe in records["recipes"].values()
                for table in ("T3_nbs_hazard_farming", "T6_nbs_scorecard")
                for row in recipe[table]
                for eid in row.get("evidence_ids", [])
            },
        }


def vote_rows(entry, actor, cohort):
    lane, payload = entry["lane"], entry["payload"]
    if entry["kind"] == "vote":
        require(
            isinstance(payload, dict)
            and set(payload) <= {"evidence_id", "decision", "reason", "note"},
            "Unknown dashboard vote fields",
        )
        rows = [dict(payload, reviewer=actor)]
    else:
        require(isinstance(payload, str), "CSV must be text")
        reader = csv.DictReader(
            io.StringIO(payload.lstrip("\ufeff"), newline=""), strict=True
        )
        fields = reader.fieldnames or []
        require(
            len(fields) == len(set(fields))
            and {"evidence_id", "reviewer", "decision"} <= set(fields) <= set(FIELDS),
            "Invalid evidence vote CSV header",
        )
        rows = list(reader)
    require(rows, "No votes supplied")
    for row in rows:
        require(
            None not in row and all(isinstance(val, str) for val in row.values()),
            "Malformed vote row",
        )
        require(
            row.get("reviewer", "").casefold() == actor.casefold(),
            "CSV reviewer differs from signed-in account",
        )
        eid = row.get("evidence_id", "")
        ids = {FIXTURES[lane]} if entry["test"] else cohort.lanes[lane]
        require(eid in ids, "Finding outside selected lane or cohort")
        decision = row.get("decision", "").lower().strip()
        require(
            decision in VERDICT
            or (
                not decision
                and any(row.get(k) for k in ("note", "picos_flags", "reason"))
            ),
            "Expected approve, hold or reject",
        )
        require(
            decision != "reject" or row.get("reason", "").strip() in cohort.reasons,
            "Give a coded rejection reason",
        )
    return rows


def extraction(entry, checkout, corpus, folder):
    units = entry["payload"]
    require(
        isinstance(units, list)
        and units
        and all(isinstance(row, dict) for row in units),
        "Expected extraction JSON array",
    )
    roles = {
        "T4": {"structural_suitability"},
        "T3/T6": {"asset_vulnerability", "nbs_effect"},
    }
    require(
        all(
            row.get("use_role") in roles[entry["lane"]]
            and row.get("reviewer_ok") in (None, False, "")
            and not row.get("review_state")
            for row in units
        ),
        "Invalid extraction lane or supplied review state",
    )
    path = folder / "staging.json"
    path.write_text(json.dumps(units, allow_nan=False))
    require(
        checkout and corpus,
        "Extraction needs pinned source checkout and private corpus",
    )
    flags = ("--allow-structural",) if entry["lane"] == "T4" else ()
    require(
        check(checkout, path, corpus, flags, validate_only=True) == 0,
        "Source/content gates failed",
    )
    try:
        eligible = check(checkout, path, corpus, flags) == 0
    except ValueError as error:
        return {"status": "held", "reason": str(error)}
    return {"status": "validated" if eligible else "held"}


def collect(issues, repo, pin, out, corpus=None, test=False):
    from csv_votes import publish_copy

    require(
        not out.exists() and not out.is_symlink(),
        "Choose a fresh private output folder",
    )
    private_path(out.parent)
    cohort = Cohort(repo, pin)
    with TemporaryDirectory(dir=out.parent) as tmp:
        root = Path(tmp)
        package = root / "result"
        package.mkdir(mode=0o700)
        pending = package / "pending"
        pending.mkdir(mode=0o700)
        ballots, mapping, received = [], {}, []
        checkout = None
        for issue in issues:
            entry = decode(issue)
            if entry["test"] != test:
                continue
            if entry["revision"] != pin:
                continue
            actor = original(issue)
            number = issue["number"]
            folder = package / str(number)
            folder.mkdir(mode=0o700)
            (folder / "original.json").write_text(json.dumps(issue, ensure_ascii=False))
            outcome = {"status": "received"}
            if entry["kind"] == "extraction":
                if checkout is None:
                    checkout = root / "engine"
                    snapshot(
                        checkout,
                        PRODUCER,
                        pin,
                        [
                            "/src/",
                            "/scripts/",
                            "/schema/",
                            "/pipeline/acquisition_queue.csv",
                        ],
                        repo,
                    )
                try:
                    outcome = extraction(entry, checkout, corpus, folder)
                except ValueError as error:
                    outcome = {"status": "held", "reason": str(error)}
            else:
                rows = vote_rows(entry, actor, cohort)
                path = folder / f"receipt-{number}.csv"
                with path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
                ballots.append(path)
                for row in rows:
                    mapping[row["reviewer"]] = actor
            received.append(
                dict(
                    **outcome,
                    number=number,
                    actor=actor,
                    kind=entry["kind"],
                    lane=entry["lane"],
                    digest=hashlib.sha256(issue["body"].encode()).hexdigest(),
                )
            )
        if ballots:
            names = root / "names.json"
            names.write_text(json.dumps(mapping))
            inputs = stage_votes(pending, ballots, names)
            publish_copy(package / "consensus-input", inputs)
            engine = root / "consensus-engine"
            snapshot(engine, PRODUCER, ENGINE, ["/src/"], repo)
            records = root / "records"
            if test:
                shutil.copytree(HERE.parent / "review_preview/example/records", records)
                with (records / EV).open(newline="") as f:
                    reader = csv.DictReader(f)
                    template = next(reader)
                    fields = reader.fieldnames
                with (records / EV).open("a", newline="") as f:
                    writer = csv.DictWriter(f, fields)
                    for eid in FIXTURES.values():
                        writer.writerow({**template, "evidence_id": eid})
            else:
                snapshot(
                    records,
                    PRODUCER,
                    pin,
                    ["/" + name for name in (EV, LOG, HISTORY)],
                    repo,
                )
            home = root / "home"
            home.mkdir()
            env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
            args = [
                sys.executable,
                "-I",
                "-B",
                str(HERE.parent / "review_preview/worker.py"),
                "--check-csv",
                str(engine / "src"),
                str(records),
                str(package / "consensus-input"),
            ]
            if not test:
                args.extend([str(repo), pin])
            receipt = subprocess.check_output(args, cwd=root, env=env)
            (package / "consensus.json").write_bytes(receipt)
        pending.rmdir()
        (package / "receipts.json").write_text(
            json.dumps(dict(revision=pin, test=test, receipts=received), indent=2)
        )
        os.rename(package, out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for kind in ("csv", "extraction"):
        cmd = sub.add_parser(kind)
        cmd.add_argument("file", type=Path)
        cmd.add_argument("--lane", choices=sorted(LANES), required=True)
        cmd.add_argument("--revision", required=True)
        cmd.add_argument("--test", action="store_true")
    cmd = sub.add_parser("collect")
    cmd.add_argument("--ciat-repo", required=True, type=Path)
    cmd.add_argument("--revision", required=True)
    cmd.add_argument("--out", required=True, type=Path)
    cmd.add_argument("--corpus", type=Path)
    cmd.add_argument("--test", action="store_true")
    args = p.parse_args()
    if args.action == "collect":
        collect(
            submissions(),
            args.ciat_repo.resolve(),
            args.revision,
            args.out,
            args.corpus,
            args.test,
        )
    else:
        raw = args.file.read_text(encoding="utf-8-sig")
        payload = (
            raw
            if args.action == "csv"
            else json.loads(
                raw, object_pairs_hook=unique_object, parse_constant=invalid_number
            )
        )
        print(receive(args.action, args.lane, args.revision, payload, test=args.test))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Submission held: {error}")
