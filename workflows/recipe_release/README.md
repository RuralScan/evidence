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

The pin identifies a candidate analytical release. Runtime selects its own accepted release. To check a subsequent candidate, supply its trusted source revision, full release ID and practice list in a file with the same shape as `pin.json`, then run the command with `--pin /path/to/new-pin.json`. Rebuild independently before updating the checked-in pin and count report together. [Candidate pin](pin.json) · [Pinned producer](https://github.com/CIAT/nbs_ruralscan/tree/e5c8da02e72810956cfd179cb32cd137fc4ba398)

## Browse and reproduce the recipe index

[Open the six-practice recipe index](../../publication/recipes/README.md). Select a practice, then a hazard, variable or indicator to inspect its pinned CIAT record. The displayed scope distinguishes practice, family and context-specific rows. T4 reports function availability, selection and spatial validation separately. T6E reports whether a numerical range is present. Read the original record for units, source conditions, evidence references and caveats.

Generate all seven Markdown pages from the verified release and compare them with the published index:

```sh
work=$(mktemp -d)
uv run --python 3.12 --locked --script workflows/recipe_release/check.py --index-dir "$work/recipes"
diff -ru publication/recipes "$work/recipes"
```

The destination must be new. The same options for a local clone and an existing store apply. A matching comparison produces no output. GitHub renders the pages directly. Registration, corrections and review continue in CIAT.

## Check the method definitions used for comparison

The release pin pairs this candidate with a method definition manifest. Verify its checksum, the complete definition inventory at its declared source revision, and the structure version. The checker then compares every T0 practice definition byte-for-byte with the validated candidate release.

```sh
uv run --python 3.12 --locked --script workflows/recipe_release/check.py --check-method --json
```

For the current pair, the JSON receipt records **15 verified definition files** and the names of **six matching T0 practices**. The other nine files are verified against the method manifest. Use the receipt to cite both immutable revisions. The historical terrace example keeps the method revision recorded with its original compilation. [Paired release pin](pin.json) · [Method manifest](https://github.com/RuralScan/method/blob/247d5cf98d3dd6daf010aa5bfe51fad21ea35849/data-model/definition-snapshot.json)

With local Git objects and cached dependencies, add `--offline` immediately after `uv run` and pass `--ciat-repo /path/to/nbs_ruralscan --method-repo /path/to/method`. The method clone must contain both the manifest commit and its declared content revision. Add `--store /path/to/recipe-store` to verify an existing candidate. A custom release pin can still verify analytical tables alone. To run the paired check, include a `method` lock with the repository, manifest path, full manifest commit and SHA-256.
