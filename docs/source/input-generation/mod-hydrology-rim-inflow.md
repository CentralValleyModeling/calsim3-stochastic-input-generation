# mod_hydrology/rim_inflow

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/rim_inflow/`  
Quantile mapping of VIC inflows to CalSim rim inflow series
```


Rim inflows represent streamflow entering the CalSim 3 model domain from surrounding mountain and foothill watersheds. They are major hydrologic drivers of reservoir inflows and downstream streamflows in the modeled river and tributary network, making their accurate reconstruction one of the most consequential components of the stochastic input generation effort. Of the 241 total rim inflow variables, 227 require stochastic generation (13 have missing historical data and 1 is unused). Rim inflow generation proceeds in two stages. The VIC hydrologic model first simulates streamflow across the domain, and quantile mapping then corrects those simulations to the distribution of the historical CalSim 3 inputs. VIC is run in two configurations. Product A is forced with a WGEN historical-parallel climate sequence and is used to train and validate the quantile mapping; Product B is forced with WGEN's 1,000-year stochastic climate and produces the synthetic traces delivered to CalSim 3. The quantile mapping is applied monthly, followed by basin level anchor adjustments that enforce mass balance between tributary inflows and their downstream aggregate watershed inflow. The validation figures on this page are all computed on Product A, comparing the Product A VIC reconstruction against the CalSim 3 historical record.

## Methodology

The methodology has four parts: correlation analysis, model selection, applying quantile mapping to each rim inflow, and enforcing mass balance across tributaries through anchor watershed adjustments.

### Correlation Analysis

The methodology development began with a systematic correlation analysis, matching each of the 227 CalSim rim inflow variables against modeled streamflow locations from both SAC-SMA and VIC hydrologic models to identify the strongest statistical predictors. Every one of the 227 variables had a corresponding VIC simulated streamflow series, and the correlations were strong: more than 80% reached an R² above 0.6 and over 60% exceeded 0.7.

### Model Selection

An early methodological choice involved selecting which hydrologic model would simulate the rim inflow streamflow: SAC-SMA or VIC. Both are rainfall-runoff models that convert climate forcings into streamflow. SAC-SMA produced higher average $R^2$ values against historical CalSim inputs, attributed to its watershed level calibration, whereas VIC is calibrated more broadly across the gridded domain. However, VIC remains the basis model for consistency with DWR's CalSim 3 climate change hydrology, which is likewise built on VIC (DWR 2023). Raw VIC streamflow tends to run wetter than the CalSim 3 historical inputs, but quantile mapping corrects that kind of systematic bias. The VIC modeling process is described in [mod_forcing/vic](mod-forcing-vic.md).

### Quantile Mapping Procedure

The rim inflow procedure follows the general quantile-mapping framework described in [Quantile Mapping](../methods.md#quantile-mapping). Quantile mapping is performed separately for each calendar month to preserve seasonal patterns in runoff. For each rim inflow variable, the corresponding VIC streamflow serves as the basis series (the series being corrected), and the historical CalSim 3 rim inflow (e.g., I_FOLSM, UNIMP_OROV) serves as the target series (the reference).

For the historical validation reported below, the mapping is trained on WY 1922-1971 and validated on WY 1972-2018, so the corrected Product A flows are scored against historical CalSim 3 inputs from outside the training period. For rim inflow generation, the Product B quantile mapping is trained on the full Product A overlap (Oct 1921-Dec 2018) and then applied to the 1,000-year stochastic VIC sequence.

Within the historical range the quantile mapping uses empirical monthly quantiles, and for synthetic values outside that range it relies on Gamma-distribution tail extrapolation. When a synthetic value falls below the entire historical range, the lower tail is extrapolated by taking the smallest observed target value and subtracting an increment from the fitted Gamma distribution; for months whose flows are already near zero, this can push the result slightly below zero. Because negative rim inflows are not physically meaningful, any negative mapped values are reset to zero.

### Anchor Watershed Mass Balance

Because quantile mapping is applied independently to each rim inflow, the corrected upstream tributary flows no longer necessarily sum to their downstream aggregate watershed flow. To restore mass balance, an anchor watershed adjustment is applied. The approach recognizes that VIC model outputs are more reliable at integrated watershed scales than for individual small tributaries, so major downstream locations, represented by quantile-mapped unimpaired watershed flows (e.g., UNIMP_FOLS), serve as "anchor" control points, and upstream tributary flows (e.g., I_ALD002) are adjusted to ensure they sum correctly to the anchor totals.

Ten anchor watersheds are defined in total, six of which require tributary adjustment: Folsom (FOLS), the largest with 46 tributaries, followed by Oroville (OROV), Sacramento River at Bend Bridge (SRBB), Yuba (YUBA), Stanislaus (ST), and Tuolumne (TU). Together these six basins account for 116 of the 227 generated rim inflows. Of the remaining four, three (Trinity, Merced, and San Joaquin) have no assigned subtributaries, so their quantile-mapped flows are used directly without adjustment. Shasta is the exception: its inflow (I_SHSTA) is itself one of the eight Bend Bridge tributaries, so it is mass balance adjusted under SRBB rather than used directly. This is why the aggregate error figures below show nine anchors (Shasta absorbed into Bend Bridge), even though Shasta still appears as its own panel in the per-location comparisons.

The Bend Bridge anchor (UNIMP_SRBB) is quantile-mapped against a composite VIC routing rather than the Shasta-inflow routing it previously borrowed. The Shasta routing stops at the dam and omits the drainage between Shasta and the Bend Bridge gauge (CalSim node SAC257), under-representing the anchor by roughly 30 percent. The composite (`CS3_8RI_SRBB`) is routed directly by `mod_forcing/vic/_2_compile_rim_inflows.py` from a merged grid-weight file (`reference/GridInfo/CS3_8RI_SRBB_GridInfo.txt`) that combines the Shasta drainage with the seven tributaries the CalSim 3 domain GIS tags as draining above SAC257: Cow, Battle, Bear, Clear (and Clear inflow to Whiskeytown), Cottonwood, and South Fork Cottonwood creeks. Routing the merged cells as a single basin produces the Bend Bridge inflow the same way every other rim point is computed. The Merced (Lake McClure) and San Joaquin (Millerton) anchors already coincide with their index gauges and need no such composite.

The adjustment formula distributes any discrepancy proportionally among tributaries based on their contribution to the total:

$$\text{Trib}_{\text{adjust}} = \left(\text{Anchor}_{\text{QM}} - \sum \text{Tribs}_{\text{QM}}\right) \times \frac{\text{Trib}_{\text{QM}}}{\sum \text{Tribs}_{\text{QM}}}$$

$$\text{Trib}_{\text{final}} = \text{Trib}_{\text{QM}} + \text{Trib}_{\text{adjust}}$$

This ensures that the downstream anchor flow equals the sum of all upstream tributary contributions, maintaining hydrologic mass balance while allowing individual tributary flows to reflect their quantile-mapped distributions.

```{mermaid}
flowchart TD
    VIC["VIC Streamflow Outputs"] --> QM_ANC["Quantile Map\nAnchor Watershed\n(e.g., UNIMP_FOLS)"]
    VIC --> QM_T1["Quantile Map\nTributary 1"]
    VIC --> QM_T2["Quantile Map\nTributary 2"]
    VIC --> QM_TN["Quantile Map\nTributary N"]

    QM_ANC --> COMPARE{"Anchor QM =\nSum of Tribs QM?"}
    QM_T1 --> SUM["Sum Tributary QMs"]
    QM_T2 --> SUM
    QM_TN --> SUM
    SUM --> COMPARE

    COMPARE -->|Yes| DONE["No Adjustment Needed"]
    COMPARE -->|No| RESIDUAL["Compute Residual\nAnchor_QM - Sum_Tribs_QM"]
    RESIDUAL --> DIST["Distribute Proportionally\nby Tributary Share"]
    DIST --> ADJ1["Trib 1 Final =\nTrib 1 QM + Adjustment"]
    DIST --> ADJ2["Trib 2 Final =\nTrib 2 QM + Adjustment"]
    DIST --> ADJN["Trib N Final =\nTrib N QM + Adjustment"]

    style QM_ANC fill:#264653,color:#fff
    style DONE fill:#2d6a4f,color:#fff
    style ADJ1 fill:#2d6a4f,color:#fff
    style ADJ2 fill:#2d6a4f,color:#fff
    style ADJN fill:#2d6a4f,color:#fff
```

_Anchor watershed mass balance adjustment. After independent quantile mapping, tributary flows are proportionally adjusted so their sum matches the anchor watershed total._

## Results

Quantile mapping substantially improved monthly skill across the rim inflow network. On the normalized skill scale of the skill figure below, the network average rose from 0.68 (raw VIC) to 0.79. Monthly bias also fell markedly at the major anchor watersheds.

The figure below summarizes this improvement across the full network. Skill is expressed as normalized NSE, $1/(2-\text{NSE})$, which maps NSE onto the 0-1 range (0.5 corresponds to NSE = 0 and 1.0 to a perfect score). The two curves are sorted independently, so the figure compares the distribution of skill rather than location by location pairs: quantile mapping shifts the entire distribution upward, with the largest gains in the low-skill tail, where the poorest performing locations rise from near zero to about 0.4.

```{image} figures/s3-inputs_rim-inflow-skill-normalized-nse.png
:alt: Rim Inflow Skill (Normalized NSE)
:width: 60%
:align: center
```

_Monthly skill (normalized NSE) across all CalSim 3 rim inflow locations, sorted lowest to highest, for raw VIC (blue) and quantile-mapped (VIC-QMAP, red) flows._

The validation demonstrated that seasonal patterns were successfully restored and bias in monthly exceedance was reduced across the board. The NSE improvements reflect not just distributional correction but genuine restoration of the relationship between synthetic and historical flows at monthly timesteps.

### Monthly Validation at Rim Inflow Anchors

Several challenges were identified during the validation process. Spring bias during April through June remains the most persistent issue for Bend Bridge, Oroville, and Yuba, where VIC tends to overestimate spring snowmelt contributions even after quantile mapping corrects distributional characteristics. Folsom showed unexpected negative bias after mapping due to VIC's drying trend over the simulation period--a clear example of the trend inheritance limitation discussed in the quantile mapping methodology section. Millerton shows persistent dry bias in May and June despite overall improvements, likely reflecting VIC's difficulty in capturing the San Joaquin's snowmelt timing.

```{image} figures/s3-inputs_rim-inflow-monthly-error-anchors.png
:alt: Average Monthly Error at Anchor Watersheds
:width: 100%
:align: center
```

_Average monthly error relative to CalSim 3 (TAF/month) at the rim inflow anchors, WY 1972--2018, for raw VIC (left) and VIC-QMAP (right) flows._

The panels below show each of the ten rim inflow anchors over the validation period
(WY 1972--2018): average monthly flow for the CalSim 3 historical target (black), raw VIC
(blue), and quantile-mapped VIC (VIC-QMAP, red), with box plots of annual water-year totals at
right. The Folsom panel illustrates the typical correction, where quantile mapping removes raw
VIC's overestimated spring peak and restores the missing summer baseflow.

::::{tab-set}
:::{tab-item} Bend Bridge
![Bend Bridge (UNIMP_SRBB) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_SRBB.png)
:::
:::{tab-item} Shasta
![Shasta (I_SHSTA) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_I_SHSTA.png)
:::
:::{tab-item} Oroville
![Oroville (UNIMP_OROV) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_OROV.png)
:::
:::{tab-item} Folsom
![Folsom (UNIMP_FOLS) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_FOLS.png)
:::
:::{tab-item} Yuba
![Yuba (UNIMP_YUBA) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_YUBA.png)
:::
:::{tab-item} Tuolumne
![Tuolumne (UNIMP_TU) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_TU.png)
:::
:::{tab-item} San Joaquin
![San Joaquin (UNIMP_SJ) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_SJ.png)
:::
:::{tab-item} Trinity
![Trinity (UNIMP_TRIN) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_TRIN.png)
:::
:::{tab-item} Stanislaus
![Stanislaus (UNIMP_ST) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_ST.png)
:::
:::{tab-item} Merced
![Merced (UNIMP_ME) monthly average flow](figures/rim-inflow-monthly-avg/Monthly_Avg_UNIMP_ME.png)
:::
::::

_Average monthly flow and annual water-year totals at each rim inflow anchor, WY 1972--2018._

### Annual Validation at Rim Inflow Anchors

Annual errors shrink markedly at some anchors (e.g., Oroville) but grow or change sign at
others (e.g., Bend Bridge, Folsom, Trinity), reflecting that monthly quantile mapping does not
directly constrain annual totals.

```{image} figures/s3-inputs_rim-inflow-annual-error-anchors.png
:alt: Average Annual Error at Anchor Watersheds
:width: 70%
:align: center
```

_Average annual error relative to CalSim 3 (TAF/year) at the rim inflow anchors, WY 1972--2018, for raw VIC (blue) and VIC-QMAP (red) flows._

The percentage error metric showed that 50% of locations fell within the -15% to +18% range. Extreme percentage errors (up to 79,000% at one location) occur exclusively at near-zero baseline values where even modest absolute differences produce outsized percentages. These extreme percentages do not indicate meaningful reconstruction failure; the underlying absolute errors remain small.

The panels below show the annual (water-year total) flow and its 5-year mean at each of the ten
anchor watersheds, comparing the CalSim 3 historical target (black), raw VIC (blue), and
quantile-mapped VIC (VIC-QMAP, red) flows. Quantile mapping is trained on WY 1922--1971 and
applied over the shaded validation period (WY 1972--2018), so the VIC-QMAP trace begins in
WY 1972. The annual series shows how well year-to-year variability and extremes are reproduced,
while the 5-year mean (labeled by middle water year) shows the persistence of multi-year wet and
dry periods such as the 1976--77 and 1987--92 droughts.

::::{tab-set}
:::{tab-item} Bend Bridge
![Bend Bridge (UNIMP_SRBB) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_SRBB.png)
![Bend Bridge (UNIMP_SRBB) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_SRBB.png)
:::
:::{tab-item} Shasta
![Shasta (I_SHSTA) annual flow](figures/rim-inflow-annual-ts/Annual_TS_I_SHSTA.png)
![Shasta (I_SHSTA) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_I_SHSTA.png)
:::
:::{tab-item} Oroville
![Oroville (UNIMP_OROV) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_OROV.png)
![Oroville (UNIMP_OROV) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_OROV.png)
:::
:::{tab-item} Folsom
![Folsom (UNIMP_FOLS) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_FOLS.png)
![Folsom (UNIMP_FOLS) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_FOLS.png)
:::
:::{tab-item} Yuba
![Yuba (UNIMP_YUBA) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_YUBA.png)
![Yuba (UNIMP_YUBA) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_YUBA.png)
:::
:::{tab-item} Tuolumne
![Tuolumne (UNIMP_TU) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_TU.png)
![Tuolumne (UNIMP_TU) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_TU.png)
:::
:::{tab-item} San Joaquin
![San Joaquin (UNIMP_SJ) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_SJ.png)
![San Joaquin (UNIMP_SJ) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_SJ.png)
:::
:::{tab-item} Trinity
![Trinity (UNIMP_TRIN) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_TRIN.png)
![Trinity (UNIMP_TRIN) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_TRIN.png)
:::
:::{tab-item} Stanislaus
![Stanislaus (UNIMP_ST) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_ST.png)
![Stanislaus (UNIMP_ST) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_ST.png)
:::
:::{tab-item} Merced
![Merced (UNIMP_ME) annual flow](figures/rim-inflow-annual-ts/Annual_TS_UNIMP_ME.png)
![Merced (UNIMP_ME) 5-year mean annual flow](figures/rim-inflow-annual-ts/Annual_5Y_Mean_TS_UNIMP_ME.png)
:::
::::

_Annual flow (top) and centered 5-year mean annual flow (bottom) at each rim inflow anchor, WY 1922--2018. VIC-QMAP begins in WY 1972; the shaded band marks the validation period._

## References

California Department of Water Resources (DWR). 2023. *Risk-Informed Future Climate Scenario Development for the State Water Project Delivery Capability Report*. Methodology report for the 2023 Delivery Capability Report (DCR 2023) climate change scenarios. <https://deltacouncil.ca.gov/pdf/science-program/2023-08-24-dwr-report-risk-informed-future-climate-scenario-development.pdf>
