# Reproduce the terrace rainfall row

Can a site with 350 mm of rainfall per year be scored for bench terraces? One source documents forward-sloping benches in places receiving 200–600 mm/year. That observation supports a siting note. The reviewed mapping leaves its numerical suitability score unassigned. [Method walkthrough](https://github.com/RuralScan/method/blob/1fb414aa2af57d5ae3ba06265fee5141ea85eaa3/handbook/read-a-suitability-recipe.md)

## Run the example

From the evidence repository root, run the command below with Git and uv available. It uses Python 3.12, a locked environment and temporary checkouts of both input repositories. The first run needs internet access. [Method lock](../../method.lock.json) · [Compiler and source revision](https://github.com/CIAT/nbs_ruralscan/tree/2023cb82c94a93120600a7feb17d8cd1e12ce54f)

```sh
uv run --python 3.12 --locked --script examples/terrace-rainfall/replay.py
```

Expect **43 T4 rows across six practices** to match their audited tables. The example then checks every column of `water_harvesting__terracing__annual_precipitation`. Its full CSV row has SHA-256 `b9fac61513d3a3f642484dab77985d4b939dab5c622b92acfdf29bfb2e0a427a`. The digest uses UTF-8 JSON of the CSV column names and original string values, sorted by key with compact separators and unescaped Unicode.

To inspect the full row locally, append `--row-output /path/to/new-file.json`. The file is created after verification and includes the historical source excerpts and decision metadata. To replay offline with cached Python dependencies, add `--offline` to the **uv** options and pass `--method-repo /path/to/method --producer-repo /path/to/nbs_ruralscan` to the **script**. Both Git repositories must already contain the pinned commits and required blobs.

## Follow the inputs

1. **Identify the practice and measurement.** The method snapshot defines bench terraces within the terracing family and annual precipitation in mm/year. Its global binding points to CHELSA BIO12. The historical decision records `worldclim_v2_precip` as the input for this mapping. Both dataset identifiers resolve in the pinned catalogue. [Method definition snapshot](https://github.com/RuralScan/method/blob/aad360c25efd64d6a2754138e79ca558d2b472c7/data-model/definition-snapshot.json)
2. **Trace the three claims.** The fixture records a source ID, evidence ID, locator, extraction ruleset and annual-terrace scope decision for each claim. The stocktake source describes a watershed model using October–April rainfall. One grey source concerns contour stone lines. The other grey source documents use of forward-sloping bench terraces under annual rainfall. Only this last claim contributes to the row's source count. The scope decisions concern this mapping. The original discovery-screening outcomes and denominator are outside this example. [Reviewed claims](reviewed-claims.json) · [Source locators and interpretation](https://github.com/CIAT/nbs_ruralscan/blob/2023cb82c94a93120600a7feb17d8cd1e12ce54f/methodology/audits/t4_water_block_20261109/terrace_rainfall.md)
3. **Replay the review.** The script checks each claim against its registered source, evidence fingerprint and recorded profile decision. It derives the supporting evidence IDs, distinct source count and excluded profiles from the fixture and writes them to a temporary copy of the authored calibration hold. These are mapping-level decisions. None of the three historical extraction records has individual reviewer approval. Source artifact hashes are compared to the recorded fingerprints. Replaying the registered claims requires no original PDFs. [Pinned decision and reference row digest](https://github.com/CIAT/nbs_ruralscan/blob/2023cb82c94a93120600a7feb17d8cd1e12ce54f/methodology/audits/t4_water_block_20261109/terrace_rainfall_run.json)
4. **Compile and compare.** The original compiler reads the pinned method family and variable tables, the complete historical evidence registers and the authored recipe settings. It rebuilds each whole practice before selecting the example row. Every audited T4 mapping must agree, and the example row must match the independent decision digest. A changed input, scope decision or calibration status that breaks these checks stops the replay.

This example reads historical records. Live evidence review continues in [CIAT](https://github.com/CIAT/nbs_ruralscan).
