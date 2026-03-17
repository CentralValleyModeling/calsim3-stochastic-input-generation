# CalSim Stochastic Input Generation

Generation of synthetic hydroclimate inputs for **CalSim 3.0** to support long-term stochastic water supply planning studies.

---
## Setup

### 1. Conda environment

> **Windows prerequisite**: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the **C++ workload** is required to compile `pydsstools`.

```bash
# Step 1 — create env and install pydsstools via pip
conda env create -f environment.yml
conda activate csstochastic

# Step 2 — install pandss from the dwr-cvm channel (requires pydsstools already present)
conda install pandss -c dwr-cvm
```

---

### 2. Repository Structure

```
root/
├── mod_forcing/          VIC model forcing and climate extractions
├── mod_hydrology/        CalSimHydro rim inflow, Delta, WYTs etc.
├── mod_reservoir/        Reservoir evaporation and storage
├── mod_other/            Day volume fractions, instream flows, upper watershed, misc SVs
├── mod_postprocessing/   Final DSS compilation, Product A validation, and Product B analysis
├── utils/                Shared utilities (quantile mapping, flow indices, WYT framework)
├── inventory/            Master CalSim SV inventory
├── config_default.json   Default config (data_dir = ./data)
└── docs/                 Sphinx documentation
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

TODO
