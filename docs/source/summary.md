# Wrap-up

## Key Results

### Input Generation

## Key Findings

### VIC Model Bias

VIC-modeled flows show approximately 25-30% positive bias compared to CalSim 3 historical inputs. This substantial bias necessitates quantile mapping correction for all VIC-derived inputs. Without bias correction, direct use of VIC outputs would systematically overestimate water availability throughout the system.

The quantile mapping approach successfully corrects the distributional bias, achieving close alignment between the mapped values and CalSim 3 historical targets during the validation period. However, the need for such significant correction highlights the importance of careful calibration and validation in any stochastic generation framework.

### WGEN Wet Bias

The exclusion of pre-1948 data from the WGEN sampling pool creates a systematic wet bias in 100-year stochastic sequences. Because atmospheric circulation data from NCEP/NCAR Reanalysis 1 is only available from 1948 onward, the WGEN cannot sample from the Dust Bowl era (1930s) and other pre-1948 dry periods. As a result, the 1948-2018 sampling period is approximately centered within the stochastic distribution, while the full historical record including pre-1948 would be drier.

This finding has important implications for drought analysis. The stochastic sequences may underrepresent the frequency and severity of extreme dry periods that could plausibly occur. Users should be aware that the 1000-year ensemble does not include Dust Bowl-like conditions, which could affect conclusions about system performance during extreme droughts.

This bias is not spatially uniform. The WGEN tends to run wet in the Sacramento Valley and dry in Southern California, driven by the 1920--1950 period being exceptionally dry in the Sacramento basin relative to post-1948 conditions.

::::{tab-set}
:::{tab-item} Inflow (1915-2018)
![Oroville Inflow Comparison](figures/s2-methods_oroville-inflow-comparison.png)
*Oroville unimpaired inflow (VIC modeled, CS3_8RI_OROVI) rolling mean flows and 100-year mean annual distribution. CalSim 3 historical (black) and WGEN historical Product A (red) are compared against 10 synthetic Product B 1,000-year traces (gray) at 2-year, 10-year, and 30-year averaging windows. The 100-year box plot (lower right) shows the CalSim 3 mean (~4,350 TAF/yr, black dot) and WGEN historical mean (~4,800 TAF/yr, red dot) both fall below any of the n=10 100-year synthetic ensemble means.*
:::
:::{tab-item} Inflow (1948-2018)
![Oroville Streamflow 1948-2018](figures/s2-methods_oroville-streamflow-1948-2018.png)
*Mean annual Oroville unimpaired flow for 14 synthetic 70-year segments (gray box, IQR ~4,950--5,330 TAF/yr) compared to the WGEN historical 1948--2018 mean (~5,070 TAF/yr, red dot). When evaluated over the 70-year (1948-2018) historical period, the historical mean falls within the inner quartile of the synthetic distribution, showing that the WGEN does not have a wet bias relative to the historical data is was sampled from.*
:::
:::{tab-item} Precipitation
![Oroville Precipitation Comparison](figures/s2-methods_oroville-precip-comparison.png)
*Kernel density estimates of rolling mean annual precipitation over the Oroville watershed grids at 1-, 2-, 5-, and 10-year averaging windows. WGEN historical Product A (1915-2018) (red curve) is compared against all synthetic stochastic window traces (gray shading). The synthetic mean (gray dashed line) exceeds the historical mean (red dashed line) at all window lengths. The historical distribution is shifted drier and narrower, consistent with the post-1948 WGEN wet bias relative to the fuller 1915-2018 record.*
:::
::::

### ET Bias

ET bias is mainly propagated through CalSimHydro. VIC flux outputs (EVAP, PET_H2OSURF, PET_SHORT) are first quantile-mapped to CalSim historical ET targets, then the mapped ET is used as input to CalSimHydro alongside WGEN precipitation. The resulting bias reflects the combined effect of both the VIC model's ET estimation under synthetic climate and the quantile mapping transformation itself. Because quantile mapping corrects the distribution but not the rank ordering, shifts in the VIC ET distribution propagate through the mapping in ways that differ from a simple temperature-driven bias.

The net effect on CalSimHydro water budgets is substantial. Lower rangeland ET under quantile-mapped inputs leaves more water available for percolation, driving a +12% increase in deep percolation across all Water Budget Areas (~600 TAF/yr). Applied water increases +2% as irrigation compensates for higher potential ET. The ET change proved more influential than the WGEN precipitation change in driving CalSimHydro output differences, with approximately 300,000 acre-feet annual shift in the valley-wide water budget.


## Recommendations

Based on the findings from Phase I, the project team offers the following recommendations for planning for Phase II refinement and production runs.

### Update ET Methodology

The current VIC-based ET quantile mapping approach should continue for Phase I completion. MSO is developing an alternative evapotranspiration calculation method that coudld allow the stochastic input generation to bypass VIC entirely. This new methodology is expected to accompany the DCR 2025 release and may offer improvements in bias characteristics inherent in the current approach. The alternative ET methodology should be incorporated as a Phase II enhancement. 

### Address WGEN Bias

The WGEN wet bias from post-1948 sampling means the stochastic ensemble excludes Dust Bowl-era (1930s) conditions. Users conducting drought vulnerability analysis should recognize that the 1,000-year ensemble may underestimate the frequency of the most extreme droughts. The VIC positive bias of approximately 25–30% in rim inflows is corrected through quantile mapping but highlights the sensitivity of the generation framework to upstream model calibration. 

### Plan Phase II Scope

Preliminary scoping for Phase II should begin based on emerging findings from Phase I, particularly around model infeasibilities and operational rule modifications that may be needed for extreme stochastic sequences. Extended droughts and multi-year wet sequences may cause CalSim operational rules to behave in unexpected ways that require adjustment for realistic simulation.

Documentation of these issues during Phase I provides the foundation for Phase II planning. The Phase I report should clearly identify areas where model modifications may be beneficial, even if those modifications are beyond the current scope.

### DCR 2025 Transition

DCR 2025 includes several retired closure terms, which will simplify processing for those variables. The retirement of closure terms reduces the complexity of the stochastic generation framework and eliminates the need to maintain the weighted-average methodology for variables that no longer exist in the model. Additionally, DCR 2025 may incorporate updated reservoir sedimentation data, revised operational rules, and potentially the new ET methodology—each of which could affect stochastic input generation requirements.

When transitioning to DCR 2025, careful attention must be paid to ensuring proper alignment of module versions. CalSimHydro, External Elements (EE), Small Watersheds, Delta Channel Depletion (DCD), and the Delta Salinity Model (DSM) all need to be compatible with the DCR 2025 baseline. The integration testing phase of DCR 2025 deployment will need to verify that stochastic inputs work correctly with all updated modules.