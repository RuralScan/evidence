# Register discovery, sources and progress

Run the operator from a RuralScan/evidence checkout. It prepares the data change on a disposable copy of the selected RuralScan revision. Preview prints the diff summary. Add `--open-pr` before the subcommand to push the proposal and print its GitHub PR link. Review the changed records and merge through the protected branch. The official data revision is the merge into RuralScan/evidence `main`.

Use Python 3.12 with the [evidence check dependencies](../../.github/workflows/evidence-checks.yml), Git, an authenticated GitHub CLI and a CIAT clone containing the pinned compiler revision. From the evidence checkout:

```sh
git fetch origin main
base=$(git rev-parse origin/main)
ciat=/path/to/nbs_ruralscan
writer=workflows/submissions/register_operation.py
```

Keep the full `base` you inspected. If main advances, inspect the intervening changes before preparing another proposal. The PR check replays the public operation against its base. Identical retries reuse the existing proposal or report that the operation was already registered. A changed run needs a distinct run ID. The input commands below use paths to your actual working files.

## Record a discovery run

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" discovery \
  --plan "$run/plan.json" --decisions "$run/decisions.json" --stamp
```

Use the [closed search plan and completed screening worksheet](../discovery/README.md). The writer checks the private worksheet fingerprint against the actual captures. It publishes the query, date, limits, scope, bibliographic records, screening reasons and counts, plus the original fingerprint. Abstracts and downloaded documents stay with the run. Check that your queries, URLs and reasons can be shared publicly.

The PR includes the SRCH row, any newly queued candidates, the report under `methodology/discovery_logs/` and explicit reuse IDs. Counts precede queue deduplication. A completed search with zero results gets a search record. With `--stamp`, the same PR records searched and screened progress for the exact practice, family, table and process. Unscreened records yield `screened=in_progress`. A blank family identifies a table-wide search. Omit the flag to publish discovery alone.

## Register an acquired source

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" source \
  --candidates "$run/screened/candidates.json" --plan "$run/acquire.json" \
  --bundle "$run/acquired" --assessment "$run/assessment.json" \
  --library-root "$synced_library" --library-path "$team_library_path"
```

Use the selected candidate and its [verified acquisition bundle](../acquisition/README.md). Supply the credibility assessment as one JSON object, for example:

```json
{"benchmark_tier":"medium","venue_type":"institutional_report","method_type":"review"}
```

For a PDF, `--library-root` points to the local synchronized copy of the team's `library/` folder. `--library-path` gives the project-relative locator used in SRC, including the `library/` segment and filename. The command compares shared-copy bytes with the receipt before preparing the PR. For supported web, text, Markdown or pinned code artifacts, the public source URL and private cached snapshot provide the locator. Supply the library flags if there is also a shared copy.

Review the queued identity, DOI or title result, source assessment, edition hash and shared locator in the PR. CI replays the public bibliographic and provenance checks. The operator checks the private artifact bytes. A known matching source keeps its canonical ID. A new source enters SRC with `extraction_status=pending`, alongside the acquired queue record and regenerated live queue. After merge, pin the new RuralScan revision for the [first extraction proposal](README.md#submit-an-exported-csv-or-extraction-file). Each extraction must still pass its lane and locator checks.

## Record verification progress

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" verification \
  --practice "$practice" --family "$family" --table "$table" --process "$process" \
  --run-id "$verification_run" --date "$step_date" --operator "$operator" \
  --status in_progress --receipts "$extraction_receipt"
```

Supply one or more applied extraction receipt numbers. The writer checks their original content against the applied journal, the cited source edition, and the current scoped findings. Search and screening must already be recorded as complete in that scope. Use `done` when the receipts cover every active finding in it. An incomplete set can support `in_progress`. This step records technical verification. Human finding decisions still go through the review queue. Extracted and reviewed counts come from EV and finding reviews.

Each operation is recorded under `operations/` and travels in the same commit as its register changes. Plain CSV edits cannot substitute for the operation. The [other write routes](README.md#which-records-can-i-update) list the remaining method and evidence work.
