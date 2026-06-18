# CalSim Stochastic Input Generation

Generate synthetic hydroclimate inputs for CalSim 3.0 (California DWR water system model) for stochastic water supply planning.

## Formatting & Style 
Do not use emojis or non-ASCII characters in code or outputs.

---

## Products

**Product A** (1921-2018): Historical-length scenarios. WGEN matched to historical period, actual wind merged. Single continuous time series per SV.

**Product B** (1000 years): Stochastic planning sequences. WGEN stochastic generation, resampled wind. 10 chunks x 100 water years (`*_n01.csv` through `*_n10.csv`). First 9 months skipped for Oct WY alignment.

---

## Repository Structure

```
root/
├── mod_forcing/              VIC model forcing and climate extractions
│   ├── vic/                  Append wind to WGEN, compile rim inflows from VIC fluxes
│   └── climate/              Point precip, basin-avg climate (T, PPT, VPD)
│
├── mod_hydrology/            Sacramento Valley, East Side, rim inflow, Delta, WYTs
│   ├── calsimhydro/          Sac Valley: compile precip/ET, postprocess Product A & B
│   ├── calsimhydro_ee/       External elements: compile precip, postprocess
│   ├── rim_inflow/           Quantile-map VIC inflows, correlation analysis, NSE metrics
│   ├── water_year_types/     Sac 40-30-30, SJ 60-20-20 WYT classification
│   ├── delta_channel_depletion/  DETAW/DCD Delta ag demands
│   ├── small_watersheds/     SWS precipitation compilation and postprocessing
│   └── tulare_gw_terms/      Tulare GW terms: WYT monthly average reconstruction
│
├── mod_reservoir/            Reservoir evaporation and storage
│   ├── evaporation/          Hargreaves-Samani for 95 reservoirs
│   └── storage_curves/       Mammoth Pool storage Product B quantile mapping
│
├── mod_other/                Supplementary terms
│   ├── instream_flows/       Feather River minimum instream flow, SJR restoration
│   ├── miscellaneous/        Misc SVs (extract baseline, NDOI accretion, WYT/hybrid)
│   └── upper_watershed/      Lower Yuba, Don Pedro: WYT/QM/hybrid reconstruction
│
├── postprocessing/           Final compilation and validation
│   └── sv_compile/           Merge all module outputs → DSS (product_a_historical_validation.py)
│
├── utils/                    Shared utilities
│   ├── paths.py              Config & path resolution (data_dir, BASE, GENERATED dirs)
│   ├── dss_io.py             open_dss() context manager: Windows long-path junction + catalog_flag (THE canonical DSS open)
│   ├── csv_io.py             SV-format CSV helpers (to_validation_df, read_sv_csv, load_sv_series)
│   ├── quantile_mapping.py   qmap_single(): empirical CDF QM (deterministic via global QMAP_SEED)
│   ├── qmap_product_a_from_pairs.py  Reusable Product A split-sample QM driven by qmap_pairs.csv
│   ├── qmap_product_b_from_pairs.py  Reusable Product B chunked QM driven by qmap_pairs.csv
│   ├── wyt_monthlyavg_framework.py  compute_wyt_monthlyavg(): WYT x month reconstruction
│   ├── dss_pickle_builder.py CalView-style DSS cache (values/diffs/units pkl); routes through dss_io
│   └── calculate_correlations_finder.py  R-squared between CalSim and VIC inflows
│
├── inventory/                Master CalSim SV inventory spreadsheet + screening
├── data/                     Large data (git-ignored): BASE/ (read-only) + GENERATED/ (outputs)
├── docs/                     Sphinx documentation source
├── config_default.json       Default config (data_dir = ./data)
└── environment.yml           Conda environment spec
```

---

## Configuration & Data Paths

`utils/paths.py` resolves all data paths. `config.json` (git-ignored) overrides `config_default.json`; both specify `data_dir` (relative paths resolve from repo root).

```python
from utils.paths import get_data_dir, get_base_dir, get_generated_dir, get_module_generated_dir, get_inventory_dir
# get_data_dir()            -> <data_dir>
# get_base_dir()            -> <data_dir>/BASE (read-only source data)
# get_generated_dir()       -> <data_dir>/GENERATED (script outputs)
# get_module_generated_dir("mod_hydrology/calsimhydro")  -> GENERATED/mod_hydrology/calsimhydro
# get_inventory_dir()       -> <repo_root>/inventory
```

Data layout: `BASE/WGEN/{Product_A,Product_B}/1/`, `BASE/Historical_Climate/1_Historical/`, `BASE/CalSim3/__calsim_sv_default__.dss`. Outputs mirror module structure under `GENERATED/`.

---

## Code Patterns

**Path setup** (all scripts):
```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
```

**Product selection**: `--product A|B` (required, no default; mod_forcing/climate scripts use `--source Product_A|Product_B|Historical`). A few scripts add a third choice for non-product output (e.g., `--product validation` on `_1_min_flow_feather.py` / `_2_sjr_rest_req.py`, or a separate `--calibrate` flag on `_5_dnp_evaporation.py`). Product A and Product B are always run separately - there is no "both" mode.

**Output dirs**: `_gen / "output" / "_N_script_name"`. Validation: `output/<script_dir>/_product_a_validation/`. Product B final: `output/_product_b_final/`.

**CSV formats**: Standard SV: `Part B, Part C, Year, Month, Value`. Product B long: `date, WY, month, WYT, term, value`. WYT framework: `WaterYear, Month, value`.

**Water year**: `df['WY'] = df['date'].dt.year + (df['date'].dt.month >= 10).astype(int)`

**DSS I/O**: open every DSS file through `utils/dss_io.py` (`open_dss`,
`read_monthly_series`, `read_monthly_frame`) instead of importing `HecDss`
directly -- it centralizes the long-path / Windows-junction handling and the
`catalog_flag` convention. DSS path format:
`/BASIN/LOCATION//PARAM/01JAN1921/1MONTH/RUN/`.

---

## Script Convention

Numbered pipeline scripts (`_0_*.py`, `_1_*.py`, ...) run in numeric order and
follow a uniform shape, enforced by `utils/check_scripts.py` (run locally and
in CI on push/PR -- see `.github/workflows/lint.yml`):

- **Header docstring**: a `Title` line, a `===` underline, then
  `Inputs` / `Outputs` / `Dependencies` / `Usage` sections.
- **ASCII only** -- no non-ASCII characters anywhere in code or output
  (CLAUDE.md hard rule).
- **Grouped imports**: stdlib, then third-party, then local
  (`from utils ...` after the `sys.path` bootstrap).
- **CLI, not notebooks**: a `main()` plus an `if __name__ == "__main__":`
  guard; no `# %%` Jupyter cell markers.
- **Paths via `utils/paths.py`** -- never hard-code `../../data/`.

---

## Data Flow & Dependencies

WGEN -> VIC (append wind, run model) -> VIC outputs -> [calsimhydro, calsimhydro_ee, rim_inflow, evaporation, ...] -> postprocessing/sv_compile -> Final DSS

**Tiers**: (1) mod_forcing/vic, (2) mod_forcing/climate, (3) mod_hydrology/*, (4) water_year_types, (5) delta_channel_depletion + small_watersheds, (6) mod_reservoir/evaporation (independent), (7) mod_other/*, (8) postprocessing/sv_compile

---

## Module Details

### mod_forcing/vic/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_append_wind_wgen_hist.py` | Append wind to WGEN for VIC (Jupyter-style) | A |
| `_1_append_wind_wgen_stochastic.py` | Append wind to WGEN for VIC (Jupyter-style) | B |
| `_2_compile_rim_inflows.py` | VIC flux files → rim inflows (argparse class); `--product {Historical,Historical_Unsplit,A,B}`; routes the `CS3_8RI_SRBB` Bend Bridge composite directly via a merged GridInfo | Historical, A & B |
| `reference/build_8RI_SRBB_gridinfo.py` | Build-time only (needs geopandas): merges Shasta + 7 rim tributary GridInfo components and rasterizes the CT_BENDBRIDGE valley floor (WBA 02/03) from `BASE/CalSim3/calsim3.gpkg` into `CS3_8RI_SRBB_GridInfo.txt` (single SRBB build; valley step folded in) | n/a |
| `reference/build_no_gooselake_gridinfo.py` | Build-time only (needs geopandas): `--target {I_SHSTA,SRBB,all}` drops the ~1000 sq mi Goose Lake over-extension outside the authoritative SHSTA / CT_BENDBRIDGE drainage, writing `CS3_I_SHSTA_no_gooselake_GridInfo.txt` and `CS3_8RI_SRBB_no_gooselake_GridInfo.txt` | n/a |

### mod_forcing/climate/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_pp_point_locations.py` | Monthly precip for PP point locations from WGEN | A, B, Historical (`--source`, `--scenario`) |
| `_2_uhh_basin_averages.py` | Basin-average precip/temp/VPD for UHH locations | A, B, Historical (`--source`, `--validate-outputs`) |

### mod_hydrology/calsimhydro/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_compare_et_cshydro_vic.py` | Compare ET: CalSimHydro vs VIC (analysis only) | -- |
| `_1_compile_precip.py` | Daily WBA precip from WGEN met files | A & B (`--product A|B`) |
| `_2_compile_et.py` | Area-weighted VIC ET -> QM to CalSim (parallel) | A & B (`--product A|B`, `--n_workers`) |
| `_3_postprocess_product_a.py` | Extract & postprocess CalSimHydro/Rebalance/Rice DSS -> validation CSVs | A (`--sources`, `--skip-compare`, `--skip-validate`) |
| `_4_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--sources`, `--chunks`, `--compare-a`) |

### mod_hydrology/calsimhydro_ee/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_EE.py` | East Side precip from WGEN grids | A & B (`--product A|B`) |
| `_2_postprocess_product_a.py` | Extract & postprocess CSHydroEE DSS -> validation CSVs | A |
| `_3_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--chunks`, `--compare-a`, `--plot`) |

### mod_hydrology/rim_inflow/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_stochastic_inflow_explore.py` | Interactive exploration (30-yr rolling drought scatter) | Analysis |
| `_0_stochastic_precipitation.py` | Precipitation exploration | Analysis |
| `_1_calc_correlations.py` | R² between CalSim and VIC inflows | Correlation (`--basis {Historical,Historical_Unsplit}`) |
| `_2_qmap_historical_validation.py` | Quantile-map Product A to historical period | A (`--basis {Product_A,Historical_Unsplit}`, `--locations`, `--qmap-col`, `--nonexceedance-month`) |
| `_3_qmap_productB.py` | Quantile-map Product B stochastic inflows | B (`--basis {Product_A,Historical_Unsplit}`) |
| `_calc_nse.py` | Nash-Sutcliffe efficiency metrics | Validation |

### mod_hydrology/water_year_types/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_calc_WYTs.py` | Sac (40-30-30) and SJ (60-20-20) WYT indices | A & B (`--product`) |
| `_2_compare_wyts.py` | Compare WYT outputs (diagnostic) | Comparison |

Rim components: Sac (SRBB+OROV+YUBA+FOLS), SJ (ST+TU+ME+SJ).

### mod_hydrology/delta_channel_depletion/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_DETAW.py` | Daily precip for DCD stations from WGEN | A & B (`--product A|B`) |
| `_2_aggregate_dpflow_gwflow_for_DCD.py` | Aggregate DP/GW flow outputs | -- |
| `_3_merge_DCD_outputs_for_CS3.py` | Merge DCD outputs for CalSim | -- |
| `_4_postprocess_product_a.py` | Extract & postprocess DCD DSS -> validation CSVs | A |
| `_5_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--chunks`, `--compare-a`, `--plot`) |

### mod_hydrology/small_watersheds/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_sws.py` | Monthly precip (in/mo) for SWS from WGEN | A & B (`--product A|B`) |
| `_1b_check_precip_output.py` | Verify compiled precip outputs (diagnostic) | -- |
| `_2_postprocess_product_a.py` | Extract & postprocess SWS DSS -> validation CSVs | A |

### mod_hydrology/tulare_gw_terms/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for Tulare GW terms | A & B |

### mod_reservoir/evaporation/

| Script | Purpose | Product |
|--------|---------|---------|
| `evaporation.py` | Core Hargreaves-Samani engine (imported by others) | Utility |
| `_0_extract_reservoir_database.py` | Extract reservoir params from Excel -> JSON | Setup |
| `_1_excel_to_python_validation.py` | Validate Python vs Excel evap results | Validation |
| `_2_run_reservoir_evap.py` | Calculate evap for 95 reservoirs + validation output | A & B (`--product A|B`, `--compare-a`) |

Oroville Level 5: storage-based, DCR 2023 sedimentation correction (3,538 -> 3,424.8 TAF max).

### mod_reservoir/storage_curves/

| Script | Purpose | Product |
|--------|---------|---------|
| `_2_qmap.py` | Quantile-map Mammoth Pool storage via qmap_pairs.csv | A & B (`--product A|B`) |

### mod_other/instream_flows/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_min_flow_feather.py` | MINFLOWFEATHER via threshold logic on annual Oroville flow | A & B |
| `_2_sjr_rest_req.py` | SJR restoration flow requirements (REST_REQ_NP, REST_REQ_P) from UNIMP_SJ | A & B |

### mod_other/miscellaneous/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_extract_others.py` | Extract misc SVs from CalSim baseline DSS | Setup |
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for misc SVs | A & B |
| `_2_DeltaAccretionForNDOI.py` | Delta accretion: precip x area x coeff (direct calc) | A & B |
| `_3_hybrid.py` | Hybrid (WYT+QM)/2 for misc terms | A & B (`--product A|B`) |
| `_4_qmap.py` | Quantile mapping via qmap_pairs.csv for misc SVs | A & B (`--product A|B`) |

### mod_other/upper_watershed/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_load_sv.py` | Load module SV outputs from DSS | Setup |
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for upper watershed SVs | A & B |
| `_2_qmap.py` | Quantile mapping via qmap_pairs.csv for upper watershed SVs | A & B (`--product A|B`) |
| `_3_hybrid.py` | Hybrid (WYT+QM)/2 for upper watershed terms | A & B (`--product A|B`) |
| `_4_pge_wy_allocation.py` | PGE_WY_ALLOCATION_SV: threshold logic on annual Folsom flow | A & B |
| `_5_dnp_evaporation.py` | Don Pedro evaporation | A & B |

---

## Reconstruction Methodologies

- **Quantile Mapping (QM)**: Empirical CDF mapping for terms with good VIC correlation. `utils/quantile_mapping.py::qmap_single()`.
- **WYT Averaging**: Monthly averages by WYT class (W/AN/BN/D/C) for weak correlation. `utils/wyt_monthlyavg_framework.py::compute_wyt_monthlyavg()`.
- **Hybrid (QM + WYT)**: `(QM + WYT) / 2` for low correlation or peak overshoot.
- **Direct Calculation**: Physical formulas and Flow (or index) -to-value relationships with optimized thresholds.
- **Date-Stitching**: Bootstrap from closest matching year by 4/8-river index (day volume fractions).

---

## Naming Conventions

### Scripts

- `_0_*.py` -- setup, database extraction, data loading
- `_1_*.py` -- first processing step (compile precip, calculate indices)
- `_2_*.py` -- second step (quantile map, aggregate)
- `_3_*.py` -- third step ... (postprocessing, Product A validation, scenario comparison, etc.)
- `*_postprocess_product_a.py` -- standard Product A validation postprocessor
- `*_postprocess_product_b.py` -- standard Product B postprocessor (chunked DSS extraction)

### Output Files & CalSim Conventions

- Product A: `*_productA_1921_2018.csv` (single file per SV)
- Product B: `*_productB_n01.csv` through `*_n10.csv` (10 chunks)
- Water Year: Oct-Sep (WY N = Oct(N-1) through Sep(N))
- Reservoir codes: 5-letter (SHSTA, OROVL, FOLSM)
- WGEN met files: `meteo_LAT_LON` (e.g., `meteo_38.5_120.3`)

---

## Git Conventions

- `data/` is git-ignored (large files on Box)
- `config.json` is git-ignored (user-local data path override)
- `.github/scripts/` is git-ignored
- Python artifacts (`__pycache__/`, `*.pyc`), Jupyter checkpoints, Sphinx `_build/`, and `.vscode/` are ignored
