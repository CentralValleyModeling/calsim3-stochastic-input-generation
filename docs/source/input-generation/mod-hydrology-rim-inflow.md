# mod_hydrology/rim_inflow

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/rim_inflow/`  
Rim-inflow SVs from the rim-inflow model's arc flows
```


Rim inflows are the streamflow entering the CalSim 3 model domain from surrounding mountain and foothill watersheds. They are major hydrologic drivers of reservoir inflows and downstream streamflows in the modeled river and tributary network, which makes their accurate reconstruction one of the more important components of the stochastic input generation effort. Of the 241 total rim inflow variables, 227 require stochastic generation (13 have missing historical data and 1 is unused).

The rim-inflow model ({doc}`mod-forcing-inflows`; SAC-SMA in the delivered sets) simulates monthly flow on the 196 rim arcs for each weather set. `_1_build_rim_inflow.py --product historical|A|B` builds the rim-inflow SVs from those arcs with no bias correction.

## Methodology

### From arcs to SVs

`reference/CalSim3_inflow_mapping.csv` gives each SV one method:

| Method | SVs | Series |
|--------|----:|--------|
| arc | 196 | The model's arc as it is. |
| sum | 23 | The 11 UNIMP anchors, each the sum of its arcs; their `_UHH` twins, equal to the anchor as in CalSim 3; and I422, a copy of I_LOSVQ. |
| qmap | 5 | The aliases FOLSM_INFLOW, FOLSOM_INFLOW, I_MLRTN_IMP, I_MELON_FCST and I_EBTML, quantile-mapped from a model series. |
| gap | 3 | I_SJR258, I_SJR265 and I_TUO054, which SAC-SMA does not simulate: quantile-mapped like the aliases, or the model's own arc when a model has it (VIC). |
| zero | 1 | I_RUB002, zero in CalSim 3. |
| wyt | 1 | I_JBP006, a San Joaquin year-type average that `mod_other/miscellaneous` builds once the year types exist. |
| none | 12 | No series. With I_RUB002 these are the 13 SVs the inventory marks Missing. |

An anchor is the sum of its arcs, so tributaries and anchor agree in every month. UNIMP_SRBB adds the Sacramento valley node I_SRBB_VAL, the valley floor between the tributaries and Bend Bridge, to its 8 tributary arcs.

SAC-SMA's arc flows already include its share model, which divides the flow of each multi-arc system among that system's arcs (139 of the 196).

### Quantile-mapped SVs

The eight quantile-mapped SVs follow the framework in [Quantile Mapping](../methods.md#quantile-mapping). Each map is fitted per calendar month from the CalSim 3 source series to the CalSim 3 SV over WY 1950-2018 and applied to the model's source series, so the SV carries the model's error like the arcs it comes from. Product B is mapped once over all ten chunks.

### Outputs

Historical_Unsplit and Product A cover the whole model run, WY 1916-2018, and their delivery files keep WY 1922-2018. Product B has one file per SV and chunk, each labelled WY 1922-2021. The builder copies the manifest of the model run beside its outputs, and the absorb fits and both compilers stop unless that run comes from the configured model at its pin.

### Skill evaluation

`_2_skill_evaluation.py` scores SAC-SMA's Historical_Unsplit run against CalSim 3, month by month, beside the VIC flows of v1.0 before their quantile maps. The script does not score Product A against CalSim 3: its temperature is detrended, so its difference from CalSim 3 mixes the warming response with model error. The windows follow the years dPL-CalSim trains on, WY 1950-1975 and WY 1986-2015 (`TRAIN_WY` at the pinned commit).

| Window | SAC-SMA median KGE | VIC median KGE | SAC-SMA median abs. PBIAS (%) | VIC median abs. PBIAS (%) |
|--------|-------:|-------:|-------:|-------:|
| WY 1976-1985, held out | 0.81 | 0.58 | 7.3 | 20.1 |
| WY 2016-2018, after training | 0.75 | 0.60 | 12.3 | 24.3 |
| Training years | 0.85 | 0.58 | 3.4 | 21.3 |
| WY 1922-1949, diagnostic | 0.76 | 0.49 | 12.7 | 26.6 |

_Median over the 196 rim arcs of monthly KGE and absolute percent bias against CalSim 3 (`arc_skill_by_kind.csv`). The evaluation treats WY 1922-1949 as diagnostic because the weather record before 1950 is less certain._

The script also writes the response to the detrending, Product A minus Historical_Unsplit by period. In the Sacramento four-river sum, Product A's April-July share of annual flow is 6.8 points lower over WY 1922-1935 and 1.1 points lower over WY 1991-2018.

## Results from v1.0

The text and figures of this section come from v1.0, which quantile-mapped VIC streamflow onto each CalSim 3 rim inflow (trained on WY 1922-1971, validated on WY 1972-2018 with Product A) and rescaled the tributaries of each anchor watershed to the anchor's mapped flow.

Quantile mapping improved monthly skill across the rim inflow network. On the normalized NSE scale of the figure below, the network average rose from 0.68 (raw VIC) to 0.79 after quantile mapping.

Skill is expressed as normalized NSE, $1/(2-\text{NSE})$, which maps NSE onto the 0-1 range (0.5 corresponds to NSE = 0 and 1.0 to a perfect score). The two curves are sorted independently, so the figure compares the distribution of skill rather than location by location pairs: quantile mapping shifts the entire distribution upward, with the largest gains in the low tail.

```{image} figures/s3-inputs_rim-inflow-skill-normalized-nse.png
:alt: Rim Inflow Skill (Normalized NSE)
:width: 60%
:align: center
```

_Monthly skill (normalized NSE) across all CalSim 3 rim inflow locations, sorted lowest to highest, for raw VIC (blue) and quantile-mapped (VIC-QMAP, red) flows._

The validation shows that quantile mapping restores seasonal patterns and reduces bias in monthly exceedance across the rim inflow network. The NSE gains reflect improved timing and magnitude agreement at the monthly timestep.

### Monthly validation at anchor watersheds
The figures below compare average monthly error relative to the CalSim 3 historical record, alongside average monthly and annual flow at each anchor location. In the average monthly error bar chart, each anchor's bar rises above zero where the reconstructed flow overestimates the historical target and falls below zero where it underestimates the historical target. Quantile mapping sharply reduces the raw VIC errors across the anchor watersheds, most clearly the late spring underestimation seen in the raw VIC panel of the Average Monthly Error Relative to CalSim 3 figure below.

Several challenges remain in the quantile-mapped flows. In the VIC-QMAP panel, a residual wet season overestimate is the most persistent issue at Bend Bridge, Oroville, and Yuba, where flows remain too high even after quantile mapping corrects distributional characteristics. At Oroville and Yuba this overestimate is concentrated in the April through June snowmelt runoff, sharpest in May, while at Bend Bridge it spans the broader December through May wet season and peaks earlier, around March and April. Folsom shows a modest negative bias after quantile mapping, concentrated in the winter months. San Joaquin shows a persistent dry bias across the year, largest in late spring around May and June, despite overall improvements.

Because the quantile mapping is trained on WY 1922-1971, these residual biases over the WY 1972-2018 validation period can also reflect differences between the training and validation period distributions.

```{image} figures/s3-inputs_rim-inflow-monthly-error-anchors.png
:alt: Average Monthly Error at Anchor Watersheds
:width: 100%
:align: center
```

_Average monthly error relative to CalSim 3 historical inflows (TAF/month) at the nine aggregate anchor watersheds (Shasta is included within Bend Bridge/UNIMP_SRBB), WY 1972-2018, for raw VIC (left) and VIC-QMAP (right) flows; positive values indicate the validation result exceeds the historical CalSim 3 inflow, negative values indicate it falls short._

The panels below show each of the ten anchor watersheds over the validation period: average monthly flow for the CalSim 3 historical target (black), raw VIC
(blue), and quantile-mapped VIC (VIC-QMAP, red), with box plots of annual water year totals at
right. The Folsom panel illustrates the typical correction, where quantile mapping removes raw
VIC's overestimated spring peak and restores the missing summer baseflow. The Shasta panel is the opposite case: its quantile-mapped flow stays close to raw VIC and well above the historical record through the wet season.

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

_Average monthly flow (left) and box plots of annual water year totals (right) at each anchor watershed, WY 1972-2018, for CS3 historical (black), raw VIC (blue), and VIC-QMAP (red)._

### Annual validation at anchor watersheds

Relative to raw VIC, the quantile-mapped annual error shrinks markedly at some anchors (e.g.,
Oroville) but grows or changes sign at others (e.g., Bend Bridge, Folsom, Trinity), reflecting
that monthly quantile mapping does not directly constrain annual totals.

```{image} figures/s3-inputs_rim-inflow-annual-error-anchors.png
:alt: Average Annual Error at Anchor Watersheds
:width: 70%
:align: center
```

_Average annual error relative to CalSim 3 (TAF/year) at the nine aggregate anchor watersheds (Shasta is included within Bend Bridge/UNIMP_SRBB), WY 1972-2018, for raw VIC (blue) and VIC-QMAP (red) flows._

Across all rim inflow locations, annual percent bias was generally modest.

The panels below show the annual (water year total) flow and its 5-year mean at each of the ten
anchor watersheds, comparing the CalSim 3 historical target (black), raw VIC (blue), and
quantile-mapped VIC (VIC-QMAP, red) flows. The annual series shows year to year variability and individual wet or dry extremes, including short events such as the 1976-77 drought. The centered 5-year mean, labeled by middle water year, smooths individual years to highlight sustained multiyear wet and dry periods, such as the 1987-92 drought.

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

_Annual flow (top) and centered 5-year mean annual flow (bottom) at each anchor watershed, WY 1922-2018._
