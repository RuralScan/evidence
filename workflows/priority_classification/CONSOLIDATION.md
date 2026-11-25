# One priority evidence route

The candidate findings from evidence PR #101 are preserved, not replaced by the five broader packet observations. `consolidation.json` records the original commit and exact file hashes. All six acquisition receipts, the search protocol/log, candidate schema and eight complete finding objects remain inspectable. Historical proposed adapters and register definitions live under `history/t5-proposal/` as inactive records.

The only active store is `priority-evidence/`, reviewed by `priority_store.py` against original authenticated human receipts. The former XCS/XCE identifiers remain candidate aliases, not new canonical IDs. There is no active `registers/cross_cutting` store or second review ledger.

`candidate-findings.json` prepares eight distinct v2 finding wrappers. Each embeds the complete original finding: passage, values, locator, context, limitations, scope and original candidate identifier. They reuse the six exact source editions already prepared in `preparations/2026-11-25`; no reacquisition, inferred equivalence, copied vote or acceptance occurs. Five earlier v1 packet findings remain separately preserved. A keep on either representation never approves another.

After this preservation commit is merged, `priority_store.py stage-candidates --revision <merged-full-sha> --base <trusted-main-sha> --path workflows/priority_classification/batches/t5-2026-11-25/candidate.json --source-root workflows/priority_classification/preparations/2026-11-25 --out <new-private-directory>` prepares candidate wrappers pinned to merged history. The wrappers in this proposal still identify their original candidate commit, which is not claimed to be merged. Registration must use the newly merged pin; it receives different content-addressed finding IDs. Old preparation IDs remain provenance, not aliases for review votes.

Remote SharePoint access still needs confirmation. Storage acceptance, canonical registration, human finding review, method classification/binding acceptance and release remain separate existing gates. This consolidation supplies none of those decisions. `protocol.md` is preserved historical extraction guidance; references there to the retired intake route do not activate it. This document defines the current route.

Run `python workflows/priority_classification/consolidation.py` and the priority-classification test suite. The check detects altered preservation bytes, omitted findings and reintroduced duplicate adapters.
