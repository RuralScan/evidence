# Priority-classification source packets (proposed staging route)

This workbench preserves source observations needed by T2/T5 classification proposals. It does not register findings, stamp discovery progress, submit votes or accept classifications. All five packets are unreviewed. Packet IDs are not SRC/EV IDs. The original PDFs/web snapshots were acquired and inspected for this batch; their hashes and precise locators identify the checked versions. Full originals are not bundled here. Reacquire from the public URL and compare bytes; a changed document needs a new packet, never silent substitution.

Run `python3 workflows/priority_classification/check.py` and `python3 -m unittest discover -s workflows/priority_classification`. Passing checks proves shape and deterministic identity, not scientific correctness or source authenticity.

## Why the existing routes cannot be widened by one enum

Verified against evidence `d20b34f6d7a98f1630c852e9d72dac50edca9a2a`:

| Stage | Current route | Gap |
|---|---|---|
| Discovery | `workflows/discovery/screen.py`, `TABLES` | Only T3/T4/T6; practice/family framing required |
| Acquisition | `workflows/acquisition/` | Reusable artefact/metadata verification; current candidate context comes from discovery |
| Extraction | `workflows/extraction/claims.py`, `ROLES`; `extract.py`, `role_tables` | Suitability, effects, asset vulnerability and operational risk; no priority calibration role |
| Intake/review | `workflows/submissions/intake.py`, `REVIEW_ROLES` / `EXTRACTION_LANES` | T4 and T3/T6; no cross-cutting classification review |
| Registration/progress | `workflows/submissions/registration.py`, `stamp` / `verification` | Practice/family/table ledger and role-to-table routing |
| Configuration adoption | `workflows/submissions/configuration.py`, `cache_path` / `pinned_release` | Five named method register mirrors and lookup CSVs; no T2/T5 or classification JSON package |
| Scientific synthesis | `workflows/synthesis/` | Effect/suitability acceptance is not classification acceptance |

Reserved vocabulary does not establish an executable workflow. No existing route is changed by this proposal. Do not submit these packets as T4 or effect findings.

## Smallest compatible extension proposed for review

1. Keep source identity, acquisition receipts and source observations in evidence. Keep scientific interpretation, concern identity and class rules in method. User weights belong in analysis runs.
2. Introduce this cross-cutting packet scope as staging only. No fabricated practice/family attribution. Existing SRC records can later be reused by verified identity; new PDF sources require normal metadata verification, team library accession and acquisition receipts before canonical registration. Web snapshots require section locators. Each packet states its outstanding registration blocker.
3. A separate reviewed intake extension must define canonical cross-cutting source-finding ownership, review disposition and replay. Do not invent new EV fields or a synthetic NbS. Until that contract is approved, these exact packets remain independently reviewable proposals and method releases referencing them remain blocked.
4. Source-review acceptance means a finding was transcribed/interpreted correctly. It does not approve the proposed method classes. Method uses its protected decision PR route for exact proposal hashes and contexts.
5. Adoption of an eventual accepted priority release needs a separate lock (method commit, release path and SHA-256), verified source/finding references, dependency hashes and an append-only receipt. Retain the existing compiler pin unchanged. A selected previous immutable release provides rollback; do not erase receipts or re-rate historical findings.

This intentionally does not claim a finished ingestion lane. It makes the missing contract explicit and prepares verifiable packets without bypassing existing scientific review. The method-side prototype can validate and review candidates now; publication remains fail-closed until source registration, binding, context and human acceptance are complete.

## First batch

- Copernicus SPEI: reverse-direction event classes; not long-term frequency calibration. PDF table inspected visually.
- WRI Aqueduct: source risk bands, annual statistic and native basin support. Four-class reduction and arid handling remain decisions. PDF table inspected visually.
- Earth Engine Aqueduct catalogue: server-hosted asset and raw/status fields, documentation only; no live asset validation.
- LandMark: incomplete mapping prevents treating unrecorded presence as zero.
- FAO GSOCseq: stock, stock change and additional management benefit are different quantities.

No DOI has been added to SRC or the acquisition queue. Existing registers, votes, review receipts, ledger, configuration pin and runtime remain unchanged.

## T5 candidate intake extension

[Validated intake and exact remaining gates](intake.md) · [Bounded review protocol](protocol.md) · [Cross-cutting register manifest proposal](../../registers/cross_cutting/README.md). This extension preserves the five original packets and adds no canonical records or source votes.
