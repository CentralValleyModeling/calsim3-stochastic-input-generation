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
*GP_GWR15 groundwater pumping reconstruction (1921--2021), best-performing GP term (R^2 = 0.96). Monthly time series cycles between approximately 0 TAF in winter and 300--400 TAF during summer irrigation season. Reconstructed (orange) closely tracks actual (blue), capturing both seasonal amplitude and year-to-year variations in peak pumping.*
:::
:::{tab-item} GP Worst (R^2 = 0.70)
![Tulare GW Best GP-19](figures/s3-inputs_tulare-gw-best-gp19.png)
*GP_GWR19 groundwater pumping reconstruction (1921--2021), worst-performing GP term (R^2 = 0.70). Summer peaks in actual data reach approximately 150 TAF while reconstructed values plateau around 110 TAF, illustrating the WYT averaging smoothing effect. The reconstructed series captures seasonal timing but compresses the range of peak values, particularly missing the higher pumping years.*
:::
:::{tab-item} DP Best (R^2 = 0.64)
![Tulare GW DP Best](figures/s3-inputs_tulare-gw-dp-best.png)
*DP_GWR17 deep percolation reconstruction (1921--2021), best-performing DP term (R^2 = 0.64). Actual values (blue) range from approximately 15 to 115 TAF with frequent spikes above 80 TAF in wet months. Reconstructed values (orange) are compressed to approximately 20--75 TAF, capturing the general seasonal pattern but underestimating wet-month peaks by 30--40 TAF.*
:::
:::{tab-item} DP Worst (R^2 = 0.32)
![Tulare GW DP Worst](figures/s3-inputs_tulare-gw-dp-worst.png)
*DP_GWR21 deep percolation reconstruction (1921--2021), worst-performing term overall (R^2 = 0.32). Actual values (blue) show dramatic wet-year spikes reaching approximately 220 TAF, while reconstructed values (orange) remain within approximately 40--90 TAF. The WYT averaging approach captures the baseline level (~50 TAF) but cannot reproduce the episodic high-percolation events that dominate variability in this area.*
:::
::::

:::{admonition} Suggested Plot
:class: note
Four-panel comparison showing best and worst examples for both GP and DP terms. Each panel includes time series (WY 1972-2018) with actual (gray) and reconstructed (blue) values, plus inset box plot by WYT showing how averages differ across water year types. Annotate R^2 and mean annual difference on each panel.
:::

The documented limitations are acceptable within project constraints. The groundwater pumping and deep percolation patterns provide hydrologically reasonable boundary conditions that avoid introducing systematic biases or unrealistic trends. For long-term stochastic planning focused on core system performance, maintaining plausible Tulare groundwater behavior through WYT averaging serves project objectives while acknowledging appropriate methodological boundaries.
