# Product A Validation - Execution Runbook

> **Scope:** the Product A pipeline -- 1921-2018 historical-length split-sample
> quantile-mapping **validation** (train 1921-1971, simulate/validate
> 1972-2018). One continuous monthly time series per study variable (SV).
>
> **Standalone document.** Lives under `docs/` but is excluded from the Sphinx
> build (`docs/conf.py` `exclude_patterns`). Runbook only -- not a
> streamlining/design log or methodology paper.
>
> **Provenance:** built from code + docstring reading and targeted spot-runs.
> Data lives outside the repo (Box / OneDrive, git-ignored); every path below
> is **logical** -- resolve it through `utils/paths.py`
> (`get_base_dir()` = `<data_dir>/BASE`, `get_generated_dir()` =
> `<data_dir>/GENERATED`). Never hard-code the OneDrive path.

## How to read this runbook

- Steps are grouped by execution **Tier**. Run tiers in order. Within a tier,
  steps are independent unless a step's **Depends on** says otherwise.
- Every repo script is a **CLI** entry point: `conda activate csstochastic`,
  then `cd <Working dir>`, then run the **Command**. (There are no
  interactive/notebook-only scripts in the Product A path.)
- **Type:** `[CLI]` a repo command-line script; `[EXTERNAL]` a manual
  CalSimHydro / model run **outside this repo** (documented so the data chain
  is complete -- it is not a script here).
- **Methodology:** QM (quantile mapping) | WYT (water-year-type monthly
  average) | Hybrid `(QM+WYT)/2` | Direct (physical/threshold formula) |
  Date-stitch | N/A (extract / compile / precip-ET prep).

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

Final-compiler module scan order (`MODULE_CONFIG` OrderedDict in
`product_a_historical_validation.py`, authoritative): 1 calsimhydro -> 2
calsimhydro_ee -> 3 evaporation -> 4 rim_inflow -> 5 delta_channel_depletion
-> 6 small_watersheds -> 7 storage_curves -> 8 instream_flows -> 9
tulare_gw_terms -> 10 climate -> 11 miscellaneous -> 12 upper_watershed.

## B. Reference & config files

- `utils/paths.py` - data-dir resolution (`config.json` overrides
  `config_default.json`; both git-ignored / tracked-default).
- `inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`
  (`MASTER` sheet) - authoritative SV inventory; drives postprocessor
  filtering and the final compiler's expected/missing/constant-rept
  accounting.
- `<module>/reference/qmap_pairs.csv` - QM target/predictor pairs
  (`target_part_b,target_part_c,predictor_part_b,predictor_part_c,lower_bound,upper_bound[,allow_negative]`).
- `mod_hydrology/rim_inflow/reference/CalSim3_VIC_name_mapping.csv`,
  `RimInflowAnchor.xlsx` - rim QM pairing + anchor/tributary mass balance.
- `.github/copilot-instructions.md` - per-module script table (cross-checked
  against this runbook's tier ordering).

> Note on QM determinism: `utils/quantile_mapping.py::qmap_single` uses an
> unseeded `np.random.choice`, so QM-derived outputs vary run-to-run by
> design; skill metrics (R2/NSE/PBIAS) are stable.

---

## Tier 0 - Setup (reference data)

### evaporation/_0_extract_reservoir_database.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (extract) |
| Working dir | `mod_reservoir/evaporation` |
| Command | `python _0_extract_reservoir_database.py --extract` |
| CLI flags | `--extract` (re-extract from Excel; default reads existing JSON) |
| Inputs | reservoir-parameter Excel workbook |
| Outputs | `reference/reservoir_parameters.json` (95 reservoirs) |
| Consumed by | `evaporation/_2_run_reservoir_evap` |
| Depends on | - |
| Notes | Run once, or whenever the source Excel changes. |

### miscellaneous/_0_extract_others.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (extract) |
| Working dir | `mod_other/miscellaneous` |
| Command | `python _0_extract_others.py` |
| Inputs | CalSim baseline `__calsim_sv_default__.dss` |
| Outputs | baseline "Other" monthly series (module reference) |
| Consumed by | `miscellaneous/_1_wyt_monthlyavg`, `_3_hybrid`, `_4_qmap` |
| Depends on | - |

### upper_watershed/_0_load_sv.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (extract / inventory match) |
| Working dir | `mod_other/upper_watershed` |
| Command | `python _0_load_sv.py` |
| Inputs | upper-watershed module `*_SV.dss` files; master inventory xlsx |
| Outputs | `output/_0_load_sv/all_dss_paths*.csv`, `matched_dss_to_inventory.csv` |
| Consumed by | `upper_watershed/_1`.._5 (SV reference) |
| Depends on | - |

---

## Tier 1 - Forcing (WGEN -> VIC -> rim inflows)

### vic/_1_append_wind_wgen_hist.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (forcing prep) |
| Working dir | `mod_forcing/vic` |
| Command | `python _1_append_wind_wgen_hist.py` |
| Inputs | WGEN `Product_A` met files; historical wind (`Historical_Climate`) |
| Outputs | wind-appended VIC forcing under `GENERATED/.../input/Product_A/1/` |
| Consumed by | [EXTERNAL] VIC model run |
| Depends on | - |

### [EXTERNAL] VIC model run
| Field | Value |
|---|---|
| Type | `[EXTERNAL]` |
| Command | `MANUAL: run VIC with the wind-appended forcing` (outside this repo) |
| Inputs | `vic/_1_append_wind_wgen_hist` output |
| Outputs | VIC flux files (RUNOFF + BASEFLOW) |
| Consumed by | `vic/_2_compile_rim_inflows` |
| Depends on | `vic/_1_append_wind_wgen_hist` |

### vic/_2_compile_rim_inflows.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (routing) |
| Working dir | `mod_forcing/vic` |
| Command | `python _2_compile_rim_inflows.py` (Product A; `--product_b` for B) |
| CLI flags | `--product_b` |
| Inputs | VIC fluxes; grid weights |
| Outputs | routed monthly rim inflows `output/routed/Product_A/1/CS3_*_qmo.csv` (+ DSS) |
| Consumed by | `rim_inflow/_2`, `water_year_types/_1` |
| Depends on | [EXTERNAL] VIC run |

---

## Tier 2 - Climate extraction

### climate/_1_pp_point_locations.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (point precip) |
| Working dir | `mod_forcing/climate` |
| Command | `python _1_pp_point_locations.py --source Product_A --scenario 1` |
| CLI flags | `--source {Product_A,Product_B,Historical}`; `--scenario N`; `--locations` |
| Inputs | WGEN met files; PP point reference locations |
| Outputs | per-location monthly precip CSVs (`output/_1_pp_point_locations/Product_A/`) |
| Consumed by | `climate/_2`; downstream point-precip consumers |
| Depends on | Tier 1 forcing |

### climate/_2_uhh_basin_averages.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | QM (VPD quantile-mapped to CS3) + basin averaging |
| Working dir | `mod_forcing/climate` |
| Command | `python _2_uhh_basin_averages.py --source Product_A --scenario 1` |
| CLI flags | `--source {Product_A,Product_B}`; `--scenario N`; `--locations`; `--validate-outputs` |
| Inputs | WGEN met files; CS3 baseline `__calsim_sv_default__.dss` (historical UHH precip via `dss_io`); grid-info weights |
| Outputs | basin-average precip/Tmax/Tmin/VPD CSVs; `output/_product_a_validation/` SV CSVs |
| Consumed by | `calsimhydro/_1`+`_2`, `evaporation/_2`, final compiler (`climate`) |
| Depends on | `climate/_1`; Tier 1 forcing |

---

## Tier 3 - Model-input preparation (CalSimHydro / EE / DCD / SWS)

### calsimhydro/_1_compile_precip.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/calsimhydro` |
| Command | `python _1_compile_precip.py --clip_period 1920-10-01 2018-09-30` |
| CLI flags | `--grid_info_file`, `--met_path`, `--output_path`, `--Product_B`, `--start_date`, `--end_date`, `--clip_period <start> <end>`, `--wbas` |
| Inputs | WGEN met files; WBA grid info |
| Outputs | daily WBA precip CSVs (CalSimHydro model input) |
| Consumed by | Tier 3e [EXTERNAL] CalSimHydro run |
| Depends on | Tier 2 climate |

### calsimhydro/_2_compile_et.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | QM (area-weighted VIC ET quantile-mapped to CS3 monthly ET) |
| Working dir | `mod_hydrology/calsimhydro` |
| Command | `python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --n_workers 8` |
| CLI flags | `--et_type {RefET,CropET,PanEvap,all}`, `--vic_col_index`, `--write_dss`, `--Product_B`, `--n_workers`, `--cshydro_refet_dss`, `--cshydro_cropet_dss`, `--cshydro_panevap_dss` |
| Inputs | VIC flux files; WBA grid info; CS3 RefETo DSS (QM target) |
| Outputs | monthly QM'd ET CSVs per WBA (WY 1972-2018) under `output/_2_compile_et/Product_A/` |
| Consumed by | Tier 3e [EXTERNAL] CalSimHydro run (monthly ET constraint) |
| Depends on | Tier 2 climate; VIC fluxes (Tier 1 external VIC run) |

### calsimhydro_ee/_1_compile_precip_EE.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/calsimhydro_ee` |
| Command | `python _1_compile_precip_EE.py` (`--Product_B` for B) |
| CLI flags | `--grid_info_file`, `--met_path`, `--output_path`, `--Product_B` |
| Inputs | WGEN met files; East-Side grid info |
| Outputs | daily East-Side precip CSVs (CSHydroEE model input) |
| Consumed by | Tier 3e [EXTERNAL] CSHydroEE run |
| Depends on | Tier 2 climate |

### delta_channel_depletion/_1_compile_precip_DETAW.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/delta_channel_depletion` |
| Command | `python _1_compile_precip_DETAW.py` (`--Product_B` for B) |
| CLI flags | `--Product_B` |
| Inputs | WGEN met files; DCD station list |
| Outputs | daily DCD-station precip (DETAW input) |
| Consumed by | Tier 3e [EXTERNAL] DETAW/DCD run |
| Depends on | Tier 2 climate |

### small_watersheds/_1_compile_precip_sws.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/small_watersheds` |
| Command | `python _1_compile_precip_sws.py` (`--Product_B` for B) |
| CLI flags | `--Product_B` |
| Inputs | WGEN met files; SWS station list |
| Outputs | monthly SWS precip (in/mo) |
| Consumed by | Tier 3e [EXTERNAL] SWS run |
| Depends on | Tier 2 climate |

---

## Tier 3e - External model runs (not repo scripts)

### [EXTERNAL] CalSimHydro run
| Field | Value |
|---|---|
| Type | `[EXTERNAL]` |
| Command | `MANUAL: run CalSimHydro` (outside this repo) |
| Inputs | `calsimhydro/_1_compile_precip` precip CSVs **and** `calsimhydro/_2_compile_et` ET CSVs |
| Outputs (per `_3_postprocess_product_a.py` SOURCES) | `CalSimHydro_Runs/CalSimHydro_Product_A/CS3L2015V0Hydro_SV.dss`; `.../CalSimHydro_Product_A/RiceOutput.dss`; `CalSimHydro_Rebalance_Runs/Rebalance_Product_A/DSS/HydroRebalanceSJRdemands.dss` (plus Historical / VICPrecip / QMET comparison scenarios) |
| Consumed by | `calsimhydro/_3_postprocess_product_a` |
| Depends on | `calsimhydro/_1_compile_precip`, `calsimhydro/_2_compile_et` (and Tier 2 climate upstream) |

### [EXTERNAL] CalSimHydroEE run
| Field | Value |
|---|---|
| Type | `[EXTERNAL]` |
| Command | `MANUAL: run CalSimHydroEE` |
| Inputs | `calsimhydro_ee/_1_compile_precip_EE` precip CSVs |
| Outputs | `CalSimHydroEE_Runs/CalSimHydroEE_Product_A/CalSimHydroEE_DP_EA.dss` (+ Historical/VICPrecip/QMET) |
| Consumed by | `calsimhydro_ee/_2_postprocess_product_a` |
| Depends on | `calsimhydro_ee/_1_compile_precip_EE` |

### [EXTERNAL] DETAW / DCD run
| Field | Value |
|---|---|
| Type | `[EXTERNAL]` |
| Command | `MANUAL: run DETAW/DCD` |
| Inputs | `delta_channel_depletion/_1_compile_precip_DETAW` precip |
| Outputs | `DeltaChannelDepletion_Runs/DCD_Calsim3_PlanningStudy[_ProductA]_1921-2018/.../CS3sv_DCD_PRISM_Dtrnd.dss` |
| Consumed by | `delta_channel_depletion/_2_postprocess_product_a` |
| Depends on | `delta_channel_depletion/_1_compile_precip_DETAW` |

### [EXTERNAL] Small Watersheds run
| Field | Value |
|---|---|
| Type | `[EXTERNAL]` |
| Command | `MANUAL: run SWS model` |
| Inputs | `small_watersheds/_1_compile_precip_sws` precip |
| Outputs | SWS Product A DSS |
| Consumed by | `small_watersheds/_2_postprocess_product_a` |
| Depends on | `small_watersheds/_1_compile_precip_sws` |

---

## Tier 4 - Rim-inflow QM + water-year types

### rim_inflow/_2_qmap_historical_validation.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | QM (split-sample: train Oct 1921-Sep 1971, validate Oct 1971-Dec 2018) + anchor/tributary mass balance |
| Working dir | `mod_hydrology/rim_inflow` |
| Command | `python _2_qmap_historical_validation.py` |
| Inputs | VIC routed inflows (`vic/_2`); CS3 baseline DSS; `reference/CalSim3_VIC_name_mapping.csv`; `RimInflowAnchor.xlsx` |
| Outputs | `output/_2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv` (+ TS/summary CSVs, figures) |
| Consumed by | `water_year_types/_1`; `instream_flows/*`; QM-engine predictor for `miscellaneous/_4`, `upper_watershed/_2`, `storage_curves/_2`; final compiler (`rim_inflow`) |
| Depends on | `vic/_2_compile_rim_inflows` |

### water_year_types/_1_calc_WYTs.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | Direct (Sac 40-30-30, SJ 60-20-20 index logic) |
| Working dir | `mod_hydrology/water_year_types` |
| Command | `python _1_calc_WYTs.py --product A` |
| CLI flags | `--product {A,B,both}`; `--product_a_input/output`, `--product_b_input/output` |
| Inputs | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) |
| Outputs | WYT indices under `output/_1_calc_WYTs/Product_A/` |
| Consumed by | `tulare_gw_terms/_1`, `miscellaneous/_1`, `upper_watershed/_1` |
| Depends on | `rim_inflow/_2` |

---

## Tier 5 - Postprocess external DSS + reservoir / reconstruction

### calsimhydro/_3_postprocess_product_a.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + scenario comparison + validation CSV) |
| Working dir | `mod_hydrology/calsimhydro` |
| Command | `python _3_postprocess_product_a.py` (`--sources {cshydro,rebalance,rice}+`; `--skip-compare`; `--skip-validate`) |
| Inputs | [EXTERNAL] CalSimHydro Product A scenario DSS; master inventory xlsx |
| Outputs | merged-scenario + summary CSVs + boxplots; `output/_3_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`calsimhydro`) |
| Depends on | Tier 3e [EXTERNAL] CalSimHydro run |
| Notes | DSS read + long-path junction + validation conversion centralized via `utils/dss_io`+`utils/csv_io`. |

### calsimhydro_ee/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV) |
| Working dir | `mod_hydrology/calsimhydro_ee` |
| Command | `python _2_postprocess_product_a.py` |
| Inputs | [EXTERNAL] CSHydroEE Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/_cshydroEE_productA_1972_2018.csv` (+ merged/summary/boxplots) |
| Consumed by | final compiler (`calsimhydro_ee`) |
| Depends on | Tier 3e [EXTERNAL] CSHydroEE run |

### delta_channel_depletion/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV; CFS->TAF) |
| Working dir | `mod_hydrology/delta_channel_depletion` |
| Command | `python _2_postprocess_product_a.py` |
| Inputs | [EXTERNAL] DCD Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/_dcd_productA_1972_2018.csv` (+ merged/summary/boxplots) |
| Consumed by | final compiler (`delta_channel_depletion`) |
| Depends on | Tier 3e [EXTERNAL] DETAW/DCD run |

### small_watersheds/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV) |
| Working dir | `mod_hydrology/small_watersheds` |
| Command | `python _2_postprocess_product_a.py` |
| Inputs | [EXTERNAL] SWS Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`small_watersheds`) |
| Depends on | Tier 3e [EXTERNAL] SWS run |

### tulare_gw_terms/_1_wyt_monthlyavg.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | WYT (monthly average by water-year-type class) |
| Working dir | `mod_hydrology/tulare_gw_terms` |
| Command | `python _1_wyt_monthlyavg.py` |
| Inputs | WYT indices (`water_year_types/_1`) |
| Outputs | `output/_1_wyt_monthlyavg/_product_a_validation/*.csv` |
| Consumed by | final compiler (`tulare_gw_terms`) |
| Depends on | `water_year_types/_1` |

### evaporation/_2_run_reservoir_evap.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | Direct (Hargreaves-Samani; Oroville L5 storage-based) |
| Working dir | `mod_reservoir/evaporation` |
| Command | `python _2_run_reservoir_evap.py` (all); `... FOLSM SHSTA` (subset); `--Product_B` for B |
| CLI flags | `--Product_B`; positional 5-letter reservoir codes |
| Inputs | climate temps (`climate/_2`); `reference/reservoir_parameters.json` (`_0`) |
| Outputs | per-reservoir monthly evap CSVs + `output/_2_run_reservoir_evap/_product_a_validation/*.csv` |
| Consumed by | final compiler (`evaporation`) |
| Depends on | `climate/_2`; `evaporation/_0_extract_reservoir_database` |
| Notes | `_1_excel_to_python_validation.py` is an optional diagnostic (Python-vs-Excel check), not in the Product A data path. |

### storage_curves: _1_wyt_index_curves.py -> _2_qmap_product_a.py -> _3_oroville_daily_precip.py -> _4_oroville_level5.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | `_1` WYT baseline curves; `_2` QM (`reference/qmap_pairs.csv`); `_3`/`_4` Direct (Oroville L5 storage, DCR-2023 sedimentation) |
| Working dir | `mod_reservoir/storage_curves` |
| Command | in order: `python _1_wyt_index_curves.py`; `python _2_qmap_product_a.py`; `python _3_oroville_daily_precip.py`; `python _4_oroville_level5.py` |
| Inputs | CS3 baseline DSS; rim/precip; `reference/qmap_pairs.csv` |
| Outputs | storage curves + `output/_product_a_validation/*.csv` |
| Consumed by | final compiler (`storage_curves`) |
| Depends on | `rim_inflow/_2` (QM predictor); evaporation/precip |
| Notes | `_2_qmap_product_a.py` is a thin CLI driver over `utils/qmap_product_a_from_pairs`. |

---

## Tier 6 - Other terms (instream, misc, upper watershed, closure)

### instream_flows/_1_min_flow_feather.py ; _2_sjr_rest_req.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | Direct (threshold on annual Oroville flow; SJR restoration from UNIMP_SJ) |
| Working dir | `mod_other/instream_flows` |
| Command | `python _1_min_flow_feather.py`; `python _2_sjr_rest_req.py` |
| Inputs | rim inflows (`rim_inflow/_2`) |
| Outputs | `output/_product_a_validation/*.csv` (MINFLOWFEATHER; REST_REQ_NP/REST_REQ_P) |
| Consumed by | final compiler (`instream_flows`) |
| Depends on | `rim_inflow/_2` |

### miscellaneous: _1_wyt_monthlyavg -> _2_DeltaAccretionForNDOI -> _3_hybrid_product_a -> _4_qmap_product_a
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | `_1` WYT; `_2` Direct (precip x area x coeff); `_3` Hybrid `(QM+WYT)/2`; `_4` QM |
| Working dir | `mod_other/miscellaneous` |
| Command | in order: `python _1_wyt_monthlyavg.py`; `python _2_DeltaAccretionForNDOI.py`; `python _3_hybrid_product_a.py`; `python _4_qmap_product_a.py` |
| Inputs | `_0_extract_others` baseline; WYT indices; `rim_inflow/_2` rim CSV; `reference/qmap_pairs.csv` |
| Outputs | `output/_product_a_validation/*.csv` (incl. `TULE_WET_INDX_productA_1972_2018.csv`); `output/_4_qmap_product_a/` detail + figures |
| Consumed by | final compiler (`miscellaneous`) |
| Depends on | `miscellaneous/_0_extract_others`, `water_year_types/_1`, `rim_inflow/_2` |
| Notes | `_4_qmap_product_a.py` spot-run on local data: R2=0.703, NSE=0.520, PBIAS=5.0% (TULE_WET_INDX from I_PEDRO/INFLOW). `_3`/`_4` are thin CLI drivers over the WYT framework / `utils/qmap_product_a_from_pairs`. |

### upper_watershed: _1_wyt_monthlyavg -> _2_qmap_product_a -> _3_hybrid_product_a -> _4_pge_wy_allocation -> _5_dnp_evaporation
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | `_1` WYT; `_2` QM; `_3` Hybrid `(QM+WYT)/2`; `_4` Direct (threshold on annual Folsom flow); `_5` Direct (Don Pedro storage-based evap) |
| Working dir | `mod_other/upper_watershed` |
| Command | in order: `python _1_wyt_monthlyavg.py`; `python _2_qmap_product_a.py`; `python _3_hybrid_product_a.py`; `python _4_pge_wy_allocation.py`; `python _5_dnp_evaporation.py` |
| Inputs | `_0_load_sv` SV reference; WYT indices; `rim_inflow/_2` rim CSV; `reference/qmap_pairs.csv` |
| Outputs | `output/_product_a_validation/*.csv` |
| Consumed by | final compiler (`upper_watershed`) |
| Depends on | `upper_watershed/_0_load_sv`, `water_year_types/_1`, `rim_inflow/_2` |

### closure_terms/_1_ct_calculation.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | Direct (WGEN closure terms: weighted vs block-stitched, correlation-driven) |
| Working dir | `mod_other/closure_terms` |
| Command | `python _1_ct_calculation.py` |
| CLI flags | (see argparse in script) |
| Inputs | upstream SV terms; WGEN-derived correlations |
| Outputs | `output/_product_a_validation/*.csv` (closure-term reconciliation) |
| Consumed by | final compiler (closure category) |
| Depends on | the SV terms it reconciles (run after Tier 5-6 producers) |

---

## Tier 7 - Final compilation to DSS

### postprocessing/sv_compile/product_a_historical_validation.py
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (scan, overwrite-merge, validate) |
| Working dir | `postprocessing/sv_compile` |
| Command | `python product_a_historical_validation.py` (`--compute-stats`; `--stats-report`; `--no-term-plots`; `--summary-tables`) |
| Inputs | every module's `output/_product_a_validation/*.csv`; CS3 baseline `__calsim_sv_default__.dss`; master inventory xlsx |
| Module scan order (`MODULE_CONFIG`, authoritative) | calsimhydro -> calsimhydro_ee -> evaporation -> rim_inflow -> delta_channel_depletion -> small_watersheds -> storage_curves -> instream_flows -> tulare_gw_terms -> climate -> miscellaneous -> upper_watershed |
| Outputs | `GENERATED/postprocessing/sv_compile/product_a_validation/ProductA_Historical_Validation_SV.dss` (overwrite window Oct 31 1971 - Sep 30 2018); diagnostic CSVs + per-category R2/NSE/trend figures |
| Consumed by | downstream CalSim 3.0 study (final Product A SV DSS) |
| Depends on | all Tier 5-6 module `_product_a_validation/` outputs |
| Notes | Auto-fills inventory "Constant/Rept" SVs from the baseline 12-month repeat. Long-path junction primitives centralized via `utils/dss_io`. |

### (optional) postprocessing/calsim_runs - post external CalSim run
| Field | Value |
|---|---|
| Type | `[CLI]` |
| Methodology | N/A (pickle cache + postprocess) |
| Working dir | `postprocessing/calsim_runs` |
| Command | `python _productA_pickle_builder.py`; `python _productA_postproc.py` |
| Inputs | external CalSim 3.0 run results that consumed `ProductA_Historical_Validation_SV.dss` |
| Outputs | Product A CalSim-run pickle cache + postprocessed comparison artifacts |
| Consumed by | analysis / reporting (not the input-generation pipeline) |
| Depends on | an external CalSim 3.0 run (outside this repo) using the Tier 7 DSS |
