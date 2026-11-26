"""Publish evidence review and accepted AI outputs; never derive scientific ratings."""

import csv
import json


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def compile_candidate(producer, evidence_repo):
    from recipe_candidate import wording_index, apply_words, manifest
    from recipe_rows import evidence_index, published_reviews, TABLES
    from registers import EV, SRC, blob, content_digest
    from corrections import correction_history
    from nbs_ruralscan.schema_tools.generate import _csv_to_rows
    from t4_baseline import REVISION, PATH, SHA256, load as load_t4
    from synthesis.core import apply as accepted_effects
    from t4_synthesis.core import apply as accepted_suitability
    from configuration import overlay

    configuration = overlay(producer, evidence_repo)
    schema = producer / "schema"
    registers = {
        name: _csv_to_rows(schema / "registers" / (name + ".csv"))
        for name in ("EV_evidence_register", "SRC_source_register")
    }
    frozen = blob(evidence_repo, REVISION, PATH)
    if content_digest(frozen) != SHA256:
        raise ValueError("Historical analytical baseline checksum differs")
    baseline = json.loads(frozen)
    rows, effect_status = accepted_effects(
        evidence_repo, producer, registers, baseline["recipes"]
    )
    _, t4_status = load_t4(evidence_repo)
    rows, t4_status = accepted_suitability(evidence_repo, producer, registers, rows, t4_status)
    effect_status["baseline"] = {
        "repository": "RuralScan/evidence",
        "revision": REVISION,
        "path": PATH,
        "sha256": SHA256,
    }
    effect_status["T6E"] = (
        "historical_baseline; new economic synthesis is outside this contract"
    )
    events = wording_index(evidence_repo)
    ev_index = evidence_index(registers)
    old_index = evidence_index(baseline["registers"])
    changed_ids = {
        eid for eid, value in ev_index.items() if old_index.get(eid) != value
    }
    raw_ev = {r["evidence_id"]: r for r in read(producer / EV)}
    hashes = {
        path: content_digest((producer / path).read_bytes()) for path in (EV, SRC)
    }
    hashes.update(configuration.get("inputs", {}))
    stale = {}
    protected = {
        (s["practice"], s["table"], s["record_id"]) for s in effect_status["rows"]
    }
    protected.update((s["practice"], "T4", s["record_id"]) for s in t4_status.get("rows", []))
    for name, tables in rows.items():
        invalid = {
            r["record_id"]
            for t in ("T3", "T6", "T6E")
            for r in tables[TABLES[t]]
            if changed_ids.intersection(r.get("evidence_ids") or [])
        }
        warnings = apply_words(
            name, tables, events, ev_index, raw_ev, invalid, protected
        )
        if warnings:
            stale[name] = warnings
    live_ids = {
        r["evidence_id"]
        for r in registers["EV_evidence_register"]
        if r.get("review_state") != "dropped"
    }
    membership = {
        t: {
            eid
            for tables in rows.values()
            for r in tables[TABLES[t]]
            for eid in (r.get("evidence_ids") or [])
            if eid in live_ids
        }
        for t in ("T3", "T6")
    }

    batch_index = json.loads((producer / "docs/review/index.json").read_bytes())
    batches = {}
    for item in batch_index["batches"]:
        batch = json.loads((producer / "docs" / item["file"]).read_bytes())
        batches[item["id"]] = {
            "title": item["title"],
            "ids": [u["evidence_id"] for u in batch["units"] if "evidence_id" in u],
        }
    review_log = read(producer / "pipeline/metrics/review_log.csv")
    candidate = manifest(evidence_repo, hashes, rows, stale)
    candidate["t4_synthesis"] = t4_status
    candidate["effect_synthesis"] = effect_status
    if configuration:
        candidate["configuration"] = configuration
    queue = {
        "corrections": correction_history(evidence_repo, review_log),
        "batches": batches,
        "registers": registers,
        "review_log": review_log,
        "row_reviews": published_reviews(
            evidence_repo, read(producer / "pipeline/metrics/row_review_log.csv")
        ),
        **({"stale_wording": stale} if stale else {}),
        "recipes": rows,
        "t4_synthesis": t4_status,
        "effect_synthesis": effect_status,
        "membership": {key: sorted(ids) for key, ids in membership.items()},
    }
    from nbs_ruralscan.schema_tools.review_priorities import load_review_priorities
    from priorities import publish

    requests = load_review_priorities(producer)
    known = {(r["batch_id"], r["evidence_id"]) for r in requests}
    for batch_id, batch in batches.items():
        for eid in dict.fromkeys(batch["ids"]):
            if (batch_id, eid) not in known:
                requests.append(
                    dict(
                        batch_id=batch_id,
                        batch_label=batch["title"],
                        evidence_id=eid,
                        priority="normal",
                    )
                )
    queue["priority_requests"] = publish(queue, requests, evidence_repo)
    from family_hierarchy import coverage

    hierarchy = coverage(evidence_repo, registers["EV_evidence_register"], review_log)
    if hierarchy is not None:
        queue["evidence_hierarchy"] = hierarchy
    return queue, candidate


def build(producer, evidence_repo):
    return compile_candidate(producer, evidence_repo)[0]


def publish_files(producer, dest):
    from registers import LIVE, json_bytes
    from recipe_rows import CANDIDATE

    queue, candidate = compile_candidate(producer, dest)
    (dest / LIVE).write_bytes(json_bytes(queue))
    (dest / CANDIDATE).write_text(
        json.dumps(candidate, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return candidate
