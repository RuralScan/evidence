# Cross-cutting T5 candidate intake

This extends the five source packets into six identified source candidates and eight separate findings. Candidate IDs are not canonical SRC/EV IDs. The original packets are unchanged. The sixth source is FAO's GSOCseq input-data guidance. All findings remain unreviewed.

## Implemented

- Frozen candidate schema, proposed register manifest and bounded search protocol.
- Read-only metadata/receipt replay and optional private-original checks using the existing acquisition identity adapter. WRI's DOI resolves to the matching technical note; the five DOI-less artefacts pass opening-title checks on publisher-origin copies.
- Source/finding separation, exact locators, source scope, credibility and transfer limitations.
- Search log with six queries in two calls, 36 visible result records screened, five seed packets reused and one new document included. These are not systematic-review totals or counts of 36 independent studies.
- Content-addressed, retry-safe candidate staging. Negative checks reject fabricated practice lanes, claimed registration/acceptance, source scores, wrong locators, stale receipts/instructions/searches and T2 scope.
- Pure source-review replay tests: keep/drop/query/reopen, exact content, sequence and retry. Fixtures cast no real votes.

## Deliberately unresolved

Production registration needs the approved cross-cutting schema, authenticated protected-review adapter and team-accession receipts. PDF and web originals are privately cached but not falsely labelled team-archived. No library path is invented. A source-finding keep decision remains distinct from exact classification acceptance in method. Immutable accepted-release publication and runtime adoption remain separate work.

## Commands

Use Python 3.12 with `pymupdf==1.27.2.3` and `jsonschema==4.25.1` (CI pins both).

```sh
python workflows/priority_classification/intake.py check \
  workflows/priority_classification/batches/t5-2026-11-25/candidate.json
python -m unittest discover -s workflows/priority_classification
python workflows/priority_classification/intake.py stage \
  workflows/priority_classification/batches/t5-2026-11-25/candidate.json \
  --out /private/review-candidates
```

To verify actual bytes, append `--artifact-locations /private/source-acquisition-paths.json`. That private mapping names source candidate IDs and cache directories. No local absolute paths or full third-party originals enter this repository. Public receipts permit bibliographic replay; optional original verification rechecks bytes and opening titles.

Review [candidate findings](batches/t5-2026-11-25/candidate.json), [search decisions](batches/t5-2026-11-25/search-log.json) and [register proposal](../../registers/cross_cutting/README.md). Class interpretation belongs to the method T5 extension; this batch publishes no classifications or weights.
