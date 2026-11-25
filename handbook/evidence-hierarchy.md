# Find evidence at more than one level

Findings can describe a subpractice, a suitability family, a broader evidence group,
or a whole practice. More detail must not hide useful broader evidence. This view
preserves each finding's original scope and review state; it does not assign effects
or suitability thresholds.

The hierarchy follows the [adopted method decision](https://github.com/RuralScan/method/blob/7d447297742d6d4aaf0cd66709ef7ccf68e8c0af/configuration/agroforestry-definitions.md).
`configuration/method-pin.json` pins the definitions and transition metadata.
`configuration/family-adoption.json` records the immutable evidence revision at adoption.
No evidence, source, search, review or acceptance record is rewritten by adoption.

## Read the coverage

```sh
python workflows/submissions/family_hierarchy.py \
  --scope group:agroforestry__linear_plantings --lane T3/T6
python workflows/submissions/family_hierarchy.py \
  --scope subpractice:windbreaks_shelterbelts --lane T4
```

These commands only read records. Omit `--lane` for all roles. The publication queue's
`evidence_hierarchy` contains the same nodes, finding joins and coverage for all lanes.
Dashboard presentation can consume that field; this adoption does not alter the UI.

| Field | Meaning |
|---|---|
| `direct_evidence_ids` | Findings recorded at this exact level. |
| `descendant_evidence_ids` | More specific findings, counted once at this broader level. |
| `broader_evidence_ids` | Findings explicitly at an ancestor level, or unassigned practice-level findings. Inspect applicability; they do not become child evidence. |
| `legacy_scope_evidence_ids` | Older family attribution in the surrounding hierarchy that still needs source-scope review. These are pointers, not support assigned to the child. |
| `total` | Union of direct and descendant finding IDs, including rejected history. |
| `retained_total` | Reviewed-kept + pending + held findings; rejected records excluded. |
| `reviewed_kept`, `pending`, `held`, `rejected` | Separate review-state counts. Holds remain visible. |

An empty child means no directly attributed findings, not a zero effect or proof of
unsuitability. A broad result does not establish the same result for every child.
Finding counts are not independent-study counts or scientific acceptance. Synthesis
still checks source overlap, compatibility, conflicting signs and current eligibility.

## Preserve historical family attribution

Old `agroforestry__linear_boundary` findings remain at that historical scope. They
appear under the broader **Linear plantings** group, without becoming wind-shelter,
boundary-planting or contour-buffer findings. Old planted-silvoarable findings also
retain their earlier scope: that family previously included boundary planting.

The adoption record identifies both affected cohorts. Search protocols and progress
are not copied to new families. Correcting another field on an existing legacy finding
remains possible: intake uses a temporary historical family definition only for that
same finding ID, practice and family. New findings cannot use a retired family ID.

A source-reviewed scope correction uses the normal approved extraction route and
the same `evidence_id`. It reopens the finding; its earlier review remains history.
For an explicit subpractice, group or broad practice attribution, place this metadata
inside the existing EV `context` object:

```json
{
  "evidence_scope": {
    "level": "subpractice",
    "id": "windbreaks_shelterbelts",
    "rationale": "Source passage establishes this scope; include its locator."
  }
}
```

Allowed levels are `subpractice`, `family`, `group` and `practice`. A subpractice or
family must match the recorded family. A group or practice uses broad attribution
(`agroforestry__cross_family` for agroforestry), not an unrelated specific family.
No column or finding ID changes are required. Do not infer subpractice from a title,
copy a finding into several children, or inherit previous approval for changed scope.

## Write a broader scientific summary

Use the [AI synthesis workflow](../workflows/synthesis/README.md#broader-effect-summaries).
An authored effect summary needs explicit child coverage, unresolved gaps, source
applicability and conflict reasoning, followed by the existing authenticated human
acceptance. A broader group is not a suitability family. Its summary never pools T4
placement rules and is published separately from runtime recipe outputs.
