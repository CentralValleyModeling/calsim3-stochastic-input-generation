# Product A Validation - Execution Runbook

> **Scope:** the Product A pipeline -- 1921-2018 historical-length split-sample
> quantile-mapping **validation** (train 1921-1971, simulate/validate
> 1972-2018). One continuous monthly time series per study variable (SV).
>
> **Standalone document.** Lives under `docs/` but is excluded from the Sphinx
> build (`docs/conf.py` `exclude_patterns`). Runbook only -- not a
> streamlining log or methodology paper.
>
> **Paths are logical.** Resolve them through `utils/paths.py`
> (`get_base_dir()` = `<data_dir>/BASE`, `get_module_generated_dir(...)` =
> `<data_dir>/GENERATED/<module>`). Data lives outside the repo and is
> git-ignored.
>
> **Per-script details** (CLI flags / working dir / methodology) live in each
> script's standardized header docstring; this runbook only carries what you
> need to *run the pipeline in order*. Convention is enforced by
> `tools/check_scripts.py` and CI.

---

## A. End-to-end ordering (quick reference)

```
Tier 0  SETUP (reference data; run once / when inputs change)
        evaporation/_0_extract_reservoir_database.py --extract
        miscellaneous/_0_extract_others.py
        upper_watershed/_0_load_sv.py

Tier 1  FORCING
        vic/_1_append_wind_wgen_hist.py
        -> [EXTERNAL] VIC model run (wind-appended forcing)
        vic/_2_compile_rim_inflows.py

Tier 2  CLIMATE
        climate/_1_pp_point_locations.py  --source Product_A --scenario 1
        climate/_2_uhh_basin_averages.py  --source Product_A --scenario 1

Tier 3  MODEL-INPUT PREP  (depends on Tier 2 climate + Tier 1 forcing)
        calsimhydro/_1_compile_precip.py --clip_period 1920-10-01 2018-09-30
        calsimhydro/_2_compile_et.py --et_type all --vic_col_index 7 --write_dss
        calsimhydro_ee/_1_compile_precip_EE.py
        delta_channel_depletion/_1_compile_precip_DETAW.py
        small_watersheds/_1_compile_precip_sws.py

Tier 3e [EXTERNAL] MODEL RUNS  (consume Tier 3 precip/ET; produce scenario DSS)
        CalSimHydro run        (<- calsimhydro _1 precip + _2 ET)
        CalSimHydroEE run      (<- calsimhydro_ee _1 precip)
        DETAW / DCD run        (<- delta_channel_depletion _1 precip)
        Small Watersheds run   (<- small_watersheds _1 precip)

Tier 4  RIM QM + WATER-YEAR TYPES
        rim_inflow/_2_qmap_historical_validation.py
        water_year_types/_1_calc_WYTs.py --product A

Tier 5  POSTPROCESS EXTERNAL DSS + RESERVOIR/RECONSTRUCTION
        calsimhydro/_3_postprocess_product_a.py --sources all
        calsimhydro_ee/_2_postprocess_product_a.py
        delta_channel_depletion/_2_postprocess_product_a.py
        small_watersheds/_2_postprocess_product_a.py
        tulare_gw_terms/_1_wyt_monthlyavg.py
        evaporation/_2_run_reservoir_evap.py
        storage_curves/_1_wyt_index_curves.py -> _2_qmap_product_a.py
              -> _3_oroville_daily_precip.py -> _4_oroville_level5.py

Tier 6  OTHER TERMS
        instream_flows/_1_min_flow_feather.py ; _2_sjr_rest_req.py
        miscellaneous/_1_wyt_monthlyavg.py -> _2_DeltaAccretionForNDOI.py
              -> _3_hybrid_product_a.py -> _4_qmap_product_a.py
        upper_watershed/_1_wyt_monthlyavg.py -> _2_qmap_product_a.py
              -> _3_hybrid_product_a.py -> _4_pge_wy_allocation.py
              -> _5_dnp_evaporation.py
        closure_terms/_1_ct_calculation.py

Tier 7  FINAL COMPILATION
        postprocessing/sv_compile/product_a_historical_validation.py
        -> ProductA_Historical_Validation_SV.dss  (WY 1972-2018)
        (optional, post external CalSim run:
         postprocessing/calsim_runs/_productA_pickle_builder.py;
         postprocessing/calsim_runs/_productA_postproc.py)
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
- `<module>/reference/qmap_pairs.csv` -- QM target/predictor pairs
  (`target_part_b,target_part_c,predictor_part_b,predictor_part_c,lower_bound,upper_bound[,allow_negative]`).
- `mod_hydrology/rim_inflow/reference/CalSim3_VIC_name_mapping.csv`,
  `RimInflowAnchor.xlsx` -- rim QM pairing + anchor/tributary mass balance.
- `.github/copilot-instructions.md` -- per-module script tables (cross-checked
  against this runbook's tier ordering); also documents the script
  convention enforced by `tools/check_scripts.py`.

Quantile mapping is **deterministic / reproducible** (global `QMAP_SEED` in
`utils/quantile_mapping.py`); the full Product A pipeline is byte-identical
run-to-run on identical inputs.

---

## Tier 0 - Setup (reference data)

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| evaporation/_0 | `python _0_extract_reservoir_database.py --extract` | reservoir-parameter Excel workbook | `reference/reservoir_parameters.json` (95 reservoirs) | evaporation/_2 |
| miscellaneous/_0 | `python _0_extract_others.py` | CalSim baseline `__calsim_sv_default__.dss` | baseline "Other" monthly series (module reference) | miscellaneous/_1, _3, _4 |
| upper_watershed/_0 | `python _0_load_sv.py` | upper-watershed `*_SV.dss`; master inventory xlsx | `output/_0_load_sv/all_dss_paths*.csv`, `matched_dss_to_inventory.csv` | upper_watershed/_1.._5 |

## Tier 1 - Forcing (WGEN -> VIC -> rim inflows)

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| vic/_1 | `python _1_append_wind_wgen_hist.py` | WGEN `Product_A` met files; historical wind | wind-appended VIC forcing | [EXTERNAL] VIC model run |
| [EXTERNAL] VIC | manual VIC run outside this repo | wind-appended forcing | VIC flux files (RUNOFF + BASEFLOW) | vic/_2 |
| vic/_2 | `python _2_compile_rim_inflows.py` (`--product_b` for B) | VIC fluxes; grid weights | routed monthly rim inflows `CS3_*_qmo.csv` (+ DSS) | rim_inflow/_2, water_year_types/_1 |

## Tier 2 - Climate extraction

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| climate/_1 | `python _1_pp_point_locations.py --source Product_A --scenario 1` | WGEN met files; PP point reference | per-location monthly precip CSVs | climate/_2; downstream point-precip consumers |
| climate/_2 | `python _2_uhh_basin_averages.py --source Product_A --scenario 1` | WGEN met files; CS3 baseline DSS (historical UHH precip via `dss_io`); grid weights | basin-average precip/Tmax/Tmin/VPD + `_product_a_validation/` SV CSVs | calsimhydro/_1, _2; evaporation/_2; final compiler (`climate`) |

## Tier 3 - Model-input preparation

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| calsimhydro/_1 | `python _1_compile_precip.py --clip_period 1920-10-01 2018-09-30` | WGEN met files; WBA grid info | daily WBA precip CSVs | [EXTERNAL] CalSimHydro run |
| calsimhydro/_2 | `python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --n_workers 8` | VIC fluxes; WBA grid; CS3 RefETo DSS (QM target) | monthly QM'd ET CSVs per WBA (WY 1972-2018) | [EXTERNAL] CalSimHydro run |
| calsimhydro_ee/_1 | `python _1_compile_precip_EE.py` (`--Product_B` for B) | WGEN met files; East-Side grid info | daily East-Side precip CSVs | [EXTERNAL] CSHydroEE run |
| delta_channel_depletion/_1 | `python _1_compile_precip_DETAW.py` (`--Product_B` for B) | WGEN met files; DCD station list | daily DCD-station precip | [EXTERNAL] DETAW/DCD run |
| small_watersheds/_1 | `python _1_compile_precip_sws.py` (`--Product_B` for B) | WGEN met files; SWS station list | monthly SWS precip (in/mo) | [EXTERNAL] SWS run |

## Tier 3e - External model runs (not repo scripts)

| Run | Inputs | Outputs (scenario DSS) | Consumed by |
|---|---|---|---|
| [EXTERNAL] CalSimHydro | calsimhydro/_1 precip + calsimhydro/_2 ET | `CalSimHydro_Product_A/CS3L2015V0Hydro_SV.dss`; `.../RiceOutput.dss`; `Rebalance_Product_A/.../HydroRebalanceSJRdemands.dss` (+ Historical/VICPrecip/QMET) | calsimhydro/_3 |
| [EXTERNAL] CalSimHydroEE | calsimhydro_ee/_1 precip | `CalSimHydroEE_Product_A/CalSimHydroEE_DP_EA.dss` (+ Historical/VICPrecip/QMET) | calsimhydro_ee/_2 |
| [EXTERNAL] DETAW/DCD | delta_channel_depletion/_1 precip | `DCD_Calsim3_PlanningStudy[_ProductA]_1921-2018/.../CS3sv_DCD_PRISM_Dtrnd.dss` | delta_channel_depletion/_2 |
| [EXTERNAL] Small Watersheds | small_watersheds/_1 precip | SWS Product A DSS | small_watersheds/_2 |

## Tier 4 - Rim-inflow QM + water-year types

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| rim_inflow/_2 | `python _2_qmap_historical_validation.py` | VIC routed inflows (vic/_2); CS3 baseline DSS; `CalSim3_VIC_name_mapping.csv`; `RimInflowAnchor.xlsx` | `_riminflow_productA_1972_2018.csv` (+ TS/summary, figures) | water_year_types/_1; instream_flows; QM predictor for miscellaneous/_4, upper_watershed/_2, storage_curves/_2; final compiler |
| water_year_types/_1 | `python _1_calc_WYTs.py --product A` | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) | WYT indices under `_1_calc_WYTs/Product_A/` | tulare_gw_terms/_1; miscellaneous/_1; upper_watershed/_1 |

## Tier 5 - Postprocess external DSS + reservoir / reconstruction

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| calsimhydro/_3 | `python _3_postprocess_product_a.py` (`--sources cshydro,rebalance,rice`; `--skip-compare`; `--skip-validate`) | [EXTERNAL] CalSimHydro Product A scenario DSS; master inventory | merged-scenario + summary CSVs + `_product_a_validation/*.csv` | final compiler (`calsimhydro`) |
| calsimhydro_ee/_2 | `python _2_postprocess_product_a.py` | [EXTERNAL] CSHydroEE DSS; master inventory | `_cshydroEE_productA_1972_2018.csv` (+ merged/summary/boxplots) | final compiler (`calsimhydro_ee`) |
| delta_channel_depletion/_2 | `python _2_postprocess_product_a.py` | [EXTERNAL] DCD DSS; master inventory (CFS->TAF) | `_dcd_productA_1972_2018.csv` (+ merged/summary/boxplots) | final compiler (`delta_channel_depletion`) |
| small_watersheds/_2 | `python _2_postprocess_product_a.py` | [EXTERNAL] SWS DSS; master inventory | `_product_a_validation/*.csv` | final compiler (`small_watersheds`) |
| tulare_gw_terms/_1 | `python _1_wyt_monthlyavg.py` | WYT indices (water_year_types/_1) | `_1_wyt_monthlyavg/_product_a_validation/*.csv` | final compiler (`tulare_gw_terms`) |
| evaporation/_2 | `python _2_run_reservoir_evap.py` (all; `... FOLSM SHSTA` subset; `--Product_B` for B) | climate temps (climate/_2); `reservoir_parameters.json` (evaporation/_0) | per-reservoir monthly evap CSVs + `_product_a_validation/*.csv` | final compiler (`evaporation`) |
| storage_curves/_1.._4 | in order: `_1_wyt_index_curves.py`; `_2_qmap_product_a.py`; `_3_oroville_daily_precip.py`; `_4_oroville_level5.py` | CS3 baseline DSS; rim/precip; `reference/qmap_pairs.csv` | storage curves + `_product_a_validation/*.csv` | final compiler (`storage_curves`) |

## Tier 6 - Other terms

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| instream_flows/_1, _2 | `python _1_min_flow_feather.py`; `python _2_sjr_rest_req.py` | rim inflows (rim_inflow/_2) | `_product_a_validation/*.csv` (MINFLOWFEATHER; REST_REQ_NP/REST_REQ_P) | final compiler (`instream_flows`) |
| miscellaneous/_1.._4 | in order: `_1_wyt_monthlyavg.py`; `_2_DeltaAccretionForNDOI.py`; `_3_hybrid_product_a.py`; `_4_qmap_product_a.py` | miscellaneous/_0 baseline; WYT indices; rim_inflow/_2 rim CSV; `reference/qmap_pairs.csv` | `_product_a_validation/*.csv` (incl. `TULE_WET_INDX_productA_1972_2018.csv`); `_4_qmap_product_a/` detail + figures | final compiler (`miscellaneous`) |
| upper_watershed/_1.._5 | in order: `_1_wyt_monthlyavg.py`; `_2_qmap_product_a.py`; `_3_hybrid_product_a.py`; `_4_pge_wy_allocation.py`; `_5_dnp_evaporation.py` | upper_watershed/_0 SV reference; WYT indices; rim_inflow/_2 rim CSV; `reference/qmap_pairs.csv` | `_product_a_validation/*.csv` | final compiler (`upper_watershed`) |
| closure_terms/_1 | `python _1_ct_calculation.py` | upstream SV terms; WGEN-derived correlations | `_product_a_validation/*.csv` (closure-term reconciliation) | final compiler (closure category) |

## Tier 7 - Final compilation to DSS

| Script | Command | Inputs | Outputs | Consumed by |
|---|---|---|---|---|
| sv_compile (final) | `python product_a_historical_validation.py` (`--compute-stats`; `--stats-report`; `--no-term-plots`; `--summary-tables`) | every module's `_product_a_validation/*.csv`; CS3 baseline DSS; master inventory | `ProductA_Historical_Validation_SV.dss` (WY 1972-2018; overwrite window Oct 31 1971 - Sep 30 2018); diagnostic CSVs + per-category R2/NSE/trend figures | downstream CalSim 3.0 study |
| (optional) calsim_runs | `python _productA_pickle_builder.py`; `python _productA_postproc.py` | external CalSim 3.0 run results consuming `ProductA_Historical_Validation_SV.dss` | Product A run pickle cache + postprocessed comparison artifacts | analysis / reporting (not the input-generation pipeline) |

The final compiler auto-fills inventory "Constant/Rept" SVs from the
baseline 12-month repeat.
