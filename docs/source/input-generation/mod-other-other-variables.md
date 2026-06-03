# mod_other/miscellaneous

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/miscellaneous/`  
Miscellaneous operational variables
```


Miscellaneous CalSim study variables spanning flow terms, return flows, allocations, and indices that don't fit established categories. The category illustrates the breadth of reconstruction approaches needed when standard quantile mapping proves unsuitable or when variables have unique governing logic.

:::note Archived Documentation
B120 Forecasts and Water Year Type Indexes were previously documented in separate files but are now consolidated here per the final CalSim SV inventory. See `__archive/` folder for historical documentation.
:::

## Scope Analysis

| Term - Part B | Term - Part C | Methodology |
|---------------|:-------------:|:-----------:|
| TULE_WET_INDX | FLOW | Quantile Mapping |
| DELTAACCRETIONFORNDOI | FLOW | Direct Calculation |
| C_CBD001HIST | FLOW | Hybrid (QM + WYT) |
| C_KLR005HIST | FLOW | Hybrid (QM + WYT) |
| R_60N_NA4_SJR022_SV | RETURN-FLOW | Water Year Type Averaging |
| R_RFS71A_OMR039_SV | RETURN-FLOW | Water Year Type Averaging |
| EBTML_LOSS | LOSS | Water Year Type Averaging |
| CAP_C_CAA238_CVC_F, CAP_C_CAA238_CVC_R | CAPACITY | Repeating Time Series |
| YBA Transfers | -- | Dynamic WRESL Flag |

## Methodology Overview

A total of five different approaches are applied to reconstruct the miscellaneous terms, plus one term governed by a dynamic WRESL flag that requires no pre-generation:

**1- Water Year Type Monthly Averaging (WYT):** Groups historical months by water year type (Wet, Above Normal, Below Normal, Dry, Critical) and assigns the corresponding monthly mean to each synthetic year. This approach captures seasonal demand and operational patterns that vary with overall water availability but not with year-to-year flow variability. It is the preferred fallback when correlation with VIC outputs is too weak for quantile mapping, and is applied here to SJR return flows and EBMUD terminal reservoir loss.

**2- Quantile Mapping (QM):** Maps the empirical CDF of a VIC-derived predictor series to the empirical CDF of the target CalSim term, trained on 1921-1971 and applied to 1972-2018. For miscellaneous terms, the predictor is selected by screening the full VIC output library for the highest R-squared correlation to the target. This approach is applied to the Tule Wetlands Index using VIC I_PEDRO (Lake Millerton inflow) as the predictor.

**3- Hybrid (QM + WYT):** Averages the QM and WYT reconstructions to blend interannual variability with stable seasonal structure. This mitigates peak overshoot or noise that pure QM can introduce when predictor correlation is moderate, while avoiding the overly smooth patterns of pure WYT averaging. It is applied to Colusa Basin Drain and Knights Landing Ridge Cut, where QM alone produced physically unrealistic peak overshoots up to 900 TAF against a historical maximum near 500 TAF.

**4- Direct Calculation:** Applies a physical formula derived from the governing source data rather than statistical mapping. This is used for NDOI precipitation accretion, where monthly volume is computed directly from Stockton gauge precipitation depth, Delta water surface area, and a watershed area ratio coefficient -- preserving the physical relationship between precipitation and accretion volume that statistical approaches failed to reproduce.

**5- Repeating Time Series:** Identifies a representative recent period exhibiting stable, infrastructure-constrained behavior and repeats it across the full synthetic sequence. This is applied to Cross Valley Canal capacity terms whose post-2009 values reflect fixed operational limits rather than hydrology-driven variability, making statistical reconstruction unnecessary.

**6- Dynamic WRESL Flag (no pre-generation required):** Some CalSim inputs are computed endogenously by the model's WRESL scripts during simulation rather than supplied as pre-generated time series. Yuba Accord transfers fall into this category: the dynamic flag is set in the CalSim configuration so the model calculates transfers at runtime based on synthetic sequence conditions, eliminating the need for and risk of pre-specifying transfer patterns.

---

## 1. Water Year Type Averaging

Three miscellaneous terms are reconstructed using WYT monthly averaging: two San Joaquin River return flow channels and the EBMUD terminal reservoir loss.

### R_60N_NA4_SJR022_SV (Return Flow, San Joaquin River)

SJR return flow at Woodbridge Irrigation District represents agricultural drainage returns to the San Joaquin River system, cycling seasonally between near-zero winter values and peak return flows of approximately 0.7 TAF in active irrigation months. San Joaquin Valley Water Year Type monthly averaging is the adopted methodology, computing the mean monthly return flow for each of the five WYT classes and assigning the corresponding class mean to each synthetic month.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/R_60N_NA4_SJR022_SV.png
:name: fig-r60n-na4-sjr022-sv
:width: 100%
Product A validation for R_60N_NA4_SJR022_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.95$, $\text{NSE} = 0.95$, and $\text{PBIAS} = -1.4\%$. The monthly time series shows the reconstructed series closely tracking the seasonal oscillation of the actual record throughout the 1972-2018 period, with values cycling between near-zero winter lows and peaks of approximately 0.7 TAF in active irrigation months. The WYT conditioning captures the inter-annual differences in return flow magnitude, and the non-exceedance CDF shows close agreement across the full distribution, with only minor divergence at the very upper tail above the 95th percentile. The near-neutral percent bias of -1.4% confirms negligible long-term volume difference, and NSE = 0.95 indicates the WYT monthly averages fully capture the dominant seasonal and inter-annual structure of this highly regular irrigation district return flow.

### R_RFS71A_OMR039_SV (Return Flow, San Joaquin River)

Westside SJR return flow at Byron Bethany Irrigation District represents a second category of miscellaneous agricultural and municipal return flows to the San Joaquin River, with historical values reaching approximately 0.20 TAF. San Joaquin Valley Water Year Type monthly averaging is the adopted methodology, identical in structure to the R_60N approach above.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/R_RFS71A_OMR039_SV.png
:name: fig-r-rfs71a-omr039-sv
:width: 100%
Product A validation for R_RFS71A_OMR039_SV: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.50$, $\text{NSE} = 0.49$, and $\text{PBIAS} = -7.3\%$. The monthly time series shows the reconstruction capturing the seasonal timing of peak return flows, but the WYT class means consistently underestimate the magnitude of the larger historical peaks, which reach approximately 0.20 TAF in active months. The non-exceedance CDF reflects this systematic underestimation: Product A falls substantially below the historical curve across the upper 40% of the distribution, indicating the reconstruction compresses the upper tail of the return flow distribution. The moderate $R^2$ reflects the episodic, event-driven nature of this agricultural return flow, where individual peak events driven by storm runoff and irrigation scheduling cannot be captured by WYT-conditioned monthly means. The PBIAS of -7.3% confirms the modest low-side volume bias. Given the absence of a stronger predictive relationship across the VIC predictor library and the relatively low volumes involved, the WYT reconstruction is accepted as the best available approach for this term.

### EBTML_LOSS (Loss, EBMUD Terminal Reservoir Loss)

East Bay Municipal Utility District terminal reservoir loss represents operational evaporation and seepage losses from EBMUD terminal storage facilities, exhibiting a highly consistent seasonal pattern between approximately 11 CFS in winter and 35 CFS in summer. Water year type averaging was selected for consistency with the broader project framework, though a repeating time series approach would also have been viable given the stable post-2009 behavior.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/EBTML_LOSS.png
:name: fig-ebtml-loss
:width: 100%
Product A validation for EBTML_LOSS: monthly time series (left) and non-exceedance CDF (right) comparing WYT-reconstructed Product A against historical record over 1972-2018.
```

The reconstruction achieves $R^2 = 0.99$, $\text{NSE} = 0.99$, and $\text{PBIAS} = -0.8\%$. The monthly time series shows the reconstructed series nearly indistinguishable from the actual record throughout the 1972-2018 period, with values cycling between approximately 0.7 TAF in winter and 2.2 TAF in summer. The non-exceedance CDF shows the two curves overlapping almost exactly across the full distribution. The near-neutral percent bias of -0.8% confirms negligible long-term volume difference. The exceptionally strong fit reflects the high regularity of EBMUD's operational loss pattern: because terminal reservoir losses are governed primarily by season and infrastructure capacity rather than year-to-year hydrologic variability, WYT-conditioned monthly means fully capture both the seasonal and inter-annual structure of this term.

---

## 2. Quantile Mapping

One miscellaneous term is reconstructed using quantile mapping, with the predictor identified by screening the full VIC output library for the highest R-squared correlation to the target.

### TULE_WET_INDX (Flow, Tulare Basin Wetlands Index)

The Tule Wetlands Index represents wetland conditions in the Tulare Basin, reconstructed through quantile mapping using VIC I_PEDRO (Lake Millerton inflow) as the predictor -- the highest R-squared match identified across the full VIC output screening. The QM relationship is trained on 1921-1971 and applied to 1972-2018. While the predictor correlation of $R^2 = 0.71$ sits at the lower threshold for effective quantile mapping, the approach preserves the statistical relationship between Millerton inflows and wetland conditions that WYT averaging alone cannot capture.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/TULE_WET_INDX_timeseries.png
:name: fig-tule-wet-indx
:width: 100%
Product A validation for TULE_WET_INDX: monthly time series (left) and non-exceedance CDF (right) comparing QM-reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.70$, $\text{NSE} = 0.52$, and $\text{PBIAS} = 5.0\%$. The monthly time series captures the spiky pulse pattern of the wetlands index -- near-zero base values punctuated by sharp wet-season peaks reaching 50-175 TAF -- and the inter-annual alternation between high- and low-flow years is broadly reproduced. The non-exceedance CDF shows close alignment through most of the distribution, with the two curves overlapping well from the 10th through approximately the 90th percentile.

The moderate NSE of 0.52 reflects the difficulty QM faces in reproducing the timing and precise magnitude of individual peak events: the reconstruction over- and under-estimates specific peaks throughout the record, leading to the squared-deviation penalties that suppress NSE relative to $R^2$. The slight positive PBIAS of 5.0% indicates the reconstruction runs marginally high on average across the 1972-2018 period. Despite these limitations, $R^2 = 0.70$ -- matching the predictor correlation -- confirms the QM approach preserves the statistical relationship between Millerton inflows and wetland conditions that WYT averaging alone could not capture.

---

## 3. Hybrid (QM + WYT)

Two miscellaneous flow terms employ the hybrid methodology, combining quantile mapping and WYT averaging to handle cases where neither approach alone performs adequately without producing physically unrealistic peak overshoots. Both terms are approximately 95% correlated with each other and share the same VIC predictor.

### C_CBD001HIST (Flow, Colusa Basin Drain)

Colusa Basin Drain represents combined USGS gauge flows through a drainage channel returning agricultural and flood waters to the Sacramento River system, with annual peaks sometimes reaching 500 TAF. VIC flow correlation testing across approximately 200 locations identified `IERC_003` as the best predictor, achieving $R^2 = 0.70$. While this approaches the 0.7 threshold for standard quantile mapping, QM alone produced extreme peak overshoots up to 900 TAF -- physically unrealistic values that would cause CalSim to simulate impossible drainage flows. The hybrid approach averages the QM and WYT reconstructions to eliminate overshoots while preserving more realistic inter-annual variability than pure WYT averaging:

$$V_{hybrid} = \frac{V_{QM} + V_{WYT}}{2}$$

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_CBD001HIST.png
:name: fig-c-cbd001hist
:width: 100%
Product A validation for C_CBD001HIST: monthly time series (left) and non-exceedance CDF (right) comparing hybrid-reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.68$, $\text{NSE} = 0.66$, and $\text{PBIAS} = -11.5\%$. The monthly time series shows the reconstruction broadly tracking the inter-annual variability of the Colusa Basin Drain record -- capturing the seasonal pulse pattern and the contrast between wet and dry years -- with the hybrid averaging successfully constraining peak values within physically plausible bounds below 600 TAF. The non-exceedance CDF shows good agreement through the lower 90% of the distribution, with the two curves closely aligned across the moderate-flow range that dominates the record.

The PBIAS of -11.5% reflects a systematic underestimation of the largest historical peaks: the reconstruction tends to underestimate events above 200 TAF, visible as the slight divergence of the Product A CDF below the historical curve in the upper tail above the 95th percentile. The largest historical peaks (approaching 600 TAF in 1997 and 2019) are partially captured but not fully reproduced, consistent with the smoothing inherent in the hybrid approach. Overall, the hybrid reconstruction represents a major improvement over QM alone, which produced physically unrealistic peak overshoots up to 900 TAF, and the combination of $R^2 = 0.68$ and NSE = 0.66 confirms that the approach successfully captures the dominant inter-annual variability of this drainage channel.

### C_KLR005HIST (Flow, Knights Landing Ridge Cut)

Knights Landing Ridge Cut represents a second Sacramento Valley drainage channel with approximately 95% correlation to Colusa Basin Drain. The same `IERC_003` predictor achieves $R^2 = 0.52$ for this term -- well below the quantile mapping threshold -- and QM alone produced the same category of extreme peak overshoots as for C_CBD001HIST. The hybrid methodology is applied identically, averaging QM and WYT reconstructions to constrain values within historical ranges while maintaining appropriate variability.

#### Validation

```{figure} ../figures/calsim-run-product-a/full-validation/C_KLR005HIST.png
:name: fig-c-klr005hist
:width: 100%
Product A validation for C_KLR005HIST: monthly time series (left) and non-exceedance CDF (right) comparing hybrid-reconstructed Product A against historical record over 1972-2018.
```

Product A validation over 1972-2018 yields $R^2 = 0.75$, $\text{NSE} = 0.75$, and $\text{PBIAS} = -4.5\%$. The monthly time series shows the reconstruction closely tracking the inter-annual variability of the Knights Landing Ridge Cut record, with the hybrid approach again constraining peak values within physical bounds while preserving meaningful year-to-year flow signal. The non-exceedance CDF demonstrates notably strong agreement: the two curves remain closely aligned from the 0th through approximately the 97th percentile, with divergence only at the very extreme upper tail where the largest historical peaks (approaching 600 TAF) are partially underestimated.

The near-neutral PBIAS of -4.5% confirms negligible long-term volume bias -- a marked improvement over C_CBD001HIST -- consistent with the higher $R^2 = 0.75$ that reflects the stronger response of this channel to the shared `IERC_003` predictor after hybrid blending. The substantially better performance relative to the pre-hybrid QM-only result, combined with elimination of the extreme peak overshoots, confirms that the hybrid methodology is the appropriate reconstruction approach for this term.

---

## 4. Direct Calculation

One miscellaneous term is reconstructed through a direct physical formula derived from the governing source data, rather than through statistical mapping.

### DELTAACCRETIONFORNDOI (Flow, NDOI Precipitation Accretion)

NDOI precipitation accretion represents direct precipitation onto Delta water surfaces used in Dayflow calculations. Multiple statistical approaches were evaluated and rejected before the direct calculation method was adopted. The formula computes monthly accretion volume as precipitation depth converted to volume with time-varying area adjustments:

$$V_{precip} = \frac{P_{Stockton}}{12} \times A_{Delta} \times C_{ratio}$$

where $P_{Stockton}$ is monthly precipitation depth in inches from the Stockton gauge, $A_{Delta}$ is the Delta water surface area in acres varying across three defined time periods covering 1930-2010 land use changes, and $C_{ratio}$ is a watershed area adjustment coefficient. The December 2025 progress meeting confirmed this approach as superior to statistical methods since it preserves the physical relationship between precipitation and accretion volume.

#### Validation

```{figure} figures/s3-inputs_other-ndoi-precip-accretion.png
:name: fig-ndoi-precip-accretion
:width: 100%
Product A validation for DELTAACCRETIONFORNDOI: actual CalSim input DSS (blue) vs. reconstructed values (orange), WY 1971--2018. Overall agreement is strong; reconstructed values spike above actuals in a few wet years (notably ~720 TAF in 1993 and ~870 TAF in 1998).
```

The direct calculation approach achieves $R^2 = 0.92$, improving on the earlier QM approach ($R^2 = 0.87$). The mean reconstructed value of 63.3 TAF compares to a mean actual of 69.3 TAF, reflecting slightly lower precipitation in the Product A synthetic climate. Some reconstructed values spike above historical actuals in extreme wet years; the current approach preserves the full range of statistically plausible events consistent with stochastic planning objectives to explore distribution tails.

---

## 5. Repeating Time Series

Two Cross Valley Canal capacity terms employ a repeating time series, using the stable post-2009 period as the representative pattern repeated across the full synthetic sequence.

### CAP_C_CAA238_CVC_F and CAP_C_CAA238_CVC_R (Capacity, Cross Valley Canal)

Forward and reverse conveyance capacity constraints on the Cross Valley Canal do not vary with hydrology in the historical record, reflecting fixed infrastructure limits rather than dynamic allocation. Post-2009 values exhibit consistent behavior indicative of operational capacity limits set by physical canal infrastructure. The repeating time series methodology uses this stable recent period as the representative pattern, applied across both the 1921-2018 historical reconstruction and all Product B synthetic sequences.

---

## 6. Dynamic WRESL Flag

One miscellaneous term requires no pre-generation because it is computed endogenously by CalSim's WRESL scripts during simulation.

### YBA Transfers (Dynamic, Yuba Accord)

Yuba Accord transfers are flagged as dynamic within the DCR CalSim WRESL scripts, enabling simulation-time calculation based on operational rules rather than pre-specified input time series. The dynamic flag was confirmed during inventory review with MSO staff, who verified that CalSim's WRESL logic computes Yuba Accord transfers endogenously based on Yuba water availability and downstream demand conditions -- making pre-generation both unnecessary and potentially conflicting with the model's internal logic.


