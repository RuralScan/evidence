# Preview pending evidence decisions

This preview answers three questions before a review batch is submitted in CIAT. Which decisions would change a record? Which votes disagree? Would a second replay change anything? It runs the pinned CIAT review code twice on disposable copies with a private review lock. The output is a JSON summary. Registration, human decisions and submission continue in CIAT. [Pinned review code](https://github.com/CIAT/nbs_ruralscan/blob/ece8d8226fed4a0b04d155888a8b4925d8f35386/src/nbs_ruralscan/schema_tools/submit_review.py)

## Run the example

From the evidence repository root, use Git and uv to run the three-record training example:

```sh
uv run --python 3.12 --locked --script workflows/review_preview/preview.py --example
```

Two reviewers agree on a keep and a drop. They disagree on the third claim. Expect one approval, one retained soft drop, one pending conflict and one new distinct clarification. The previously recorded clarification appears in the input again. The second replay must leave the evidence, review log and clarification history byte-identical. [Example inputs](example)

## Check a private batch

Export a revision with the `review-support` snapshot profile. Prepare a stable private copy of `decisions.json`, `clarifications.json`, or both, outside Git. The example below uses the `repo`, `work` and `target` variables from the snapshot instructions. [Create and verify the review-support export](../evidence_snapshot/README.md#restore-committed-review-support-records)

```sh
uv run --offline --python 3.12 --locked --script workflows/review_preview/preview.py \
  --ciat-repo "$repo" --records "$work/support-restored/$target" \
  --pending-dir /path/to/private/saved-review
```

Offline use requires cached Python dependencies and a local clone with the pinned engine and record revisions. The directory name identifies the exported commit. The command compares the evidence register, review log and clarification history with Git before replay. Missing clarification history is valid only if it is absent at that commit. The optional pending files are listed in the receipt; missing saved decisions cannot be counted.

`agreed_verdict_ids` counts matching verdicts, including a single vote; `applied` counts newly applied decisions. An agreed verdict may already be recorded. Conflicts and IDs missing from the evidence register are reported separately and can overlap. For reclassification, the engine takes the first supplied scope and taxon. A positive `divergent_reclassification_targets` count flags conflicting explicit targets for human resolution. Clarification counts distinguish new distinct events from duplicate historical entries coalesced by the engine. Review notes, reviewer identities and source quotations are omitted from the summary.

## Check a saved batch across two revisions

A saved vote can refer to a claim whose evidence or review history has changed. Use the same private batch with the two verified exports from the [snapshot advance rehearsal](../evidence_snapshot/README.md#advance-a-private-copy-by-one-interval). Set `seed` to the earlier exported revision directory and `pending` to a stable private copy of the saved files.

```sh
uv run --offline --python 3.12 --locked --script workflows/review_preview/preview.py \
  --ciat-repo "$repo" --pending-dir "$pending" \
  --previous-records "$seed" --records "$work/advanced/$target"
```

The earlier commit must lie on the target’s first-parent history. The preview verifies both exports against Git, captures the pending inputs once, and runs the same review engine twice at each revision. Each replay uses disposable copies. The top-level counts describe the target. Under `comparison`, `previous_preview` gives the earlier counts and `previous_revision` identifies that export.

| Result | What to check |
|---|---|
| `evidence_row_changes` | Lists added, modified, removed and missing-at-both IDs addressed by a vote or explicitly linked to a pending clarification thread in either export or the saved batch. A modified row has at least one changed CSV field. Inspect the claim and its locator before submitting an old vote. For an absent ID, check deferred or historical records in the producing system. |
| `review_history_changed_ids` | The ordered review entries differ for these IDs. Check for a later decision or reopening even when the claim itself looks unchanged. |
| `clarification_history_changed_ids` | A recorded thread linked to the claim changed. The comparison includes replies that name only the issue. |
| `pending_issues_with_changed_history` | Number of issues in the pending clarification file whose recorded history differs. The separate count `pending_issues_without_linked_claims` identifies pending issues that could only be checked at thread level. |

Changes are measured between the selected exports. A receipt with identical replay counts can still list changes to individual records. Keep the comparison receipt private as it includes claim IDs. Consult CIAT for subsequent edits, and submit any confirmed decisions through its live review workflow.

## Rehearse an interrupted submission and retry

Run the training case from the repository root:

```sh
uv run --python 3.12 --locked --script workflows/review_preview/preview.py \
  --example --rehearse-recovery
```

The example interrupts the first changed record immediately after its replacement on disk. It checks that the pinned replay restores the evidence register, review log and clarification history, including any initially absent file. It checks both saved input files for changes. An independent example decision and clarification then advance the local main branch. The retry must preserve that newer history and produce exactly the record bytes from a clean replay on the later revision.

For a private rehearsal, add `--rehearse-recovery` to the two-revision command above. Use different revisions to exercise a real change in history. The receipt reports whether an installation was interrupted. If the earlier replay changes no bytes, only the pre-push failure and retry are exercised. A retry with no changes should create no branch on the local remote.

Git fetch, worktree creation, commit and push run against a disposable file-only remote. The first attempt must release its submission lock, retain its failed checkout for inspection by the rehearsal and leave all remote refs intact. The rehearsal uses the pinned record replay in place of the full generation command and simulates GitHub authentication and PR creation. Temporary repositories are removed on exit. Save the JSON receipt outside Git. Live decisions and submission stay in CIAT.
