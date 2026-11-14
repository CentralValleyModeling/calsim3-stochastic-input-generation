# CalSim Stochastic Input Generation

Generate synthetic hydroclimate inputs for CalSim 3.0 (California DWR water system model) for stochastic water supply planning.

## Formatting & Style 
Do not use emojis or non-ASCII characters in code or outputs.

---

## Products

**Historical_Unsplit** (`--product historical`, WY1922-2018): the historical weather record without the temperature detrending (WGEN `Historical_Unsplit`). Single continuous time series per SV; the validation basis.

**Product A** (`--product A`, WY1922-2018, `utils.paths.DELIVERY_WY`): Historical-length scenarios. WGEN matched to historical period, actual wind merged. Single continuous time series per SV.

**Product B** (1000 years): Stochastic planning sequences. WGEN stochastic generation, resampled wind. 10 chunks x 100 water years (`*_n01.csv` through `*_n10.csv`). First 9 months skipped for Oct WY alignment.

---

## Repository Structure

```
root/
├── mod_forcing/              Rim-inflow model runs and climate extractions
│   ├── inflows/              Run the configured rim-inflow model (SAC-SMA or VIC) and write its arc flows
│   └── climate/              Point precip, basin-avg climate (T, PPT, VPD); GridInfo basin weights;
│                             CIMIS-adjusted RefET and CropET (_3_refet_cimis_adj)
│
├── mod_hydrology/            Sacramento Valley, East Side, rim inflow, Delta, WYTs
│   ├── calsimhydro/          Sac Valley: compile precip and pan evaporation, postprocess the single series & Product B
│   ├── calsimhydro_ee/       External elements: compile precip, postprocess
│   ├── rim_inflow/           Build the rim-inflow SVs from the model's arc flows; skill evaluation
│   ├── water_year_types/     Sac 40-30-30, SJ 60-20-20 WYT classification
│   ├── delta_channel_depletion/  DETAW/DCD Delta ag demands
│   ├── small_watersheds/     SWS precipitation compilation and postprocessing
│   └── tulare_gw_terms/      Tulare GW terms: WYT monthly average reconstruction
│
├── mod_reservoir/            Reservoir evaporation and storage
│   ├── evaporation/          Hargreaves-Samani for 95 reservoirs
│   └── storage_curves/       Storage-level index curves, Mammoth Pool QM, Oroville daily precip and Level 5
│
├── mod_other/                Supplementary terms
│   ├── closure_terms/        Product B closure terms from the WGEN resampling record
│   ├── day_volume_fractions/ Product B daily VOL-FRACTION patterns (date-stitching)
│   ├── instream_flows/       Feather River minimum instream flow, SJR restoration
│   ├── miscellaneous/        Misc SVs (extract baseline, NDOI accretion, WYT/hybrid)
│   └── upper_watershed/      Lower Yuba, Don Pedro: WYT/QM/hybrid reconstruction
│
├── postprocessing/           Final compilation and validation
│   ├── calsim_runs/          Postprocess the external CalSim 3 runs (pickle caches, validation, infeasibility diagnostics)
│   └── sv_compile/           Merge all module outputs into DSS (single_series_compilation.py, product_b_compilation.py)
│
├── utils/                    Shared utilities
│   ├── paths.py              Config & path resolution (data_dir, BASE, GENERATED dirs), WEATHER_SETS, DELIVERY_WY
│   ├── wgen.py               WGEN weather reader (met_path, nearest_cell, read_met, weighted_daily)
│   ├── wgen_calendar.py      Calendar of the weather sets: water_year, Product B stamp and label months, write_chunk_csvs
│   ├── env_check.py          require_env(): stop a run outside the pipeline's environment
│   ├── check_outputs.py      Check the delivery CSVs of Historical_Unsplit and Product A before a compile
│   ├── check_scripts.py      Script convention check (CI)
│   ├── validation_plots.py   Validation figure (time series + CDF) and R2 / NSE / PBIAS
│   ├── qmap_fit.py           Fit window and predictor sources of the rim-inflow quantile maps
│   ├── dss_io.py             open_dss() context manager: Windows long-path junction + catalog_flag (THE canonical DSS open)
│   ├── csv_io.py             SV-format CSV helpers (to_validation_df, read_sv_csv, load_sv_series)
│   ├── quantile_mapping.py   qmap_single(): empirical CDF QM (deterministic via global QMAP_SEED)
│   ├── qmap_single_from_pairs.py  Reusable single-series QM (Historical_Unsplit, Product A) driven by qmap_pairs.csv
│   ├── qmap_product_b_from_pairs.py  Reusable Product B chunked QM driven by qmap_pairs.csv
│   ├── wyt_monthlyavg_framework.py  compute_wyt_monthlyavg(): WYT x month reconstruction
│   └── dss_pickle_builder.py CalView-style DSS cache (values/diffs/units pkl); routes through dss_io
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

Data layout: `BASE/WGEN/Historical_Unsplit/`, `BASE/WGEN/{Product_A,Product_B}/1/`, `BASE/Historical_Climate_LTO/1_Historical/`, `BASE/CalSim3/__calsim_sv_default__.dss`. Outputs mirror module structure under `GENERATED/`.

---

## Code Patterns

**Path setup** (all scripts):
```python
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
```

**Weather set selection**: `--product historical|A|B` (required, no default; the keys of `utils.paths.WEATHER_SETS`). Climate and storage curves `_3` also take `LTO` (Historical_Climate_LTO). A few scripts add a choice for non-product output (e.g., `--product validation` on `_1_min_flow_feather.py` / `_2_sjr_rest_req.py`, or a separate `--calibrate` flag on `_5_dnp_evaporation.py`). The sets are always run separately; there is no "all" mode. WGEN files are read through `utils/wgen.py` and dated through `utils/wgen_calendar.py` (Product B: `label`, `write_chunk_csvs`, `LABEL_MONTHS`, `LABEL_DAYS`).

**Output dirs**: `_gen / "output" / "_N_script_name"`. Delivery of the single series: `utils.paths.delivery_dir(<output root>, product)`, i.e. `_historical_unsplit_validation/` or `_product_a_validation/` (all of them: `utils.paths.delivery_dirs`). Product B final: a `_product_b_final/` folder in the module's output, `output/_product_b_final/` or under a script's folder (`output/_4_postprocess_product_b/_product_b_final/`); `product_b_compilation.py` lists each in `MODULE_CONFIG_B`.

**CSV formats**: Standard SV: `Part B, Part C, Year, Month, Value`. Product B long: `date, WY, month, WYT, term, value`. WYT framework: `WaterYear, Month, value`.

**Water year**: `utils.wgen_calendar.water_year(year, month)`; October to December count toward the next year.

**DSS I/O**: open every DSS file through `utils/dss_io.py` (`open_dss`,
`read_monthly_series`, `read_monthly_frame`) instead of importing `HecDss`
directly -- it centralizes the long-path / Windows-junction handling and the
`catalog_flag` convention. DSS path format:
`/BASIN/LOCATION//PARAM/01JAN1921/1MONTH/RUN/`.

---

## Script Convention

Numbered pipeline scripts (`_0_*.py`, `_1_*.py`, ...) run in numeric order and
follow a uniform shape. `utils/check_scripts.py` (run locally and in CI on push/PR,
`.github/workflows/lint.yml`) checks the rules its docstring lists, among them ASCII only,
no `# %%` markers, a docstring with the `===` title underline, pyflakes, DSS files opened
through `utils.dss_io` and no hard-coded `../data`. The shape:

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

WGEN -> rim-inflow model (mod_forcing/inflows) -> rim_inflow builder -> [water_year_types, mod_other, ...]; WGEN -> [climate, calsimhydro, calsimhydro_ee, evaporation, ...] -> postprocessing/sv_compile -> Final DSS

**Tiers**: (1) mod_forcing/inflows, (2) mod_forcing/climate, (3) mod_hydrology/*, (4) water_year_types, (5) delta_channel_depletion + small_watersheds, (6) mod_reservoir/evaporation (independent), (7) mod_other/*, (8) postprocessing/sv_compile

---

## Module Details

### mod_forcing/inflows/

The config names the model (`inflow_model`, an adapter in `adapters/`), its folder, environment and pin (`inflow_pin`); `generated_dir` names the GENERATED folder of its chain.

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_build_forcing.py` | Build the model's input from BASE where its folder lacks it (VIC: a forcing file per cell with the LTO wind) and check it against BASE (G2) | historical, A, B (`--forcing`, `--cells`; `--cells all` builds) |
| `_2_run_product.py` | Run the model at the pin and write `arc_inflow_monthly.csv` + `run_manifest.json` | historical, A, B (`--forcing`, `--allow-dirty`) |
| `adapters/sacsma.py` | SAC-SMA dPL-CalSim with its share model; Product B in 10 segments (G1, G6) | delivered in v1.1 |
| `adapters/vic.py` | VIC 4.2.d under WSL, pinned by the sha256 of its files; arcs routed from GridInfo; xz-compressed flux store reused while model and inputs match (G1: 8 cells rerun byte for byte) | selectable |

### mod_forcing/climate/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_pp_point_locations.py` | Monthly precip for PP point locations from WGEN | historical, A, B, LTO (`--product`) |
| `_2_uhh_basin_averages.py` | Basin-average precip/temp/VPD for UHH locations (VPD quantile-mapped from temperature, fit on Historical_Unsplit) | historical, A, B, LTO (`--product`, `--start_date`, `--end_date`, `--validate-outputs`, `--compare-historical-productB`) |
| `_3_refet_cimis_adj/step5_*.py` ... `step14_final_cs3_et_dss.py` | Hargreaves-Samani ETo with the CIMIS adjustment (F1); steps 10a-14 write the CalSimHydro `CS3_RefETo.dss` (11a) and `CS3_ET.dss` (14, PyCUP) to `calsimhydro/output/_2_compile_et/Product_A/` | A (steps 10a-14) |
| `reference/build_8RI_SRBB_gridinfo.py` | Build-time only (needs geopandas): merges Shasta + 7 rim tributary GridInfo components and rasterizes the CT_BENDBRIDGE valley floor (WBA 02/03) from `BASE/CalSim3/calsim3.gpkg` into `CS3_8RI_SRBB_GridInfo.txt`, and writes the valley floor alone as `CS3_I_SRBB_VAL_GridInfo.txt` | n/a |
| `reference/build_no_gooselake_gridinfo.py` | Build-time only (needs geopandas): `--target {I_SHSTA,SRBB,all}` drops the ~1000 sq mi Goose Lake over-extension outside the authoritative SHSTA / CT_BENDBRIDGE drainage, writing `CS3_I_SHSTA_no_gooselake_GridInfo.txt` and `CS3_8RI_SRBB_no_gooselake_GridInfo.txt` | n/a |

### mod_hydrology/calsimhydro/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip.py` | Daily WBA precip from WGEN met files | historical, A & B (`--product`) |
| `_2b_compile_pan_evap.py` | Gerber pan evaporation per WBA from WGEN temperature | historical, A & B (`--product`) |
| `_3_postprocess_single.py` | Extract & postprocess CalSimHydro/Rebalance/Rice DSS -> delivery CSVs | historical, A (`--product`, `--sources`, `--skip-compare`, `--skip-validate`) |
| `_4_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--sources`, `--chunks`, `--compare-a`) |

### mod_hydrology/calsimhydro_ee/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_EE.py` | East Side precip from WGEN grids | historical, A & B (`--product`) |
| `_2_postprocess_single.py` | Extract & postprocess CSHydroEE DSS -> delivery CSVs | historical, A (`--product`) |
| `_3_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--chunks`, `--compare-a`, `--plot`) |

### mod_hydrology/rim_inflow/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_stochastic_inflow_explore.py` | Interactive exploration (30-yr rolling drought scatter) | Analysis |
| `_0_stochastic_precipitation.py` | Precipitation exploration | Analysis |
| `_1_build_rim_inflow.py` | The 241 rim-inflow SVs from the model's arc flows (arcs, anchor sums, gap arcs, alias maps) | A, B, historical (`--product`) |
| `_2_skill_evaluation.py` | The model's historical run against CalSim 3 and v1.0 | historical |

### mod_hydrology/water_year_types/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_calc_WYTs.py` | Sac (40-30-30) and SJ (60-20-20) WYT indices | historical, A & B (`--product`) |
| `_2_compare_wyts.py` | Compare WYT outputs (diagnostic) | Comparison |

Rim components: Sac (SRBB+OROV+YUBA+FOLS), SJ (ST+TU+ME+SJ).

### mod_hydrology/delta_channel_depletion/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_DETAW.py` | Daily precip for DCD stations from WGEN | historical, A & B (`--product`) |
| `_aggregate_dpflow_gwflow_for_DCD.py` | Aggregate DP/GW flow outputs | -- |
| `_merge_DCD_outputs_for_CS3.py` | Merge DCD outputs for CalSim | -- |
| `_2_postprocess_single.py` | Extract & postprocess DCD DSS -> delivery CSVs | historical, A (`--product`) |
| `_3_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--chunks`, `--compare-a`, `--plot`) |

### mod_hydrology/small_watersheds/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_compile_precip_sws.py` | Monthly precip (in/mo) for SWS from WGEN | historical, A & B (`--product`) |
| `_1b_check_precip_output.py` | Verify compiled precip outputs (diagnostic) | -- |
| `_2_postprocess_single.py` | Extract & postprocess SWS DSS -> delivery CSVs | historical, A (`--product`) |
| `_3_postprocess_product_b.py` | Extract Product B DSS (10 chunks) -> per-chunk CSVs | B (`--chunks`, `--compare-a`) |

### mod_hydrology/tulare_gw_terms/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for Tulare GW terms | historical, A & B (`--product`) |

### mod_reservoir/evaporation/

| Script | Purpose | Product |
|--------|---------|---------|
| `evaporation.py` | Core Hargreaves-Samani engine (imported by others) | Utility |
| `_0_extract_reservoir_database.py` | Extract reservoir params from Excel -> JSON | Setup |
| `_1_excel_to_python_validation.py` | Validate Python vs Excel evap results | Validation |
| `_2_run_reservoir_evap.py` | Calculate evap for 95 reservoirs + delivery output | historical, A & B (`--product`, `--compare-a`) |

### mod_reservoir/storage_curves/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_wyt_index_curves.py` | Storage-level index curves from schedule tables and WYTs | historical, A & B (`--product`) |
| `_2_qmap.py` | Quantile-map Mammoth Pool storage via qmap_pairs.csv | historical, A & B (`--product`) |
| `_3_oroville_daily_precip.py` | Daily Oroville basin precip from WGEN | historical, A, B, LTO (`--product`, `--compare`) |
| `_4_oroville_level5.py` | S_OROVLLEVEL5 from the Oroville daily basin precipitation of `_3` (Smax 3,425.2 TAF) | historical, A & B (`--product`) |

### mod_other/closure_terms/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_ct_calculation.py` | The 13 CT_*_SV closure terms of each stamp month: the day-weighted mean of the baseline closure terms of the months WGEN resampled | B (`--product B`), `--diagnostics` |

### mod_other/day_volume_fractions/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_vol_fractions_analysis.py` | Tests whether the baseline's WY1921-1954 VOL-FRACTION patterns copy WY1955-2003 years of similar annual flow (diagnostic) | -- |
| `_2_generate_product_b.py` | Daily VOL-FRACTION patterns of each chunk from the donor water year (WY1955 or later) of nearest annual flow index | B |

### mod_other/instream_flows/

| Script | Purpose | Product |
|--------|---------|---------|
| `_1_min_flow_feather.py` | MINFLOWFEATHER via threshold logic on annual Oroville flow | validation, historical, A & B (`--product`) |
| `_2_sjr_rest_req.py` | SJR restoration flow requirements (REST_REQ_NP, REST_REQ_P) from UNIMP_SJ | validation, historical, A & B (`--product`) |

### mod_other/miscellaneous/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_extract_others.py` | Extract misc SVs from CalSim baseline DSS | Setup |
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for misc SVs | historical, A & B (`--product`) |
| `_2_DeltaAccretionForNDOI.py` | Delta accretion: precip x area x coeff (direct calc) | historical, A & B (`--product`) |
| `_3_hybrid.py` | Hybrid (WYT+QM)/2 for misc terms | historical, A & B (`--product`) |
| `_4_qmap.py` | Quantile mapping via qmap_pairs.csv for misc SVs | historical, A & B (`--product`) |

### mod_other/upper_watershed/

| Script | Purpose | Product |
|--------|---------|---------|
| `_0_load_sv.py` | Load module SV outputs from DSS | Setup |
| `_1_wyt_monthlyavg.py` | WYT monthly average reconstruction for upper watershed SVs | historical, A & B (`--product`) |
| `_2_qmap.py` | Quantile mapping via qmap_pairs.csv for upper watershed SVs | historical, A & B (`--product`) |
| `_3_hybrid.py` | Hybrid (WYT+QM)/2 for upper watershed terms | historical, A & B (`--product`) |
| `_4_pge_wy_allocation.py` | PGE_WY_ALLOCATION_SV: threshold logic on annual Folsom flow | historical, A & B (`--product`) |
| `_5_dnp_evaporation.py` | Don Pedro evaporation | historical, A & B (`--product`), `--calibrate` |

### postprocessing/calsim_runs/

| Script | Purpose | Product |
|--------|---------|---------|
| `_productA_pickle_builder.py`, `_productA_postproc.py` | Pickle cache of the historical and Product A DV DSS of an external CalSim 3 run; tables and figures per metric against the baseline | A |
| `_productB_pickle_builder.py`, `_productB_postproc.py` | The same for the chunks of the Product B runs: annual statistics, worst rolling-window means, CDFs, block box plots | B |
| `_historical_modified_pickle_builder.py`, `_historical_modified_postproc.py` | Historical against a modified historical run (Freeport / Vernalis metrics) | -- |
| `infeasibilities/n*.py` | WRIMS infeasibility diagnostics of Product B chunks; `n10.py` writes the n10 SV DSS with the baseline's first month | B |

---

## Reconstruction Methodologies

- **Quantile Mapping (QM)**: Empirical CDF mapping of a rim-inflow predictor onto a CalSim3 term, fitted on WY1950-2018 as a pass or absorb fit (`utils/qmap_fit.py`). `utils/quantile_mapping.py::qmap_single()`.
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
- `_3_*.py` -- third step ... (postprocessing, scenario comparison, etc.)
- `*_postprocess_single.py` -- postprocessor of an external run of Historical_Unsplit or Product A (`--product historical|A`)
- `*_postprocess_product_b.py` -- standard Product B postprocessor (chunked DSS extraction)

### Output Files & CalSim Conventions

- Historical_Unsplit and Product A: `*_historicalUnsplit_<first WY>_<last WY>.csv` in `_historical_unsplit_validation/` and `*_productA_<first WY>_<last WY>.csv` in `_product_a_validation/`, WY1922-2018 (`utils.paths.DELIVERY_WY`), or the water years a run covers within it; `utils.csv_io.write_delivery_csv` clips to it and removes a series' other spans; `python utils/check_outputs.py` checks the files of both sets before a compile
- Product B: `*_productB_n01.csv` through `*_n10.csv` (10 chunks, each labelled WY1922-2021; `utils.wgen_calendar.write_chunk_csvs`)
- Water Year: Oct-Sep (WY N = Oct(N-1) through Sep(N))
- Reservoir codes: 5-letter (SHSTA, OROVL, FOLSM)
- WGEN met files: `<prefix>_LAT_LON` (`data` for Historical_Unsplit, `meteo` for Products A and B), read through `utils/wgen.py`

---

## Git Conventions

- `data/` is git-ignored (large files on Box)
- `config.json` is git-ignored (user-local data path override)
- `.github/scripts/` is git-ignored
- Python artifacts (`__pycache__/`, `*.pyc`), Jupyter checkpoints, Sphinx `_build/`, and `.vscode/` are ignored
