# Review a rating or change row wording

A finding is a claim from one source. A rating is a compiled row supported by zero or more findings. Review a **rating** to approve, hold or reject that row as presented. Choose **wording** to suggest a textual correction. Neither action approves a finding, changes a threshold or accepts a methodology edition.

## Reviewer: browser or CLI

1. Pull RuralScan/evidence main and start its [local submission desk](README.md#use-the-local-desk-for-browser-or-csv-entry) at the full evidence revision shown on the dashboard. Sign in to GitHub as yourself. Use a current RuralScan revision, not a CIAT revision.
2. Choose **Review a compiled rating or propose row wording**. Select a practice, table and row. Read its current text, rating and linked findings. T4 uses its stable mapping ID; the other tables use their record ID.
3. Choose **Review this rating** or **Suggest clearer wording**. Hold needs a reason; reject needs a coded reason. For wording, edit the mechanism and conditions for T3/T6/T6E, or the explanation for T4. Submit creates a public issue under your account. Keep restricted sources out of the note. If a correction is needed before application, close the issue and file a fresh one; edited issues cannot be replayed.
4. A protected data PR applies the original issue. Until merge, it is a proposal. After merge, look in the selected table’s **My reviewed** history or inspect the exact register and receipt. Wording changes appear in the compiled row on refresh. A new rating review is a separate historical decision; a reject does not remove the row.

From the RuralScan/evidence checkout, the same route works without a browser:

```sh
git fetch origin main
pin=$(git rev-parse origin/main)
rows=workflows/submissions/recipe_rows.py
python "$rows" inspect --revision "$pin" --practice agroforestry --table T3 --record agroforestry__drought__all
python "$rows" rating --revision "$pin" --practice agroforestry --table T3 --record agroforestry__drought__all \
  --decision hold --reason other --note "Describe what needs checking"
python "$rows" wording --revision "$pin" --practice agroforestry --table T3 --record agroforestry__drought__all \
  --wording wording.json
```

The last two commands preview the exact receipt; add `--submit` only to send it. Wording JSON: `{"mechanism":"…","conditionality":"…"}` or, for T4, `{"justification":"…"}`. The desk binds the practice, table, record, evidence IDs, full register revision and hashes of the visible row and supporting evidence. The original GitHub issue supplies the reviewer and timestamp. No typed reviewer name can overwrite them. The finding-vote CSV importer is not a rating importer: inspect a historical row CSV, then submit the judgment against the identified revision.

## Operator: preview, open protected PR, verify

```sh
git fetch origin main
base=$(git rev-parse origin/main)
writer=workflows/submissions/register_operation.py
python "$writer" --ciat-repo "$ciat" --base "$base" row "$receipt"
python "$writer" --ciat-repo "$ciat" --base "$base" --open-pr row "$receipt"
```

Use the merged writer in a clean checkout. Replay requires an open, unedited issue by an eligible GitHub contributor. The required check independently reads that issue. A receipt from an earlier merged revision can still apply if the actual row and its evidence match both revisions; otherwise re-inspect and file a new one. An exact retry produces no second event. Use one protected PR per receipt. Finding consensus and method decisions follow their own routes.

- **Rating:** append to `registers/pipeline/metrics/row_review_log.csv` and `row-reviews/receipts.jsonl`. CI preserves the imported CSV bytes and checks the appended record against GitHub. The new element of `publication/review-queue.json → row_reviews` includes `reviewer`, `nbs_id`, `table`, `record_id`, `date`, `decision`, `reason`, `note`, `revision` (edition reviewed) and `receipt` (RuralScan/evidence issue number). Historical records keep their original fields.
- **Wording:** append to `recipe-inputs/wording.jsonl`. T3/T6/T6E use the pinned compiler’s prose validator and native prose fields. T4 explanations may change independently of the mapping’s inputs, gates, weights and thresholds. The candidate records the source sidecars (`schema/recipes/<practice>/T3T6_prose.json`), declared T4 inputs (`schema/recipe_inputs/t4/`) and RuralScan’s new authored text separately from output hashes. Never edit generated rows by hand. If evidence, its locator or the analytical result changes, the old proposal is withheld, the compiled fallback is shown, and the affected row is listed in `stale_wording`. A removed row is listed by its former ID.

## Candidate and method acceptance

[Candidate manifest](../../publication/recipe-candidate.json) pins the compiler revision, SHA-256 of input files and one output hash per practice/table. Output hashes cover the ordered row array in `publication/review-queue.json → recipes[practice][table]`, serialized with the compiler’s canonical JSON (UTF-8, sorted keys, compact separators, trailing LF). The RuralScan/evidence commit pins both these files and the workbench source. All four table families rebuild for finding, source and row changes. The register PR shows the affected fields. Compare editions or independently reproduce the candidate in a checkout of the candidate revision:

```sh
python workflows/submissions/recipe_candidate.py "$earlier_evidence_sha" "$candidate_evidence_sha"
python workflows/submissions/check_registers.py --ciat-repo "$ciat" --base "$parent_evidence_sha"
git show "$candidate_evidence_sha:publication/recipe-candidate.json" | shasum -a 256
git show "$earlier_evidence_sha:publication/review-queue.json" > earlier-queue.json
```

**Method acceptance is separate.** Open a RuralScan/method PR identifying the evidence SHA, manifest file and SHA-256, practices/tables being adopted, previous edition and changed rows. Review the row differences and stale wording before approving that edition. Keep previous pins selectable. Publishing a candidate or approving a row does not replace the accepted method or the runtime pilot’s pin. The existing [versioned recipe release](../recipe_release/README.md) and its [release pin](../recipe_release/pin.json) remain available.

## Dashboard integration (November 10 design)

Link the two row actions to the running local desk at `http://127.0.0.1:8934/rows?revision=<full-evidence-sha>&practice=<nbs_id>&table=<T3|T4|T6|T6E>&record=<record_id-or-mapping_id>`. Add `&kind=rating` or `&kind=wording` to preselect the action. URL-encode values. The desk rejects a link from a different edition. Tell reviewers how to start the desk when it is not running. Consume `row_reviews` for **My reviewed** using authenticated handle, practice and table; use `receipt` for the original issue and `revision` for the edition reviewed. Read `stale_wording[practice]` (absent means empty) for the warning. Do not promote the candidate to the default methodology or expose write credentials in the public dashboard.
