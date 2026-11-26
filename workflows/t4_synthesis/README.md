# AI-authored T4 proposals and accepted mapping packages

AI authors suitability judgments. Code checks the declared representation and
replays exact human-accepted bytes. This route does not run the retired T4 compiler,
write CIAT registers, change finding reviews, or implement a runtime evaluator.
The [contract](contract.json) is pinned to its immutable method origin in
[`contract.lock.json`](contract.lock.json). The [skill](../../.agents/skills/source-command-t4-synthesise/SKILL.md)
and contract must be used together.

Use Python 3.12 with the dependencies in the Evidence checks workflow, Git and
authenticated `gh`. `--ciat-repo` points to a read-only clone/bare repository with
the pinned historical reader and structural definitions. Its dirty working files
are not input. Current official registers and method configuration come from this
RuralScan/evidence checkout.

## 1. Prepare the evidence and prior mapping

```sh
python workflows/t4_synthesis/run.py prepare \
  --practice water_harvesting_conservation \
  --family water_harvesting__terracing \
  --id terracing-slope-proposal --task 'Assess the authorised terracing slope mapping' \
  --out /tmp/terracing-slope-proposal --ciat-repo /path/to/nbs_ruralscan
```

Use a family ID present in the current FAM register. Preparation checks that ID;
it does not infer family identity from a label. Exactly four files are written:

- `inputs.json`: practice-wide suitability/operational candidates, matching pending
  `override_candidates`, full registered source records (including registered
  references cited by those overrides), review log, current definition rows and
  hashes. The authoritative override CSV hash is frozen too. Preserve exact bytes.
- `skill.md`: exact instruction snapshot. Preserve exact bytes.
- `rows.csv`: empty ordered contract header; the agent authors mapping rows.
- `proposal.json`: unscored worksheet, task, model/prompt/settings, reasoning,
  candidate dispositions and explicit before/after comparison.

Read previous `publication/review-queue.json` mappings and review decisions.
Account for every candidate as `include`, `exclude`, `context` or `hold`, with
reason and originating study. Operational, observed, species, unreviewed, dropped,
held and unresolved historical-scope findings remain visible for disposition;
they cannot silently supply a calibrated practice rule. Broader practice evidence
needs a finding-specific applicability explanation. Sibling scope does not transfer.
Crop admission follows the pinned policy. Recorded calibration/applicability holds
require a reviewed finding correction before inclusion.

## 2. Author and validate

One proposal addresses one current suitability family. Each row declares a
variable, bound dataset, spatial context/support, limitations and separate
variable-use, direction, calibration, precision and mechanism rationales. Explain
binding, transfer, exclusion and weight choices, even when no weight is proposed.

Contract v1.1 retains `piecewise`, `threshold`, `ranked_classes` and
`qualitative`, and adds the exact response/profile types below. Parameters are exact:

| Representation | `relationship_params` beyond `unit` and `missing: null` |
|---|---|
| `piecewise` | `points: [[input, score], ...]`, strictly increasing inputs; `below` and `above` explicitly null or authored score. Linear interpolation inside the points; exact endpoints use their point scores. |
| `threshold` | `operator: lt/le/gt/ge`, `threshold`, `pass`, `fail`. No inferred endpoint convention. |
| `ranked_classes` | `classes: {"class-code": score, ...}`. Unknown classes return null. |
| `qualitative` | `note`. Requires `readiness: calibration_hold`; it remains visible but blocks packaging. |
| `logistic` | `x20`, `x80`: increasing finite anchors where membership is exactly 0.2 and 0.8. |
| `log_logistic` | Positive `x20`, `x80`; logistic in log input. Zero maps to zero; negative input is invalid. |
| `composite_scoping` | Typed profile described below; structured inputs and outputs rather than a scalar curve. |
| `precomputed_unit_index` | Typed native-score/source-area profile described below. |

Scores are in [0,1], not probabilities. Units must match the canonical quantity;
the agent documents any source conversion before proposing values. No scores,
missing tails, crop thresholds or weights are filled automatically. Other response
forms require a reviewed contract extension, not an unrecognised parameter.

`justification.boundary_cases` contains objects with `input`, `expected` and
`reason`. Cover every endpoint and both sides plus missing input; categorical
profiles cover every class plus an unknown class. These examples check exact
encoding. Scientific review still assesses the mechanism, source precision,
compatibility, dependence, proxy use and transfer—not just test success.

`applicability` has `scope_type`, `scope_id`, `spatial_support`, `limitations`.
Global uses `scope_type: global`, `scope_id: ""`; other contexts must exist in T7.
This version keeps context mappings separate and does not infer override precedence.
`justification.evidence_applicability` maps every supporting evidence ID to its
source-based applicability explanation.

`replaces` maps prior mapping IDs to `core.replacement_digest(old_row)`, using rows from
the current queue. This omits only historical editorial `justification`; it retains
all scientific fields and the complete rationale of an accepted AI mapping.
A new ID cannot bypass replacement of an existing scientific
cell. To withdraw a mapping, use `action: withdraw`, exact replacement hashes and
header-only `rows.csv`. Reversal uses another proposal that explicitly restores
earlier accepted values; never rewrite history.

After authoring, update only the row hash in proposal metadata:

```python
import hashlib, json
from pathlib import Path
folder = Path('/tmp/terracing-slope-proposal')
p = json.loads((folder / 'proposal.json').read_text())
p['rows_sha256'] = hashlib.sha256((folder / 'rows.csv').read_bytes()).hexdigest()
(folder / 'proposal.json').write_text(json.dumps(p, indent=2) + '\n')
```

```sh
python workflows/t4_synthesis/run.py validate /tmp/terracing-slope-proposal --ciat-repo /path/to/nbs_ruralscan
python workflows/t4_synthesis/run.py stage /tmp/terracing-slope-proposal --ciat-repo /path/to/nbs_ruralscan
```

Both print the proposal SHA-256. Stage copies immutable files to
`suitability/proposals/<id>/`. Commit them and open a protected PR for scientific
inspection. Capture that full commit SHA. File validation and PR approval do not
constitute scientific acceptance.

## 3. Human scientific acceptance

An eligible human creates an **original issue** in RuralScan/evidence:

````text
RuralScan T4 scientific acceptance v1
```json
{
  "proposal_id": "terracing-slope-proposal",
  "proposal_sha256": "<exact 64-character proposal hash>",
  "proposal_revision": "<full 40-character commit containing the proposal>",
  "decision": "accept",
  "reason": "<scientific interpretation and approval scope, not only schema validity>"
}
```
````

The issue author must meet the existing reviewer eligibility policy. Edited bodies,
bot receipts, wrong-lane receipts and mismatched Git blobs are rejected. An agent
must never invent this approval. A `hold` can stop an unaccepted proposal or challenge
an accepted one, using the same proposal pin and a reason. An initially held proposal
applies no output. Once held, use a new proposal for renewed acceptance.

```sh
python workflows/t4_synthesis/run.py decision 123 --ciat-repo /path/to/nbs_ruralscan
```

This appends `suitability/acceptances.jsonl` and rebuilds publication files. Failure
rolls back the journal and generated files; retry does not double-apply. Submit the
diff through a protected PR. CI checks authenticated receipts, append-only history,
proposal hashes and exact queue replay. Keep findings, sources and their review
history unchanged; corrections use existing finding routes.

Accepted mappings overlay only explicitly replaced historical rows. Other rows
remain historical. `t4_synthesis.rows` reports accepted, stale or held status.
Changed sources, evidence, reviews, configuration or definitions make affected
practice input packets stale. A later rating hold/rejection on exact accepted row
bytes also blocks packaging. Editorial wording cannot mutate accepted science.

## 4. Package for the separate runtime consumer

```sh
python workflows/t4_synthesis/run.py package --out /tmp/accepted-t4 \
  --ciat-repo /path/to/nbs_ruralscan
```

Packaging re-authenticates receipts and refuses held or stale active mappings.
The manifest pins each file, proposal, input packet, acceptance receipt and exact
row hash. Explicit withdrawals are retained. No historical or provisional row is
substituted for a missing accepted mapping.

This is `ruralscan.accepted-t4.v1`, a **partial mapping package**. It explicitly sets
`runtime_implemented: false`. It is not a complete recipe, T4_RUN policy or a claim
that raster execution, context selection or whole-recipe weighting is implemented.
Runtime integration must separately validate this format and select the intended
accepted context. Pin the printed manifest SHA-256 through that consumer's own
reviewed configuration. Do not auto-update runtime or infer missing criterion weights.

## Acceptance tests

`python -m unittest discover -v -s workflows/t4_synthesis` exercises synthetic
prepare/validate/stage/decision/package, retries and failed-write rollback,
authentication, source/review eligibility, family scope, boundary/unit failures,
staleness, late challenges, exact rating holds, withdrawals and reverse-delta
restoration. Fixtures are not real reviewer acceptance or approved scientific rows.


## Typed pending profiles and reference execution

`profiles.py` validates a bounded typed representation and evaluates small examples
in physical units. It is not a raster adapter, runtime deployment or scientific
acceptance. Quantities, datasets, numerical anchors and screens are authored in
configuration; no agroforestry or mangrove thresholds are embedded in the evaluator.

A profile has exact keys `type`, `unit: "dimensionless"`, `missing: null`, `scope`
and `inputs`, plus its type-specific fields. `scope` is a list of objects with
`nbs_id`, `family_id`, `subpractice_ids`, `pathways`. Climate lists must explicitly
name subpractices and pathways. Unit-index profiles may explicitly use null lists
for unrestricted subpractice/pathway within the named family. A missing or
mismatched context returns `outside_review_scope`, no score or climate exclusion.
Multiple NbS may be represented in a pending candidate; an official proposal still
addresses only one current family.

Each named `inputs` object declares exactly `variable`, `dataset_id`, `unit`,
`valid_range: [minimum, maximum]`. This includes every derived output. Ranges reject
invalid data; they do not clip it or create suitability cutoffs. Numeric booleans,
NaN and infinity are rejected. Missing is null. Reference execution receives
physical values; pinned source decoding and spatial support remain the adapter's
responsibility. Arbitrary expressions and undeclared profile fields are rejected.

### Composite scoping

Additional exact fields:

- `score`: tree containing only `{kind: "minimum", children: [...]}` and
  `{kind: "logistic" | "log_logistic", input, x20, x80}`. A minimum has 2–16
  children; depth is at most eight. Unknown children propagate unknown, except the
  explicitly defined empty thermal season below. No product or compensating mean.
- `screens`: objects `{id, input, operator, threshold, water_bypass}`. Operators
  are `lt`, `le`, `gt`, `ge`; equality follows that declaration. Screens reference
  component inputs, never the combined score. A thermal screen cannot be bypassed
  by water context.
- `thermal_season`: null, or `{kind: "periodic_monthly_temperature_season", input,
  mean_output, days_output, month_lengths, threshold, operator: "ge",
  empty_season_score: 0}`. The three IDs must be separate declared inputs; units
  are `degC`, `degC`, `days`. Month lengths are the ordinary 365-day no-leap
  calendar. Interpolate monthly values linearly at day-number month centres,
  wrapping December/January. Count all daily means meeting the threshold; average
  those days. There is no moisture/snow selection. A complete series with zero
  qualifying days returns duration zero, mean null and explicit mean-membership
  zero. A missing monthly value leaves both derived quantities unknown. Supplying
  derived values directly is forbidden; coupled or otherwise substituted metrics
  cannot bypass the declared derivation.
- `water_policy: "conditional_unscored"`, `combined_score_cutoff: null`, `weight:
  null`. No implicit combined-score footprint or criterion weighting.

Context declares `nbs_id`, `family_id`, `subpractice_id`, `pathway`,
`host_state: present/absent/unknown`, `legal_state: clear/excluded/unknown`, and
`water_context: ordinary_rainfed/mapped_potential_refuge/unknown`. A mapped refuge
requires `water_evidence_ref`. Existing host/legal exclusions prevail, followed
by non-bypassable component screens. A mapped refuge is conditional and unscored;
it cannot rescue cold. Known exclusions remain visible when another input is
missing. Unknown water context retains the climate score but remains
`climate_pass_water_context_unresolved`, never default rainfed eligibility. Climate membership is neither probability nor a hectare multiplier.

### Precomputed unit index

Additional exact fields: `score_input`, `area_input`, `area_to_hectares: 100`,
`area_policy: "whole_units_partial_bounds_no_prorating"`. Exactly two input
quantities from the same declared dataset/release: native dimensionless score with validity range [0,1], and source area
in km2 with nonnegative validity domain. Positive area requires positive score.
Zero/zero returns `no_modelled_restorable_area` with no suitability ranking; it
is not universal ecological infeasibility. Missing returns unknown; zero mismatch,
negative area or out-of-range score is invalid. No rescaling or clipping.

Context additionally needs `unit_id`, `spatial_relation: whole/partial`, and
`geometry_valid: true/false/null`. Missing geometry is unknown, invalid geometry
blocks spatial use. Include the pinned release in unit identity. Union overlapping
AOIs before evaluating units; exclude boundary-only touches. Duplicate unit IDs
are rejected by `evaluate_units`. Callers must verify overlap/topology independently.
For eligible whole units, report source km2 ×100 once. Partial units have no point
estimate and bounds [0, source hectares]. No polygon prorating, score-weighted
hectares or assumption that support polygons map eligible restoration footprints.
Unresolved/excluding independent gates add no automatic eligible area.

### Pending candidate route and publication gate

Candidate exact keys: `format: "ruralscan.t4-profile-candidate.v1"`, `id`,
`status: "pending"`, `activate: false`, `profile`, `justification`, `evidence_refs`.
Justification has separate nonempty strings `rationale`, `mechanism`,
`source_relationship`, `analyst_choices`, `transfer_limits`, `binding`,
`area_accounting`, `replacement_policy`, `approval_remaining`. Each source ref has
`source_id`, `citation`, `url`, `locator`, `claim_role`, `admission_status` strings.
These references do not create EV, prove source admission or approve a transfer.

```sh
python workflows/t4_synthesis/profiles_cli.py validate suitability/overrides/candidates
# Once committed, also verify exact HEAD blobs:
python workflows/t4_synthesis/profiles_cli.py validate suitability/overrides/candidates --committed
python workflows/t4_synthesis/profiles_cli.py evaluate candidate.json --inputs example.json
```

An evaluation example has `{ "values": {...}, "context": {...} }`. Outputs are
explicitly pending and inactive. This command never stages an official proposal,
changes registers, accepts science or emits a runtime package.

An official row uses `relationship_type` equal to its profile `type` and the full
profile as `relationship_params`. It still needs an adopted parent quantity and
binding, every input/derived quantity in VONT/T1 with its preferred usable BIND,
registered subpractice scope, eligible reviewed structural evidence, complete
rationales, exact replacements and original human scientific acceptance. Held
numeric profiles with unresolved definitions cannot enter the official route;
keep them in the pending candidate route. Structured boundary examples use
`input: {values, context}` and the complete expected result; missing, outside-scope, numeric-score and independent-exclusion examples are mandatory.
Unit profiles additionally cover whole, partial and zero area. Composite profiles
cover every named screen, conditional water and a known empty thermal season. Scientific reviewers must also inspect the
component endpoints/screens and mechanism. `weight_default` must remain null for
these profiles. Package/runtime separation and all v1 source/evidence gates remain.

Preparation reads the CSV-authoritative pending catalog when present. Account for
its matching candidate scopes, proposed functions, mechanisms and holds in the AI
reasoning; pending presence never authorizes application. Candidate-only source
references remain explicitly unregistered until source admission. Changes to the
catalog or any referenced registered source make the input snapshot stale. Neither
this projection nor source verification adds EV or accepts a numerical rule.
