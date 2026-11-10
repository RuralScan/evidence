# Public evidence workbook

Download the single HTML file and open it in a browser. The overview, bibliography, claim records, search records and recipe rows work offline. External links open the original pinned records or a publication. [Open the workbook file on GitHub and select **Download raw file**](../../publication/workbook/index.html)

## Follow a recipe row back to its source

1. In **Overview**, choose a count for a practice and analytical table.
2. Open a row to read its scope and analytical fields. Follow a direct evidence reference to the claim, then its source to see the citation. Some T4 mappings also reference evidence inside calibration or alternative inputs. The workbook lists those separately.
3. To inspect the original entry, follow its pinned record link. For large registers, GitHub can offer a raw file in place of a line preview. The workbook provides local claim and source destinations for offline use.
4. Copy the URL fragment to share a record with someone using the same edition. For example, append `#source=wocat_wh_guidelines_2013` when opening a copy of the workbook. Use the ID displayed on the source record.

## Read the counts

The six-practice candidate contains 806 analytical rows. Rows are counted once within each table. Of these, 797 directly cite evidence and nine have no direct claim ID. The 9,131 direct links refer to 3,259 distinct claims. Several analytical rows can cite the same claim.

The bibliography covers all registered sources at the pinned producer revision. The claim index covers retained register records, including claims outside the compiled tables. These register totals measure different populations from the analytical row counts. The search view reports the recorded figures for each search. Searches can overlap, and a missing stage count means it was unreported. Candidate rows and linked evidence alone do not establish suitability for a site.

## Reproduce the publication

From the evidence repository root, use Git and uv. The normal release checker rebuilds the candidate and compares the resulting HTML byte-for-byte with the checked-in workbook.

```sh
uv run --locked --python 3.12 --script workflows/recipe_release/check.py --check-workbook --json
```

Use `--workbook-dir /path/to/new-directory` in place of `--check-workbook` to write a fresh copy. The JSON receipt includes the file checksum, row and link totals. To rerun offline with dependencies already cached, add `--offline` immediately after `uv run` and pass `--ciat-repo /path/to/nbs_ruralscan` to the checker. The local clone must contain the pinned Git objects. [Candidate and producer revisions](../recipe_release/pin.json)

The publication uses the recipe index’s record links, field labels and table definitions. The source and claim registers supply a limited set of bibliographic fields, identifiers and locators. Live evidence review continues in CIAT. [Recipe index](../../publication/recipes/README.md)

## Rebuild after an interrupted review submission

This exercise checks whether the published workbook can be reproduced after a failed write and a retry. It uses an interval ending at the workbook’s pinned CIAT revision. Nine review events were added during this interval. Use a local CIAT clone with both revisions and the pinned review engine. Run from the evidence repository root:

```sh
uv run --offline --locked --python 3.12 --script workflows/recipe_release/check.py \
  --ciat-repo /path/to/nbs_ruralscan \
  --check-recovered-workbook 23ce026d885f3a29a272ec693d4d10bf9bf8bf55 --json
```

1. The checker verifies both copies of the evidence register, review log and clarification history against their Git blobs. It reconstructs a training batch from the recorded approvals and drops. It reads committed history only.
2. The rehearsal interrupts a changed record during local submission, checks rollback and retries against the later history. All nine decisions are already recorded there. Expect `record_install_interrupted: true` and `retry_changed_records: 0`. Duplicating an event would fail the check.
3. The checker takes the three records from the disposable Git remote, regenerates the typed evidence register from the recovered CSV and rebuilds all six recipes. It uses the regenerated register to render the workbook, verifies the evidence links against the immutable revision and compares the entire HTML file byte for byte with the published copy.

A successful receipt contains `workbook_recovery` and `public_workbook`. Compare the latter with the ordinary clean-build receipt above. The exercise writes temporary copies and prints aggregate results. Live review and release approval continue in CIAT. To exercise a retry that still has changes to submit, use the [private two-revision rehearsal](../review_preview/README.md#rehearse-an-interrupted-submission-and-retry).
