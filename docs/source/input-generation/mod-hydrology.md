# Hydrology (mod_hydrology)

Sacramento Valley, East Side, rim inflow, Delta, water year types, small watersheds, and Tulare groundwater processing.

---

## Rim Inflows (241 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/rim_inflow/`  
Quantile mapping of VIC inflows to CalSim rim inflow series
```


Rim inflows represent streamflow entering the CalSim 3 model domain from surrounding watersheds. They are the primary hydrologic drivers of reservoir inflows and river flows throughout the Central Valley, and their accurate reconstruction is arguably the single most consequential component of the stochastic generation effort. Of the 241 total rim inflow variables, 227 require stochastic generation (13 have missing historical data and 1 is unused). All 227 generated rim inflow locations have been processed through the quantile mapping methodology with comprehensive validation.

### Methodology

#### Correlation Analysis and VIC Selection

The methodology development began with a systematic correlation analysis, matching each of the approximately 252 CalSim inflow variables against 32 modeled streamflow locations from both SAC-SMA and VIC hydrologic models to identify the strongest statistical predictors. Of the 227 generated variables, all had direct VIC counterparts, with 80% showing correlations exceeding 0.6 and approximately 50% exceeding 0.7.

An important early decision point arose when SAC-SMA showed higher average R^2 values than VIC, attributed to SAC-SMA's superior watershed-level calibration. However, the team elected to maintain VIC as the basis model for consistency with the CalSim 3 framework and to avoid the complexity of managing multiple hydrologic models within the generation pipeline. VIC-modeled flows carry an approximately 25-30% positive bias compared to CalSim 3 historical inputs, but quantile mapping is specifically designed to correct such distributional mismatches, making the magnitude of raw bias less important than the strength of the underlying correlation.

Variable naming was verified against the WRESL codebase to ensure correct variable identification. For example, the Folsom watershed uses the naming convention I_FOLSM rather than FOLSM_INFLOW or FOLSOM_INFLOW--a distinction confirmed by searching the WRESL code for active variable references.

#### Quantile Mapping Procedure

VIC model streamflow serves as the basis for quantile mapping to CalSim 3 historical rim inflows. The procedure uses monthly stratification to preserve seasonal patterns, with Gamma distribution tail extrapolation for extreme values. Zero-clipping was added to the quantile mapping function to prevent negative flows, which can occur when Gamma tail extrapolation extends below zero for months with near-zero distributions.

#### Anchor Watershed Mass Balance

To ensure mass balance consistency across river basins after quantile mapping, an anchor watershed adjustment methodology is applied. The approach recognizes that VIC model outputs are more reliable at integrated watershed scales than for individual small tributaries. Major downstream locations serve as "anchor" control points--quantile-mapped unimpaired watershed flows (e.g., UNIMP_FOLS)--and upstream tributary flows (e.g., I_ALD002) are adjusted to ensure they sum correctly to the anchor totals.

Six major anchor watersheds require adjustment: Folsom (FOLS, 46 tributaries--the largest), Oroville (OROV), Sacramento River at Bend Bridge (SRBB), Yuba (YUBA), Stanislaus (ST), and Tuolumne (TU). A total of 116 of the 227 tributary flows are adjusted through this process. Four additional anchor watersheds--Shasta, Trinity, Merced, and San Joaquin--have no assigned sub-tributaries and require no adjustment.

The adjustment formula distributes any discrepancy proportionally among tributaries based on their contribution to the total:

$$\text{Trib}{\text{adjust}} = \left(\text{Anchor}{\text{QM}} - \sum \text{Tribs}_{\text{QM}}\right) \times \frac{\text{Trib}_{\text{QM}}}{\sum \text{Tribs}_{\text{QM}}}$$

$$\text{Final Flow} = \text{Trib}_{\text{QM}} + \text{Trib}_{\text{adjust}}$$

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

### Results

The quantile mapping methodology achieved substantial improvements across the rim inflow network. The average NSE improved by 0.10 points compared to raw VIC flows, and approximately 80% of total CalSim 3 rim inflow volume achieved NSE of 0.78 or better after quantile mapping. The minimum NSE was raised from 0.3 to 0.6 for the poorest performing locations. Monthly bias was reduced by approximately 50% at major anchor watersheds, with Shasta's annual error declining from 750 TAF to 375 TAF. Trinity's enormous negative bias in raw VIC was nearly eliminated through quantile mapping.

These results were first presented at Progress Meeting 2, where the validation demonstrated that seasonal patterns were successfully restored and bias in monthly exceedance was reduced across the board. The NSE improvements reflect not just distributional correction but genuine restoration of the relationship between synthetic and historical flows at monthly timesteps.

Several challenges were identified during the validation process. Spring bias during April through June remains the most persistent issue for Shasta, Oroville, and Yuba, where VIC tends to overestimate spring snowmelt contributions even after quantile mapping corrects distributional characteristics. Folsom showed unexpected negative bias after mapping due to VIC's drying trend over the simulation period--a clear example of the trend inheritance limitation discussed in the quantile mapping methodology section. Millerton shows persistent dry bias in May and June despite overall improvements, likely reflecting VIC's difficulty in capturing the San Joaquin's snowmelt timing.

The percentage error metric showed that 50% of locations fell within the -15% to +18% range. Extreme percentage errors (up to 79,000% at one location) occur exclusively at near-zero baseline values where even modest absolute differences produce outsized percentages. These extreme percentages do not indicate meaningful reconstruction failure; the underlying absolute errors remain small.

![QM Example -- Folsom Inflow Detail](figures/s3-inputs_rim-inflow-qm-folsom-detail.png)
_Monthly average flow (TAF) for Folsom inflow (I_FOLSM) by water year month (Oct--Sep). Raw VIC (red) overestimates the winter--spring peak at approximately 615 TAF in March and drops to near zero in summer. Quantile mapping (Q-MAP, blue) corrects the distribution to closely match the CalSim 3 target (CS3, black), restoring summer baseflow (~100 TAF) and reducing the March peak to approximately 395 TAF._

---

## CalSimHydro (746 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/calsimhydro/`  
Sacramento Valley water budget model processing
```


CalSimHydro is a water budget model that calculates agricultural and urban water demands, groundwater interactions, and return flows for 58 Water Budget Areas (WBAs) across California's Central Valley. It provides critical inputs for CalSim 3 including applied water demands, deep percolation, surface runoff, and actual evapotranspiration. By variable count, it is the largest single input category in the CalSim 3 stochastic inventory.

### Methodology

Precipitation and temperature data generated by the weather generator (WGEN) are first processed through the VIC model. The VIC flux outputs--including EVAP, PET_H2OSURF, and PET_SHORT--are then used to develop quantile-mapped evapotranspiration data covering crop ET, reference ET, and pan evaporation. The resulting evapotranspiration outputs together with precipitation directly from the weather generator meteorological data (with no adjustment for precipitation) are subsequently used as inputs to the CalSimHydro simulations.

The CalSimHydro validation process covers the period of 1972-2018, since the quantile-mapped ET input requires a training/testing split that limits the independent testing period to the latter half of the CalSim 3 historical input record. This validation period aligns with the QM testing window used for rim inflows.

An important model version issue arose during processing: CalSimHydro 2015 is required for DCR 2023 compatibility, as the 2020 version is missing WBAs 50 and 91. WBA 91 grid information had to be sourced separately to complete the spatial domain. During initial runs, a DSS file writing issue was traced to mixed string/numeric WBA identifiers (WBA 73 appeared as both text and integer), requiring explicit type handling in the output scripts.

The version incompatibility was first surfaced when the Rebalance model produced errors using L2020A CalSimHydro output, specifically reporting that initial time series for areas "50" and "91" were missing. While the Rebalance package ran successfully with the older L2015A CalSimHydro output, the L2020A output lacked these demand areas because they were not defined in its configuration. Attempts to resolve the issue by changing the PART F identifier from L2020A to L2015A in the DSS file were unsuccessful. After consultation with Mohammad Hassan and Richard Chen, the root cause was identified as missing demand units in the CalSimHydro L2020A configuration--specifically, units 50_PA1, 91_PA, and 91_PR needed to be added. Mohammad provided an updated "Existing CSHydro" model package with the corrected configuration, which was run with the input dataset prior to executing the Rebalance module. This resolved the compatibility problem by ensuring the required demand areas were properly defined in the hydro model output, allowing the Rebalance module to run successfully.

An alternative ET methodology was proposed by MSO in late 2025, separate from the VIC-based approach. After discussion, the team elected to continue with VIC-based QM because the MSO alternative would not be available until June 2026 with the final DCR 2025 release. The ET methodology change was assessed as "low-effort" compared to replacing the hydrologic model, meaning it can be incorporated as a Phase II enhancement without disrupting the current timeline.

### Results

Two separate model simulations were conducted to isolate the effects of precipitation changes alone and evapotranspiration changes alone, enabling clearer attribution of the resulting differences to each factor independently. This decomposition approach was presented at Progress Meetings 1 and 2, providing stakeholders with clear insight into which input change drives which output response.

The ET-driven simulation revealed that rangeland ET decreased under quantile-mapped inputs while agricultural ET increased slightly--a divergence attributable to the different response of managed and unmanaged land covers to ET adjustments. Lower rangeland ET leaves more water available at the soil surface for percolation, directly causing the +12% deep percolation increase seen across all WBAs. Applied water requirements for agriculture increased to meet higher potential ET requirements, representing the expected physical response where irrigation must compensate for elevated atmospheric demand.

The precipitation-driven simulation showed that 8% lower WGEN precipitation (relative to CalSim 3 historical) translates directly to reduced surface runoff (-18%) with modest effects on other water budget components. This finding confirms that CalSimHydro's surface runoff response is amplified relative to the precipitation input change--a nonlinear response consistent with rainfall-runoff theory where small reductions in precipitation cause proportionally larger reductions in excess precipitation available for runoff.

Monthly analysis across all WBAs confirmed these patterns at seasonal resolution. The combined effects of both ET and precipitation changes were tested in a third simulation, showing that ET changes appear more dominant than precipitation changes in driving overall CalSimHydro output differences. The approximately 300,000 acre-feet annual change across all WBAs represents a meaningful but not disabling shift in the valley-wide water budget.

The San Joaquin River (SJR) Rebalance processing was completed with a maximum difference of +4% deep percolation for the quantile-mapped ET scenario. The rebalance generates 97 additional variables required for CalSim 3 State Variable composition, covering Contract Conservation Yield, Water Use Factor adjustments, and related accounting terms on a March-through-February contract year basis.

::::{tab-set}
:::{tab-item} ET Response
![CalSimHydro QM-ET Response](figures/s3-inputs_calsimhydro-qm-et-response.png)
*CalSimHydro annual average difference from historical (TAF) for the QM-ET scenario, stacked by land type (Urban, Rangeland, Refuge, AG Rice, AG Others). Deep percolation (DP) shows the largest change at +12% (~600 TAF), dominated by rangeland where lower ET leaves more water for percolation. Applied water (AW) increases +2% as irrigation compensates for higher potential ET. Total ET decreases -2%.*
:::
:::{tab-item} Precipitation Response
![CalSimHydro Precipitation Response](figures/s3-inputs_calsimhydro-precipitation-response.png)
*CalSimHydro annual average difference from historical (TAF) for the WGEN precipitation scenario, stacked by land type. Surface runoff (SR) shows the largest response at -9% (~-350 TAF), followed by precipitation (PR) at -3% and deep percolation (DP) at -2%. Applied water, ET, and ETAW are effectively unchanged, confirming that precipitation changes propagate primarily through the runoff and percolation pathways.*
:::
:::{tab-item} Monthly Applied Water
![CalSimHydro Monthly Response](figures/s3-inputs_calsimhydro-monthly-response.png)
*Monthly applied water (TAF/month) summed across all WBAs by water year month (Oct--Sep), with annual totals as box plots at right. Irrigation demand peaks in July at approximately 2,500 TAF/month. The QM-ET scenario (blue) produces slightly higher summer demand than Historical (black) or Precip-only (red), reflecting increased crop water requirements under higher potential ET. Annual totals show QM-ET approximately 300 TAF higher than Historical (~13,300 vs ~12,800 TAF/yr).*
:::
:::{tab-item} Monthly Deep Percolation
![CalSimHydro Monthly Response -- Deep Percolation](figures/s3-inputs_calsimhydro-monthly-deep-percolation.png)
*Monthly deep percolation (TAF/month) summed across all WBAs. QM-ET (blue) is consistently above Historical (black) and Precip (red), particularly from December through March where it peaks at approximately 630 TAF/month compared to approximately 500 for Historical. Annual box plots (right) show QM-ET median approximately 4,100 TAF/yr vs Historical approximately 3,400 TAF/yr, reflecting the +12% annual increase from reduced rangeland ET.*
:::
:::{tab-item} Monthly Tailwater
![CalSimHydro Monthly Response -- Tailwater](figures/s3-inputs_calsimhydro-monthly-surface-runoff.png)
*Monthly tailwater return flow (TAF/month) summed across all WBAs. Tailwater follows the irrigation season cycle, dipping to approximately 40 TAF/month in March before rising to approximately 400 TAF/month in May--Jul. All three scenarios (Historical, Precip, QM-ET) produce nearly identical tailwater patterns because tailwater is driven primarily by applied water timing rather than climate inputs. Annual totals cluster tightly around 2,550--2,600 TAF/yr.*
:::
:::{tab-item} SJR Rebalance
![SJR Rebalance Annual Response](figures/s3-inputs_sjr-rebalance-annual.png)
*SJR Rebalance percent difference from historical for the QM-ET scenario, by Water Budget Area (WBAs 50, 64, 71, 72, 73, 90, 91). Stacked by component: tailwater (TW), deep percolation (DP), applied water for wetlands/rice/other (AWW, AWR, AWO). Deep percolation (brown) dominates the positive differences, with WBA 71 showing the largest total change at approximately +7%. Applied water for rice (AWR) contributes small negative offsets in WBAs 50 and 73.*
:::
:::{tab-item} SJR Rebalance Detail
![SJR Rebalance Decomposition](figures/s3-inputs_sjr-rebalance-decomposition.png)
*SJR Rebalance percent difference from historical for the WGEN precipitation scenario, by Water Budget Area. All WBAs show net negative differences driven by lower WGEN precipitation. WBA 91 is most affected at approximately -3.5%, with deep percolation (DP) and applied water for rice (AWR) as the primary contributors. WBA 50 shows a small positive AWR offset partially compensating the DP decrease.*
:::
::::

---

## CalSimHydroEE (17 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/calsimhydro_ee/`  
External Elements boundary condition processing
```


**External Elements**

The External Elements (EE) module generates deep percolation outputs for boundary areas outside the main CalSimHydro domain, including the Mono Lake basin and other peripheral Central Valley watersheds. These provide groundwater recharge boundary conditions for the integrated groundwater-surface water modeling framework.

### Methodology

The External Elements module uses evapotranspiration quantile mapped from VIC outputs combined with precipitation taken directly from WGEN data. This approach mirrors the CalSimHydro methodology but applies to boundary regions where less detailed calibration data is available. The module generates exactly 17 deep percolation variables, each corresponding to an External Area (EA) recharge zone.

The EE model was successfully configured using historical WGEN Product A inputs, with scripts requiring modification of hard-coded paths for the project directory structure. Unlike CalSimHydro which uses ET with interannual variation, the EE module employs a simpler input structure reflecting the data-sparse nature of these boundary areas.

### Results

The analysis showed maximum differences of approximately +100% for some exterior areas, a statistic that requires careful interpretation. The extreme percentage reflects the small baseline values in these boundary regions--often fractions of a TAF per year--which amplify relative differences even when absolute differences are minimal. The median absolute difference was less than 1 TAF/yr, and the median percentage difference is manageable when viewed in context of the overall system water balance.

The ET-driven and precipitation-driven effects mirror CalSimHydro's patterns at smaller magnitudes. Quantile-mapped ET produces the maximum +100% deep percolation difference, while slightly lower WGEN precipitation leads to correspondingly lower deep percolation. The dominant signal in EE output is the ET change rather than precipitation, consistent with CalSimHydro findings where ET changes proved more influential than precipitation changes.

::::{tab-set}
:::{tab-item} Overview
![CalSimHydroEE Overview](figures/s3-inputs_calsimhydroee-overview.png)
*Monthly deep percolation (TAF/month) summed across all External Areas, with annual totals as box plots (right). QM-ET (blue) approximately doubles the winter peak relative to Historical (black), reaching approximately 13 TAF/month in March vs approximately 7.5 for Historical. Deep percolation drops to zero from June through September across all scenarios. Precip (red) tracks slightly below Historical. Annual box plots show QM-ET median approximately 40 TAF/yr with high-year outliers exceeding 300 TAF.*
:::
:::{tab-item} Absolute Differences
![CalSimHydroEE Differences](figures/s3-inputs_calsimhydroee-differences.png)
*Annual average deep percolation difference from historical (TAF) for the WGEN precipitation scenario across all 17 External Areas. All differences are less than 1 TAF in magnitude. DP_EA_06 shows the largest negative difference at -0.65 TAF; DP_EA_63 (+0.23) and DP_EA_73 (+0.22) are the largest positive differences. Several areas (DP_EA_15S, DP_EA_50) show effectively zero change.*
:::
:::{tab-item} Absolute Differences (Detail)
![CalSimHydroEE Differences Detail](figures/s3-inputs_calsimhydroee-differences-detail.png)
*Annual average deep percolation difference from historical (TAF) for the QM-ET scenario across all 17 External Areas. All differences are positive, reflecting increased percolation from reduced ET. DP_EA_02 (+3.78 TAF), DP_EA_06 (+3.70), and DP_EA_NBAY (+3.64) show the largest increases. QM-ET differences are an order of magnitude larger than the Precip scenario, confirming ET as the dominant driver of EE output changes.*
:::
:::{tab-item} Percent Differences
![CalSimHydroEE Percent Differences](figures/s3-inputs_calsimhydroee-pct-differences.png)
*Percent difference from historical for the QM-ET scenario across all 17 External Areas. DP_EA_NBAY shows the largest percent change at +710%, followed by DP_EA_90 (+309%) and DP_EA_15S (+212%). Most areas fall in the +47% to +95% range. The extreme percentages at NBAY and EA_90 reflect very small historical baseline values (fractions of a TAF/yr) where even modest absolute increases produce outsized relative differences.*
:::
:::{tab-item} Percent Differences (Detail)
![CalSimHydroEE Percent Differences Detail](figures/s3-inputs_calsimhydroee-pct-differences-detail.png)
*Percent difference from historical for the WGEN precipitation scenario across all 17 External Areas. Most areas fall within -13% to +18%. DP_EA_15S is a positive outlier at +96% (reflecting a near-zero historical baseline of 0.01 TAF); DP_EA_NBAY is the largest negative at -45%. The mixed positive and negative signs contrast with the uniformly positive QM-ET scenario, reflecting the spatially variable influence of WGEN precipitation bias across the domain.*
:::
::::

These boundary condition changes should have relatively minor effects on overall CalSim 3 results since the External Elements represent a small fraction of total system water balance. However, they ensure consistency between the stochastic inputs and the boundary conditions used in the groundwater modeling components. Maintaining this consistency avoids introducing artificial discontinuities at the boundary of the primary CalSim domain.

---

## Small Watersheds (210 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/small_watersheds/`  
Small tributary groundwater recharge processing
```


The Small Watersheds module generates groundwater recharge estimates for 210 small watershed areas throughout the Central Valley. Unlike CalSimHydro, this module uses a repeating 12-month ET pattern with no interannual variation and directly input precipitation. This design makes results primarily sensitive to precipitation differences rather than evapotranspiration variations.

### Methodology

The Small Watersheds executable operates similarly to CalSimHydro, accepting climate inputs and computing groundwater recharge through a water budget calculation. However, the module takes ET as a repeating 12-month seasonal pattern without interannual variation, meaning precipitation drives all year-to-year variability in results. Precipitation comes directly from WGEN data without bias correction or VIC intermediation.

Initial setup required locating the correct executable, which was not immediately available from MSO. Coordination over several weeks eventually produced the proper `smwshed_compiler.exe` and associated configuration files. The model reads precipitation from a CSV with 1,602 columns representing spatial grid cells across the small watershed domains--each column corresponding to a specific latitude-longitude precipitation point compiled from WGEN output. The precipitation compilation script aggregates WGEN station data into this wide-format CSV that the executable consumes directly.

This relatively simple modeling approach reflects both the limited calibration data available for small watershed recharge estimates and the secondary importance of these terms in overall CalSim water balance. The fixed ET pattern means results are purely precipitation-driven, making Small Watersheds a direct test of WGEN precipitation fidelity without the confounding effects of VIC ET bias seen in CalSimHydro.

### Results

The analysis showed maximum differences ranging from -4 to +2 TAF/yr in absolute terms. Percentage differences ranged widely, from approximately -100% to +100%, though this reflects the small baseline values for many watersheds. The median absolute difference was less than 1 TAF/yr, with a median percentage difference of -13.5%.

![Small Watersheds Distribution](figures/s3-inputs_small-watersheds-distribution.png)
*Percent difference (Precip vs Historical) plotted against historical groundwater recharge magnitude (TAF/yr) for all 210 small watersheds. Red dashed line marks the median at -13.5%. Larger watersheds (>10 TAF/yr) cluster tightly near the median; smaller watersheds scatter widely from -100% to +300%, where near-zero baseline values amplify even modest absolute differences.*

The scatter plot reveals an important pattern: smaller watersheds with lower baseline flow volumes show proportionally larger percentage differences, while larger watersheds cluster near the median. This behavior is expected since small absolute changes produce large percentage changes when the baseline is small. The -13.5% median difference provides a useful system-level summary, indicating that the WGEN precipitation deficit translates into a roughly proportional groundwater recharge reduction across the domain.

The differences across all watersheds are driven primarily by lower WGEN precipitation compared to the historical baseline. Since ET is held constant as a repeating pattern, there is no VIC-derived ET bias to offset or amplify the precipitation signal--unlike CalSimHydro where ET and precipitation changes interact. This makes Small Watersheds a clean diagnostic of WGEN precipitation bias: the -13.5% median recharge reduction is a direct expression of how much less precipitation WGEN produces relative to historical records across the Central Valley.

---

## Delta Channel Depletion (28 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/delta_channel_depletion/`  
Delta consumptive use and seepage (DCD/DETAW)
```


Delta Channel Depletion (DCD) represents consumptive use and seepage in the Sacramento-San Joaquin Delta. The model operates on a "planning study" configuration (as opposed to "historical study") to align with CalSim 3 DCR 2023. Each DCD run requires approximately 3 hours of processing time.

### Methodology

Temperature and precipitation data come directly from WGEN without additional processing. The DETAW component computes crop water demands from temperature and precipitation, which then feed into the DCD model to simulate agricultural water use, seepage, and return flows across Delta islands. The DCD version 2.1 was downloaded for this project, with key inputs including groundwater contribution rate (held constant at 0.4 for the planning study configuration), irrigation efficiency parameters, and land use classifications.

The distinction between "planning study" and "historical study" configurations is important: the planning study configuration assumes equilibrium groundwater and land use conditions appropriate for long-term planning, matching the DCR 2023 baseline. Using the historical configuration would inject year-specific calibration adjustments that are not reproducible from synthetic climate alone.

The master inventory requires 28 DCD variables, but direct model output contains only 24. Four additional aggregated variables--Delta_DP, Delta_GW, DPWA_50, and DPWA_60--are generated through post-processing that combines island-level outputs into larger spatial units. Mohammad Hasan at MSO provided the weighted aggregation scheme: a two-column weight matrix where columns sum to 1.0, enabling proper spatial averaging from island-scale DCD results to the aggregated zones CalSim expects. The aggregation produces 2 groundwater flow variables and 2 deep percolation variables, completing the 28-variable inventory.

Input labeling follows an important naming convention: files are labeled "WGen precip" rather than "VIC precip" to accurately reflect the data lineage, since DCD receives WGEN climate directly without VIC intermediation.

### Results

![Delta Channel Depletion Differences](figures/s3-inputs_delta-channel-depletion-differences.png)
*Annual average difference from historical (TAF) for all 28 DCD variables, grouped by type: deep percolation flow (DP-FLOW), drainage (DRN), groundwater flow (GW-FLOW), irrigation (IRR), and seepage (SEEP). Percentage differences (purple, bottom) range from -8% to +10%. Drainage variables show the largest absolute differences, with DRN_SIR_EAST at -166 TAF and DP_DELTA_DCD at -101 TAF. Seepage variables are effectively unchanged (0%). All differences are driven by lower WGEN precipitation.*

The maximum differences ranged from -166 TAF/yr to +6 TAF/yr across the suite of DCD variables. Percentage differences spanned -8% to +10%, with overall changes driven by lower WGEN precipitation relative to the historical baseline. The largest absolute difference (-166 TAF/yr) occurs in the deep percolation variable, reflecting the reduced precipitation available for recharge.

The pattern of differences across variable types reveals a coherent physical story. Drainage (DRN) variables tend to have larger negative differences, reflecting reduced surface runoff and subsurface drainage from lower precipitation. Groundwater and seepage flows show more modest changes, consistent with their deeper hydrologic pathways that buffer rapid precipitation changes. Irrigation variables track agricultural demands which depend on both precipitation (reducing demand when higher) and evapotranspiration (increasing demand when higher), producing a mixed signal.

Running DCD for Product B's 1,000-year simulation required careful attention to computational logistics. Each DCD run takes approximately 3 hours, and the Product B sequence is divided into 10 chunks of 100 water years. The DETAW climate compilation step prepares temperature and precipitation input files for each chunk before launching the DCD executable. Total processing time for the full Product B suite approached 30 hours, making it one of the more computationally intensive input generation modules alongside VIC.

An important DCD limitation emerged during testing: a DSS writing bug involving mixed string/numeric handling for certain Delta island identifiers (particularly WBA 73, which appears as both numeric 73 and string "73" in different contexts). This required a targeted fix in the post-processing scripts to ensure consistent data type handling when writing final DSS files.

---

## Tulare Groundwater Terms (14 Variables)

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/tulare_gw_terms/`  
Tulare Basin groundwater terms via WYT averaging
```


Groundwater pumping and deep percolation terms for Tulare Basin C2VSim areas 15-21. The 14 terms comprise seven groundwater pumping variables and seven deep percolation variables representing C2VSim fine grid solution outputs. These terms exist outside CalSim's primary water system domain, serving as placeholders that maintain groundwater dynamics in reasonable ranges without full integration into CalSim's operations.

### Methodology

Correlation testing against rim inflow variables across all 14 terms revealed correlations uniformly below 0.8, with most substantially lower. This eliminated quantile mapping as a viable approach since QM performance degrades significantly when basis-target correlation falls below 0.7. The Progress Meeting 3 presentation included an R^2 comparison table showing QM versus WYT performance for all 14 terms, confirming WYT averaging's superiority for these low-correlation variables. Water year type averaging emerged as the only practical methodology given these constraints.

The approach calculates monthly averages conditional on San Joaquin water year type classification (Wet, Above Normal, Below Normal, Dry, Critical), which is appropriate given Tulare Basin's location and hydrologic character. For each calendar month and water year type combination, historical values are averaged to produce representative patterns. These patterns are then applied to synthetic sequences based on reconstructed San Joaquin WYT classification.

Running C2VSim for 1,000 years would require land use projections, agricultural demand assumptions, and computational resources beyond Phase I scope. MSO staff provided important context during the October and November progress meetings, noting that these terms "are kind of like a placeholder that we just keep the groundwater in a reasonable range" and emphasizing "I really wouldn't put too much weight on this part of the data." CalSim 3 does not cover the entire Tulare region, and these terms originate from an older C2VSim fine grid solution not directly coupled to CalSim operations. The terms represent a legacy boundary condition inherited from earlier model versions where Tulare Basin dynamics were approximated rather than simulated.

This candid assessment from MSO informed the decision to accept WYT averaging despite its limitations. Investing significant effort in sophisticated reconstruction methods for variables that model developers themselves consider approximate placeholders would not be an efficient use of project resources.

### Results

#### Groundwater Pumping Terms

Groundwater pumping variables show acceptable R^2 values ranging from moderate to strong correspondence. The best-performing examples demonstrate good overall fit with realistic seasonal patterns. The worst-performing pumping term (GP-19) still achieves acceptable results despite showing less variation than actual historical values, reflecting the inherent averaging effect of the WYT methodology. Drought period reconstruction shows less up-and-down volatility than actual values, which is expected when using categorical averaging rather than continuous predictors. Given the lack of better predictive methods, this smoothing effect represents an acceptable trade-off.

#### Deep Percolation Terms

Deep percolation variables exhibit lower R^2 values and reduced ability to capture signal variability compared to groundwater pumping. Best and worst examples spanning areas 15-21 illustrate a range of performance, with Term 15 showing poor reconstruction, while Terms 19-20 demonstrate moderate improvement. A consistent pattern of underestimation appears in deep percolation reconstruction, suggesting potential mass balance considerations merit investigation.

::::{tab-set}
:::{tab-item} GP Best (R² = 0.96)
![Tulare GW Best Examples](figures/s3-inputs_tulare-gw-best-examples.png)
*GP_GWR15 groundwater pumping reconstruction (1921--2021), best-performing GP term (R^2 = 0.96). Monthly time series cycles between approximately 0 TAF in winter and 300--400 TAF during summer irrigation season. Reconstructed (orange) closely tracks actual (blue), capturing both seasonal amplitude and year-to-year variations in peak pumping.*
:::
:::{tab-item} GP Worst (R² = 0.70)
![Tulare GW Best GP-19](figures/s3-inputs_tulare-gw-best-gp19.png)
*GP_GWR19 groundwater pumping reconstruction (1921--2021), worst-performing GP term (R^2 = 0.70). Summer peaks in actual data reach approximately 150 TAF while reconstructed values plateau around 110 TAF, illustrating the WYT averaging smoothing effect. The reconstructed series captures seasonal timing but compresses the range of peak values, particularly missing the higher pumping years.*
:::
:::{tab-item} DP Best (R² = 0.64)
![Tulare GW DP Best](figures/s3-inputs_tulare-gw-dp-best.png)
*DP_GWR17 deep percolation reconstruction (1921--2021), best-performing DP term (R^2 = 0.64). Actual values (blue) range from approximately 15 to 115 TAF with frequent spikes above 80 TAF in wet months. Reconstructed values (orange) are compressed to approximately 20--75 TAF, capturing the general seasonal pattern but underestimating wet-month peaks by 30--40 TAF.*
:::
:::{tab-item} DP Worst (R² = 0.32)
![Tulare GW DP Worst](figures/s3-inputs_tulare-gw-dp-worst.png)
*DP_GWR21 deep percolation reconstruction (1921--2021), worst-performing term overall (R^2 = 0.32). Actual values (blue) show dramatic wet-year spikes reaching approximately 220 TAF, while reconstructed values (orange) remain within approximately 40--90 TAF. The WYT averaging approach captures the baseline level (~50 TAF) but cannot reproduce the episodic high-percolation events that dominate variability in this area.*
:::
::::

:::note Suggested Plot
Four-panel comparison showing best and worst examples for both GP and DP terms. Each panel includes time series (WY 1972-2018) with actual (gray) and reconstructed (blue) values, plus inset box plot by WYT showing how averages differ across water year types. Annotate R^2 and mean annual difference on each panel.
:::

The documented limitations are acceptable within project constraints. The groundwater pumping and deep percolation patterns provide hydrologically reasonable boundary conditions that avoid introducing systematic biases or unrealistic trends. For long-term stochastic planning focused on core system performance, maintaining plausible Tulare groundwater behavior through WYT averaging serves project objectives while acknowledging appropriate methodological boundaries.
