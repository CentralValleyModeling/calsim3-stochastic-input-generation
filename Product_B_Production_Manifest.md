# Product B Production - Execution Runbook

> **Scope:** the Product B pipeline -- 1000-year stochastic CalSim 3.0
> input generation, delivered as **10 chunks of 100 water years** each
> (`ProductB_SV_n01.dss` .. `ProductB_SV_n10.dss`, canonical window
> Oct 1921 -- Sep 2021 per chunk; the first 9 months of each chunk are
> skipped so each chunk starts in October / water-year aligned).
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
> (a few have an additional `validation` / `calibrate` / `diagnostics`
> choice for non-product artifacts). There is no implicit default and no
> mode that runs both in one go. To switch to the Product A pipeline,
> re-invoke each command with `--product A`.
>
> **Tier structure mirrors `docs/source/input-generation/overview.md`:**
> Tier 1 Forcing -> Tier 2 Core Hydrology -> Tier 3 Water Year Types ->
> Tier 4 Dependent Modules -> Tier 5 Final Compilation. Within Tier 2,
> each external-run model is presented as a contiguous block:
> compile precip/ET -> [EXTERNAL] model run -> postprocess.
>
> **Per-script details** (CLI flags / methodology) live in each script's
> standardized header docstring. Convention is enforced by
> `utils/check_scripts.py` and CI.

---

## A. End-to-end ordering (quick reference)

```
Tier 1  FORCING (mod_forcing)
    VIC:
        python mod_forcing/vic/_1_append_wind_wgen_hist.py
        -> [EXTERNAL] VIC hydrologic model run
        python mod_forcing/vic/_2_compile_rim_inflows.py --product B
    Climate:
        python mod_forcing/climate/_1_pp_point_locations.py --source Product_B --scenario 1
        python mod_forcing/climate/_2_uhh_basin_averages.py --source Product_B --scenario 1

Tier 2  CORE HYDROLOGY (mod_hydrology)
    CalSimHydro:
        python mod_hydrology/calsimhydro/_1_compile_precip.py --product B
        python mod_hydrology/calsimhydro/_2_compile_et.py --product B --et_type all --vic_col_index 7 --write_dss
        -> [EXTERNAL] CalSimHydro model run (10 chunks)
        python mod_hydrology/calsimhydro/_4_postprocess_product_b.py
    CalSimHydroEE:
        python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product B
        -> [EXTERNAL] CalSimHydroEE model run (10 chunks)
        python mod_hydrology/calsimhydro_ee/_3_postprocess_product_b.py
    Rim Inflow:
        python mod_hydrology/rim_inflow/_3_qmap_productB.py
    Small Watersheds:
        python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product B
        -> [EXTERNAL] Small Watersheds model run (10 chunks)
        python mod_hydrology/small_watersheds/_3_postprocess_product_b.py
    Delta Channel Depletion:
        python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product B
        -> [EXTERNAL] DETAW/DCD model run (10 chunks)
        python mod_hydrology/delta_channel_depletion/_3_postprocess_product_b.py

Tier 3  WATER YEAR TYPES (mod_hydrology)
        python mod_hydrology/water_year_types/_1_calc_WYTs.py --product B

Tier 4  DEPENDENT MODULES
    Reservoir Evaporation:=
        python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product B
    Reservoir Storage Curves:
        python mod_reservoir/storage_curves/_2_qmap.py --product B
    Tulare Groundwater Terms:
        python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product B
    Instream Flows:
        python mod_other/instream_flows/_1_min_flow_feather.py --product B
        python mod_other/instream_flows/_2_sjr_rest_req.py --product B
    Upper Watershed Modules:
        python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product B
        python mod_other/upper_watershed/_2_qmap.py --product B
        python mod_other/upper_watershed/_3_hybrid.py --product B
        python mod_other/upper_watershed/_4_pge_wy_allocation.py --product B
        python mod_other/upper_watershed/_5_dnp_evaporation.py --product B
    Closure Terms:
        python mod_other/closure_terms/_1_ct_calculation.py --product B
    Day Volume Fractions:
        python mod_other/day_volume_fractions/_2_generate_product_b.py
    Other Variables (Miscellaneous):
        python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product B
        python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product B
        python mod_other/miscellaneous/_3_hybrid.py --product B
        python mod_other/miscellaneous/_4_qmap.py --product B

Tier 5  FINAL COMPILATION (postprocessing)
        python postprocessing/sv_compile/product_b_compilation.py
        -> ProductB_SV_n01.dss ... ProductB_SV_n10.dss  (10 x 100 WY)

        python postprocessing/calsim_runs/infeasibilities/n10.py
        -> ProductB_SV_n10_fixed.dss  (REQUIRED n10 cold-start fix: restores
           baseline SV values for months <= Oct 1921 so the first simulation
           timestep is feasible; preserves the Nov 1921 - Sep 2021 stochastic
           sequence. Use the _fixed file as the n10 input to CalSim. Re-run
           whenever ProductB_SV_n10.dss is recompiled. n10 is the only chunk
           with an SV-side fix; the others are addressed via WRESL model code.)

        Optional CLI flags:
          --chunks N [N ...]   Process specific chunks (default: all 10).
          --skip-comparison    Skip the Product A vs B comparison step.
          --skip-dss           Skip DSS file generation (CSV only).
          --summary-figures    Regenerate figures from a previous compare CSV.

        (optional, post external CalSim 3.0 run consuming the SV DSS files:
         python postprocessing/calsim_runs/_productB_pickle_builder.py
         python postprocessing/calsim_runs/_productB_postproc.py)
```

Final-compiler module scan order (authoritative -- `MODULE_CONFIG_B` in
`product_b_compilation.py:165-208`):
calsimhydro -> calsimhydro_ee -> evaporation -> rim_inflow ->
delta_channel_depletion -> small_watersheds -> storage_curves ->
instream_flows -> tulare_gw_terms -> climate -> miscellaneous ->
upper_watershed -> closure_terms -> day_volume_fractions.

Salinity has no Product B module: the final compiler auto-fills the 5
Salinity SVs from the CalSim baseline 12-month repeat via the Constant/
Rept pathway (`Constant_Rept = T` in the master inventory).

---

## B. Reference & config files

- `utils/paths.py` -- data-dir resolution (`config.json` overrides
  `config_default.json`; both git-ignored / tracked-default).
- `inventory/_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx`
  (`MASTER` sheet) -- authoritative SV inventory; drives postprocessor
  filtering and the final compiler's expected/missing/constant-rept
  accounting (shared with Product A).
- `<module>/reference/qmap_pairs.csv` -- QM target/predictor pairs
  (shared with Product A; same file drives both pipelines).
- `mod_hydrology/rim_inflow/reference/CalSim3_VIC_name_mapping.csv`,
  `RimInflowAnchor.xlsx` -- rim QM pairing + anchor/tributary mass
  balance (shared with Product A).
- `BASE/WGEN/resampled.dates_Product_B_1000yr.csv` -- WGEN day-to-history
  mapping consumed by closure_terms and day_volume_fractions.
- `.github/copilot-instructions.md` -- per-module script tables and the
  numbered-script convention enforced by `utils/check_scripts.py`.

Quantile mapping is **deterministic / reproducible** (global `QMAP_SEED`
in `utils/quantile_mapping.py`); the full Product B pipeline is
byte-identical run-to-run on identical inputs.

---

## Tier 1 - Forcing (mod_forcing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| vic/_1 | `python mod_forcing/vic/_1_append_wind_wgen_hist.py` | WGEN `Product_B` met files; historical wind | wind-appended VIC forcing |
| [EXTERNAL] VIC | manual VIC model run (10 chunks) | wind-appended forcing | VIC flux files (RUNOFF + BASEFLOW) per chunk |
| vic/_2 | `python mod_forcing/vic/_2_compile_rim_inflows.py --product B` | VIC fluxes; grid weights (incl. composite `CS3_8RI_SRBB_GridInfo.txt`) | routed monthly rim inflows `CS3_*_qmo_n{01..10}.csv` (+ DSS per chunk), incl. Bend Bridge `CS3_8RI_SRBB_qmo_n{01..10}.csv` (Shasta + above-SAC257 tributaries) |
| climate/_1 | `python mod_forcing/climate/_1_pp_point_locations.py --source Product_B --scenario 1` | WGEN met files; PP point reference | per-location monthly precip CSVs (per chunk) |
| climate/_2 | `python mod_forcing/climate/_2_uhh_basin_averages.py --source Product_B --scenario 1` | WGEN met files; CS3 baseline DSS (UHH precip); grid weights | basin-average precip/Tmax/Tmin/VPD + `_product_b_final/` SV CSVs |

---

## Tier 2 - Core Hydrology (mod_hydrology)

Each external-run model is a contiguous block: compile inputs ->
[EXTERNAL] model run (10 chunks) -> postprocess scenario DSS into per-
chunk CSVs under `_product_b_final/`.

### CalSimHydro (746 vars)

1. `python mod_hydrology/calsimhydro/_1_compile_precip.py --product B`
   - **Inputs:** WGEN met files; WBA grid info
   - **Outputs:** daily WBA precip CSVs per chunk
2. `python mod_hydrology/calsimhydro/_2_compile_et.py --product B --et_type all --vic_col_index 7 --write_dss --n_workers 8`
   - **Inputs:** VIC fluxes; WBA grid; CS3 RefETo DSS (QM target)
   - **Outputs:** monthly QM'd ET CSVs per WBA per chunk
3. **[EXTERNAL] CalSimHydro model run (10 chunks)** -- manual; consumes
   the precip + ET above.
   - **Outputs:** `CalSimHydro_Runs/CalSimHydro_Product_B/
     CS3L2015V0Hydro_SV_n{01..10}.DSS`, `RiceOutput_n{01..10}.DSS`,
     `CalSimHydro_Rebalance_Runs/Rebalance_Product_B/
     HydroRebalanceSJRdemands_n{01..10}.DSS`
4. `python mod_hydrology/calsimhydro/_4_postprocess_product_b.py`
   - Optional: `--sources cshydro rebalance rice`, `--chunks 1 2 3`,
     `--compare-a`, `--plot`
   - **Inputs:** external CalSimHydro Product B scenario DSS; master
     inventory
   - **Outputs:** per-chunk + summary CSVs +
     `output/_4_postprocess_product_b/_product_b_final/*.csv`

### CalSimHydroEE (17 vars)

1. `python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product B`
   - **Inputs:** WGEN met files; East-Side grid info
   - **Outputs:** daily East-Side precip CSVs per chunk
2. **[EXTERNAL] CalSimHydroEE model run (10 chunks)**
   - **Outputs:** `CalSimHydroEE_Runs/CalSimHydroEE_Product_B/
     CalSimHydroEE_DP_EA_n{01..10}.DSS`
3. `python mod_hydrology/calsimhydro_ee/_3_postprocess_product_b.py`
   - Optional: `--chunks 1 2 3`, `--compare-a`, `--plot`
   - **Inputs:** external CSHydroEE DSS; master inventory
   - **Outputs:** `_cshydroEE_productB_n{01..10}.csv`
     (+ merged/summary/boxplots) and `_product_b_final/*.csv`

### Rim Inflow (227 vars)

1. `python mod_hydrology/rim_inflow/_3_qmap_productB.py`
   - **Inputs:** VIC routed inflows (vic/_2); CS3 baseline DSS;
     `CalSim3_VIC_name_mapping.csv`; `RimInflowAnchor.xlsx`
   - **Outputs:** per-chunk QM'd rim inflows
     `output/_3_qmap_product_b/<PartB>_qmo_n{01..10}.csv` (consumed by
     several Tier 4 modules + the final compiler)

### Small Watersheds (210 vars)

1. `python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product B`
   - **Inputs:** WGEN met files; SWS station list
   - **Outputs:** monthly SWS precip per chunk (in/mo)
2. **[EXTERNAL] Small Watersheds model run (10 chunks)**
   - **Outputs:** `SmallWatersheds_Runs/SmallWatershed_Product_B/
     CVSWShed_FlowContribution3pcntWBA24_2013Init_2021_n{01..10}.DSS`
3. `python mod_hydrology/small_watersheds/_3_postprocess_product_b.py`
   - Optional: `--chunks 1 2 3`, `--compare-a`, `--plot`
   - **Inputs:** external SWS DSS; master inventory
   - **Outputs:** `_product_b_final/*.csv`

### Delta Channel Depletion (28 vars)

1. `python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product B`
   - **Inputs:** WGEN met files; DCD station list
   - **Outputs:** daily DCD-station precip per chunk
2. **[EXTERNAL] DETAW/DCD model run (10 chunks)**
   - **Outputs:** `DeltaChannelDepletion_Runs/
     DCD_Calsim3_PlanningStudy_Product_B/
     CS3sv_DCD_PRISM_Dtrnd_n{01..10}.DSS`
3. `python mod_hydrology/delta_channel_depletion/_3_postprocess_product_b.py`
   - Optional: `--chunks 1 2 3`, `--compare-a`, `--plot`
   - **Inputs:** external DCD DSS; master inventory (CFS->TAF)
   - **Outputs:** `_dcd_productB_n{01..10}.csv` and
     `_product_b_final/*.csv`

---

## Tier 3 - Water Year Types (mod_hydrology)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| water_year_types/_1 | `python mod_hydrology/water_year_types/_1_calc_WYTs.py --product B` | rim inflows (Sac: SRBB+OROV+YUBA+FOLS; SJ: ST+TU+ME+SJ) per chunk | WYT indices under `_1_calc_WYTs/Product_B/` (per chunk) |

---

## Tier 4 - Dependent Modules

### Reservoir Evaporation (95 vars)

1. `python mod_reservoir/evaporation/_0_extract_reservoir_database.py --extract` *(setup; run once when the parameter spreadsheet changes)*
   - **Inputs:** reservoir-parameter Excel workbook
   - **Outputs:** `reference/reservoir_parameters.json` (95 reservoirs)
2. `python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product B`
   - **Inputs:** climate temps (climate/_2 Product B); `reservoir_parameters.json`
   - **Outputs:** per-reservoir monthly evap CSVs per chunk +
     `_product_b_final/*.csv`

### Reservoir Storage Curves (7 vars)

1. `python mod_reservoir/storage_curves/_2_qmap.py --product B`
   - **Inputs:** CS3 baseline DSS; rim inflows (rim_inflow/_3); `reference/qmap_pairs.csv`
   - **Outputs:** intermediate detail CSVs in `_2_qmap/product_b/` +
     `_product_b_final/*.csv` per chunk

*Storage Curves `_1_wyt_index_curves.py`, `_3_oroville_daily_precip.py`,
and `_4_oroville_level5.py` are Product A-only diagnostic / calibration
tools and are not part of the Product B pipeline.*

### Tulare Groundwater Terms (14 vars)

1. `python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product B`
   - **Inputs:** WYT indices (water_year_types/_1 Product B)
   - **Outputs:** `_1_wyt_monthlyavg/_product_b_final/*.csv` per chunk

### Instream Flows (3 vars)

1. `python mod_other/instream_flows/_1_min_flow_feather.py --product B`
2. `python mod_other/instream_flows/_2_sjr_rest_req.py --product B`
- **Inputs:** rim inflows (rim_inflow/_3 Product B)
- **Outputs:** `_product_b_final/*.csv` (MINFLOWFEATHER;
  REST_REQ_NP/REST_REQ_P) per chunk
- *Optional diagnostic:* both scripts also accept `--product validation`
  for a 3-way historical-comparison artifact (not a Product A or B
  output).

### Upper Watershed Modules (12 vars)

1. `python mod_other/upper_watershed/_0_load_sv.py` *(setup; run once when upstream SV inventories change)*
   - **Inputs:** upper-watershed `*_SV.dss`; master inventory xlsx
   - **Outputs:** `output/_0_load_sv/all_dss_paths*.csv`, `matched_dss_to_inventory.csv`
2. `python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product B`
3. `python mod_other/upper_watershed/_2_qmap.py --product B`
4. `python mod_other/upper_watershed/_3_hybrid.py --product B`
5. `python mod_other/upper_watershed/_4_pge_wy_allocation.py --product B`
6. `python mod_other/upper_watershed/_5_dnp_evaporation.py --calibrate` *(setup; run once to derive the hypsographic polynomial)*
7. `python mod_other/upper_watershed/_5_dnp_evaporation.py --product B`
- **Inputs:** upper_watershed/_0 SV reference; WYT indices Product B;
  rim_inflow/_3 rim CSV; `reference/qmap_pairs.csv`
- **Outputs:** `_product_b_final/*.csv` per chunk

### Closure Terms (13 vars)

1. `python mod_other/closure_terms/_1_ct_calculation.py --product B`
   - **Inputs:** CalSim baseline DSS (Part C = CLOSURE-TERM);
     `BASE/WGEN/resampled.dates_Product_B_1000yr.csv`
   - **Outputs:** `_product_b_final/<TERM>_productB_n{01..10}.csv`
     (13 closure terms x 10 chunks)
- *Optional diagnostic:* `--diagnostics` runs the WGEN methodology
  analysis (weighted-mean vs 4-yr-block-stitched correlations, coverage
  boxplots, etc.); not a Product A or B output. Mutually exclusive with
  `--product B`.

### Day Volume Fractions (31 vars; Product B only)

1. `python mod_other/day_volume_fractions/_2_generate_product_b.py`
   - **Inputs:** CalSim baseline DSS (VOL-FRACTION); reference inflows;
     rim_inflow/_3 Product B chunks
   - **Outputs:** `_product_b_final/vol_fraction_productB_n{01..10}.csv`
     + WY-match diagnostics under `_2_generate_product_b/wy_matches_*.csv`

### Other Variables (Miscellaneous) (6 vars)

1. `python mod_other/miscellaneous/_0_extract_others.py` *(setup; run once when the CalSim baseline changes)*
   - **Inputs:** CalSim baseline `__calsim_sv_default__.dss`
   - **Outputs:** baseline "Other" monthly series (module reference)
2. `python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product B`
3. `python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product B`
4. `python mod_other/miscellaneous/_3_hybrid.py --product B`
5. `python mod_other/miscellaneous/_4_qmap.py --product B`
- **Inputs:** miscellaneous/_0 baseline; WYT indices Product B;
  rim_inflow/_3 rim CSV; `reference/qmap_pairs.csv`
- **Outputs:** `_product_b_final/*.csv` per chunk

### Salinity

No Product B module. The 5 Salinity SVs use repeating historical
patterns auto-filled by the final compiler from the CalSim baseline
12-month repeat (`Constant_Rept = T` in the master inventory).

---

## Tier 5 - Final Compilation (postprocessing)

| Script | Command | Inputs | Outputs |
|---|---|---|---|
| sv_compile (final) | `python postprocessing/sv_compile/product_b_compilation.py` (`--chunks N`; `--skip-comparison`; `--skip-dss`; `--summary-figures`) | every module's `_product_b_final/*.csv`; CS3 baseline DSS; master inventory; optional Product A compiled DSS for comparison | `ProductB_SV_n{01..10}.dss` (10 chunks; canonical window Oct 1921 - Sep 2021 / WY 1922-2021; first 9 months of each chunk skipped for water-year alignment); inventory cross-reference CSVs; `product_b_vs_a_comparison.csv` and `product_b_vs_calsim_base_comparison.csv` + per-category `figures/` |
| n10 cold-start fix | `python postprocessing/calsim_runs/infeasibilities/n10.py` | compiled `ProductB_SV_n10.dss`; CalSim baseline DSS | `ProductB_SV_n10_fixed.dss` -- baseline SV values restored for months <= Oct 1921, curing the n10 first-timestep LP infeasibility caused by an extreme cold-start stochastic draw (Cosumnes/Sacramento inflows 10-60x baseline at Oct 1921); Nov 1921 - Sep 2021 stochastic sequence preserved. **Required:** use `_n10_fixed.dss` (not the raw `_n10.dss`) as the n10 input to CalSim, and re-run this script whenever n10 is recompiled. Only n10 needs an SV-side fix; other chunks are handled by WRESL model-code changes. |
| (optional) calsim_runs | `python postprocessing/calsim_runs/_productB_pickle_builder.py`; `python postprocessing/calsim_runs/_productB_postproc.py` | external CalSim 3.0 run results consuming `ProductB_SV_n{01..10}.dss` | Product B run pickle cache (per-chunk values / diffs / units pkls) |

The final compiler auto-fills inventory "Constant/Rept" SVs from the
baseline 12-month repeat (same logic as the Product A compiler).
