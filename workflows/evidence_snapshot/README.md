# Reproduce committed evidence updates

Use this workflow to make a private, read-only copy of the committed evidence tables at a particular revision, or to inspect how they changed between revisions. Live registration, corrections and review continue in CIAT.

## What the snapshot contains

The default `core` profile covers seven tables: the SRC source register, EV evidence register, SRCH search register, progress ledger, acquisition queue, evidence review log and recipe-row review log. Each CSV is kept byte-for-byte, including repeated events, row order, dropped evidence and empty cells. The archive stores the starting table versions and the changes introduced by every subsequent first-parent commit through the selected endpoint. Identical contents share one archive member. An intermediate version remains available even if its change was later reversed.

The optional `review-support` profile adds the four committed files described below. Pending decisions, browser feedback, staged intake, specialist audit files, source PDFs, library copies and generated recipe releases have separate storage. Live review requires those additional inputs.

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

## Restore committed review-support records

Use `--profile review-support` for both creation and verification to include these records alongside the seven core tables.

| File | What it records |
|---|---|
| `pipeline/metrics/clarification_log.json` | Recorded clarification events, including their ordering. |
| `pipeline/metrics/gaps.csv` | Reported missing evidence. A header-only file contains zero recorded reports. |
| `pipeline/cited_originals.csv` | Citation-chasing trace register for original sources referenced in existing evidence. Acquisition decisions reside in the acquisition queue. |
| `pipeline/review_priorities.csv` | Requests for prioritised review, including the referenced evidence fingerprints. The dashboard reads this file to build its priority view. |

The seven core tables must exist at every revision. Each of the four support files can be absent in an earlier revision, added, changed or removed. A missing file has a null inventory entry and is absent from that revision’s export. Existing empty and header-only files retain their bytes. Selecting the default profile still verifies existing seven-table archives.

For an interval that includes the first priority file and subsequent changes to the citation-chasing records, reuse `repo`, `work` and `tool` from the previous example:

```sh
base=eb61805191880b2856c374230dadb73f4e40b308
target=c7cf745cfa6a02b9ce114cdfbeca3c4e71681fca
python3 "$tool" create --profile review-support --ciat-repo "$repo" --base "$base" --target "$target" --bundle "$work/support.zip"
python3 "$tool" verify --profile review-support --ciat-repo "$repo" --base "$base" --target "$target" --bundle "$work/support.zip" --export-to "$work/support-restored"
```

The verifier reports **11 scoped paths, 28 first-parent steps, 6 changed paths and 31 distinct file versions**. The base contains ten files. The priority register first appears with six entries at `04300b18c25059773bdabec7f4ac73b01654e3f0`. To reproduce that state, add `--at` with this full commit and choose a new export directory. Throughout this example, the gap register contains its header and zero reports. This count describes recorded reports only.

The snapshot pins describe evidence history. For compiled recipes use the separate [recipe release check](../recipe_release/README.md), which has its own version and source revision.

## Advance a private copy by one interval

Start with a verified export at the base commit. A delta archive records each first-parent change and carries each new file version once. If a file reverts to its starting contents, the export reuses the verified seed bytes. The unit of transfer is a whole changed file, which preserves event order, corrections, drops and repeated rows.

For a worked interval, set the following variables in the evidence repository. Use a local producer clone containing both commits and their Git objects.

```sh
repo=/path/to/nbs_ruralscan
work=$(mktemp -d)
tool=workflows/evidence_snapshot/rehearse.py
base=23ce026d885f3a29a272ec693d4d10bf9bf8bf55
target=e5c8da02e72810956cfd179cb32cd137fc4ba398
```

If starting from scratch, create the base export. If you already have the verified revision directory, set `seed` to its path and skip these three commands.

```sh
python3 "$tool" create --profile review-support --ciat-repo "$repo" \
  --base "$base" --target "$base" --bundle "$work/seed.zip"
python3 "$tool" verify --profile review-support --ciat-repo "$repo" \
  --base "$base" --target "$base" --bundle "$work/seed.zip" --export-to "$work/seed"
seed="$work/seed/$base"
```

```sh
python3 "$tool" create-delta --profile review-support --ciat-repo "$repo" \
  --base "$base" --target "$target" --bundle "$work/changes.zip"
python3 "$tool" apply-delta --profile review-support --ciat-repo "$repo" \
  --base "$base" --target "$target" --bundle "$work/changes.zip" \
  --seed "$seed" --export-to "$work/advanced"
```

The result is a new revision directory at `$work/advanced/$target`. Each exported file is read-only. Keep the base export for rollback or to repeat the comparison. To retry, select a fresh output directory. The verifier compares the entire seed inventory and all archive members against the two Git pins before publishing. A seed for a different revision, a modified file or an unexpected extra file stops the operation.

This interval spans seven commits. Four of the eleven scoped paths changed, and the archive contains eight new file versions. The target adds three source records and ten evidence records. Sixty-five existing evidence records changed, including two drops. The acquisition queue has three updated records, and nine events were appended to the evidence review log. All 229 search records match the seed. Browser drafts, staged files and compiled recipe releases have separate checkpoints.

## Register migration seed

[Browse the registers](../../registers/) or read the [machine-readable manifest](../../registers/manifest.json). This is the starting copy for migration at [CIAT #691](https://github.com/CIAT/nbs_ruralscan/pull/691), commit `e43c42bd581dba791ce1f1697b6b41952ab0cfe3`. Public issues already receive submissions in RuralScan/evidence. CIAT retains authority to update the registers during this preparation stage.

The manifest gives each file's source path, SHA-256, size and CSV record count, plus the exact Git objects for external inputs. The seed includes the seven core tables and four review-support files listed above, six configuration registers, rating setters, the ranking and flags, benchmark divergences, and the extraction sweep and learning history. Finding decisions, rating reviews and method decisions have separate tables. The method ledger preserves every scientific decision ID, question, option, recommendation, recorded outcome and status. Its public copy omits the named task-assignment column (`owner`). The manifest records hashes for both representations. All other files match the source bytes exactly.

The pinned source commit supplies the remaining compiler inputs, historical extraction rules, review batches and archive. Open a source path at that commit to reproduce it, including the [review batch index](https://github.com/CIAT/nbs_ruralscan/blob/e43c42bd581dba791ce1f1697b6b41952ab0cfe3/docs/review/index.json) and [answered holds](https://github.com/CIAT/nbs_ruralscan/blob/e43c42bd581dba791ce1f1697b6b41952ab0cfe3/docs/review/ratings_top60_holds_answered_2026-11-13.json). Raw source files continue to use their existing library locators.

### Verify locally

Use a CIAT clone or bare repository containing the pinned commit. Python's standard library can verify the transferred records. Add `--rebuild` in the evidence-checks Python environment to apply the destination register bytes to a disposable copy of the pinned compiler and compare the T3, T4, T6 and T6E outputs for all six practices with their audited tables.

```sh
python3 workflows/evidence_snapshot/verify_registers.py --ciat-repo /path/to/nbs_ruralscan --rebuild
```

To reproduce the directory independently, pass `--export-to /path/to/new-folder`. The command refuses to overwrite an existing destination. The initial parity check catches changed or missing records while CIAT is still the writer. At the official switch, preserve this seed by its RuralScan Git commit and validate later changes as reviewed deltas against it. The switch requires reconciliation of any newer CIAT writes, the destination apply path and protection of both repositories' register paths.

### Reconciliation at the merge

Compared with parent `69f53985`, the evidence register gained seven IDs, changed 83 existing records and removed zero. All 6,839 findings resolve to the 834 registered sources. The search register has 252 records. The finding log grew from 3,993 to 4,083 events, with its original sequence intact. The 90 additional events include the 60 Top 60 votes (23 approved, nine soft-dropped, 28 held), 21 further attributed corrections, eight AI correction events and one supersession. The 37 rating-review events are byte-identical to the parent. The method ledger moved 22 Round 7 questions to decided, parked three, and added 18 open Round 8 questions.

The 28 original holds correspond to 29 cards awaiting a human response. The Thierfelder finding was superseded by two successor findings. Its original review and soft-dropped evidence record remain traceable. The remaining 27 held IDs occur directly in the answered batch. A source correction or an AI answer does not establish human sign-off. The prospective T4 Evans correction stays staged outside these committed records.
