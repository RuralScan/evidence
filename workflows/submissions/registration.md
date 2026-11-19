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

## Register a batch of acquired sources

Use `source-batch` for several verified bundles against one inspected base. Paths in the JSON manifest are relative to the manifest file (absolute paths also work):

```json
[
  {
    "candidates": "source-a/candidates.json",
    "plan": "source-a/acquire.json",
    "bundle": "source-a/acquired",
    "assessment": "source-a/assessment.json",
    "library_root": "/path/to/synced/library",
    "library_path": "library/mangroves/source-a.pdf"
  },
  {
    "candidates": "source-b/candidates.json",
    "plan": "source-b/acquire.json",
    "bundle": "source-b/acquired",
    "assessment": "source-b/assessment.json",
    "library_root": "/path/to/synced/library",
    "library_path": "library/mangroves/source-b.pdf"
  }
]
```

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" source-batch --manifest "$run/sources.json"
# After inspecting the preview, add --open-pr before source-batch.
```

Every source keeps its own operation record, identity checks, hashes, credibility assessment and library check. The writer validates all inputs on disposable copies, sorts operations in CI replay order, compiles the publication once and opens one protected PR. A failure names the source and publishes nothing. Duplicate source IDs are rejected. Identical retries reuse the proposal or report `Already registered. No change.` after merge. A partly registered batch adds only the remaining matching sources. If main advances, inspect its changes and rebuild the proposal at that revision; do not merge a stale operation record.

## Correct queued metadata before registering sources

Use `queue --corrections` for one JSON object or a list of corrections in one PR. The queue row must still be unregistered, non-duplicate and pending or acquired. URL, citation and DOI are the only editable fields; the operation retains the entire previous row, reason, operator, date and replayable Crossref facts.

```json
[
  {
    "source_id": "source_with_missing_locator",
    "changes": {},
    "doi_locator": true,
    "reason": "Use the Crossref-verified DOI as this screened work's locator.",
    "operator": "your-handle",
    "date": "2026-11-19"
  }
]
```

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" queue --corrections "$run/queue-corrections.json"
# Add --open-pr before queue to submit the recorded repairs for approval.
```

For an explicit repair, use `"changes": {"url": "https://publisher.example/report", "citation": "Author (1989). Screened title. Publisher."}` and omit `doi_locator`. Correct a year through the citation; there is no separate queue year column. A DOI may be changed or cleared. Every nonempty DOI is reverified against Crossref and must identify the same full title; an old `doi_verified` flag alone is insufficient. An outage or mismatch stops the batch. `doi_locator: true` supplies `https://doi.org/<verified DOI>` only when verification passes; it cannot be combined with an explicit URL.

Changing the screened title is refused by default. If the existing title itself is wrong, an explicitly confirmed same-work repair needs `"confirm_title_change": true` and `"identity_reference": "https://publisher.example/authoritative-record"`, plus the explanation in `reason`. This is a proposed metadata correction, not a human finding decision or automatic sign-off. The PR highlights the title change; its reviewer must confirm the identity before merge. Do not use this flag to substitute a different work or infer approval from an AI match. A different work must be screened separately.

Corrections reset the queue to `pending` and clear `title_verified`; they never mark a file acquired, create SRC/EV rows or approve findings. After merge, use the corrected queue identity to rebuild the candidate and acquisition plan and make a new bundle; retain the originals. Then register the verified bundles together with `source-batch`. A source already registered in SRC cannot be altered through this route.

For a title-only source whose discovery URL is an OpenAlex record, retain that discovery URL and set the acquisition plan's `artifact_url` to the independently verified publisher/repository location, with its `publisher_hosts` and the file's `expected_sha256`. This existing override also works for local replay. A DOI locator is bibliographic identity, not a claim about where bytes were downloaded.

## Record verification progress

```sh
python "$writer" --ciat-repo "$ciat" --base "$base" verification \
  --practice "$practice" --family "$family" --table "$table" --process "$process" \
  --run-id "$verification_run" --date "$step_date" --operator "$operator" \
  --status in_progress --receipts "$extraction_receipt"
```

Supply one or more applied extraction receipt numbers. The writer checks their original content against the applied journal, the cited source edition, and the current scoped findings. Search and screening must already be recorded as complete in that scope. Use `done` when the receipts cover every active finding in it. An incomplete set can support `in_progress`. This step records technical verification. Human finding decisions still go through the review queue. Extracted and reviewed counts come from EV and finding reviews.

Each operation is recorded under `operations/` and travels in the same commit as its register changes. Plain CSV edits cannot substitute for the operation. The [other write routes](README.md#which-records-can-i-update) list the remaining method and evidence work.
