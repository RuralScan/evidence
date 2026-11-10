# Riparian buffer

[All practices](README.md)

Candidate release `2ff6f85ed5493b25a8b2279c572d792cc23ed5251fa99463f1421a4380730f2b` · [source revision](https://github.com/CIAT/nbs_ruralscan/tree/e5c8da02e72810956cfd179cb32cd137fc4ba398).

Jump to [T3 hazard responses](#t3-hazard-responses) · [T4 suitability mappings](#t4-suitability-mappings) · [T6 scorecard effects](#t6-scorecard-effects) · [T6E economic profiles](#t6e-economic-profiles).

## T3 Hazard responses

For livelihood rows, the rating describes mitigation potential. For investment-risk rows, it describes the asset’s sensitivity to the hazard.

| Hazard | Risk role | Farming system | Scope | Potential or sensitivity | Confidence |
|---|---|---|---|---|---|
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L3 "riparian_buffer__flood__all") | Livelihood risk mitigation | All | Practice | Low | Medium |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L108 "riparian_buffer__natural_restored__flood__all") | Livelihood risk mitigation | All | Natural restored | Low | Medium |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L206 "riparian_buffer__planted__flood__all") | Livelihood risk mitigation | All | Planted | Unspecified | Very low |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L295 "riparian_buffer__natural_restored__flood__cropping_rainfed") | Livelihood risk mitigation | Cropping rainfed | Natural restored | Low | Medium |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L393 "riparian_buffer__asset_threat__flood") | Threat to the investment | All | Practice | Low | Medium |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L483 "riparian_buffer__natural_restored__asset_threat__flood") | Threat to the investment | All | Natural restored | Unspecified | Very low |
| [Flood](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T3_nbs_hazard_farming.json#L568 "riparian_buffer__planted__asset_threat__flood") | Threat to the investment | All | Planted | Low | Very low |

## T4 Suitability mappings

A selected function still needs checks against the intended spatial inputs and location.

| Variable | Family | Function role | Reviewed numerical calibration | Function options | Function selected | Spatially validated |
|---|---|---|---|---|---|---|
| [Distance to waterbody](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T4_suitability_mappings.json#L3 "riparian_buffer__natural_restored__distance_to_waterbody") | Natural restored | Suitability score | Held | 0 | No | No |
| [Distance to waterbody](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T4_suitability_mappings.json#L111 "riparian_buffer__planted__distance_to_waterbody") | Planted | Suitability score | Held | 0 | No | No |

## T6 Scorecard effects

Use the linked record for the evidence, applicability and caveats behind each effect.

| Indicator | Scope | Effect direction | Confidence |
|---|---|---|---|
| [Biodiversity priority](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L3 "riparian_buffer__biodiversity_priority") | Practice | Slight positive | Very high |
| [Biodiversity priority](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L174 "riparian_buffer__biodiversity_priority__income_group-upper_middle") | Practice / Income group · Upper middle | Slight positive | Medium |
| [Biodiversity priority](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L289 "riparian_buffer__natural_restored__biodiversity_priority") | Natural restored | Slight positive | Very high |
| [Biodiversity priority](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L416 "riparian_buffer__planted__biodiversity_priority") | Planted | Slight positive | Low |
| [Carbon sequestration potential](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L531 "riparian_buffer__carbon_sequestration_potential") | Practice | Slight positive | High |
| [Carbon sequestration potential](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L627 "riparian_buffer__natural_restored__carbon_sequestration_potential") | Natural restored | Unspecified | Very low |
| [Carbon sequestration potential](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L709 "riparian_buffer__planted__carbon_sequestration_potential") | Planted | Slight positive | Medium |
| [Flood hazard](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L798 "riparian_buffer__flood_hazard") | Practice | Slight positive | Medium |
| [Flood hazard](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L889 "riparian_buffer__natural_restored__flood_hazard") | Natural restored | Slight positive | Medium |
| [Flood hazard](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L974 "riparian_buffer__planted__flood_hazard") | Planted | Unspecified | Very low |
| [Heat stress hazard](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1060 "riparian_buffer__natural_restored__heat_stress_hazard") | Natural restored | Slight positive | Very low |
| [Production gap](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1150 "riparian_buffer__production_gap") | Practice | Unspecified | Very low |
| [Soil erosion risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1231 "riparian_buffer__soil_erosion_risk") | Practice | Moderate positive | Very high |
| [Soil erosion risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1441 "riparian_buffer__soil_erosion_risk__income_group-upper_middle") | Practice / Income group · Upper middle | Moderate positive | High |
| [Soil erosion risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1548 "riparian_buffer__soil_erosion_risk__farming_system-cropping_rainfed") | Practice / Farming system · Cropping rainfed | Moderate positive | Very high |
| [Soil erosion risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1690 "riparian_buffer__natural_restored__soil_erosion_risk") | Natural restored | Moderate positive | Very high |
| [Soil erosion risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1828 "riparian_buffer__planted__soil_erosion_risk") | Planted | Moderate positive | Very high |
| [Water quality risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L1984 "riparian_buffer__water_quality_risk") | Practice | Strong positive | Very high |
| [Water quality risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L2341 "riparian_buffer__water_quality_risk__income_group-upper_middle") | Practice / Income group · Upper middle | Strong positive | High |
| [Water quality risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L2486 "riparian_buffer__water_quality_risk__farming_system-cropping_rainfed") | Practice / Farming system · Cropping rainfed | Strong positive | Very high |
| [Water quality risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L2688 "riparian_buffer__natural_restored__water_quality_risk") | Natural restored | Strong positive | Very high |
| [Water quality risk](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6_nbs_scorecard.json#L2904 "riparian_buffer__planted__water_quality_risk") | Planted | Strong positive | Very high |

## T6E Economic profiles

Where a numerical range is reported, consult the linked record for its values, units and source conditions.

| Indicator | Scope | Numerical range reported | Confidence |
|---|---|---|---|
| [Cost per hectare restored](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6E_economic_profile.json#L3 "riparian_buffer__cost_per_hectare_restored") | Practice | No | Very low |
| [Cost reduction](https://github.com/CIAT/nbs_ruralscan/blob/e5c8da02e72810956cfd179cb32cd137fc4ba398/schema/recipes/riparian_buffer/T6E_economic_profile.json#L97 "riparian_buffer__cost_reduction") | Practice | No | Very low |
