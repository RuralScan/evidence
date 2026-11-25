# Source-finding review cards

Prepared for inspection only. No review receipt submitted or decision recorded. Register selected objects and obtain their merged revision before a human submits an issue receipt. A source keep verifies the observation; it does not accept RuralScan class cutoffs.

## WRI Aqueduct Baseline Annual Version 4.0
[Original source](https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Water_Risk_V4_baseline_annual)

Proposed source: `psrc_10b696b6b25533d3fc9d9c10b04d64adf8bfce87fa368318293db3f9bc1d3ee8`. Artifact SHA-256: `226be8c474a4ca0eeb560d14ed65dff7db806d68f6f34b1420240df953f76797`.

Proposed finding: `pfind_8d50b63941822906f060891f6b2a06c92db813c1fbef43f709fcadb332009cbd`.

Locator: Earth Engine Snippet; Table Schema rows string_id, pfaf_id, bws_raw, bws_cat, bws_score

Source-reported content:

```json
{
  "asset": "WRI/Aqueduct_Water_Risk/V4/baseline_annual",
  "raw_field": "bws_raw",
  "status_field": "bws_cat",
  "type": "FeatureCollection"
}
```

Interpretation limit: The hosted annual collection exposes raw stress, provider categories and scores separately. Polygon geometry combines basins, provinces and aquifers; intersections do not imply finer stress information.

T5 candidate observations retained separately: `xce_aqueduct_catalogue_fields`. No equivalence or vote transfer asserted.

## Standardized Precipitation-Evapotranspiration Index (SPEI)
[Original source](https://drought.emergency.copernicus.eu/data/factsheets/factsheet_spei.pdf)

Proposed source: `psrc_923f257d39917903ce6aa6a29b67753b9b63329ea4f118d0f0f1eb18968f3a2c`. Artifact SHA-256: `a65d8e7fb2727e1b66ec97517760d7a3eb49ca6552831ca1108fb7e66fad3086`.

Proposed finding: `pfind_e7ff2463fac6d46baaf9b91f5d69f25be3546c670357b2d624b74f089decf55a`.

Locator: PDF/printed page 6, section 4, Table 2; pages 2–4 for accumulation and fitting

Source-reported content:

```json
{
  "dry_classes": [
    {
      "label": "moderately dry",
      "lower_exclusive": -1.5,
      "upper_inclusive": -1.0
    },
    {
      "label": "very dry",
      "lower_exclusive": -2.0,
      "upper_inclusive": -1.5
    },
    {
      "label": "extremely dry",
      "lower_exclusive": null,
      "upper_inclusive": -2.0
    }
  ],
  "unit": "unitless"
}
```

Interpretation limit: SPEI dry-event classes have upper-inclusive boundaries. The table caption says SPI, but its entries and surrounding section explicitly describe SPEI. This defines event severity, not thresholds for long-term drought frequency. Copernicus and CSIC datasets use different derivations; transfer requires review.

T5 candidate observations retained separately: `xce_spei_dry_event_classes`, `xce_spei_standardization`. No equivalence or vote transfer asserted.

## Chapter 2 | Soil Organic Carbon (SOC) sequestration | Technical Manual Global Soil Organic Carbon Sequestration Potential Map GSOCseq
[Original source](https://fao-sid.github.io/GSOCseq/soil-organic-carbon-soc-sequestration.html)

Proposed source: `psrc_e2ae93f1c7327cab7876ac1c72e17148a107474703e93090b9db75161cf3c084`. Artifact SHA-256: `64f02aae75aee5e327c2d739944b868bfe9d96d03d7929d4985a0d21f57b6e39`.

Proposed finding: `pfind_ba42e1baa3c027d2c93ee52f9ec658fdc8e2a4bd15096e9aee13f2c09fda6d15`.

Locator: 2.4 Estimating SOC sequestration potential; equations 2.1 and 2.2

Source-reported content:

```json
{
  "comparators": [
    "initial stock",
    "business as usual at common horizon"
  ],
  "rate_unit": "t C/ha/year",
  "stock_unit": "t C/ha"
}
```

Interpretation limit: Sequestration is stock change over time or relative to a management counterfactual. An annual rate divides change by the stated horizon. A stock map alone does not measure additional sequestration potential.

T5 candidate observations retained separately: `xce_soc_change_comparators`. No equivalence or vote transfer asserted.

## Data sets and inputs
[Original source](https://fao-sid.github.io/GSOCseq/data-sets-and-inputs.html)

Proposed source: `psrc_774ccb1ced4b76405e3275e1976d9072c0220d9f838f2454a9bed9bf3f8b6a9b`. Artifact SHA-256: `75fe431797cd7fdf908fcd7507bd73332b7ff07fdaae7912ee5b743d8aba0206`.

Source-only preparation. No packet finding; review the separate T5 input-documentation observation through its own reviewed route.

T5 candidate observations retained separately: `xce_soc_stock_input_support`. No equivalence or vote transfer asserted.

## Data completeness
[Original source](https://www.landmarkmap.org/data-methods/data-completeness)

Proposed source: `psrc_59f0c1d79cedf666ccff135cea4ac8022ac75f0aaecd9165ba33d7e3253c7b30`. Artifact SHA-256: `55dad9e0ea9a51452fffe21310b0bd48312b38ee86b210fb349618f5472777ee`.

Proposed finding: `pfind_55d0a50795093f6a057903f0d4f15509552e65e32a4d7c67877daaec0f14a3be`.

Locator: Accounting for the map gap on LandMark

Source-reported content:

```json
{
  "coverage": "incomplete",
  "unmapped_means": "unknown_presence"
}
```

Interpretation limit: Unmapped areas do not establish absence of Indigenous or community lands. Mapped presence is not a numerical severity gradient.

T5 candidate observations retained separately: `xce_landmark_missingness`. No equivalence or vote transfer asserted.

## Aqueduct 4.0: Updated Decision-Relevant Global Water Risk Indicators
[Original source](https://files.wri.org/d8/s3fs-public/2023-08/aqueduct-40-technical-note.pdf)

Proposed source: `psrc_2798ca451ec4f03c51d8f1278bffc90fe1d3e5654d1b025d9cf3c2f4a89e3122`. Artifact SHA-256: `bb55ea20f39c4272dea87b1089725900ffbf45673709c18cb0dab8d361a97ae5`.

Proposed finding: `pfind_1ae9de2e644e68a23f49f38cb5fc2042ad364d059395411313481ea28352cc7c`.

Locator: PDF/printed page 11, Baseline water stress; page 12, Limitations

Source-reported content:

```json
{
  "input_period": "1979–2019",
  "source_band_boundaries": [
    0.1,
    0.2,
    0.4,
    0.8
  ],
  "source_class_count": 5,
  "special_status": "arid and low water use",
  "support": "HydroBASINS 6",
  "unit": "fraction"
}
```

Interpretation limit: Baseline water stress compares total demand with renewable supply. Annual values weight monthly stress by demand. Five risk bands and a separate arid status are reported. The range table does not settle every exact endpoint. Formula printing conflicts with the prose clipping description; use verified provider outputs, not that printed expression.

T5 candidate observations retained separately: `xce_aqueduct_quantity_support`, `xce_aqueduct_provider_bands`. No equivalence or vote transfer asserted.

## Storage decision draft

The current method decision `priority_catalogue_release` remains open. If Pete accepts the storage/release contract after review, its exact ruling is:

> Accept priority catalogue sidecar storage and release contract v1.

This text is a draft for explicit human acceptance. It is not a decision event. Source findings, binding verification and classification/context acceptance remain separate.
