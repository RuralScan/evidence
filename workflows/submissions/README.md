# Submit a finding vote or extraction proposal

The November 10 dashboard lets you submit a finding under your own GitHub account. The vote, note and account name appear on a public RuralScan/evidence issue. Choose **Submit review** on a finding, enter your decision, continue to GitHub and create the issue. Its number is your receipt. **My reviewed** links to your public submissions alongside the historical records. Restricted source files stay in the source library.

## Use the local desk for browser or CSV entry

Use a single-user computer with Git, GitHub CLI and Python 3.12. Sign in with your own GitHub account. Run these commands from a checkout of RuralScan/evidence. Set the paths to your own clone and corpus. The revision below is the November 10 dashboard's review-queue revision. The analytical edition has a separate pin.

```sh
source_repo=/path/to/nbs_ruralscan
pin=16e76d3e76bf9695cf5cda1ef9027e54a121d1f1
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

## Process submissions for one revision

Run in the evidence pipeline's Python environment with its intake dependencies and acquired corpus. Choose a fresh private output directory outside Git each time. The command reads open and closed receipts, checks GitHub's original author and edit history, and processes the requested revision. Organization members and repository collaborators enter the consensus preview. Other signed-in users can submit public receipts. A maintainer can confirm the reviewer for that receipt by applying the `confirmed-reviewer` issue label. Unconfirmed submissions stay visible and pending. An edited receipt requires a new original. Keep previous receipts for audit. Reconcile revisions before joining results across cohorts.

```sh
python3 workflows/submissions/intake.py collect --ciat-repo "$source_repo" \
  --revision "$pin" --corpus /path/to/private/corpus --out /private/work/batch-01
```

Inspect `receipts.json` for validated or held extractions. The operator can inspect the original content and staged units in each numbered folder. Dashboard and CSV votes use the same consensus process. `consensus.json` reports disagreements, potential register changes and retry checks against copies. Opposing votes stay pending. A proposed change to an already reviewed finding needs reconciliation against its existing event. Review the receipt before applying any register changes during the coordinated migration. Multiple receipts with an identical ballot produce one effective reviewer vote. Row reviews and method decisions use their existing separate workflows.

## Verify the connection

Add `--test-inbox` to the desk command to use marked synthetic finding IDs with public GitHub receipts. Run the collector with `--test` to process these receipts separately. For a local-only check, use `--sandbox /private/work/fixture.sqlite`. Sandbox receipts persist on that computer and can be found under **My reviewed** after restart.
