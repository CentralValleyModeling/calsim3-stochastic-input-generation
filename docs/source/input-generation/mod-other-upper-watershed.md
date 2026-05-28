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


## Methodology

Total of four different approaches are applied to reconstruct the studied upper watershed terms, including:

- **Water Year Type Monthly Averaging (WYT):** Groups historical months by water year type (Wet, Above Normal, Below Normal, Dry, Critical) and assigns the corresponding monthly mean to each synthetic year. This approach captures seasonal demand and operational patterns that vary with overall water availability but not with year-to-year flow variability. It is the preferred fallback when correlation with VIC outputs is too weak for quantile mapping.

- **Quantile Mapping (QM):** For the Upper_Watershed Modules terms (i.e., other terms), quantile mapping follows a three-stage chaining approach. First, the full CS3 input DSS file is screened to identify the CalSim 3 historical term with the highest R-squared correlation to the target upper watershed term; this becomes the matching term. In the second stage, VIC Product A output is quantile-mapped to the matching term (trained on 1921-1971, applied on 1972-2018), producing a QMAP Product A reconstruction of the matching term. In the third stage, that reconstructed matching-term series serves as the simulation basis for a second QM step trained on the relationship between the matching term and the target term (again over 1921-1971), yielding the final QMAP Product A reconstruction of the upper watershed term for 1972-2018.

- **Hybrid (QM + WYT):** Averages the QM and WYT reconstructions to blend interannual variability with stable seasonal structure. This mitigates peak overshoot or noise that pure QM can introduce when predictor correlation is moderate. It is applied where QM alone is insufficient but the term still shows meaningful year-to-year signal.

- **Threshold Optimization:** Defines a step-function mapping from an annual flow index to a discrete output value, with threshold boundaries optimized to maximize correlation with historical observations. This technique generalizes to any CalSim input governed by threshold-triggered operational rules.

---

### 1. Water Year Type Averaging

Eight upper watershed terms are reconstructed using WYT monthly averaging, spanning the Upper Tuolumne, Upper American, Upper Yuba Bear, and Upper Feather watershed modules.

#### S_PEDRO_SV (Storage, Upper Tuolumne)

Don Pedro storage is a pre-processed input to the Upper Tuolumne Watershed module and enters State and Federal Project (SFP) sharing account calculations. Direct quantile mapping of storage levels and quantile mapping of monthly change-in-storage (delta-S) were both evaluated but rejected: the former introduces abrupt discontinuities at water year boundaries when splicing sequences from different historical analogues, while the latter accumulates mapping errors across monthly integration steps causing trajectories to drift away from the plausible storage range over multi-year dry periods. 

San Joaquin Water Year Type (WYT) monthly averaging was ultimately adopted as the final methodology, computing the mean Don Pedro storage for each of the five WYT classes (Wet, Above Normal, Below Normal, Dry, Critical) and assigning the corresponding class mean to each synthetic month.

The reconstruction achieves $R^2 = 0.53$ against the historical record -- moderate, but the best result among all approaches tested. It captures the seasonal fill-and-drawdown cycle and broad inter-annual contrasts between wet and dry years, but underestimates the depth of severe multi-year droughts such as 1976-1977 and 2014-2015, where actual storage dropped below 500 TAF. This is an inherent limitation of WYT averaging: class means smooth out the tail of observed variability, keeping the reconstructed series generally in the 1,000-1,700 TAF range throughout the historical period.

#### E_PEDRO_SV (Evaporation, Upper Tuolumne)

Don Pedro evaporation exists in reservoir evaporation module output but requires unit conversion, as the module term is expressed in CFS (flow rate) rather than depth or volume. The conversion depends on pre-processed storage time series to determine surface area, then translates evaporation depth to volumetric rate. If storage varies significantly, water year type average storage may serve as basis for area calculation, followed by evaporation depth computation and CFS conversion.

> **Note:** E_PEDRO_SV does not have a methodology assigned in the scope analysis table. The evaporation values are derived from the reservoir evaporation module output, with WYT-based storage serving as the area conversion input.

#### UARPFORECASTRELEASE (Storage-Forecast, Upper American)

Upper American River forecast release is a storage-forecast signal for the upstream reservoirs feeding Folsom Lake, expressed in TAF and oscillating between negative winter values (reservoir holding, reduced releases) and positive summer values (augmented releases). The term feeds into Folsom envelope calculations where Folsom full natural flow is adjusted by forecast release to set operating targets. 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, computing the mean monthly forecast release for each of the five WYT classes and assigning the corresponding class mean to each synthetic month. The reconstruction achieves $R^2 = 0.78$, indicating a strong fit that captures both the seasonal sign reversal and the WYT-dependent magnitude of the release signal. 

As visible in the validation time series, the reconstructed series closely tracks the seasonal oscillation of the actual record throughout the 1921-2021 period, with the WYT conditioning accounting for the inter-annual variation in release magnitudes between wet and dry years.

#### MFPFORECASTRELEASE (Storage-Forecast, Upper American)

Middle Fork Pit forecast release is a storage-forecast signal for the Middle Fork American River reservoirs upstream of Folsom Lake, following the same seasonal regulation pattern as UARPFORECASTRELEASE, which is negative values in winter (reservoir holding) and positive values in summer (augmented releases). 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, and the reconstruction achieves $R^2 = 0.75$, reflecting a strong fit between the WYT-conditioned monthly means and the historical record. 

The validation time series confirms that the reconstructed series captures the seasonal sign reversal and the inter-annual variation in release magnitude driven by annual water supply classification, though the WYT averaging smooths out some of the more extreme negative excursions seen in the actual record.

#### P184FORECASTRELEASE (Storage-Forecast, Upper American)

P184 forecast release is the third American River storage forecast term exhibiting the same seasonal regulation pattern as UARPFORECASTRELEASE and MFPFORECASTRELEASE. The three forecast release terms collectively represent the coordinated upstream reservoir signaling that drives Folsom storage envelope management.

 Sacramento Valley Water Year Type monthly averaging is the adopted methodology, assigning the mean monthly forecast release for each WYT class to each synthetic month. The reconstruction achieves $R^2 = 0.78$, consistent with the other American River forecast terms. 
 
 The validation time series shows that the reconstructed series closely follows the seasonal oscillation of the actual record, with values ranging from approximately -10 to +7 TAF. The WYT conditioning captures inter-annual differences in release magnitude, though the class-mean averaging moderates the more extreme negative excursions present in the actual record.

#### D_NFA016_ABT002_SV (Diversion, Upper American)

North Fork American River at Auburn Tunnel Pump Station diversion follows a highly consistent seasonal pattern, cycling between near-zero winter values and a near-constant ~2.1 TAF in active diversion months. 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, and the reconstruction achieves $R^2 = 0.98$, an exceptionally strong fit reflecting the regularity of this operational diversion. 

As visible in the validation time series, the reconstructed series is nearly indistinguishable from the actual record across the full 1921-2021 period, with only rare episodic deviations in severe drought years where actual diversions dropped below the WYT class mean.

#### C_STH007_SV (Channel Flow, Upper Yuba Bear)

Newcastle Powerplant near Newcastle channel flow exhibits a seasonal pattern governed by operational releases and inter-basin transfers that correlate more strongly with overall water year conditions than with individual monthly flows. 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, and the reconstruction achieves $R^2 = 0.88$, indicating a strong fit. 

The validation time series shows the reconstructed series closely tracking the seasonal oscillation of the actual record, with values cycling between near-zero winter lows and approximately 14 TAF summer peaks. The WYT conditioning captures inter-annual variability in flow magnitude, though occasional extreme peaks above 14 TAF and rare near-zero summer values in severe drought years fall outside the range of WYT class means.

#### D_SLT009_SCT000_SV (Diversion, Upper Feather)

Diversion at Slate Creek Tunnel in the Upper Feather watershed follows a consistent seasonal pattern, cycling between near-zero winter values and peaks of approximately 18-21 TAF in high-diversion months. 

Sacramento Valley Water Year Type monthly averaging is the adopted methodology, and the reconstruction achieves $R^2 = 0.88$, reflecting a strong fit between the WYT-conditioned monthly means and the historical record. 

The validation time series shows the reconstructed series closely tracking the actual seasonal pattern throughout the 1921-2021 period, with WYT conditioning capturing inter-annual differences in diversion magnitude between wet and dry years. Rare near-zero diversions during severe drought years such as 1976-1977 fall below the WYT class means and are not fully captured by the averaging approach.

---

### 2. Quantile Mapping

Three upper watershed channel flow terms are reconstructed using the three-stage chaining quantile mapping approach, covering the Upper American, Upper Yuba Bear, and Lower Yuba watershed modules.

#### C_NFA048_SV (Channel Flow, Upper American)

North Fork American channel flow exhibits year-to-year hydrologic variability with sufficient correlation to VIC outputs to support quantile mapping. The three-stage chaining approach first screens the full CS3 input DSS to identify the CalSim 3 historical term with the highest R-squared correlation to C_NFA048_SV as the matching term. VIC Product A output is then quantile-mapped to the matching term trained over 1921-1971 and applied over 1972-2018. A second QM step maps the reconstructed matching-term series to the target C_NFA048_SV over the same split-sample periods, yielding the final Product A reconstruction.

#### C_SFY007_SV (Channel Flow, Upper Yuba Bear)

South Fork Yuba channel flow shows year-to-year variability consistent with a runoff-driven response, enabling the quantile mapping approach. As with other QM terms, the best-correlated matching term in the CS3 input DSS is identified by maximum R-squared, and the three-stage chain maps VIC Product A through the intermediate matching term to produce the final reconstruction. The split-sample training (1921-1971) and validation (1972-2018) periods ensure the QM relationship is not overfit to the full historical record.

#### C_DER001_SV (Channel Flow, Lower Yuba)

Lower Yuba channel flow exhibits a clear hydrologic pattern, making quantile mapping the primary approach. The term shows correlation with Yuba River flows, enabling standard QM methodology with VIC output as basis. The three-stage chaining methodology applies: the highest-R-squared CalSim 3 matching term is identified from the full DSS screening, VIC Product A is mapped to that matching term over the training period, and a second QM step reconstructs the target Lower Yuba channel term from the intermediate matching-term series over the validation period.

---

### 3. Hybrid (QM + WYT)

One upper watershed term employs the hybrid methodology, blending quantile mapping and WYT averaging to handle a term where neither approach alone performs adequately.

#### C_MFY044_SV (Channel Flow, Upper Yuba Bear)

Middle Fork Yuba minimum channel flow shows unusual peak patterns that neither pure quantile mapping nor pure WYT averaging captures fully on its own. Pure QM tends to overfit to extreme years and can introduce peak overshoot, while WYT averaging smooths out year-to-year variability that is physically meaningful in the Middle Fork system. The hybrid approach averages the QM and WYT reconstructions to blend interannual variability from QM with the stable seasonal structure from WYT, mitigating peak overshoot while preserving the year-to-year signal present in the historical record. This makes the hybrid particularly appropriate for minimum flow terms where both seasonal patterns and annual hydrologic conditions govern the observed values.

---

### 4. Threshold Optimization

One upper watershed term employs threshold optimization, where discrete output values are determined by optimized annual flow index thresholds.

#### PGE_WY_ALLOCATION_SV (Ratio, Upper Yuba Bear)

PG&E Water Year Allocation determines hydropower generation water rights as a function of Folsom unimpaired flow thresholds. The five-level threshold logic was initially developed through manual trial-and-error (achieving $R^2 = 0.75$) and then refined using Excel Solver's GRG Nonlinear algorithm, which optimized the four threshold boundaries simultaneously to maximize $R^2$. The optimized thresholds achieved $R^2 = 0.90$, a substantial improvement that demonstrates the value of systematic optimization for threshold-based reconstruction. The logic applies from May of the triggering water year through the following April, representing annual allocation decisions that persist through the contract year. The term appears in the Don Pedro module as it affects Stanislaus River system operations through PG&E facilities.

The Solver optimization approach was developed during the January progress meetings as a generalizable technique for any threshold-based CalSim input. By parameterizing the threshold boundaries and using a nonlinear solver to maximize correlation with historical values, the team established a repeatable workflow that avoids subjective manual threshold selection. Further detail on PGE_WY_ALLOCATION_SV is available in the {doc}`/source/input-generation/mod-other-other-variables` section.

---

## Results

The S_PEDRO change-in-storage methodology was successfully applied and validated, demonstrating that change-based QM avoids discontinuities while capturing storage dynamics responsive to runoff patterns.

:::{admonition} Suggested Plot
:class: note
Three-panel comparison: (1) Time series showing reconstructed S_PEDRO storage with water year boundaries marked, demonstrating smooth transitions without discontinuities. (2) Monthly delta-S scatter plot (Tuolumne runoff vs storage change) with QM relationship overlaid showing training and validation periods. (3) Storage trajectory for a multi-year drought sequence demonstrating continuous drawdown/recovery.
:::

Several cross-cutting patterns emerge across upper watershed module terms. Forecast and regulation terms (American storage forecasts, various minimum flows) represent operational decisions that respond to water availability through threshold or seasonal logic. Reservoir-dependent terms (E_PEDRO, S_PEDRO) require careful handling of storage-elevation-area relationships and temporal continuity. Demand and allocation terms (diversions, PG&E allocation) follow either seasonal patterns or threshold-triggered ratios based on annual hydrology assessment.

The diversity of methodologies applied to these 13 terms illustrates the flexibility required for comprehensive input reconstruction. No single approach suffices, but the toolkit of quantile mapping, water year type averaging, threshold logic, direct calculation, and change-in-storage QM provides appropriate methods for each variable's characteristics.

---

## Previous Version

### Methodology

#### Lower Yuba Module Terms

##### Channel Diversion and MFY-44

Channel diversion exhibits clear hydrologic pattern making quantile mapping the primary approach. The term shows correlation with Yuba River flows, enabling standard QM methodology with VIC output as basis. MFY-44 minimum flow shows unusual peak patterns suggesting either quantile mapping or water year type averaging may be appropriate. Validation will determine which approach best captures the operational logic driving these peaks.

##### Diversion Schedule

Diversion schedule follows regular seasonal patterns without strong correlation to individual flow years, making water year type averaging the natural methodology choice. The approach calculates monthly average diversions conditional on water year type, capturing seasonal demand patterns that vary with overall water availability without requiring year-to-year flow matching.

#### American River Module Terms

##### Storage Forecast (Three Terms)

Three American River storage forecast terms (likely P184, P185, P186) exhibit unique seasonal patterns ranging from -15 to +150 TAF with positive values after July and negative values starting January. These represent upstream flow regulation signals: reservoirs hold water in winter (negative, indicating reduced releases) and release in summer (positive, indicating augmented flows above natural patterns).

The forecast release terms feed into Folsom envelope calculations where Folsom full natural flow combines with forecast release adjustments. Initial approach attempts quantile mapping using American River unimpaired flow or temperature as basis. If correlation proves weak, fallback to water year type averaging will preserve seasonal regulation patterns conditional on overall water availability classification.

:::{admonition} Suggested Plot
:class: note
Seasonal pattern visualization showing monthly distributions for the three storage forecast terms across water year types. Include separate panels for each term with box plots by month colored by WYT, illustrating the winter reduction/summer augmentation pattern and WYT-dependent magnitude.
:::

#### Don Pedro / Stanislaus Module Terms

##### E_PEDRO (Evaporation)

Don Pedro evaporation exists in reservoir evaporation module output but requires unit conversion as the module term is expressed in CFS (flow rate) rather than depth or volume. The conversion depends on pre-processed storage time series to determine surface area, then translate evaporation depth to volumetric rate. If storage varies significantly, water year type average storage may serve as basis for area calculation, followed by evaporation depth computation and CFS conversion.

##### S_PEDRO (Storage)

Don Pedro storage reconstruction addresses pre-processed storage values used in State and Federal Project (SFP) sharing account calculations. Direct quantile mapping of storage levels creates potential water year boundary discontinuities where one year ends at high storage while the next synthetic year (from different historical analogue) starts at low storage.

The change-in-storage approach resolves this issue by quantile mapping monthly change in storage (delta-S) rather than absolute storage levels. Tuolumne River unimpaired flow serves as the basis for QM, establishing relationship between monthly runoff and storage change. Synthetic sequence storage is then computed by accumulating mapped delta-S values with appropriate initial conditions, producing continuous storage trajectories without year-boundary artifacts.

##### PG&E Water Year Allocation

PG&E Water Year Allocation (described in detail in the {doc}`/source/input-generation/mod-other-other-variables` section) determines hydropower generation water rights as function of Folsom unimpaired flow thresholds. The five-level threshold logic was initially developed through manual trial-and-error (achieving $R^2 = 0.75$) and then refined using Excel Solver's GRG Nonlinear algorithm, which optimized the four threshold boundaries simultaneously to maximize $R^2$. The optimized thresholds achieved $R^2 = 0.90$, a substantial improvement that demonstrates the value of systematic optimization for threshold-based reconstruction. The logic applies from May of the triggering water year through the following April, representing annual allocation decisions that persist through the contract year. The term appears in Don Pedro module as it affects Stanislaus River system operations through PG&E facilities.

The Solver optimization approach was developed during the January progress meetings as a generalizable technique for any threshold-based CalSim input. By parameterizing the threshold boundaries and using a nonlinear solver to maximize correlation with historical values, the team established a repeatable workflow that avoids subjective manual threshold selection.

### Results

The S_PEDRO change-in-storage methodology was successfully applied and validated, demonstrating that change-based QM avoids discontinuities while capturing storage dynamics responsive to runoff patterns.

:::{admonition} Suggested Plot
:class: note
Three-panel comparison: (1) Time series showing reconstructed S_PEDRO storage with water year boundaries marked, demonstrating smooth transitions without discontinuities. (2) Monthly delta-S scatter plot (Tuolumne runoff vs storage change) with QM relationship overlaid showing training and validation periods. (3) Storage trajectory for a multi-year drought sequence demonstrating continuous drawdown/recovery.
:::

Several cross-cutting patterns emerge across upper watershed module terms. Forecast and regulation terms (American storage forecasts, various minimum flows) represent operational decisions that respond to water availability through threshold or seasonal logic. Reservoir-dependent terms (E_PEDRO, S_PEDRO) require careful handling of storage-elevation-area relationships and temporal continuity. Demand and allocation terms (diversions, PG&E allocation) follow either seasonal patterns or threshold-triggered ratios based on annual hydrology assessment.

The diversity of methodologies applied to these 13 terms illustrates the flexibility required for comprehensive input reconstruction. No single approach suffices, but the toolkit of quantile mapping, water year type averaging, threshold logic, direct calculation, and change-in-storage QM provides appropriate methods for each variable's characteristics.
