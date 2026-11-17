"""Revision-bound team triage of review requests; never a finding or rating vote."""

import json
import re

import intake
from recipe_rows import digest, evidence_index, lines, local, prior
from registers import LIVE, blob, content_digest, git, json_bytes, member, require

HEADER = "RuralScan review priority v1"
RECORDS = "priority-reviews/receipts.jsonl"
ACTIONS = {"addressed", "deprioritize", "restore"}
TARGET_FIELDS = {"batch_id", "evidence_id", "request_sha256", "basis_sha256", "last_receipt"}


def automatic(row, ev, events, rating_events, corrections):
    """Conservative presentation status, not a claim that a request was answered."""
    if not ev:
        return "active"
    date = row.get("requested_date", "")
    latest = events[-1] if events else {}
    calls = {}
    for event in events:
        if event["decision"] == "reopen":
            calls.clear()
        else:
            for who in event.get("reviewer", "").lower().split(","):
                calls[who.strip()] = event["decision"]
    values = set(calls.values())
    if values & {"flag", "query", "hold"} or (values & {"ok", "keep"} and "drop" in values):
        return "active"
    settled = ev.get("review_state") == "dropped" or str(ev.get("reviewer_ok")).lower() == "true"
    if not settled:
        return "recheck" if corrections else "active"
    # A prior approval cannot answer a newer request. Same-day ordering is unknown.
    if date and (latest.get("date", "")[:10] <= date[:10] or row.get("context_changed")):
        return "active"
    if row.get("mapping_id"):
        decisions = [r for r in rating_events if r["record_id"] == row["mapping_id"]]
        if not decisions or decisions[-1]["decision"] not in {"approve", "reject"} or decisions[-1]["date"][:10] <= date[:10]:
            return "active"
    return "excluded" if ev.get("review_state") == "dropped" else "reviewed"


def publish(queue, requests, root):
    """Join immutable request definitions with current inputs and append-only events."""
    from collections import defaultdict

    by_id = {e["evidence_id"]: e for e in queue["registers"]["EV_evidence_register"]}
    fingerprints = evidence_index(queue["registers"])
    log = defaultdict(list)
    for event in queue["review_log"]:
        log[event["evidence_id"]].append(event)
    history = defaultdict(list)
    for event in lines(local(root, RECORDS)):
        for target in event["entry"]["targets"]:
            history[target["batch_id"], target["evidence_id"]].append((event, target))
    mappings = {r.get("mapping_id", r.get("record_id")):r for recipe in queue["recipes"].values() for rows in recipe.values() for r in rows}
    result = []
    seen = set()
    for request in requests:
        row = dict(request)
        key = (row["batch_id"], row["evidence_id"])
        require(key not in seen, "Duplicate priority request")
        seen.add(key)
        eid = row["evidence_id"]
        row["request_sha256"] = digest({k: v for k, v in request.items() if k != "context_changed"})
        mapping = mappings.get(row.get("mapping_id"))
        row["basis_sha256"] = digest([fingerprints.get(eid), log[eid], mapping,
            [r for r in queue["row_reviews"] if row.get("mapping_id") and r["record_id"] == row["mapping_id"]]])
        row["last_receipt"] = None
        row["status"] = automatic(row, by_id.get(eid), log[eid], queue["row_reviews"], queue.get("corrections", {}).get(eid))
        row["history"] = []
        for event, target in history[key]:
            matches = all(row[k] == target[k] for k in ("request_sha256", "basis_sha256"))
            row["history"].append(dict(receipt=event["receipt"], actor=event["actor"], date=event["created_at"],
                action=event["entry"]["action"], reason=event["entry"]["reason"], current=matches))
            row["last_receipt"] = event["receipt"]
        if row["history"]:
            latest = row["history"][-1]
            row["status"] = ({"restore":"active", "addressed":"addressed", "deprioritize":"deprioritized"}[latest["action"]]
                             if latest["current"] else "recheck")
        result.append(row)
    return result


def validate(entry, queue, revision):
    require(isinstance(entry, dict) and entry.get("revision") == revision and re.fullmatch(r"[0-9a-f]{40}", revision), "Invalid priority revision")
    require(set(entry) == {"kind", "revision", "action", "reason", "targets"} and entry["kind"] == "priority", "Unknown priority fields")
    require(entry["action"] in ACTIONS, "Unknown priority action")
    reason = entry["reason"]
    require(isinstance(reason, str) and 3 <= len(reason.strip()) <= 2000 and "\0" not in reason, "A recorded reason is required (3–2000 characters)")
    targets = entry["targets"]
    require(isinstance(targets, list) and 1 <= len(targets) <= 500, "Choose 1–500 review requests")
    current = {(r["batch_id"], r["evidence_id"]):r for r in queue.get("priority_requests", [])}
    seen = set()
    for target in targets:
        require(isinstance(target, dict) and set(target) == TARGET_FIELDS, "Invalid priority target")
        key = (target["batch_id"], target["evidence_id"])
        require(key not in seen and key in current, "Unknown or duplicate priority request")
        require(all(target[k] == current[key][k] for k in TARGET_FIELDS), "Request, evidence or team status changed; reload before submitting")
        seen.add(key)


def fetch(number):
    issue = intake.gh(f"repos/{intake.INBOX}/issues/{number}")
    require(issue["number"] == number and "pull_request" not in issue and issue["state"] == "open"
            and intake.reviewer_eligible(issue), "Priority receipt must be open and from an eligible contributor")
    actor = intake.original(issue)
    tag, sep, raw = issue["body"].partition("\n")
    require(sep and tag.rstrip("\r") == HEADER, "Expected an original priority receipt")
    return dict(receipt=number, actor=actor, created_at=issue["created_at"],
                body_sha256=content_digest(issue["body"].encode()), entry=json.loads(raw, object_pairs_hook=intake.unique_object))


def additions(event, history, queue, base, root):
    for old in history:
        if old["receipt"] == event["receipt"]:
            require(old == event, "Priority receipt changed")
            return False
        if old["actor"].casefold() == event["actor"].casefold() and old["entry"] == event["entry"]:
            return False
    entry = event["entry"]
    pin = entry.get("revision")
    if pin != base:
        require(isinstance(pin, str) and re.fullmatch(r"[0-9a-f]{40}", pin) and member(root, pin, base), "Unknown priority baseline")
        validate(entry, json.loads(blob(root, pin, LIVE)), pin)
    validate(dict(entry, revision=base), queue, base)
    return True


def append(root, event, base):
    history = lines(local(root, RECORDS))
    if not additions(event, history, json.loads((root / LIVE).read_bytes()), base, root):
        return False
    path = root / RECORDS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream:
        stream.write(json_bytes(event))
    return True


def verify(root, base):
    old = prior(root, base, RECORDS)
    data = local(root, RECORDS)
    require(data.startswith(old), "Historical priority records changed")
    added = data[len(old):]
    events = lines(added)
    require(len(events) <= 1 and added == b"".join(map(json_bytes, events)), "Use one canonical priority receipt per protected PR")
    history = lines(old)
    for event in events:
        queue = json.loads(blob(root, base, LIVE))
        require(event == fetch(event["receipt"]) and additions(event, history, queue, base, root), "Duplicate or misattributed priority event")
        require(not git("diff", base, "--", "registers", "row-reviews", "recipe-inputs", "operations", "configuration", cwd=root), "Submit priority changes separately from evidence, rating and method changes")
        current = json.loads((root / LIVE).read_bytes())
        require(all(current[k] == queue[k] for k in ("registers", "review_log", "row_reviews", "recipes", "membership", "corrections")), "Priority event changed scientific records")
