# T4 evidence overrides: climate and mangrove rules

The override representation and reference evaluation are implemented for review. The numerical relationships remain **pending scientific approval**, with `activate=false`. This implementation does not change accepted T4 mappings, opportunity hectares, source findings or runtime configuration.

Overrides let the synthesis agent carry a deliberate, justified relationship into its T4 proposal when a pooled literature relationship would be inappropriate. Each record preserves scope, source provenance, mechanism, the exact function, its limitations and the intended treatment of existing variables. Source admission, evidence review, scientific acceptance and runtime activation remain separate.

Contract extension: [method PR #130](https://github.com/RuralScan/method/pull/130).

## What is implemented

- Exact logistic and log-logistic 20/80 membership functions; no piecewise approximation.
- Typed nested minimum operators and an explicitly defined temperature-only seasonal derivation.
- Explicit practice, family, subpractice and establishment-pathway scope; scope may contain more than one practice. Official accepted proposals still address one current family at a time.
- Separate continuous scores, named exclusion screens, missing values and conditional water pathways.
- A precomputed native-score relationship with independent source-area accounting for mangroves.
- An authoritative CSV and generated typed candidate JSON, with validation and reproducible examples. Pending candidates cannot serve as accepted mapping packages.

These are deterministic checks of authored rules. They do not fit ecological thresholds, manufacture evidence claims or approve the relationships.

## Pending rules created

| Rule | Proposed function and scope | Mechanism and interpretation |
|---|---|---|
| Planted silvoarable agroforestry | Moisture log-logistic: membership 0.20 at AI 0.20 and 0.80 at AI 0.46. Explicitly planted alley cropping/tree intercropping. | Long-term water supply relative to atmospheric demand constrains establishment and persistent growth. Ecological transition anchors are transferred into a scoping convention, not fitted planting success. |
| Farmer-managed/assisted natural regeneration | Moisture log-logistic: membership 0.20 at AI 0.03 and 0.80 at AI 0.20. Rainfed AI below 0.03 is separately screened. FMNR and ANR on farmland aimed at persistent upright trees. | Regeneration can avoid part of the planted-seedling bottleneck, but it is not exempt from severe water limitation. Climate-class boundaries inform a provisional planning convention. Retention-only parklands do not inherit recruitment constraints. |
| Planted silvopastoral agroforestry | Same planted moisture function, limited to named planted livestock systems. | No automatic transfer to pastoral regeneration or retained trees. Existing host and ecosystem constraints remain independent. |
| Mangrove restoration | Preserve archived `OVERALL_SCORE` unchanged where modelled `Restorable_km2 > 0`. Pin Worthington et al., Zenodo record 11283186, v1, 24 May 2024. | Relative modelled restoration ease in historically lost mangrove systems. This is not survival probability, current mangrove extent or a site-feasibility determination. |

For the three agroforestry records:

`climate_support = min(family_moisture_support, min(thermal_mean_support, thermal_duration_support))`

Cold membership uses a logistic with 20/80 anchors at 3/10°C and a log-logistic with anchors at 30/130 thermal days. A separate screen excludes mean temperature below 3°C or fewer than 30 thermal days; equality is retained. The source's coupled climate belts are explicitly transferred to a new temperature-only proxy. This operator prevents wetness compensating for cold or warmth compensating for dryness. It is not a fitted physiological interaction.

Temperature-only thermal metrics use a 365-day periodic linear reconstruction of monthly mean 2-m air temperature. Count all days at or above 0.9°C and average those days. Complete zero thermal days means known severe cold; incomplete climate data means unknown. Released water-limited CHELSA GSL/GST is not an independent cold input. The proposed historical climate pair uses Global-AI v3 (1970–2000) and CHELSA v2.1 temperature (1981–2010); the mixed baselines, snow omission and mountain/frost limitations remain explicit.

Mapped potential water refuges are conditional and unscored, not automatic opportunity hectares. They cannot override known cold, host or legal exclusions. There is no common combined-score cutoff, no inferred criterion weight and no multiplication of membership by hectares.

## Mangrove area and release safeguards

The selected archive belongs to the Mapping Ocean Wealth research lineage. Live Mapping Ocean Wealth/Global Mangrove Watch values are not silently substituted for the pinned release. Preserve the source's score range of 0–1; do not divide by 100 or rescale its observed range.

Source estimated restoration area is `100 × Restorable_km2` hectares. For a whole source unit, retain that estimate once. For a partial unit without verified loss allocation, report an unresolved allocation interval from zero to the source unit estimate. Whole-unit estimates and partial-unit bounds may be summed only after AOIs have been unioned and source unit IDs deduplicated. These are allocation bounds, not confidence intervals. Missing coverage stays unknown. Zero area with zero score means no modelled restorable area in this release; inconsistent zeros and invalid values fail validation.

Typological polygons provide score support. Rasterizing them does not create a restoration footprint. Pixel-level opportunity intersection requires a separately verified eligible-loss footprint and spatial adapter. No beneficiary-buffer distance, geometry-area proration or score-weighted hectares is introduced. Hydrological and local feasibility follow-up remains downstream.

## Provenance and remaining review

The candidate records link the source edition, passage/code/table locator, mechanism and transfer rationale. Bibliographic references in these records are not fabricated Evidence Register units and cannot substitute for reviewed claims in an accepted T4 proposal.

Climate source admission and exact convention review are documented in [method proposal #129](https://github.com/RuralScan/method/pull/129), [six-source admission #116](https://github.com/RuralScan/evidence/pull/116), and [Berdugo follow-up #117](https://github.com/RuralScan/evidence/pull/117). The separate [source-identity repair #118](https://github.com/RuralScan/evidence/pull/118) preserves acquisition verification in frozen T4 input packets; it does not approve numerical relationships.

Before any live activation: review the scientific convention and family transfer; adopt the exact variable/dataset/binding definitions; complete appropriate source/claim admission, including the bounded mangrove dataset intake; fingerprint actual replaced mappings; obtain the existing authenticated human acceptance receipt for exact per-family proposal bytes; then integrate and verify the runtime consumer. Generic climate classes must not be misrepresented as measured agroforestry success thresholds. The mangrove sea-level scenario/horizon and pilot footprint remain explicit limitations.

## Dashboard and methods integration

The same record should support a short summary and an expandable technical view:

1. Show why an override is needed, what it includes/replaces, scope and lifecycle status.
2. Separate what the source reports from the mechanism interpretation and analyst choices (anchors, smooth interpolation, transfer, operators and screens).
3. Link source editions and exact locators; distinguish source admission from evidence Keep and relationship approval.
4. Show the continuous curve and separate exclusion/conditional states, with missing-data behavior and units.
5. Show dataset release, native support, period and binding limitations, plus the distinct area-accounting policy.
6. Preserve the prior mapping, exact replacement fingerprints, dependencies, review reasons and supersession history.

The consumer must not present “implemented” as “scientifically accepted” or “active in maps”. The pending candidate files are review inputs; the accepted-output stream remains the source of executable production mappings.


## Reproduce the review

```sh
python workflows/t4_synthesis/override_candidates.py --check
python workflows/t4_synthesis/profiles_cli.py validate suitability/overrides/candidates
python workflows/t4_synthesis/profiles_cli.py evaluate \
  suitability/overrides/candidates/agroforestry__regeneration_farmland__climate_override_v1.json \
  --inputs suitability/overrides/examples/fmnr-dan-saga.json
python workflows/t4_synthesis/profiles_cli.py evaluate \
  suitability/overrides/candidates/mangrove_restoration__tidal_coastal__archive_override_v1.json \
  --inputs suitability/overrides/examples/mangrove-partial-unit.json
python -m unittest discover -s workflows/t4_synthesis
```

Use the Python 3.12 workflow environment for the full suite. The standalone profile and candidate tools use the standard library. After editing the CSV, run the generator without `--check`, inspect the typed diff, then repeat validation. `profiles_cli.py validate ... --committed` checks exact committed candidate bytes; it still does not approve the science.

The FMNR example reproduces the selected Dan Saga climate reference: membership about 0.704. Its host/legal context remains unresolved in this illustrative climate check, so no site or area eligibility is asserted. The mangrove example is **synthetic arithmetic**, not a real mapped unit: score 0.6 remains 0.6; partial coverage of a unit with 100 source estimated hectares gives no point estimate and bounds 0–100 hectares. It does not yield 60 hectares.

Validation reproduces all six prior climate reference calculations to numerical precision and checks activation guards, dry-tail and equality behavior, retained-parkland scope, known exclusions with missing data, water/cold precedence, native score/area separation and duplicate-unit rejection. A separate cached-archive check reconciles 3,983 mangrove units: 3,635 positive scores preserved, 348 zero-area units excluded, and 793,912.889 source estimated hectares. That attribute-only check assumes geometry and independent gates valid; it does not validate the spatial adapter.
