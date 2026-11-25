# Update compiler configuration

New T3/T6 scientific synthesis is AI-led. Definition adoption changes input context;
it never automatically recalculates scientific ratings. The historical format names
below remain for compatibility. Use [scientific proposals and acceptance](../workflows/synthesis/README.md)
for new effect judgments. Historical scoring lookups are reference material only.


A protected RuralScan/evidence PR adopts a method release or updates evidence-owned tool and lookup records. The [method pin](method-pin.json) names the immutable method commit, release digest and exact file hashes. The [change history](changes.json) records each source-backed edit. The [candidate manifest](../publication/recipe-candidate.json) identifies the inputs used to build T3, T4, T6 and T6E.

## Choose the owner

| Table | Row key | Provenance and compatibility checks |
|---|---|---|
| `registers/schema/registers/TOOL_tool_registry.csv` | `tool_id` | Registered source, source locator, all listed finding IDs. Tool type, validation, language and review status use the pinned method vocabulary. Practice and variable references resolve through FAM and VONT. Dataset descriptions can name the external tool’s own datasets. |
| `configuration/lookups/direction_cue_exceptions.csv` | `evidence_id` | The exception names its own finding, source, locator, rationale and existing adjudication fields. Recording an exception leaves the finding review log untouched. |
| `configuration/lookups/wocat_hazard_map.csv` | `wocat_group` + `wocat_key` | WOCAT source record and locator, supporting finding IDs when available, target T3 hazard in the pinned vocabulary. |
| `configuration/lookups/wocat_impact_map.csv` | `wocat_group` + `wocat_field` | WOCAT source and locator, defined variable in VONT, EV use role and valid comment flag. Rejected variables cannot be mapping targets. |
| Five definition registers and fifteen method policy or vocabulary tables | Keys listed in the method contract | Propose reusable definitions in method, record the scientific ruling, then adopt its release here. [Method release procedure](https://github.com/RuralScan/method/blob/e50a3a01b6b164bebed8dfd09229c4df83086c01/configuration/README.md) |

Existing pending rows keep their recorded status. A registered tool or source mapping may precede extraction. Supply the SRC ID and an inspectable locator, and use an empty supporting finding list until findings exist. For a change that cites findings, every cited finding must belong to the stated source and at least one must carry the cited locator. A human reviewer checks that the source supports the changed fields.

## Adopt a method release

Start a branch from current evidence main. Use a full method SHA containing the reviewed release. Use the CIAT checkout solely to reproduce the pinned engine.

```sh
git fetch origin main
git switch -c config/adopt-method origin/main
python3 workflows/submissions/configuration.py pin "$method_sha"
python3 workflows/submissions/configuration.py build --ciat-repo "$ciat_checkout"
python3 workflows/submissions/check_registers.py --base origin/main --ciat-repo "$ciat_checkout"
git diff origin/main --stat
```

Use the Python environment documented in [the register operator guide](../workflows/submissions/README.md). For offline verification set `RURALSCAN_METHOD_REPO` to a clone containing the selected method commit. The five register copies and `method-lookups/` are verified mirrors. Rebuilds use the committed evidence pin. A later method merge takes effect here only after a new adoption PR merges.

## Propose an evidence-owned change

1. Start a branch from current evidence main. Inspect the row and copy its `before_sha256`. A new row uses JSON `null`. Composite key names appear in the table above.
2. Create an event JSON file following [the two real examples](changes.json). Supply a unique change ID, compiler-relative table path, key, expected previous row hash, method revision, changed fields, reason and source provenance. The compiler-relative path starts with `schema/registers/` or `schema/lookups/`.
3. Record, rebuild, verify and open the branch as a PR. Review the source, changed rows and candidate. The required **Extraction and review** check replays the history, verifies method bytes and reproduces the queue. Repeating an identical event is safe. A stale row hash or a reused ID with different content requires reconciliation.

```sh
python3 workflows/submissions/configuration.py row schema/registers/TOOL_tool_registry.csv \
  '{"tool_id":"saraheb3_af_midwest"}'
python3 workflows/submissions/configuration.py record /path/to/event.json --ciat-repo "$ciat_checkout"
python3 workflows/submissions/configuration.py build --ciat-repo "$ciat_checkout"
python3 workflows/submissions/check_registers.py --base origin/main --ciat-repo "$ciat_checkout"
git add configuration registers publication/recipe-candidate.json publication/review-queue.json
git commit -m "Update the source-backed compiler input"
git push -u origin HEAD
gh pr create --base main --fill
```

## Reproduce an edition in an extraction session

At the chosen evidence Git commit, export a new disposable engine checkout. Its `schema/` includes the selected method definitions, WOCAT mappings, direction exceptions and TOOL register. `configuration-inputs.json` records the evidence commit, method commit and input hashes. WOCAT source adapters and QA checks can use this checkout. Review submissions still go through RuralScan/evidence.

```sh
python3 workflows/submissions/configuration.py checkout /path/to/new-engine --ciat-repo "$ciat_checkout"
```

Historical editions remain available at their evidence Git commits. To restore an earlier method release, adopt its full SHA in a new evidence PR and verify the candidate against current evidence-owned records. To correct an evidence-owned entry, append a new source-backed change against its current hash.

## Family transitions and broader evidence

A release may also pin `configuration/family-transition.json`. This metadata is
consumed by the [evidence hierarchy](../handbook/evidence-hierarchy.md), not as an
analytical table. Adoption records the affected original finding IDs and scopes in
`family-adoption.json`, then generates coverage without moving those findings or
their reviews. CI verifies the adoption basis and preserves it across later PRs and
rollbacks. The current transition supports the agroforestry family split; a later
transition needs an explicit compatibility update rather than replacing this history.

New synthesis inputs contain the hierarchy, source-scope warnings and current
method pin. Changed definitions make earlier accepted summaries stale; code never
relabels an old acceptance or derives new science from the definition change.
