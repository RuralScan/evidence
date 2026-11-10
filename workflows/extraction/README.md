# Extract evidence from a verified source

This workflow turns a passage in a verified PDF into a proposed Evidence Register unit. The operator selects the claim and interprets it. The tool retrieves the quotation from the specified page, checks the draft, and writes a private staging file. CIAT owns review, corrections and publication.

## Worked example · rainfall and bench terraces

Start from the repository root. Run [the acquisition example](../acquisition/README.md#worked-example--wocat-terrace-manual) in the same shell first. It sets `work`, `candidates` and `plan`, and produces `$work/manual`. You need Python 3.12 and uv. With the locked PDF reader installed, extraction runs offline.

```sh
extract_pdf() {
  action=$1
  shift
  uv run --python 3.12 --locked --script workflows/extraction/extract.py "$action" \
    --candidates "$candidates" --plan "$plan" --bundle "$work/manual" "$@"
}
```

Search the manual, read the relevant page, then stage the proposal.

```sh
extract_pdf inspect --find 'forward sloping bench terraces'
extract_pdf inspect --page 129
extract_pdf stage --worksheet workflows/extraction/example/terrace-rainfall.json \
  --out "$work/extraction"
cat "$work/extraction/inventory.json"
```

Expect one proposed unit for `annual_precipitation` in family `water_harvesting__terracing`. On PDF page **129** (printed **116**), the manual describes contour forward-sloping bench terraces used in areas receiving **200–600 mm/year**. The proposal retains that range under `context.reported_values`. The manual establishes neither a suitability boundary nor a response to increasing rainfall, so direction is unclear and calibration stays on hold. The slope and catchment ratio in the same paragraph are outside this extraction. This exercise covers one passage in the 210-page source.

**Outputs.** `staging.json` is a list of proposed CIAT units; `inventory.json` records scope, checked edition, inspected pages, source-purpose quotation, dispositions and staged IDs. Quotes are continuous spans of the PDF text layer with whitespace normalised. Private outputs can contain licensed source passages. Keep them beside the acquisition bundle. Use a new output directory for another run.

## Recheck the historical record in CIAT

The existing terrace unit is `ev_wh_precip_wocatgl13_benchterraces`, extracted under v1.6.0. It stores the endpoints in `relationship.abs_min/abs_max`. This exercise uses the archived v1.9.9 instructions and retains observed use as context. Both refer to the same passage and evidence ID. Counting a second source or replacing the historical row would misrepresent the evidence. The [compiled terrace example](../../examples/terrace-rainfall/README.md) independently reproduces the existing recipe row and its calibration hold.

Set `ciat` to a CIAT checkout. For the reproducible comparison, use this revision in a disposable checkout:

```sh
ciat="$work/ciat-reference"
git clone --quiet --filter=blob:none --no-checkout https://github.com/CIAT/nbs_ruralscan.git "$ciat"
git -C "$ciat" sparse-checkout set --no-cone '/scripts/ingest-effects-staging.py' \
  '/src/' '/schema/' '/pipeline/acquisition_queue.csv'
git -C "$ciat" checkout --quiet 157a26c2729c05cccf2b1d9374a63e28c97acac6
uv run --no-project --python 3.12 --with pymupdf==1.27.2.3 \
  python workflows/extraction/handoff.py --ciat "$ciat" \
  --staging "$work/extraction/staging.json" --corpus-dir "$work/manual/cache" \
  --allow-structural --check-existing
```

To run the current proposal through CIAT’s scientific and provenance checks separately, repeat the command with `--validate-only` in place of `--check-existing`. Passing this check does not approve an update.

The archived unit should pass with **zero new units**. The comparison names differences in the current proposal. Normal handoff (omit `--check-existing`) holds a changed existing ID for audited correction. Current proposals and historical records keep their own ruleset versions. The bridge reads the corpus and runs validation against temporary copies of CIAT's registers. It has no publish command.

## Extract a different claim

1. **Frame the lane.** Select a screened and acquired source, practice, suitability family, role and canonical variable. Check FAM and VONT in CIAT. Review existing evidence IDs and coverage before assigning an ID. Roles distinguish establishment suitability (`structural_suitability`), outcomes (`nbs_effect`), hazards to the asset (`asset_vulnerability`) and implementation feasibility (`operational_risk`).
2. **Inspect the source.** Use `inspect --find` for page numbers and `inspect --page` for page text. Read the original PDF for columns, headings, figures, footnotes, tables and continuations. Record coverage gaps, including scans and missing supplements. A search hit or a site description alone cannot justify a suitability claim.
3. **Fill in a worksheet.** Copy [the terrace worksheet](example/terrace-rainfall.json). Replace the source ID and edition hash with those in the acquisition receipt. Record inspected PDF pages, coverage and a source-purpose disposition. A pass requires a locatable source passage. For T4, explain how the source addresses *where the specified practice can be implemented*. Record holds, exclusions and referrals explicitly.
4. **Describe one claim per unit.** Give the PDF page and two unambiguous boundary phrases on that page. Preserve original scope, units, raw variable name and attribution. Separate evidence for variable use, direction, reported values and relative importance. A numeric value must be grounded in its own passage. Record the cited primary source for secondary claims, and the taxon for crop- or species-specific claims. If an AI assists, give it the same scoped worksheet and page text, ask for reasons and anchors, then check them against the original page. Archive the prompt/model version privately alongside the worksheet.
5. **Stage and inspect.** Run `stage` and read both outputs. Confirm what the numbers measure, which practice they apply to and whether the passage supports the proposed interpretation. Local checks catch transcription and formatting problems. CIAT’s central gate also checks identities, vocabularies, context, bands and direction. Use the handoff command above with the applicable role flag for the intended lane; effects use the default. Only validated, genuinely new units should advance to CIAT review.

This workbench stages v1.9.9 proposals. CIAT’s later v1.10.0 instructions have their own archived copy. [Compare instruction versions](../../rulesets/README.md)

The executable handles page-anchored PDF passages. Web sections, code lines, specialised questionnaire transcripts and table cells needing multiple distinct anchors use their established source-specific procedures. An unreadable page, ambiguous anchor or unsupported relationship belongs on hold. Scientific acceptance and synthesis remain separate from extraction. [Versioned extraction instructions](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/.agents/skills/_versions/v1.9.9/SKILL.md) · [T4 contract](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/.agents/skills/_versions/v1.9.9/contracts/T4_review_contract.md) · [Effect contract](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/.agents/skills/_versions/v1.9.9/contracts/T3_T6_extraction_contract.md)

For an explicitly reported T4 threshold, class table or weight, put the source-defined value in `relationship` and the supporting verbatim group excerpt in `context.source_check` under `parameters`, `classes` or `weight`. Supply the scale for a weight. Use `context.calibration_hold` to explain limits on transfer. Ordinary observations remain in `context.reported_values`.

To carry an unfinished extraction batch forward, keep its original files, record their order and compare them with a later evidence register. [Checkpoint a staged batch](checkpoint.md)
