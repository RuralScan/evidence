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
