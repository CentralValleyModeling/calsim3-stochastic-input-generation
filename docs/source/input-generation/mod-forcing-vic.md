# mod_forcing/vic

```{admonition} Repository Module
:class: tip

**Module:** `mod_forcing/vic/`  
Append wind to WGEN, run VIC, compile rim inflows from VIC fluxes
```

The Variable Infiltration Capacity (VIC) model is a macroscale distributed hydrologic model that translates daily climate inputs (precipitation, temperature, wind speed) into gridded water and energy fluxes including evapotranspiration, runoff, and baseflow. VIC does not produce CalSim 3 state variables directly -- it does not appear in the input variable inventory -- but its flux outputs serve as the upstream basis for over 1,000 downstream variables through rim inflow quantile mapping (`mod_hydrology/rim_inflow/`), CalSimHydro ET quantile mapping (`mod_hydrology/calsimhydro/`), and water year type classification (`mod_hydrology/water_year_types/`).

## Wind Data Processing

WGEN generates daily precipitation and temperature but does not produce wind speed, which VIC requires as a forcing input. This gap is filled differently for each product:

- **Product A** (`_1_append_wind_wgen_hist.py`): Historical observed wind data (1915--2021) is appended directly to the WGEN meteorological files. Since Product A replicates the historical weather regime sequence, actual historical wind is the appropriate match.
- **Product B** (`_1_append_wind_wgen_stochastic.py`): Wind is resampled from historical records using the WGEN internal date mapping (`resampled.dates_Product_B_1000yr.csv`). Each synthetic day's wind comes from the historical day that WGEN sampled for that position, maintaining consistency between precipitation/temperature patterns and wind conditions.

Both scripts rename WGEN output files from `data_*` to `meteo_*` format and merge wind as an additional column alongside the existing precipitation, maximum temperature, and minimum temperature fields. The resulting files are the complete forcing inputs consumed by VIC.

## Rim Inflow Compilation

The `compile_rim_inflows` class (`_2_compile_rim_inflows.py`) aggregates VIC flux files into watershed-level streamflow time series that serve as the basis for downstream quantile mapping. For each grid cell in a watershed:

1. Daily runoff and baseflow fluxes are summed: $Q_{cell} = \text{RUNOFF} + \text{BASEFLOW}$
2. Cell contributions are weighted by the grid information ratio $f_2 / f_1$, accounting for partial cell coverage and area adjustments
3. Weighted cell flows are summed across the watershed and converted from mm to TAF

Product A uses standard `DatetimeIndex` (1915--2021), while Product B requires `PeriodIndex` (2025--3033) to handle 1,000-year sequences that exceed pandas Timestamp limits. The compiled watershed flows become the VIC basis series for quantile mapping in `mod_hydrology/rim_inflow/`.

VIC also produces ET-related flux outputs (EVAP, PET_H2OSURF, PET_SHORT) that are consumed by `mod_hydrology/calsimhydro/` for area-weighted ET quantile mapping to CalSim reference ET targets.
