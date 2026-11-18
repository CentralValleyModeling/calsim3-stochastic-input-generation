# Changelog

Each version covers the delivered input sets and the code that builds them, and gets a git tag at release.

## v1.1 (in progress)

As of 2026-11-17, every module, the external runs (CalSimHydro, CalSimHydroEE, Rebalance, DCD,
Small Watersheds) and the compiles are done for Historical_Unsplit and Product A. Product B
still needs its reference ET (steps 12 and 14, rerunning), pan evaporation, the external runs,
their postprocessors, the compile and a fix for the n10 infeasibility. The CalSim 3 runs come
last.

### Delivered sets

- Historical_Unsplit, the weather record without the temperature detrending, is a third
  delivered set. Scripts take `--product historical|A|B` (`utils.paths.WEATHER_SETS`);
  `mod_forcing/inflows` takes `--forcing`, and closure terms and day-volume fractions build
  Product B only.
- Historical_Unsplit and Product A cover WY1922-2018 (`utils.paths.DELIVERY_WY`), from the first
  water year of the CalSim 3 baseline. v1.0 delivered Product A over WY1972-2018.
- `utils/wgen.py` reads the weather of every set. Historical_Unsplit has precipitation 10 times
  too high on 289 grid-cell days (`mod_hydrology/rim_inflow/reference/prcp_x10_artifacts.csv`),
  which the reader divides by 10. Products A and B already carry a tenth of those values.
- Modules leave the delivery CSVs of Historical_Unsplit and Product A in
  `_historical_unsplit_validation/` and `_product_a_validation/`. `utils/check_outputs.py`
  checks them, and `postprocessing/sv_compile/single_series_compilation.py --product
  historical|A` compiles either set into one DSS.
- `_1_calc_WYTs.py` computes the water year types of a single series over WY1916-2018, starting
  from CDEC's WY1915 index. v1.0 started Product A at WY1972.

### Rim inflows from SAC-SMA

- `mod_forcing/inflows/` runs SAC-SMA dPL-CalSim at the commit `inflow_pin` names, and
  `mod_hydrology/rim_inflow/_1_build_rim_inflow.py` builds the rim-inflow SVs from its 196
  arcs. v1.0 quantile-mapped VIC flows onto CalSim 3.
- The arcs are SAC-SMA's product flow: its share model divides the flow of each multi-arc
  system among that system's arcs (139 of the 196). The builder corrects nothing further and
  sums the arcs into the UNIMP anchors. It quantile-maps five aliases (FOLSM_INFLOW,
  FOLSOM_INFLOW, I_MLRTN_IMP, I_MELON_FCST, I_EBTML) and the three arcs SAC-SMA does not
  simulate (I_SJR258, I_SJR265, I_TUO054) from a SAC-SMA series, fitting each map on CalSim 3
  over WY1950-2018. I_RUB002 is zero and I422 copies I_LOSVQ, as in CalSim 3.
  `mod_other/miscellaneous` builds I_JBP006 as a San Joaquin year-type average.
- UNIMP_SRBB is its 8 tributary arcs plus SAC-SMA's valley node, I_SRBB_VAL. v1.0 scaled the
  tributaries up to the whole of UNIMP_SRBB, though in CalSim 3 they carry 89% of it, so its
  Product A I_SHSTA runs 20% above CalSim 3 over WY1972-2018. The v1.0 data keep this error.
- Product B runs as one simulation in ten segments, each starting from the model state the one
  before ended with.
- The rim-inflow builder, the absorb fits and both compilers first check the run's manifest
  (`utils.paths.require_pinned_run`): the run must come from the configured model at its pin
  with no local changes, pass every gate, and have read the inputs the forcing check passed.
- v1.0 fitted its rim-inflow quantile maps on VIC's Product A run against CalSim 3's historical
  series. Product A's weather is detrended, so its early years are warmer than the record
  behind CalSim 3 and its runoff comes earlier. Maps fitted that way remove the warming response
  along with VIC's error: over WY1972-2018 the April-July share of v1.0's Sacramento four-river
  flow sits 2.1 points above CalSim 3's. v1.1 fits nothing on Product A, and we validate
  SAC-SMA against CalSim 3 on Historical_Unsplit weather.
- `_2_skill_evaluation.py` scores that run beside v1.0's VIC flows before their quantile maps.
  dPL-CalSim trains on WY1950-1975 and WY1986-2015 (`TRAIN_WY` at the pin). The median KGE of
  the 196 arcs is 0.81 on the held-out WY1976-1985 (VIC 0.58) and 0.75 on WY2016-2018 (VIC
  0.60). The Sacramento four-river sum runs 2.2% low on WY1976-1985, 5.3% high on WY2016-2018,
  and 14.1% low on WY1922-1949, where the weather record is least certain.
- Over WY1972-2018, v1.0's validation window, the Sacramento four-river sum runs 0.2% high
  against CalSim 3 and the San Joaquin sum 5.0% low. v1.0's method, refit on the same weather,
  gives 6.6% high and 9.2% low.
- Product A's detrending moves runoff earlier. Against Historical_Unsplit, the April-July share
  of its Sacramento four-river flow is 6.8 points lower in WY1922-1935 and 1.1 points lower in
  WY1991-2018.

### VIC as a second rim-inflow model

- With `inflow_model` set to `vic`, `mod_forcing/inflows/` runs VIC 4.2.d from v1.0's
  `VIC_Support_4.2.d` folder in `GENERATED_v1.0` under WSL, pinned by the sha256 of its binary,
  parameter and global files. Each arc is the area-weighted runoff plus baseflow of its grid
  cells, routed as in v1.0, with no quantile maps. The builder takes I_SJR258, I_SJR265 and
  I_TUO054 from VIC's arcs, and the absorb fits train on VIC's Historical_Unsplit run. v1.1
  delivers SAC-SMA.
- A VIC chain writes to its own GENERATED folder (`generated_dir`) and reads the config file
  that `CSSTOCHASTIC_CONFIG` names. `_2_skill_evaluation.py` stops on a VIC chain.
- I_SHSTA covers the Shasta drainage without Goose Lake, which v1.0's I_SHSTA included, and
  counts each cell on the drainage edge by its area inside it. UNIMP_SRBB's valley node takes
  the Bend Bridge valley floor from its own GridInfo, `CS3_I_SRBB_VAL_GridInfo.txt`.
- On sample cells the adapter repeats v1.0's VIC forcing for all three weather sets, and its
  Historical_Unsplit and Product A fluxes byte for byte. v1.0's Product B fluxes came from an
  earlier build of VIC: on 4 of 6 cells they drift from the pinned build's for a few days at a
  time, and runoff plus baseflow over the 1,000 years agrees within 0.003%.

### Second-stage quantile maps

- We fit each quantile map that reads a rim inflow, hybrids included, on WY1950-2018, with one
  fit for every set (`utils/qmap_fit.py`):
  - pass (CalSim 3 predictor to CalSim 3 target, applied to SAC-SMA): MAMMOTH_STORAGE,
    C_NFA048_SV, C_SFY007_SV, C_DER001_SV, C_MFY044_SV;
  - absorb (SAC-SMA predictor on Historical_Unsplit weather to CalSim 3 target): TULE_WET_INDX,
    C_CBD001HIST, C_KLR005HIST.
- New predictors: the 45 Folsom arcs for C_SFY007_SV, the four Deer Creek arcs for C_DER001_SV,
  and the two Middle Yuba arcs for C_MFY044_SV.

### Reference ET and pan evaporation

- CalSimHydro's reference ETo and crop ET come from the set's own weather: Hargreaves-Samani
  ETo, corrected per grid cell and month by factors (F1) fitted to Spatial CIMIS on
  Historical_Unsplit over 2004-2018, then crop ET from CUP+
  (`mod_forcing/climate/_3_refet_f1_factors.py`, `_4_refet_product_et.py`,
  `refet_cimis_adj.py`). v1.0 quantile-mapped VIC's ET fluxes onto CalSim 3's.
- One F1 table serves every set. `CS3_ET.dss` keeps CalSim 3's bare soil and urban ET
  climatologies, which do not depend on the weather.
- `mod_hydrology/calsimhydro/_2b_compile_pan_evap.py` builds Gerber pan evaporation from
  Hargreaves-Samani ETo at the eight Gerber cells, quantile-mapped onto the CalSim 3 pan record
  with one map fitted on Historical_Unsplit over WY1921-2018.

### Basin weather

- Basin, WBA and small-watershed averages weight a grid cell by its area inside the polygon.
  CalSimHydroEE areas and DCD stations take the simple mean of their cells. All go through one
  reader (`utils.wgen.weighted_daily`).
- The UHH VPD map of each basin is fitted once, on Historical_Unsplit temperature against
  CalSim 3 VPD over WY1922-2018, and applied to every set. v1.0 fitted a map per product, on
  the product's own temperature.

### Product B calendar

- WGEN's calendar has a leap year every fourth year, with no century exception. v1.0 dated its
  days from 2025-01-01 on the Gregorian calendar, so by chunk n10 about a quarter of the days
  carried the wrong month. `utils/wgen_calendar.py` gives every day its WGEN month, and every
  module that reads Product B weather takes its months from there.
- The v1.0 daily files of CalSimHydro, CalSimHydroEE and DETAW started each chunk a day early:
  WGEN's first year is a leap year, so its January-September has 274 days, not 273.
- Where a donor February and its target differ in length, the v1.0 day-volume fractions put
  fraction on days past the end of the month, in 394 of the 1,000 Februaries. v1.1 resamples
  the donor's real days onto the target's, and every month sums to 1.

### Delta Channel Depletion

- `_1b_prepare_dcd_run.py` writes a set's weather and Sacramento Valley water year types into a
  DETAW-DCD run folder, and `_1c_build_cs3sv_dss.py` builds `CS3sv_DCD_PRISM_Dtrnd.dss` from the
  finished run. They take the place of the aggregate and merge scripts and of
  `NOTES_To_Run_DCD_and_Outputs.txt`. DCD runs after the water year types.
- Every set runs on the planning study's land use, the same in every year, with its own water
  year types. A chunk of Product B runs through WY2021, so its run folder needs rows 2019-2021
  added to `GW_RATES_CALSIM3.TXT`.
- `_1_compile_precip_DETAW.py` writes `mm_pcp.csv` and `LODI_PT.csv`, the file names DETAW reads.

### Stops in place of stale output

- Product B scripts stop when an input is missing (a rim inflow, part of a summed predictor, a
  WGEN grid cell, a DNP evaporation chunk) or a WGEN file has the wrong number of days. In v1.0
  several of them printed a warning, skipped the item and exited with code 0, which could leave
  old output in place.
- Single-series quantile mapping stops on a pair it cannot map, and a failed VPD fit stops
  before any delivery file is written.
- Both compilers stop when an SV has two rows for one month, and unless the rim inflows come
  from the configured model at its pin. `product_b_compilation.py` stops on a module or chunk
  without CSVs unless given `--allow-missing`. Each compile clears `compiled_input_files/` and
  its figure folders.
- `utils.dss_io.open_dss` raises on a missing file unless the caller passes `create=True`;
  `HecDss.Open` would create an empty one. Its long-path junctions live in
  `%LOCALAPPDATA%\csstochastic\dss_links`, outside the repo.

### Code, data and config

- The postprocessors of a single series are `_N_postprocess_single.py --product historical|A`
  (v1.0: `_N_postprocess_product_a.py`), and `utils/qmap_single_from_pairs.py` drives their
  quantile maps. The Product B files of miscellaneous and upper_watershed carry the tag
  `productB`, as every other module's do.
- Removed: the VIC quantile-map scripts of `mod_hydrology/rim_inflow`,
  `utils/calculate_correlations_finder.py`, and CalSimHydro's `_2_compile_et.py` and
  `_0_compare_et_cshydro_vic.py`. The wind append and the routing of `mod_forcing/vic` moved
  into the VIC adapter, and the GridInfo basin weights to
  `mod_forcing/climate/reference/GridInfo/`.
- `GENERATED_v1.0` holds the v1.0 outputs, read-only (`utils.paths.get_archive_dir()`).
- `config.json` overrides `config_default.json` key by key, and a key the defaults lack stops
  the run. New keys: `archive_dir`, `generated_dir`, `inflow_model`, `inflow_repo`,
  `inflow_env`, `inflow_pin` (a commit of the model's git checkout, or the sha256 of its
  files). `CSSTOCHASTIC_CONFIG` names a config file to read in place of `config.json`.
- `environment.yml` adds geopandas, which reference ET step 0 imports.

### v1.0's VIC run on Historical_Unsplit weather

- v1.0 delivered nothing from this run, but it read the 289 x10 precipitation values as they
  were. We compare v1.0 with SAC-SMA on that weather, so we redid the run on the corrected
  values and rebuilt its rim inflows and v1.0's quantile-map validation from it.
  `GENERATED_v1.0` holds the results beside the originals (suffix `_x10fix`), with the script
  that made them in its `mod_forcing/vic/x10fix/` folder. `_2_skill_evaluation.py` and the v1.0
  numbers on Historical_Unsplit weather in this changelog use this run.

## v1.0 (2026-07-23)

- First release of Products A and B, with rim inflows and CalSimHydro ET from VIC,
  quantile-mapped to CalSim 3. See {doc}`summary`.
