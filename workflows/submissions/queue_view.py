"""Build the live queue, effect candidates and explicitly frozen T4 baseline."""

import csv
import json
from classification import compiler_record
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def compile_candidate(producer, evidence_repo):
    from recipe_candidate import wording_index, effects_inputs, apply_words, manifest
    from recipe_rows import evidence_index, published_reviews, SOURCE_PROGRESS
    from registers import EV, SRC, SEED, blob, content_digest, index, rows as csv_rows
    from corrections import correction_history
    from nbs_ruralscan.schema_tools.generate import _csv_to_rows
    from nbs_ruralscan.recipe import t3t6_build
    from t4_baseline import load as load_t4, TABLE as T4_TABLE
    from tempfile import TemporaryDirectory

    from configuration import overlay

    configuration = overlay(producer, evidence_repo)
    t4_rows, t4_status = load_t4(evidence_repo)
    schema = producer / "schema"
    registers = {
        name: _csv_to_rows(schema / "registers" / (name + ".csv"))
        for name in ("EV_evidence_register", "SRC_source_register")
    }
    membership = {"T3": set(), "T6": set()}
    rows = {}
    events = wording_index(evidence_repo)
    ev_index = evidence_index(registers)
    old_ev = index(
        json.loads(blob(producer, SEED, str(Path(EV).with_suffix(".json")))),
        "evidence_id",
    )
    current_ev = registers["EV_evidence_register"]
    changed_ids = {
        r["evidence_id"] for r in current_ev if compiler_record(r) != old_ev.get(r["evidence_id"])
    }
    old_sources = index(csv_rows(blob(producer, SEED, SRC)), "source_id")
    # Source assessment/locator changes also invalidate prose; extraction progress does not.
    changed_sources = {
        r["source_id"]
        for r in read(producer / SRC)
        if any(
            v != old_sources.get(r["source_id"], {}).get(k)
            for k, v in r.items()
            if k not in SOURCE_PROGRESS
        )
    }
    changed_ids.update(
        e["evidence_id"] for e in current_ev if e["source_id"] in changed_sources
    )
    raw_ev = index(read(producer / EV), "evidence_id")
    hashes = {EV: content_digest((producer / EV).read_bytes())}
    stale = {}
    for folder in sorted((schema / "recipes").iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        name = folder.name
        effects = t3t6_build.T3T6BuildInputs.from_root(producer, name)
        for path in effects.paths():
            if path != effects.evidence and path.is_file():
                key = path.relative_to(producer).as_posix()
                if key not in hashes:
                    hashes[key] = content_digest(path.read_bytes())
        with TemporaryDirectory() as tmp:
            output = Path(tmp).resolve()
            effects, invalid = effects_inputs(effects, output, current_ev, changed_ids)
            computed = t3t6_build.synthesise(
                name, t3t6_build.load_inputs(name, [], inputs=effects)
            )
            for table in membership:
                for record in computed[table]:
                    membership[table].update(record.get("evidence_ids") or [])
            t3t6_build.write_recipe(
                name, computed, inputs=effects, output_dir=output, dry_run=False
            )
            rows[name] = {
                file.stem: _csv_to_rows(file) for file in sorted(output.glob("*.csv"))
            }
            rows[name][T4_TABLE] = t4_rows[name]
            # The native sidecar also rejects changed evidence membership or class.
            inherited = json.loads(effects.prose.read_bytes())
            for table in ("T3", "T6", "T6E"):
                for record in computed[table]:
                    rid = record["record_id"]
                    if rid in inherited and (record.get("justification") or {}).get(
                        "prose_pending"
                    ):
                        invalid.add(rid)
            warnings = apply_words(name, rows[name], events, ev_index, raw_ev, invalid)
            if warnings:
                stale[name] = warnings

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
        "membership": {key: sorted(ids) for key, ids in membership.items()},
    }
    from nbs_ruralscan.schema_tools.review_priorities import load_review_priorities
    from priorities import publish

    requests = load_review_priorities(producer)
    known = {(r["batch_id"], r["evidence_id"]) for r in requests}
    for batch_id, batch in batches.items():
        for eid in dict.fromkeys(batch["ids"]):
            if (batch_id, eid) not in known:
                requests.append(dict(batch_id=batch_id, batch_label=batch["title"], evidence_id=eid, priority="normal"))
    queue["priority_requests"] = publish(queue, requests, evidence_repo)
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
