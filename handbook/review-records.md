# Find the right review record

Start with where the work was saved. A single review session can leave several kinds of records. The commands below inspect private copies. Continue editing, resolving disagreements and submitting changes in CIAT.

| What you have | What you can check |
|---|---|
| A CIAT revision containing the evidence register and review history | Restore the exact files for that revision. Use the review-support profile to include clarifications, gaps, citation traces and priorities. [Restore committed records](../workflows/evidence_snapshot/README.md) |
| Ordered JSON files of proposed extraction units | Restore the files byte-for-byte. Compare IDs, scientific fields and review flags against a chosen register revision before referring changes for intake. [Check staged extractions](../workflows/extraction/checkpoint.md) |
| Server-side saved decisions or clarifications from the checkout’s review directory | Preview the batch against a verified register export. Check agreement, conflict, missing IDs and previously logged events. [Preview saved decisions](../workflows/review_preview/README.md) |
| A CSV downloaded from an evidence or compiled-row review page | Run the matching importer twice on temporary copies. Check whether a retry adds events, especially where reviewers disagree. [Preview a review CSV](../workflows/review_exports/README.md) |
| JSON downloaded from **Browser review backup** | Check draft votes, notes, reviewer settings, batch reviews and the dashboard’s cleared-feedback backup against a receiving browser export. [Rehearse browser restore](../workflows/browser_backup/README.md) |

For a move between browsers, keep the original profile available until the exports have been checked. For a submitted decision, verify the corresponding event and evidence state in the committed CIAT records. A local vote, successful rehearsal or feedback report alone cannot establish that the review was submitted.
