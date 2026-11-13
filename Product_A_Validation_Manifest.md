# Historical_Unsplit and Product A Validation - Execution Runbook

> **Scope:** the pipeline of the two single series, Historical_Unsplit
> (`--product historical`, WGEN `Historical_Unsplit`) and Product A
> (`--product A`, WGEN `Product_A/1`). Each is delivered and compared with
> CalSim 3 over WY 1922-2018 (`utils.paths.DELIVERY_WY`; the CalSim 3 baseline
> starts in October 1921). A module whose run covers less (the CalSimHydro family
> runs on the span of its ET) delivers the water years it has, and the compiler
> lists those SVs in `paths_partial_window.csv`. The quantile maps are fitted on
> WY 1950-2018 (`utils/qmap_fit.py`). One continuous monthly time series per study
> variable (SV).
>
> **Standalone document** at the repo root. Not part of the Sphinx build.
>
> **Paths are logical.** Resolve them through `utils/paths.py`
> (`get_base_dir()` = `<data_dir>/BASE`, `get_module_generated_dir(...)` =
> `<data_dir>/GENERATED/<module>`). Data lives outside the repo and is
> git-ignored.
>
> **All commands run from the repo root.** The commands below are for Product A;
> run each again with `--product historical` for Historical_Unsplit, except the
> setup steps marked "run once". `--product` takes a key of
> `utils.paths.WEATHER_SETS` (`historical`, `A`, `B`) and has no default, and no
> script runs two sets in one call. The instream-flow scripts also take
> `validation`, and climate and the Oroville daily precip take `LTO`. Product B has
> its own runbook, `Product_B_Production_Manifest.md`.
>
> **Delivery files.** Each module writes its SVs for the compiler to
> `<module output>/_historical_unsplit_validation/*_historicalUnsplit_<first WY>_<last WY>.csv`
> or `<module output>/_product_a_validation/*_productA_<first WY>_<last WY>.csv`
> (`utils.csv_io.write_delivery_csv`, `utils.paths.delivery_dirs`).
> `python utils/check_outputs.py` checks their names, spans and duplicates, and that
> the two sets match file for file, before a compile.
>
> **Tier structure mirrors `docs/source/input-generation/overview.md`:**
> Tier 1 Forcing -> Tier 2 Core Hydrology -> Tier 3 Water Year Types ->
> Tier 4 Dependent Modules -> Tier 5 Final Compilation. Within Tier 2, each
> external-run model is presented as a contiguous block:
> compile precip/ET -> [EXTERNAL] model run -> postprocess.
>
> **Per-script details** (CLI flags / methodology) live in each script's
> standardized header docstring. Convention is enforced by
> `utils/check_scripts.py` and CI.

---

## A. End-to-end ordering (quick reference)

```
Tier 1  FORCING (mod_forcing)
    Rim-inflow model (config inflow_*; SAC-SMA, or VIC under WSL). The historical run is
    also the one the absorb fits of the second stage read, so build it first:
        python mod_forcing/inflows/_1_build_forcing.py --forcing historical --cells all
        python mod_forcing/inflows/_2_run_product.py --forcing historical
        python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product historical
        python mod_forcing/inflows/_1_build_forcing.py --forcing A --cells all
        python mod_forcing/inflows/_2_run_product.py --forcing A
    Climate:
        python mod_forcing/climate/_1_pp_point_locations.py --product A
        python mod_forcing/climate/_2_uhh_basin_averages.py --product A

Tier 2  CORE HYDROLOGY (mod_hydrology)
    CalSimHydro:
        python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30
        python mod_hydrology/calsimhydro/_2_compile_et.py --product A --et_type all --vic_col_index 7 --write_dss
        python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product A
        -> [EXTERNAL] CalSimHydro model run
        python mod_hydrology/calsimhydro/_3_postprocess_single.py --product A --sources cshydro rebalance rice
    CalSimHydroEE:
        python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A
        -> [EXTERNAL] CalSimHydroEE model run
        python mod_hydrology/calsimhydro_ee/_2_postprocess_single.py --product A
    Rim Inflow:
        python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product A
    Small Watersheds:
        python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A
        -> [EXTERNAL] Small Watersheds model run
        python mod_hydrology/small_watersheds/_2_postprocess_single.py --product A
    Delta Channel Depletion:
        python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A
        -> [EXTERNAL] DETAW/DCD model run
        python mod_hydrology/delta_channel_depletion/_2_postprocess_single.py --product A

Tier 3  WATER YEAR TYPES (mod_hydrology)
        python mod_hydrology/water_year_types/_1_calc_WYTs.py --product A

Tier 4  DEPENDENT MODULES
    Reservoir Evaporation:
        python mod_reservoir/evaporation/_0_extract_reservoir_database.py --extract   (setup; run once)
        python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A
    Reservoir Storage Curves:
        python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product A
        python mod_reservoir/storage_curves/_2_qmap.py --product A
        python mod_reservoir/storage_curves/_3_oroville_daily_precip.py --product A
        python mod_reservoir/storage_curves/_4_oroville_level5.py --product A
    Tulare Groundwater Terms:
        python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product A
    Instream Flows:
        python mod_other/instream_flows/_1_min_flow_feather.py --product A
        python mod_other/instream_flows/_2_sjr_rest_req.py --product A
    Upper Watershed Modules:
        python mod_other/upper_watershed/_0_load_sv.py                              (setup; run once)
        python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product A
        python mod_other/upper_watershed/_2_qmap.py --product A
        python mod_other/upper_watershed/_3_hybrid.py --product A
        python mod_other/upper_watershed/_4_pge_wy_allocation.py --product A
        python mod_other/upper_watershed/_5_dnp_evaporation.py --calibrate          (setup; run once)
        python mod_other/upper_watershed/_5_dnp_evaporation.py --product A
    Other Variables (Miscellaneous):
        python mod_other/miscellaneous/_0_extract_others.py                          (setup; run once)
        python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product A
        python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product A
        python mod_other/miscellaneous/_3_hybrid.py --product A
        python mod_other/miscellaneous/_4_qmap.py --product A

Tier 5  FINAL COMPILATION (postprocessing)
        python utils/check_outputs.py
        python postprocessing/sv_compile/single_series_compilation.py --product A
        -> product_a_validation/ProductA_Historical_Validation_SV.dss  (WY 1922-2018)
           (--product historical: historical_unsplit_validation/HistoricalUnsplit_Historical_Validation_SV.dss)

        (optional, post external CalSim 3.0 run consuming the SV DSS:
         python postprocessing/calsim_runs/_productA_pickle_builder.py
         python postprocessing/calsim_runs/_productA_postproc.py)
```

Final-compiler module scan order (authoritative: `utils.paths.DELIVERY_ROOTS`):
calsimhydro -> calsimhydro_ee -> evaporation -> rim_inflow ->
delta_channel_depletion -> small_watersheds -> storage_curves ->
instream_flows -> tulare_gw_terms -> climate -> miscellaneous ->
upper_watershed. An SV that two modules deliver stops the compile.

---

## B. Reference & config files

- `utils/paths.py` -- data-dir resolution (`config.json` overrides
  `config_default.json`; both git-ignored / tracked-default); the weather sets
  (`WEATHER_SETS`), the delivery folders and tags (`DELIVERY`, `DELIVERY_ROOTS`).
- `inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`
  (`MASTER` sheet) -- authoritative SV inventory; drives postprocessor
  filtering and the final compiler's expected/missing/constant-rept
  accounting.
- `<module>/reference/qmap_pairs.csv` -- QM target/predictor pairs.
- `mod_hydrology/rim_inflow/reference/CalSim3_VIC_name_mapping.csv`,
  `RimInflowAnchor.xlsx` -- rim QM pairing + anchor/tributary mass balance.
- `.github/copilot-instructions.md` -- per-module script tables and the
  numbered-script convention enforced by `utils/check_scripts.py`.

Quantile mapping is **deterministic / reproducible** (global `QMAP_SEED` in
`utils/quantile_mapping.py`); the pipeline is byte-identical run-to-run on
identical inputs.

---

## Tier 1 - Forcing (mod_forcing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| inflows/_1 | `python mod_forcing/inflows/_1_build_forcing.py --forcing A --cells all` | WGEN met files of the set (VIC: and the LTO wind) | the model's input where its folder does not hold it (VIC: a forcing file per cell) and its G2 check against BASE |
| inflows/_2 | `python mod_forcing/inflows/_2_run_product.py --forcing A` | the model at the pin; the inputs above | `arc_inflow_monthly.csv` (date, WY, month, arc, taf, kind) and `run_manifest.json` (with G1: the run repeats what the model tracks) |
| inflows, historical | `--forcing historical` for both, then `python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product historical` | as above, on Historical_Unsplit | the Historical_Unsplit rim inflows, which the absorb fits of every set read (`utils/qmap_fit.py`); they refuse a run from another pin |
| climate/_1 | `python mod_forcing/climate/_1_pp_point_locations.py --product A` | WGEN met files; PP point reference | per-location monthly precip CSVs + the set's `_pp_precip` delivery CSV |
| climate/_2 | `python mod_forcing/climate/_2_uhh_basin_averages.py --product A` | WGEN met files; CS3 baseline DSS (UHH precip); grid weights | basin-average precip/Tmax/Tmin/VPD + the set's `_uhh_*` delivery CSVs |

---

## Tier 2 - Core Hydrology (mod_hydrology)

Each external-run model is a contiguous block: compile inputs ->
[EXTERNAL] model run -> postprocess the set's run DSS into delivery CSVs. The
runs live in `<Model>_<set>` folders (`<set>`: `Historical_Unsplit`, `Product_A`).

### CalSimHydro (746 vars)

1. `python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30`
   - **Inputs:** WGEN met files; WBA grid info
   - **Outputs:** daily WBA precip CSVs under `_1_compile_precip/<set>/`
2. `python mod_hydrology/calsimhydro/_2_compile_et.py --product A --et_type all --vic_col_index 7 --write_dss --n_workers 8`
   - **Inputs:** VIC fluxes; WBA grid; CS3 RefETo DSS (QM target)
   - **Outputs:** monthly QM'd ET CSVs per WBA (WY 1972-2018). Product A only; the
     CIMIS-adjusted ET of `mod_forcing/climate/_3_refet_cimis_adj` (steps 5-14) covers
     1921-2018.
3. `python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product A`
   - **Inputs:** WGEN temperature
   - **Outputs:** Gerber pan evaporation per WBA
4. **[EXTERNAL] CalSimHydro model run** -- manual; consumes the precip + ET above.
   - **Outputs:** `CalSimHydro_<set>/CS3L2015V0Hydro_SV.dss`, `RiceOutput.dss`, `Rebalance_<set>/DSS/HydroRebalanceSJRdemands.dss` (+ the Historical/VICPrecip/QMET 1972-2018 comparison runs)
5. `python mod_hydrology/calsimhydro/_3_postprocess_single.py --product A --sources cshydro rebalance rice`
   - **Inputs:** the set's CalSimHydro and Rebalance DSS; master inventory
   - **Outputs:** merged-scenario + summary CSVs under `_3_postprocess_single/<set>/<source>/` + `_cshydro_<sv|rebalance|rice>_productA_<span>.csv`, the run's water years within WY 1922-2018

### CalSimHydroEE (17 vars)

1. `python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A`
   - **Inputs:** WGEN met files; East-Side grid info
   - **Outputs:** daily East-Side precip CSVs
2. **[EXTERNAL] CalSimHydroEE model run**
   - **Outputs:** `CalSimHydroEE_<set>/CalSimHydroEE_DP_EA.dss` (+ Historical/VICPrecip/QMET)
3. `python mod_hydrology/calsimhydro_ee/_2_postprocess_single.py --product A`
   - **Inputs:** the set's CSHydroEE DSS; master inventory
   - **Outputs:** `_cshydroEE_productA_<span>.csv`, the run's water years within WY 1922-2018 (+ merged/summary/boxplots under `_2_postprocess_single/<set>/`)

### Rim Inflow (227 vars)

1. `python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product A`
   - **Inputs:** the arc flows of inflows/_2 (only from a run at the pin); `CalSim3_inflow_mapping.csv`; CS3 baseline DSS (pass-through QM fits of the aliases)
   - **Outputs:** `_riminflow_productA_1922_2018.csv` and `calsim_qmap_validation_TS.csv` (WY 1916-2018, the whole model run)

### Small Watersheds (210 vars)

1. `python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A`
   - **Inputs:** WGEN met files; SWS station list
   - **Outputs:** monthly SWS precip (in/mo)
2. **[EXTERNAL] Small Watersheds model run**
   - **Outputs:** `SmallWatershed_<set>/CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss`
3. `python mod_hydrology/small_watersheds/_2_postprocess_single.py --product A`
   - **Inputs:** the set's SWS DSS; master inventory
   - **Outputs:** `_smallwatersheds_productA_1922_2018.csv` (+ merged/summary/boxplots under `_2_postprocess_single/<set>/`)

### Delta Channel Depletion (28 vars)

1. `python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A`
   - **Inputs:** WGEN met files; DCD station list
   - **Outputs:** daily DCD-station precip
2. **[EXTERNAL] DETAW/DCD model run**
   - **Outputs:** `DCD_Calsim3_PlanningStudy_<set>/DCD/Output/CALSIM3/CS3sv_DCD_PRISM_Dtrnd.dss`
3. `python mod_hydrology/delta_channel_depletion/_2_postprocess_single.py --product A`
   - **Inputs:** the set's DCD DSS; master inventory (CFS->TAF)
   - **Outputs:** `_dcd_productA_1922_2018.csv` (+ merged/summary/boxplots under `_2_postprocess_single/<set>/`)

---

## Tier 3 - Water Year Types (mod_hydrology)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| water_year_types/_1 | `python mod_hydrology/water_year_types/_1_calc_WYTs.py --product A` | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) | WYT indices under `_1_calc_WYTs/<set>/` |

---

## Tier 4 - Dependent Modules

### Reservoir Evaporation (95 vars)

1. `python mod_reservoir/evaporation/_0_extract_reservoir_database.py --extract` *(setup; run once when the parameter spreadsheet changes)*
   - **Inputs:** reservoir-parameter Excel workbook
   - **Outputs:** `reference/reservoir_parameters.json` (95 reservoirs)
2. `python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A`
   - **Inputs:** WGEN temperature of the set; `reservoir_parameters.json`
   - **Outputs:** per-reservoir monthly evap CSVs under `_2_run_reservoir_evap/<set>/` + `_reservoir_evaporation_productA_1922_2018.csv`

### Reservoir Storage Curves (7 vars)

1. `python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product A`
2. `python mod_reservoir/storage_curves/_2_qmap.py --product A`
3. `python mod_reservoir/storage_curves/_3_oroville_daily_precip.py --product A`
4. `python mod_reservoir/storage_curves/_4_oroville_level5.py --product A`
- **Inputs:** CS3 baseline DSS; rim/precip; `reference/qmap_pairs.csv`
- **Outputs:** storage curves (`_4_oroville_level5/<set>/`) + the set's delivery CSVs

### Tulare Groundwater Terms (14 vars)

1. `python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product A`
   - **Inputs:** WYT indices (water_year_types/_1)
   - **Outputs:** `_1_wyt_monthlyavg/_product_a_validation/*.csv`

### Instream Flows (3 vars)

1. `python mod_other/instream_flows/_1_min_flow_feather.py --product A`
2. `python mod_other/instream_flows/_2_sjr_rest_req.py --product A`
- **Inputs:** rim inflows of the set (`calsim_qmap_validation_TS.csv`)
- **Outputs:** the set's delivery CSVs (MINFLOWFEATHER; REST_REQ_NP/REST_REQ_P)
- *Optional diagnostic:* both scripts also accept `--product validation` for a 3-way historical-comparison artifact (no set's output).

### Upper Watershed Modules (12 vars)

1. `python mod_other/upper_watershed/_0_load_sv.py` *(setup; run once when upstream SV inventories change)*
   - **Inputs:** upper-watershed `*_SV.dss`; master inventory xlsx
   - **Outputs:** `output/_0_load_sv/all_dss_paths*.csv`, `matched_dss_to_inventory.csv`
2. `python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product A`
3. `python mod_other/upper_watershed/_2_qmap.py --product A`
4. `python mod_other/upper_watershed/_3_hybrid.py --product A`
5. `python mod_other/upper_watershed/_4_pge_wy_allocation.py --product A`
6. `python mod_other/upper_watershed/_5_dnp_evaporation.py --calibrate` *(setup; run once to derive the hypsographic polynomial)*
7. `python mod_other/upper_watershed/_5_dnp_evaporation.py --product A`
- **Inputs:** upper_watershed/_0 SV reference; WYT indices; the set's rim CSV; `reference/qmap_pairs.csv`; the set's S_PEDRO_SV (step 2) and ER_PEDRO (evaporation) for step 7
- **Outputs:** one delivery CSV per Part B, `<Part B>_productA_1922_2018.csv`

### Other Variables (Miscellaneous) (6 vars)

1. `python mod_other/miscellaneous/_0_extract_others.py` *(setup; run once when the CalSim baseline changes)*
   - **Inputs:** CalSim baseline `__calsim_sv_default__.dss`
   - **Outputs:** baseline "Other" monthly series (module reference)
2. `python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product A`
3. `python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product A`
4. `python mod_other/miscellaneous/_3_hybrid.py --product A`
5. `python mod_other/miscellaneous/_4_qmap.py --product A`
- **Inputs:** miscellaneous/_0 baseline; WYT indices; the set's rim CSV; `reference/qmap_pairs.csv`
- **Outputs:** one delivery CSV per Part B (incl. `TULE_WET_INDX_productA_1922_2018.csv`); `_4_qmap/<historical_unsplit|product_a>/` detail + figures

### Closure Terms, Day Volume Fractions, Salinity

No single-series scripts. Closure Terms and Day Volume Fractions are Product B
only; Closure Terms and Salinity use repeating historical patterns
auto-filled by the final compiler (Constant/Rept = T in the master
inventory). The closure-terms diagnostic mode
(`mod_other/closure_terms/_1_ct_calculation.py --diagnostics`) is a
non-product methodology analysis and emits no SV CSV.

---

## Tier 5 - Final Compilation (postprocessing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| delivery check | `python utils/check_outputs.py` (`--product historical` or `A` for one set) | every module's delivery folder of both sets | a report; exit 1 on a misnamed file, a span gap, a month twice, an SV from two modules, or a file without its twin in the other set |
| sv_compile (final) | `python postprocessing/sv_compile/single_series_compilation.py --product A` (`--compute-stats`; `--stats-report`; `--no-term-plots`; `--summary-tables`) | the set's delivery folders (`utils.paths.delivery_dirs`); CS3 baseline DSS; master inventory | `product_a_validation/ProductA_Historical_Validation_SV.dss` (`historical_unsplit_validation/HistoricalUnsplit_Historical_Validation_SV.dss`; WY 1922-2018; overwrite window Oct 31 1921 - Sep 30 2018); diagnostic CSVs (incl. `paths_partial_window.csv`) + per-category R2/NSE figures |
| (optional) calsim_runs | `python postprocessing/calsim_runs/_productA_pickle_builder.py`; `python postprocessing/calsim_runs/_productA_postproc.py` | external CalSim 3.0 run results consuming `ProductA_Historical_Validation_SV.dss` | Product A run pickle cache + postprocessed comparison artifacts |

The final compiler auto-fills inventory "Constant/Rept" SVs from the
baseline 12-month repeat.
