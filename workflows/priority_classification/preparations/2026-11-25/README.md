# First source-registration preparation

**Proposed, not registered.** Six source objects and five original packet findings are prepared here. The official `priority-evidence/` store has no records from this batch. There are no human votes, accepted classifications, binding verifications or releases.

## Source access and identity

The six originals were copied without alteration to the project's OneDrive-synced library under `2_Technical_&_Data/library/0_Methodology_&_Frameworks/priority_classification/2026_11_25/`. The manifest records exact relative paths, byte counts and SHA-256 values. Both PDFs passed existing acquisition/title checks; the WRI receipt retains its verified Crossref facts. Four HTML snapshots preserve the checked page editions.

Local mirror copies were read back and hashed. Remote SharePoint accessibility has **not** been confirmed; do not mark that gate complete from this dossier. The full third-party originals are not committed to Git. Metadata and acquisition provenance are preserved in the proposed objects. No legacy SRC IDs were fabricated.

The three already prepared web-source identities are reused. New identities are prepared for Copernicus SPEI, the WRI technical note and FAO GSOCseq input documentation. Different acquisition attempts for the same source bytes do not justify duplicate source registrations.

## Reconciliation with the T5 candidate route

[Evidence PR #101](https://github.com/RuralScan/evidence/pull/101) proposes XCS/XCE candidate records; [PR #102](https://github.com/RuralScan/evidence/pull/102) implements content-addressed source/finding storage. The candidate bundle is pinned by full commit and file hash in `manifest.json`. All six XCS candidates map by identical original-artifact hash to a proposed `psrc_` object. These are proposed mappings, not canonical registration receipts.

Eight XCE candidate findings retain their own IDs and content. Five earlier packet findings are broader observations and are **not** declared equivalent to those eight findings. The FAO input-documentation source has no earlier packet finding. Do not turn that source-only record into a fabricated finding or inherit a review from another observation.

| Source | Original packet finding | T5 candidate observations |
|---|---|---|
| Copernicus SPEI | Event classes and interpretation limits | Event classes; long-term classification still unresolved |
| WRI Aqueduct 4.0 | Provider bands, support and limits | Quantity/support and provider bands remain separate |
| Earth Engine Aqueduct catalogue | Dataset fields and documentation limits | Catalogue-field observation |
| LandMark | Incomplete mapped coverage | Coverage/absence interpretation |
| FAO GSOCseq definitions | Stock/change/potential distinction | Additional-change definition and horizon/rate interpretation remain separate |
| FAO GSOCseq inputs | None | Stock-input guidance; does not verify potential-output binding |

`priority_store.fetch_review` now loads the authenticated submission adapter by exact file path. Both routes have an `intake.py`; Python's generic module cache must not substitute candidate intake for authenticated human review. The regression test deliberately preloads an unrelated `intake` module.

[Readable source-finding cards and storage-decision draft](review-cards.md) support review without generating votes.

## Concrete remaining gates

1. Confirm remote accessibility of the six archived originals. Preserve original bytes and locators.
2. Review and explicitly accept the storage contract through the method decision route. A machinery merge does not supply this ruling.
3. Resolve XCS/XCE candidate ownership in the companion T5 proposal. Prefer these source identity mappings rather than registering duplicates. A reviewed adapter must preserve each finer-grained finding's passage, values, scope and uncertainty; it cannot copy candidate votes or silently collapse observations.
4. Introduce selected source/finding objects through a separate evidence registration PR. This preparation is not that activation.
5. Obtain original human source-finding decisions against the exact registered finding revisions. Human review cannot be prefilled by the agent.
6. Complete bindings and classification/context decisions separately. The event-level SPEI candidate is not a long-term T5 drought default; Aqueduct endpoints/arid handling, mapped IPLC absence and carbon potential remain unresolved.

No actual dataset samples, country calibration or runtime files were changed. Binding work must verify asset/band, units, valid domain, temporal reducer, period, scenario and spatial support before any `verified` claim. Existing illustrative classifications remain blocked.
