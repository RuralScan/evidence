# Rural Scan evidence workbench

This repository will document and run the evidence workflow behind Rural Scan: discovery, screening, acquisition, extraction, validation, human review and compilation into candidate analytical tables.

The workflows below run locally. Live registration and evidence review continue in [CIAT/nbs_ruralscan](https://github.com/CIAT/nbs_ruralscan).

Browse the six practices to see which hazards, suitability variables, scorecard effects and economic indicators have compiled rows. Each row links to its pinned source record. [Open the recipe index](publication/recipes/README.md)

## Runnable workflows

Find sources, screen a bounded result set and prepare a candidate bundle. The guide includes an offline replay and a dry run against the CIAT registrar. [Run discovery and screening](workflows/discovery/README.md)

Check a screened citation, acquire the source and verify its identity. The WOCAT manual example can be replayed from the publisher or a private copy. [Run source verification and acquisition](workflows/acquisition/README.md)

Locate a source passage and stage an evidence claim for review. [Extract the WOCAT terrace rainfall observation](workflows/extraction/README.md)

## Worked example

Replay screening, source verification and extraction in one command, then reproduce the reviewed bench-terrace rainfall row from its historical inputs. [Run the terrace rainfall example](examples/terrace-rainfall/README.md)

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
