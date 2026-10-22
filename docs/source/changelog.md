# Changelog

Each version covers both delivered input sets and the code that builds them, and has a git tag.

## v1.2 (planned)

- A new CalSimHydro ET method replaces VIC potential ET, the last input still taken from VIC.

## v1.1 (in progress)

We are regenerating Products A and B. Before the tag come the Product B runs of CalSimHydro,
CalSimHydroEE, Small Watersheds and DETAW, the compile, the CalSim 3 runs, and new fixes for
the Product B infeasibilities (we derived the v1.0 fixes from VIC-based inputs).

### Rim inflows from SAC-SMA

- `mod_forcing/inflows/` runs SAC-SMA dPL-CalSim at the commit that `inflow_commit` pins, and
  `mod_hydrology/rim_inflow/_1_build_rim_inflow.py` builds the 241 rim-inflow SVs from its 196
  arcs.
- The arcs are SAC-SMA's product flow. Its share model divides the flow of each multi-arc
  system among its arcs (139 arcs, 107 of them under five anchors) in proportions fitted to
  CalSim 3, and keeps each system's water-year total. The builder corrects nothing further and
  sums the arcs into the UNIMP anchors, so every anchor keeps the model's water-year flow;
  the share model's timing step moves 0.6-1.6% of an anchor's volume between months. The
  builder quantile-maps five aliases (FOLSM_INFLOW, FOLSOM_INFLOW, I_MLRTN_IMP,
  I_MELON_FCST, I_EBTML) and the three arcs SAC-SMA does not simulate (I_SJR258, I_SJR265,
  I_TUO054) from a SAC-SMA series, fitting each map on CalSim 3 over WY1950-2018. I_RUB002 is
  zero and I422 copies I_LOSVQ, as in CalSim 3. `mod_other/miscellaneous` builds I_JBP006 as
  a San Joaquin year-type average.
- UNIMP_SRBB is its 8 tributary arcs plus SAC-SMA's valley node, I_SRBB_VAL. v1.0 scaled the
  tributaries up to the whole of UNIMP_SRBB, though in CalSim 3 they carry 88% of it, so I_SHSTA
  ran about 20% high in Product A and 23% high in Product B. The v1.0 data keep this error.
- Product B runs as one 1,000-year simulation in ten segments, each starting from the model
  state the one before ended with.
- Every script that reads model output first checks the run's manifest: the configured model
  at the pinned commit, a clean checkout, every gate passed, and the inputs the forcing check
  passed.
- v1.0 fitted its rim-inflow quantile maps on VIC's Product A run against CalSim 3's historical
  series. Product A's weather is detrended, so its early years are warmer than the record behind
  CalSim 3 and its runoff comes earlier. The maps took that warming response for VIC error and
  removed it: delivered Product A ran later than CalSim 3, with the Sacramento four's April-July
  share 2.1 points high. v1.1 fits nothing on Product A. We validate SAC-SMA against CalSim 3 on
  the historical (unsplit, not detrended) weather, and check Product A only for its response to
  the detrending.
- On historical weather over WY1972-2018, the Sacramento four-river sum runs 0.2% high against
  CalSim 3 and the San Joaquin sum 5.1% low. v1.0's method, refit on the same weather, gives
  6.6% high and 9.2% low. Under WGEN weather the April-July share of annual runoff falls 3-7
  points below CalSim 3's; in Product A about 2 points of that is the response to the
  detrending.

### Second-stage quantile maps

- We fit each quantile map that reads a rim inflow, hybrids included, on WY1950-2018, with one
  fit for both products:
  - pass (CalSim 3 predictor to CalSim 3 target, applied to SAC-SMA): MAMMOTH_STORAGE,
    C_NFA048_SV, C_SFY007_SV, C_DER001_SV, C_MFY044_SV;
  - absorb (SAC-SMA predictor on historical weather to CalSim 3 target): TULE_WET_INDX,
    C_CBD001HIST, C_KLR005HIST.
- New predictors: the 45 Folsom arcs for C_SFY007_SV, the four Deer Creek arcs for C_DER001_SV,
  and the two Middle Yuba arcs for C_MFY044_SV.

### Product B calendar

- WGEN's calendar has a leap year every fourth year, with no century exception. Nine v1.0
  scripts labelled its days from 2025-01-01 on the Gregorian calendar, so by chunk n10 about a
  quarter of the days carried the wrong month.
- `utils/wgen_calendar.py` now gives every day its WGEN month. The climate point and basin
  averages, CalSimHydro precipitation and ET, CalSimHydroEE, DETAW, Small Watersheds and
  reservoir evaporation all use it.
- The v1.0 daily files of CalSimHydro, CalSimHydroEE and DETAW started each chunk a day early:
  WGEN's first year is a leap year, so its January-September has 274 days, not 273.

### Missing inputs

- Product B scripts now stop with an error when an input is missing (a rim inflow, part of a
  summed predictor, a WGEN grid cell, a DNP evaporation chunk) or a WGEN file has the wrong
  number of days. In v1.0 several of them printed a warning, skipped the item and exited with
  code 0, which could leave old output in place.

### Code, data and config

- Removed `mod_forcing/vic`, the VIC rim-inflow scripts and
  `utils/calculate_correlations_finder.py`. The GridInfo basin weights moved to
  `mod_forcing/climate/reference/GridInfo/`.
- `GENERATED_v1.0` holds the v1.0 outputs, read-only (`utils.paths.get_archive_dir()`).
  CalSimHydro ET reads the VIC fluxes from there.
- `config.json` overrides `config_default.json` key by key. New keys: `archive_dir`,
  `inflow_model`, `inflow_repo`, `inflow_env`, `inflow_commit`.
- `Product_B_Production_Manifest.md` adds the forcing build and the storage-curve scripts
  `_1` to `_4`.

### v1.0's VIC run on historical weather

- The historical WGEN weather (unsplit, not detrended) has precipitation 10 times too high on
  289 grid-cell days, listed in `mod_hydrology/rim_inflow/reference/prcp_x10_artifacts.csv`.
  Products A and B carry a tenth of those values, and so does SAC-SMA's historical forcing, so
  no delivered input of v1.0 or v1.1 used them. The one run that did is v1.0's optional VIC run
  on the historical weather, in 236 VIC cells; v1.0 fitted and validated its maps on Product A.
- We compare v1.0 with SAC-SMA on that weather, so we redid the run for those cells on the
  corrected values and rebuilt its rim inflows and v1.0's quantile-map validation from it.
  `GENERATED_v1.0` holds the results beside the originals (suffix `_x10fix`), with the script
  that made them in `mod_forcing/vic/x10fix/`; the originals are unchanged.
  `_2_skill_evaluation.py` and the v1.0 numbers on historical weather in this changelog use
  this run.

## v1.0 (2026-07-23)

- First release of Products A and B, with rim inflows and CalSimHydro ET from VIC,
  quantile-mapped to CalSim 3. See {doc}`summary`.
