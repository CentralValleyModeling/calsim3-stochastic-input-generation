# mod_hydrology/tulare_gw_terms

```{admonition} Repository Module
:class: tip

**Module:** `mod_hydrology/tulare_gw_terms/`  
Tulare Basin groundwater terms via WYT averaging
```


Groundwater pumping and deep percolation terms for Tulare Basin C2VSim areas 15-21. The 14 terms comprise seven groundwater pumping variables and seven deep percolation variables representing C2VSim fine grid solution outputs. These terms exist outside CalSim's primary water system domain, serving as placeholders that maintain groundwater dynamics in reasonable ranges without full integration into CalSim's operations.

## Methodology

Correlation testing against rim inflow variables across all 14 terms revealed correlations uniformly below 0.8, with most substantially lower. This eliminated quantile mapping as a viable approach since QM performance degrades significantly when basis-target correlation falls below 0.7. The Progress Meeting 3 presentation included an R^2 comparison table showing QM versus WYT performance for all 14 terms, confirming WYT averaging's superiority for these low-correlation variables. Water year type averaging emerged as the only practical methodology given these constraints.

The approach calculates monthly averages conditional on San Joaquin water year type classification (Wet, Above Normal, Below Normal, Dry, Critical), which is appropriate given Tulare Basin's location and hydrologic character. For each calendar month and water year type combination, historical values are averaged to produce representative patterns. These patterns are then applied to synthetic sequences based on reconstructed San Joaquin WYT classification.

Running C2VSim for 1,000 years would require land use projections, agricultural demand assumptions, and computational resources beyond Phase I scope. MSO staff provided important context during the October and November progress meetings, noting that these terms "are kind of like a placeholder that we just keep the groundwater in a reasonable range" and emphasizing "I really wouldn't put too much weight on this part of the data." CalSim 3 does not cover the entire Tulare region, and these terms originate from an older C2VSim fine grid solution not directly coupled to CalSim operations. The terms represent a legacy boundary condition inherited from earlier model versions where Tulare Basin dynamics were approximated rather than simulated.

This candid assessment from MSO informed the decision to accept WYT averaging despite its limitations. Investing significant effort in sophisticated reconstruction methods for variables that model developers themselves consider approximate placeholders would not be an efficient use of project resources.

## Results

### Groundwater Pumping Terms

Groundwater pumping variables show acceptable R^2 values ranging from moderate to strong correspondence. The best-performing examples demonstrate good overall fit with realistic seasonal patterns. The worst-performing pumping term (GP-19) still achieves acceptable results despite showing less variation than actual historical values, reflecting the inherent averaging effect of the WYT methodology. Drought period reconstruction shows less up-and-down volatility than actual values, which is expected when using categorical averaging rather than continuous predictors. Given the lack of better predictive methods, this smoothing effect represents an acceptable trade-off.

### Deep Percolation Terms

Deep percolation variables exhibit lower R^2 values and reduced ability to capture signal variability compared to groundwater pumping. Best and worst examples spanning areas 15-21 illustrate a range of performance, with Term 15 showing poor reconstruction, while Terms 19-20 demonstrate moderate improvement. A consistent pattern of underestimation appears in deep percolation reconstruction, suggesting potential mass balance considerations merit investigation.

::::{tab-set}
:::{tab-item} GP Best (R^2 = 0.96)
![Tulare GW Best Examples](figures/s3-inputs_tulare-gw-best-examples.png)
*GP_GWR15 groundwater pumping reconstruction (WY 1972 to 2018), the GP term with the highest agreement (NSE = 0.96, PBIAS = 1.1%). Left: monthly time series cycling between approximately 0 TAF in winter and 300 to 400 TAF during summer irrigation season; Product A (orange) closely tracks historical (blue), capturing both seasonal amplitude and yearly variations in peak pumping. Right: non-exceedance CDF showing the Product A distribution closely matching the historical distribution.*
:::
:::{tab-item} GP Worst (R^2 = 0.76)
![Tulare GW Best GP-19](figures/s3-inputs_tulare-gw-best-gp19.png)
*GP_GWR19 groundwater pumping reconstruction (WY 1972 to 2018), the GP term with the lowest agreement (NSE = 0.76, PBIAS = 4.0%). Left: summer peaks in historical data reach approximately 150 to 175 TAF while Product A values plateau lower, illustrating the WYT averaging smoothing effect; the Product A series captures seasonal timing but compresses the range of peak values. Right: non-exceedance CDF showing Product A values underestimating the upper tail of the distribution.*
:::
:::{tab-item} DP Best (R^2 = 0.62)
![Tulare GW DP Best](figures/s3-inputs_tulare-gw-dp-best.png)
*DP_GWR17 deep percolation reconstruction (WY 1972 to 2018), the DP term with the highest agreement (NSE = 0.62, PBIAS = -2.1%). Left: historical values (blue) range from approximately 15 to 115 TAF with frequent spikes in wet months, while Product A values (orange) are compressed, capturing the general seasonal pattern but underestimating peaks in wet months. Right: non-exceedance CDF showing close agreement through the middle range with divergence in the upper tail.*
:::
:::{tab-item} DP Worst (R^2 = 0.41)
![Tulare GW DP Worst](figures/s3-inputs_tulare-gw-dp-worst.png)
*DP_GWR21 deep percolation reconstruction (WY 1972 to 2018), the term with the lowest agreement overall (NSE = 0.38, PBIAS = -5.7%). Left: historical values (blue) show dramatic spikes in wet years reaching approximately 220 TAF, while Product A values (orange) remain much lower; the WYT averaging approach captures the baseline level but cannot reproduce the episodic high percolation events that dominate variability in this area. Right: non-exceedance CDF showing the Product A distribution falling well below the historical distribution at the upper tail, where the largest percolation events are not reproduced.*
:::
::::

:::{admonition} Suggested Plot
:class: note
Four-panel comparison showing best and worst examples for both GP and DP terms. Each panel includes time series (WY 1972-2018) with actual (gray) and reconstructed (blue) values, plus inset box plot by WYT showing how averages differ across water year types. Annotate R^2 and mean annual difference on each panel.
:::

The documented limitations are acceptable within project constraints. The groundwater pumping and deep percolation patterns provide hydrologically reasonable boundary conditions that avoid introducing systematic biases or unrealistic trends. For long-term stochastic planning focused on core system performance, maintaining plausible Tulare groundwater behavior through WYT averaging serves project objectives while acknowledging appropriate methodological boundaries.
