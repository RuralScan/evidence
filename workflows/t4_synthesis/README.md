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

- `inputs.json`: practice-wide suitability/operational candidates, full source
  records, review log, current definition rows and hashes. Preserve exact bytes.
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

This first contract supports `piecewise`, `threshold`, `ranked_classes` and
`qualitative`. Parameters are exact:

| Representation | `relationship_params` beyond `unit` and `missing: null` |
|---|---|
| `piecewise` | `points: [[input, score], ...]`, strictly increasing inputs; `below` and `above` explicitly null or authored score. Linear interpolation inside the points; exact endpoints use their point scores. |
| `threshold` | `operator: lt/le/gt/ge`, `threshold`, `pass`, `fail`. No inferred endpoint convention. |
| `ranked_classes` | `classes: {"class-code": score, ...}`. Unknown classes return null. |
| `qualitative` | `note`. Requires `readiness: calibration_hold`; it remains visible but blocks packaging. |

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
