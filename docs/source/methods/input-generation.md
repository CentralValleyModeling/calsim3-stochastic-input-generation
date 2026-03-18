# Input Generation Methods

CalSim 3 stochastic inputs are generated through two broad approaches: model-based generation, where physical process models are driven directly with WGEN climate inputs, and statistical generation, where quantile mapping or other statistical methods reconstruct variables from model outputs or flow indices. Model-based generation is upstream in the pipeline—its outputs serve both as direct CalSim inputs and as basis variables for downstream statistical methods.

## Model-Based Generation

Five process models are run directly with WGEN synthetic climate to produce CalSim inputs. Together these models generate over 1,100 variables (roughly 75% of all stochastically generated inputs) through physical simulation rather than statistical reconstruction.

### VIC Hydrologic Model

*Module: `mod_forcing/vic/`*

The Variable Infiltration Capacity (VIC) model translates daily WGEN temperature and precipitation into spatially distributed hydrologic fluxes including streamflow, evapotranspiration, soil moisture, and snow water equivalent. VIC runs at a 1/16° grid resolution across the Central Valley domain and serves a dual role: its streamflow outputs provide the basis variables for rim inflow quantile mapping, and its ET outputs feed into CalSimHydro and CalSimHydroEE as quantile-mapped inputs.

Wind speed data, which WGEN does not produce, requires special handling. For Product A, actual historical wind speed records are merged directly using date-matched values, maintaining physical consistency with the observed climate. For Product B, wind speed is sampled from historical records using the WGEN's date mapping—each synthetic day inherits the wind speed from its corresponding historical source date. The WGEN "resampled dates" file, a companion to the baseline meteorological archive, provides this mapping between synthetic and historical timelines.

VIC produces three distinct output sets corresponding to different climate inputs. The historical run uses non-detrended, PRISM bias-corrected climate (the CalSim 3 baseline forcing). Product A uses temperature-detrended WGEN meteorology for the historical period (1915–2018), creating a synthetic parallel to the actual observed climate that serves as the validation dataset. Product B uses the full 1,000-year stochastic WGEN sequences. Product A is methodologically closest to Product B—both use detrended WGEN climate—making Product A validation results the most reliable predictor of Product B performance. The historical VIC run uses a fundamentally different forcing dataset (non-detrended, different bias correction) and therefore provides less direct insight into expected Product B behavior.

### CalSimHydro

*Module: `mod_hydrology/calsimhydro/`*

CalSimHydro is a water budget model that calculates agricultural and urban water demands, groundwater interactions, and return flows for 58 Water Budget Areas (WBAs) across the Central Valley. It receives precipitation directly from WGEN (without bias correction) and evapotranspiration quantile-mapped from VIC flux outputs. CalSimHydro produces 746 variables spanning applied water demands, deep percolation, surface runoff, and actual ET—the largest single category by variable count.

An additional San Joaquin River rebalance step generates 97 supplementary variables required for proper water accounting in the SJR basin. A critical compatibility consideration emerged during processing: the CalSimHydro 2015 version is required for DCR 2023 alignment, as the 2020 version is missing WBAs 50 and 91. WBA 91 grid information required separate sourcing to complete the input set. The SV Composer identifies 746 CalSimHydro variables from DCR 2023, with 45 variables traced to intermediate processes (rebalance, rice output) rather than direct CalSimHydro output.

### CalSimHydroEE (External Elements)

*Module: `mod_hydrology/calsimhydro_ee/`*

The External Elements module mirrors CalSimHydro methodology but applies to 17 boundary areas outside the main domain, generating deep percolation values that serve as groundwater recharge boundary conditions. These areas have less detailed calibration data, and the resulting values are small in magnitude relative to the main system water balance.

### Small Watersheds

*Module: `mod_hydrology/small_watersheds/`*

The Small Watersheds module generates groundwater recharge for 210 small tributary areas using WGEN precipitation directly (no bias correction) and a repeating 12-month ET pattern with no interannual variation. This simpler approach reflects limited calibration data for small watersheds and makes results primarily sensitive to precipitation differences.

### Delta Channel Depletion (DCD)

*Module: `mod_hydrology/delta_channel_depletion/`*

The Delta Channel Depletion model simulates consumptive use and seepage across Sacramento–San Joaquin Delta islands using WGEN temperature and precipitation directly. The model operates in "planning study" configuration (as opposed to "historical study") to match the DCR 2023 baseline established by MSO. Each run requires approximately 3 hours. The model produces 24 direct outputs, with 4 additional aggregated variables (Delta_DP, Delta_GW, DPWA_50, DPWA_60) computed in post-processing using island-level weighted aggregation factors provided by Mohammad Hasan at MSO. The two-column weight matrix sums to 1.0, combining island-scale results into the spatial units CalSim expects. The stochastic configuration holds groundwater contribution rate constant at 0.4, matching the planning study assumption that groundwater conditions reach equilibrium rather than trending over the simulation period.

### Reservoir Evaporation

*Module: `mod_reservoir/evaporation/`*

Monthly evaporation rates for 95 reservoirs are calculated using the Hargreaves-Samani equation driven by WGEN daily temperature. Reservoir-specific monthly calibration factors and elevation-dependent adjustments replicate the original Excel-based methodology in a Python implementation that processes all 95 reservoirs in seconds. The approach produces slightly lower evaporation estimates than historical baselines due to reduced daily temperature range in the synthetic climate.

## Quantile Mapping Methodology

*Implementation: `utils/quantile_mapping.py`*

Quantile mapping (QM) is the primary statistical method for generating synthetic time series for CalSim inputs that are not directly produced by physical models. The technique establishes a statistical relationship between a "basis" time series (typically VIC model output) and a "target" time series (CalSim historical input), then applies that relationship to transform new basis values into corresponding target values.

### Procedure

The quantile mapping procedure operates through a sequence of carefully designed steps. First, the data is split by month so that separate analysis is performed for each calendar month, preserving seasonal patterns. Next, empirical cumulative distribution functions are constructed for both basis and target time series from the training period. For each simulated basis value, its empirical probability is interpolated from the basis CDF.

When values fall outside the historical range, tail extrapolation becomes necessary. If the value is above or below the historical range, a fitted Gamma distribution handles the tail extrapolation. Finally, the target CDF is inverted at the interpolated probability to obtain the mapped value, using the fitted Gamma for tail values.

### Validation Approach

Validation of the quantile mapping methodology uses a historical data split approach. The overlapping historical period (October 1921 through September 2018) is divided into a training period (1921–1971) and a testing period (1972–2018). The statistical relationship is developed using training data, then applied to the testing period where mapped values can be compared against actual CalSim inputs that were held out. This 50/50 split provides approximately equal-length samples for relationship development and independent testing, with evaluation via monthly boxplots, mean percentage error, and R².

The choice of Product A VIC output as the validation basis rather than historical VIC ensures consistency with the stochastic Product B generation methodology. As discussed in the WGEN methods section, Product A and Product B share the same detrended climate forcing, making Product A the methodologically closest analogue to what the stochastic generation will encounter. Historical VIC uses fundamentally different input data (non-detrended, PRISM bias-corrected), meaning performance metrics derived from historical VIC validation would overstate or understate expected Product B performance in unpredictable ways.

This validation framework was first presented at Progress Meeting 1, where the team demonstrated that the same quantile mapping relationships trained on 1921–1971 data successfully reconstruct CalSim inputs during the 1972–2018 holdout period. The figure below illustrates the framework, with VIC streamflow as basis and CalSim input as target, showing clearly that the "truth target" comparison is only available during the testing period—a constraint that stochastic applications must accept.

![Quantile Mapping Validation Framework](../figures/s2-methods_qm-validation-framework.png)
_Figure: Quantile mapping validation framework showing VIC streamflow as basis and CalSim input as target. Training period (1921-1971) develops statistical relationships; testing period (1972-2018) validates mapped values against held-out CalSim truth._

:::note Suggested Plot
Scatter plot comparing Product A validation vs Historical VIC validation for a representative rim inflow location, demonstrating the minor performance difference between approaches while highlighting consistency justification.
:::

The figure below demonstrates quantile mapping performance for reference ET (ETo) at Water Budget Area 02. The empirical CDF comparison shows the raw VIC output (red) deviates substantially from the CalSim 3 target (gray), while the quantile-mapped values (blue) closely match the target distribution. This demonstrates the effectiveness of the bias correction approach.

![ET Quantile Mapping](../figures/s2-methods_qm-et-cdf-comparison.png)
_Figure: Empirical CDF comparison for monthly reference ET at WBA 02. Gray: CalSim 3 historical (target); Red: Raw VIC output (basis); Blue: Quantile-mapped VIC. Quantile mapping successfully corrects the VIC bias._

#### Performance Metrics

Two complementary metrics assess quantile mapping performance. The Pearson correlation coefficient squared (R²) measures the strength of linear relationship between reconstructed and actual values, providing a primary metric for reporting. The Nash-Sutcliffe Efficiency (NSE) offers additional insight particularly for evaluating peak flow reproduction and sensitivity to outliers. For most applications, Pearson R² serves as the primary metric while NSE provides supplementary validation, especially when assessing whether overshoots or undershoots significantly degrade performance.

### Limitations

Several important limitations of the quantile mapping approach should be understood. Trend inheritance is perhaps the most significant concern: quantile mapping inherits long-term trends from the VIC model. If VIC shows a drying trend, mapped flows will also be drier regardless of the target distribution. This was observed at Folsom where unexpected negative bias appeared after mapping.

Sequence preservation is another consideration. While distributions are corrected, the temporal sequence—the timing of peaks and lows—follows the basis time series. This means that the synthetic sequences will have a different temporal structure than the historical record, even though their statistical distributions match.

Tail extrapolation introduces uncertainty because values outside the historical range rely on parametric distribution assumptions that may not hold for truly extreme events. The Gamma distribution provides a reasonable approximation for many hydrologic variables, but users should be aware that extreme value behavior may not be perfectly captured.

Finally, there is a correlation threshold for effective application. The method works best when basis and target are well-correlated (R² greater than 0.7). Performance degrades for weakly or moderately correlated pairs, which led to the development of alternative approaches for certain variables.

## Hybrid Quantile Mapping Approach

For variables where standard quantile mapping produces acceptable correlation but problematic peak overshoots, a hybrid methodology has proven effective. The approach combines quantile-mapped values with water year type monthly averages to balance distributional accuracy with physical realism.

The hybrid method computes reconstructed values as the simple average of quantile-mapped output and water year type monthly averages. This formulation addresses a common pattern where quantile mapping alone overshoots historical peaks (sometimes dramatically) while water year type averaging alone produces overly smooth sequences that fail to capture variability. The averaging dampens excessive QM peaks while adding variability to flat WYT patterns.

Application of the hybrid approach improved performance for Colusa Basin Drain from R² = 0.70 to 0.78 and Knights Landing Ridge Cut from R² = 0.52 to 0.66, with particularly dramatic NSE improvements due to elimination of extreme overshoots. The method is generally recommended for terms with moderate correlation (R² between 0.5 and 0.7) or when standard QM produces peaks exceeding historical maxima by substantial margins.

:::note Suggested Plot
Side-by-side time series comparison for Colusa Basin Drain showing: (1) actual historical, (2) QM-only with overshoots highlighted, (3) WYT-only showing excessive smoothness, (4) hybrid approach achieving balance. Include R² and NSE values for each method.
:::

## Other Approaches

*WYT Framework: `utils/wyt_monthlyavg_framework.py` | Flow Indices: `utils/flow_indices.py`*

For variables where standard and hybrid quantile mapping prove unsuitable, several alternative methods have been developed. Water Year Type averaging works well for variables with regular seasonal patterns but weak direct correlation, such as diversions and scheduled operations. The approach calculates monthly averages conditional on water year type (Wet, Above Normal, Below Normal, Dry, Critical) using Sacramento or San Joaquin indices as appropriate.

Direct calculation using known physical relationships works for variables like NDOI precipitation accretion, where the relationship between precipitation depth and volume can be explicitly computed with area and coefficient adjustments. This approach achieved R² = 0.92, outperforming initial quantile mapping attempts.

Threshold-based logic suits allocation ratios and conditional operations like PG&E Water Year Allocation. The methodology develops threshold relationships between predictor variables (such as Folsom unimpaired flow) and allocation ratios, then applies these relationships systematically. Excel Solver optimization of threshold values improved R² from 0.75 to 0.90, demonstrating the power of careful threshold calibration.

Change-in-storage quantile mapping addresses a specific challenge with reservoir storage reconstruction. Rather than mapping storage levels directly, which can produce water year discontinuities, the approach quantile maps monthly change in storage (ΔS). This preserves realistic storage dynamics while avoiding artifacts at water year boundaries. The method is applied to S_PEDRO reconstruction.

Date-stitching using WGEN sampling dates provides a path forward for variables with weak or no correlation to physical drivers. The methodology matches synthetic years to historical years based on flow indices (four-river or eight-river unimpaired flow sums), then borrows patterns from the matched historical year. This bootstrap approach works particularly well for day volume fractions where 1921-1948 validation shows exact matches for many years.

:::note Suggested Plot  
Decision tree flowchart showing the methodology selection process: starting with correlation assessment, branching to QM (R² > 0.7), hybrid QM (R² 0.5-0.7), WYT averaging (regular seasonal patterns), threshold logic (allocation ratios), direct calculation (known relationships), or date-stitching (weak correlation).
:::

