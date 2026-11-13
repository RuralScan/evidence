"""Build the live queue from RuralScan register bytes using the pinned recipe compiler."""

import csv
from pathlib import Path


def read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def build(producer):
    from nbs_ruralscan.schema_tools.generate import _csv_to_rows
    from nbs_ruralscan.recipe import t3t6_build, t4_build
    from tempfile import TemporaryDirectory

    schema = producer / "schema"
    registers = {
        name: _csv_to_rows(schema / "registers" / (name + ".csv"))
        for name in ("EV_evidence_register", "SRC_source_register")
    }
    membership = {"T3": set(), "T6": set()}
    rows = {}
    for folder in sorted((schema / "recipes").iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        name = folder.name
        effects = t3t6_build.T3T6BuildInputs.from_root(producer, name)
        computed = t3t6_build.synthesise(
            name, t3t6_build.load_inputs(name, [], inputs=effects)
        )
        for table in membership:
            for record in computed[table]:
                ids = record.get("evidence_ids") or []
                membership[table].update(ids)
        spatial = t4_build.T4BuildInputs.from_root(producer, name)
        families = t4_build.synthesise(name, inputs=spatial, approved_only=True)
        with TemporaryDirectory() as tmp:
            output = Path(tmp).resolve()
            t4_build.write_recipe(
                name,
                families,
                read(spatial.ontology),
                inputs=spatial,
                output_dir=output,
            )
            t3t6_build.write_recipe(
                name, computed, inputs=effects, output_dir=output, dry_run=False
            )
            rows[name] = {
                file.stem: _csv_to_rows(file) for file in sorted(output.glob("*.csv"))
            }
    import json

    batch_index = json.loads((producer / "docs/review/index.json").read_bytes())
    batches = {}
    for item in batch_index["batches"]:
        batch = json.loads((producer / "docs" / item["file"]).read_bytes())
        batches[item["id"]] = {
            "title": item["title"],
            "ids": [u["evidence_id"] for u in batch["units"] if "evidence_id" in u],
        }
    return {
        "batches": batches,
        "registers": registers,
        "review_log": read(producer / "pipeline/metrics/review_log.csv"),
        "row_reviews": read(producer / "pipeline/metrics/row_review_log.csv"),
        "recipes": rows,
        "membership": {key: sorted(ids) for key, ids in membership.items()},
    }
