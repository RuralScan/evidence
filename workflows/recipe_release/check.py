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
from method_definitions import load_definitions  # noqa: E402
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


def match_identities(release, model):
    filename = "T0_nbs_registry.csv"
    identities = {
        path.parent.name: path
        for path in (model / "configuration/recipes").glob("*/" + filename)
    }
    require(
        set(identities) == set(release.practices),
        "Method and release practice inventories differ",
    )
    # The pinned release loader requires exactly one row with the practice's
    # nbs_id. Comparing its original bytes covers that ID and every other field.
    for practice, identity in identities.items():
        require(
            identity.read_bytes() == release.setting(practice, filename),
            f"Method and release T0 bytes differ for {practice}",
        )


def verify(
    source,
    store,
    pin,
    build,
    index_dir=None,
    *,
    check_method=False,
    method_repo=None,
    check_workbook=False,
    workbook_dir=None,
    recovered_evidence=None,
):
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
    if check_method:
        lock = pin.get("method")
        require(
            isinstance(lock, dict),
            "No method definition lock in the selected release pin",
        )
        with TemporaryDirectory(prefix="recipe-definitions-") as tmp:
            model, manifest = load_definitions(Path(tmp) / "method", lock, method_repo)
            require(
                manifest["structure_version"] == provenance["schema_version"],
                "Method and release structure versions differ",
            )
            match_identities(release, model)
        summary["method"] = {
            "manifest_revision": lock["revision"],
            "manifest_sha256": lock["sha256"],
            "definition_revision": manifest["source_revision"],
            "definition_files_verified": len(manifest["sha256"]),
            "identical_practice_definitions": list(release.practices),
        }
    if index_dir is not None:
        write_index(index_dir, render_index(release, summary, TABLE_STEMS))
    if check_workbook or workbook_dir is not None:
        from public_workbook.publish import publish

        summary["public_workbook"] = publish(
            source,
            release,
            summary,
            workbook_dir,
            check_workbook,
            recovered_evidence=recovered_evidence,
        )
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
    if method := summary.get("method"):
        lines.extend(
            [
                "",
                f"Verified {method['definition_files_verified']} method definition files at `{method['definition_revision']}`. "
                f"All {len(method['identical_practice_definitions'])} released T0 practice definitions match byte-for-byte.",
            ]
        )
    if recovery := summary.get("workbook_recovery"):
        lines.extend(
            [
                "",
                f"Workbook reproduced after interruption and retry across {recovery['appended_review_events']} recorded review events.",
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
    p.add_argument(
        "--check-method",
        action="store_true",
        help="Verify the pinned method definitions and compare all released T0 records",
    )
    p.add_argument(
        "--method-repo",
        type=Path,
        help="Use local method Git objects and enable --check-method",
    )
    workbook = p.add_mutually_exclusive_group()
    workbook.add_argument(
        "--workbook-dir",
        type=Path,
        help="Build the standalone public workbook in a new directory.",
    )
    workbook.add_argument(
        "--check-workbook",
        action="store_true",
        help="Rebuild and compare the checked-in public workbook byte-for-byte.",
    )
    workbook.add_argument(
        "--check-recovered-workbook",
        metavar="EARLIER_COMMIT",
        help="Rehearse review rollback and retry, rebuild the pinned release and check the workbook.",
    )
    args = p.parse_args()
    if args.check_recovered_workbook and (not args.ciat_repo or args.store):
        p.error(
            "--check-recovered-workbook requires --ciat-repo and a fresh release build"
        )
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
        if args.check_recovered_workbook:
            paths.extend(["/pipeline/", "/docs/", "/methodology/discovery_logs/"])
        if (
            args.check_workbook
            or args.check_recovered_workbook
            or args.workbook_dir is not None
        ):
            paths.extend(
                [
                    "/schema/registers/",
                    "/schema/recipes/",
                    "/pipeline/acquisition_queue.csv",
                ]
            )
        snapshot(source, REPOSITORY, pin["source_revision"], paths, args.ciat_repo)
        recovery = recovered_evidence = None
        if args.check_recovered_workbook:
            from workbook_recovery import recover

            recovery, recovered_evidence = recover(
                root,
                source,
                args.ciat_repo.resolve(),
                args.check_recovered_workbook,
                pin["source_revision"],
            )
        result = verify(
            source,
            args.store or root / "store",
            pin,
            args.store is None,
            args.index_dir,
            check_method=args.check_method or args.method_repo is not None,
            method_repo=args.method_repo,
            check_workbook=args.check_workbook or bool(args.check_recovered_workbook),
            recovered_evidence=recovered_evidence,
            workbook_dir=args.workbook_dir,
        )
        if recovery is not None:
            result["workbook_recovery"] = recovery
    print(json.dumps(result, indent=2) if args.json else markdown(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Recipe release check failed: {error}")
