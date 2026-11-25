# Dataset binding inspection — 25 November 2026

Ten technical observations support the first drought, water, carbon and IPLC binding candidates in RuralScan/method. They record actual service responses and small diagnostic samples. They do not approve thresholds, establish pilot fitness, register datasets as scientific evidence, change human votes or release runtime inputs. The diagnostic locations are not selected pilots.

| Observation | Result | Remaining limit |
|---|---|---|
| Aqueduct 4 annual/monthly | Live Earth Engine tables; 68,506/16,395 features; native categories and raw fields checked | Annual rows intersect basins/admin units/aquifers. Raw ratios reach 30.14, conflicting with the technical note's clipping wording. Preserve native categories; resolve before numeric calibration. |
| FAO DI annual | Official ImageServer; 168 year/season/land-type combinations; raw pixels and 24×24 TIFF checked | Float32 0–1 values, with special codes before ×100 conversion. GAUL2 analytical support persists despite the raster grid. |
| FAO ASI annual | Same explicit dimensions; unsigned-byte percentages and real zero checked | Severity, affected extent and recurrence are different quantities. No accepted frequency/severity reducer. |
| FAO HDF | Eight season/land-type/affected-area records | Access page, item period and formula denominator disagree (2025/2024/2023). No raw-pixel or denominator verification. |
| FAO Earth Engine | Four documented new assets attempted using existing credentials | Not-found/no-permission responses remain ambiguous. Official ArcGIS serves as the checked fallback. No access request sent. |
| SPEI 2.11 | 1,488 monthly images; 48 accumulation bands; 0.5° native grid | Observed values outside ±2.33 are valid extremes, not display-limit errors. Meteorological anomalies do not define livelihood loss. |
| Hansen forest loss | 2025 v1.13 asset; positive loss and zero-event samples checked | `lossyear` is masked at no-event locations; valid-land mask plus `loss` needed. Tree-cover loss is not carbon mass. |
| Forest emissions | Community-hosted model v1.4.2, 2001–2024, sampled | Mg CO2e/ha over the whole period, not per year. Definitive upstream rasters/version still need pinning; 2025 Hansen cannot supply matching event timing. |
| LandMark | Official current access page inspected | June 2026 community layer, CC BY-SA 4.0; download form and terms not submitted. No vector schema/coverage verification. IPLC stays unscored. |
| Naturebase avoided forest conversion | ZIP directory, README and one TIFF member inspected | Modelled potential, not observed loss; 2017–2021 mean annual rate. Actual EPSG:4326 header resolves conflicting README CRS text. Ocean sample is zero: applicability cannot be inferred from nonmissing/zero pixels. Other 19 pathways not raster-checked. |

## Provenance and replay

`manifest.json` pins each observation by SHA-256. Each observation identifies raw response hashes and requests; `library-receipt.json` records the raw metadata/web snapshot and two raster samples copied to the existing team-library mirror. Local read-back hashes match. Remote SharePoint/team access has **not** been verified. These files are technical diagnostics, not canonical source/acquisition registrations. The dataset-intake pause is not bypassed.

`python3 workflows/priority_classification/binding_checks.py` verifies the packet offline. Add `--raw-root /path/to/library/bindings_2026_11_25` to verify all referenced original responses. SHA-256 establishes byte identity, not scientific authenticity or approval.

Replay scripts accept a separate output directory as their sole argument. They preserve the original bounded read-only inspection queries. Earth Engine scripts require the `earthengine-api` package and already-authorized credentials; they do not initiate authentication. HTTP probes use Python's standard library. Run `probe_initial.py`, `probe_water.py`, `probe_rasters.py`, then `probe_followup.py` for Earth Engine; `probe_fao_samples.py` for FAO raw point checks; `probe_zip.py` for bounded Naturebase ZIP metadata inspection. A replay against mutable services may differ; keep a new dated packet rather than overwriting this one. Query responses are diagnostics, not approved runtime adapters. The larger SPEI follow-up retains the native grid and raises only the pixel-count ceiling after the first diagnostic limit was exceeded.

Exact FAO TIFF request is in `fao_di_live.json`; the Naturebase TIFF member name/hash/header are in `naturebase_afc_inspection.json`. No credentials, raster export signed URL or private user details are required in the committed records. The multipart S3 ETag is not treated as a content SHA-256.

## Source documentation

- [Aqueduct annual](https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Water_Risk_V4_baseline_annual), [monthly](https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Water_Risk_V4_baseline_monthly), [WRI technical note](https://www.wri.org/research/aqueduct-40-updated-decision-relevant-global-water-risk-indicators). Baseline uses 2019 target values from smoothed historical trends; annual stress is demand-weighted across monthly ratios. See existing acquired WRI packet, pp. 8 and 11.
- [FAO access and frequency definitions](https://www.fao.org/giews/earthobservation/access.jsp), [2026 Earth Engine asset adjustment](https://www.fao.org/giews/earthobservation/asis/data/ref/ASIS_GEE_AdjustmentNote_2026.pdf), [DI service](https://asis-esri.fao.org/image/rest/services/DI_A/ImageServer), [ASI service](https://asis-esri.fao.org/image/rest/services/ASI_A/ImageServer), [HDF item](https://www.arcgis.com/sharing/rest/content/items/71a7a03a60e44734adf8c2bab91600f5?f=pjson). DI's current service legend uses “≥42 None”; earlier static legend says “>42”. Equality needs producer-algorithm resolution.
- [SPEI 2.11](https://developers.google.com/earth-engine/datasets/catalog/CSIC_SPEI_2_11), [Hansen 2025 v1.13](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2025_v1_13).
- [Forest-carbon primary paper](https://essd.copernicus.org/articles/17/1217/2025/), [definitive GFW rasters](https://data.globalforestwatch.org/datasets/forest-greenhouse-gas-emissions), [community asset hosting](https://gee-community-catalog.org/projects/cflux/).
- [LandMark access](https://www.landmarkmap.org/data-methods/access-data), section “Indigenous Peoples’ and Local Community Lands and Territories”; [Naturebase catalogue](https://app.naturebase.org/data), Avoided Forest Conversion download and archive README. Naturebase license is CC BY-NC-SA 4.0.
