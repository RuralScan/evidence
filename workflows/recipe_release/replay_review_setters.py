# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.4.6", "requests==2.34.2"]
# ///
"""Replay the CIAT headline sensitivity assessment on the workbook's original compiler.

Each independent run omits exactly one contributing finding from one practice.
The assessment revision supplies the headline selector and candidate population.
Published ratings and their evidence membership must match the baseline run.
"""

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import redirect_stdout
from functools import lru_cache
import importlib.util
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from git_snapshot import snapshot

ASSESSMENT = "e930734c0705406f14757ee3e62e90537e8d4095"
REPO = "https://github.com/CIAT/nbs_ruralscan.git"
TABLES = {"T3": "T3_nbs_hazard_farming.json", "T6": "T6_nbs_scorecard.json"}


@lru_cache(maxsize=1)
def modules(producer, assessment):
    sys.path.insert(0, str(producer / "src"))

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    return (
        load("producer_synth", producer / "scripts/synthesise-t3t6.py"),
        load("assessment", assessment / "scripts/build-rating-setters.py"),
    )


@lru_cache(maxsize=1)
def baseline(producer, assessment, practice):
    synth, method = modules(producer, assessment)
    inputs = synth.load_inputs(practice, [])
    with redirect_stdout(io.StringIO()):
        result = synth.synthesise(practice, inputs)
    heads = {t: method._headline(result, t) for t in TABLES}
    pools = {t: method._ids(result, t) for t in TABLES}
    for table, name in TABLES.items():
        published = {
            table: json.loads(
                (producer / "schema/recipes" / practice / name).read_text()
            )
        }
        if heads[table] != method._headline(published, table) or pools[
            table
        ] != method._ids(published, table):
            raise ValueError(
                f"Historical baseline differs from published {practice} {table}"
            )
    return inputs, heads, pools


def assess(task):
    producer, assessment, practice, ids = task
    synth, method = modules(producer, assessment)
    inputs, heads, pools = baseline(producer, assessment, practice)
    changed = defaultdict(list)
    for eid in ids:
        filtered = dict(
            inputs, units=[u for u in inputs["units"] if u.evidence_id != eid]
        )
        with redirect_stdout(io.StringIO()):
            output = synth.synthesise(practice, filtered)
        for t in TABLES:
            if eid in pools[t]:
                after = method._headline(output, t)
                for rid, before in heads[t].items():
                    if after.get(rid) != before:
                        changed[rid].append(eid)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ciat-repo", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    pin = json.loads((HERE / "pin.json").read_text())
    with TemporaryDirectory() as temp:
        producer, assessment = Path(temp) / "producer", Path(temp) / "assessment"
        snapshot(
            producer,
            REPO,
            pin["source_revision"],
            ["/src/", "/schema/", "/scripts/synthesise-t3t6.py"],
            args.ciat_repo,
        )
        snapshot(
            assessment,
            REPO,
            ASSESSMENT,
            ["/scripts/build-rating-setters.py"],
            args.ciat_repo,
        )
        by_record = {}
        tasks = []
        tested = {}
        for practice in pin["practices"]:
            _, heads, pools = baseline(producer, assessment, practice)
            by_record.update({rid: [] for table in heads.values() for rid in table})
            ids = sorted(set.union(*pools.values()))
            tested[practice] = len(ids)
            tasks.extend(
                (producer, assessment, practice, ids[i : i + 40])
                for i in range(0, len(ids), 40)
            )
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            for changes in executor.map(assess, tasks):
                for rid, ids in changes.items():
                    by_record[rid].extend(ids)
        for ids in by_record.values():
            ids.sort()
        result = dict(
            producer_revision=pin["source_revision"],
            assessment_revision=ASSESSMENT,
            release_id=pin["release_id"],
            tested_findings_per_practice=tested,
            by_record=by_record,
        )
        args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(
            f"Verified {len(by_record)} headline ratings across {sum(tested.values())} practice/finding removals."
        )


if __name__ == "__main__":
    main()
