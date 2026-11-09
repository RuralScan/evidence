# Discover and screen sources

Use this workflow to answer a bounded question such as “Which sources discuss annual rainfall for bench terraces?” The result is a set of candidate sources, screening reasons and search counts. Live registration, acquisition and evidence review continue in [CIAT/nbs_ruralscan](https://github.com/CIAT/nbs_ruralscan).

## Replay the terrace screening example

From the root of this repository, run the following with Python 3.10 or newer. The example runs offline using the standard library.

```sh
workflow=workflows/discovery
run_dir=$(mktemp -d)
python3 "$workflow/screen.py" stage "$workflow/example/plan.json" \
  "$workflow/example/decisions.json" --out "$run_dir/terrace"
cat "$run_dir/terrace/report.md"
```

Expect **3 distinct records retrieved, 3 screened, 1 included**. The WOCAT manual already has a source ID. It contributes one reuse candidate. The FAO passage concerns stone lines. The GIS study stays on hold because its rainfall classes are seasonal. This is a teaching selection of three public citations from a fixed stock register. The decisions illustrate screening and add no new search coverage. To reproduce the *compiled T4 row* from reviewed evidence, use the separate [terrace rainfall example](../../examples/terrace-rainfall/README.md).

## Run a new search

1. **Frame one search.** Copy [the example plan](example/plan.json) to a private working directory. Set the actual practice, family (empty for a whole-practice search), one table (T4, T3 or T6), one process, a unique run ID, inclusion criteria and limits. Choose a table for the question: T4 for suitability, T3 for hazard response and T6 for scorecard effects. Distinguish establishment from species matching, restoration priority and operational feasibility. Check existing source IDs, acquisition queue, search register, progress ledger, discovery logs and original stock inventory. A source already extracted for another family may still need screening for this question.
2. **Search and retain what came back.** Save one capture per executed query. Retain terms, channel, date, language, filters, scope and the records actually returned. Record omitted channels and languages in the plan. Use parent-practice synonyms and relevant family terms in English, Spanish, French and Portuguese where appropriate. Start with syntheses, manuals and methods, then seek primary studies for uncovered criteria. Trace promising references back to the original work and forward to applications.
3. **Screen the captured records.** Generate the worksheet below. Inspect titles, abstracts, source descriptions or methods. Record what the source covers and why it belongs in this scope. For each record that passes source-type and relevance screening, consider strength of evidence, transparency, authority, transferability, recency and seminality. Record independence or conflicts of interest in the credibility note. Give a reason for any proposed benchmark tier. A cap, unavailable channel or language gap belongs in the stop reason or omissions. Claim saturation only when further sources add no new criteria and coverage is adequate.
4. **Close and replay.** Enter the actual search close date, searcher, screener, stop reason and omissions in the plan before generating the worksheet. Keep plan, captures and completed worksheet together. Replaying frozen inputs reproduces the bundle. Re-querying a live index starts a new run and may return a different set. Keep provider abstracts, local credentials and unpublished decisions in private storage.

| Process | What to capture |
|---|---|
| `stock` | Reconcile the existing stocktake pool, titles, source IDs and missed intake. Record the inventory version and exact selection. |
| `updated_lit` | Search OpenAlex titles or the Lens scholarly index. Start with review-type terms appropriate to the provider, widen for missing methods, and keep each query. |
| `grey` | Run functional searches plus targeted agency, practice-database and repository checks. For AGRIS, run the search in the browser and capture the inspected result set manually. |
| `tool` | Inspect repositories or project methods. Record URL, commit and file path supporting relevance. A demo or README alone rarely establishes a parameter or rule. |

Use a separate plan for each table, process and scope. Keep overlaps visible across runs. A search that serves two tables may be referenced by both. Sum across scopes only after reconciling stable source identities.

### Capture records

The commands below illustrate two alternative literature searches. Run each authorized query from the repository root and list its filename in the plan's `captures` array. Change the copied plan's process from `stock` to `updated_lit`, replace the teaching question and dates, and list only the captures you actually completed. The cap applies to one page in provider order.

```sh
workflow=workflows/discovery
run_dir=$(mktemp -d)
cp "$workflow/example/plan.json" "$run_dir/plan.json"
python3 "$workflow/capture.py" openalex 'bench terraces rainfall' \
  --limit 20 --out "$run_dir/openalex.json"
python3 "$workflow/capture.py" lens '"bench terraces" AND rainfall' \
  --limit 20 --out "$run_dir/lens.json"
```

Use `--year-from 2015` to apply an inclusive lower year in either provider. For a synthesis-first Lens query, add `--reviews` to include the method’s review-type term block. The capture records the expanded query and date filter.

Supply `OPENALEX_API_KEY` when using keyed OpenAlex access. Lens requires `LENS_TOKEN`. A failed request produces an error. Record an unavailable channel in omissions or retry with a new output filename after quota/access recovers. A successful request returning no records can be staged as an observed zero. [OpenAlex search](https://help.openalex.org/api/searching/) · [Lens scholarly requests](https://docs.api.lens.org/request-scholar.html)

For a manual search, use [stock.json](example/stock.json) as a format example. Record the process (`stock`, `updated_lit`, `grey` or `tool`), channel, exact query or inventory selector, ISO date, actual limits and a `records` list. Each record needs a stable `record_id`. Copy the title, citation, URL and any DOI from the record. If identity is incomplete, use a local ID to track a hold. International titles can be preserved verbatim. For AGRIS, record the search language and stable record URL. For citation chasing, retain the parent source ID or citation and how the additional work was found. Historical reports with only aggregate counts cannot be replayed as individual captures.

### Record screening decisions

Once the plan and captures are complete, create a worksheet. Open it alongside the captures and fill it in.

```sh
python3 "$workflow/screen.py" worksheet "$run_dir/plan.json" \
  --out "$run_dir/decisions.json"
```

| Disposition | What to enter | Count |
|---|---|---|
| `include` | Reason with evidence of relevance. Check identity against the source register and queue by DOI, title and report ID. | Screened and included |
| `reuse` | Existing `reuse_source_id`; explain in `reason` why this scope needs the source. | Screened and included once before queue deduplication |
| `exclude` | Specific reason the record falls outside the criteria. Add a `referral` for related work if appropriate. | Screened |
| `hold` | What is uncertain, where you looked and what would resolve it. | Screened |
| `unscreened` | Leave untouched when the record was retrieved but not assessed. | Retrieved only |
| `duplicate` | Primary record ID in `duplicate_of` and reason the records describe the same work. | Primary record supplies counts; both IDs stay in the audit |

The same provider ID returned by several queries counts once. Inspect different IDs for the same DOI, title, report, translation or companion study. Use `duplicate` for a second identity of the same work. For a distinct work using the same method, preserve the record and describe its dependence in `lineage`. Use `parent_source_id` for citation chasing and `credibility` for the credibility assessment. An included record can carry `families`, `hazards` and `t6_targets` as lists of registry IDs. These describe the source even when the search targeted a whole practice. An optional `proposed_benchmark_tier` requires `tier_rationale`. Capture positive open-access metadata as `oa_status: "oa"` and use `"unknown"` otherwise. A DOI shared by conflicting titles requires an identity check. Preserve the original capture, document the correction in a new input version and regenerate the worksheet. Final DOI and title verification are downstream steps.

For AI-assisted screening, give the assistant the plan, captures and rubric above. Ask for a disposition and its source-grounded reason per ID, including uncertainty and related-study lineage. Record the model/version and instruction version in `screened_by`; archive the actual prompt with the run. Check weak exclusions, ambiguous matches, duplicate families of publications and proposed tiers before staging. The worksheet is bound to its input fingerprint. If inputs change, generate a fresh worksheet and reassess affected records.

### Stage and inspect

```sh
python3 "$workflow/screen.py" stage "$run_dir/plan.json" "$run_dir/decisions.json" \
  --out "$run_dir/staged"
```

Open `report.md` for verbatim queries, coverage, omissions and per-record decisions. `screening.json` maps dispositions to captures. `candidates.json` contains only included and reused sources. `protocols.json` records the exact query scope and observed funnel counts before queue deduplication. Search engine estimates do not enter these counts. An empty capture from an executed search yields a zero protocol. Use a fresh output directory for each replay.

Run `python3 -m unittest discover -s workflows/discovery` from the repository root to check capture and screening offline.

## Validate the handoff in CIAT

To confirm the teaching bundle against a disposable CIAT checkout, run the following from the evidence repository immediately after the **Replay the terrace screening example** commands above. The example uses the producer revision from which the three citations were selected. The validation command uses `uv` to select Python 3.12. With Python 3.12 already active, you can replace `uv run --no-project --python 3.12 python` with `python`.

```sh
git clone --quiet --filter=blob:none --no-checkout https://github.com/CIAT/nbs_ruralscan.git "$run_dir/ciat"
git -C "$run_dir/ciat" sparse-checkout set --no-cone '/scripts/register-discovery.py' \
  '/src/nbs_ruralscan/' '/pipeline/acquisition_queue.csv' '/schema/registers/' '/methodology/discovery_logs/'
git -C "$run_dir/ciat" checkout --quiet 1773e86e76d45ec7a61f8fbd3673047f9601072d
bundle="$run_dir/terrace"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$run_dir/ciat/src" uv run --no-project --python 3.12 python "$run_dir/ciat/scripts/register-discovery.py" \
  water_harvesting_conservation --family water_harvesting__terracing \
  --root "$run_dir/ciat" --dry-run --date 2026-11-09 --ruleset v1.8.1 \
  --run-prefix terrace_stock_training --searched-by 'offline training example' \
  --assigned unassigned --candidates stock="$bundle/candidates.json" \
  --protocols stock="$bundle/protocols.json" --reports stock="$bundle/report.md" \
  --log-names stock=terrace_stock_training.md --reuse-log terrace_stock_training_reuse.json
```

Expect `DRY RUN: complete registration batch validated; nothing published`, zero new queue entries, one explicit reuse task and a stock protocol with one inclusion. For an operational handoff, use the current CIAT checkout and substitute the plan's practice, family, date, process, run ID, searched-by value and unique log names. The dry run checks source identity, family tags and inclusion counts against those registers. Resolve identity conflicts there before handing over the bundle with its input files. The ordinary CIAT intake and review process owns publication and progress updates. Staging a bundle here records no extraction or recipe change.

After screening, use the candidate bundle to [verify and acquire one source](../acquisition/README.md).

The workflow follows the [versioned discovery instructions](https://github.com/CIAT/nbs_ruralscan/blob/1773e86e76d45ec7a61f8fbd3673047f9601072d/.agents/skills/source-command-discover-sources/SKILL.md) and [screening rubric, §3](https://github.com/CIAT/nbs_ruralscan/blob/1773e86e76d45ec7a61f8fbd3673047f9601072d/methodology/T4_generation_method.md). See the [software license](LICENSE).
