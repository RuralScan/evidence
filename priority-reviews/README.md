# Shared review-request priorities

Priority status controls the team's review queue. It is separate from finding votes, rating reviews and method decisions. It never changes a finding, its synthesis inclusion, a rating, approval or the review log.

On a finding or a selected review set, choose **Update team priority**. Select **Addressed**, **Deprioritize** or **Restore**, and explain why. Continue to GitHub and create the public receipt under your own account. Large sets produce several receipts. A protected evidence PR applies each receipt. Opening the draft alone does not change the team queue.

An organization member, collaborator or maintainer-confirmed reviewer can submit. The writer checks the original GitHub author and unedited issue body; a claimed reviewer name inside a payload is not accepted. A reason is required for all three actions, including restoration. Priority actions follow their own `RuralScan review priority v1` contract and cannot be interpreted as evidence votes.

## Apply a receipt

From a clean checkout of merged RuralScan/evidence main, inspect the reason, request IDs and revision in the issue. Resolve current main, then preview the change:

```sh
git fetch origin main
pin=$(git rev-parse origin/main)
python3 workflows/submissions/register_operation.py \
  --ciat-repo /path/to/nbs_ruralscan --base "$pin" priority ISSUE_NUMBER
```

Add `--open-pr` before `priority` to open the protected PR. Existing receipts are idempotent; duplicate submissions from the same author do not append again. A newer status for any target, or a change to its request, source, evidence or linked rating, rejects a stale submission. Reopen the current queue and submit a new receipt. CI re-fetches the original receipt and replays the append against the protected base.

## What reviewers see

**Needs attention** is the default priority filter. **Reviewed / excluded**, **Addressed / deprioritized** and **All requests** preserve access to earlier work. These are request filters, not scientific decisions. Counts describe requests within the selected practice and evidence type; the usual queue tabs still describe findings.

Automatic `reviewed` or `excluded` means the current register records that state. It does not assert that every question has been answered. A dated request stays active if a decision predates it, occurred on the same day with unknown order, or its recorded context changed. Holds, unresolved opposing decisions and unreviewed corrected findings stay active. A request naming a mapping also needs a later rating decision before it can be automatically treated as reviewed. An applied correction does not grant sign-off.

A shared **Addressed** or **Deprioritize** action removes only the specified requests from the default priority view. **Restore** brings them back. Changed request wording, evidence, source, relevant review history or linked rating invalidates the old status and returns the request as `recheck`. The prior reason remains visible.

## Machine-readable records

- `priority-reviews/receipts.jsonl`: append-only applied events, created when the first receipt is applied. Each line records `receipt`, authenticated `actor`, `created_at`, `body_sha256` and the original `entry`. `entry` contains `kind: priority`, full `revision`, `action`, required `reason` and `targets`.
- Each target identifies `(batch_id, evidence_id)` and pins `request_sha256`, `basis_sha256` and `last_receipt`. These pins prevent an unseen newer team status from being overwritten.
- `publication/review-queue.json` → `priority_requests`: generated request definitions, fingerprints, current status and complete per-request status history. `last_receipt` is null before a shared event. Each history item includes its receipt, author, date, action, reason and whether it still matches current inputs.
- Status values: `active`, `recheck`, `reviewed`, `excluded`, `addressed`, `deprioritized`. Only the last two are shared removals; `restore` explicitly returns a request to `active`.

The request definitions come from the migrated `registers/pipeline/review_priorities.csv` and the compiler's pinned review batches. The queue reads all registers at one RuralScan/evidence revision. Historical definitions and events remain available; none are deleted to make a queue look complete.
