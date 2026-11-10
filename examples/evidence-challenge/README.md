# Practice an evidence handoff

Can you enter a source, correct a claim and resolve a reviewer’s question? This exercise uses a fictional field sheet for intake, a verified WOCAT passage for extraction, and three synthetic claims for review. At the end it independently rebuilds the published candidate tables from their pinned inputs. The practice decisions stay in your private workspace. Live evidence review continues in CIAT.

## Work through the cases

1. **Enter a source.** Read the fictional riparian field sheet. Identify its title and the feature described by its sketch legend. Fill in the screening worksheet, stage the candidate and verify the bundled edition. Check that the acquisition receipt reports one title-verified source. [Field sheet, worksheet and commands](source/README.md)
2. **Correct the rainfall claim.** The WOCAT manual on PDF page 129 describes forward-sloping benches in areas receiving 200–600 mm/year. Could that passage alone establish a lower or upper suitability limit? Inspect the paragraph and identify which fields should retain the reported values. The worked run saves the rejected worksheet and a corrected copy for comparison. [WOCAT source and verified extraction](../terrace-rainfall/README.md)
3. **Decide the three review cases.** The first passage describes contour planting on gentle slopes. The reviewer asks whether it gives a numerical cutoff. A follow-up reply requests more detail. The checked answer confirms the observation and finds no cutoff. The second passage describes the location of a sampling plot. The third gives the growing conditions of *Faidherbia albida*. Decide which practice observation to keep, which claim to drop with a reason and which to move to species-level evidence. Record your votes using the format below.
4. **Read the compiled result.** In the final receipt, find the number of compiled T4 mappings, how many have a selected function, and how many have spatial validation. Each count answers a different question about readiness to run the method. Compare with the [candidate release counts](../../workflows/recipe_release/counts.md).

## Run the checks

Complete the [terrace rainfall replay](../terrace-rainfall/README.md) first. Use Git, uv and Python 3.12. Set `terrace` to that completed private directory. Use the run record digest you saved when the replay finished. It can also be read from the original `summary.json` as shown here.

```sh
terrace=/path/to/completed/terrace
work=$(mktemp -d)
digest=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["run_record_sha256"])' "$terrace/summary.json")
exercise=examples/evidence-challenge/run.py
uv run --python 3.12 --locked --script "$exercise" \
  --terrace-run "$terrace" --sha256 "$digest" --out "$work/worked"
```

The command uses the worked votes by default. To try your own, copy the [blank voting worksheet](review-worksheet.json) to `$work/my-answers.json` and fill in the three votes. Each entry needs `evidence_id`, `decision` and a short `note` explaining your reading. The IDs are `training_contour_tree_siting`, `training_plot_description` and `training_species_envelope`. Available decisions are `ok`, `drop` and `reclassify`. Supply a coded `reason` for the latter two. This exercise uses the CIAT codes `off_scope` and `species_envelope`. For species reclassification also give `claim_scope` and `taxon`. Append `--review-answers "$work/my-answers.json"` and use a fresh output directory. A wrong decision stops the exercise at that case. [Worked answer sheet](review-answers.json)

For an offline run, use local Git clones containing the pinned producer, review engine and method objects, and cached uv environments:

```sh
uv run --offline --python 3.12 --locked --script "$exercise" \
  --offline --ciat-repo /path/to/nbs_ruralscan --method-repo /path/to/method \
  --terrace-run "$terrace" --sha256 "$digest" --out "$work/offline"
```

## Try the extraction correction yourself

After the worked run, copy its rejected worksheet and try it with the same extractor. Use your private source files from the verified terrace run.

```sh
cp "$work/worked/claim/invalid-worksheet.json" "$work/my-worksheet.json"
extract() {
  uv run --offline --python 3.12 --locked --script workflows/extraction/extract.py stage \
    --candidates "$terrace/screening/candidates.json" \
    --plan workflows/acquisition/example/terrace-manual.json \
    --bundle "$terrace/manual" --worksheet "$work/my-worksheet.json" --out "$1"
}
extract "$work/first-attempt"
```

The extractor should report `Observed-use excerpt cannot establish a source-defined limit`. In the draft’s `relationship`, remove the unsupported numeric bounds and their unit. Remove the associated numerical justification in `context.source_check`. Preserve the observed range and units in `context.reported_values`, the calibration hold and the original page locator. Save your worksheet, run `extract "$work/corrected"`, then run `diff -ru "$terrace/extraction" "$work/corrected"`. Matching outputs give an empty diff.

## Check your results

| Case | Expected outcome |
|---|---|
| New training source | One retrieved, screened and included. The opening title and edition hash match the bundled file. |
| WOCAT correction | The original numerical proposal fails. The corrected staging and inventory files match the verified terrace run byte-for-byte. Calibration stays on hold. |
| Reviewer query | The reply keeps the question open. The checked answer becomes available for a decision. Approval follows the explicit Keep. |
| Other review decisions | The off-scope row stays recoverable as a soft drop. The species-specific claim stays in the register under its taxon. Replaying the decisions adds zero events. |
| Candidate rebuild | The pinned compiler reproduces 804 analytical rows across six practices, including 47 T4 mappings. Ten have selected functions and zero are spatially validated. All six T0 definitions agree with the pinned method. |

A complete run writes `result.json` plus the training acquisition and worksheet files to the new directory. An interrupted run retains its private files for inspection. Retry in a fresh directory. The review engine uses temporary records throughout. The candidate compiler reads the release’s own evidence and settings. Runtime adoption is a separate decision.
