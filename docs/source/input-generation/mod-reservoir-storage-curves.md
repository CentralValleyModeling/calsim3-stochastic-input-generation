# mod_reservoir/storage_curves

```{admonition} Repository Module
:class: tip

**Module:** `mod_reservoir/storage_curves/`  
Reservoir storage reconstruction and rule curves
```


Reservoir storage curves define operational constraints at multiple "levels" for major California reservoirs, representing flood control space, conservation pool limits, and minimum operating thresholds.

## Methodology

### Mammoth Pool Storage (Flood Reservation Space)

Mammoth Pool flood reservation space was reconstructed using quantile mapping from Millerton unimpaired inflow, which serves as the hydrologic basis with correlation R = 0.7. The methodology employed split-sample validation with 1921-1971 as training period and 1972-2018 as testing period.

:::{admonition} Suggested Plot
:class: note
Exceedance probability curves for Mammoth Pool flood space at end-of-September and end-of-February, comparing historical CalSim inputs (black line) against reconstructed values (blue line) for WY 1972-2018 validation period. Include confidence bands and highlight 10th, 50th, and 90th percentiles.
:::

### Oroville Level 5 (Top of Conservation / Flood Control)

Oroville Level 5 represents a complex flood control calculation based on Water Control Manual procedures rather than simple correlation approaches. The reconstruction faced a fundamental challenge: reconciling water control diagram specifications with actual CalSim storage values revealed a systematic discrepancy due to reservoir sedimentation.

#### Sedimentation Correction

DCR 2023 reporting documents a critical finding from LIDAR and SONAR bathymetric surveys showing 3% reduction in storage capacity since original construction. The original water control manual maximum storage of 3,538 TAF no longer reflects current physical capacity, which is now 3,424.8 TAF. This ~113 TAF difference reflects approximately 50 years of sediment accumulation behind Oroville Dam, accelerated by major flood events. The sedimentation correction presents a challenge as reservoir operations use elevations as control targets, not volumes. The same elevation that previously corresponded to 3,538 TAF now corresponds to 3,424.8 TAF due to changed bathymetry.

#### Wetness Index Methodology

The reconstruction implements the USGS-documented wetness index algorithm, which recursively calculates daily wetness based on precipitation and previous day's wetness with seasonal parameter variations. Physically, the wetness index represents antecedent soil moisture and catchment wetness conditions that govern how much flood pool space the Army Corps requires--wetter conditions demand more reserved flood space since the watershed can absorb less additional precipitation before generating dangerous runoff.

The water control diagram translates wetness index to flood pool requirement, with maximum flood space of 737.3 TAF at wetness index $\geq 11$ declining to minimum flood space of 368.2 TAF at wetness index $= 1$. Original implementation used stepwise function rounding to nearest integer wetness index, but refinement to interpolate to first decimal place (e.g., 4.1, 4.2) provides smoother transitions matching CalSim behavior. This interpolation refinement was identified during Progress Meeting 3 discussions, where comparison of scatter plots between integer-stepped and interpolated wetness indices showed substantially reduced scatter in the reconstructed flood pool values.

Flood pool adjustments across the wetness index range maintain consistent operational elevations while correcting storage volumes for sedimentation. The minimum and maximum values align well with current results, and interpolation refinement addresses scatter in intermediate values. For synthetic sequences, the wetness index algorithm runs on WGEN precipitation directly, producing daily wetness values that translate through the calibrated relationship to monthly flood pool requirements without requiring intermediate model runs.

### Other Reservoir Levels (WYT-Driven and Monthly Repeating)

The remaining reservoir storage-level curves are reconstructed from schedule tables rather than hydrologic correlation, falling into two categories: WYT-driven (value determined by water year type) and monthly repeating (fixed seasonal pattern).

#### WYT-Driven Series

WYT-driven series assign a constant storage target for each Sacramento Valley water year type classification (W, AN, BN, D, C). 

All four WYT-driven series use calendar-year mapping, meaning the storage target changes at the January boundary rather than the October water-year boundary. This reflects how CalSim applies water year type classifications to these operating rules: the Sac Valley 40-30-30 index is determined on a calendar-year basis, so Oct--Dec inherit the prior year's classification while Jan--Sep use the current year's classification. For example, in WY 1924 (a Critical year), Shasta Level 2 remains at 2,000 TAF through Oct--Dec 1923 (still governed by the BN classification of CY 1923), then drops to 650 TAF starting January 1924 when the Critical classification takes effect.

The five WYT-driven series and their target storage values (TAF) are:

| Series | W | AN | BN | D | C | Basin |
|--------|--:|---:|---:|--:|--:|-------|
| S_SHSTALEVEL2 | 2,000 | 2,000 | 2,000 | 1,700 | 650 | Sac |
| S_TRNTYLEVEL2 | 1,100 | 1,100 | 1,100 | 700 | 500 | Sac |
| S_TRNTYLEVEL3 | 1,600 | 1,600 | 1,500 | 1,300 | 1,000 | Sac |
| S_FOLSMLEVEL2 | 350 | 350 | 350 | 300 | 300 | Sac |

**Shasta Level 2** target values were verified against the CalSim 3 WRESL operating rules and the historical SV timeseries. Shasta Level 2 is *not* a fixed constant--it varies substantially with water year type, from 2,000 TAF in wet years down to 650 TAF in critical years.

**Trinity Levels 2 and 3** track Sacramento Valley index patterns with high fidelity. **Folsom Level 2** shows remarkably consistent step-function behavior between 300 and 350 TAF, confirming that WYT averaging captures the essential operational pattern.

#### Monthly Repeating Series

Monthly repeating series use a fixed 12-month seasonal pattern that repeats identically every year regardless of water year type. **Don Pedro Level 4** (flood control) uses this pattern, with values ranging from 1,660 TAF (October) to 2,030 TAF (June), reflecting the seasonal flood reservation space cycle.

#### Boundary Gap Fill

Because the reconstruction period begins in October of the year preceding the first labeled WYT year, the first three months of a generated series can lack a matching WYT assignment. The script therefore allows a DSS-based boundary fill only for the initial October--December window.

## Results

### WYT-Based
The five WYT-based reservoir storage level reconstructions show strong performance, with two requiring careful interpretation of historical anomalies. Trinity Levels 2 and 3 completely align with CalSim inputs using water year type patterns. Folsom Level 2, Don Pedro Level 4, and Shasta Level 2 show very limited mismatches, demonstrating robust methodology. 

::::{tab-set}
:::{tab-item} Folsom Level 2
![Reservoir Storage Curves Overview](figures/s3-inputs_reservoir-storage-curves.png)
*Folsom Level 2 (minimum pool) storage reconstruction, 1921--2021. Actual CalSim input (blue) and WYT-based reconstruction (orange) show step-function behavior alternating between approximately 300 and 350 TAF depending on water year type. Agreement is near-perfect, with only brief departures visible in a few years (~1951, 1978, 1985, 1993).*
:::
:::{tab-item} Don Pedro Level 4
![Reservoir Storage Validation](figures/s3-inputs_reservoir-storage-validation.png)
*Don Pedro Level 4 (S_PEDRO) storage reconstruction validation, 1921--2021. Reconstructed values (orange) closely track actual CalSim inputs (blue) across the seasonal range of approximately 1,700--2,030 TAF. One anomalous drawdown to approximately 1,250 TAF around 1977--1980 in the historical record is not replicated by the reconstruction, consistent with the identified unique operational event.*
:::
:::{tab-item} Shasta Level 2
![Reservoir Storage WYT Alignment](figures/s3-inputs_reservoir-storage-wyt-alignment.png)
*Shasta Level 2 (S_SHASTA) storage reconstruction, 1921--2021. Reconstructed WYT-based values (orange) step between approximately 800 and 2,000 TAF depending on water year type. Actual CalSim inputs (blue) are available only in limited time windows (circa 1989--1995 and 2009--2021), showing general agreement in the overlap periods with minor mismatches in level assignment.*
:::
::::


### Mammoth Pool

Validation achieved R^2 = 0.83 with values predominantly aligned to actual inputs. Minor misalignments appear in two contexts: minimum storage values during September through February, and anomalous behavior during the 2012-2015 drought period where actual CalSim inputs maintain storage consistently higher than expected.

![Mammoth Pool QM Validation](figures/s3-inputs_mammoth-pool-qm-validation.png)
*Mammoth Pool storage quantile mapping validation, WY 1972--2018 (R^2 = 0.83). Millerton inflow serves as basis (R = 0.7). Storage oscillates seasonally between approximately 10--20 TAF (troughs) and 120--125 TAF (peaks), with reconstructed values (orange) generally tracking actual CalSim inputs (blue).* The drought anomaly likely reflects maintenance or operational constraints where actual operations deviated from typical patterns. Attempting to replicate such anomalies through algorithms may be counterproductive, as the systematic reconstruction based on hydrologic relationships provides more defensible projections for synthetic sequences.

### Oroville Level 5

![Oroville TOC Reconstruction](figures/s3-inputs_oroville-toc-reconstruction.png)
*Oroville Level 5 (Top of Conservation / flood control) reconstruction, WY 1972--2018 (R^2 = 0.75). The wetness index approach translates precipitation-based antecedent wetness to flood pool requirements, producing seasonal drawdowns from the sedimentation-corrected maximum of approximately 3,425 TAF to troughs of 2,700--3,050 TAF depending on winter wetness. Reconstructed values (orange) generally track actual CalSim inputs (blue), with differences reflecting sensitivity of the wetness index to precipitation timing.*

