"""Explain applied extraction corrections from the two official register versions."""

from collections import defaultdict
import csv
import io
import json
import re

from registers import EV, JOURNAL, blob, git, require, same_value, scientific_fields

REGISTER = "registers/" + EV
MISSING = object()
# The review engine prepends these stamps to attribution when a finding changes state.
STAMP = re.compile(
    r"^\[(?:VERIFY-FLAG\s+\w+:|(?:reviewed|dropped|query|reclassified)\s+\d{4}-\d\d-\d\d\b)[^\]]*\]\s*"
)


def content(row):
    fields = scientific_fields(row)
    attribution = fields.pop("attribution", "").strip()
    while STAMP.match(attribution):
        attribution = STAMP.sub("", attribution, count=1)
    if attribution:
        fields["attribution"] = attribution
    return fields


def changes(before, after):
    result = []

    def compare(path, old, new):
        if same_value(old, new):
            return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in sorted(old.keys() | new.keys()):
                compare([*path, key], old.get(key, MISSING), new.get(key, MISSING))
            return
        change = {"path": path}
        for side, value, record in (("before", old, before), ("after", new, after)):
            if value is MISSING:
                continue
            change[side] = value
            if path in (
                ["relationship", "observed_min"],
                ["relationship", "observed_max"],
            ):
                unit = record["relationship"].get("unit")
                if unit:
                    change[side + "_unit"] = unit
        result.append(change)

    compare([], before, after)
    return result


def correction_history(repo, review_log):
    journal = json.loads((repo / JOURNAL).read_bytes())
    events = []
    for row in review_log:
        match = re.fullmatch(r"RuralScan receipt #(\d+)", row["reviewer"])
        if row["decision"] == "reopen" and match:
            receipt = match[1]
            require(
                journal.get(receipt, {}).get("kind") == "extraction",
                f"Reopening has no applied extraction receipt #{receipt}",
            )
            events.append((receipt, row))

    if not events:
        return {}

    # Before commit, the writer uses the staged register. After merge, use the
    # commit that first published each receipt, even if a later review edited EV.
    pending = {receipt for receipt, _ in events}
    applied_at = {}
    commits = git(
        "log",
        "--reverse",
        "--first-parent",
        "--format=%H",
        "HEAD",
        "--",
        JOURNAL,
        cwd=repo,
    )
    for commit in commits.decode().splitlines():
        ledger = json.loads(blob(repo, commit, JOURNAL))
        found = pending.intersection(ledger)
        applied_at.update(dict.fromkeys(found, commit))
        pending -= found
        if not pending:
            break

    wanted = defaultdict(set)
    for receipt, row in events:
        for version in (journal[receipt]["base"], applied_at.get(receipt)):
            wanted[version].add(row["evidence_id"])

    # Read each distinct revision once and retain only the findings that changed.
    records = {}
    for version, ids in wanted.items():
        data = (
            blob(repo, version, REGISTER) if version else (repo / REGISTER).read_bytes()
        )
        for row in csv.DictReader(io.StringIO(data.decode(), newline="")):
            eid = row["evidence_id"]
            if eid in ids:
                records[version, eid] = content(row)

    history = defaultdict(list)
    for receipt, row in events:
        eid = row["evidence_id"]
        before = records[journal[receipt]["base"], eid]
        after = records[applied_at.get(receipt), eid]
        fields = changes(before, after)
        if fields:
            history[eid].append(
                {"receipt": int(receipt), "date": row["date"], "changes": fields}
            )
    return dict(history)
