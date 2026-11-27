# Decide whether an intervention belongs

Current runs check practice fit and nature-based-solution fit before extracting or
reusing claims. A database category, beneficial outcome or familiar technology name
does not settle either decision. These are scoping decisions, not site certification.

This protocol is `nbs-inclusion-1.0.0`. It supplements the pinned discovery,
extraction and synthesis instructions without rewriting their historical versions.

## Read the definition and the intervention

Use the authorised World Bank rural catalogue's general definition **and** the
section matching the intervention. Record its edition, SHA-256, actual locator and
the relevant clause assessment in a private inclusion record. Read adjacent scope,
exclusion and safeguard passages, not only the positive definition. A chapter name
is not itself an inclusion decision. Check neighbouring chapters when technologies
overlap. Catalogue chapters and this project's six practices are not identical:
record the crosswalk and its rationale without changing FAM.

The catalogue may be restricted. An operator must have authorised access; possession
of a link, an earlier AI summary or a public document with a similar title does not
prove inspection. If it is unavailable, record a definition-access hold. Public
references below explain the general framework but do not replace that check.
DOCX paragraph locators may support a private assessment; they are not automatically
approved Evidence Register locators. Do not ingest restricted definitions as evidence.

Inspect the intervention's verified source and diagrams. Record its primary purpose,
components, ecological mechanism and setting. For bundled interventions, identify
which component each claim describes. Whole-package environmental observations cannot
silently become component-specific thresholds.

## Check three separate questions

1. **Does the intervention belong to the requested practice and family?** Cite its
   purpose and design. For this project's water-harvesting scope, collecting and
   managing rainfall/runoff for use must be a primary purpose. In-situ soil storage
   can qualify; a tank is not required. Secondary infiltration or water retention
   in an erosion-control structure does not establish water-harvesting membership.
   If primary purpose is ambiguous or a mixed package cannot be separated, hold.
   Do not impose this water-harvesting-specific rule on all other NbS categories.
2. **Does that intervention work as an NbS in this context?** Explain what ecosystem
   is protected, restored or sustainably managed; which natural processes deliver
   the service; who benefits; and the credible biodiversity/ecosystem benefit.
   Consider baseline habitat, effects beyond the footprint, rights, trade-offs and
   durability. Record what the source reports versus what remains an inference.
3. **Does the claim answer the authorised analytical question?** Keep the existing
   T4 source-purpose gate, effect attribution, species/crop policy and operational
   routing. Inclusion does not turn observed rainfall, slope or soil classes into
   suitability thresholds. Source credibility and numerical calibration remain
   separate from practice/NbS inclusion.

The public [World Bank explanation](https://www.worldbank.org/en/news/feature/2022/05/19/what-you-need-to-know-about-nature-based-solutions-to-climate-change)
connects ecosystem action with benefits for people and biodiversity, illustrates
combined ecological and engineered approaches, and cautions against assuming every
planting benefits nature. The [UNEP definition](https://www.unep.org/en/what-we-do/nature-and-land-action/nature-based-solutions/overview-nature-based-solutions)
also covers modified ecosystems. The [IUCN criteria](https://inbs.iucn.org/understand/8-criteria/)
address context, ecological outcomes, viability, participation, safeguards and
adaptive management. The checks below operationalise these themes for this scoping
workflow; they are not an IUCN certification or a reproduction of the private catalogue.

## Record the reasoning

Use `workflows/inclusion/template.json` as the private record structure. Each
criterion needs `status`, `rationale` and `source_locator`; use `unknown` for missing
information, not a fabricated positive or negative. `definition_locator` identifies
the relevant authorised definition passage when available.

| Criterion | What to establish |
|---|---|
| `ecosystem_action` | The ecosystem and protective, restorative or sustainable-management action. |
| `natural_process` | How ecological/hydrological processes deliver the benefit; distinguish them from equipment alone. |
| `human_benefit` | Societal need, intended beneficiaries and plausible benefit pathway. |
| `biodiversity_pathway` | Credible benefit for biodiversity/ecosystem integrity, with evidence limitations. Crop yield or carbon alone is insufficient. |
| `baseline_habitat` | Existing ecosystem, degradation and conversion risks; low productivity is not proof of degradation. |
| `landscape_hydrology` | Off-site water, sediment, pollutant and habitat effects, including downstream users where relevant. |
| `equity_governance` | Rights, access, participation, burdens, benefits and unresolved conflicts. |
| `durability_management` | Maintenance, monitoring, adaptation and practical viability over time. |

Retain known contradictions as `material_conflicts`; generic conditions cannot erase
them. Distinguish an uncertain risk needing clarification from an evidenced failure
of the criterion. Engineering or non-native species alone is not an automatic veto:
assess function and context. Green appearance, crop diversity and baseline species
counts are not proof of biodiversity improvement. Avoid requiring already measured
net gain from every scoping source, but do require a defensible ecological pathway.

For all six project practices, use the actual catalogue section, not a universal
technology whitelist. Pay particular attention to ecological purpose and habitat
baseline in tree systems, hydrological processes in wetland/coastal/riparian systems,
and catchment-to-use purpose in water harvesting. Supplementary chapter references
and detailed catalogue-to-criterion crosswalks remain private.

## Dispositions and downstream use

| Result | Action |
|---|---|
| `exclude_wrong_practice` | Stop inclusion in this practice. Preserve source/evidence; offer a referral only within authorised scope. |
| `exclude_nbs` | Source establishes failure of NbS criteria. Preserve reasons and evidence; do not mislabel it as a practice mismatch. |
| `hold` | Definition unavailable, purpose unclear, core ecological pathway unsupported or material conflict unresolved. Do not carry it into accepted outputs. |
| `conditional_include` | Core pathway supported; explicit restrictions or remaining implementation checks accompany every use. Not full compliance. |
| `include_for_scoping` | Recorded scope and NbS checks pass without unresolved conditions. Still requires claim-level and human review. |

The first four criteria are core pathway checks. Unknown ancillary criteria require
explicit implementation conditions; a material unresolved conflict makes the result
a hold. A source may have no applicable off-site mechanism: use `not_applicable`
only with a reason and never for a core pathway. Water-harvesting hydrology cannot
be marked not applicable. A negative practice decision can be recorded without
pretending to have completed NbS assessment.

Run before current staging, review replay or synthesis reuse:

```sh
python3 workflows/inclusion/check.py /private/run/inclusion.json \
  --source /private/corpus/source.pdf --definition /private/authorised/catalogue.docx \
  --out /private/run/inclusion-check.json
```

`--source` checks the reviewed source bytes. `--definition` checks the declared
catalogue bytes when available. An unavailable definition produces a hold. The
command exits 0 only for scoping inclusion, 2 for a valid hold/exclusion, and 1 for
invalid or stale assessment. It records hashes and disposition, not quotations or
private source paths. Even that receipt stays private unless separately cleared.
Do not bypass exit 2 to stage a new claim as included. A historic example replay
continues under its pinned instructions and is not evidence of current admission.

At discovery, incomplete abstracts can support a provisional retrieval candidate,
not final inclusion. Complete the assessment after acquisition and before extraction.
At review, inspect prior approvals against the current rule; record supersession
explicitly and use the protected register writer. At synthesis, carry exclusions,
holds and conditions into candidate dispositions and scope. Do not change analytical
rows automatically or treat a software merge as scientific acceptance.

This is a required operator/AI procedure with a standalone validator. Legacy intake
and synthesis APIs do not yet enforce presence of this sidecar. Report that boundary;
do not claim a repository-wide admission lock. The validator checks consistency of
the recorded judgments, not their scientific truth. Independent source review and
existing human acceptance remain necessary.
