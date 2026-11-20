# Submit evidence and recipe reviews

The review dashboard lets you submit a finding under your own GitHub account. The vote, note and account name appear on a public RuralScan/evidence issue. Choose **Submit review** on a finding, enter your decision, continue to GitHub and create the issue. Its number is your receipt. **My reviewed** links to your public submissions alongside the historical records. Restricted source files stay in the source library.

## Which records can I update?

The [live finding queue](https://ruralscan.github.io/method/#review-queue) accepts structural suitability (T4), hazard and scorecard (T3/T6), and operational feasibility (M2b) finding votes. The desk also accepts a reviewer’s finding CSV or a proposed new or corrected finding from a source already in SRC. A submitted issue records the proposal or vote. After a protected register PR merges, its receipt appears in the [applied journal](../../registers/applied-receipts.json) and the queue reads the new revision. The [operator procedure](#apply-approved-submissions) explains approval, consensus and application.

Operators can register a completed search and its acquisition candidates, repair queued metadata with a recorded reason, promote one or a batch of verified sources before extraction, and stamp progress from its producing step. Each proposal travels through a protected RuralScan/evidence PR. [Commands and expected register changes](registration.md)

| Other work | What you can do now | Missing official route |
|---|---|---|
| Candidate tables and row wording | [Propose wording, rebuild and compare a candidate](recipe-rows.md). Method acceptance is a separate PR. | — |
| Rating reviews | [Review a compiled row](recipe-rows.md). The protected PR appends authenticated rating history. | — |
| Method decisions | [Propose, decide, implement or supersede a coded scientific ruling in RuralScan/method](https://github.com/RuralScan/method/blob/040f701fa0455c0dfc3fddbeee8ef6c74fe636f9/decisions/README.md). | — |
| Configuration and lookups | [Adopt reviewed method definitions, update tools or source-specific mappings, and rebuild the pinned candidate](../../configuration/README.md). | The guide identifies inputs still held at archived revisions. |
| Shared priority status | [Record addressed requests, deprioritize or restore them with a reason](../../priority-reviews/README.md). Priority events do not cast finding or rating votes. | — |
| Retrospectives | Preserve measured sweep results and links from feedback to changes in instructions or checks. | Record the sweep and advance its learnings cursor ([evidence #41](https://github.com/RuralScan/evidence/issues/41)). |

The [CIAT retirement check](https://github.com/CIAT/nbs_ruralscan/blob/4d53620f7a9f0f17a42a007fa0a653e5ed55c519/scripts/check-retired-evidence.py#L7-L32) protects the archived records. The [RuralScan register check](check_registers.py) verifies the migration inventory and replays each new change against its base revision. · [Queue compiler](https://github.com/RuralScan/evidence/blob/4198da5febfb8e4fbc0707ccbdbbade8a2147cff/workflows/submissions/queue_view.py#L24-L69)

## Submit findings together in the hosted queue

Select your GitHub reviewer name, review findings and save decisions. **Submit my decisions** shows the batch and one **Open submission** button. Small batches open a prefilled GitHub issue with all decisions included: choose **Create**. Larger batches download a named CSV and open a prefilled issue: attach that CSV, wait for its upload to finish, then choose **Create**. No JSON copying, revision entry or local server is needed.

Return to the queue to find the matching submission automatically, or choose **Check submissions**. The dashboard retains the original decisions on this device and shows **Submitted · awaiting validation and processing**. **Applied** appears only when the matching receipt is in the official applied journal. Opening an issue draft alone never marks votes submitted. Different register revisions and test/live votes remain separate; large CSVs split at a 1 MB transport limit.

The `RuralScan review submission v2` issue carries a manifest in an HTML comment: lane, full revision, test flag, CSV byte count, row count and SHA-256. Small batches include CSV text in the manifest; large batches attach exactly one CSV through GitHub. The operator verifies the original issue author and edit history, downloads only allowed GitHub attachment storage, and checks the exact bytes before normal CSV validation and consensus. Missing/changed files are rejected; an unavailable attachment stops the preview so a possible opposing ballot cannot silently disappear. Existing v1 issues and CLI submissions remain valid. Attachments record votes only; they do not approve extractions or bypass register PR review.

Single-lane batches use the existing vote CSV. A cross-lane CSV uses `lane: Mixed` in its receipt and a `lane` column on every row. Each ID must match its own lane at the pinned revision. M2b accepts finding reviews for `operational_risk`; extraction proposals retain their existing lanes. Submission, consensus, retry and protected register application use the same path as desk CSVs.

## Source previews

**View source preview** shows a passage matched against the acquired source or a cropped table image. Public assets in `publication/source-previews/` bind to source, locator, quote and access metadata. When no matching public preview exists, reviewers can open the cited source or select acquired PDFs on their device for inline reading. Restricted PDFs stay in the team library.

Applying approved extractions through the register writer refreshes previews for those findings with the supplied corpus in the same PR. For a full rebuild, use the current register, acquired corpus and Python with PyMuPDF and Pillow. Generate into a fresh directory, inspect coverage and replace the published directory together with its index in a PR.

```sh
python workflows/submissions/source_previews.py --corpus /path/to/acquired/corpus --out /tmp/new-source-previews
```

## Use the local desk for browser or CSV entry

Use a single-user computer with Git, GitHub CLI and Python 3.12. Sign in with your own GitHub account. Run these commands from a checkout of RuralScan/evidence. Set the paths to your own clone and corpus. Use the full register revision shown on the finding or linked from the live queue. The example resolves the current RuralScan main commit. The analytical edition has a separate pin.

```sh
source_repo=/path/to/nbs_ruralscan
git fetch origin main
pin=$(git rev-parse origin/main)
gh api user --jq .login
python3 workflows/submissions/serve.py --ciat-repo "$source_repo" --revision "$pin"
```

Open [the local desk](http://127.0.0.1:8934/) and enter the finding ID from the [review queue](https://ruralscan.github.io/method/#review-queue). Check the cited source. The form checks the lane, revision and account. **Drop** requires a coded reason. **My reviewed** in the desk lists your submissions. A receipt records submission. Applied history still comes from the edition's evidence register and decision log.

The desk binds only to 127.0.0.1 on port 8934 and uses the local operating-system user's GitHub credentials. Use one account per workstation session. On a shared or remotely exposed machine, use the authenticated CLI from your own login instead. Stop the desk with Ctrl-C.

## Submit an exported CSV or extraction file

Choose **Submit a review CSV** on the desk or run the first command below. Each CSV must contain votes from the submitting GitHub account for one selected lane and revision. Confirm the source revision before submitting an old CSV. T3 and T6 share the effect lane. Both the browser and CLI preserve the same verdicts and provenance. Staged extraction JSON uses the existing input format, with source, locator, quote and ruleset version on each unit. Split files larger than the GitHub issue-body limit into smaller batches.

```sh
python3 workflows/submissions/intake.py csv votes.csv --lane T4 --revision "$pin"
python3 workflows/submissions/intake.py extraction t4-units.json --lane T4 --revision "$pin"
python3 workflows/submissions/intake.py extraction effects.json --lane T3/T6 --revision "$pin"
```

## Preview receipts pinned to a historical CIAT revision

Run in the evidence pipeline's Python environment with its intake dependencies and acquired corpus. For this historical preview, set the pin to the CIAT revision on the original receipt. Choose a fresh private output directory outside Git each time. The command reads open and closed receipts, checks GitHub's original author and edit history, and processes the requested revision. Organization members and repository collaborators enter the consensus preview. Other signed-in users can submit public receipts. A maintainer can confirm the reviewer for that receipt by applying the `confirmed-reviewer` issue label. Unconfirmed submissions stay visible and pending. An edited receipt requires a new original. Keep previous receipts for audit. Reconcile revisions before joining results across cohorts.

```sh
python3 workflows/submissions/intake.py collect --ciat-repo "$source_repo" \
  --revision "$pin" --corpus /path/to/private/corpus --out /private/work/batch-01
```

Inspect `receipts.json` for validated or held extractions. The operator can inspect the original content and staged units in each numbered folder. Dashboard and CSV votes use the same consensus process. `consensus.json` reports disagreements, potential register changes and retry checks against copies. Opposing votes stay pending. A proposed change to an already reviewed finding needs reconciliation against its existing event. Compare preview results with the receipt and the register revision it names. Multiple receipts with an identical ballot produce one effective reviewer vote. This preview concerns finding votes. For rating reviews and method decisions, see [which records can be updated](#which-records-can-i-update).

## Verify the connection

Add `--test-inbox` to the desk command to use marked synthetic finding IDs with public GitHub receipts. Run the collector with `--test` to process these receipts separately. For a local-only check, use `--sandbox /private/work/fixture.sqlite`. Sandbox receipts persist on that computer and can be found under **My reviewed** after restart.

## Apply approved submissions

The live queue reads the live RuralScan register revision. A finding vote (dashboard or CSV) is attributable to its signed-in GitHub author. A maintainer who has reviewed an extraction marks its original issue **approved-extraction**. Review the cited source and the exact proposed changes before applying that label. The correction path preserves the original extraction stamp and reopens a changed finding for review.

From a clean checkout, run the command below with the issue numbers to process and your local corpus. Use the Python environment from the evidence checks (PyMuPDF, requests and NumPy). Preview is the default. Add `--open-pr` to open a normal, protected register PR with traceable receipts. The command reads current RuralScan main and refuses publication until the CIAT retirement marker is present on CIAT main.

```sh
python3 workflows/submissions/registers.py 29 --ciat-repo /path/to/nbs_ruralscan --corpus /path/to/acquired/corpus
```

The local operator can process accepted votes in either lane. Allowlisted or maintainer-confirmed reviewer identity, original issue body, matching finding and source, and agreement across eligible ballots are checked. An opposing vote, including a late challenge, remains on its public receipt for reconciliation. The receipt ledger prevents duplicate application. A newly created register PR needs GitHub approval and current CI checks. The merge publishes new register bytes and the regenerated six-practice review queue as one Git revision. Reload the live queue to see the applied result. Each corrected T4 or T3/T6 finding shows the changed fields before and after application, the date and the receipt. Earlier corrections remain on the card after later edits or reviews. Historical analytical editions retain their original data.

For rollback, stop applying register PRs, retain submissions received since the switch, and reconcile each changed finding, source, decision event and published output since the last common revision. Verify the reverse delta before restoring a writer. The immutable migration baseline is RuralScan `3d734daa5cf5452b69a5a63c6815efae7be0181d`.

## T4 synthesis retirement

Review intake still updates findings, source assessments, votes and approved wording.
It no longer derives T4 mappings. The queue and candidate manifest include
`t4_synthesis.status = historical_baseline`, an immutable evidence revision and SHA-256,
`current_evidence_applied = false` and `needs_agent_synthesis = true`.
The evidence checkout must contain the pinned Git revision; a shallow clone must fetch
that revision before rebuilding the queue.
The 54 baseline rows are retained verbatim apart from separately approved wording;
this includes empty practice tables. New, changed or dropped evidence cannot silently
change their analytical values. These rows are not newly approved or validated AI results.
Consumers must show the historical status and must not treat this candidate as a fresh
T4 release. Evidence review approval does not approve a mapping.

T3/T6/T6E still use the existing effect engine. An AI-led scientific proposal and
acceptance route remains to be implemented; AI prose does not replace that engine.
The old T4 compiler and whole-recipe rebuild entrypoints are retired. Historical
Git editions remain readable; the current release checker requires an existing store.
See the [decision audit](https://github.com/RuralScan/method/issues/85#issuecomment-7049325204).
