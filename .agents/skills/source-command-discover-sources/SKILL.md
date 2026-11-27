---
name: source-command-discover-sources
description: Discover and screen sources for an authorised RuralScan practice and analytical lane, including practice-purpose and NbS inclusion checks.
metadata:
  version: "1.9.0"
---

# Current discovery and screening

Work in RuralScan/evidence. Read `AGENTS.md`, `handbook/assisted-evidence-run.md`,
`workflows/discovery/README.md` and `handbook/nbs-inclusion.md`. This adapter extends
the archived discovery v1.8.1 instructions; it does not edit their history.

1. Confirm the authorised practice, family, analytical lane and bounded question.
   Read current FAM and source/search/acquisition registers. Reuse canonical IDs.
2. Inspect the authorised catalogue's general definition and matching practice
   chapter, including exclusions and safeguards. Keep edition/hash, locators and
   detailed assessment private. Never send a restricted document or its excerpts
   to a public tool, repository or issue. Missing access is an explicit hold.
3. Set practice-purpose and NbS criteria before search. Water harvesting must be a
   primary purpose; secondary infiltration or erosion benefits cannot establish it.
   Other practices use their own definitions; no universal primary-purpose override.
4. Capture executed searches and returned records. Do not count planned queries as
   completed searches. Screen actual records with the existing credibility rubric.
   A promising abstract may justify acquisition, not final NbS inclusion.
5. After acquisition, assess the actual intervention/components using the inclusion
   template. Run `workflows/inclusion/check.py`. Hold unresolved purpose, ecological
   pathways or conflicts; preserve negative cases and justified referrals. Keep
   conditional restrictions attached to included candidates.
6. Stage candidates/protocols and report omissions and actual counts. Only supported
   register workflows publish search or acquisition changes. Do not extract evidence
   or assign approvals without scope. New practice attribution needs its own source
   assessment even when the publication was previously included elsewhere.

Record adapter version 1.9.0, inclusion addendum `nbs-inclusion-1.0.0`, the base
instructions actually used, model identity/settings and exact prompt hashes in the
private run record. Preserve frozen historical replays and extraction stamps.
