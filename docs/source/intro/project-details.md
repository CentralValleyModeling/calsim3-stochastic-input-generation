# Project Details

## Project Context

This effort represents Phase I of a two-phase initiative to build a production-level stochastic capability into DWR's core water planning model. The overarching goal is to have this capability ready for the DCR 2027 planning cycle, providing California's water managers with tools to evaluate system performance across hydrologic conditions far more diverse than the approximately 100-year observed record. Phase I focuses on generating and validating the complete set of input time series; Phase II, to be scoped based on Phase I findings, will address operational rule modifications needed for extreme synthetic sequences and any infeasibilities discovered during model testing.


## Project Team

The project team comprises staff from the Division of Planning with technical coordination with the Modeling Support Office (MSO).

### Core Team

| Name | Role |
|------|------|
| Wyatt Arnold | Project Lead 1 |
| Karandev Singh | Project Lead 2 |
| Melika Mani | Technical Staff |
| Mehrdad Bastani | Technical Staff |

The MSO provided essential technical consultation throughout the project. Mohammad Hasan and Richard Chen served as primary MSO liaisons, supplying domain expertise on CalSim 3 internals, model configuration, and historical calibration decisions that informed methodology choices. Andrew Schwarz provided project sponsorship and direction, ensuring alignment with broader Division of Planning priorities.

## Development Environment and Practices

The codebase is organized as a standalone Python repository (`calsim3-stochastic-input-generation`) using a conda environment (`csstochastic`, Python 3.11). Scripts follow a numbered prefix naming convention (e.g., `_1_compile_precip.py`, `_2_postprocess_run.py`) indicating processing order within each module directory.

### Repository Structure

The repository is organized into four top-level module groups that mirror the input generation pipeline:

```
calsim3-stochastic-input-generation/
├── mod_forcing/              # Climate forcing & VIC model
│   ├── vic/                  #   VIC hydrologic model (wind append, run, compile)
│   └── climate/              #   Climate extractions (point locations, basin averages)
├── mod_hydrology/            # Core hydrologic processing
│   ├── calsimhydro/          #   Sacramento Valley water budget (746 variables)
│   ├── calsimhydro_ee/       #   External Elements boundary conditions
│   ├── rim_inflow/           #   Rim inflow quantile mapping from VIC
│   ├── small_watersheds/     #   Small tributary groundwater recharge
│   ├── delta_channel_depletion/  # Delta ag demands (DCD/DETAW)
│   ├── water_year_types/     #   Sac/SJ water year type classification
│   ├── closure_terms/        #   Water balance closure adjustments
│   └── tulare_gw/            #   Tulare Basin groundwater terms
├── mod_reservoir/            # Reservoir-specific terms
│   ├── evaporation/          #   Hargreaves-Samani for 95 reservoirs
│   └── storage_curves/       #   Storage reconstruction (Oroville, Mammoth)
├── mod_other/                # Ancillary & operational terms
│   ├── day_volume_fractions/ #   Monthly-to-daily disaggregation
│   ├── instream_flows/       #   Minimum flow requirements
│   ├── upper_watershed/      #   Upper watershed modules (Yuba, Don Pedro)
│   └── miscellaneous/        #   B120 forecasts, WYT indexes, NDOI, etc.
├── postprocessing/           # Final compilation & validation
│   ├── sv_compile/           #   Merge all outputs → DSS
│   └── product_a_validation/ #   Product A vs. historical CalSim comparison
├── utils/                    # Shared Python utilities
│   ├── quantile_mapping.py   #   qmap_single() — empirical CDF interpolation
│   ├── flow_indices.py       #   flowAggregator() — seasonal flow aggregations
│   ├── wyt_monthlyavg_framework.py  # WYT×monthly-average reconstruction
│   ├── dss_pickle_builder.py #   DSS cache builder for validation
│   └── paths.py              #   Configuration-based path resolution
├── inventory/                # Master SV inventory & reference data
├── docs/                     # Sphinx documentation (this site)
├── data/                     # Input (BASE/) and output (GENERATED/) — gitignored
├── environment.yml           # Conda environment specification
└── config_default.json       # Data directory configuration template
```

### Data Management

Input data and generated outputs are stored under a configurable `data/` directory (gitignored). The directory has two tiers:

- **`data/BASE/`** — Read-only source data downloaded from Box (WGEN products, historical climate, CalSim 3 baseline DSS)
- **`data/GENERATED/`** — Script outputs, mirroring the module structure (`mod_forcing/`, `mod_hydrology/`, etc.)

Path resolution uses `utils/paths.py` with a `config.json` file (copied from `config_default.json`) to support portable deployment across machines.

### Shared Utilities

A shared `utils/` directory houses reusable Python modules for quantile mapping, flow index aggregation, WYT×monthly-average reconstruction, and DSS file handling. The master inventory spreadsheet (`inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`) tracks variable status across all 15 input categories, providing a single source of truth for completion monitoring.

## Key Milestones

| Milestone | Date |
|-----------|-------------|
| Project Commencement | July 2025 |
| Progress Meeting 1 (Internal) | July 23, 2025 |
| Progress Meeting 2 (with MSO) | August 27, 2025 |
| Progress Meeting 3 (with MSO) | January 8, 2026 |
| Input Generation Complete | February 2026 |
| 46-Year Validation Run (Product A) | February–March 2026 |
| Progress Meeting 4 (with MSO) | March 12, 2026 |
| 1000-Year Stochastic Runs (Product B) | March–April 2026 |
| Progress Meeting 5 (with MSO) | April 23, 2026 |
| Final Documentation | April 2026 |


