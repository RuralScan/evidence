# Enter a source and check its identity

Enter one fictional field sheet into a private screening run. The sheet was written for this exercise. Its sketch legend identifies the streambank symbol. It supplies no site measurements or evidence for calibrating suitability. The reserved address in the bibliographic record identifies the teaching fixture. The commands read the bundled edition locally.

From the evidence repository root, start a private run with the [empty capture](capture-template.json) and the bundled [field sheet](field-sheet.md).

```sh
work=$(mktemp -d)
source_dir="$work/source-entry"
mkdir "$source_dir"
fixture=examples/evidence-challenge/source
cp "$fixture/plan.json" "$fixture/acquisition.json" "$fixture/field-sheet.md" "$source_dir/"
cp "$fixture/capture-template.json" "$source_dir/capture.json"
```

Open your copy of `capture.json`. Add one object to the empty `records` list. Give it the `record_id` used by the acquisition plan, `training_riparian_field_sheet`. Transcribe the opening heading into `title`. In `citation`, record the title, Rural Scan training collection, year 2026 and training edition 1. Use `https://example.invalid/training/riparian-field-sheet.md` for `url` and an empty string for `doi`. Compare with the [completed capture](capture.json) after entering the source.

Generate a worksheet from the record you entered:

```sh
python3 -B workflows/discovery/screen.py worksheet "$source_dir/plan.json" \
  --out "$source_dir/decisions.json"
```

Open the new worksheet. Keep its fingerprint, record ID and title. Change `disposition` from `unscreened` to `include` and enter your reason in `reason`. For example, the legend names the streambank symbol and meets the exercise criterion. Choosing `include` makes a new candidate available for acquisition. Choosing `reuse` would require an existing source ID. A completed [sample decision](decisions.json) is available for comparison. Regenerate the worksheet after editing the plan or capture.

```sh
python3 -B workflows/discovery/screen.py stage "$source_dir/plan.json" \
  "$source_dir/decisions.json" --out "$source_dir/screening"

tool=workflows/acquisition/run.py
uv run --offline --python 3.12 --locked --script "$tool" acquire \
  --candidates "$source_dir/screening/candidates.json" --plan "$source_dir/acquisition.json" \
  --local-file "$source_dir/field-sheet.md" --out "$source_dir/acquired"
uv run --offline --python 3.12 --locked --script "$tool" check \
  --candidates "$source_dir/screening/candidates.json" --plan "$source_dir/acquisition.json" \
  --bundle "$source_dir/acquired"
```

The acquisition commands require the locked dependencies in the uv cache. On first use, omit `--offline` to install them and retain `--local-file` for acquisition. Expect one record retrieved, screened and included, with its 427-byte Markdown snapshot under `acquired/cache/`. Check `acquired/receipt.json` for the opening-title match, the pinned SHA-256 and the `local_hash_replay` route. The submitted DOI is empty. A changed edition fails the hash check. All records produced here describe this private training exercise. Live source registration and review continue in CIAT.
