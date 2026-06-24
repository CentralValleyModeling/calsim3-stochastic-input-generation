# VIC Workflow

All paths below are relative to the repo root (`calsim3-stochastic-input-generation/`). Scripts use `utils.paths` to resolve data directories from `config.json` / `config_default.json`.

- **Scripts**: `mod_forcing/vic/`
- **Base data**: `data/BASE/` (`get_base_dir()`)
- **Generated data**: `data/GENERATED/mod_hydrology/vic/` (`get_module_generated_dir("mod_hydrology/vic")`)
- **Grid info**: `mod_forcing/vic/reference/GridInfo/`

## 1. Append Wind to WGEN Climate Data

WGEN outputs precip and temperature but not wind. These scripts merge historical wind data with WGEN climate files to create complete VIC forcing inputs.

**`_1_append_wind_wgen_hist.py`** — Product A (historical-length scenarios)
- Merges wind from `data/BASE/Historical_Climate_LTO/1_Historical/` with WGEN files from `data/BASE/WGEN/Product_A/{scenario}/`
- Matches by date (1915-2021)
- Output: `data/GENERATED/mod_hydrology/vic/input/Product_A/{scenario}/meteo_*`

**`_1_append_wind_wgen_stochastic.py`** — Product B (1000-year stochastic)
- Uses `data/BASE/WGEN/resampled.dates_Product_B_1000yr.csv` to map stochastic dates → historical wind dates
- WGEN files from `data/BASE/WGEN/Product_B/{scenario}/`
- Output: `data/GENERATED/mod_hydrology/vic/input/Product_B/{scenario}/meteo_*`

## 2. Run VIC

The VIC model version used for CalSim perturbed hydrology is 4.2.d. The source
tree, parameter files, and global parameter files live in the generated data
directory (downloaded from Box once):

```
data/GENERATED/mod_forcing/vic/VIC_Support_4.2.d/
  src/          C source + Makefile, and the compiled vicNl binary
  parameters/   soil / veg / snow-band parameter files
  global_*.txt  one global parameter file per scenario
```

VIC 4.2.d is a C program. The `vicNl` binary shipped in `src/` was compiled for
**ARM aarch64** and will NOT run on an x86-64 machine. On Windows, build and run
it under WSL (Ubuntu). The original ARM binary is preserved as `src/vicNl_aarch64`.

### 2a. Build (one-time, under WSL)

```bash
# install a C toolchain (WSL authenticates via Windows, so -u root needs no password)
wsl -u root -e bash -lc 'apt-get update && apt-get install -y build-essential'

# build on the native Linux filesystem (not /mnt/c) for speed
SRC="/mnt/c/.../data/GENERATED/mod_forcing/vic/VIC_Support_4.2.d/src"
mkdir -p ~/vicbuild && cp "$SRC"/*.c "$SRC"/*.h "$SRC/Makefile" ~/vicbuild/ && cd ~/vicbuild
make model CC=gcc \
  CFLAGS="-I. -O2 -std=gnu89 -fcommon -w -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -fno-stack-protector" \
  LIBRARY="-lm"
```

Why the non-default flags (all required to build/run VIC 4.2.d on a modern gcc/glibc):
- `-std=gnu89` keeps implicit declarations as warnings (gcc 14+ makes them hard errors by default).
- `-fcommon` allows the legacy multiple-tentative-definition globals (gcc 10+ defaults to `-fno-common`).
- `-U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 -fno-stack-protector` disables glibc hardening. VIC 4.2.d
  has a benign fixed-buffer over-write in startup config parsing (`get_global_param`) that a
  fortified build aborts on (`*** buffer overflow detected ***`). This is a one-time startup
  write, not in the simulation loop; the de-hardened build (how VIC is historically compiled)
  produces correct, mass-balanced output.

To refresh the committed binary in the data dir: `cp ~/vicbuild/vicNl "$SRC/vicNl"`.

### 2b. Run on the native ext4 filesystem

Run from WSL's ext4 home, not the `/mnt/c` (DrvFs) mount -- output is many large files
and DrvFs is far slower. Stage inputs/outputs on ext4 and point a copy of the global
file at absolute ext4 paths (`FORCING1`, `SOIL`, `VEGLIB`, `VEGPARAM`, `SNOW_BAND`,
`RESULT_DIR`). Keep paths short.

```bash
cd ~/vicbuild
./vicNl -g ~/vicrun/global_WGEN_Product_A_1.txt
```

Reference throughput (this machine, WSL2): ~2.1 s per grid cell for the full
1915-2018 period; the full Product A grid (~4097 cells) takes ~2.4 h and writes
~7.5 GB of daily fluxes. Copy results back to
`data/GENERATED/mod_forcing/vic/output/fluxes/{Product}/` when done.

Outputs daily fluxes (runoff, baseflow, ET, etc.) named `fluxes_<lat>_<lon>`.

## 3. Compile Rim Inflows

**`_2_compile_rim_inflows.py`** — Aggregates VIC grid-cell fluxes to watershed-scale monthly inflows.

Default paths are resolved via `utils.paths`; explicit overrides shown below (relative to repo root):

```bash
# Historical
python mod_forcing/vic/_2_compile_rim_inflows.py \
    --fluxes_path data/GENERATED/mod_hydrology/vic/output/fluxes/Historical \
    --output_path data/GENERATED/mod_hydrology/vic/output/routed/Historical

# Product A
python mod_forcing/vic/_2_compile_rim_inflows.py --product A \
    --fluxes_path data/GENERATED/mod_hydrology/vic/output/fluxes/Product_A/1 \
    --output_path data/GENERATED/mod_hydrology/vic/output/routed/Product_A/1

# Product B (10 chunks of 100 water years)
python mod_forcing/vic/_2_compile_rim_inflows.py --product B \
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
