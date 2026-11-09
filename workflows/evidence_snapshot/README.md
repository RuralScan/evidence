# Reproduce committed evidence updates

Use this workflow to make a private, read-only copy of the committed evidence tables at a particular revision, or to inspect how they changed between revisions. Live registration, corrections and review continue in CIAT.

## What the snapshot contains

The snapshot covers seven tables: the SRC source register, EV evidence register, SRCH search register, progress ledger, acquisition queue, evidence review log and recipe-row review log. Each CSV is kept byte-for-byte, including repeated events, row order, dropped evidence and empty cells. The archive stores the starting table versions and the changes introduced by every subsequent first-parent commit through the selected endpoint. Identical contents share one archive member. An intermediate version remains available even if its change was later reversed.

This covers the records present in those seven committed files. Pending decisions, browser feedback, staged intake, clarification and specialist audit files, source PDFs, library copies and generated recipe releases have separate storage. This workflow is insufficient for moving live review to a new location.

## Create and check a snapshot

Use Python 3.9 or newer, Git with the `--no-lazy-fetch` option (tested with 2.49), and a local clone containing the selected commits and blobs. Run the following in the evidence repository. Replace the example clone path with your own. Keep the working directory for private outputs outside Git repositories. The archive contains internal evidence and review history.

```sh
repo=/path/to/nbs_ruralscan
work=$(mktemp -d)
base=210b20a6b92c0dbe8a84da912457eb5f88be4cb7
target=ece8d8226fed4a0b04d155888a8b4925d8f35386
tool=workflows/evidence_snapshot/rehearse.py

python3 "$tool" create --ciat-repo "$repo" --base "$base" --target "$target" --bundle "$work/evidence.zip"
python3 "$tool" verify --ciat-repo "$repo" --base "$base" --target "$target" --bundle "$work/evidence.zip" --export-to "$work/restored"
```

The example verifies **7 tables, 15 first-parent steps, 4 changed tables and 21 distinct file versions**. The changed tables are SRC, EV, the acquisition queue and the evidence review log. The selected window includes evidence drops and reopens. The verifier independently reads the requested revisions from Git and compares the manifest, archive membership and all file bytes. A match proves faithful copying of committed records; scientific review and source acquisition are separate checks.

The export appears under `$work/restored/$target/`, with the original paths below it. To inspect an intermediate state, run `verify` again with `--at FULL_COMMIT` and another new `--export-to` directory. Omit `--export-to` for verification alone. Specify the same commit for both pins to seed a single snapshot. Choose private storage on a filesystem with hard-link support. Builds and exports use fresh destinations. A missing required table, missing Git object, off-branch interval or altered archive stops the operation.

The snapshot pins describe evidence history. For compiled recipes use the separate [recipe release check](../recipe_release/README.md), which has its own version and source revision.
