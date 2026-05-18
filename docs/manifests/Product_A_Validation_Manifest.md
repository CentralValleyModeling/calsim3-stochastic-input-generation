# Product A Validation - Execution Runbook

> **Scope:** the Product A pipeline -- 1921-2018 historical-length split-sample
> quantile-mapping **validation** (train 1921-1971, simulate/validate
> 1972-2018). One continuous monthly time series per study variable (SV).
>
> **Standalone document.** This file lives under `docs/` but is excluded from
> the Sphinx build (`docs/conf.py` `exclude_patterns`). It is a *runbook only*
> -- not a streamlining/design log and not a methodology paper.
>
> **Provenance:** built from code + docstring reading and targeted spot-runs.
> Data lives outside the repo (Box / OneDrive, git-ignored); every path below
> is **logical** -- resolve it through `utils/paths.py`
> (`get_base_dir()` = `<data_dir>/BASE`, `get_generated_dir()` =
> `<data_dir>/GENERATED`). Never hard-code the OneDrive path.

## How to read this runbook

- Steps are grouped by execution **Tier**. Run tiers in order. Within a tier,
  steps are independent unless a step's **Depends on** says otherwise.
- Run each script **from its own directory** in the `csstochastic` conda env:
  `conda activate csstochastic` then `cd <Working dir>` then the **Command**.
- **Status legend**
  - `[VERIFIED]` - spot-run end-to-end this effort (output produced + checked).
  - `[CODE-READ]` - documented from source/docstring; not run end-to-end here
    (needs external model runs and/or the full data set).
- **Type legend**
  - `[CLI]` - normal command-line script.
  - `[JUPYTER]` - `# %%` cell-style; run interactively (VS Code "Run All") --
    no argparse.
  - `[EXTERNAL]` - a manual CalSimHydro / model run **outside this repo**;
    not a script here. Inputs/outputs documented so the chain is complete.
- **Methodology** - QM (quantile mapping) | WYT (water-year-type monthly
  average) | Hybrid `(QM+WYT)/2` | Direct (physical/threshold formula) |
  Date-stitch | N/A (compile/extract/precip-prep).
- The final compiler (`postprocessing/sv_compile/product_a_historical_validation.py`)
  scans every module's `output/_product_a_validation/` directory; its
  authoritative scan order is in **Tier 6** and matches the `MODULE_CONFIG`
  `OrderedDict` in that script.

---

## Tier 0 - Forcing preparation (WGEN -> VIC -> rim inflows)

### vic/_1_append_wind_wgen_hist.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[JUPYTER]` |
| Methodology | N/A |
| Working dir | `mod_forcing/vic` |
| Command | Open in VS Code; **Run All** cells (no argparse) |
| Inputs | WGEN `Product_A` met files; historical wind |
| Outputs | wind-appended VIC forcing files (`BASE`/`GENERATED` VIC input) |
| Consumed by | external VIC model run (Tier 0e) |
| Depends on | - |
| Notes | Cell-style; prepares VIC forcing for the historical (Product A) span. |

### vic/_2_compile_rim_inflows.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (routing) |
| Working dir | `mod_forcing/vic` |
| Command | `python _2_compile_rim_inflows.py` (Product A; add `--product_b` for B) |
| Inputs | VIC fluxes (RUNOFF + BASEFLOW); grid weights |
| Outputs | routed monthly rim inflows under `output/routed/Product_A/1/` (+ DSS) |
| Consumed by | `rim_inflow/_2_qmap_historical_validation`, `water_year_types/_1` |
| Depends on | external VIC run fed by `_1_append_wind_wgen_hist` |
| Notes | `--product_b` flag selects the Product B span instead. |

### [EXTERNAL] CalSimHydro / Rebalance / Rice model runs
| Field | Value |
|---|---|
| Status | `[EXTERNAL]` |
| Type | `[EXTERNAL]` |
| Methodology | N/A |
| Command | `MANUAL: run CalSimHydro -> scenario DSS` (outside this repo) |
| Inputs | precip CSVs from Tier 2 (`calsimhydro/_1`, `calsimhydro_ee/_1`) |
| Outputs (Product A scenario DSS, per `_3_postprocess_product_a.py` SOURCES) | `CalSimHydro_Runs/CalSimHydro_Product_A/CS3L2015V0Hydro_SV.dss`; `CalSimHydro_Runs/CalSimHydro_Product_A/RiceOutput.dss`; `CalSimHydro_Rebalance_Runs/Rebalance_Product_A/DSS/HydroRebalanceSJRdemands.dss` (plus the Historical / VICPrecip / QMET comparison scenarios) |
| Consumed by | Tier 4 calsimhydro / calsimhydro_ee postprocessors |
| Depends on | Tier 2 precip compilation |
| Notes | Not a repo script. CalSimHydro is run in its own toolchain; the DSS files it writes are the inputs to the Tier 4 postprocessors. |

---

## Tier 1 - Climate extraction

### climate/_1_pp_point_locations.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (point precip extraction) |
| Working dir | `mod_forcing/climate` |
| Command | `python _1_pp_point_locations.py --source Product_A --scenario 1` |
| CLI flags | `--source {Product_A,Product_B,Historical}`; `--scenario N` |
| Inputs | WGEN met files; PP point reference locations (nearest VIC grid) |
| Outputs | per-location monthly precip CSVs under `output/_1_pp_point_locations/Product_A/` |
| Consumed by | downstream point-precip consumers; `climate/_2` |
| Depends on | Tier 0 forcing |

### climate/_2_uhh_basin_averages.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | QM (VPD quantile-mapped to CS3 baseline) + basin averaging |
| Working dir | `mod_forcing/climate` |
| Command | `python _2_uhh_basin_averages.py --source Product_A --scenario 1` |
| CLI flags | `--source {Product_A,Product_B}`; `--scenario N`; `--validate-outputs` |
| Inputs | WGEN met files; CS3 baseline `__calsim_sv_default__.dss` (historical UHH precip via `dss_io`); grid-info weights |
| Outputs | basin-average precip/Tmax/Tmin/VPD CSVs; `output/_product_a_validation/` SV CSVs |
| Consumed by | `mod_reservoir/evaporation`, final compiler (`climate` module) |
| Depends on | `climate/_1`; Tier 0 forcing |
| Notes | `--validate-outputs` runs the validation-CSV path. DSS read centralized via `utils/dss_io` (this effort); grid-weight/qmap logic unchanged. |

---

## Tier 2 - Hydrology precip compilation (CalSimHydro inputs)

### calsimhydro/_1_compile_precip.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/calsimhydro` |
| Command | `python _1_compile_precip.py --clip_period 1920-10-01 2018-09-30` |
| CLI flags | `--grid_info_file`, `--met_path`, `--output_path`, `--Product_B`, `--start_date`, `--end_date`, `--clip_period <start> <end>` |
| Inputs | WGEN met files; WBA grid info |
| Outputs | daily WBA precip CSVs (CalSimHydro model input) |
| Consumed by | [EXTERNAL] CalSimHydro run -> Tier 4 |
| Depends on | Tier 0 forcing |

### calsimhydro_ee/_1_compile_precip_EE.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/calsimhydro_ee` |
| Command | `python _1_compile_precip_EE.py` (add `--Product_B` for B) |
| CLI flags | `--grid_info_file`, `--met_path`, `--output_path`, `--Product_B` |
| Inputs | WGEN met files; East-Side grid info |
| Outputs | daily East-Side precip CSVs (CSHydroEE model input) |
| Consumed by | [EXTERNAL] CSHydroEE run -> Tier 4 |
| Depends on | Tier 0 forcing |

### delta_channel_depletion/_1_compile_precip_DETAW.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/delta_channel_depletion` |
| Command | `python _1_compile_precip_DETAW.py` (add `--Product_B` for B) |
| CLI flags | `--Product_B` |
| Inputs | WGEN met files; DCD station list |
| Outputs | daily DCD-station precip (DETAW input) |
| Consumed by | [EXTERNAL] DCD/DETAW run -> Tier 4 DCD postprocessor |
| Depends on | Tier 0 forcing |

### small_watersheds/_1_compile_precip_sws.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (precip prep) |
| Working dir | `mod_hydrology/small_watersheds` |
| Command | `python _1_compile_precip_sws.py` (add `--Product_B` for B) |
| CLI flags | `--Product_B` |
| Inputs | WGEN met files; SWS station list |
| Outputs | monthly SWS precip (in/mo) |
| Consumed by | [EXTERNAL] SWS run -> Tier 4 SWS postprocessor |
| Depends on | Tier 0 forcing |

---

## Tier 3 - Rim-inflow QM + water-year types

### rim_inflow/_2_qmap_historical_validation.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | QM (split-sample: train Oct 1921-Sep 1971, validate Oct 1971-Dec 2018) + anchor/tributary balance |
| Working dir | `mod_hydrology/rim_inflow` |
| Command | `python _2_qmap_historical_validation.py` (no argparse) |
| Inputs | VIC routed inflows (`vic/_2`); CS3 baseline DSS |
| Outputs | `output/_2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv` |
| Consumed by | `water_year_types/_1`; `instream_flows/*`; the QM-engine predictor for `miscellaneous/_4`, `upper_watershed/_2`, `storage_curves/_2`; final compiler (`rim_inflow`) |
| Depends on | `vic/_2_compile_rim_inflows` |
| Notes | Produces the Product A rim CSV that the QM driver (`utils/qmap_product_a_from_pairs`) reads as the simulation predictor. |

### water_year_types/_1_calc_WYTs.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | Direct (Sac 40-30-30, SJ 60-20-20 index logic) |
| Working dir | `mod_hydrology/water_year_types` |
| Command | `python _1_calc_WYTs.py --product A` |
| CLI flags | `--product {A,B,both}`; `--product_a_input/output`, `--product_b_input/output` |
| Inputs | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) |
| Outputs | WYT indices under `output/_1_calc_WYTs/Product_A/` |
| Consumed by | `tulare_gw_terms/_1`, `miscellaneous/_1`, `upper_watershed/_1` (WYT framework) |
| Depends on | `rim_inflow/_2` |

---

## Tier 4 - Postprocessing + reconstruction

### calsimhydro/_3_postprocess_product_a.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + scenario comparison + validation CSV) |
| Working dir | `mod_hydrology/calsimhydro` |
| Command | `python _3_postprocess_product_a.py` (everything); `--sources cshydro`; `--skip-compare`; `--skip-validate` |
| CLI flags | `--sources {cshydro,rebalance,rice}+`; `--skip-compare`; `--skip-validate` |
| Inputs | [EXTERNAL] Product A scenario DSS (see Tier 0e SOURCES); master inventory xlsx |
| Outputs | merged-scenario + summary CSVs + boxplots; `output/_3_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`calsimhydro`) |
| Depends on | Tier 0e external CalSimHydro/Rebalance/Rice runs |
| Notes | DSS read + long-path junction + validation conversion centralized via `utils/dss_io`+`utils/csv_io` (this effort); SOURCES / comparison / plots unchanged. |

### calsimhydro_ee/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV) |
| Working dir | `mod_hydrology/calsimhydro_ee` |
| Command | `python _2_postprocess_product_a.py` (standard postprocess flags) |
| Inputs | [EXTERNAL] CSHydroEE Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`calsimhydro_ee`) |
| Depends on | Tier 0e external CSHydroEE run |

### delta_channel_depletion/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV) |
| Working dir | `mod_hydrology/delta_channel_depletion` |
| Command | `python _2_postprocess_product_a.py` (standard postprocess flags) |
| Inputs | [EXTERNAL] DCD Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`delta_channel_depletion`) |
| Depends on | Tier 0e external DCD/DETAW run |

### small_watersheds/_2_postprocess_product_a.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (DSS extract + validation CSV) |
| Working dir | `mod_hydrology/small_watersheds` |
| Command | `python _2_postprocess_product_a.py` (standard postprocess flags) |
| Inputs | [EXTERNAL] SWS Product A DSS; master inventory xlsx |
| Outputs | `output/_2_postprocess_product_a/_product_a_validation/*.csv` |
| Consumed by | final compiler (`small_watersheds`) |
| Depends on | Tier 0e external SWS run |

### tulare_gw_terms/_1_wyt_monthlyavg.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | WYT (monthly average by water-year-type class) |
| Working dir | `mod_hydrology/tulare_gw_terms` |
| Command | `python _1_wyt_monthlyavg.py` (no argparse; configurable targets) |
| Inputs | WYT indices (`water_year_types/_1`) |
| Outputs | `output/_1_wyt_monthlyavg/_product_a_validation/*.csv` |
| Consumed by | final compiler (`tulare_gw_terms`) |
| Depends on | `water_year_types/_1` |

### evaporation/_2_run_reservoir_evap.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | Direct (Hargreaves-Samani; Oroville L5 storage-based) |
| Working dir | `mod_reservoir/evaporation` |
| Command | `python _2_run_reservoir_evap.py` (Product A, all); `... FOLSM SHSTA` (subset); `--Product_B` for B |
| CLI flags | `--Product_B`; positional reservoir codes (5-letter) |
| Inputs | climate temps (`climate/_2`); reservoir parameter DB (`_0_extract_reservoir_database`) |
| Outputs | per-reservoir monthly evap CSVs + `output/_2_run_reservoir_evap/_product_a_validation/*.csv` |
| Consumed by | final compiler (`evaporation`) |
| Depends on | `climate/_2`; `_0_extract_reservoir_database` (setup) |
| Notes | Independent tier in the dependency graph; no DSS I/O (engine `evaporation.py` left untouched). |

### storage_curves/_1_wyt_index_curves.py -> _2_qmap_product_a.py -> _3_oroville_daily_precip.py -> _4_oroville_level5.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | `_1` WYT baseline curves; `_2` QM (qmap_pairs.csv); `_3`/`_4` Direct (Oroville L5 storage, DCR-2023 sedimentation) |
| Working dir | `mod_reservoir/storage_curves` |
| Command | run in order: `python _1_wyt_index_curves.py`; `python _2_qmap_product_a.py`; `python _3_oroville_daily_precip.py`; `python _4_oroville_level5.py` |
| Inputs | CS3 baseline DSS; rim/precip; `reference/qmap_pairs.csv` |
| Outputs | storage curves + `output/_product_a_validation/*.csv` |
| Consumed by | final compiler (`storage_curves`) |
| Depends on | `rim_inflow/_2` (QM predictor); evaporation/precip |
| Notes | `_2_qmap_product_a.py` is a thin driver over `utils/qmap_product_a_from_pairs` (the QM engine refactored this effort). |

---

## Tier 5 - Other terms (instream, misc, upper watershed)

### instream_flows/_1_min_flow_feather.py / _2_sjr_rest_req.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | Direct (threshold logic on annual Oroville flow; SJR restoration from UNIMP_SJ) |
| Working dir | `mod_other/instream_flows` |
| Command | `python _1_min_flow_feather.py`; `python _2_sjr_rest_req.py` (no argparse) |
| Inputs | rim inflows (`rim_inflow/_2`) |
| Outputs | `output/_product_a_validation/*.csv` (MINFLOWFEATHER; REST_REQ_NP/REST_REQ_P) |
| Consumed by | final compiler (`instream_flows`) |
| Depends on | `rim_inflow/_2` |

### miscellaneous/_1_wyt_monthlyavg.py -> _2_DeltaAccretionForNDOI.py -> _3_hybrid_product_a.py -> _4_qmap_product_a.py
| Field | Value |
|---|---|
| Status | `_4` `[VERIFIED]` (spot-run end-to-end this effort); `_0/_1/_2/_3` `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | `_0` extract (setup); `_1` WYT; `_2` Direct (precip x area x coeff); `_3` Hybrid `(QM+WYT)/2`; `_4` QM |
| Working dir | `mod_other/miscellaneous` |
| Command | in order: `python _0_extract_others.py`; `python _1_wyt_monthlyavg.py`; `python _2_DeltaAccretionForNDOI.py`; `python _3_hybrid_product_a.py`; `python _4_qmap_product_a.py` |
| Inputs | CS3 baseline DSS; WYT indices; `rim_inflow/_2` Product A rim CSV; `reference/qmap_pairs.csv` |
| Outputs | `output/_product_a_validation/*.csv` (incl. `TULE_WET_INDX_productA_1972_2018.csv`); `output/_4_qmap_product_a/` detail + figures |
| Consumed by | final compiler (`miscellaneous`) |
| Depends on | `water_year_types/_1`, `rim_inflow/_2` |
| Verification | `_4_qmap_product_a.py` spot-run repeatedly on local data: R2=0.703, NSE=0.520, PBIAS=5.0% (TULE_WET_INDX from I_PEDRO/INFLOW). Note: QM output varies run-to-run by design (`qmap_single` uses unseeded `np.random.choice`); the metrics are stable. |
| Notes | `_3`/`_4` are thin drivers over the WYT framework / `utils/qmap_product_a_from_pairs` (QM engine refactored this effort). |

### upper_watershed/_1_wyt_monthlyavg.py -> _2_qmap_product_a.py -> _3_hybrid_product_a.py -> _4_pge_wy_allocation.py -> _5_dnp_evaporation.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | `_0` load (setup); `_1` WYT; `_2` QM; `_3` Hybrid `(QM+WYT)/2`; `_4` Direct (threshold on annual Folsom flow); `_5` Direct (Don Pedro storage-based evap) |
| Working dir | `mod_other/upper_watershed` |
| Command | in order: `python _0_load_sv.py`; `python _1_wyt_monthlyavg.py`; `python _2_qmap_product_a.py`; `python _3_hybrid_product_a.py`; `python _4_pge_wy_allocation.py`; `python _5_dnp_evaporation.py` |
| Inputs | CS3 baseline DSS; WYT indices; `rim_inflow/_2` Product A rim CSV; `reference/qmap_pairs.csv` |
| Outputs | `output/_product_a_validation/*.csv` |
| Consumed by | final compiler (`upper_watershed`) |
| Depends on | `water_year_types/_1`, `rim_inflow/_2` |
| Notes | `_2`/`_3` thin drivers over `utils/qmap_product_a_from_pairs` (QM engine refactored this effort). |

---

## Tier 6 - Final compilation to DSS

### postprocessing/sv_compile/product_a_historical_validation.py
| Field | Value |
|---|---|
| Status | `[CODE-READ]` |
| Type | `[CLI]` |
| Methodology | N/A (scan, overwrite-merge, validate) |
| Working dir | `postprocessing/sv_compile` |
| Command | `python product_a_historical_validation.py` (`--compute-stats`; `--stats-report`; `--no-term-plots`; `--summary-tables`) |
| CLI flags | `--compute-stats`, `--stats-report`, `--no-term-plots`, `--summary-tables` |
| Inputs | every module's `output/_product_a_validation/*.csv`; CS3 baseline `__calsim_sv_default__.dss`; master inventory xlsx |
| Module scan order (`MODULE_CONFIG`, authoritative) | 1 calsimhydro -> 2 calsimhydro_ee -> 3 evaporation -> 4 rim_inflow -> 5 delta_channel_depletion -> 6 small_watersheds -> 7 storage_curves -> 8 instream_flows -> 9 tulare_gw_terms -> 10 climate -> 11 miscellaneous -> 12 upper_watershed |
| Outputs | `GENERATED/postprocessing/sv_compile/product_a_validation/ProductA_Historical_Validation_SV.dss` (overwrite window Oct 31 1971 - Sep 30 2018); diagnostic CSVs + per-category R2/NSE/trend figures |
| Consumed by | downstream CalSim 3.0 study (final Product A SV DSS) |
| Depends on | all Tier 4-5 module `_product_a_validation/` outputs |
| Notes | Auto-fills inventory "Constant/Rept" SVs from the baseline 12-month repeat. Long-path junction primitives centralized via `utils/dss_io` (this effort); the single-persistent-junction architecture + all DSS-open sites unchanged. |

---

## Appendix A - End-to-end Product A ordering (condensed)

```
Tier 0  vic/_1_append_wind_wgen_hist [JUPYTER] -> vic/_2_compile_rim_inflows
        -> [EXTERNAL] CalSimHydro / Rebalance / Rice runs
Tier 1  climate/_1_pp_point_locations --source Product_A
        climate/_2_uhh_basin_averages --source Product_A
Tier 2  calsimhydro/_1_compile_precip --clip_period 1920-10-01 2018-09-30
        calsimhydro_ee/_1_compile_precip_EE
        delta_channel_depletion/_1_compile_precip_DETAW
        small_watersheds/_1_compile_precip_sws
Tier 3  rim_inflow/_2_qmap_historical_validation
        water_year_types/_1_calc_WYTs --product A
Tier 4  calsimhydro/_3_postprocess_product_a --sources all
        calsimhydro_ee/_2_postprocess_product_a
        delta_channel_depletion/_2_postprocess_product_a
        small_watersheds/_2_postprocess_product_a
        tulare_gw_terms/_1_wyt_monthlyavg
        evaporation/_2_run_reservoir_evap
        storage_curves/_1 -> _2_qmap_product_a -> _3 -> _4
Tier 5  instream_flows/_1_min_flow_feather ; _2_sjr_rest_req
        miscellaneous/_0 -> _1 -> _2 -> _3_hybrid_product_a -> _4_qmap_product_a
        upper_watershed/_0 -> _1 -> _2_qmap_product_a -> _3 -> _4 -> _5
Tier 6  postprocessing/sv_compile/product_a_historical_validation.py
        -> ProductA_Historical_Validation_SV.dss  (WY 1972-2018)
```

## Appendix B - Reference / config files

- `utils/paths.py` - data-dir resolution (`config.json` overrides
  `config_default.json`; both git-ignored / tracked-default).
- `<module>/reference/qmap_pairs.csv` - QM target/predictor pairs
  (`target_part_b,target_part_c,predictor_part_b,predictor_part_c,lower_bound,upper_bound[,allow_negative]`).
- `inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`
  (`MASTER` sheet) - SV inventory; drives postprocessor filtering and the
  final compiler's expected/missing/constant-rept accounting.
- `.github/copilot-instructions.md` - per-module script table (cross-checked
  against this runbook's tier ordering).
