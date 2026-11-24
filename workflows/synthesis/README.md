# AI-led T3/T6 synthesis

AI authors scientific judgments. Code validates, packages and reads accepted outputs.
Authority: [method decision](https://github.com/RuralScan/method/issues/85#issuecomment-7052114229).
The [skill](../../.agents/skills/source-command-t3t6-synthesise/SKILL.md) provides the
scientific reasoning requirements. No automatic effect-scoring engine runs here.

Existing T3/T6 and T6E values remain frozen historical outputs. This workflow does not
relabel them as accepted AI results. T6E is outside the new contract. New accepted
outputs replace only explicitly named prior rows. The queue displays both historical
and accepted rows, with separate `effect_synthesis` status. Packages contain accepted
outputs only and therefore need not be complete recipes.

## Prepare and author

Run from this repository, with Python 3.12 and the workflow dependencies used by CI
(numpy, requests, PyMuPDF, Pillow), plus Git and authenticated `gh` for acceptance.
The read-only producer clone supplies pinned structural validators and definitions;
it performs no scientific scoring. `--ciat-repo` can be a bare clone with the pinned
history. Use the commands below with your actual paths and proposal ID.

```sh
python workflows/synthesis/run.py prepare --practice agroforestry --table T6 \
  --id agroforestry-t6-20261120 --task 'Review the authorised T6 cells' \
  --out /tmp/agroforestry-t6-proposal --ciat-repo /path/to/nbs_ruralscan
```

This writes exactly four files:

- `inputs.json`: generated practice effect corpus, source records, review log,
  definitions, configuration hashes and method contract hash. Preserve exact bytes.
- `skill.md`: exact skill snapshot. Preserve exact bytes.
- `rows.csv`: empty table with the required header; AI authors the scientific rows.
- `proposal.json`: unscored worksheet. AI completes candidate dispositions, model,
  skill version, full prompt, exposed settings, reasoning and before/after comparison.

Every candidate in the broad practice corpus needs one `include`, `exclude`, `context`
or `hold` disposition, a reason and origin. Included evidence must be reviewed,
undropped and unheld, with verified source identity, quote and locator. Origin labels
and compatibility are scientific assertions requiring review; validation cannot prove
that two named origins are independent. The AI must justify evidence level, agreement,
confidence, direction/strength, uncertainty, context and sensitivity separately.

`replaces` maps old record IDs to `core.replacement_digest(old_row)`, calculated from
current queue rows. This fingerprint excludes old editorial-only fields, not scientific
values. New IDs need no replacement; existing IDs require one. A withdrawal sets
`action: "withdraw"`, names the prior rows and leaves `rows.csv` header-only. Otherwise
use `action: "replace"`. Each row needs `justification.rationale`; data deficiency sets
`justification.data_deficient: true`, with blank scientific classes and asset weights.
JSON-valued CSV cells use valid JSON; booleans are `true`/`false`; blank means null.

After authoring, update only the CSV hash in proposal metadata:

```python
import hashlib, json
from pathlib import Path

folder = Path("/tmp/agroforestry-t6-proposal")
p = json.loads((folder / "proposal.json").read_text())
p["rows_sha256"] = hashlib.sha256((folder / "rows.csv").read_bytes()).hexdigest()
(folder / "proposal.json").write_text(json.dumps(p, indent=2) + "\n")
```

```sh
python workflows/synthesis/run.py validate /tmp/agroforestry-t6-proposal --ciat-repo /path/to/nbs_ruralscan
python workflows/synthesis/run.py stage /tmp/agroforestry-t6-proposal --ciat-repo /path/to/nbs_ruralscan
```

Both print the proposal SHA-256 (a canonical hash of the four file hashes). Commit
`synthesis/proposals/<id>/` and publish it for review. Capture the full Git revision.
Validation does not accept science. New evidence or definitions require preparation
again, not editing the input snapshot to make an old proposal pass.

## Scientific acceptance

An eligible human reviewer creates an **original** issue in RuralScan/evidence with
this exact body structure, substituting the actual ID, hashes and reason:

````text
RuralScan scientific acceptance v1
```json
{
  "proposal_id": "agroforestry-t6-20261120",
  "proposal_sha256": "<64-character hash printed by validate>",
  "proposal_revision": "<40-character Git commit containing the proposal>",
  "decision": "accept",
  "reason": "<scientific review of the exact judgments, not only file validity>"
}
```
````

Eligibility follows the existing submission policy: owner/member/collaborator or
maintainer-confirmed reviewer. The original issue author/body are authenticated; edited
bodies and bot receipts are rejected. A `hold` receipt uses the same proposal pin and
an explicit reason. Acceptance occurs once; after a hold use a new proposal.

```sh
python workflows/synthesis/run.py decision 123 --ciat-repo /path/to/nbs_ruralscan
```

This appends `synthesis/acceptances.jsonl` and rebuilds the publication queue. Submit
that change through a protected PR. CI verifies original receipts, proposal Git blobs,
append-only history and exact output replay. Proposals are immutable once published;
corrections use a new ID. A software PR or an evidence Keep vote does not approve a
scientific synthesis proposal. The agent must not invent a human acceptance.

## Package and consume

```sh
python workflows/synthesis/run.py package --out /tmp/accepted-effects \
  --ciat-repo /path/to/nbs_ruralscan
```

Publication re-authenticates scientific receipts and validates current inputs. Any held
or stale active output blocks the package. It exports exact accepted rows and explicit
withdrawals, never historical fallback values. T3 asset weights, when supplied, must
cover the six core hazards and sum to one; code supplies no missing weights. No class,
confidence, magnitude, family maximum, context transfer or equal weight is inferred.

The package has per-practice T3/T6 JSON, file hashes and a manifest with exact row hashes,
proposal hashes, input hashes, receipt numbers and statuses. Pin its printed manifest
SHA-256 independently in runtime configuration, not by reading the untrusted package:

```python
from pathlib import Path
from nbs_runtime.accepted_effects import AcceptedEffects

accepted = AcceptedEffects(
    Path("/path/to/accepted-effects"), manifest_sha256=TRUSTED_SHA256
)
row = accepted.row("agroforestry", "T6", "accepted_record_id")
```

Runtime verifies bytes, inventory and acceptance provenance, then returns the explicitly
selected row without modifying values or selecting a different context. Withdrawn or
missing rows cannot be read as values; their provenance remains inspectable. This is a
consumer boundary for accepted scientific outputs, not a new geospatial model.

Reproducibility means replaying exact accepted bytes, not re-running a model and assuming
the same scientific answer. Input changes mark accepted outputs stale without re-rating
them. Re-opened reviews and changed source metadata are part of that freshness check.
The contract is a pinned method definition, verified in CI against its immutable origin.
