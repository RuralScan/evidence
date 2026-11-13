# Publish the review status of a workbook edition

Run this companion step after building the [public workbook](../public_workbook/README.md) and rebuilding its [headline setter assessment](../recipe_release/replay_review_setters.py). Use the same output directory for the workbook, assessment and status. The CIAT clone must contain full history through the producer revision and the separate pinned live-navigation revision.

```sh
uv run --python 3.12 --locked --script workflows/review_status/build.py --ciat-repo /path/to/nbs_ruralscan
```

Add `--check` to reproduce the published bytes. Set `--directory` for a staged release. The manifest binds the workbook, historical headline assessment and status JSON by SHA-256 to the release ID, producer revision and schema version. A consumer verifies the three hashes before using the edition. Git reads target the named revisions. The limited Roose replay runs the historical compiler in a separate checkout.

The finding projection covers every EV unit, including excluded units. Each applied event identifies the decision, date, public reason code, first-parent commit containing its log line and physical line at the producer revision. EV determines inclusion. A flag leaves the finding active and unresolved. A reopen clears effective approval. Human sign-off requires an active EV approval and an applied approval from an identified human reviewer. The current edition recognises the project’s two reviewer accounts and their names in the historical exports. Unknown actors cannot grant sign-off. Automated corrections and field backfills appear as applied events and preserve any outstanding hold. The public event records actor kind only. Where EV and effective review state disagree, `reconciliation_required` is true. Historical log IDs missing from the edition register appear under `unmatched_finding_reviews`, with a deferred-register pointer or a verified rename. CIAT #293 renamed the dropped duplicate WOCAT landslide finding and its active sibling. The generator checks both records on each side of the commit before attaching the old drop event to the excluded counter-based ID. Private notes, personal identities, browser votes and export contents stay outside the projection.

Rows cover T3 and T6. Every assessed headline reports all confirmed setters and the count of distinct finding removals evaluated for that table. The practice-wide union of T3 and T6 removals is a separate count. Some setters affect a headline through changes elsewhere in synthesis and do not appear in its direct citations. The independent Roose check records the before/without values separately for all seven of its direct rows. For other non-headline rows, coverage is unavailable. A row with any confirmed held or unreviewed setter is provisional. Without a confirmed unresolved setter, partial or missing coverage yields null. An assessed row can have zero setters. The published rating remains visible throughout.

Finding events, rating reviews and decided method codes have distinct records. The rating-review log supplies the reviewed record ID and review date. Its rows have no browser version pin, so `row_revision` is null. A method decision's recorded commit is its ledger provenance. A separate implementing commit requires evidence of implementation and is null where unverified. The IEG comparison records two adjacent CIAT commits, the subsequent workbook edition, explicit evidence membership and the ratings in each. Later changes have unverified attribution.

Live links use membership in indexed, active CIAT batches at the separately identified navigation revision. `live_queue_available` records whether the finding occurs in the active EV register of the pinned CIAT dashboard, providing a direct queue route when no named batch contains it.

Run the historical assertions and the conflict/hold fixtures against a temporary checkout using the same Python dependencies as the release worker:

```sh
CIAT_TEST_REPO=/path/to/nbs_ruralscan uv run --python 3.12 --with numpy==2.4.6 --with requests==2.34.2 python workflows/review_status/test_status.py
```

The fixture enters two opposing CSV exports through the pinned shared-decision builder, confirms that consensus leaves the evidence untouched, then applies a synthetic hold to a confirmed historical setter in its private checkout. It regenerates EV using the historical CSV reader, recompiles the row and checks its original evidence membership, rating and confidence.
