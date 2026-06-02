# mod_other/upper_watershed

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/upper_watershed/`  
Upper watershed module preprocessing (Yuba, Don Pedro, etc.)
```
## Scope Analysis

Inputs for seven CalSim 3 upper watershed sub-models that run prior to main model execution. These modules include Upper American, Upper Feather, Upper Yuba Bear, Lower Yuba, Upper Mokelumne, Upper Stanislaus and Upper Tuolumne Watersheds, each representing detailed operations for specific river systems. The modules execute first with outputs feeding into the main CalSim run, enabling more sophisticated representation of upstream reservoir management and hydropower operations.

Comprehensive analysis of all seven module DSS files identified 104 total terms across the modules. However, most of these terms already appear in the main CalSim inventory, having been generated through other input categories such as CalSimHydro demands, rim inflows, or external elements. After filtering for monthly repeating patterns, zero-value terms, and matches to existing inventory, only 13 terms from 5 modules require new generation: Lower Yuba, Upper Yuba Bear, Upper American, Upper Feather, and Upper Tuolumne Watersheds. The other two modules (Upper Stanislaus and Upper Mokelumne Watersheds) are fully covered by existing inventory.

This finding significantly reduces upper watershed module workload compared to initial expectations. The 13 remaining terms employ diverse methodologies spanning quantile mapping, water year type averaging, and threshold optimization logic.

| Term - Part B | Term - Part C | Methodology | Source Watershed Module |
|---------------|:-------------:|:-----------:|:-----------------------:|
| S_PEDRO_SV | STORAGE | Water Year Type Averaging | Upper Tuolumne |
| E_PEDRO_SV | EVAPORATION |  | Upper Tuolumne |
| UARPFORECASTRELEASE | STORAGE-FORECAST | Water Year Type Averaging | Upper American |
| D_NFA016_ABT002_SV | DIVERSION | Water Year Type Averaging | Upper American |
| MFPFORECASTRELEASE | STORAGE-FORECAST | Water Year Type Averaging | Upper American |
| P184FORECASTRELEASE | STORAGE-FORECAST | Water Year Type Averaging | Upper American |
| C_NFA048_SV | CHANNEL | Quantile Mapping | Upper American |
| C_STH007_SV | CHANNEL | Water Year Type Averaging | Upper Yuba Bear |
| PGE_WY_ALLOCATION_SV | RATIO | Threshold Optimization | Upper Yuba Bear |
| C_SFY007_SV | CHANNEL | Quantile Mapping | Upper Yuba Bear |
| C_MFY044_SV | CHANNEL | Hybrid (QM + WYT) | Upper Yuba Bear |
| D_SLT009_SCT000_SV | DIVERSION | Water Year Type Averaging | Upper Feather |
| C_DER001_SV | CHANNEL | Quantile Mapping | Lower Yuba |


## Methodology Overview

Total of four different approaches are applied to reconstruct the studied upper watershed terms, including:

**1- Water Year Type Monthly Averaging (WYT):** Groups historical months by water year type (Wet, Above Normal, Below Normal, Dry, Critical) and assigns the corresponding monthly mean to each synthetic year. This approach captures seasonal demand and operational patterns that vary with overall water availability but not with year-to-year flow variability. It is the preferred fallback when correlation with VIC outputs is too weak for quantile mapping.

**2- Quantile Mapping (QM):** For the Upper_Watershed Modules terms (i.e., other terms), quantile mapping follows a two-stage chaining approach. As a prerequisite step, the full CS3 input DSS file is screened to identify the CalSim 3 historical term with the highest R-squared correlation to the target upper watershed term; this becomes the matching term. In the first QM stage, VIC Product A output is quantile-mapped to the matching term (trained on 1921-1971, applied on 1972-2018), producing a QMAP Product A reconstruction of the matching term. In the second QM stage, that reconstructed matching-term series serves as the simulation basis for a second QM step trained on the relationship between the matching term and the target term (again over 1921-1971), yielding the final QMAP Product A reconstruction of the upper watershed term for 1972-2018.

**3- Hybrid (QM + WYT):** Averages the QM and WYT reconstructions to blend interannual variability with stable seasonal structure. This mitigates peak overshoot or noise that pure QM can introduce when predictor correlation is moderate. It is applied where QM alone is insufficient but the term still shows meaningful year-to-year signal.

**4- Threshold Optimization:** Defines a step-function mapping from an annual flow index to a discrete output value, with threshold boundaries optimized to maximize correlation with historical observations. This technique generalizes to any CalSim input governed by threshold-triggered operational rules.

---

## 1. Water Year Type Averaging

Eight upper watershed terms are reconstructed using WYT monthly averaging, spanning the Upper Tuolumne, Upper American, Upper Yuba Bear, and Upper Feather watershed modules.

### S_PEDRO_SV (Storage, Upper Tuolumne)

Don Pedro storage is a pre-processed input to the Upper Tuolumne Watershed module and enters State and Federal Project (SFP) sharing account calculations. Direct quantile mapping of storage levels and quantile mapping of monthly change-in-storage (delta-S) were both evaluated but rejected: the former introduces abrupt discontinuities at water year boundaries when splicing sequences from different historical analogues, while the latter accumulates mapping errors across monthly integration steps causing trajectories to drift away from the plausible storage range over multi-year dry periods. 

San Joaquin Water Year Type (WYT) monthly averaging was ultimately adopted as the final methodology, computing the mean Don Pedro storage for each of the five WYT classes (Wet, Above Normal, Below Normal, Dry, Critical) and assigning the corresponding class mean to each synthetic month.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/S_PEDRO_SV.png
:name: fig-s-pedro-sv
:width: 100%
Product A validation for S_PEDRO_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.39$ -- moderate, but the best result among all approaches tested -- and PBIAS of only 0.3%, indicating near-perfect long-term volume balance. It captures the seasonal fill-and-drawdown cycle and broad inter-annual contrasts between wet and dry years, with the non-exceedance CDF showing close agreement across the upper 60% of the storage distribution (roughly 1,100-2,050 TAF) where most operational months fall. 

The low $R^2$ is driven almost entirely by a small number of extreme drought months such as 1976-1977 and 2014-2015, where actual storage dropped below 500 TAF but WYT class means keep the reconstruction in the 1,000-1,700 TAF range -- an inherent limitation of the averaging approach. Because Don Pedro storage enters CalSim as a pre-processed input to SFP sharing account calculations governed primarily by annual WYT classification rather than absolute storage levels during extreme droughts, the WYT-conditioned reconstruction is fit for purpose.

### E_PEDRO_SV (Evaporation, Upper Tuolumne)

Don Pedro evaporation exists in reservoir evaporation module output but requires unit conversion, as the module term is expressed in CFS (flow rate) rather than depth or volume. The conversion depends on pre-processed storage time series to determine surface area, then translates evaporation depth to volumetric rate. If storage varies significantly, water year type average storage may serve as basis for area calculation, followed by evaporation depth computation and CFS conversion.

> **Note:** E_PEDRO_SV does not have a methodology assigned in the scope analysis table. The evaporation values are derived from the reservoir evaporation module output, with WYT-based storage serving as the area conversion input.

### UARPFORECASTRELEASE (Storage-Forecast, Upper American)

Upper American River forecast release is a storage-forecast signal for the upstream reservoirs feeding Folsom Lake, expressed in TAF and oscillating between negative winter values (reservoir holding, reduced releases) and positive summer values (augmented releases). The term feeds into Folsom envelope calculations where Folsom full natural flow is adjusted by forecast release to set operating targets. 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, computing the mean monthly forecast release for each of the five WYT classes and assigning the corresponding class mean to each synthetic month. 

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/UARPFORECASTRELEASE.png
:name: fig-uarpforecastrelease
:width: 100%
Product A validation for UARPFORECASTRELEASE: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.76$, indicating a strong fit that captures both the seasonal sign reversal and the WYT-dependent magnitude of the release signal. As visible in the validation time series, the reconstructed series closely tracks the seasonal oscillation of the actual record throughout the 1921-2021 period, with the WYT conditioning accounting for the inter-annual variation in release magnitudes between wet and dry years.

### MFPFORECASTRELEASE (Storage-Forecast, Upper American)

Middle Fork Pit forecast release is a storage-forecast signal for the Middle Fork American River reservoirs upstream of Folsom Lake, following the same seasonal regulation pattern as UARPFORECASTRELEASE, which is negative values in winter (reservoir holding) and positive values in summer (augmented releases). Sacramento Valley Water Year Type monthly averaging is the adopted methodology for this term. 

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/MFPFORECASTRELEASE.png
:name: fig-mfpforecastrelease
:width: 100%
Product A validation for MFPFORECASTRELEASE: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.70$, reflecting a strong fit between the WYT-conditioned monthly means and the historical record. The validation time series confirms that the reconstructed series captures the seasonal sign reversal and the inter-annual variation in release magnitude driven by annual water supply classification, though the WYT averaging smooths out some of the more extreme negative excursions seen in the actual record.

The PBIAS of -967.7% is a numerical artifact rather than a meaningful bias indicator: because positive and negative monthly values nearly cancel when summed, the historical mean approaches zero, causing PBIAS (which normalizes by the observed sum) to amplify even small absolute differences into extreme percentages. The strong agreement visible in both the monthly time series and the non-exceedance CDF, together with NSE = 0.70, confirms that the reconstruction captures the seasonal pattern and distributional shape well despite the misleading PBIAS value.

### P184FORECASTRELEASE (Storage-Forecast, Upper American)

P184 forecast release is the third American River storage forecast term exhibiting the same seasonal regulation pattern as UARPFORECASTRELEASE and MFPFORECASTRELEASE. The three forecast release terms collectively represent the coordinated upstream reservoir signaling that drives Folsom storage envelope management.Sacramento Valley Water Year Type monthly averaging is the adopted methodology, assigning the mean monthly forecast release for each WYT class to each synthetic month. 
 
 #### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/P184FORECASTRELEASE.png
:name: fig-p184forecastrelease
:width: 100%
Product A validation for P184FORECASTRELEASE: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

 The reconstruction achieves $R^2 = 0.77$, consistent with the other American River forecast terms. The validation time series shows that the reconstructed series closely follows the seasonal oscillation of the actual record, with values ranging from approximately -10 to +7 TAF. The WYT conditioning captures inter-annual differences in release magnitude, though the class-mean averaging moderates the more extreme negative excursions present in the actual record.
 
 The PBIAS of -252.4% is a near-zero-denominator artifact: the positive and negative monthly values of this signed forecast term nearly cancel in the historical sum, so the PBIAS denominator approaches zero and small absolute differences are amplified into extreme percentages. The close alignment of the two curves in both the monthly time series and the non-exceedance CDF, together with NSE = 0.77, confirms that the reconstruction is a good match to the historical record despite the misleading PBIAS value.

### D_NFA016_ABT002_SV (Diversion, Upper American)

North Fork American River at Auburn Tunnel Pump Station diversion follows a highly consistent seasonal pattern, cycling between near-zero winter values and a near-constant ~2.1 TAF in active diversion months. Sacramento Valley Water Year Type monthly averaging is the adopted methodology for this term. 

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/D_NFA016_ABT002_SV.png
:name: fig-d-nfa016-abt002-sv
:width: 100%
Product A validation for D_NFA016_ABT002_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.97$, an exceptionally strong fit reflecting the regularity of this operational diversion. As visible in the validation time series, the reconstructed series is nearly indistinguishable from the actual record across the full 1921-2021 period, with only rare episodic deviations in severe drought years where actual diversions dropped below the WYT class mean.

### C_STH007_SV (Channel Flow, Upper Yuba Bear)

Newcastle Powerplant near Newcastle channel flow exhibits a seasonal pattern governed by operational releases and inter-basin transfers that correlate more strongly with overall water year conditions than with individual monthly flows. Sacramento Valley Water Year Type monthly averaging is the adopted methodology for this term. 

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_STH007_SV.png
:name: fig-c-sth007-sv
:width: 100%
Product A validation for C_STH007_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.88$, indicating a strong fit. The validation time series shows the reconstructed series closely tracking the seasonal oscillation of the actual record, with values cycling between near-zero winter lows and approximately 14 TAF summer peaks. The WYT conditioning captures inter-annual variability in flow magnitude, though occasional extreme peaks above 14 TAF and rare near-zero summer values in severe drought years fall outside the range of WYT class means.

### D_SLT009_SCT000_SV (Diversion, Upper Feather)

Diversion at Slate Creek Tunnel in the Upper Feather watershed follows a consistent seasonal pattern, cycling between near-zero winter values and peaks of approximately 18-21 TAF in high-diversion months. Sacramento Valley Water Year Type monthly averaging is the adopted methodology for this term. 

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/D_SLT009_SCT000_SV.png
:name: fig-d-slt009-sct000-sv
:width: 100%
Product A validation for D_SLT009_SCT000_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.85$, reflecting a strong fit between the WYT-conditioned monthly means and the historical record. The validation time series shows the reconstructed series closely tracking the actual seasonal pattern throughout the 1921-2021 period, with WYT conditioning capturing inter-annual differences in diversion magnitude between wet and dry years. Rare near-zero diversions during severe drought years such as 1976-1977 fall below the WYT class means and are not fully captured by the averaging approach.

---

## 2. Quantile Mapping

Three upper watershed channel flow terms are reconstructed using the two-stage chaining quantile mapping approach, covering the Upper American, Upper Yuba Bear, and Lower Yuba watershed modules.

### C_NFA048_SV (Channel Flow, Upper American)

North Fork American channel flow is reconstructed using the two-stage chaining quantile mapping approach for "other terms", with `I_NFA054` identified as the CalSim 3 matching term (highest R-squared correlation to C_NFA048_SV across the full CS3 input DSS screening). 

In the first stage, VIC Product A output is quantile-mapped to `I_NFA054`, with the QM relationship trained on the 1921-1971 period and applied to the 1972-2018 simulation period, yielding a QMAP Product A reconstruction of the matching term. In the second stage, that reconstructed `I_NFA054` series (1972-2018) serves as the basis for a new QM step trained on the historical relationship between `I_NFA054` and `C_NFA048_SV` over 1921-1971, producing the final QMAP Product A reconstruction of the target term for 1972-2018.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_NFA048_SV.png
:name: fig-c-nfa048-sv
:width: 100%
Product A validation for C_NFA048_SV: monthly time series (left) and non-exceedance CDF (right) comparing reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.86$, $\text{NSE} = 0.85$, and $\text{PBIAS} = -11.5\%$. The monthly time series shows the reconstruction closely tracking the historical seasonal pattern and capturing near-zero dry-season base flows well. However, several prominent wet-season peaks in the historical record -- particularly the largest events exceeding 150-200 TAF visible in years such as 1983, 1997, and 2017 -- are not fully reproduced, with the reconstruction underestimating their magnitude. This is consistent with the negative percent bias of -11.5% and the upper-tail divergence in the non-exceedance CDF, where Product A falls below the historical curve above the 90th percentile. The chaining QM approach captures the overall flow regime and inter-annual variability well, but the smoothing inherent in the two-stage mapping limits its ability to reproduce the most extreme monthly flow events.

### C_SFY007_SV (Channel Flow, Upper Yuba Bear)

South Fork Yuba channel flow is reconstructed using the two-stage chaining quantile mapping approach for "other terms", with `FOLSOM_INFLOW` identified as the CalSim 3 matching term (highest R-squared correlation to C_SFY007_SV across the full CS3 input DSS screening).

In the first stage, VIC Product A output is quantile-mapped to `FOLSOM_INFLOW`, with the QM relationship trained on the 1921-1971 period and applied to the 1972-2018 simulation period, yielding a QMAP Product A reconstruction of the matching term. In the second stage, that reconstructed `FOLSOM_INFLOW` series (1972-2018) serves as the basis for a new QM step trained on the historical relationship between `FOLSOM_INFLOW` and `C_SFY007_SV` over 1921-1971, producing the final QMAP Product A reconstruction of the target term for 1972-2018.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_SFY007_SV.png
:name: fig-c-sfy007-sv
:width: 100%
Product A validation for C_SFY007_SV: monthly time series (left) and non-exceedance CDF (right) comparing reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.82$, $\text{NSE} = 0.82$, and $\text{PBIAS} = -4.2\%$. The monthly time series shows the reconstruction closely tracking the historical seasonal pattern, capturing both near-zero dry-season base flows and wet-season peaks across the 0-290 TAF range. The very low percent bias of -4.2% indicates near-neutral volume balance, and the non-exceedance CDF shows the two curves overlapping closely through most of the distribution. A small number of extreme peaks -- most notably the largest wet-season event near 2019 -- are not fully captured, with the reconstruction underestimating peak magnitude, which accounts for the slight upper-tail divergence visible in the CDF above the 95th percentile.

### C_DER001_SV (Channel Flow, Lower Yuba)

Lower Yuba channel flow is reconstructed using the two-stage chaining quantile mapping approach for "other terms", with `I_CSM035` identified as the CalSim 3 matching term (highest R-squared correlation to C_DER001_SV across the full CS3 input DSS screening).

In the first stage, VIC Product A output is quantile-mapped to `I_CSM035`, with the QM relationship trained on the 1921-1971 period and applied to the 1972-2018 simulation period, yielding a QMAP Product A reconstruction of the matching term. In the second stage, that reconstructed `I_CSM035` series (1972-2018) serves as the basis for a new QM step trained on the historical relationship between `I_CSM035` and `C_DER001_SV` over 1921-1971, producing the final QMAP Product A reconstruction of the target term for 1972-2018.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_DER001_SV.png
:name: fig-c-der001-sv
:width: 100%
Product A validation for C_DER001_SV: monthly time series (left) and non-exceedance CDF (right) comparing reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.87$, $\text{NSE} = 0.86$, and $\text{PBIAS} = -2.3\%$. The monthly time series shows the reconstruction closely tracking the historical seasonal pattern of spiky wet-season peaks and near-zero dry-season base flows across the 0-90 TAF range. The near-neutral percent bias of -2.3% indicates very good volume balance overall, and the non-exceedance CDF shows the two curves closely aligned through most of the distribution. Some individual peak events are over- or underestimated in specific years, contributing to minor divergence at the very upper tail of the CDF above the 95th percentile, but the overall timing and magnitude agreement reflected in NSE = 0.86 represents strong reconstruction performance for this Lower Yuba channel term.

---

## 3. Hybrid (QM + WYT)

One upper watershed term employs the hybrid methodology, blending quantile mapping and WYT averaging to handle a term where neither approach alone performs adequately.

### C_MFY044_SV (Channel Flow, Upper Yuba Bear)

Middle Fork Yuba minimum channel flow shows unusual peak patterns that neither pure quantile mapping nor pure WYT averaging captures fully on its own. Pure QM tends to overfit to extreme years and can introduce peak overshoot, while WYT averaging smooths out year-to-year variability that is physically meaningful in the Middle Fork system. The hybrid approach averages the two reconstructions to blend interannual variability from QM with the stable seasonal structure from WYT, mitigating peak overshoot while preserving the year-to-year signal present in the historical record.

For the QM component, `I_SFA076` is used as the CalSim 3 matching term, identified through screening as the highest R-squared predictor for C_MFY044_SV, and the two-stage chaining approach is applied over the standard 1921-1971 training and 1972-2018 simulation split. For the WYT component, San Joaquin Water Year Type monthly averaging is used, computing the conditional monthly mean for each of the five WYT classes and assigning the corresponding class mean to each synthetic month. The final reconstruction is the arithmetic average of the two component series.

#### Validation





---

## 4. Threshold Optimization

One upper watershed term employs threshold optimization, where discrete output values are determined by optimized annual flow index thresholds.

### PGE_WY_ALLOCATION_SV (Ratio, Upper Yuba Bear)

PG&E Water Year Allocation ratio determines contractual water allocation as a function of annual water availability, with values ranging from 0.40 (severe shortage) to 1.00 (full allocation). All allocation changes occur in May each year, with the ratio transitioning from 1.0 to a restricted level and persisting through the following April before resetting. The term appears in the Upper Yuba Bear module as it affects Stanislaus River system operations through PG&E facilities.

Five distinct ratio categories were identified from the historical record: 1.00, 0.90, 0.80, 0.60, and 0.40. Annual Folsom unimpaired flow serves as the governing index, with optimized threshold boundaries separating the five levels. Initial trial-and-error threshold selection achieved $R^2 = 0.75$. Excel Solver's GRG Nonlinear algorithm then refined the four boundaries simultaneously to maximize $R^2$, improving to $R^2 = 0.90$:

| Annual Folsom Unimpaired Flow (TAF) | Allocation Ratio |
|-------------------------------------|:----------------:|
| $\leq$ 488 | 0.40 |
| 489 -- 801 | 0.60 |
| 802 -- 957 | 0.80 |
| 958 -- 1,146 | 0.90 |
| $>$ 1,146 | 1.00 |

The exact Solver-optimized threshold boundaries are 488.24, 800.72, 957.08, and 1,146.02 TAF. The Solver optimization approach is a generalizable technique for any threshold-based CalSim input: by parameterizing threshold boundaries and using a nonlinear solver to maximize correlation with historical values, the workflow avoids subjective manual threshold selection. The logic applies from May of the triggering water year through the following April and has been implemented in Python (`_4_pge_wy_allocation.py`) for production runs.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/PGE_WY_ALLOCATION_SV.png
:name: fig-pge-wy-allocation-sv
:width: 100%
Validation of PGE_WY_ALLOCATION_SV: reconstructed (orange) vs. actual (blue) water year allocation ratio over 1921-2021, showing the step-function response to annual Folsom unimpaired flow thresholds.
```

The validation time series confirms that the reconstructed series correctly reproduces the discrete step-function nature of the allocation ratio, with the optimized thresholds capturing the timing and level of allocation reductions across wet, normal, and dry year sequences. The reconstruction achieves $R^2 = 0.90$ against the full historical record, with the remaining mismatches concentrated in transition years where annual Folsom unimpaired flow falls near a threshold boundary.

---
