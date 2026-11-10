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
