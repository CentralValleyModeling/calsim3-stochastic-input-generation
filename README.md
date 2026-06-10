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
│   ├── sv_compile/           Merge all module outputs -> DSS (Product A & B)
│   └── calsim_runs/          Postprocess DSS from calsim runs
│
├── utils/                    Shared utilities (quantile mapping, flow indices, WYT framework)
├── inventory/                Master CalSim SV inventory spreadsheet
├── docs/                     Sphinx documentation
├── config_default.json       Default config (data_dir = ./data)
└── environment.yml           Conda environment spec
```

---

### 3. Data

Large files (WGEN, VIC, DSS) are git-ignored and live outside the repo on Box: https://cadwr.app.box.com/s/8dqqrbw86cutpbihpuktgmx8nni9vcv7

By default scripts expect data under `data/` at the repo root, split into `BASE/` (read-only inputs) and `GENERATED/` (script outputs). To use a different location, copy `config_default.json` → `config.json` and set `data_dir`.

#### Acquiring the data

`data_management.py` downloads the module-level zips published on Box (listed in `data_links.json`) and extracts them into your `data_dir`, mirroring the `BASE/` and `GENERATED/` structure:

```bash
python data_management.py acquire                       # all modules
python data_management.py acquire --base-only           # BASE/ only
python data_management.py acquire GENERATED/mod_forcing/climate   # one module
python data_management.py acquire --dry-run             # preview without downloading
```

The `cadwr.box.com` enterprise instance requires authentication. Provide a Box Developer Token (from https://developer.box.com) via the `BOX_TOKEN` environment variable or `--token`. 

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

### 4. Run the pipeline

Scripts within each module are numbered in execution order (`_1_`, `_2_`, ...) and run as scripts from inside their own directory. The full end-to-end run order, per-module commands, validation steps, and CLI flags are documented in the two production runbooks:

- **[Product A Validation Runbook](Product_A_Validation_Manifest.md)** — 1921–2018 historical-length scenarios.
- **[Product B Production Runbook](Product_B_Production_Manifest.md)** — 1000-year stochastic sequences (10 chunks of 100 water years).

Follow the relevant manifest start to finish; it points at each module in dependency-tiered order through to the final DSS compilation.

---

### 5. Documentation

Published documentation: **https://centralvalleymodeling.github.io/calsim3-stochastic-input-generation/**
(deployed automatically from `main` by `.github/workflows/deploy-docs.yml`).

The docs are a Sphinx site under `docs/`. To work on them locally:

**Install the docs toolchain (once):**

```bash
pip install -r docs/requirements.txt
```

**Serve with live reload** (rebuilds and refreshes the browser as you edit — recommended while authoring):

```bash
cd docs
sphinx-autobuild . _build/html      # then open http://127.0.0.1:8000
# equivalently, if GNU make is installed:  make livehtml
```

**Build once (static HTML):**

```bash
cd docs
sphinx-build -b html . _build/html  # output in docs/_build/html
# equivalently, if GNU make is installed:  make html
```

Open the result at `docs/_build/html/index.html` (on Windows: `start docs/_build/html/index.html`).

> The `make html` / `make livehtml` shortcuts require GNU `make`, which is not installed by
> default on Windows; use the `sphinx-build` / `sphinx-autobuild` commands above instead.
> `docs/_build/` is git-ignored.
