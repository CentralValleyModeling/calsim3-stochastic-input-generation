# mod_hydrology/tulare_gw_terms

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/tulare_gw_terms/`  
Tulare Basin groundwater terms via WYT averaging
```


Groundwater pumping (`GP_GWR15`–`GP_GWR21`) and deep percolation (`DP_GWR15`–`DP_GWR21`) terms represent seven legacy Tulare Basin C2VSim areas used for groundwater pumping and deep percolation time series. These 14 terms derive from C2VSim fine grid solution outputs. They exist outside CalSim's primary water system domain, serving as placeholders that maintain groundwater dynamics in reasonable ranges without full integration into CalSim's operations.

## Methodology

Correlation testing against rim inflow variables across all 14 terms revealed correlations uniformly below 0.8, with most substantially lower. This eliminated quantile mapping as a viable approach since QM performance degrades significantly when correlation between basis and target falls below 0.7. The Progress Meeting 3 presentation included an R^2 comparison table showing QM versus WYT performance for all 14 terms, confirming WYT averaging's superiority for these low correlation variables. Water year type averaging emerged as the only practical methodology given these constraints.

The approach calculates monthly averages conditional on San Joaquin water year type classification (Wet, Above Normal, Below Normal, Dry, Critical), which is appropriate given Tulare Basin's location and hydrologic character. For each calendar month and water year type combination, historical values are averaged to produce representative patterns. These patterns are then applied to synthetic sequences based on reconstructed San Joaquin WYT classification.

Running C2VSim for 1,000 years would require land use projections, agricultural demand assumptions, and computational resources beyond Phase I scope. These terms function as placeholders that keep groundwater within a reasonable range rather than fully simulated quantities. CalSim 3 does not cover the entire Tulare region, and these terms originate from an older C2VSim fine grid solution not directly coupled to CalSim operations. The terms represent a legacy boundary condition inherited from earlier model versions where Tulare Basin dynamics were approximated rather than simulated.

This understanding informed the decision to accept WYT averaging despite its limitations. Investing significant effort in sophisticated reconstruction methods for variables that function as approximate placeholders would not be an efficient use of project resources.

## Results

### Groundwater Pumping Terms

Groundwater pumping variables show acceptable NSE values ranging from moderate to strong correspondence. The highest agreement examples demonstrate good overall fit with realistic seasonal patterns. The lowest agreement pumping term (`GP_GWR19`) still achieves acceptable results despite showing less variation than historical values, reflecting the inherent averaging effect of the WYT methodology. Drought period Product A values show less volatility than historical values, which is expected when using categorical averaging rather than continuous predictors. Given the lack of better predictive methods, this smoothing effect represents an acceptable tradeoff.

### Deep Percolation Terms

Deep percolation variables exhibit lower NSE values and reduced ability to capture signal variability compared to groundwater pumping. The highest and lowest agreement examples spanning areas 15 to 21 illustrate a range of performance, with `DP_GWR17` showing the strongest reconstruction while `DP_GWR21` shows the weakest, unable to reproduce the episodic high percolation events that dominate its variability. A consistent pattern of underestimation appears in deep percolation Product A values, suggesting potential mass balance considerations merit investigation.

::::{tab-set}
:::{tab-item} GP Highest Agreement
![Tulare GW Best Examples](figures/s3-inputs_tulare-gw-best-examples.png)
*`GP_GWR15` groundwater pumping reconstruction (WY 1972 to 2018), the GP term with the highest agreement (NSE = 0.96, PBIAS = 1.1%). Left: monthly time series cycling between approximately 0 TAF in winter and 300 to 400 TAF during summer irrigation season; Product A (orange) closely tracks historical (blue), capturing both seasonal amplitude and yearly variations in peak pumping. Right: non-exceedance CDF showing the Product A distribution closely matching the historical distribution.*
:::
:::{tab-item} GP Lowest Agreement
![Tulare GW Best GP-19](figures/s3-inputs_tulare-gw-best-gp19.png)
*`GP_GWR19` groundwater pumping reconstruction (WY 1972 to 2018), the GP term with the lowest agreement (NSE = 0.76, PBIAS = 4.0%). Left: summer peaks in historical data reach approximately 150 to 175 TAF while Product A values plateau lower, illustrating the WYT averaging smoothing effect; the Product A series captures seasonal timing but compresses the range of peak values. Right: non-exceedance CDF showing Product A values underestimating the upper tail of the distribution.*
:::
:::{tab-item} DP Highest Agreement
![Tulare GW DP Best](figures/s3-inputs_tulare-gw-dp-best.png)
*`DP_GWR17` deep percolation reconstruction (WY 1972 to 2018), the DP term with the highest agreement (NSE = 0.62, PBIAS = -2.1%). Left: historical values (blue) range from approximately 15 to 115 TAF with frequent spikes in wet months, while Product A values (orange) are compressed, capturing the general seasonal pattern but underestimating peaks in wet months. Right: non-exceedance CDF showing close agreement through the middle range with divergence in the upper tail.*
:::
:::{tab-item} DP Lowest Agreement
![Tulare GW DP Worst](figures/s3-inputs_tulare-gw-dp-worst.png)
*`DP_GWR21` deep percolation reconstruction (WY 1972 to 2018), the term with the lowest agreement overall (NSE = 0.38, PBIAS = -5.7%). Left: historical values (blue) show dramatic spikes in wet years reaching approximately 220 TAF, while Product A values (orange) remain much lower; the WYT averaging approach captures the baseline level but cannot reproduce the episodic high percolation events that dominate variability in this area. Right: non-exceedance CDF showing the Product A distribution falling well below the historical distribution at the upper tail, where the largest percolation events are not reproduced.*
:::
::::

The documented limitations are acceptable within Phase I constraints. Groundwater pumping terms reproduce historical seasonal patterns well, while deep percolation terms show reduced variability and some negative bias that should be tracked in aggregate recharge volume checks. For long term stochastic planning focused on core system performance, WYT averaging provides plausible legacy Tulare groundwater boundary behavior while clearly documenting its limitations.
