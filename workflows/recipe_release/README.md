# Check a candidate recipe release

Use this check when reporting how much evidence has been compiled into practice tables. The unit is an analytical row. Source discovery, bibliography and evidence-excerpt counts use separate registers. [Verified counts by practice](counts.md)

## Rebuild and verify

From the repository root with Git and uv installed, run the following command. The first run downloads the pinned Python environment and the required CIAT files. The producer compiles all six practices in temporary storage, compares the results with the audited tables, and the reader verifies the release and reports the counts.

```sh
uv run --python 3.12 --locked --script workflows/recipe_release/check.py
```

To use a local CIAT clone and cached dependencies, add `--offline` immediately after `uv run` and append `--ciat-repo /path/to/nbs_ruralscan`. The clone must contain the pinned Git objects. The command reads that revision in a separate checkout. Local edits and live review decisions stay in the original checkout.

To check an existing store without rebuilding, append `--store /path/to/recipe-store`. It must contain the exact release named in the pin. The reader verifies all members by hash, checks provenance and checks the practice inventory. Append `--json` for machine-readable counts. Any missing or altered member, changed release ID or source mismatch stops the check.

## Interpret the results

T3 covers hazard responses, T4 suitability mappings, T6 scorecard effects and T6E economic profiles. Each row belongs to one practice table. One source can inform many rows. Among the T4 mappings, the report counts rows offering one or more functions, rows with an effective selection, and rows the producer marks ready for spatial execution. These measures overlap. Reference material outside the compiled T4 table does not increase its count. A zero means the pinned release contains zero qualifying rows.

The pin identifies a candidate analytical release. Runtime selects its own accepted release. To check a subsequent candidate, supply its trusted source revision, full release ID and practice list in a file with the same shape as `pin.json`, then run the command with `--pin /path/to/new-pin.json`. Rebuild independently before updating the checked-in pin and count report together. [Candidate pin](pin.json) · [Pinned producer](https://github.com/CIAT/nbs_ruralscan/tree/157a26c2729c05cccf2b1d9374a63e28c97acac6)
