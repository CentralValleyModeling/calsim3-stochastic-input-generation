# Product A Validation - Execution Runbook

> **Scope:** the Product A pipeline -- 1921-2018 historical-length split-sample
> quantile-mapping **validation** (train 1921-1971, simulate/validate
> 1972-2018). One continuous monthly time series per study variable (SV).
>
> **Standalone document** at the repo root. Not part of the Sphinx build.
>
> **Paths are logical.** Resolve them through `utils/paths.py`
> (`get_base_dir()` = `<data_dir>/BASE`, `get_module_generated_dir(...)` =
> `<data_dir>/GENERATED/<module>`). Data lives outside the repo and is
> git-ignored.
>
> **All commands run from the repo root.**
>
> **Product A and Product B are always run separately.** Every script that
> emits Product A or Product B data takes a required `--product A|B` flag
> (a few have an additional `validation` or `calibrate` choice for
> diagnostics that are neither A nor B). There is no implicit default and no
> mode that runs both in one go. To switch to the Product B pipeline,
> re-invoke each command with `--product B`.
>
> **Tier structure mirrors `docs/source/input-generation/overview.md`:**
> Tier 1 Forcing -> Tier 2 Core Hydrology -> Tier 3 Water Year Types ->
> Tier 4 Dependent Modules -> Tier 5 Final Compilation. Within Tier 2, each
> external-run model is presented as a contiguous block:
> compile precip/ET -> [EXTERNAL] model run -> postprocess.
>
> **Per-script details** (CLI flags / methodology) live in each script's
> standardized header docstring. Convention is enforced by
> `tools/check_scripts.py` and CI.

---

## A. End-to-end ordering (quick reference)

```
Tier 1  FORCING (mod_forcing)
    VIC:
        python mod_forcing/vic/_1_append_wind_wgen_hist.py
        -> [EXTERNAL] VIC hydrologic model run
        python mod_forcing/vic/_2_compile_rim_inflows.py --product A
    Climate:
        python mod_forcing/climate/_1_pp_point_locations.py --source Product_A --scenario 1
        python mod_forcing/climate/_2_uhh_basin_averages.py --source Product_A --scenario 1

Tier 2  CORE HYDROLOGY (mod_hydrology)
    CalSimHydro:
        python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30
        python mod_hydrology/calsimhydro/_2_compile_et.py --product A --et_type all --vic_col_index 7 --write_dss
        -> [EXTERNAL] CalSimHydro model run
        python mod_hydrology/calsimhydro/_3_postprocess_product_a.py --sources cshydro rebalance rice
    CalSimHydroEE:
        python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A
        -> [EXTERNAL] CalSimHydroEE model run
        python mod_hydrology/calsimhydro_ee/_2_postprocess_product_a.py
    Rim Inflow:
        python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
    Small Watersheds:
        python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A
        -> [EXTERNAL] Small Watersheds model run
        python mod_hydrology/small_watersheds/_2_postprocess_product_a.py
    Delta Channel Depletion:
        python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A
        -> [EXTERNAL] DETAW/DCD model run
        python mod_hydrology/delta_channel_depletion/_2_postprocess_product_a.py

Tier 3  WATER YEAR TYPES (mod_hydrology)
        python mod_hydrology/water_year_types/_1_calc_WYTs.py --product A

Tier 4  DEPENDENT MODULES
    Reservoir Evaporation:
        python mod_reservoir/evaporation/_0_extract_reservoir_database.py --extract   (setup; run once)
        python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A
    Reservoir Storage Curves:
        python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product A
        python mod_reservoir/storage_curves/_2_qmap_product_a.py
        python mod_reservoir/storage_curves/_3_oroville_daily_precip.py --source Product_A --scenario 1
        python mod_reservoir/storage_curves/_4_oroville_level5.py --product A
    Tulare Groundwater Terms:
        python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product A
    Instream Flows:
        python mod_other/instream_flows/_1_min_flow_feather.py --product A
        python mod_other/instream_flows/_2_sjr_rest_req.py --product A
    Upper Watershed Modules:
        python mod_other/upper_watershed/_0_load_sv.py                              (setup; run once)
        python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product A
        python mod_other/upper_watershed/_2_qmap_product_a.py
        python mod_other/upper_watershed/_3_hybrid_product_a.py
        python mod_other/upper_watershed/_4_pge_wy_allocation.py --product A
        python mod_other/upper_watershed/_5_dnp_evaporation.py --calibrate          (setup; run once)
        python mod_other/upper_watershed/_5_dnp_evaporation.py --product A
    Other Variables (Miscellaneous):
        python mod_other/miscellaneous/_0_extract_others.py                          (setup; run once)
        python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product A
        python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product A
        python mod_other/miscellaneous/_3_hybrid_product_a.py
        python mod_other/miscellaneous/_4_qmap_product_a.py

Tier 5  FINAL COMPILATION (postprocessing)
        python postprocessing/sv_compile/product_a_historical_validation.py
        -> ProductA_Historical_Validation_SV.dss  (WY 1972-2018)

        (optional, post external CalSim 3.0 run consuming the SV DSS:
         python postprocessing/calsim_runs/_productA_pickle_builder.py
         python postprocessing/calsim_runs/_productA_postproc.py)
```

Final-compiler module scan order (authoritative -- `MODULE_CONFIG` in
`product_a_historical_validation.py`):
calsimhydro -> calsimhydro_ee -> evaporation -> rim_inflow ->
delta_channel_depletion -> small_watersheds -> storage_curves ->
instream_flows -> tulare_gw_terms -> climate -> miscellaneous ->
upper_watershed.

---

## B. Reference & config files

- `utils/paths.py` -- data-dir resolution (`config.json` overrides
  `config_default.json`; both git-ignored / tracked-default).
- `inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`
  (`MASTER` sheet) -- authoritative SV inventory; drives postprocessor
  filtering and the final compiler's expected/missing/constant-rept
  accounting.
- `<module>/reference/qmap_pairs.csv` -- QM target/predictor pairs.
- `mod_hydrology/rim_inflow/reference/CalSim3_VIC_name_mapping.csv`,
  `RimInflowAnchor.xlsx` -- rim QM pairing + anchor/tributary mass balance.
- `.github/copilot-instructions.md` -- per-module script tables and the
  numbered-script convention enforced by `tools/check_scripts.py`.

Quantile mapping is **deterministic / reproducible** (global `QMAP_SEED` in
`utils/quantile_mapping.py`); the full Product A pipeline is byte-identical
run-to-run on identical inputs.

---

## Tier 1 - Forcing (mod_forcing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| vic/_1 | `python mod_forcing/vic/_1_append_wind_wgen_hist.py` | WGEN `Product_A` met files; historical wind | wind-appended VIC forcing |
| [EXTERNAL] VIC | manual VIC model run | wind-appended forcing | VIC flux files (RUNOFF + BASEFLOW) |
| vic/_2 | `python mod_forcing/vic/_2_compile_rim_inflows.py --product A` | VIC fluxes; grid weights | routed monthly rim inflows `CS3_*_qmo.csv` (+ DSS) |
| climate/_1 | `python mod_forcing/climate/_1_pp_point_locations.py --source Product_A --scenario 1` | WGEN met files; PP point reference | per-location monthly precip CSVs |
| climate/_2 | `python mod_forcing/climate/_2_uhh_basin_averages.py --source Product_A --scenario 1` | WGEN met files; CS3 baseline DSS (UHH precip); grid weights | basin-average precip/Tmax/Tmin/VPD + `_product_a_validation/` SV CSVs |

---

## Tier 2 - Core Hydrology (mod_hydrology)

Each external-run model is a contiguous block: compile inputs ->
[EXTERNAL] model run -> postprocess scenario DSS into validation CSVs.

### CalSimHydro (746 vars)

1. `python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30`
   - **Inputs:** WGEN met files; WBA grid info
   - **Outputs:** daily WBA precip CSVs
2. `python mod_hydrology/calsimhydro/_2_compile_et.py --product A --et_type all --vic_col_index 7 --write_dss --n_workers 8`
   - **Inputs:** VIC fluxes; WBA grid; CS3 RefETo DSS (QM target)
   - **Outputs:** monthly QM'd ET CSVs per WBA (WY 1972-2018)
3. **[EXTERNAL] CalSimHydro model run** -- manual; consumes the precip + ET above.
   - **Outputs:** `CalSimHydro_Product_A/CS3L2015V0Hydro_SV.dss`, `RiceOutput.dss`, `Rebalance_Product_A/.../HydroRebalanceSJRdemands.dss` (+ Historical/VICPrecip/QMET scenarios)
4. `python mod_hydrology/calsimhydro/_3_postprocess_product_a.py --sources cshydro rebalance rice`
   - **Inputs:** external CalSimHydro Product A scenario DSS; master inventory
   - **Outputs:** merged-scenario + summary CSVs + `_product_a_validation/*.csv`

### CalSimHydroEE (17 vars)

1. `python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A`
   - **Inputs:** WGEN met files; East-Side grid info
   - **Outputs:** daily East-Side precip CSVs
2. **[EXTERNAL] CalSimHydroEE model run**
   - **Outputs:** `CalSimHydroEE_Product_A/CalSimHydroEE_DP_EA.dss` (+ Historical/VICPrecip/QMET)
3. `python mod_hydrology/calsimhydro_ee/_2_postprocess_product_a.py`
   - **Inputs:** external CSHydroEE DSS; master inventory
   - **Outputs:** `_cshydroEE_productA_1972_2018.csv` (+ merged/summary/boxplots)

### Rim Inflow (227 vars)

1. `python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py`
   - **Inputs:** VIC routed inflows (vic/_2); CS3 baseline DSS; `CalSim3_VIC_name_mapping.csv`; `RimInflowAnchor.xlsx`
   - **Outputs:** `_riminflow_productA_1972_2018.csv` (+ TS/summary, figures)

### Small Watersheds (210 vars)

1. `python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A`
   - **Inputs:** WGEN met files; SWS station list
   - **Outputs:** monthly SWS precip (in/mo)
2. **[EXTERNAL] Small Watersheds model run**
   - **Outputs:** SWS Product A DSS
3. `python mod_hydrology/small_watersheds/_2_postprocess_product_a.py`
   - **Inputs:** external SWS DSS; master inventory
   - **Outputs:** `_product_a_validation/*.csv`

### Delta Channel Depletion (28 vars)

1. `python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A`
   - **Inputs:** WGEN met files; DCD station list
   - **Outputs:** daily DCD-station precip
2. **[EXTERNAL] DETAW/DCD model run**
   - **Outputs:** `DCD_Calsim3_PlanningStudy_Product_A/.../CS3sv_DCD_PRISM_Dtrnd.dss`
3. `python mod_hydrology/delta_channel_depletion/_2_postprocess_product_a.py`
   - **Inputs:** external DCD DSS; master inventory (CFS->TAF)
   - **Outputs:** `_dcd_productA_1972_2018.csv` (+ merged/summary/boxplots)

---

## Tier 3 - Water Year Types (mod_hydrology)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| water_year_types/_1 | `python mod_hydrology/water_year_types/_1_calc_WYTs.py --product A` | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) | WYT indices under `_1_calc_WYTs/Product_A/` |

---

## Tier 4 - Dependent Modules

### Reservoir Evaporation (95 vars)

1. `python mod_reservoir/evaporation/_0_extract_reservoir_database.py --extract` *(setup; run once when the parameter spreadsheet changes)*
   - **Inputs:** reservoir-parameter Excel workbook
   - **Outputs:** `reference/reservoir_parameters.json` (95 reservoirs)
2. `python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A`
   - **Inputs:** climate temps (climate/_2); `reservoir_parameters.json`
   - **Outputs:** per-reservoir monthly evap CSVs + `_product_a_validation/*.csv`

### Reservoir Storage Curves (7 vars)

1. `python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product A`
2. `python mod_reservoir/storage_curves/_2_qmap_product_a.py`
3. `python mod_reservoir/storage_curves/_3_oroville_daily_precip.py --source Product_A --scenario 1`
4. `python mod_reservoir/storage_curves/_4_oroville_level5.py --product A`
- **Inputs:** CS3 baseline DSS; rim/precip; `reference/qmap_pairs.csv`
- **Outputs:** storage curves + `_product_a_validation/*.csv`

### Tulare Groundwater Terms (14 vars)

1. `python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product A`
   - **Inputs:** WYT indices (water_year_types/_1)
   - **Outputs:** `_1_wyt_monthlyavg/_product_a_validation/*.csv`

### Instream Flows (3 vars)

1. `python mod_other/instream_flows/_1_min_flow_feather.py --product A`
2. `python mod_other/instream_flows/_2_sjr_rest_req.py --product A`
- **Inputs:** rim inflows (rim_inflow/_2)
- **Outputs:** `_product_a_validation/*.csv` (MINFLOWFEATHER; REST_REQ_NP/REST_REQ_P)
- *Optional diagnostic:* both scripts also accept `--product validation` for a 3-way historical-comparison artifact (not a Product A or B output).

### Upper Watershed Modules (12 vars)

1. `python mod_other/upper_watershed/_0_load_sv.py` *(setup; run once when upstream SV inventories change)*
   - **Inputs:** upper-watershed `*_SV.dss`; master inventory xlsx
   - **Outputs:** `output/_0_load_sv/all_dss_paths*.csv`, `matched_dss_to_inventory.csv`
2. `python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product A`
3. `python mod_other/upper_watershed/_2_qmap_product_a.py`
4. `python mod_other/upper_watershed/_3_hybrid_product_a.py`
5. `python mod_other/upper_watershed/_4_pge_wy_allocation.py --product A`
6. `python mod_other/upper_watershed/_5_dnp_evaporation.py --calibrate` *(setup; run once to derive the hypsographic polynomial)*
7. `python mod_other/upper_watershed/_5_dnp_evaporation.py --product A`
- **Inputs:** upper_watershed/_0 SV reference; WYT indices; rim_inflow/_2 rim CSV; `reference/qmap_pairs.csv`
- **Outputs:** `_product_a_validation/*.csv`

### Other Variables (Miscellaneous) (6 vars)

1. `python mod_other/miscellaneous/_0_extract_others.py` *(setup; run once when the CalSim baseline changes)*
   - **Inputs:** CalSim baseline `__calsim_sv_default__.dss`
   - **Outputs:** baseline "Other" monthly series (module reference)
2. `python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product A`
3. `python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product A`
4. `python mod_other/miscellaneous/_3_hybrid_product_a.py`
5. `python mod_other/miscellaneous/_4_qmap_product_a.py`
- **Inputs:** miscellaneous/_0 baseline; WYT indices; rim_inflow/_2 rim CSV; `reference/qmap_pairs.csv`
- **Outputs:** `_product_a_validation/*.csv` (incl. `TULE_WET_INDX_productA_1972_2018.csv`); `_4_qmap_product_a/` detail + figures

### Closure Terms, Day Volume Fractions, Salinity

No Product A scripts. Closure Terms and Day Volume Fractions are Product B
only; Closure Terms and Salinity use repeating historical patterns
auto-filled by the final compiler (Constant/Rept = T in the master
inventory). The closure-terms diagnostic mode
(`mod_other/closure_terms/_1_ct_calculation.py --diagnostics`) is a
non-product methodology analysis and emits no SV CSV.

---

## Tier 5 - Final Compilation (postprocessing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| sv_compile (final) | `python postprocessing/sv_compile/product_a_historical_validation.py` (`--compute-stats`; `--stats-report`; `--no-term-plots`; `--summary-tables`) | every module's `_product_a_validation/*.csv`; CS3 baseline DSS; master inventory | `ProductA_Historical_Validation_SV.dss` (WY 1972-2018; overwrite window Oct 31 1971 - Sep 30 2018); diagnostic CSVs + per-category R2/NSE/trend figures |
| (optional) calsim_runs | `python postprocessing/calsim_runs/_productA_pickle_builder.py`; `python postprocessing/calsim_runs/_productA_postproc.py` | external CalSim 3.0 run results consuming `ProductA_Historical_Validation_SV.dss` | Product A run pickle cache + postprocessed comparison artifacts |

The final compiler auto-fills inventory "Constant/Rept" SVs from the
baseline 12-month repeat.
