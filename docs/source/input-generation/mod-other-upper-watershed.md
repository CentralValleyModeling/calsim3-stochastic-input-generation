# mod_other/upper_watershed

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/upper_watershed/`  
Upper watershed module preprocessing (Yuba, Don Pedro, etc.)
```


Inputs for seven CalSim 3 upper watershed sub-models that run prior to main model execution. These modules include Upper American, Upper Feather, Upper Yuba Bear, Lower Yuba, Upper Mokelumne, Upper Stanislaus and Upper Tuolumne Watersheds, each representing detailed operations for specific river systems. The modules execute first with outputs feeding into the main CalSim run, enabling more sophisticated representation of upstream reservoir management and hydropower operations.

## Scope Analysis

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

:::{admonition} Suggested Plot
:class: note
Stacked bar chart showing term counts by module with three segments: (1) matched to existing inventory (gray), (2) filtered out as repeating/constant (light gray), (3) requiring new generation (blue). Annotate total counts and highlight that only Lower Yuba and Don Pedro require new work.
:::

## Methodology
Total of four different approaches are applied to reconstruct the studied upper watershed terms, including:

**1- Water Year Type Monthly Averaging (WYT):** Groups historical months by water year type (Wet, Above Normal, Below Normal, Dry, Critical) and assigns the corresponding monthly mean to each synthetic year. This approach captures seasonal demand and operational patterns that vary with overall water availability but not with year-to-year flow variability. It is the preferred fallback when correlation with VIC outputs is too weak for quantile mapping.

**2- Quantile Mapping (QM):** For the Upper_Watershed Modules terms (i.e., other terms), quantile mapping follows a three-stage chaining approach. First, the full CS3 input DSS file is screened to identify the CalSim 3 historical term with the highest R-squared correlation to the target upper watershed term; this becomes the matching term. In the second stage, VIC Product A output is quantile-mapped to the matching term (trained on 1921–1971, applied on 1972–2018), producing a QMAP Product A reconstruction of the matching term. 
In the third stage, that reconstructed matching-term series serves as the simulation basis for a second QM step trained on the relationship between the matching term and the target term (again over 1921–1971), yielding the final QMAP Product A reconstruction of the upper watershed term for 1972–2018.

**3- Hybrid (QM + WYT):** Averages the QM and WYT reconstructions to blend interannual variability with stable seasonal structure. This mitigates peak overshoot or noise that pure QM can introduce when predictor correlation is moderate. It is applied where QM alone is insufficient but the term still shows meaningful year-to-year signal.

**4- Threshold Optimization:** Defines a step-function mapping from an annual flow index to a discrete output value, with threshold boundaries optimized to maximize correlation with historical observations. This technique generalizes to any CalSim input governed by threshold-triggered operational rules.

### Lower Yuba Module Terms

#### Channel Diversion and MFY-44

Channel diversion exhibits clear hydrologic pattern making quantile mapping the primary approach. The term shows correlation with Yuba River flows, enabling standard QM methodology with VIC output as basis. MFY-44 minimum flow shows unusual peak patterns suggesting either quantile mapping or water year type averaging may be appropriate. Validation will determine which approach best captures the operational logic driving these peaks.

#### Diversion Schedule

Diversion schedule follows regular seasonal patterns without strong correlation to individual flow years, making water year type averaging the natural methodology choice. The approach calculates monthly average diversions conditional on water year type, capturing seasonal demand patterns that vary with overall water availability without requiring year-to-year flow matching.

### American River Module Terms

#### Storage Forecast (Three Terms)

Three American River storage forecast terms (likely P184, P185, P186) exhibit unique seasonal patterns ranging from -15 to +150 TAF with positive values after July and negative values starting January. These represent upstream flow regulation signals: reservoirs hold water in winter (negative, indicating reduced releases) and release in summer (positive, indicating augmented flows above natural patterns).

The forecast release terms feed into Folsom envelope calculations where Folsom full natural flow combines with forecast release adjustments. Initial approach attempts quantile mapping using American River unimpaired flow or temperature as basis. If correlation proves weak, fallback to water year type averaging will preserve seasonal regulation patterns conditional on overall water availability classification.

:::{admonition} Suggested Plot
:class: note
Seasonal pattern visualization showing monthly distributions for the three storage forecast terms across water year types. Include separate panels for each term with box plots by month colored by WYT, illustrating the winter reduction/summer augmentation pattern and WYT-dependent magnitude.
:::

### Don Pedro / Stanislaus Module Terms

#### E_PEDRO (Evaporation)

Don Pedro evaporation exists in reservoir evaporation module output but requires unit conversion as the module term is expressed in CFS (flow rate) rather than depth or volume. The conversion depends on pre-processed storage time series to determine surface area, then translate evaporation depth to volumetric rate. If storage varies significantly, water year type average storage may serve as basis for area calculation, followed by evaporation depth computation and CFS conversion.

#### S_PEDRO (Storage)

Don Pedro storage reconstruction addresses pre-processed storage values used in State and Federal Project (SFP) sharing account calculations. Direct quantile mapping of storage levels creates potential water year boundary discontinuities where one year ends at high storage while the next synthetic year (from different historical analogue) starts at low storage.

The change-in-storage approach resolves this issue by quantile mapping monthly change in storage (delta-S) rather than absolute storage levels. Tuolumne River unimpaired flow serves as the basis for QM, establishing relationship between monthly runoff and storage change. Synthetic sequence storage is then computed by accumulating mapped delta-S values with appropriate initial conditions, producing continuous storage trajectories without year-boundary artifacts.

#### PG&E Water Year Allocation

PG&E Water Year Allocation (described in detail in the {doc}`/source/input-generation/mod-other-other-variables` section) determines hydropower generation water rights as function of Folsom unimpaired flow thresholds. The five-level threshold logic was initially developed through manual trial-and-error (achieving $R^2 = 0.75$) and then refined using Excel Solver's GRG Nonlinear algorithm, which optimized the four threshold boundaries simultaneously to maximize $R^2$. The optimized thresholds achieved $R^2 = 0.90$, a substantial improvement that demonstrates the value of systematic optimization for threshold-based reconstruction. The logic applies from May of the triggering water year through the following April, representing annual allocation decisions that persist through the contract year. The term appears in Don Pedro module as it affects Stanislaus River system operations through PG&E facilities.

The Solver optimization approach was developed during the January progress meetings as a generalizable technique for any threshold-based CalSim input. By parameterizing the threshold boundaries and using a nonlinear solver to maximize correlation with historical values, the team established a repeatable workflow that avoids subjective manual threshold selection.

## Results

The S_PEDRO change-in-storage methodology was successfully applied and validated, demonstrating that change-based QM avoids discontinuities while capturing storage dynamics responsive to runoff patterns.

:::{admonition} Suggested Plot
:class: note
Three-panel comparison: (1) Time series showing reconstructed S_PEDRO storage with water year boundaries marked, demonstrating smooth transitions without discontinuities. (2) Monthly delta-S scatter plot (Tuolumne runoff vs storage change) with QM relationship overlaid showing training and validation periods. (3) Storage trajectory for a multi-year drought sequence demonstrating continuous drawdown/recovery.
:::

Several cross-cutting patterns emerge across upper watershed module terms. Forecast and regulation terms (American storage forecasts, various minimum flows) represent operational decisions that respond to water availability through threshold or seasonal logic. Reservoir-dependent terms (E_PEDRO, S_PEDRO) require careful handling of storage-elevation-area relationships and temporal continuity. Demand and allocation terms (diversions, PG&E allocation) follow either seasonal patterns or threshold-triggered ratios based on annual hydrology assessment.

The diversity of methodologies applied to these 13 terms illustrates the flexibility required for comprehensive input reconstruction. No single approach suffices, but the toolkit of quantile mapping, water year type averaging, threshold logic, direct calculation, and change-in-storage QM provides appropriate methods for each variable's characteristics.
