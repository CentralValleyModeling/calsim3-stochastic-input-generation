# CalSim 3 Stochastic

**Phase I Project Report**

_California Department of Water Resources_

_Prepared by Wyatt Arnold, Karandev Singh, Melika Mani, and Mehrdad Bastani_ 
_Division of Planning_

---

## Executive Summary

This report documents progress on the CalSim 3 Stochastic Input Generation project, a Phase I effort to enable California's primary water resources planning model to operate with synthetic hydroclimate scenarios. The project addresses a fundamental limitation of traditional planning approaches that rely solely on the approximately 100-year historical hydrologic record, which cannot capture the full range of plausible future conditions including extended droughts and multi-year wet sequences not yet observed.

The project leverages a Weather Generator (WGEN) product that produces 1,008 years of statistically plausible daily temperature and precipitation sequences through a Non-Homogeneous Hidden Markov Model (NHMM). This synthetic weather data drives the generation of all CalSim 3 input variables, enabling planners to evaluate water system performance across a much broader envelope of hydrologic conditions than previously possible.

The Phase I effort has achieved completion of all 15 major input categories spanning 1,732 CalSim variables. The rim inflows category, representing 206 variables of streamflow entering the model domain, achieves an average Nash-Sutcliffe Efficiency of 0.72 following quantile mapping with monthly mean adjustment, substantially improving upon the raw VIC baseline NSE of 0.03. Monthly bias was reduced by 50% at major watersheds. CalSimHydro processing for 768 water budget variables successfully reconstructs Sacramento Valley hydrology, though the analysis revealed a +12% deep percolation bias and -18% surface runoff bias requiring careful interpretation in model applications.

External Elements (17 variables), Small Watersheds (210 variables), and Delta Channel Depletion (28 variables) are all complete with documented baselines. The closure terms presented a unique challenge since they represent model error corrections with no direct physical basis. A novel weighted-average approach using WGEN sampling dates achieves mean correlation of 0.8 with historical values, providing a viable methodology for these 26 variables.

Reservoir evaporation calculations for 95 reservoirs are complete, with Python implementation validating exactly against original Excel calculations while reducing processing time from hours to seconds. The Hargreaves-Samani equation with monthly calibration factors provides robust evaporation estimates across the CalSim domain, showing slightly lower Product A values due to reduced daily temperature range in the synthetic climate.

Minimum instream flow requirements are now complete for both San Joaquin Restoration and Feather River using original agreement methodologies adapted to synthetic inputs. Reservoir storage curves for seven major facilities show excellent alignment at Trinity, Folsom, Don Pedro, and Shasta, with Oroville Level 5 successfully incorporating DCR 2023 sedimentation corrections through Water Control Manual wetness index algorithms. Mammoth Pool storage reconstruction achieved R² = 0.83 through quantile mapping from Millerton inflow.

Climate terms covering 56 forecast inputs are complete, with temperature-based quantile mapping successfully reconstructing vapor pressure deficit at R > 0.97 correlation. Tulare groundwater terms (14 variables) employ water year type averaging given low correlations with predictive variables, providing reasonable placeholder values as these terms represent conditions outside the primary CalSim domain.

Development of a hybrid quantile mapping approach combining QM with water year type averaging has proven particularly effective for terms with moderate correlation (R² 0.5-0.7). Applied to Colusa Basin Drain and Knights Landing Ridge Cut, the hybrid method improved R² by 0.08-0.14 points while eliminating unrealistic peak overshoots. The technique provides a middle ground between overly smooth WYT averaging and occasionally excessive QM extrapolation.

Upper watershed module analysis identified only 13 new terms requiring generation, with most module inputs already covered by the main inventory. Approaches span from direct calculation for forecast release terms to quantile mapping for hydrologic variables and storage-based methods for Don Pedro operations.

Day volume fractions, which disaggregate monthly CalSim values to daily timesteps, employ a bootstrap methodology matching synthetic years to historical patterns based on eight-river unimpaired flow plus an additional subset of flow terms that yield the best historical match over the 1921-1948 validation period.

The project ran a 46-year validation run (WY 1972-2018) using WGEN Product A inputs to verify CalSim behavior against the historical Baseline. This validation period matches the quantile mapping training window, providing consistent comparison.The project then executed ten independent 100-year stochastic sequences using WGEN Product B inputs, with each run initialized from consistent surface water and groundwater conditions to avoid unrealistic multi-century depletion trends. Final deliverables will support DCR 2027 analysis and establish robust stochastic planning capability for California's integrated water system.
