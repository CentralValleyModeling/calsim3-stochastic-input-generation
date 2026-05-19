# mod_reservoir/storage_curves

```{admonition} Repository Module
:class: tip

**Module:** `mod_reservoir/storage_curves/`  
Reservoir storage reconstruction and rule curves
```
## Module Overview


Reservoir storage curves define operational "level" targets, flood control
reservation space, top of conservation, and minimum pool thresholds for
major California reservoirs in CalSim3.

Seven series are reconstructed and grouped by how they are generated:

1. **Mammoth Pool Quantile Mapping**: monthly-stratified empirical CDF
   mapping from a correlated unimpaired inflow basis (`MAMMOTH_STORAGE`)
2. **Oroville Level 5 Top of Conservation**: USACE wetness-index rule
   curve driven by basin precipitation (`S_OROVLLEVEL5`)
3. **Water Year Type Levels**: constant per Sacramento Valley water year
   type class (`S_SHSTALEVEL2`, `S_TRNTYLEVEL2`, `S_TRNTYLEVEL3`,
   `S_FOLSMLEVEL2`)
4. **Monthly Schedule Levels**: fixed 12-month seasonal pattern
   (`S_PEDROLEVEL4`, `S_FOLSMLEVEL4`, `S_FOLSMLEVEL5`)


## Methodology

### Mammoth Pool Quantile Mapping

Mammoth Pool storage is reconstructed by quantile mapping from
Millerton unimpaired inflow, which serves as the hydrologic basis variable.
Millerton unimpaired inflow provides a representative runoff signal with
similar seasonal timing and a monthly historical correlation of
$R = 0.76$ with the Mammoth Pool storage target over WY 1922--2021
(Oct 1921 -- Sep 2021).

The quantile-mapping pair is `MAMMOTH_STORAGE / STORAGE` as the target and
`I_MLRTN / INFLOW` as the basis, with target values bounded between 0 and
123 TAF. The procedure follows the same monthly-stratified empirical CDF
mapping used elsewhere in the pipeline (`utils/quantile_mapping.py`),
preserving seasonal distributions. The mapping was trained on WY 1921--1971
using the CalSim 3 historical baseline from DCR 2023
(`CalSim3/__calsim_sv_default__.dss`) and validated on WY 1972--2018 using
the Product A quantile-mapped Millerton inflow.

#### Validation

Validation achieved $R^2 = 0.78$ with values predominantly aligned to actual inputs. Minor misalignments appear in two contexts: minimum storage values during September through February, and anomalous behavior during the 2012-2015 drought period where actual CalSim inputs maintain storage consistently higher than expected.

![Mammoth Pool QM Validation](figures/s3-inputs_mammoth-pool-qm-validation.png)
*Mammoth Pool storage quantile mapping validation, WY 1972--2018 (R^2 = 0.78). Millerton inflow serves as basis (R = 0.76). Mammoth storage shows a seasonal pattern, with low-storage periods generally around 10–30 TAF and high-storage peaks of roughly 120-124 TAF during the spring-summer refill period, with the highest sustained peaks in wetter years. The reconstructed series generally follows the timing and magnitude of the historical CalSim input series, although some mid to high storage values are underestimated. A distinct departure is evident during the 2012–2015 drought, when the historical CalSim input storage remains higher than the reconstructed in many months. The drought anomaly likely reflects maintenance or operational constraints where actual operations deviated from typical patterns. Attempting to replicate such anomalies through algorithms may be counterproductive, as the systematic reconstruction based on hydrologic relationships provides more defensible projections for synthetic sequences.

:::{admonition} Suggested Plot
:class: note
Exceedance probability curves for Mammoth Pool flood space at end-of-September and end-of-February, comparing historical CalSim inputs (black line) against reconstructed values (blue line) for WY 1972-2018 validation period. Include confidence bands and highlight 10th, 50th, and 90th percentiles.
:::

### Oroville Level 5 Top of Conservation


Oroville Level 5 represents the reservoir top of conservation storage used
for flood-control operations. The rule curve follows the U.S. Army Corps of
Engineers Water Control Manual for Oroville Dam (USACE, 1970), in
which the allowable conservation storage varies seasonally and depends on
antecedent watershed wetness.

Daily precipitation is first converted to a Feather River basin
wetness index. The wetness index is then translated into a flood reservation
requirement and, finally, into a daily top of conservation storage target.
Monthly end of month values are written as the CalSim storage-level series
`S_OROVLLEVEL5`.


#### Storage-Capacity Adjustment

The USACE Oroville flood-control rule curve was originally based on a gross
pool capacity of approximately 3,538 TAF at elevation 900 feet, with
750 TAF allocated to flood-control storage. Recent DWR bathymetric mapping
using 2021 LiDAR and 2022 multibeam-sonar data revised Lake Oroville’s
capacity to 3,424,753 acre-feet, or approximately 3,424.8 TAF (DWR, 2024). This is about
113 TAF, or 3 percent, less than the original 1968 estimate.

The updated bathymetry requires an explicit elevation to volume translation in the reconstruction. The USACE Water Control Manual defines the flood-control requirement in terms of reservoir elevation and required flood-reservation space, and its listed storage volumes are tied to the manual’s historical area-capacity curve. CalSim `S_OROVLLEVEL5` input is expressed as a storage volume. Because of the revised bathymetry, the elevation that historically corresponded to 3,538 TAF of gross pool capacity now corresponds to only 3,424.8 TAF. The volume-based rule curve must therefore be rescaled so that flood-control allocations remain consistent with the operating elevations specified in the USACE Water Control Manual, even though the underlying storage volumes have changed.


#### Wetness-Index Method
The Oroville wetness-index method implements the Lake Oroville flood-control
rule-curve logic summarized by Knowles and Cronkite-Ratcliff (2018).

The wetness index is computed recursively from daily Feather River basin
precipitation:

$$
x_t = 0.97\, x_{t-1} + p_t
$$

where $x_t$ is the wetness index for day $t$, $x_{t-1}$ is the previous
day's wetness index, and $p_t$ is the basin-averaged daily precipitation.
The wetness index is bounded between 3.5 and 11.0. Lower wetness values
represent drier antecedent conditions and require less flood reservation
space; higher wetness values represent wetter antecedent conditions and
require more flood reservation space.

The flood reservation volume is interpolated between the adjusted endpoint
values:

$$
R(x) = \text{interp}(x;\ [3.5, 11.0],\ [368.2, 737.3])
$$

where $R(x)$ is the required flood reservation in TAF. The corresponding
minimum flood-season top-of-conservation storage is:

$$
S_{\min}(x) = S_{\max} - R(x)
$$

where $S_{\max}$ is the adjusted maximum storage capacity.

#### Seasonal Rule Curve Translation

The daily top-of-conservation target follows the seasonal structure of the
Lake Oroville flood-control rule curve:

- From September 15 to October 15, storage ramps down from the summer
  maximum storage to the wetness dependent flood season target.
- From October 15 through March 31, the target remains at the
  wetness dependent flood season storage level.
- After March 31, the target refills toward the summer maximum at the
  prescribed refill rate, capped at $S_{\max}$.


#### Synthetic Hydroclimate Implementation

For synthetic sequences, the same wetness index and rule curve calculation is applied to WGEN-derived daily Oroville basin precipitation. The resulting daily storage targets are aggregated to monthly end of month values compatible with Calsim monthly input.

#### Validation

Validation against historical CalSim inputs shows that the wetness index approach
captures the primary seasonal drawdown and refill behavior, with remaining
differences largely reflecting the method’s sensitivity to daily precipitation
timing and basin mean precipitation representation.



![Oroville TOC Reconstruction](figures/s3-inputs_oroville-toc-reconstruction.png)
*Oroville Level 5 (Top of Conservation / flood control) reconstruction, WY 1972--2018 (R^2 = 0.75). The wetness index approach translates precipitation-based antecedent wetness to flood pool requirements, producing seasonal drawdowns from the sedimentation-corrected maximum of approximately 3,425 TAF to troughs of 2,700--3,050 TAF depending on winter wetness. Reconstructed values (orange) generally track actual CalSim inputs (blue), with differences reflecting sensitivity of the wetness index to precipitation timing.*


### Water Year Type Levels

WYT-driven series assign a constant storage target for each Sacramento Valley water year type classification (W, AN, BN, D, C). 

The current implementation includes four WYT-driven series: Shasta Level 2,
Trinity Level 2, Trinity Level 3, and Folsom Level 2. Each series uses the
Sacramento Valley WYT classification and is mapped on a calendar-year basis
rather than a water-year basis. Under this convention, October–December
values are assigned using the prior calendar year’s WYT classification, while
January–September values use the current calendar year’s WYT classification.

For example, if WY 1924 is classified as Critical, Shasta Level 2 remains at
the prior classification value through October–December 1923, then changes
to the Critical-year target beginning in January 1924.

This calendar-year mapping follows the CalSim storage-level convention and
avoids look-ahead use of WYT information. Because in real-time operations, the Sacramento Valley
40-30-30 index is not fully known at the October 1 water-year boundary,
October–December retain the prior calendar year’s classification, while
January–September use the current calendar year’s classification.


The five WYT-driven series and their target storage values (TAF) are:

| Series | W | AN | BN | D | C | Basin |
|--------|--:|---:|---:|--:|--:|-------|
| S_SHSTALEVEL2 | 2,000 | 2,000 | 2,000 | 1,700 | 650 | Sac |
| S_TRNTYLEVEL2 | 1,100 | 1,100 | 1,100 | 700 | 500 | Sac |
| S_TRNTYLEVEL3 | 1,600 | 1,600 | 1,500 | 1,300 | 1,000 | Sac |
| S_FOLSMLEVEL2 | 350 | 350 | 350 | 300 | 300 | Sac |

Because the reconstruction period begins in October of the year preceding the first labeled WYT year, the first three months of a generated series can lack a matching WYT assignment. The script therefore allows a DSS-based boundary fill only for the initial October--December window.

#### Validation

The five WYT-based reservoir storage level reconstructions show strong performance, with two requiring careful interpretation of historical anomalies. Trinity Levels 2 and 3 completely align with CalSim inputs using water year type patterns. Folsom Level 2, and Shasta Level 2 show very limited mismatches.

::::{tab-set}
:::{tab-item} Folsom Level 2
![Reservoir Storage Curves Overview](figures/s3-inputs_reservoir-storage-curves.png)

*Folsom Level 2 (minimum pool) storage reconstruction, 1921--2021. Actual CalSim input (blue) and WYT-based reconstruction (orange) show step-function behavior alternating between approximately 300 and 350 TAF depending on water year type. Agreement is near-perfect, with only brief departures visible in a few years (~1951, 1978, 1985, 1993)*
:::
:::{tab-item} Shasta Level 2
![Reservoir Storage WYT Alignment](figures/s3-inputs_reservoir-storage-wyt-alignment.png)

*Shasta Level 2 (S_SHASTA) storage reconstruction, 1921--2021. Reconstructed WYT-based values (orange) step between approximately 800 and 2,000 TAF depending on water year type. Actual CalSim inputs (blue) are available only in limited time windows (circa 1989--1995 and 2009--2021), showing general agreement in the overlap periods with minor mismatches in level assignment.*
:::
::::


**Shasta Level 2** target values were verified against the CalSim 3 WRESL operating rules and the historical SV timeseries. Shasta Level 2 is *not* a fixed constant--it varies substantially with water year type, from 2,000 TAF in wet years down to 650 TAF in critical years.

**Trinity Levels 2 and 3** track Sacramento Valley index patterns with high fidelity. **Folsom Level 2** shows remarkably consistent step-function behavior between 300 and 350 TAF, confirming that WYT averaging captures the essential operational pattern.

### Monthly Schedule Levels

Monthly schedule series use a fixed 12-month seasonal pattern that repeats identically every year regardless of water year type. **Don Pedro Level 4** (flood control) uses this pattern, with values ranging from 1,660 TAF (October) to 2,030 TAF (June), reflecting the seasonal flood reservation space cycle.

#### Validation

::::{tab-set}
:::{tab-item} Don Pedro Level 4
![Reservoir Storage Validation](figures/s3-inputs_reservoir-storage-validation.png)

*Don Pedro Level 4 (S_PEDRO) storage reconstruction validation, 1921--2021. Reconstructed values (orange) closely track actual CalSim inputs (blue) across the seasonal range of approximately 1,700--2,030 TAF. One anomalous drawdown to approximately 1,250 TAF around 1977--1980 in the historical record is not replicated by the reconstruction, consistent with the identified unique operational event.*
:::
::::

## References
California Department of Water Resources (DWR). 2024. “Climate Readiness:
Using Advanced Lasers and Sonar to Determine if Lake Oroville Has Lost
Capacity.” Published June 26, 2024. California Department of Water Resources.

Knowles, N., and Cronkite-Ratcliff, C., 2018. *Modeling Managed Flows in
the Sacramento/San Joaquin Watershed, California, Under Scenarios of
Future Change for CASCaDE2*. U.S. Geological Survey Open-File Report
2018–1101. https://doi.org/10.3133/ofr20181101

U.S. Army Corps of Engineers (USACE). 1970. *Oroville Dam and Reservoir,
Feather River, California: Report on Reservoir Regulation for Flood Control,
Appendix IV to Master Manual of Reservoir Regulation, Sacramento River Basin,
California*. Sacramento District, Corps of Engineers, Sacramento, California.



