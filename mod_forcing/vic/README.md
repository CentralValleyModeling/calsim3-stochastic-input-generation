# VIC Workflow

All paths below are relative to the repo root (`calsim3-stochastic-input-generation/`). Scripts use `utils.paths` to resolve data directories from `config.json` / `config_default.json`.

- **Scripts**: `mod_forcing/vic/`
- **Base data**: `data/BASE/` (`get_base_dir()`)
- **Generated data**: `data/GENERATED/mod_hydrology/vic/` (`get_module_generated_dir("mod_hydrology/vic")`)
- **Grid info**: `mod_forcing/vic/reference/GridInfo/`

## 1. Append Wind to WGEN Climate Data

WGEN outputs precip and temperature but not wind. These scripts merge historical wind data with WGEN climate files to create complete VIC forcing inputs.

**`_1_append_wind_wgen_hist.py`** — Product A (historical-length scenarios)
- Merges wind from `data/BASE/Historical_Climate/1_Historical/` with WGEN files from `data/BASE/WGEN/Product_A/{scenario}/`
- Matches by date (1915-2021)
- Output: `data/GENERATED/mod_hydrology/vic/input/Product_A/{scenario}/meteo_*`

**`_1_append_wind_wgen_stochastic.py`** — Product B (1000-year stochastic)
- Uses `data/BASE/WGEN/resampled.dates_Product_B_1000yr.csv` to map stochastic dates → historical wind dates
- WGEN files from `data/BASE/WGEN/Product_B/{scenario}/`
- Output: `data/GENERATED/mod_hydrology/vic/input/Product_B/{scenario}/meteo_*`

## 2. Run VIC

The VIC model version used for CalSim perturbed hydrology is 4.2.d and can be downloaded from:
https://cadwr.box.com/s/64ghda1cqfy4vtdwkbsr8s6o8i3lbem5

After download, place the VIC model executable in the generated data directory:
```data/GENERATED/mod_hydrology/vic/VIC_Support_4.2.d/src/```

The global parameter files for running VIC are available from the Box folder.

To run:
```bash
cd data/GENERATED/mod_hydrology/vic/VIC_Support_4.2.d/src/
./vicNl.exe -g ../global_Historical.txt
./vicNl.exe -g ../global_WGEN_Product_A_1.txt
./vicNl.exe -g ../global_WGEN_Product_B_1.txt
```

Outputs daily fluxes (runoff, baseflow, ET, etc.) to `data/GENERATED/mod_hydrology/vic/output/fluxes/{Product}/`.

## 3. Compile Rim Inflows

**`_2_compile_rim_inflows.py`** — Aggregates VIC grid-cell fluxes to watershed-scale monthly inflows.

Default paths are resolved via `utils.paths`; explicit overrides shown below (relative to repo root):

```bash
# Historical
python mod_forcing/vic/_2_compile_rim_inflows.py \
    --fluxes_path data/GENERATED/mod_hydrology/vic/output/fluxes/Historical \
    --output_path data/GENERATED/mod_hydrology/vic/output/routed/Historical

# Product A
python mod_forcing/vic/_2_compile_rim_inflows.py \
    --fluxes_path data/GENERATED/mod_hydrology/vic/output/fluxes/Product_A/1 \
    --output_path data/GENERATED/mod_hydrology/vic/output/routed/Product_A/1

# Product B (10 × 100 water-year chunks)
python mod_forcing/vic/_2_compile_rim_inflows.py --Product_B \
    --fluxes_path data/GENERATED/mod_hydrology/vic/output/fluxes/Product_B/1 \
    --output_path data/GENERATED/mod_hydrology/vic/output/routed/Product_B/1
```

Grid info defaults to `mod_forcing/vic/reference/GridInfo/` (override with `--grid_info_path`).

**Product B chunking:**
- Skips first 9 months to align to October (water year start)
- Outputs 10 files per watershed: `*_qmo_n01.csv` through `*_qmo_n10.csv`
- Each file contains 100 full water years (Oct–Sep), stamped as WY1922–WY2021
- n01 = stochastic months 10–1209, n02 = months 1210–2409, etc.

**Options:**
- `--watersheds NAME [NAME ...]` — process only specified watersheds
- `--full_vic` — use full VIC output columns (default is trimmed)
- `--start_date` / `--end_date` — date range for non-Product B runs
