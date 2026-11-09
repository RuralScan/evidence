# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.4.6", "requests==2.34.2"]
# ///

"""Rebuild or verify a pinned candidate recipe release and report dashboard counts."""

import argparse
import contextlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from git_snapshot import require, revision, snapshot  # noqa: E402
from recipe_index import render_index, write_index  # noqa: E402

REPOSITORY = "https://github.com/CIAT/nbs_ruralscan.git"
COLUMNS = (
    "T3",
    "T4",
    "T6",
    "T6E",
    "T4 with options",
    "T4 with selected function",
    "Spatially validated T4",
)


def practice_counts(release, practice):
    tables = {table: release.table(practice, table) for table in COLUMNS[:4]}
    counts = {table: len(records) for table, records in tables.items()}
    mappings = {row["mapping_id"] for row in tables["T4"]}
    report = json.loads(release.read_bytes(f"tables/{practice}/T4_readiness.json"))
    rows = [r for r in report["rows"] if r["rule_id"] in mappings]
    reported = {row["rule_id"] for row in rows}
    require(
        reported == mappings and len(rows) == len(mappings) == counts["T4"],
        "T4 and readiness inventories differ",
    )
    counts["T4 with options"] = sum(bool(r["functions"]) for r in rows)
    counts["T4 with selected function"] = sum(
        bool(r["readiness"]["effective_function_id"]) for r in rows
    )
    counts["Spatially validated T4"] = sum(
        r["readiness"]["execution_ready"] is True for r in rows
    )
    return counts


def verify(source, store, pin, build, index_dir=None):
    # Use the producer and reader from the same immutable source revision.
    sys.path.insert(0, str(source / "src"))
    from nbs_ruralscan.runtime.schema_loader import TABLE_STEMS, load_recipe_release

    if build:
        from nbs_ruralscan.recipe.publish_release import publish_recipes

        with contextlib.redirect_stdout(sys.stderr):
            generated = publish_recipes(source, store)
        require(
            generated.release_id == pin["release_id"],
            "Rebuilt release differs from expected ID",
        )
    release = load_recipe_release(store, pin["release_id"])
    provenance = json.loads(release.read_bytes("provenance.json"))
    require(
        provenance["source_revision"] == pin["source_revision"],
        "Release source revision differs",
    )
    require(
        list(release.practices) == sorted(pin["practices"]),
        "Release practice inventory differs",
    )
    rows = {p: practice_counts(release, p) for p in release.practices}
    summary = {
        "source_revision": pin["source_revision"],
        "release_id": release.release_id,
        "practices": rows,
        "totals": {k: sum(row[k] for row in rows.values()) for k in COLUMNS},
    }
    if index_dir is not None:
        write_index(index_dir, render_index(release, summary, TABLE_STEMS))
    return summary


def markdown(summary):
    lines = [
        "# Candidate recipe tables",
        "",
        f"Source revision `{summary['source_revision']}` · release `{summary['release_id']}`.",
        "",
        f"{sum(summary['totals'][k] for k in COLUMNS[:4])} analytical rows across {len(summary['practices'])} practices.",
        "",
        "| Practice | " + " | ".join(COLUMNS) + " |",
        "|---|" + "---:|" * len(COLUMNS),
    ]
    for name, counts in [*summary["practices"].items(), ("Total", summary["totals"])]:
        lines.append(
            "| "
            + name.replace("_", " ").capitalize()
            + " | "
            + " | ".join(str(counts[k]) for k in COLUMNS)
            + " |"
        )
    lines.extend(
        [
            "",
            "T3 counts hazard-response rows, T4 suitability mappings, T6 scorecard rows and T6E economic-profile rows. "
            "Totals count rows across practice tables. The readiness columns describe the same T4 rows and overlap. A source may contribute to several rows.",
            "",
            "The final three columns count T4 mappings with a function option, a selected function and execution readiness recorded by the producer, respectively. "
            "Reference-only entries outside the T4 tables are excluded.",
        ]
    )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--ciat-repo",
        type=Path,
        help="Local producer clone containing the pinned revision",
    )
    p.add_argument(
        "--store",
        type=Path,
        help="Verify an existing release store read-only; default rebuilds in temporary storage",
    )
    p.add_argument(
        "--pin",
        type=Path,
        default=HERE / "pin.json",
        help="Trusted producer revision, release ID and practice list",
    )
    p.add_argument("--json", action="store_true", help="Emit machine-readable counts")
    p.add_argument(
        "--index-dir",
        type=Path,
        help="Write a browsable recipe index to a new directory",
    )
    args = p.parse_args()
    pin = json.loads(args.pin.read_bytes())
    revision(pin["source_revision"])
    require(
        re.fullmatch("[a-f0-9]{64}", pin["release_id"]), "Expected a full release ID"
    )
    with TemporaryDirectory(prefix="recipe-check-") as tmp:
        root = Path(tmp)
        source = root / "source"
        paths = (
            ["/src/"]
            if args.store
            else [
                "/src/",
                "/schema/",
                "/pipeline/t4_audit/agroforestry/importance_2026-10-21/source_weight_trees.csv",
            ]
        )
        snapshot(source, REPOSITORY, pin["source_revision"], paths, args.ciat_repo)
        result = verify(
            source,
            args.store or root / "store",
            pin,
            args.store is None,
            args.index_dir,
        )
    print(json.dumps(result, indent=2) if args.json else markdown(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Recipe release check failed: {error}")
