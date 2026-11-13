"""Verify applied-PR lineage and rebuild the published queue from destination records."""

import argparse
from pathlib import Path
import sys
import json
import shutil
from tempfile import TemporaryDirectory

from registers import (
    ROOT,
    SEED,
    FIRST,
    EV,
    SRC,
    LOG,
    JOURNAL,
    LIVE,
    blob,
    index,
    rows,
    json_bytes,
    content_digest,
    git,
    require,
    snapshot,
)

MUTABLE = {EV, SRC, LOG}


def check(ciat, *, base=None):
    manifest = json.loads((ROOT / "registers/manifest.json").read_bytes())
    require(
        (ROOT / "registers/manifest.json").read_bytes()
        == blob(ROOT, FIRST, "registers/manifest.json"),
        "Migration manifest changed",
    )
    applied = json.loads((ROOT / JOURNAL).read_bytes())
    expected = set(manifest["files"]) | {"manifest.json", "applied-receipts.json"}
    actual = {
        p.relative_to(ROOT / "registers").as_posix()
        for p in (ROOT / "registers").rglob("*")
        if p.is_file()
    }
    require(expected == actual, "Unexpected register inventory")
    for name, meta in manifest["files"].items():
        if name not in MUTABLE or not applied:
            require(
                content_digest((ROOT / "registers" / name).read_bytes())
                == meta["sha256"],
                f"Unexpected change to {name}",
            )
    if base:

        def previous(path):
            return blob(ROOT, base, path)

        had_journal = bool(git("ls-tree", base, "--", JOURNAL, cwd=ROOT))
        prior = json.loads(previous(JOURNAL)) if had_journal else {}
        require(
            all(applied.get(k) == v for k, v in prior.items()),
            "Removed or altered an applied receipt",
        )
        new = {k: v for k, v in applied.items() if k not in prior}
        old_ev = index(rows(previous("registers/" + EV)), "evidence_id")
        old_src = index(rows(previous("registers/" + SRC)), "source_id")
        ev = index(rows((ROOT / "registers" / EV).read_bytes()), "evidence_id")
        src = index(rows((ROOT / "registers" / SRC).read_bytes()), "source_id")
        require(
            old_ev.keys() <= ev.keys() and old_src.keys() == src.keys(),
            "Removed finding or changed source inventory",
        )
        prior_log = previous("registers/" + LOG)
        current_log = (ROOT / "registers" / LOG).read_bytes()
        require(
            current_log.startswith(prior_log), "Rewrote historical finding decisions"
        )
        ids = set()
        source_ids = set()
        if new:
            import intake
            from handoff import same_value, scientific_fields
            from registers import scientific_fields_dict, cohort

            cohorts = {}
            from registers import authenticated, participants

            public = authenticated(intake.submissions())
            target_ids = set()
            for k, record in new.items():
                n = int(k)
                item = public.get(n)
                require(
                    item
                    and record["base"] == base
                    and record["digest"] == item["digest"]
                    and record["actor"] == item["actor"]
                    and record["revision"] == item["entry"]["revision"]
                    and record["kind"] == item["entry"]["kind"],
                    f"Invalid, edited or stale receipt #{n}. Rebuild on latest main.",
                )
                entry = item["entry"]
                pin = entry["revision"]
                if pin not in cohorts:
                    cohorts[pin] = cohort(ROOT, base, ciat, pin)
                seen_ev, seen_src = cohorts[pin]
                if entry["kind"] == "extraction":
                    require(
                        "approved-extraction" in item["labels"],
                        f"Unapproved extraction #{n}",
                    )
                    for u in entry["payload"]:
                        eid, sid = u["evidence_id"], u["source_id"]
                        require(
                            eid not in ids
                            and ev[eid]["source_id"] == sid
                            and seen_ev.get(eid) == old_ev.get(eid)
                            and seen_src.get(sid) == old_src.get(sid),
                            "Stale or overlapping extraction",
                        )
                        actual_science = scientific_fields(ev[eid])
                        proposed = scientific_fields_dict(u)
                        if eid in old_ev and old_ev[eid] != ev[eid]:
                            # Reopen writes a review attribution; prove the scientific changes separately.
                            actual_science.pop("attribution", None)
                            proposed.pop("attribution", None)
                        require(
                            same_value(actual_science, proposed),
                            "Register differs from approved extraction",
                        )
                        if eid not in old_ev or old_ev[eid] != ev[eid]:
                            require(
                                ev[eid]["reviewer_ok"].lower() in {"", "false"}
                                and ev[eid]["review_state"] == "",
                                "Extraction granted sign-off or changed quarantine",
                            )
                        ids.add(eid)
                        source_ids.add(sid)
                else:
                    for eid in participants({n: item}, {n}, set())[n]:
                        require(
                            eid in old_ev
                            and seen_ev.get(eid) == old_ev[eid]
                            and seen_src.get(old_ev[eid]["source_id"])
                            == old_src[old_ev[eid]["source_id"]],
                            "Stale finding vote",
                        )
                        target_ids.add(eid)
            # All related currently authenticated ballots participate, including later
            # challenges filed between preparing and checking the PR.
            related = participants(public, set(), target_ids)
            require(
                all(str(n) in applied for n in related),
                "New related vote arrived; rebuild consensus",
            )
            verdicts = {}
            for n in related:
                from intake import VERDICT

                entry = public[n]["entry"]
                ballots = (
                    [entry["payload"]]
                    if entry["kind"] == "vote"
                    else rows(entry["payload"].encode())
                )
                for ballot in ballots:
                    eid = ballot["evidence_id"]
                    if eid in target_ids:
                        verdict = VERDICT[ballot["decision"].strip().lower()]
                        require(
                            verdicts.setdefault(eid, verdict) == verdict,
                            "Opposing votes remain pending",
                        )
                        row = ev[eid]
                        require(
                            (row["reviewer_ok"].lower() == "true") == (verdict == "ok")
                            and (row["review_state"] == "dropped")
                            == (verdict == "drop"),
                            "Register disagrees with vote",
                        )
                        protected = set(row) - {
                            "reviewer_ok",
                            "review_state",
                            "attribution",
                        }
                        require(
                            all(row[f] == old_ev[eid][f] for f in protected),
                            "Vote changed scientific fields",
                        )
            ids.update(target_ids)
        require(
            all(row == old_ev.get(eid) or eid in ids for eid, row in ev.items()),
            "Finding changed without its receipt",
        )
        require(
            all(row == old_src[sid] or sid in source_ids for sid, row in src.items()),
            "Unrelated source changed",
        )
        require(
            all(
                r["evidence_id"] in ids
                for r in rows(current_log)[len(rows(prior_log)) :]
            ),
            "Unrelated review event",
        )
        if not ids:
            require(
                prior_log == current_log
                and all(
                    previous("registers/" + p) == (ROOT / "registers" / p).read_bytes()
                    for p in MUTABLE
                ),
                "Register bytes changed without receipts",
            )
        for sid in source_ids:
            allowed = {
                "vars_extracted",
                "extraction_status",
                "extraction_date",
                "extraction_run_id",
                "extractor",
            }
            require(
                all(
                    src[sid][k] == old_src[sid][k]
                    for k in old_src[sid].keys() - allowed
                ),
                "Extraction changed source identity or locator",
            )
    with TemporaryDirectory() as tmp:
        producer = Path(tmp).resolve() / "engine"
        snapshot(
            producer,
            "",
            SEED,
            [
                "/src/",
                "/schema/",
                "/pipeline/",
                "/docs/review/*.json",
                "!/docs/review/*/",
            ],
            ciat,
        )
        for name in manifest["files"]:
            if (producer / name).is_file():
                shutil.copyfile(ROOT / "registers" / name, producer / name)
        sys.path.insert(0, str(producer / "src"))
        from queue_view import build

        require(
            (ROOT / LIVE).read_bytes() == json_bytes(build(producer)),
            "Published review queue differs from current registers",
        )
    print(
        "Verified register provenance and rebuilt T3, T4, T6 and T6E for six practices."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciat-repo", required=True, type=Path)
    parser.add_argument("--base")
    args = parser.parse_args()
    check(args.ciat_repo, base=args.base)
