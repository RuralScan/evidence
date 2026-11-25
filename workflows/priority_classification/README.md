# Priority-classification source packets and gated store

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

These first-batch packets remain staging records. The next implementation below supplies a distinct store and adoption route, still pending storage acceptance and real source review. It makes the missing contract explicit and prepares verifiable packets without bypassing existing scientific review. The method-side prototype can validate and review candidates now; publication remains fail-closed until source registration, binding, context and human acceptance are complete.

## First batch

- Copernicus SPEI: reverse-direction event classes; not long-term frequency calibration. PDF table inspected visually.
- WRI Aqueduct: source risk bands, annual statistic and native basin support. Four-class reduction and arid handling remain decisions. PDF table inspected visually.
- Earth Engine Aqueduct catalogue: server-hosted asset and raw/status fields, documentation only; no live asset validation.
- LandMark: incomplete mapping prevents treating unrecorded presence as zero.
- FAO GSOCseq: stock, stock change and additional management benefit are different quantities.

No DOI has been added to SRC or the acquisition queue. Existing registers, votes, review receipts, ledger, configuration pin and runtime remain unchanged.


## Source/finding store implementation

`priority_store.py` prepares content-addressed objects under `priority-evidence/sources/` and `priority-evidence/findings/`. Their identities are `psrc_<full-sha256>` and `pfind_<full-sha256>`; they are not legacy SRC/EV IDs. Legacy identities are recorded only when acquisition resolves an existing canonical source. No synthetic NbS, table enum, ledger stamp or existing register change is needed.

`stage` requires the original packet at a merged revision, a selected acquisition candidate/plan and a checked acquisition bundle. It reuses `workflows/acquisition` for file/metadata verification. PDFs additionally require a matching team-library copy and project-relative library locator. Web/code sources retain their original URL, snapshot hash and section/file locator. Stage writes only to a new private directory. A separate reviewed PR may introduce unreviewed objects after the storage contract is accepted. No real source objects or votes are included in this implementation change.

```sh
python workflows/priority_classification/priority_store.py stage \
  --packet workflows/priority_classification/packets/example.json \
  --packet-revision FULL_MERGED_SHA --base FULL_MAIN_SHA \
  --candidates /private/candidates.json --plan /private/plan.json \
  --bundle /private/acquired --out /private/new-stage
```

For a PDF also provide `--library-root /local/synced/library` and `--library-path 2_Technical_&_Data/library/cross-cutting/file.pdf` (shell-quote the path). The operator supplies the genuine shared-library location; the tool checks byte identity, not SharePoint permissions.

Human finding review uses an original GitHub issue in RuralScan/evidence. Body begins `RuralScan priority finding review v1`, followed by one JSON fence containing `finding_sha256`, `finding_revision`, `decision` (`keep`, `hold`, `reject`, `reopen`) and a nonempty `reason`. The existing submission desk verifies original unedited body and eligible human author. `review --receipt ISSUE_NUMBER --base FULL_MAIN_SHA` consumes that receipt; it does not create an issue or impersonate a reviewer. Save proposed append-only `priority-evidence/reviews.jsonl` changes through the protected evidence PR route.

Latest decision per reviewer controls status. All keeps means kept; all rejects means rejected; any dissent or hold prevents release. Retry of the same receipt is a no-op. An edited receipt, older replacement, duplicate receipt identity, rewritten object or deleted history fails. Source finding review does not approve classification cutoffs.

`priority_store.py check --base FULL_TRUSTED_BASE_SHA` replays source provenance, pinned observations and review history. New review rows are authenticated against GitHub. Existing reviewed history is trusted only from the protected base supplied by CI. Use trusted checkouts; provenance receipts are operator attestations backed by acquisition replay, not cryptographic proof of publisher origin.

## Independent priority adoption

`adopt.py` uses `configuration/priority/releases/<hash>.json` and append-only `configuration/priority/adoptions.jsonl`. It does not change `configuration/method-pin.json`, compiler mirrors, ratings or runtime. The journal is the active-pin authority: each event includes its previous release and full `{repository, revision, path, sha256}` pin. No mutable `latest` pointer exists.

Adoption resolves an immutable `priority/releases/<hash>.json` on method main, executes the producer validator from that exact merged commit, replays exact acceptance, then checks current method/evidence bases for changed decisions, definitions or source holds. Source changes must merge before adoption, rather than introducing a hold and adoption in one PR. Missing approvals or unsupported producer versions fail closed. Review manifests are never adoptable.

```sh
python workflows/priority_classification/adopt.py adopt \
  --method-repo /trusted/method --method-base FULL_METHOD_MAIN_SHA \
  --evidence-base FULL_EVIDENCE_MAIN_SHA --pin /private/release-pin.json \
  --operation-id unique-operation-name
```

Use `rollback` with a previously adopted pin and new operation ID to record rollback. It passes the same current acceptance/source checks; historical reproduction does not authorize reuse of a currently held rule. Retrying an identical operation does not append a duplicate; reusing its ID differently fails. Changes remain local until a separate reviewed evidence PR merges them. CI checks immutable cache/history, authenticated source receipts and all new adoption events.

Unit tests cover real local acquisition replay, original human review authentication, conflicts/reopening, selected-versus-current source state, immutable adoption history, rollback and execution of the pinned producer rather than a mutable checkout. Method tests independently exercise complete synthetic package construction/replay. No project votes, scientific approvals or actual adoption receipts are generated by tests.


## Registration preparation, 25 November 2026

The [preparation dossier](preparations/2026-11-25/README.md) contains six proposed source objects and five original packet findings, not live registry records. It reconciles their artifact hashes with six XCS candidates and preserves the eight distinct XCE candidate findings from evidence PR #101. The crosswalk establishes source-byte identity only. No candidate ID, finding interpretation or review vote is automatically promoted.

Run `python workflows/priority_classification/preparation.py` to verify the preparation. An optional `--library-project /path/to/D591_Rural-Scan_NBS` verifies local library copies against the pinned hashes; it cannot establish remote SharePoint availability. The official store and adoption journal remain empty.

## Consolidated T5 candidate route

[CONSOLIDATION.md](CONSOLIDATION.md) supersedes the parallel XCS/XCE adapter proposal. Eight detailed findings retain complete content and reuse six prepared sources through `priority_store.py`; five earlier packet observations remain distinct. All are unreviewed preparations. The single official review ledger and existing adoption route are unchanged.
