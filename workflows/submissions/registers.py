"""Prepare a protected register PR from authenticated RuralScan issue receipts."""

import argparse
import csv
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import intake
from handoff import check_replays, same_value, scientific_fields
from git_snapshot import git, require, snapshot

ROOT = Path(__file__).resolve().parents[2]
SEED = "e43c42bd581dba791ce1f1697b6b41952ab0cfe3"
FIRST = "3d734daa5cf5452b69a5a63c6815efae7be0181d"
OLD_QUEUE = "16e76d3e76bf9695cf5cda1ef9027e54a121d1f1"
EV = intake.EV
SRC = "schema/registers/SRC_source_register.csv"
LOG = intake.LOG
JOURNAL = "registers/applied-receipts.json"
LIVE = "publication/review-queue.json"


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode(), newline=""), strict=True))


def index(records, key):
    values = {row[key]: row for row in records}
    require(
        len(values) == len(records) and "" not in values, f"Invalid or duplicate {key}"
    )
    return values


def write_csv(path, records):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def json_bytes(obj):
    return (
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def content_digest(data):
    return hashlib.sha256(data).hexdigest()


def blob(repo, pin, path):
    return git("show", f"{pin}:{path}", cwd=repo)


def member(repo, child, parent):
    return (
        subprocess.run(
            ["git", "-C", repo, "merge-base", "--is-ancestor", child, parent],
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def cohort(repo, base, ciat, pin):
    require(re.fullmatch("[0-9a-f]{40}", pin), "Invalid receipt revision")
    if pin in {SEED, OLD_QUEUE}:
        producer, prefix = ciat, ""
    else:
        require(
            member(repo, pin, base) and member(repo, FIRST, pin),
            "Unknown or unmerged RuralScan revision",
        )
        producer, prefix = repo, "registers/"
    return tuple(
        index(rows(blob(producer, pin, prefix + p)), key)
        for p, key in [(EV, "evidence_id"), (SRC, "source_id")]
    )


def authenticated(issues):
    """Fetch original receipts under the same issuer and identity policy as the desk."""
    accepted = {}
    for item in issues:
        try:
            entry = intake.decode(item)
        except (ValueError, TypeError):
            continue
        if entry["test"] or not intake.reviewer_eligible(item):
            continue
        try:
            actor = intake.original(item)
        except ValueError:
            # Edited/unattributable receipts have no effective ballot.
            continue
        accepted[item["number"]] = dict(
            entry=entry,
            actor=actor,
            digest=content_digest(item["body"].encode()),
            labels={label["name"] for label in item["labels"]},
        )
    return accepted


def participants(receipts, selected, targets):
    """Include every eligible opposing ballot on the selected findings, across cohorts."""
    result = {}
    for number, item in receipts.items():
        entry = item["entry"]
        if entry["kind"] == "vote":
            raw = [entry["payload"]]
        elif entry["kind"] == "csv" and isinstance(entry["payload"], str):
            raw = intake.csv_reader(entry["payload"])
        else:
            continue
        ids = {
            r["evidence_id"]
            for r in raw
            if isinstance(r, dict)
            and r.get("evidence_id")
            and (r.get("decision") or "").strip()
        }
        if number in selected or ids & targets:
            result[number] = ids
    return result


def ballot_verdict(row):
    decision = row["decision"].strip().lower()
    require(decision in intake.VERDICT, "A note alone has no finding verdict")
    note = row.get("note", "").strip()
    if row.get("picos_flags"):
        note = (note + " [PICOS fails: " + row["picos_flags"] + "]").strip()
    return dict(
        decision=intake.VERDICT[decision],
        reason=row.get("reason", "").strip()
        or ("confirmed_pass" if decision == "approve" else ""),
        note=note,
    )


def apply_batch(repo, ciat, base, producer, receipts, selected, journal, corpus):
    from nbs_ruralscan.schema_tools import evidence_intake, review
    from nbs_ruralscan.schema_tools.migrate_effects import _cell, resync_vars_extracted
    from nbs_ruralscan.schema_tools.submit_review import consensus_decisions

    require(
        set(selected) <= receipts.keys(),
        "Missing, test-only, edited or unconfirmed receipt",
    )
    for n in selected:
        if str(n) in journal:
            require(
                journal[str(n)]["digest"] == receipts[n]["digest"],
                f"Receipt #{n} changed after application",
            )
    selected = set(n for n in selected if str(n) not in journal)
    if not selected:
        return []
    current = index(rows((producer / EV).read_bytes()), "evidence_id")
    sources = index(rows((producer / SRC).read_bytes()), "source_id")
    cohorts = {}

    def pinned(pin):
        if pin not in cohorts:
            cohorts[pin] = cohort(repo, base, ciat, pin)
        return cohorts[pin]

    raw_votes = participants(receipts, selected, set())
    targets = set().union(*raw_votes.values())
    related = participants(receipts, selected, targets)
    # A multi-finding CSV is applied as one unit. Never mark a partial CSV processed.
    require(
        all(n in selected or str(n) in journal for n in related),
        f"Include all pending receipts for these findings: {sorted(related)}",
    )
    votes = defaultdict(dict)
    for n in sorted(related):
        item = receipts[n]
        entry, actor = item["entry"], item["actor"]
        old, old_sources = pinned(entry["revision"])
        roles = {
            "T4": {"structural_suitability"},
            "T3/T6": {"asset_vulnerability", "nbs_effect"},
        }

        class VoteCohort:
            reasons = review.REASON_CODES
            lanes = {
                entry["lane"]: {
                    eid
                    for eid, row in old.items()
                    if row["use_role"] in roles[entry["lane"]]
                }
            }

        for row in intake.vote_rows(entry, actor, VoteCohort):
            eid = row["evidence_id"]
            if not row["decision"].strip() or eid not in targets:
                continue
            vote = ballot_verdict(row)
            require(
                actor not in votes[eid] or votes[eid][actor] == vote,
                f"Conflicting receipts for {eid} by {actor}",
            )
            votes[eid][actor] = vote
            if str(n) not in journal:
                # Identical historical decisions can be credited to another reviewer. A changed
                # source or scientific record, including a later review stamp, needs a fresh vote.
                require(
                    eid in current
                    and old[eid] == current[eid]
                    and old_sources[old[eid]["source_id"]]
                    == sources.get(old[eid]["source_id"]),
                    f"Finding/source changed since receipt #{n}: {eid}",
                )
    agreed, conflicts = consensus_decisions(votes)
    require(not conflicts, f"Opposing votes remain pending: {conflicts}")
    history = defaultdict(list)
    for event in rows((producer / LOG).read_bytes()):
        history[event["evidence_id"]].append(event)
    for eid, verdict in agreed.items():
        latest = next(
            (
                event
                for event in reversed(history[eid])
                if event["decision"] in {"ok", "flag", "drop", "reopen", "reclassify"}
                and not event["reviewer"].lower().startswith(("ai_", "auto"))
            ),
            None,
        )
        if latest and latest["decision"] not in {verdict["decision"], "flag", "reopen"}:
            require(
                False,
                f"Late challenge to applied finding {eid}; reconcile with its recorded decision",
            )
    extraction_ids = set()
    for n in sorted(selected):
        item = receipts[n]
        entry = item["entry"]
        if entry["kind"] != "extraction":
            continue
        require(
            "approved-extraction" in item["labels"],
            f"Extraction #{n} awaits scientific approval",
        )
        units = entry["payload"]
        require(
            isinstance(units, list)
            and units
            and all(isinstance(u, dict) for u in units),
            "Expected extraction units",
        )
        require(
            corpus and corpus.is_dir(),
            "An acquired source corpus is required for extraction",
        )
        old, old_sources = pinned(entry["revision"])
        ids = [u["evidence_id"] for u in units]
        require(
            len(set(ids)) == len(ids) and not set(ids) & (targets | extraction_ids),
            "Overlapping evidence IDs in application batch",
        )
        extraction_ids.update(ids)
        roles = {
            "T4": {"structural_suitability"},
            "T3/T6": {"asset_vulnerability", "nbs_effect"},
        }[entry["lane"]]
        paths = evidence_intake.EvidenceIntakePaths.from_root(producer, corpus=corpus)
        for u in units:
            eid, sid = u["evidence_id"], u["source_id"]
            require(
                sid in sources
                and sources[sid] == old_sources.get(sid)
                and current.get(eid) == old.get(eid),
                f"Stale source or finding for {eid}",
            )
            require(
                u.get("reviewer_ok") in (None, False, "") and not u.get("review_state"),
                "Extraction carries a review decision",
            )
            issues = evidence_intake.gate([u], roles, paths=paths)
            prev = current.get(eid)
            if prev and u.get("ruleset_version") == prev["ruleset_version"]:
                # Historical observations retain their original stamp. Only waive the
                # version-enumeration diagnostic for an existing identically stamped unit.
                issues = [
                    s
                    for s in issues
                    if not s.startswith(
                        f"{eid}: ruleset_version '{prev['ruleset_version']}' not in "
                    )
                ]
            require(not issues, f"Content gate #{n}: {issues}")
        new = [u for u in units if u["evidence_id"] not in current]
        changed = [
            u
            for u in units
            if u["evidence_id"] in current
            and not same_value(
                scientific_fields(current[u["evidence_id"]]), scientific_fields_dict(u)
            )
        ]
        for u in changed:
            eid = u["evidence_id"]
            require(
                u["source_id"] == current[eid]["source_id"]
                and u["ruleset_version"] == current[eid]["ruleset_version"],
                "Correction changes source identity or original ruleset",
            )
            require(
                current[eid]["review_state"] != "dropped",
                "Dropped finding needs explicit reopening",
            )
            current[eid].update(
                {
                    key: _cell(u.get(key))
                    for key in current[eid]
                    if key not in {"reviewer_ok", "review_state"}
                }
            )
        if changed:
            write_csv(producer / EV, list(current.values()))
            review.reopen_units(
                [u["evidence_id"] for u in changed],
                reviewer=f"RuralScan receipt #{n}",
                files=review.ReviewFiles.from_root(producer),
            )
            resync_vars_extracted(
                {u["source_id"] for u in changed}, producer / SRC, producer / EV
            )
        if new:
            check_replays(producer / EV, new)
            evidence_intake.ingest(
                new,
                paths=paths,
                allowed_roles=roles,
                run_id=f"RuralScan-issue-{n}",
                extractor=item["actor"],
            )
        current = index(rows((producer / EV).read_bytes()), "evidence_id")
    if agreed:
        review.apply_decisions(agreed, files=review.ReviewFiles.from_root(producer))
    for n in sorted(selected):
        item = receipts[n]
        journal[str(n)] = {key: item[key] for key in ("actor", "digest")}
        journal[str(n)].update(
            base=base, revision=item["entry"]["revision"], kind=item["entry"]["kind"]
        )
    return sorted(selected)


def scientific_fields_dict(unit):
    return {
        k: v
        for k, v in unit.items()
        if k not in {"reviewer_ok", "review_state"} and v is not None and v != ""
    }


def prepare(ciat, corpus, selected, *, publish=False):
    require(
        not git("status", "--porcelain", cwd=ROOT).strip(),
        "Use a clean RuralScan/evidence checkout",
    )
    require(
        git("remote", "get-url", "origin", cwd=ROOT)
        .decode()
        .strip()
        .removesuffix(".git")
        .lower()
        in {
            "https://github.com/ruralscan/evidence",
            "git@github.com:ruralscan/evidence",
        },
        "Wrong register repository",
    )
    git("fetch", "--quiet", "origin", "main", cwd=ROOT)
    base = git("rev-parse", "origin/main", cwd=ROOT).decode().strip()
    require(member(ROOT, FIRST, base), "Missing register migration")
    receipts = authenticated(intake.submissions())
    with TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        producer = root / "engine"
        dest = root / "evidence"
        snapshot(dest, "", base, ["/*"], ROOT)
        snapshot(
            producer,
            intake.PRODUCER,
            SEED,
            [
                "/src/",
                "/scripts/",
                "/schema/",
                "/pipeline/",
                "/docs/review/*.json",
                "!/docs/review/*/",
            ],
            ciat,
        )
        sys.path.insert(0, str(producer / "src"))
        for path in (dest / "registers").rglob("*"):
            target = producer / path.relative_to(dest / "registers")
            if path.is_file() and target.is_file():
                shutil.copyfile(path, target)
        ledger = dest / JOURNAL
        journal = json.loads(ledger.read_bytes()) if ledger.exists() else {}
        applied = apply_batch(
            ROOT, ciat, base, producer, receipts, selected, journal, corpus
        )
        if not applied:
            print("Receipts already applied.")
            return
        for name in (EV, SRC, LOG):
            shutil.copyfile(producer / name, dest / "registers" / name)
        ledger.write_bytes(json_bytes(journal))
        from queue_view import build

        (dest / LIVE).write_bytes(json_bytes(build(producer)))
        git("add", "--", "registers", LIVE, cwd=dest)
        print(git("diff", "--cached", "--stat", cwd=dest).decode(), flush=True)
        if publish:
            require(
                member(ROOT, git("rev-parse", "HEAD", cwd=ROOT).decode().strip(), base),
                "Pull the merged register writer before opening an official PR",
            )
            # CIAT archival certification must already be on its public main. A
            # held register delta or a missing retirement commit stops the switch.
            authority = intake.gh(
                "repos/CIAT/nbs_ruralscan/contents/.ciat-evidence-readonly?ref=main"
            )
            require(see_authority(authority), "CIAT write retirement has not landed")
            branch = "registers/" + base[:12] + "-" + "-".join(map(str, applied))
            title = "Apply RuralScan receipts " + ", ".join(f"#{n}" for n in applied)
            git("commit", "-qm", title, cwd=dest)
            git(
                "remote",
                "set-url",
                "origin",
                "https://github.com/RuralScan/evidence.git",
                cwd=dest,
            )
            prior = intake.gh(
                f"repos/{intake.INBOX}/pulls?state=open&head=RuralScan:{branch}"
            )
            if prior:
                print(prior[0]["html_url"])
                return
            existing = (
                git("ls-remote", "--heads", "origin", "refs/heads/" + branch, cwd=dest)
                .decode()
                .split()
            )
            if existing:
                git("fetch", "--quiet", "origin", branch, cwd=dest)
                require(
                    git("rev-parse", "FETCH_HEAD^{tree}", cwd=dest)
                    == git("rev-parse", "HEAD^{tree}", cwd=dest),
                    "Existing proposal differs; inspect branch",
                )
            else:
                git("push", "origin", "HEAD:refs/heads/" + branch, cwd=dest)
            body = root / "pr.md"
            body.write_text(
                f"Apply verified issue receipts against RuralScan/evidence at `{base}`.\n\n"
                + "\n".join(
                    f"- https://github.com/RuralScan/evidence/issues/{n}"
                    for n in applied
                )
            )
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "-R",
                    intake.INBOX,
                    "--head",
                    branch,
                    "--base",
                    "main",
                    "--title",
                    title,
                    "--body-file",
                    str(body),
                ],
                cwd=dest,
                check=True,
            )


def see_authority(response):
    import base64

    marker = json.loads(base64.b64decode(response["content"]))
    return (
        marker["source_revision"] == SEED
        and marker["destination"] == "https://github.com/RuralScan/evidence"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", type=int)
    parser.add_argument(
        "--ciat-repo",
        type=Path,
        required=True,
        help="Local immutable compiler/history checkout",
    )
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--open-pr", action="store_true")
    args = parser.parse_args()
    try:
        prepare(
            args.ciat_repo.resolve(),
            args.corpus.resolve() if args.corpus else None,
            args.receipts,
            publish=args.open_pr,
        )
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as err:
        sys.exit(f"Register submission held: {err}")
