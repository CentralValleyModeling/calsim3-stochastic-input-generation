# mod_hydrology/small_watersheds

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/small_watersheds/`  
Small tributary groundwater recharge processing
```


The Small Watersheds module generates groundwater recharge estimates for 210 small watershed areas throughout the Central Valley.

## Methodology

The Small Watersheds executable operates similarly to CalSimHydro water budget calculation. However, the module takes ET as a repeating 12-month seasonal pattern without interannual variation, meaning precipitation drives all year-to-year variability in results. Precipitation comes directly from WGEN data without bias correction or post-processing. The fixed ET pattern means results that differ from the CalSim historical baseline are purely precipitation-driven.

The model reads precipitation from a CSV with 1,602 columns representing spatial grid cells across the small watershed domains, where each column corresponds to a specific latitude-longitude precipitation point compiled from WGEN output. The precipitation compilation script aggregates WGEN precipitation data into a wide-format CSV that the executable consumes directly.

## Results

The analysis showed maximum differences ranging from -4 to +2 TAF/yr in absolute terms. Percentage differences ranged widely, from approximately -100% to +300%, though this reflects the small baseline values for many watersheds. The median absolute difference was less than 1 TAF/yr, with a median percentage difference of -13.5%. The scatter plot shows that smaller watersheds with lower baseline flow volumes have proportionally larger percentage differences, while larger watersheds cluster near the median. This behavior is expected since small absolute changes produce large percentage changes when the baseline is small. The differences across all watersheds are driven primarily by lower WGEN precipitation compared to the historical baseline. There is no VIC-derived ET bias to offset or amplify the precipitation signal, unlike CalSimHydro where ET and precipitation changes interact.

![Small Watersheds Distribution](figures/s3-inputs_small-watersheds-distribution.png)
*Percent difference (Precip vs Historical) plotted against historical groundwater recharge magnitude (TAF/yr) for all 210 small watersheds. Red dashed line marks the median at -13.5%. Larger watersheds (>10 TAF/yr) cluster tightly near the median; smaller watersheds scatter widely from -100% to +300%, where near-zero baseline values amplify even modest absolute differences.*
