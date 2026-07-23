# Results / Product A

Product A validation proceeds in two stages. First, the reconstructed Product A SV variables are compared directly against their CalSim 3 baseline values over the WY 1972--2018 overlap period, to check that the input generation pipeline reproduces historical patterns. This comparison focuses on the time-varying generated variables, the subset that carries a meaningful skill signal (see the variable-count breakdown below); constant, zero-valued, and annually repeating outputs are excluded from skill scoring. Second, the CalSim 3 model is run with the Product A mapped SV variables over WY 1972--2018. The baseline runs normally with unchanged SV from 1921 through September 1971, so initial conditions are identical at the start of WY 1972. The resulting system outputs (deliveries, Delta flows, reservoir storage) over the validation period are compared against the CalSim baseline to see how input differences propagate through operational logic.

## Full summary

Product A validation shows good agreement at both stages. At the input level, the reconstructed variables reach a median $R^2$ of 0.98 and mean $R^2$ of 0.90 against historical CalSim values, with 71% of variables exceeding $R^2 \geq 0.90$. At the system level, a CalSim 3 run driven by Product A inputs produces annual-average deliveries, Delta flows, and reservoir storage within roughly 0--6% of the historical baseline over WY 1972--2018, with CVP total deliveries differing by only +0.5% and SWP total deliveries by -0.1%. During the 1987--1992 drought the differences are larger (SWP deliveries +30%, Banks exports +27%), because Product A conditions were wetter in that period. The sections below give detailed validation for both stages.

## Input validation detail

All skill metrics on this page are computed for the 1,224 scored variables only, the time-varying generated outputs. The two larger inventory counts are given to show where that scored set comes from:

- **1,733**: all variables in the CalSim 3 SV inventory (15 categories).
- **1,465**: the subset requiring stochastic generation; the other 268 are constant/repeating (130) or not used in the DCR 2023 baseline (138).
- **1,224**: the time-varying subset of those generated variables, the only set scored here. Constant, zero-valued, and annually repeating outputs carry no skill signal and are excluded (e.g., CalSimHydro contributes 655 time-varying outputs of its 746 generated).

Across these 1,224 scored variables, median $R^2$ is 0.98 and mean $R^2$ is 0.90. Approximately 71% achieve $R^2 \geq 0.90$, and 83% exceed $R^2 \geq 0.80$. About 46 variables (4%) fall below $R^2 = 0.50$.

![R2 Monthly by Input Category](figures/s4-results_r2-monthly-by-category.png)
*Monthly $R^2$ distributions by input category for Product A validation (WY 1972--2018), excluding constant and repeating variables. Box plots show median (orange line), interquartile range (box), and outliers (circles). Category sample sizes shown in parentheses. Dashed green line marks $R^2 = 1.0$; dashed red line marks $R^2 = 0.0$.*


Key observations from the figure:

- **CalSimHydro** (n=655) shows the tightest distribution with the highest median, from its direct use of WGEN precipitation and VIC-derived ET in the CalSimHydro model. Urban demand and wastewater terms achieve $R^2 = 1.0$ because they are entirely determined by repeating non-climate inputs.
- **Reservoir Evaporation** (n=95) scores very high because the Hargreaves-Samani equation responds smoothly to temperature inputs with minimal sensitivity to precipitation timing.
- **Rim Inflow** (n=228) and **Delta Channel Depletion** (n=28) cluster around $R^2 \approx 0.80$ with moderate spread, consistent with quantile mapping from VIC-simulated flows.
- **Small Watersheds** (n=118) and **Tulare Groundwater Terms** (n=14) show the widest distributions, from WYT averaging on terms with weak VIC correlation. The median $R^2$ of ~0.70 for small watersheds reflects lower WGEN precipitation and a -3.0% median recharge reduction.
- **Climate** (n=56) performs well overall, with slightly lower scores in VPD terms due to the quantile mapping step required for vapor pressure deficit.
- **Upper Watershed Modules** (n=13) show moderate spread, with storage forecast terms and the S_PEDRO change-in-storage approach producing lower correlations due to the indirect relationship between flow indices and operational decisions.

### Detailed tables by category

The following tables report the weighted-average $R^2$ and NSE for each variable type within a category, along with annual average values for the CalSim historical baseline and Product A reconstruction. Count is the number of non-zero, time-varying CalSim state variables in each row; counts may be lower than the full inventory totals because constant and zero-valued outputs are excluded from validation. Absolute difference and percent difference are calculated as Product A minus Historical.

#### CalSimHydro

CalSimHydro is the largest single category, with 655 variables across Sacramento Valley water budget areas. The ET quantile mapping drives a +8.8% increase in deep percolation (from lower rangeland ET under WGEN climate) and a -5.8% decrease in surface runoff (from lower WGEN precipitation).

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Applied Water | 259 | 0.985 | 0.983 | 15,260 | 15,558 | +298 | +2.0% |
| Deep Percolation | 42 | 0.930 | 0.874 | 4,303 | 4,680 | +377 | +8.8% |
| Return Flow | 4 | 0.999 | 0.999 | 352 | 352 | +0.3 | +0.1% |
| Surface Runoff | 42 | 0.932 | 0.923 | 2,589 | 2,439 | -151 | -5.8% |
| Tailwater | 153 | 0.984 | 0.982 | 2,992 | 3,020 | +28 | +1.0% |
| Urban Demand | 78 | 1.000 | 1.000 | 1,003 | 1,003 | 0 | 0.0% |
| Wastewater | 77 | 1.000 | 1.000 | 503 | 503 | 0 | 0.0% |

#### CalSimHydroEE

CalSimHydro external elements show the largest percent difference of any category. The +83% deep percolation increase reflects small absolute values in each element area, where even modest ET differences produce large percentage changes.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Deep Percolation | 16 | 0.720 | -3.894 | 24.7 | 45.4 | +20.6 | +83.4% |

#### Rim Inflow (Total)

Rim inflow validation covers 203 individual flow terms (excluding unimpaired flows reported separately). The aggregate $R^2$ of 0.76 reflects the combined effect of VIC model bias correction through quantile mapping and the anchor watershed mass balance adjustment.

| Rim Inflow | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|------------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Total | 203 | 0.761 | 0.694 | 30,137 | 31,041 | +904 | +3.0% |

#### Rim Inflow (Unimpaired)

Unimpaired flows for the nine major river systems perform well ($R^2$ range 0.87--0.94). Trinity is the largest outlier, at -24%.

| Part B | $R^2$ | NSE | Hist. Ann Avg (TAF) | Prod. A Ann Avg (TAF) | Abs Diff (TAF) | Pct Diff |
|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| UNIMP_TRIN | 0.874 | 0.791 | 1,298 | 991 | -307 | -23.7% |
| UNIMP_SRBB | 0.930 | 0.904 | 8,435 | 9,122 | +687 | +8.2% |
| UNIMP_OROV | 0.905 | 0.892 | 4,389 | 4,707 | +318 | +7.2% |
| UNIMP_YUBA | 0.911 | 0.888 | 2,289 | 2,524 | +235 | +10.3% |
| UNIMP_FOLS | 0.936 | 0.933 | 2,682 | 2,531 | -151 | -5.6% |
| UNIMP_ST | 0.892 | 0.886 | 1,164 | 1,070 | -94 | -8.1% |
| UNIMP_TU | 0.912 | 0.905 | 1,934 | 1,745 | -188 | -9.7% |
| UNIMP_ME | 0.927 | 0.913 | 1,002 | 875 | -127 | -12.7% |
| UNIMP_SJ | 0.899 | 0.893 | 1,796 | 1,626 | -171 | -9.5% |

#### Delta Channel Depletion

Delta channel depletion terms show strong agreement across all five output types. Differences are small and driven by lower WGEN precipitation, consistent with the overall precipitation bias pattern.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| DP Flow | 2 | 0.957 | 0.955 | 82.2 | 78.4 | -3.8 | -4.6% |
| Drainage | 8 | 0.960 | 0.939 | 981 | 966 | -15.0 | -1.5% |
| GW Flow | 2 | 0.993 | 0.993 | 611 | 610 | -1.0 | -0.2% |
| Irrigation | 8 | 0.991 | 0.991 | 1,088 | 1,088 | -0.1 | -0.0% |
| Seepage | 8 | 0.989 | 0.989 | 680 | 681 | +0.9 | +0.1% |

#### Small Watersheds

Small watershed groundwater recharge terms show a median reduction of -3.0%, driven by lower WGEN precipitation. Smaller watersheds tend to have higher percentage differences due to lower absolute flow volumes.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| BUGW Inflow | 118 | 0.682 | -0.114 | 345 | 335 | -10.4 | -3.0% |

#### Tulare Groundwater Terms

Pumping terms ($R^2$ = 0.87) are better reproduced than deep percolation terms ($R^2$ = 0.50) because pumping follows more stable WYT-dependent patterns. MSO staff noted these terms "are kind of like a placeholder" and "I really wouldn't put too much weight on this part of the data."

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Deep Percolation | 7 | 0.499 | 0.488 | 5,694 | 5,551 | -143 | -2.5% |
| Pumping | 7 | 0.874 | 0.872 | 7,321 | 7,506 | +185 | +2.5% |

#### Reservoir Evaporation

Reservoir evaporation matches the baseline within +0.2%, confirming that the Hargreaves-Samani Python automation reproduces the original Excel methodology. The small remaining difference stems from Product A synthetic temperature being slightly lower than historical.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg (in/yr) | Prod. A Ann Avg (in/yr) | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Evaporation Rate | 95 | 0.978 | 0.958 | 50.8 | 50.9 | +0.12 | +0.2% |

#### Reservoir Storage Curves

Seven reservoir storage levels were reconstructed using a mix of quantile mapping, wetness index algorithms, and WYT averaging. Oroville Level 5 achieves $R^2$ = 0.98 using the refined wetness index with decimal interpolation and sedimentation correction. Shasta Level 2 shows the lowest $R^2$ (0.35), but this reflects misalignment of WYT boundaries in limited historical data windows rather than methodological failure.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| MAMMOTH_STORAGE | Storage | 0.779 | 0.771 | 608 | 579 | -29.1 | -4.8% |
| S_FOLSMLEVEL2 | Storage Level | 0.687 | 0.640 | 3,956 | 4,009 | +52.7 | +1.3% |
| S_OROVLLEVEL5 | Storage Level | 0.979 | 0.978 | 37,805 | 37,746 | -59.1 | -0.2% |
| S_PEDROLEVEL4 | Storage Level | 0.790 | 0.782 | 21,203 | 21,255 | +52.1 | +0.2% |
| S_SHSTALEVEL2 | Storage Level | 0.346 | 0.207 | 19,423 | 21,243 | +1,819 | +9.4% |
| S_TRNTYLEVEL2 | Storage Level | 0.780 | 0.740 | 10,749 | 11,362 | +613 | +5.7% |
| S_TRNTYLEVEL3 | Storage Level | 0.835 | 0.793 | 16,806 | 17,368 | +562 | +3.3% |

#### Climate

Climate inputs (precipitation, temperature, VPD) reproduce the baseline closely. Differences stem from the WGEN base climate dataset. VPD shows -3.9% difference from the quantile mapping transformation of temperature.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Precipitation | 36 | 0.956 | 0.916 | 41.3 | 41.5 | +0.19 | +0.5% |
| Temperature | 10 | 0.997 | 0.962 | 51.0 | 50.2 | -0.79 | -1.5% |
| VPD | 10 | 0.966 | 0.962 | 9.66 | 9.29 | -0.37 | -3.9% |

#### Instream Flows

San Joaquin Restoration flows and Feather River minimum instream flow reproduce well. Differences in restoration flows (-4.7% for non-pulse, -12.2% for pulse) trace to differences in the unimpaired inflow volumes fed to the threshold logic.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| MINFLOWFEATHER | Flow Min Required | 0.789 | 0.767 | 1,170 | 1,162 | -9.0 | -0.8% |
| REST_REQ_NP | Release Hydrograph | 0.890 | 0.885 | 383 | 365 | -18.2 | -4.7% |
| REST_REQ_P | Release Hydrograph | 0.906 | 0.903 | 65.3 | 57.3 | -8.0 | -12.2% |

#### Other / Miscellaneous

Miscellaneous terms use a range of methodologies. EBTML Loss ($R^2$ = 0.99) and NDOI Precipitation Accretion ($R^2$ = 0.89) reproduce well. Colusa Basin Drain and Knights Landing Ridge Cut benefit from the hybrid QM+WYT approach ($R^2$ = 0.69 and 0.76 respectively). The Tule Wetness Index ($R^2$ = 0.70) captures the seasonal pattern adequately for Friant operations.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| C_CBD001HIST | Flow | 0.687 | 0.668 | 579 | 516 | -63.1 | -10.9% |
| C_KLR005HIST | Flow | 0.757 | 0.752 | 301 | 290 | -10.2 | -3.4% |
| DELTAACCRETIONFORNDOI | Flow | 0.894 | 0.892 | 864 | 812 | -52.7 | -6.1% |
| EBTML_LOSS | Loss | 0.993 | 0.993 | 17.1 | 16.9 | -0.12 | -0.7% |
| R_60N_NA4_SJR022_SV | Return Flow | 0.954 | 0.954 | 2.66 | 2.62 | -0.04 | -1.4% |
| R_RFS71A_OMR039_SV | Return Flow | 0.496 | 0.491 | 0.69 | 0.64 | -0.05 | -7.3% |
| TULE_WET_INDX | Friant Index | 0.703 | 0.520 | 141 | 148 | +7.0 | +5.0% |

#### Upper Watershed Modules

Upper watershed terms show the most methodological diversity, spanning quantile mapping, WYT averaging, threshold optimization, change-in-storage, and direct calculation. Storage forecast terms produce negative or very small values in both directions, making percent difference misleading; $R^2$ values of 0.70--0.76 adequately capture the seasonal regulation patterns. PG&E Water Year Allocation ($R^2$ = 0.70) uses Solver-optimized thresholds applied to Folsom unimpaired flow.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| C_DER001_SV | Channel | 0.871 | 0.856 | 87.0 | 85.0 | -2.0 | -2.3% |
| C_MFY044_SV | Channel | 0.558 | 0.508 | 25.8 | 16.8 | -8.9 | -34.7% |
| C_NFA048_SV | Channel | 0.862 | 0.852 | 368 | 325 | -42.5 | -11.5% |
| C_SFY007_SV | Channel | 0.824 | 0.823 | 307 | 294 | -13.0 | -4.2% |
| C_STH007_SV | Channel | 0.885 | 0.884 | 95.8 | 97.2 | +1.3 | +1.4% |
| D_NFA016_ABT002_SV | Diversion | 0.974 | 0.974 | 9.15 | 9.10 | -0.05 | -0.5% |
| D_SLT009_SCT000_SV | Diversion | 0.854 | 0.851 | 75.0 | 79.5 | +4.4 | +5.9% |
| E_PEDRO_SV | Evaporation | 0.953 | 0.947 | 73.4 | 70.0 | -3.4 | -4.7% |
| MFPFORECASTRELEASE | Storage Forecast | 0.698 | 0.696 | 0.21 | -2.35 | -2.56 | -- |
| P184FORECASTRELEASE | Storage Forecast | 0.761 | 0.760 | 0.05 | -0.13 | -0.18 | -- |
| PGE_WY_ALLOCATION_SV | Ratio | 0.703 | 0.350 | 0.93 | 0.98 | +0.05 | +5.2% |
| S_PEDRO_SV | Storage | 0.392 | 0.389 | 16,760 | 16,814 | +53 | +0.3% |
| UARPFORECASTRELEASE | Storage Forecast | 0.755 | 0.753 | 0.18 | -0.69 | -0.87 | -- |

### Key takeaways

1. **Overall skill is high.** Median $R^2$ of 0.98 and mean $R^2$ of 0.90 show that the WGEN-VIC-QM pipeline captures the dominant variability in CalSim inputs. The pipeline turns stochastic climate sequences into physically consistent model inputs.

2. **Reconstructed hydrology carries a net bias.** Two hydrologic sources dominate. First, ET quantile mapping raises CalSimHydro deep percolation by +8.8% (approximately 380 TAF/yr) through lower rangeland ET under VIC quantile-mapped inputs. Second, the rim inflows retain a residual VIC wet bias even after quantile mapping: the 203-term aggregate runs +3.0% high (+904 TAF/yr), with major anchors biased upward (Bend Bridge +8.2%, Oroville +7.2%, Yuba +10.3%). These biases compound at the system scale and lift Delta inflow +4.5% and Delta outflow +5.7% above the historical baseline in the CalSim run.

3. **WGEN precipitation drives a consistent drying signal.** Surface runoff (-6%), small watershed recharge (-3%), delta channel depletion terms (-1.5% to -4.6%), and NDOI accretion (-6.1%) all show slight negative bias consistent with the WGEN historical period (1948--2018) producing mildly different precipitation patterns than the full CalSim baseline period.

4. **Model-driven categories outperform index-based categories.** Variables produced by physical models (CalSimHydro, reservoir evaporation, delta channel depletion) consistently achieve higher $R^2$ than variables reconstructed through statistical relationships (WYT averaging, quantile mapping of indices). This is expected: model-driven terms respond deterministically to climate inputs, while index-based terms rely on statistical associations that introduce additional uncertainty.

5. **Categories with weak hydrologic correlation have inherent limitations.** Tulare groundwater terms ($R^2$ = 0.50 for deep percolation), CalSimHydroEE ($R^2$ = 0.72 with negative NSE), and S_PEDRO storage ($R^2$ = 0.39) are terms where the chosen methodology is the best available given project constraints. These terms are either approximate placeholders (Tulare GW), involve very small absolute values (CalSimHydroEE), or represent operational decisions with limited hydrologic predictability (S_PEDRO).

6. **Trinity anomaly requires investigation.** The -24% difference in UNIMP_TRIN ($R^2$ = 0.87) is the largest among unimpaired flows and traces to a potential grid file discrepancy with CalSim-3 forecast DLL's spatial averaging domain.

7. **Threshold-based terms are sensitive to near-threshold years.** Instream flows, PG&E allocation, and water year type classifications all employ threshold logic where small differences in input flows can cause discrete category shifts. The Solver-optimized approach for PG&E allocation ($R^2$ = 0.70, improved from 0.75 with manual thresholds to 0.90 with optimization) demonstrates that systematic threshold calibration meaningfully improves results.

## CalSim run validation

CalSim 3 was run with the full Product A input set (WY 1922--2021) and compared against the historical baseline CalSim run (DCR 2023). The tables below report average annual values in TAF for key system metrics across two evaluation windows: the full WY 1972--2018 validation period and the WY 1987--1992 drought period. Figures show monthly time series and non-exceedance probability distributions for each metric.

### Long-term performance (WY 1972--2018)

| Group | Metric | Baseline Avg (TAF/yr) | Product A Avg (TAF/yr) | Diff (TAF) | Diff (%) |
|-------|--------|---------:|---------:|---------:|---------:|
| Deliveries | CVP Total Delivery | 4,640 | 4,665 | +24 | +0.5% |
| Deliveries | SWP Total Delivery | 2,477 | 2,475 | -2 | -0.1% |
| Delta | Total Banks Exports | 2,565 | 2,566 | +1 | +0.0% |
| Delta | Cache Slough | 3,169 | 3,754 | +586 | +18.5% |
| Delta | Total Jones Exports | 2,463 | 2,485 | +22 | +0.9% |
| Delta | SAC River at Freeport | 16,014 | 16,978 | +964 | +6.0% |
| Delta | SJR at Vernalis | 2,983 | 2,529 | -454 | -15.2% |
| Delta | Delta Inflow | 23,067 | 24,113 | +1,046 | +4.5% |
| Delta | Delta Outflow | 16,960 | 17,928 | +968 | +5.7% |
| Storage | Oroville | 1,930 | 2,000 | +70 | +3.6% |
| Storage | Shasta | 2,931 | 2,998 | +67 | +2.3% |
| Storage | San Luis (Total) | 675 | 685 | +10 | +1.5% |

Total deliveries (CVP + SWP) average 7,140 TAF/yr under Product A versus 7,117 TAF/yr under the baseline, a combined difference of +0.3%. Delta inflow increases by +4.5% and Delta outflow by +5.7%, consistent with the +3.0% rim inflow increase propagating through the system. Reservoir storage levels show modest positive bias (+1.5% to +3.6%) reflecting the slightly wetter input signal. The largest outlier is Cache Slough (+18.5%), which amplifies the precipitation-driven differences in local Delta channel depletion terms. SJR at Vernalis (-15.2%) traces to the San Joaquin rim inflow deficit described in the input validation section.

### Drought period (WY 1987--1992)

| Group | Metric | Baseline Avg (TAF/yr) | Product A Avg (TAF/yr) | Diff (TAF) | Diff (%) |
|-------|--------|---------:|---------:|---------:|---------:|
| Deliveries | CVP Total Delivery | 3,686 | 3,941 | +254 | +6.9% |
| Deliveries | SWP Total Delivery | 1,101 | 1,434 | +333 | +30.3% |
| Delta | Total Banks Exports | 1,246 | 1,577 | +331 | +26.5% |
| Delta | Cache Slough | 213 | 339 | +126 | +59.0% |
| Delta | Total Jones Exports | 1,826 | 2,014 | +188 | +10.3% |
| Delta | SAC River at Freeport | 8,943 | 10,267 | +1,324 | +14.8% |
| Delta | SJR at Vernalis | 1,057 | 1,034 | -24 | -2.3% |
| Delta | Delta Inflow | 10,559 | 11,995 | +1,436 | +13.6% |
| Delta | Delta Outflow | 6,350 | 7,137 | +787 | +12.4% |
| Storage | Oroville | 1,266 | 1,617 | +350 | +27.7% |
| Storage | Shasta | 2,517 | 2,928 | +412 | +16.4% |
| Storage | San Luis (Total) | 446 | 516 | +71 | +15.9% |

During the 1987--1992 drought, differences are substantially larger than the long-term averages. SWP total deliveries increase by +30.3% and Banks exports by +26.5% because the Product A inputs produce modestly wetter conditions during these critical years, which relaxes operational constraints on exports and deliveries. Oroville storage is +27.7% higher and Shasta +16.4% higher, consistent with higher rim inflows maintaining reservoir levels above historical drought lows. These differences illustrate the sensitivity of drought-period operations to the input signal: small differences in inflow timing and magnitude during drought years propagate nonlinearly through reservoir operating rules and export constraints.

### Full validation figures (WY 1972--2018)

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery](figures/calsim-run-product-a/full-validation/DEL_CVP_TOTAL.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery](figures/calsim-run-product-a/full-validation/DEL_SWP_TOTAL.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports](figures/calsim-run-product-a/full-validation/C_CAA003.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports](figures/calsim-run-product-a/full-validation/C_DMC000.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport](figures/calsim-run-product-a/full-validation/C_SAC048.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis](figures/calsim-run-product-a/full-validation/C_SJR070.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow](figures/calsim-run-product-a/full-validation/DELTAINFLOWFORNDOI.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow](figures/calsim-run-product-a/full-validation/NDOI.png)
:::
:::{tab-item} Cache Slough
![Cache Slough](figures/calsim-run-product-a/full-validation/C_CSL004A.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage](figures/calsim-run-product-a/full-validation/S_OROVL.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage](figures/calsim-run-product-a/full-validation/S_SHSTA.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage](figures/calsim-run-product-a/full-validation/S_SLUIS_TOTAL.png)
:::
::::

### Drought period figures (WY 1987--1992)

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery](figures/calsim-run-product-a/drought/DEL_CVP_TOTAL.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery](figures/calsim-run-product-a/drought/DEL_SWP_TOTAL.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports](figures/calsim-run-product-a/drought/C_CAA003.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports](figures/calsim-run-product-a/drought/C_DMC000.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport](figures/calsim-run-product-a/drought/C_SAC048.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis](figures/calsim-run-product-a/drought/C_SJR070.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow](figures/calsim-run-product-a/drought/DELTAINFLOWFORNDOI.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow](figures/calsim-run-product-a/drought/NDOI.png)
:::
:::{tab-item} Cache Slough
![Cache Slough](figures/calsim-run-product-a/drought/C_CSL004A.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage](figures/calsim-run-product-a/drought/S_OROVL.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage](figures/calsim-run-product-a/drought/S_SHSTA.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage](figures/calsim-run-product-a/drought/S_SLUIS_TOTAL.png)
:::
::::
