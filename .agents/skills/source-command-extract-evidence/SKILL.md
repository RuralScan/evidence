---
name: source-command-extract-evidence
description: Extract or review source-provenanced RuralScan evidence after separate practice, NbS and analytical-role checks.
metadata:
  version: "1.10.2"
---

# Current evidence extraction and review

Work in RuralScan/evidence. Read `AGENTS.md`, `handbook/nbs-inclusion.md`,
`workflows/extraction/README.md` and the applicable T4/effect contract from the
pinned v1.10.1 instructions identified in `rulesets/README.md`. This adapter adds
current inclusion checks; historical archives, quotes and EV stamps stay unchanged.

## Establish inclusion

Inspect the source's actual primary purpose, components and ecological mechanism.
Check the authorised catalogue's general definition and matching practice section,
including exclusions and safeguards. Record edition/hash and real locators privately.
Do not treat database labels, prior approval or a beneficial outcome as an inclusion
decision. Public definitions cannot stand in for an unread restricted catalogue.

Complete `workflows/inclusion/template.json` and run `workflows/inclusion/check.py`
against the source and definition files. Water harvesting must be a primary purpose:
in-situ capture can qualify; incidental infiltration in a gully repair cannot.
Keep practice mismatch, NbS failure, uncertainty and conditional inclusion separate.
Do not extract included claims from held/excluded interventions. Restrict bundled
claims to supported components; never infer component-level suitability from a
whole-package environmental table. Existing evidence is retained, not hard-deleted.

## Extract or review within the authorised lane

- Verify DOI/title, acquired edition and team access before claim extraction.
- Read source pages, tables, continuations and figures. Record purpose and coverage.
- Apply T4's separate source-purpose gate: does the source establish where the
  practice can be implemented? Keep observed settings, design dimensions, variable
  use, direction, numerical calibration and importance distinct.
- Keep `nbs_effect`, `asset_vulnerability` and `operational_risk` separate. Do not
  opportunistically add T4 extraction to an effect lane without authorisation.
- Slice source quotations using supported adapters. Preserve units, locators,
  species/crop scope, lineage and conflicting evidence. No inferred thresholds.
- Run the existing provenance, number, scope, species and direction checks on
  disposable records. Passing inclusion does not approve a claim or numerical rule.
- Stage and report actual coverage, holds, conditions and omissions. Use the
  protected submission/correction workflow; never write official registers by hand.

For historical review, preserve the original decision and record any explicit
supersession under the new rule before replay. Wrong-practice drops are reversible.
NbS uncertainty remains a hold. Do not silently reassign another practice or apply
new rules to analytical rows without scientific review.

Record adapter version 1.10.2, inclusion addendum `nbs-inclusion-1.0.0`, base contract
versions, exact prompt/model settings and file hashes privately. Stamp only new work
with instructions actually used; corrections retain the original EV extraction stamp.
Restricted definitions and detailed assessments never enter public receipts. Run the
retrospective after an actual extraction sweep, not merely this workflow update.
