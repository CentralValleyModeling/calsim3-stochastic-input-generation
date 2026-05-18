# CalSim Stochastic Input Generation

Generation of synthetic hydroclimate inputs for **CalSim 3.0** to support long-term stochastic water supply planning studies.

---
## Setup

### 1. Conda environment

> **Windows prerequisite**: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the **C++ workload** is required to compile `pydsstools`.

```bash
conda env create -f environment.yml
conda activate csstochastic
```

---

### 2. Repository Structure

```
root/
├── mod_forcing/              
│   ├── vic/                  Append wind to WGEN, compile rim inflows from VIC fluxes
│   └── climate/              Point precip, basin-avg climate (T, PPT, VPD)
│
├── mod_hydrology/            
│   ├── calsimhydro/          Sac Valley: compile precip/ET, postprocess Product A & B
│   ├── calsimhydro_ee/       External Elements: compile precip, postprocess
│   ├── rim_inflow/           Quantile-map VIC inflows, correlation analysis, NSE metrics
│   ├── water_year_types/     Sac 40-30-30, SJ 60-20-20 WYT classification
│   ├── delta_channel_depletion/  DETAW/DCD Delta
│   ├── small_watersheds/     SWS precipitation compilation and postprocessing
│   └── tulare_gw_terms/      Tulare GW terms: WYT monthly average reconstruction
│
├── mod_reservoir/            
│   ├── evaporation/          Hargreaves-Samani for 95 reservoirs
│   └── storage_curves/       WYT index-based curves, Mammoth Pool QM, Oroville Level 5
│
├── mod_other/                
│   ├── closure_terms/        Closure term calculation
│   ├── day_volume_fractions/ Day-volume fraction analysis and Product B generation
│   ├── instream_flows/       Feather River minimum instream flow, SJR restoration
│   ├── miscellaneous/        Misc SVs (extract baseline, NDOI accretion, WYT/hybrid/QM)
│   └── upper_watershed/      Lower Yuba, Don Pedro: WYT/QM/hybrid reconstruction
│
├── postprocessing/           
│   └── sv_compile/           Merge all module outputs -> DSS (Product A & B)
│
├── utils/                    Shared utilities (quantile mapping, flow indices, WYT framework)
├── inventory/                Master CalSim SV inventory spreadsheet
├── docs/                     Sphinx documentation
├── config_default.json       Default config (data_dir = ./data)
└── environment.yml           Conda environment spec
```

---

### 3. Data

Large files (WGEN, VIC, DSS) are on Box: https://cadwr.app.box.com/s/8dqqrbw86cutpbihpuktgmx8nni9vcv7

By default scripts expect data under `data/` at the repo root, split into `BASE/` (read-only inputs) and `GENERATED/` (script outputs). To use a different location, copy `config_default.json` → `config.json` and set `data_dir`.


#### Expected data directory layout

```
data/                            (or wherever data_dir points)
├── BASE/                        Read-only source data (download from Box)
│   ├── WGEN/
│   │   ├── Product_A/1           meteo_LAT_LON files, 1915–2018  (~14 GB)
│   │   └── Product_B/1           10 chunk subdirs n01–n10, 1000 yr  (~120 GB)
│   ├── Historical_Climate/
│   │   └── 1_Historical/        Observed climate with wind column  (~1 GB)
│   └── CalSim3/
│       └── __calsim_sv_default__.dss   CalSim3 baseline study-variable DSS
│
└── GENERATED/                   Script outputs, mirroring module structure
    ├── mod_forcing/
    │   └── climate/             Climate extraction outputs
    └── ...
```

### 4. Run a module

Scripts within each module are numbered in execution order (`_1_`, `_2_`, ...).  
Example for reservoir evaporation:

```bash
cd mod_reservoir/evaporation
python _2_run_reservoir_evap.py            # Product A, all reservoirs
python _2_run_reservoir_evap.py --Product_B  # Product B
```

---

### 5. Documentation

Sphinx site: `cd docs && make html` (output `docs/_build/html`).

**Execution runbooks** (standalone, not part of the Sphinx build):

- [Product A Validation Runbook](docs/manifests/Product_A_Validation_Manifest.md)
