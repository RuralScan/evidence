---
name: source-command-t3t6-synthesise
description: Author AI-led T3 hazard and T6 scorecard scientific synthesis proposals from reviewed evidence, validate them, and package exact scientifically accepted outputs.
---

# AI-led effect synthesis — v2.0.2

AI performs scientific synthesis. Code validates, packages and reads accepted values.
Do not run the retired `synthesise-t3t6.py`, `t3t6_build`, `cell_synthesis` or T4
synthesis engine. Do not use historical fixed weights, rank medians, family maxima,
confidence matrices or equal-weight fallbacks as automatic decision rules.

Work in RuralScan/evidence. Read `workflows/synthesis/README.md` and its pinned
`contract.json`. Method authority: decision `t3t6_agent_synthesis` in RuralScan/method,
recorded in method issue #85. This workflow covers T3/T6 only; T6E remains historical.

## Prepare and reason

1. Establish the authorised practice, table and cells. Use `run.py prepare` to create
   the unscored input packet and skill snapshot. Do not edit those generated snapshots.
2. Read the relevant evidence passages, source identity and applied review history.
   Open original sources where needed to resolve meaning; flag unavailable material.
   Account for every candidate in the broad practice packet: include, exclude,
   context or hold, with reason and originating study/dataset/review lineage.
3. Assess relevance, outcome routing, comparators, context, units/denominators,
   duration, hazard severity, independence and overlapping reviews. Separate
   livelihood mitigation from asset damage. Do not treat quotation count as support.
   Crosswalks and bands provide definitions/context, not a scientific verdict.
4. Author the scientific judgments: direction, strength, evidence level, agreement,
   confidence, family/context scope, time scale, applicability, uncertainty and
   optional numerical summaries. Explain each and test plausible alternative
   interpretations. Confidence is a justified qualitative judgment, not probability
   or an automatic matrix result. Keep conflicting signs visible. Missing evidence
   is data deficiency with blank classes; genuine nulls need evidence.
5. Use practice-level effects reported for species where justified; do not apply T4's
   species-envelope exclusion to effects. Exclude qualitative-only families from
   landscape outputs. T6 links only to T5 priorities; costs belong to T6E.
6. Pool numbers only with compatible measures and independent origins. Record
   conversions, source overlap and limitations. Two named origins are a validation
   floor, not proof of comparability. Never invent a magnitude or scientific weight.
   If authoring asset weights, justify all six core hazards and a complete sum of one.

## Author the proposal

Use `rows.csv` as source of truth with exact contract columns. Complete `proposal.json`:
actual model identity (never invent a precise version), prompt, settings or “not exposed”,
skill version, all required reasoning, candidate dispositions and before/after comparison.
Set `replaces` to each previous row's `replacement_digest`; include scientific rationale
in every row's `justification.rationale`. An explicit withdrawal has no output rows.
Record the final CSV hash. Do not edit generated analytical JSON directly.

Validate against current inputs and prior rows, stage under a new immutable ID, commit
and present the exact proposal hash/revision and scientific comparison for review.
A passing validator is not scientific approval. Do not fabricate reviewer receipts,
accept your own proposal as a human, or treat approval of this software as approval of
scientific rows. Use an already-authorised exact scientific decision when available;
otherwise obtain that decision for the concrete completed proposal.

## Accept, package and run

Follow the documented human receipt format and `decision` command. Acceptance is
separate from individual evidence review. Code authenticates the original reviewer
receipt and binds it to exact committed proposal bytes. A new scientific judgment,
wording change, changed evidence or reopened review needs a new proposal; holds block
publication. Replays preserve accepted values without scientific recalculation.

Package only current accepted outputs. Pin the manifest hash independently in the
consumer and use runtime's `AcceptedEffects` reader. Explicitly report missing accepted
cells; never fill them from historical rows. Preserve withdrawal provenance. Report
which proposals are accepted, stale or held and what remains historical.


## Current practice and NbS inclusion

Before candidate admission or reuse of old approvals, read `handbook/nbs-inclusion.md`
and run `workflows/inclusion/check.py` on the private assessment. Inspect the authorised
catalogue's general and practice-specific criteria and the actual source. Keep practice
fit separate from NbS fit and analytical-role fit. Strongly demonstrated water harvesting may be primary or secondary; weak
secondary benefits cannot qualify. Unclear demonstration stays held. Carry exclusions, unresolved holds and
conditional scope into candidate dispositions; do not silently reroute or rehabilitate
previously rejected records. A conditional scoping decision does not approve numerical
mappings or effects. Record addendum `nbs-inclusion-1.1.0` and its hash with the actual
skill version. Preserve restricted materials privately and retain the existing exact
human-acceptance workflow. This procedural gate does not itself change accepted rows.
