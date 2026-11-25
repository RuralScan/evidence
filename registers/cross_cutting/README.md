# Cross-cutting source and finding register proposal

Schema tracking: [method issue #103](https://github.com/RuralScan/method/issues/103).

The manifest proposes an explicit destination for practice-neutral T5 evidence. It declares **zero canonical records** and disabled activation. Source/finding/search files named there are prospective stores, not records already registered. The candidate workbench is executable; protected registration and production adoption are not implemented by this PR.

## Proposed canonical record shape

| Store | Key and version | Required content |
|---|---|---|
| XCS source versions | `source_id`, `version` | Candidate source fields, with `candidate_source_id` promoted to `source_id`; exact acquisition receipt, title/DOI identity, artefact hash, format, URL and actual shared accession. If a reviewed SRC identity is reused, retain `{repository,revision,path,source_id,record_sha256}` instead of duplicating its identity. |
| XCE finding versions | `finding_id`, `version` | Candidate finding fields, with source/finding IDs promoted; source-version/hash, source statement/values, excerpt/locator, variables, context and limitations. Review state is derived from events, never accepted from an agent-authored field. |
| XSRCH searches | `search_id`, version | Query/provider/date, bounded scope, visible result counts and per-result decisions; no manufactured practice/family attribution. |
| Review events | `event_id`; per-finding sequence | Exact finding ID/version/hash, keep/drop/query/reopen, reviewer, reason and protected PR provenance. Append-only; idempotent retries; no deletion. |

Promotion must retain a candidate-to-canonical mapping and original candidate digest. New versions keep lineage; changed source or finding bytes invalidate old review for the changed content. A protected registration adapter must authenticate human review against merged PR history, verify shared acquisition, replay the current register and compare a pinned method schema decision. Merely supplying a PR-shaped URL is not authentication.

A future activation PR must add those checks, tests and the store files together, then update this manifest. It must not widen retired SRC/EV columns or route through a T4/effect vote. The present pure review replay is a testable specification, not an approval API. No CLI writes these stores.

[Candidate schema and intake](../../workflows/priority_classification/intake.md) · [Bounded protocol](../../workflows/priority_classification/protocol.md)
