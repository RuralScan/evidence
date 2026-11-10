"""Compare the records addressed by one pending batch before either replay."""

from collections import defaultdict
import csv

from preview import EV, LOG, require


def evidence_rows(root):
    with (root / EV).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {row["evidence_id"]: row for row in rows}
    require(
        len(rows) == len(by_id) and "" not in by_id,
        "Evidence IDs must be present and unique",
    )
    return by_id


def batch_changes(before, after, decision_ids, pending_events, old_events, new_events):
    # A pending reply may carry only an issue ID. Use explicit claim links
    # from either committed thread, including ones removed at the target.
    linked = defaultdict(set)
    for event in [*old_events, *new_events, *pending_events]:
        linked[event["issue_id"]].update(event.get("evidence_ids", []))
    saved_issues = {e["issue_id"] for e in pending_events}
    ids = set(decision_ids)
    for issue in saved_issues:
        ids.update(linked[issue])
    old_rows, new_rows = evidence_rows(before), evidence_rows(after)
    changes = {"added": [], "modified": [], "removed": [], "missing_at_both": []}
    for eid in sorted(ids):
        if eid not in old_rows:
            changes["added" if eid in new_rows else "missing_at_both"].append(eid)
        elif eid not in new_rows:
            changes["removed"].append(eid)
        elif old_rows[eid] != new_rows[eid]:
            changes["modified"].append(eid)

    def review_log(root):
        by_claim = defaultdict(list)
        with (root / LOG).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                eid = row["evidence_id"]
                if eid in ids:
                    by_claim[eid].append(row)
        return by_claim

    old_log, new_log = review_log(before), review_log(after)
    changed_log = sorted(eid for eid in ids if old_log[eid] != new_log[eid])

    # A reply need only name the issue. Compare the complete ordered thread
    # whenever another event explicitly links it to a claim in this batch.
    relevant = saved_issues | {
        issue for issue, claims in linked.items() if not claims.isdisjoint(ids)
    }

    def threads(events):
        by_issue = defaultdict(list)
        for event in events:
            if event["issue_id"] in relevant:
                by_issue[event["issue_id"]].append(event)
        return by_issue

    old_threads, new_threads = threads(old_events), threads(new_events)
    changed_threads = {i for i in relevant if old_threads[i] != new_threads[i]}
    return {
        "batch_evidence_ids": len(ids),
        "evidence_row_changes": changes,
        "review_history_changed_ids": changed_log,
        "clarification_history_changed_ids": sorted(
            {eid for issue in changed_threads for eid in linked[issue] if eid in ids}
        ),
        "pending_issues_without_linked_claims": sum(
            not linked[i] for i in saved_issues
        ),
        "pending_issues_with_changed_history": len(changed_threads & saved_issues),
    }
