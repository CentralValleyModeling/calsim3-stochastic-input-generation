# mod_hydrology/delta_channel_depletion

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/delta_channel_depletion/`  
Delta consumptive use and seepage (DCD/DETAW)
```


Delta Channel Depletion (DCD) represents consumptive use and seepage in the Sacramento-San Joaquin Delta. The model operates on a "planning study" configuration (as opposed to "historical study") to align with CalSim 3 DCR 2023. The two configurations differ in their assumptions. The planning study configuration assumes equilibrium groundwater and land use conditions appropriate for long-term planning, matching the DCR 2023 baseline. Using the historical configuration would inject year-specific calibration adjustments that are not reproducible from synthetic climate alone.

## Methodology

Temperature and precipitation data come directly from WGEN without additional processing. The DETAW component computes crop water demands from temperature and precipitation, which then feed into the DCD model to simulate agricultural water use, seepage, and return flows across Delta islands. The DCD version 2.1 was downloaded for this project, with key inputs including groundwater contribution rate (held constant at 0.4 for the planning study configuration), irrigation efficiency parameters, and land use classifications.

For each weather set, `_1_compile_precip_DETAW.py` compiles the station weather and `_1b_prepare_dcd_run.py` writes it, with the set's Sacramento Valley water year types, into a copy of the planning study run. DCD.py then runs DETAW and DCD, and `_1c_build_cs3sv_dss.py` writes the DSS file the postprocessors read. A Product B chunk runs through WY2021; land use and groundwater rates end in 2018, so its last three years repeat the 2018 values.

The master inventory requires 28 DCD variables, and the model writes 24 of them: irrigation, seepage and drainage at eight CalSim nodes. `_1c_build_cs3sv_dss.py` adds the deep percolation (DP_DELTA_DCD, DP_WBA50_DCD) and groundwater flow (GW_DELTA_DCD, GW_WBA50_DCD) of the Delta and of WBA 50. Each is the sum over the 168 islands of the island's flow times its share of that area. Mohammad Hasan at MSO provided the shares (`reference/WeightedRatiosForDCD.csv`); each island's Delta and WBA 50 shares add to 1.


## Results

The changes in Delta Channel Depletion (DCD) variables under the WGEN precipitation scenario relative to historical conditions are summarized in the following figure. The comparison highlights how reduced precipitation affects multiple hydrologic components, including drainage, deep percolation, groundwater flow, irrigation demand, and seepage throughout the Delta system.

```{figure} figures/s3-inputs_delta-channel-depletion-differences.png
:name: fig-dcd-differences
:width: 100%
Annual average difference from historical (TAF) for all 28 DCD variables, grouped by type: deep percolation flow (DP-FLOW), drainage (DRN), groundwater flow (GW-FLOW), irrigation (IRR), and seepage (SEEP). Percentage differences (purple, bottom) range from -8% to +10%. Drainage variables show the largest absolute differences, with DRN_SAC_SOUTH at -166 TAF and DP_DELTA_DCD at -101 TAF. Seepage variables are effectively unchanged (0%). All differences are driven by lower WGEN precipitation.
```


The maximum differences ranged from -166 TAF/yr to +6 TAF/yr across the suite of DCD variables. Percentage differences spanned -8% to +10%, with overall changes driven by lower WGEN precipitation relative to the historical baseline. The largest absolute difference (-166 TAF/yr) occurs in the deep percolation variable, reflecting the reduced precipitation available for recharge.

The differences across variable types are physically consistent. Drainage (DRN) variables tend to have larger negative differences, reflecting reduced surface runoff and subsurface drainage from lower precipitation. Groundwater and seepage flows show more modest changes, consistent with their deeper hydrologic pathways that buffer rapid precipitation changes. Irrigation variables track agricultural demands which depend on both precipitation (reducing demand when higher) and evapotranspiration (increasing demand when higher), producing a mixed signal.

Running DCD for Product B's 1,000-year simulation required careful attention to computational logistics. Each DCD run takes approximately 3 hours, and the Product B sequence is divided into 10 chunks of 100 water years. The DETAW climate compilation step prepares temperature and precipitation input files for each chunk before launching the DCD executable. Total processing time for the full Product B suite approached 30 hours, which places it among the more computationally intensive input generation modules alongside VIC.

An important DCD limitation emerged during testing: a DSS writing bug involving mixed string/numeric handling for certain Delta island identifiers (particularly WBA 73, which appears as both numeric 73 and string "73" in different contexts). This required a targeted fix in the post-processing scripts to ensure consistent data type handling when writing final DSS files.
