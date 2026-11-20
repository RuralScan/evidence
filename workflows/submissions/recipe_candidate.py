"""Compile authored wording independently of ratings and fingerprint the resulting tables."""

import json

from recipe_rows import TABLES, RECORDS, digest, basis, ident, lines, local
from registers import SEED, content_digest, json_bytes, require


def wording_index(root):
    latest = {}
    for event in lines(local(root, RECORDS["wording"])):
        e = event["entry"]
        latest[e["practice"], e["table"], e["record"]] = event
    return latest


def apply_words(practice, tables, events, ev_index, raw_ev, invalid_legacy, protected=()):
    from nbs_ruralscan.recipe import prose

    stale = []
    seen = set()
    for table, name in TABLES.items():
        for row in tables[name]:
            rid = ident(row)
            key = (practice, table, rid)
            seen.add(key)
            event = events.get(key)
            if not event:
                if table != "T4" and rid in invalid_legacy:
                    stale.append(
                        dict(
                            table=table,
                            record=rid,
                            reason="Evidence changed since archived wording",
                        )
                    )
                continue
            if key in protected:
                stale.append(dict(table=table, record=rid, receipt=event["receipt"],
                                  reason="Accepted scientific output requires a new synthesis proposal for wording changes"))
                continue
            e = event["entry"]
            if basis(row, table, ev_index) != e["basis_sha256"]:
                stale.append(
                    dict(
                        table=table,
                        record=rid,
                        receipt=event["receipt"],
                        reason="Evidence or analytical row changed",
                    )
                )
                continue
            if table == "T4":
                row["justification"] = e["wording"]["justification"]
            else:
                flags = prose.check_prose([row], table, {rid: e["wording"]}, raw_ev)
                require(
                    not flags,
                    f"Wording failed source-account checks for {rid}: {flags}",
                )
                entry = dict(
                    **e["wording"],
                    evidence_ids=e["evidence_ids"],
                    written=event["created_at"][:10],
                    writer=event["actor"],
                )
                entry["class"] = prose._class_of(row)
                applied, _ = prose.apply_prose([row], table, {rid: entry})
                require(applied == 1, "Compiler did not apply authored wording")
    for key, event in events.items():
        if key[0] == practice and key not in seen:
            stale.append(
                dict(
                    table=key[1],
                    record=key[2],
                    receipt=event["receipt"],
                    reason="Row no longer published",
                )
            )
    return stale


def manifest(root, hashes, tables, stale):
    return {
        "format": "ruralscan.recipe-candidate.v1",
        "producer": {"workflow": "ai_scientific_synthesis", "code_role": "validate_and_package",
                     "historical_scoring_retired": True},
        "inputs": dict(
            hashes,
            **{RECORDS["wording"]: content_digest(local(root, RECORDS["wording"]))},
        ),
        "tables": {
            p: {
                t: {"rows": len(rows), "sha256": digest(rows)} for t, rows in ts.items()
            }
            for p, ts in tables.items()
        },
        "stale_wording": stale,
    }


def changes(before, after):
    """Show changed fields by stable row ID, regardless of array order."""
    for p in sorted(before.keys() | after.keys()):
        for t in sorted(before.get(p, {}).keys() | after.get(p, {}).keys()):
            a = {ident(r): r for r in before.get(p, {}).get(t, [])}
            b = {ident(r): r for r in after.get(p, {}).get(t, [])}
            for rid in sorted(a.keys() | b.keys()):
                x, y = a.get(rid, {}), b.get(rid, {})
                if x != y:
                    yield {
                        "practice": p,
                        "table": t,
                        "record": rid,
                        "change": "added"
                        if not x
                        else "removed"
                        if not y
                        else "changed",
                        "fields": {
                            k: {"before": x.get(k), "after": y.get(k)}
                            for k in sorted(x.keys() | y.keys())
                            if x.get(k) != y.get(k)
                        },
                    }


if __name__ == "__main__":
    import argparse
    from registers import ROOT, LIVE, blob

    parser = argparse.ArgumentParser(
        description="Compare two Git editions of the compiled tables."
    )
    parser.add_argument("before")
    parser.add_argument("after")
    args = parser.parse_args()
    for diff in changes(
        *(
            json.loads(blob(ROOT, pin, LIVE))["recipes"]
            for pin in (args.before, args.after)
        )
    ):
        print(json.dumps(diff, ensure_ascii=False))
