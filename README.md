# Rural Scan evidence workbench

This repository will document and run the evidence workflow behind Rural Scan: discovery, screening, acquisition, extraction, validation, human review and compilation into candidate analytical tables.

**Status: technical scaffold.** This repository does not yet contain the active registers or executable workflow. The structure below describes the intended technical components, not currently available commands.

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

The compiler consumes pinned method definitions and evidence snapshots, then publishes candidate results. Runtime consumes versioned analytical releases, not unreviewed candidate output. Human review, source credibility and runtime readiness are separate judgements.

Keep source PDFs, restricted content, credentials, local decisions and recovery backups in approved external or ignored storage. Preserve stable source/evidence IDs, soft deletions and audit events. Public workbook builds use publication-approved material and expose no review submission route.

Implementation requires reproducible fixtures, validated inputs, preserved review history and tested recovery behavior. An empty scaffold is not an operational evidence service.
