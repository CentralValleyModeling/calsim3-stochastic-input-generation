# VIC Workflow

## 1. Append Wind to WGEN Climate Data

WGEN outputs precip and temperature but not wind. These scripts merge historical wind data with WGEN climate files to create complete VIC forcing inputs.

**`_1_append_wind_wgen_hist.py`** — Product A (historical-length scenarios)
- Merges wind from `data/Historical_Climate/1_Historical/` with WGEN files
- Matches by date (1915-2021)
- Output: `input/Product_A/{scenario}/meteo_*`

**`_1_append_wind_wgen_stochastic.py`** — Product B (1000-year stochastic)
- Uses `data/WGEN/resampled.dates_Product_B_1000yr.csv` to map stochastic dates → historical wind dates
- Output: `input/Product_B/{scenario}/meteo_*`

## 2. Run VIC

```bash
cd VIC_Support_4.2.d/src/
./vicNl.exe -g ../global_Historical.txt
./vicNl.exe -g ../global_WGEN_Product_A_1.txt
./vicNl.exe -g ../global_WGEN_Product_B_1.txt
```

Outputs daily fluxes (runoff, baseflow, ET, etc.) to `output/fluxes/{Product}/`.

## 3. Compile Rim Inflows

**`_2_compile_rim_inflows.py`** — Aggregates VIC grid-cell fluxes to watershed-scale monthly inflows.

```bash
# Historical
python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo \
    --fluxes_path ./output/fluxes/Historical --output_path ./output/routed/Historical

# Product A
python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo \
    --fluxes_path ./output/fluxes/Product_A/1 --output_path ./output/routed/Product_A/1

# Product B (10 × 100 water-year chunks)
python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo \
    --fluxes_path ./output/fluxes/Product_B/1 --output_path ./output/routed/Product_B/1 --Product_B
```

**Product B chunking:**
- Skips first 9 months to align to October (water year start)
- Outputs 10 files per watershed: `*_qmo_n01.csv` through `*_qmo_n10.csv`
- Each file contains 100 full water years (Oct–Sep), stamped as WY1922–WY2021
- n01 = stochastic months 10–1209, n02 = months 1210–2409, etc.

**Options:**
- `--watersheds NAME [NAME ...]` — process only specified watersheds
- `--full_vic` — use full VIC output columns (default is trimmed)
- `--start_date` / `--end_date` — date range for non-Product B runs
