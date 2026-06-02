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

```{figure} figures/s3-inputs_other-return-flows-r60n.png
:name: fig-r60n-return-flow
:width: 100%
Product A validation for R_60N_NA4_SJR022_SV: WYT-based reconstruction (orange) vs. actual CalSim inputs (blue), 1921--2021. Values oscillate between 0 and approximately 0.7 TAF.
```

The reconstruction achieves $R^2 = 0.97$, demonstrating that seasonal patterns conditional on water year type fully capture the dominant behavior of this highly regular irrigation district return flow.

### R_RFS71A_OMR039_SV (Return Flow, San Joaquin River)

Westside SJR return flow at Byron Bethany Irrigation District represents a second category of miscellaneous agricultural and municipal return flows to the San Joaquin River, with historical values reaching approximately 0.20 TAF. San Joaquin Valley Water Year Type monthly averaging is the adopted methodology, identical in structure to the R_60N approach above.

#### Validation

```{figure} figures/s3-inputs_other-return-flows-rfs71a.png
:name: fig-rrfs71a-return-flow
:width: 100%
Product A validation for R_RFS71A_OMR039_SV: WYT-based reconstruction (orange) vs. actual CalSim inputs (blue), 1921--2021. Reconstruction captures the seasonal timing but underestimates peak magnitudes reaching approximately 0.20 TAF.
```

The reconstruction achieves $R^2 = 0.55$, which is considered acceptable given the relatively low volumes involved and the absence of stronger predictive relationships across the VIC predictor library.

### EBTML_LOSS (Loss, EBMUD Terminal Reservoir Loss)

East Bay Municipal Utility District terminal reservoir loss represents operational evaporation and seepage losses from EBMUD terminal storage facilities, exhibiting a highly consistent seasonal pattern between approximately 11 CFS in winter and 35 CFS in summer. Water year type averaging was selected for consistency with the broader project framework, though a repeating time series approach would also have been viable given the stable post-2009 behavior.

#### Validation

```{figure} figures/s3-inputs_other-ebtml-loss.png
:name: fig-ebtml-loss
:width: 100%
Product A validation for EBTML_LOSS: WYT-based reconstruction (orange) closely overlaps actual CalSim inputs (blue), 1921--2021. Seasonal values oscillate between approximately 11 CFS in winter and 35 CFS in summer.
```

The reconstruction achieves $R^2 = 0.99$, an exceptionally strong fit reflecting the regularity of EBMUD's operational loss pattern. The near-perfect agreement confirms that WYT-conditioned monthly means fully capture the seasonal and inter-annual structure of this term.

---

## 2. Quantile Mapping

One miscellaneous term is reconstructed using quantile mapping, with the predictor identified by screening the full VIC output library for the highest R-squared correlation to the target.

### TULE_WET_INDX (Flow, Tulare Basin Wetlands Index)

The Tule Wetlands Index represents wetland conditions in the Tulare Basin, reconstructed through quantile mapping using VIC I_PEDRO (Lake Millerton inflow) as the predictor -- the highest R-squared match identified across the full VIC output screening. The QM relationship is trained on 1921-1971 and applied to 1972-2018. While the predictor correlation of $R^2 = 0.71$ sits at the lower threshold for effective quantile mapping, the approach preserves the statistical relationship between Millerton inflows and wetland conditions that WYT averaging alone cannot capture.

#### Validation

Validation over 1,248 months (WY 1915-2018) achieved $R^2 = 0.86$ with RMSE = 11.61 and mean difference of +0.30. The reconstructed time series maintains physical bounds, with bias differences comparable to other regional terms.

---

## 3. Hybrid (QM + WYT)

Two miscellaneous flow terms employ the hybrid methodology, combining quantile mapping and WYT averaging to handle cases where neither approach alone performs adequately without producing physically unrealistic peak overshoots. Both terms are approximately 95% correlated with each other and share the same VIC predictor.

### C_CBD001HIST (Flow, Colusa Basin Drain)

Colusa Basin Drain represents combined USGS gauge flows through a drainage channel returning agricultural and flood waters to the Sacramento River system, with annual peaks sometimes reaching 500 TAF. VIC flow correlation testing across approximately 200 locations identified `IERC_003` as the best predictor, achieving $R^2 = 0.70$. While this approaches the 0.7 threshold for standard quantile mapping, QM alone produced extreme peak overshoots up to 900 TAF -- physically unrealistic values that would cause CalSim to simulate impossible drainage flows. The hybrid approach averages the QM and WYT reconstructions to eliminate overshoots while preserving more realistic inter-annual variability than pure WYT averaging:

$$V_{hybrid} = \frac{V_{QM} + V_{WYT}}{2}$$

#### Validation

The hybrid approach improved reconstruction performance from $R^2 = 0.70$ (QM only) to $R^2 = 0.78$. Nash-Sutcliffe Efficiency showed even more dramatic improvement as the squared deviation penalty in NSE heavily weights the eliminated extreme overshoots.

### C_KLR005HIST (Flow, Knights Landing Ridge Cut)

Knights Landing Ridge Cut represents a second Sacramento Valley drainage channel with approximately 95% correlation to Colusa Basin Drain. The same `IERC_003` predictor achieves $R^2 = 0.52$ for this term -- well below the quantile mapping threshold -- and QM alone produced the same category of extreme peak overshoots as for C_CBD001HIST. The hybrid methodology is applied identically, averaging QM and WYT reconstructions to constrain values within historical ranges while maintaining appropriate variability.

#### Validation

The hybrid approach improved reconstruction performance from $R^2 = 0.52$ (QM only) to $R^2 = 0.66$. As with Colusa Basin Drain, NSE improvement was substantial due to elimination of the extreme QM overshoots.

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


