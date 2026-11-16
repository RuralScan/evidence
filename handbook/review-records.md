# Find the right review record

Start with where the work was saved. A single review session can leave several kinds of records. The commands below inspect private copies. For a current finding, check the source in the [live finding queue](https://ruralscan.github.io/method/#review-queue) and submit a vote or review CSV through the [RuralScan submission desk](../workflows/submissions/README.md).

| What you have | What you can check |
|---|---|
| A RuralScan/evidence submission issue | Check the original receipt. After the register PR merges, find its issue number in the [applied journal](../registers/applied-receipts.json) and inspect the finding in the queue at that revision. |
| A CIAT revision containing the evidence register and review history | Restore the exact files for that revision. Use the review-support profile to include clarifications, gaps, citation traces and priorities. [Restore committed records](../workflows/evidence_snapshot/README.md) |
| Ordered JSON files of proposed extraction units | Restore the files byte-for-byte. Compare IDs, scientific fields and review flags against a chosen register revision before referring changes for intake. [Check staged extractions](../workflows/extraction/checkpoint.md) |
| Server-side saved decisions or clarifications from the checkout’s review directory | Preview the batch against a verified register export. Compare the same batch across two exported revisions to identify edited claims, changed review history and missing IDs. Use the recovery rehearsal to check rollback and retry against newer records. [Preview saved decisions](../workflows/review_preview/README.md) |
| An evidence-review vote CSV | Submit your own votes against the finding revision through the [CSV desk](../workflows/submissions/README.md#submit-an-exported-csv-or-extraction-file). For historical recovery, [preview votes on a private copy](../workflows/review_preview/README.md#collect-csv-votes-for-private-consensus). |
| A CSV for reproducing an older direct import, or a compiled-row review CSV | Run the matching importer twice on temporary copies. Check whether a retry adds events, especially where reviewers disagree. [Preview a review CSV](../workflows/review_exports/README.md) |
| JSON downloaded from **Browser review backup** | Check draft votes, notes, reviewer settings, batch reviews and the dashboard’s cleared-feedback backup against a receiving browser export. [Rehearse browser restore](../workflows/browser_backup/README.md) |

For a move between browsers, keep the original profile available until the exports have been checked. For an applied decision, verify the review event and evidence state at the same commit. Use CIAT for historical events and RuralScan/evidence for changes applied after retirement. For a new compiled-row review, inspect the row and submit it through the [rating-review desk](../workflows/submissions/recipe-rows.md). Keep the original export with its row ID and revision.
