# Knowledge basis and extraction format

`knowledge_basis` records how a claim was established: `primary_measured`, `modelled`, `cited_secondary`, `expert_assertion`, or `unknown`. `extraction_format` records `prose`, `table`, `figure`, `code`, or `unknown`. Format carries no scientific credibility. A table of expert-selected classes is expert assertion extracted from a table.

The [method contract](../../rulesets/evidence-classification.json) is copied byte-for-byte from the immutable revision in [its pin](../../rulesets/evidence-classification-pin.json). The [schema migration receipt](../../configuration/evidence-classification-migration.json) records the input/output hashes and row count. CI reproduces the exact additive transform from the PR base and rejects unrelated scientific edits.

## Historical records

The migration preserves every original column, evidence ID, quote, source locator, review decision and ruleset stamp, including dropped rows. A legacy `table` becomes knowledge basis `unknown`, format `table`; `figure_read` becomes `unknown` and `figure`. Other known bases retain their meaning with format `unknown`. No source was re-read or scientifically reclassified by this mechanical migration.

Legacy `claim_basis` is retained because the pinned compiler still consumes it. Accepted analytical tables and source weights are not recalibrated by adding labels. Replacing historical credibility weights requires a separate scientific release and source review. The candidate build checks that the table hashes remain unchanged through this migration.

## Current extraction and correction

Supply both fields in every new submission. A known `knowledge_basis` must match the epistemic value in compatibility field `claim_basis`. `extraction_format` is independently specified; use explicit `unknown` when unavailable. New unknown-basis proposals remain staged for source review, not discarded or labelled measured. Current intake rejects missing fields or a new format-only legacy basis. The historical public terrace replay retains its original ruleset; its unextended output must be classified before submitting to a current edition.

A correction may retain the same historical classification while changing another reviewed field. Changing its knowledge basis requires a compatible `claim_basis` change through the existing correction receipt, source checks and reopening route. Migration alone grants no new human approval. Old finding votes remain comparable when the only difference is deterministic added metadata; changes to scientific fields or explicit classifications still make a vote stale.

Example for a literature-reported judgement:

```json
{
  "claim_basis": "expert_assertion",
  "knowledge_basis": "expert_assertion",
  "extraction_format": "table"
}
```

Expert opinion here is extracted from publications and published accounts. No new interviews or panels are part of this workflow. Retain reported rationale, uncertainty, scope and lineage; do not invent missing elicitation details.

## Dependencies and counts

Preserve distinct observations and complete response profiles. Repeated table cells, publication copies and reused datasets do not create independent votes. Shared authorship is a signal to investigate overlap, not proof that studies are duplicates. Record data/claim origin and unresolved dependence in the synthesis audit; compare influence by independent origin and, where relevant, author group. These appraisal recommendations do not introduce a new statistical pooling algorithm.

## Reproduce the migration

On the original migration base, with the pinned method commit available:

```sh
python3 workflows/submissions/schema_migration.py --base <full-base-sha>
python3 workflows/submissions/configuration.py build --ciat-repo /path/to/nbs_ruralscan
python3 workflows/submissions/check_registers.py --base <full-base-sha> --ciat-repo /path/to/nbs_ruralscan
```

The original migration is one-time and idempotent at that base. Later evidence commits preserve its receipt; they use normal protected submission routes. Source code lives in `classification.py` and `schema_migration.py`; unknown formats or new scientific interpretations require a reviewed contract update.
