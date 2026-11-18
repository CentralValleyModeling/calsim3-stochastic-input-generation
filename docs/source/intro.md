# Introduction

California's water system planning depends on CalSim 3, a large-scale operations model that simulates reservoir operations, water deliveries, and regulatory compliance across the Central Valley and State Water Project. Historically, CalSim has been driven by a single observed hydrologic record of about 100 years. That record is too short to capture the full range of droughts, wet periods, and transitions the system may face.

This project removes that limitation. Coupling a stochastic Weather Generator (WGEN) to the full CalSim 3 input framework produces 1,000 years of synthetic hydroclimate inputs. These inputs preserve the spatial and temporal structure of the observed climate while covering conditions well beyond the historical record.

## What this project produces

The generation pipeline covers 1,733 CalSim input variables organized into 15 categories, spanning rim inflows, Sacramento Valley hydrology, reservoir evaporation, Delta channel depletion, and operational forecast terms. Of these, 1,465 require active stochastic generation; the remaining 268 are held constant, repeat historical patterns, or are unused in the DCR 2023 baseline. The pipeline delivers three input sets:

- Historical_Unsplit (WY 1922--2018) comes from the historical weather record without the temperature detrending. It is the set we validate against the CalSim 3 baseline.
- Product A (WY 1922--2018) comes from the same record with its temperature detrended.
- Product B (1,000 years) is ten 100-year stochastic sequences (`_n01`--`_n10`) for planning analysis, the project's primary deliverable.

## How it works

The WGEN ("Weather Generator" ([Report](https://water.ca.gov/-/media/DWR-Website/Web-Pages/Programs/All-Programs/Climate-Change-Program/Resources-for-Water-Managers/Files/WGENCalifornia_Final_Report_final_20230808.pdf)/[Data](https://data.ca.gov/dataset/gridded-weather-generator-perturbations-of-historical-detrended-and-stochastically-generated-te))) produces daily temperature and precipitation fields across the Sacramento--San Joaquin basin. The weather of each set then drives a chain of processing steps:

1. The SAC-SMA rainfall-runoff model turns the daily weather into monthly flow on the 196 CalSim 3 rim-inflow arcs, which become the rim inflows without bias correction.
2. Precipitation from the same weather drives the valley-floor models (CalSimHydro, CalSimHydroEE, Small Watersheds and Delta Channel Depletion); CalSimHydro and CalSimHydroEE also take reference ET computed from its temperature.
3. Reservoir evaporation, water year type indices, instream flow requirements, and dozens of other operational inputs are reconstructed using a mix of quantile mapping, water-year-type averaging, hybrid methods, and direct physical calculation.
4. All variables are merged into DSS files matching CalSim's native format, ready for model execution.

The choice of reconstruction method for each variable depends on its correlation with available predictors. Terms well correlated with a rim inflow use empirical quantile mapping. Weakly correlated terms (Tulare groundwater) use water year type monthly averages. A hybrid approach averaging QM and WYT results handles intermediate cases where pure QM overshoots peaks.

## How this documentation is organized

- {doc}`Methods </source/methods>` describes the WGEN algorithm, the input generation framework, and reconstruction techniques in detail.
- {doc}`Input Generation </source/input-generation/overview>` documents each of the 15 variable categories with methodology specifics, validation results, and known limitations.
- {doc}`Results / Product A </source/results_product_a>` reports the v1.0 input-level and CalSim-run validation of Product A against the CalSim baseline.
- {doc}`Results / Product B </source/results_product_b>` reports the v1.0 distributional comparison and CalSim-run behavior of the 1,000-year stochastic ensemble.
- {doc}`CalSim Runs </source/calsim-run/overview>` covers the run framework and stochastic-sequence diagnostics, including solver infeasibilities.
- {doc}`Wrap-up </source/summary>` presents technical observations, cross-category dependencies, and recommendations for Phase II.
- {doc}`Changelog </source/changelog>` lists what each version changes.

## Development environment

The [codebase](https://github.com/CentralValleyModeling/calsim3-stochastic-input-generation) is organized into module directories (`mod_forcing/`, `mod_hydrology/`, `mod_reservoir/`, `mod_other/`) that mirror the input generation pipeline, with shared utilities for quantile mapping, flow aggregation, and path resolution. Input data and generated outputs are managed under a configurable `data/` directory with read-only source data (`BASE/`) separated from script outputs (`GENERATED/`).
