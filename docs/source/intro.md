# Introduction

California's water system planning depends on CalSim 3, a large-scale operations model that simulates reservoir operations, water deliveries, and regulatory compliance across the Central Valley and State Water Project. Historically, CalSim has been driven by a single approximately 100-year observed hydrologic record -- a record too short to capture the full range of plausible droughts, wet sequences, and transitional periods that the system may face.

This project removes that limitation. By coupling a stochastic Weather Generator (WGEN) with the full CalSim 3 input framework, we produce 1,000 years of statistically plausible synthetic hydroclimate inputs that preserve the spatial and temporal structure of observed climate while exploring conditions well beyond the historical envelope.

## What This Project Produces

The generation pipeline covers **1,733 CalSim input variables** organized into 15 categories -- from rim inflows and Sacramento Valley hydrology to reservoir evaporation, Delta channel depletion, and operational forecast terms. Two products are generated:

- **Product A** (1972--2018): A historical-based sequence used for validation against the historical CalSim baseline.
- **Product B** (1,000 years): Ten 100-year stochastic sequences for planning analysis.

## How It Works

The WGEN ("Weather Generator" ([Report](https://water.ca.gov/-/media/DWR-Website/Web-Pages/Programs/All-Programs/Climate-Change-Program/Resources-for-Water-Managers/Files/WGENCalifornia_Final_Report_final_20230808.pdf)/[Data](https://data.ca.gov/dataset/gridded-weather-generator-perturbations-of-historical-detrended-and-stochastically-generated-te))) produces daily temperature and precipitation fields across the Sacramento--San Joaquin basin. These synthetic weather sequences then drive a chain of processing steps:

1. **Climate forcing** -- Synthetic weather is combined with wind fields and fed through the VIC hydrologic model to produce gridded runoff and baseflow.
2. **Hydrologic translation** -- VIC outputs are quantile-mapped, spatially aggregated, and bias-corrected to CalSim's historical baseline.
3. **Ancillary terms** -- Reservoir evaporation, water year type indices, instream flow requirements, and dozens of other operational inputs are reconstructed using a mix of quantile mapping, water-year-type averaging, hybrid methods, and direct physical modeling calculation.
4. **Compilation** -- All variables are merged into DSS files matching CalSim's native format, ready for model execution.

The choice of reconstruction method for each variable depends on its correlation with available predictors. Well-correlated terms (rim inflows, ET) use empirical quantile mapping. Weakly correlated terms (Tulare groundwater) use water year type monthly averages. A hybrid approach averaging QM and WYT results handles intermediate cases where pure QM overshoots peaks.

## How This Documentation Is Organized

- {doc}`Methods </source/methods>` describes the WGEN algorithm, the input generation framework, and reconstruction techniques in detail.
- {doc}`Input Generation </source/input-generation/overview>` documents each of the 15 variable categories with methodology specifics, validation results, and known limitations.
- {doc}`CalSim Runs </source/calsim-run/overview>` covers the Product A validation run and Product B stochastic execution, including diagnostics.
- {doc}`Wrap-up </source/summary>` presents technical observations, cross-category dependencies, and recommendations for Phase II.

## Development Environment

The [codebase](https://github.com/CentralValleyModeling/calsim3-stochastic-input-generation) is organized into module directories (`mod_forcing/`, `mod_hydrology/`, `mod_reservoir/`, `mod_other/`) that mirror the input generation pipeline, with shared utilities for quantile mapping, flow aggregation, and path resolution. Input data and generated outputs are managed under a configurable `data/` directory with read-only source data (`BASE/`) separated from script outputs (`GENERATED/`).
