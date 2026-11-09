# Preview a browser review CSV

Use this when a reviewer has downloaded a CSV from an evidence or compiled-row review page. The command runs the actual importer on temporary copies, records the changes to review history and repeats the import to measure retry behaviour. Only the aggregate JSON receipt leaves the temporary directory. Live review and submission continue in CIAT. For saved dashboard decisions in JSON, use the separate [decision preview](../review_preview/README.md).

## Run the examples

Use Git and Python 3.12. From the evidence repository root run:

```sh
uv run --no-project --python 3.12 python -I -B workflows/review_exports/check_export.py --example
```

The first run fetches pinned CIAT code and the example table inputs. For offline use, add `--offline` immediately after `uv run` and append `--ciat-repo /path/to/nbs_ruralscan` to use local Git objects.

| Example | First import on the copy | Second import |
|---|---|---|
| [Evidence decisions](example/evidence.csv) | Four events across three evidence IDs. Two reviewers disagree on one ID. | Two more events for that ID. Its hold and approval are replayed in reviewer order. |
| [Compiled-row decisions](example/rows.csv) | Two events. The two holds share a key even though the note differs. | Zero new events; the log bytes match. |

The evidence example uses three synthetic evidence records. The row example uses synthetic votes on two actual compiled row IDs at the engine revision.

## Preview one private export

Restore either committed snapshot profile, then use its revision-named subdirectory and a separate private copy of the browser CSV outside Git. The local clone must contain the engine commit and the selected record revision. The checkout must support Git’s `--no-lazy-fetch` option. [Restore a snapshot](../evidence_snapshot/README.md)

```sh
uv run --offline --no-project --python 3.12 python -I -B workflows/review_exports/check_export.py \
  --ciat-repo "$repo" --records "$work/restored/$target" --csv /path/to/private/review.csv
```

Use the original browser headers. For an evidence export saved with a UTF-8 byte-order mark, retain `batch` as the first column. The row importer supports reordered columns with or without this mark.

The evidence import checks the restored evidence register and evidence review log against Git. Approve, hold and reject become OK, flag and soft-drop events. The last valid decision for each reviewer and evidence ID within an export wins. Different reviewers’ batches run in first-seen reviewer order. A disagreement can therefore change the result and grow the log again on retry. Inspect the conflict, superseded-row, missing-ID and skipped-row counts before using CIAT’s submission process. PICOS flags accompany accepted evidence decisions in the review note. [Pinned evidence importer](https://github.com/CIAT/nbs_ruralscan/blob/ece8d8226fed4a0b04d155888a8b4925d8f35386/scripts/apply-review-export.py)

The compiled-row import checks the restored row review log against Git and appends review events there. Its duplicate key contains record ID, reviewer, date and decision. A changed note or reason on the same key is skipped; a new decision can append another event. `duplicate_event_keys` counts skipped input rows matching a previously logged or newly encountered key. The preview separately counts distinct practice, table and record-ID combinations missing from the pinned T3, T6 or T6E tables. The native importer can log an unknown record ID. Generated recipe tables retain their original values. [Pinned row importer](https://github.com/CIAT/nbs_ruralscan/blob/ece8d8226fed4a0b04d155888a8b4925d8f35386/scripts/apply-row-review-export.py)
