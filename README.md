# CalSim Synthetic Hydroclimate

Generate synthetic hydroclimate inputs for **CalSim 3.0** (California's State Water Project model) to support long-term stochastic water supply planning studies.

**Organization**: California Department of Water Resources (DWR)  
**Python Environment**: `py38` (conda)

---

## Products

| Product | Period | Description |
|---------|--------|-------------|
| **A** | 1915–2018 (~104 yr) | Historical-length scenarios; WGEN matched to historical period |
| **B** | 1000 years | Long-term stochastic sequences; 10 chunks × 100 water years |

---

## Repository Structure

```
calsim-stochastic/
├── mod_forcing/
│   ├── vic/                  Append wind → run VIC → compile rim inflows
│   └── climate/              Climate extractions (point locations + basin averages)
│
├── mod_hydrology/
│   ├── calsimhydro/          Sacramento Valley hydrology (CalSimHydro model)
│   ├── calsimhydro_ee/       East Side hydrology (Mono Lake basin)
│   ├── closure_terms/        Water balance closure terms
│   ├── rim_inflow/           Quantile-map VIC rim inflows
│   ├── delta_channel_depletion/  Delta ag demands (DETAW/DCD)
│   ├── small_watersheds/     Small watershed precipitation + model post-processing
│   ├── tulare_gw/            Tulare groundwater WYT monthly-average reconstruction
│   └── water_year_types/     Water Year Type classification (Sac/SJ 40-30-30)
│
├── mod_reservoir/
│   ├── evaporation/          Hargreaves-Samani evaporation for 95 reservoirs
│   └── storage_curves/       Reservoir storage alignment
│
├── mod_other/
│   ├── day_volume_fractions/ Monthly→daily disaggregation
│   ├── instream_flows/       Minimum instream flow requirements (Feather River)
│   ├── upper_watershed/      Lower Yuba and Don Pedro modules
│   └── miscellaneous/        Miscellaneous CalSim SVs (NDOI accretion, WYT terms, etc.)
│
├── mod_postprocessing/
│   ├── sv_compile/           Final DSS compilation (all modules → single DSS)
│   └── product_a_validation/ Product A vs. historical CalSim comparison
│
├── utils/                    Shared Python utilities (quantile mapping, flow indices, WYT framework)
├── inventory/                Master CalSim SV inventory
│   └── screening/
│       └── salinity/         Delta salinity (not yet implemented)
│
├── config_default.json       Default config (data_dir = ./data; tracked in git)
├── data/                     NOT tracked — download from Box (see Data section below)
└── docs/                     Sphinx documentation (deployed to GitHub Pages)
```

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

### 2. Data

Large data files (WGEN output, VIC forcing/flux files, model run DSS outputs) are
hosted on a public Box.com folder. Download what you need and place it under `data/`
(or any directory you specify in `config.json`).

**Box folder**: https://cadwr.app.box.com/s/8dqqrbw86cutpbihpuktgmx8nni9vcv7

#### Configuring the data directory

All scripts resolve data paths through `utils/paths.py`, which reads the `data_dir`
setting from a config file:

1. **Default** — `config_default.json` (tracked in git) sets `"data_dir": "./data"`.
   This works if you place data files in a `data/` folder at the repo root.

2. **Custom** — Copy `config_default.json` to `config.json` (gitignored) and set
   `data_dir` to any absolute or relative path on your machine:

   ```json
   {
     "data_dir": "D:/CalSim_Data"
   }
   ```

   Relative paths are resolved relative to the repo root.

Data is organized into two sub-folders under `data_dir`:

- **`BASE/`** — Original, read-only reference and modeling files (WGEN output,
  historical climate, baseline CalSim DSS, etc.)
- **`GENERATED/`** — All script-produced inputs and outputs, mirroring the module
  folder structure (e.g., `GENERATED/mod_hydrology/calsimhydro/output/`)

---

## Expected data directory layout

```
data/                            (or wherever data_dir points)
├── BASE/                        Read-only source data (download from Box)
│   ├── WGEN/
│   │   ├── Product_A/           meteo_LAT_LON files, 1915–2018  (~14 GB)
│   │   └── Product_B/           10 chunk subdirs n01–n10, 1000 yr  (~120 GB)
│   ├── Historical_Climate/
│   │   └── 1_Historical/        Observed climate with wind column  (~1 GB)
│   ├── CalSim3/
│   │   └── __calsim_sv_default__.dss   CalSim3 baseline study-variable DSS
│   └── CS3_Baseline_Hydrology/  CDEC rim inflow grid info, etc.
│
└── GENERATED/                   Script outputs, mirroring module structure
    ├── mod_forcing/
    │   └── climate/             Climate extraction outputs
    ├── mod_hydrology/
    │   ├── vic/                  VIC forcing (input/) and flux/routed output
    │   ├── calsimhydro/          CalSimHydro precip, ET, postprocessed outputs
    │   │   ├── CalSimHydro_Runs/         DSS model run outputs
    │   │   └── CalSimHydro_Rebalance_Runs/
    │   ├── calsimhydro_ee/       CalSimHydroEE outputs + run DSS
    │   ├── delta_channel_depletion/  DETAW precip, DCD run outputs
    │   │   └── DeltaChannelDepletion_Runs/
    │   ├── rim_inflow/
    │   ├── small_watersheds/
    │   │   └── SmallWatersheds_Runs/
    │   └── ...
    ├── mod_reservoir/
    │   ├── evaporation/
    │   └── storage_curves/
    └── mod_other/
        ├── miscellaneous/
        └── ...
```

### 3. Run a module

Scripts within each module are numbered in execution order (`_1_`, `_2_`, ...).  
Example for reservoir evaporation:

```bash
cd mod_reservoir/evaporation
python _2_run_reservoir_evap.py            # Product A, all reservoirs
python _2_run_reservoir_evap.py --Product_B  # Product B
```

---

## Processing Dependencies

```
data/  (WGEN met files + Historical Climate)
  │
  ├─► mod_forcing/vic             append wind → run VIC → compile rim inflows
  │       │
  │       ├─► mod_hydrology/rim_inflow        quantile-map VIC rim inflows
  │       │       └─► mod_hydrology/water_year_types   Sac/SJ WYT classification
  │       │               ├─► mod_hydrology/closure_terms    water balance closure
  │       │               ├─► mod_hydrology/tulare_gw        WYT monthly-avg reconstruction
  │       │               ├─► mod_other/upper_watershed      Lower Yuba / Don Pedro
  │       │               └─► mod_other/miscellaneous        (WYT-based terms)
  │       │
  │       ├─► mod_hydrology/rim_inflow (also feeds)
  │       │       ├─► mod_other/instream_flows    Feather River min flow (Oroville)
  │       │       └─► mod_reservoir/storage_curves Oroville storage alignment
  │       │
  │       ├─► mod_hydrology/calsimhydro         Sacramento Valley ET/runoff
  │       ├─► mod_hydrology/calsimhydro_ee      East Side hydrology
  │       ├─► mod_hydrology/delta_channel_depletion  Delta ag demands (DETAW/DCD)
  │       ├─► mod_hydrology/small_watersheds
  │       ├─► mod_reservoir/evaporation         Hargreaves-Samani, 95 reservoirs
  │       ├─► mod_forcing/climate               Point + basin climate extractions
  │       └─► mod_other/miscellaneous           (NDOI precip accretion)
  │
  └─► mod_other/day_volume_fractions    bootstrap daily fractions (Freeport flows)

All modules above
  └─► mod_postprocessing/sv_compile          merge all SVs → output DSS
        └─► mod_postprocessing/product_a_validation
```

---

## Documentation

Built with Sphinx + MyST-Parser, deployed to GitHub Pages via Actions.

```bash
cd docs && make html
```
