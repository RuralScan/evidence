# Run an assisted evidence search and extraction

Use this procedure to take one authorised practice, family and table question from captured search results to page-anchored proposals for review. A researcher can do each interpretive step directly or give the task brief to an assistant. The commands read frozen inputs and check the resulting files. Live registration, correction and human review take place in CIAT.

## Choose the instructions

Record the workbench revision and select the instructions for the stage before beginning. The terrace exercise uses discovery **v1.8.1** and the workbench PDF extractor **v1.9.9**. The historical terrace evidence record carries **v1.6.0**. CIAT extraction **v1.10.0** adds guidance on distinguishing observed practice distributions from proposed suitability bounds. A live run must use the instructions and checks for its actual version. Keep the original version on every historical record. [Ruleset catalog](../rulesets/catalog.json) · [Terrace example and rerun commands](../examples/terrace-rainfall/README.md)

## 1. Frame and capture the search

Prepare a private working directory and a plan with a run ID, practice ID, family ID, table, discovery process, purpose, inclusion criteria, actual limits and stopping rule. Use one plan per scope and process. Check existing stock, source IDs, acquisition queue, search records and the progress ledger. Account for stock, updated literature, grey literature and tools. Record omitted channels and languages. [Search plan example](../workflows/discovery/example/plan.json)

> Using the attached scope, suggest search terms and sources for this family and table. Explain what each query could find and give its language and limits. List possible gaps separately. Mark every query as proposed until there is a saved result from executing it.

Run each authorised query through the supported capture route. Each capture records its process, channel, query or inventory selector, date, limits and returned records with stable IDs. Close the plan with the actual date, captures, operators, stop reason and omissions. A successful empty result is a recorded zero. Leave an inaccessible channel unresolved and retain the reason. [Discovery commands and capture formats](../workflows/discovery/README.md#capture-records)

## 2. Screen the frozen records

Generate the worksheet with `screen.py worksheet`. Give the screener the closed plan, captures, worksheet and rubric. Keep the input fingerprint and record IDs intact. [Screening procedure and dispositions](../workflows/discovery/README.md#record-screening-decisions)

> For each inspected record, enter its disposition and reason in the supplied worksheet. Cite what the captured record says about the practice, setting, method or outcome. Distinguish a duplicate publication from a separate study using the same data. Explain uncertain identities, generic practice matches, proposed tiers and any referral. Leave uninspected records unscreened.

The worksheet has `input_sha256` and a `records` list. Use `include`, `reuse`, `exclude`, `hold`, `unscreened` or `duplicate`. A reuse needs an existing `reuse_source_id`; a duplicate needs `duplicate_of`. For records passing relevance, examine strength, transparency, authority, transferability, recency, seminality and independence. Retain the rationale for a proposed tier. Inspect weak exclusions, disputed identities and holds before running `screen.py stage`. Its outputs are `candidates.json`, `protocols.json`, `screening.json` and `report.md`. The source, retrieval and inclusion counts refer to that particular scope. If a capture changes, regenerate the worksheet and reassess affected decisions. [Completed screening worksheet](../workflows/discovery/example/decisions.json)

## 3. Verify the actual source

Use the screened citation as the identity anchor. Run `verify`, `acquire` and `check` with the selected candidate ID and acquisition plan. For DOI sources, examine the resolved DOI and title. For a DOI-less manual, verify the publisher route and the title in the file. Before extraction, check the receipt, file digest, edition and locator. Keep the verified bytes and receipt privately. Resolve edition changes, unreadable files, missing provenance and unsupported formats before drafting claims. [Acquisition commands, verification and recovery](../workflows/acquisition/README.md)

## 4. Extract and challenge each claim

For the supported PDF route, use `extract.py inspect` to find and read the page in the verified file. Copy the worksheet structure. Supply `source_id`, `artifact_sha256`, `scope`, `coverage`, `inspected_pdf_pages`, `source_purpose` and `inventory`. Scope contains `nbs_id`, `suitability_family_id`, `variable` and `use_role`. Keep sources, roles and pages within the authorised question. [PDF extraction worksheet](../workflows/extraction/example/terrace-rainfall.json)

> Read the supplied pages and identify the passage establishing the source’s purpose. For each relevant passage, return a worksheet inventory entry with its PDF page, disposition and reason. For an extraction, give exact start and end phrases from that page and one atomic draft. Identify the practice, variable, units, geographic or crop restrictions, attribution and what the number measures. Record missing context, calibration limits, referrals and omissions explicitly.

Source purpose uses `pass`, `hold` or `exclude`. A pass needs a located anchor. Inventory entries use `extract`, `hold`, `exclude` or `referral`. Stage into a new private directory. Read both `staging.json` (proposed units) and `inventory.json` (pages, scope, dispositions and IDs). An empty staging list can accompany a completed inspection. Use the CIAT content checks on a disposable copy before handing over a proposal. [Extraction, content checks and historical comparison](../workflows/extraction/README.md)

> Independently check each staged claim against the verified original page. Check the variable, the table heading or surrounding sentence, the units, the practice and its scope. Distinguish an observed site range from a scored response. Record the evidence ID or inventory position, your finding and the change or source check needed. List any unchecked pages or claims.

In the terrace example, PDF page 129 describes forward-sloping benches in a 200–600 mm/year setting. The worksheet keeps those values in `context.reported_values`. Suitability at 350 mm/year remains unscored. Preserve a disputed interpretation as a hold for human review. Record who or what performed the challenge and whether they examined the source independently of the draft author. Keep the source-page finding with the disputed proposal.

## Record and hand over the run

Keep the actual inputs and output files together in private storage. Record provenance while each stage runs.

| Record | What to retain |
|---|---|
| Scope and instructions | Run ID, scope, stage, workbench revision, ruleset version, exact instructions used and their SHA-256. Include any additional stage brief. |
| How work was done | For human work, record the operator in the private run record. For assisted work, record the provider, exact model identifier/version as exposed, settings used, actual prompt and its digest. Identify the material supplied to the model. Mark an unavailable identifier as unknown. For a replay, identify the frozen worksheet and its digest. |
| Inputs, outputs and tools | Queries and capture parameters, source identity, edition, locator, artifact digest, definition and compiler pins when used, tool versions and input/output hashes. Keep restricted passages, provider responses and reviewer details privately under their applicable terms. |
| Findings and decisions | Record checks run, failures, untested scope, independent review findings, unresolved holds and next action. Link actual CIAT review events and any resulting release when available. Record later compilation separately from staged proposals. |

Record the retained inputs, actual prompt files and checked outputs in a private run record. [Create and verify a run record](../workflows/run_record/README.md)

For the worked exercise, run `python3 examples/terrace-rainfall/run-workflow.py --out "$work/terrace"` from the repository root, with `work` set to a new private working directory. It replays three screening decisions, stages one WOCAT observation and independently reproduces the historical recipe row. The replay performs no fresh search, model call or human approval. Use CIAT when a proposal needs registration or a reviewer decision. [Worked example](../examples/terrace-rainfall/README.md) · [Find the corresponding review record](review-records.md)
