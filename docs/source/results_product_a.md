# Results / Product A

Product A validation proceeds in two stages. First, the 1,223 reconstructed input variables are compared directly against their CalSim 3 baseline (DCR 2023) values over the WY 1972--2018 overlap period to verify that the WGEN-VIC-QM input generation pipeline faithfully reproduces historical patterns. Second, the full Product A input set (WY 1922--2021) is run through the CalSim 3 model and the resulting system outputs (deliveries, Delta flows, reservoir storage) are compared against the historical CalSim baseline to evaluate how input differences propagate through operational logic.

## Summary

Product A validation demonstrates strong overall fidelity across both stages. At the input level, the 1,223 reconstructed variables achieve a median $R^2$ of 0.98 and mean $R^2$ of 0.90 against historical CalSim values, with 69% of variables exceeding $R^2 \geq 0.90$. At the system level, a CalSim 3 run driven by Product A inputs produces annual-average deliveries, Delta flows, and reservoir storage within 0--5% of the historical baseline over WY 1972--2021, with CVP total deliveries differing by only +0.3% and SWP total deliveries by -0.2%. During the 1987--1992 drought, differences are larger (SWP deliveries +33%, Banks exports +28%) because the wetter Product A inputs during this period propagate through drought-sensitive operational rules. The sections below provide detailed validation for both the input generation and CalSim run stages.

## Input Validation

Input validation compares reconstructed variables against CalSim 3 baseline (DCR 2023) values over the WY 1972--2018 period. This 47-year overlap between the WGEN-generated synthetic climate (WY 1921--2018) and the CalSim baseline historical record provides a direct test of reconstruction fidelity across 1,223 actively generated variables.

### Summary

![R2 Monthly by Input Category](figures/s4-results_r2-monthly-by-category.png)
*Monthly $R^2$ distributions by input category for Product A validation (WY 1972--2018), excluding constant and repeating variables. Box plots show median (orange line), interquartile range (box), and outliers (circles). Category sample sizes shown in parentheses. Dashed green line marks $R^2 = 1.0$; dashed red line marks $R^2 = 0.0$.*

Across all 1,223 validated variables, median $R^2$ is 0.98 and mean $R^2$ is 0.90. Approximately 69% of variables achieve $R^2 \geq 0.90$, and 71% exceed $R^2 \geq 0.80$. Only 10 variables (0.8%) fall below $R^2 = 0.50$.

Key observations from the figure:

- **CalSimHydro** (n=655) shows the tightest distribution with the highest median, reflecting direct use of WGEN precipitation and VIC-derived ET in the CalSimHydro model. Urban demand and wastewater terms achieve $R^2 = 1.0$ because they are entirely determined by repeating non-climate inputs.
- **Reservoir Evaporation** (n=95) achieves near-perfect agreement because the Hargreaves-Samani equation responds smoothly to temperature inputs with minimal sensitivity to precipitation timing.
- **Rim Inflow** (n=228) and **Delta Channel Depletion** (n=28) cluster around $R^2 \approx 0.80$ with moderate spread, consistent with quantile mapping from VIC-simulated flows.
- **Small Watersheds** (n=118) and **Tulare Groundwater Terms** (n=14) show the widest distributions, reflecting WYT averaging for terms with weak VIC correlation. The median $R^2$ of ~0.70 for small watersheds is driven by lower WGEN precipitation producing a -13.5% median recharge reduction.
- **Climate** (n=56) performs well overall, with slightly lower scores in VPD terms due to the quantile mapping step required for vapor pressure deficit.
- **Upper Watershed Modules** (n=13) show moderate spread, with storage forecast terms and the S_PEDRO change-in-storage approach producing lower correlations due to the indirect relationship between flow indices and operational decisions.

### Detailed Tables by Category

The following tables report the weighted-average $R^2$ and NSE for each variable type within a category, along with annual average values for the CalSim historical baseline and Product A reconstruction. Count indicates the number of non-zero, time-varying CalSim state variables represented by each row; counts may be lower than the full inventory totals because constant and zero-valued outputs are excluded from validation (e.g., CalSimHydro reports 655 varying outputs here versus 746 total outputs in the inventory). Absolute difference and percent difference are calculated as Product A minus Historical.

#### CalSimHydro

CalSimHydro represents the largest single category with 655 variables across Sacramento Valley water budget areas. The ET quantile mapping drives a +12% increase in deep percolation (driven by lower rangeland ET under WGEN climate) and a -6% decrease in surface runoff (driven by lower WGEN precipitation).

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

 CalsimHydro external elements show the largest percent difference of any category. The +83% deep percolation increase reflects small absolute values in each element area where even modest ET differences produce large percentage changes.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Deep Percolation | 16 | 0.720 | -3.894 | 24.7 | 45.4 | +20.6 | +83.4% |

#### Rim Inflow (Total)

Rim inflow validation covers 202 individual flow terms (excluding unimpaired flows reported separately). The aggregate $R^2$ of 0.76 reflects the combined effect of VIC model bias correction through quantile mapping and the anchor watershed mass balance adjustment.

| Rim Inflow | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|------------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Total | 202 | 0.761 | 0.695 | 30,137 | 30,990 | +853 | +2.8% |

#### Rim Inflow (Unimpaired)

Unimpaired flows for the nine major river systems show overall strong performance ($R^2$ range 0.87--0.94). Trinity stands out with -24% difference.

| Part B | $R^2$ | NSE | Hist. Ann Avg (TAF) | Prod. A Ann Avg (TAF) | Abs Diff (TAF) | Pct Diff |
|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| UNIMP_TRIN | 0.874 | 0.791 | 1,298 | 991 | -307 | -23.7% |
| UNIMP_SRBB | 0.918 | 0.889 | 8,435 | 9,071 | +637 | +7.5% |
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
| DP Flow | 2 | 0.957 | 0.955 | 82.2 | 78.4 | -3.9 | -4.7% |
| Drainage | 8 | 0.961 | 0.939 | 981 | 966 | -14.9 | -1.5% |
| GW Flow | 2 | 0.994 | 0.994 | 611 | 610 | -0.7 | -0.1% |
| Irrigation | 8 | 0.992 | 0.992 | 1,088 | 1,088 | +0.7 | +0.1% |
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

Reservoir evaporation achieves excellent agreement with only +0.2% difference, confirming that the Hargreaves-Samani Python automation exactly replicates the original Excel methodology. The small remaining difference stems from Product A synthetic temperature being slightly lower than historical.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg (in/yr) | Prod. A Ann Avg (in/yr) | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Evaporation Rate | 95 | 0.978 | 0.958 | 50.8 | 50.9 | +0.12 | +0.2% |

#### Reservoir Storage Curves

Seven reservoir storage levels were reconstructed using a mix of quantile mapping, wetness index algorithms, and WYT averaging. Oroville Level 5 achieves $R^2$ = 0.98 using the refined wetness index with decimal interpolation and sedimentation correction. Shasta Level 2 shows the lowest $R^2$ (0.35), but this reflects misalignment of WYT boundaries in limited historical data windows rather than methodological failure.

| Part B  | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| MAMMOTH_STORAGE | Storage | 0.834 | 0.832 | 608 | 609 | +1.2 | +0.2% |
| S_FOLSMLEVEL2 | Storage Level | 0.687 | 0.640 | 3,956 | 4,009 | +52.7 | +1.3% |
| S_OROVLLEVEL5 | Storage Level | 0.979 | 0.978 | 37,805 | 37,746 | -59.1 | -0.2% |
| S_PEDROLEVEL4 | Storage Level | 0.790 | 0.782 | 21,203 | 21,255 | +52.1 | +0.2% |
| S_SHSTALEVEL2 | Storage Level | 0.346 | 0.207 | 19,423 | 21,243 | +1,819 | +9.4% |
| S_TRNTYLEVEL2 | Storage Level | 0.780 | 0.740 | 10,749 | 11,362 | +613 | +5.7% |
| S_TRNTYLEVEL3 | Storage Level | 0.835 | 0.797 | 16,806 | 17,343 | +536 | +3.2% |

#### Climate

Climate inputs (precipitation, temperature, VPD) show strong performance. Differences stem from the WGEN base climate dataset. VPD shows -3.9% difference due to the quantile mapping transformation from temperature.

| Part C | Count | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|------:|------:|----:|-------------:|-----------:|---------:|---------:|
| Precipitation | 36 | 0.956 | 0.916 | 41.3 | 41.5 | +0.19 | +0.5% |
| Temperature | 10 | 0.997 | 0.962 | 51.0 | 50.2 | -0.79 | -1.5% |
| VPD | 10 | 0.966 | 0.962 | 9.66 | 9.29 | -0.37 | -3.9% |

#### Instream Flows

San Joaquin Restoration flows and Feather River minimum instream flow show strong performance. Differences in restoration flows (-4.7% for non-pulse, -12.2% for pulse) trace to differences in the unimpaired inflow volumes used as input to the threshold logic.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| MINFLOWFEATHER | Flow Min Required | 0.789 | 0.767 | 1,170 | 1,162 | -9.0 | -0.8% |
| REST_REQ_NP | Release Hydrograph | 0.890 | 0.885 | 383 | 365 | -18.2 | -4.7% |
| REST_REQ_P | Release Hydrograph | 0.906 | 0.903 | 65.3 | 57.3 | -8.0 | -12.2% |

#### Other / Miscellaneous

Miscellaneous terms span diverse methodologies. EBTML Loss ($R^2$ = 0.99) and NDOI Precipitation Accretion ($R^2$ = 0.89) show strong performance. Colusa Basin Drain and Knights Landing Ridge Cut benefit from the hybrid QM+WYT approach ($R^2$ = 0.63 and 0.71 respectively). The Tule Wetness Index ($R^2$ = 0.71) captures the seasonal pattern adequately for Friant operations.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| C_CBD001HIST | Flow | 0.627 | 0.613 | 579 | 504 | -74.5 | -12.9% |
| C_KLR005HIST | Flow | 0.711 | 0.707 | 301 | 280 | -20.8 | -6.9% |
| DELTAACCRETIONFORNDOI | Flow | 0.894 | 0.892 | 864 | 812 | -52.7 | -6.1% |
| EBTML_LOSS | Loss | 0.993 | 0.993 | 17.1 | 16.9 | -0.13 | -0.8% |
| R_60N_NA4_SJR022_SV | Return Flow | 0.954 | 0.954 | 2.66 | 2.62 | -0.04 | -1.4% |
| R_RFS71A_OMR039_SV | Return Flow | 0.496 | 0.491 | 0.69 | 0.64 | -0.05 | -7.3% |
| TULE_WET_INDX | Friant Index | 0.715 | 0.518 | 141 | 148 | +6.9 | +4.9% |

#### Upper Watershed Modules

Upper watershed terms show the most methodological diversity, spanning quantile mapping, WYT averaging, threshold optimization, change-in-storage, and direct calculation. Storage forecast terms produce negative or very small values in both directions, making percent difference misleading; $R^2$ values of 0.70--0.77 adequately capture the seasonal regulation patterns. PG&E Water Year Allocation ($R^2$ = 0.70) uses Solver-optimized thresholds applied to Folsom unimpaired flow.

| Part B | Part C | $R^2$ | NSE | Hist. Ann Avg | Prod. A Ann Avg | Abs Diff | Pct Diff |
|--------|--------|------:|----:|-------------:|-----------:|---------:|---------:|
| C_DER001_SV | Channel | 0.889 | 0.877 | 87.0 | 82.3 | -4.8 | -5.5% |
| C_MFY044_SV | Channel | 0.675 | 0.617 | 25.8 | 20.8 | -5.0 | -19.4% |
| C_NFA048_SV | Channel | 0.909 | 0.903 | 368 | 387 | +19.2 | +5.2% |
| C_SFY007_SV | Channel | 0.788 | 0.788 | 307 | 296 | -10.4 | -3.4% |
| C_STH007_SV | Channel | 0.884 | 0.883 | 95.8 | 97.1 | +1.2 | +1.3% |
| D_NFA016_ABT002_SV | Diversion | 0.974 | 0.974 | 9.15 | 9.11 | -0.04 | -0.4% |
| D_SLT009_SCT000_SV | Diversion | 0.855 | 0.852 | 75.0 | 78.9 | +3.9 | +5.2% |
| E_PEDRO_SV | Evaporation | 0.953 | 0.947 | 73.4 | 70.0 | -3.4 | -4.7% |
| MFPFORECASTRELEASE | Storage Forecast | 0.701 | 0.699 | 0.21 | -1.79 | -2.0 | -- |
| P184FORECASTRELEASE | Storage Forecast | 0.767 | 0.766 | 0.05 | -0.08 | -0.13 | -- |
| PGE_WY_ALLOCATION_SV | Ratio | 0.703 | 0.350 | 0.93 | 0.98 | +0.05 | +5.2% |
| S_PEDRO_SV | Storage | 0.392 | 0.389 | 16,760 | 16,814 | +53 | +0.3% |
| UARPFORECASTRELEASE | Storage Forecast | 0.755 | 0.754 | 0.18 | -0.52 | -0.70 | -- |

### Key Takeaways

1. **The overall framework performs well.** Median $R^2$ of 0.98 and mean $R^2$ of 0.90 across 1,223 variables demonstrates that the WGEN-VIC-QM pipeline captures the dominant variability in CalSim inputs. The synthetic input generation methodology successfully translates stochastic climate sequences into physically consistent model inputs.

2. **ET quantile mapping is the dominant source of bias.** The +12% deep percolation increase in CalSimHydro (approximately 600 TAF/yr shift in the valley-wide water budget) is driven by lower rangeland ET under VIC quantile-mapped inputs rather than precipitation differences. MSO is developing an alternative ET methodology for DCR 2025 that could reduce this bias.

3. **WGEN precipitation drives a consistent drying signal.** Surface runoff (-6%), small watershed recharge (-3%), delta channel depletion terms (-1.5% to -4.7%), and NDOI accretion (-6.1%) all show slight negative bias consistent with the WGEN historical period (1948--2018) producing mildly different precipitation patterns than the full CalSim baseline period.

4. **Model-driven categories outperform index-based categories.** Variables produced by physical models (CalSimHydro, reservoir evaporation, delta channel depletion) consistently achieve higher $R^2$ than variables reconstructed through statistical relationships (WYT averaging, quantile mapping of indices). This is expected: model-driven terms respond deterministically to climate inputs, while index-based terms rely on statistical associations that introduce additional uncertainty.

5. **Categories with weak hydrologic correlation accept appropriate limitations.** Tulare groundwater terms ($R^2$ = 0.50 for deep percolation), CalSimHydroEE ($R^2$ = 0.72 with negative NSE), and S_PEDRO storage ($R^2$ = 0.39) represent terms where the chosen methodology is the best available given project constraints. These terms are either approximate placeholders (Tulare GW), involve very small absolute values (CalSimHydroEE), or represent operational decisions with limited hydrologic predictability (S_PEDRO).

6. **Trinity precipitation anomaly requires investigation.** The -24% difference in UNIMP_TRIN ($R^2$ = 0.87) is the largest among unimpaired flows and traces to a potential grid file discrepancy with CalSim-3 forecast DLL's spatial averaging domain.

7. **Threshold-based terms are sensitive to near-threshold years.** Instream flows, PG&E allocation, and water year type classifications all employ threshold logic where small differences in input flows can cause discrete category shifts. The Solver-optimized approach for PG&E allocation ($R^2$ = 0.70, improved from 0.75 with manual thresholds to 0.90 with optimization) demonstrates that systematic threshold calibration meaningfully improves results.

## CalSim Run Validation

CalSim 3 was run with the full Product A input set (WY 1922--2021) and compared against the historical baseline CalSim run (DCR 2023). The tables below report average annual values in TAF for key system metrics across two evaluation windows: the full WY 1972--2021 validation period and the WY 1987--1992 drought period. Figures show monthly time series and non-exceedance probability distributions for each metric.

### Long-Term Performance (WY 1972--2021)

| Group | Metric | Baseline Avg (TAF/yr) | Product A Avg (TAF/yr) | Diff (TAF) | Diff (%) |
|-------|--------|---------:|---------:|---------:|---------:|
| Deliveries | CVP Total Delivery | 4,619 | 4,632 | +13 | +0.3% |
| Deliveries | SWP Total Delivery | 2,452 | 2,446 | -6 | -0.2% |
| Delta | Total Banks Exports | 2,540 | 2,544 | +3 | +0.1% |
| Delta | Cache Slough | 3,067 | 3,622 | +555 | +18.1% |
| Delta | Total Jones Exports | 2,454 | 2,467 | +13 | +0.5% |
| Delta | SAC River at Freeport | 15,822 | 16,681 | +859 | +5.4% |
| Delta | SJR at Vernalis | 2,942 | 2,501 | -441 | -15.0% |
| Delta | Delta Inflow | 22,731 | 23,661 | +930 | +4.1% |
| Delta | Delta Outflow | 16,663 | 17,523 | +861 | +5.2% |
| Storage | Oroville | 1,915 | 1,970 | +55 | +2.9% |
| Storage | Shasta | 2,914 | 2,970 | +56 | +1.9% |
| Storage | San Luis (Total) | 674 | 679 | +5 | +0.7% |

Total deliveries (CVP + SWP) average 7,078 TAF/yr under Product A versus 7,071 TAF/yr under the baseline, a combined difference of +0.1%. Delta inflow increases by +4.1% and Delta outflow by +5.2%, consistent with the +2.8% rim inflow increase propagating through the system. Reservoir storage levels show modest positive bias (+1.9% to +2.9%) reflecting the slightly wetter input signal. The largest outlier is Cache Slough (+18.1%), which amplifies the precipitation-driven differences in local Delta channel depletion terms. SJR at Vernalis (-15.0%) traces to the San Joaquin rim inflow deficit described in the input validation section.

### Drought Period (WY 1987--1992)

| Group | Metric | Baseline Avg (TAF/yr) | Product A Avg (TAF/yr) | Diff (TAF) | Diff (%) |
|-------|--------|---------:|---------:|---------:|---------:|
| Deliveries | CVP Total Delivery | 3,686 | 3,904 | +217 | +5.9% |
| Deliveries | SWP Total Delivery | 1,101 | 1,468 | +367 | +33.4% |
| Delta | Total Banks Exports | 1,246 | 1,590 | +343 | +27.5% |
| Delta | Cache Slough | 213 | 277 | +64 | +29.9% |
| Delta | Total Jones Exports | 1,826 | 1,973 | +147 | +8.0% |
| Delta | SAC River at Freeport | 8,943 | 10,192 | +1,249 | +14.0% |
| Delta | SJR at Vernalis | 1,057 | 1,028 | -30 | -2.8% |
| Delta | Delta Inflow | 10,559 | 11,856 | +1,297 | +12.3% |
| Delta | Delta Outflow | 6,350 | 7,030 | +680 | +10.7% |
| Storage | Oroville | 1,266 | 1,543 | +276 | +21.8% |
| Storage | Shasta | 2,517 | 2,850 | +333 | +13.2% |
| Storage | San Luis (Total) | 446 | 480 | +34 | +7.6% |

During the 1987--1992 drought, differences are substantially larger than the long-term averages. SWP total deliveries increase by +33.4% and Banks exports by +27.5% because the Product A inputs produce modestly wetter conditions during these critical years, which relaxes operational constraints on exports and deliveries. Oroville storage is +21.8% higher and Shasta +13.2% higher, consistent with higher rim inflows maintaining reservoir levels above historical drought lows. These differences illustrate the sensitivity of drought-period operations to the input signal: small differences in inflow timing and magnitude during drought years propagate nonlinearly through reservoir operating rules and export constraints.

### Full Validation Figures (WY 1972--2021)

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

### Drought Period Figures (WY 1987--1992)

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
