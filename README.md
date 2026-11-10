# Rural Scan evidence workbench

This repository will document and run the evidence workflow behind Rural Scan: discovery, screening, acquisition, extraction, validation, human review and compilation into candidate analytical tables.

The workflows below run locally. Live registration and evidence review continue in [CIAT/nbs_ruralscan](https://github.com/CIAT/nbs_ruralscan).

Browse the six practices to see which hazards, suitability variables, scorecard effects and economic indicators have compiled rows. Each row links to its pinned source record. [Open the recipe index](publication/recipes/README.md)

Use the operator handbook for an AI-assisted or manual run. It provides task briefs for searching, screening and extracting evidence, and shows how to record which instructions were used. [Run an assisted evidence search and extraction](handbook/assisted-evidence-run.md)

## Runnable workflows

Find sources, screen a bounded result set and prepare a candidate bundle. The guide includes an offline replay and a dry run against the CIAT registrar. [Run discovery and screening](workflows/discovery/README.md)

Check a screened citation, acquire the source and verify its identity. The WOCAT manual example can be replayed from the publisher or a private copy. [Run source verification and acquisition](workflows/acquisition/README.md)

Locate a source passage and stage an evidence claim for review. [Extract the WOCAT terrace rainfall observation](workflows/extraction/README.md)

Restore the seven committed evidence tables, with optional clarification history, evidence gaps, citation traces and review priorities. [Reproduce committed evidence updates](workflows/evidence_snapshot/README.md)

Choose a workflow by the file you have. Browser backups, downloaded CSVs and server decisions each preserve different parts of a review session. [Find the right review record](handbook/review-records.md)

Preview saved decisions against a verified export to count approvals, soft drops, conflicts and clarifications. Try the three-record example first. [Preview a review batch](workflows/review_preview/README.md)

Preserve staged extraction files and check which evidence IDs have landed at a chosen CIAT revision. [Checkpoint a staged batch](workflows/extraction/checkpoint.md)

Preview a downloaded review CSV and see what a repeated import would do to evidence or compiled-row history. [Preview browser review exports](workflows/review_exports/README.md)

Rehearse restoring browser drafts and feedback into a fresh or already-used profile. [Check a browser backup](workflows/browser_backup/README.md)

## Worked example

Replay screening, source verification and extraction in one command, then reproduce the reviewed bench-terrace rainfall row from its historical inputs. [Run the terrace rainfall example](examples/terrace-rainfall/README.md)

Practice entering a source, correcting a claim and resolving a review question on disposable records. The exercise ends with an independent six-practice candidate rebuild. [Try the evidence handoff exercise](examples/evidence-challenge/README.md)

Rebuild the six-practice candidate release and check how many analytical rows and selectable functions each practice contributes. [Check the candidate release](workflows/recipe_release/README.md) · [View the verified counts](workflows/recipe_release/counts.md)

## Planned structure

| Directory | Purpose |
|---|---|
| `handbook/` | Operator and reviewer instructions, examples and recovery procedures |
| `registers/` | Source, claim and search records |
| `rulesets/` | Current instructions and immutable historical versions |
| `workflows/` | Model-neutral workflow stages and tool-specific adapters |
| `src/` and `tools/` | Validated intake, review, compilation and publication commands |
| `apps/workbook/` | One interface with public and review-enabled capabilities |
| `fixtures/` and `tests/` | Lawful training example and reproducibility checks |
| `audit/` and `publication/` | Unresolved holds, provenance and release manifests |

Every workflow stage must state its inputs, outputs, permitted writes, checks, human decisions, retry/stop conditions and an example run. Record source locators, instruction/model versions and review history. Model output is a proposal; only validated registration enters the records.

The compiler consumes pinned method definitions and evidence snapshots, then publishes candidate results. Method acceptance is separate; runtime consumes accepted releases. Human review, source credibility and runtime readiness are separate judgements.

Keep source PDFs, restricted content, credentials, local decisions and recovery backups in approved external or ignored storage. Preserve stable source/evidence IDs, soft deletions and audit events. Public workbook builds use publication-approved material and expose no review submission route.
