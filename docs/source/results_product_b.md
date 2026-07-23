# Results / Product B

Product B is the project's primary deliverable, a 1,000-year stochastic hydroclimate ensemble
delivered as ten 100-water-year traces (`_n01` through `_n10`). Unlike Product A, Product B has no
historical truth to validate against, because the synthetic sequences are not tied to the observed
chronology. Evaluation therefore proceeds in two distributional stages. First, the compiled input
ensemble is compared against the CalSim 3 baseline (DCR 2023) to confirm that the 10-trace
distribution brackets the historical record and that category-level biases match the patterns found
in Product A validation. Second, the full ensemble is run through CalSim 3 and the resulting system
outputs (deliveries, Delta flows, reservoir storage) are examined across the ten traces.

## Summary

In its central tendency, the Product B ensemble runs wetter than the CalSim baseline, driven by the
WGEN sampling pool and the rim-inflow hydrology bias. Its spread still extends beyond the
historical range in both directions. At the input level, the 10-trace ensemble mean
reproduces the baseline for most categories within a few percent and shows the same signed biases
found in Product A. The largest is a wet rim-inflow bias (ensemble median +7%, weighted +9%) carried
over from the WGEN post-1948 sampling pool and the VIC-to-CalSim quantile mapping. At the system
level, the ensemble runs wetter than the historical baseline on average (Delta outflow +6
to +35% across traces, CVP deliveries +1 to +8%, SWP deliveries +5 to +25%), yet individual traces
reach single-year minima *below* the historical worst year for deliveries, exports, and carryover
storage. The CalSim runs also surfaced operational edge cases. Eight of ten traces initially failed
the San Joaquin restoration cycle under extreme flows and required targeted WRESL fixes, documented
separately in the {doc}`infeasibility report </source/calsim-run/sjr_infeasibility_report>`.

## Input distribution comparison

This stage compares the compiled Product B input ensemble against the CalSim 3 baseline monthly
means. Because no held-out truth exists for the stochastic sequences, the comparison is
distributional. For each study variable the ten chunk means are compared to the single baseline
mean, and differences are aggregated by input category. The underlying data are produced by
`postprocessing/sv_compile/product_b_compilation.py`
(`product_b_vs_calsim_base_comparison.csv` and the water-year exceedance summaries).

### Summary by category

![Weighted annual percent difference by input category](figures/results-product-b/input-distribution/weighted_annual_pctdiff_by_category.png)
*Distribution of annual percent difference (Product B chunk vs CalSim baseline) by input category,
weighted by absolute baseline magnitude so that high-volume terms dominate each category's
distribution. Boxes span the interquartile range across all study variables and all ten chunks.*

The table below reports, for each category, the number of evaluated (non-zero) study variables, the
median per-variable percent difference of the ensemble mean against the baseline, and the
magnitude-weighted aggregate percent difference. Both percentages are computed on annual totals of
the ensemble-mean (10-chunk) series. The median is robust to small-denominator terms, while the
weighted aggregate reflects the basin-scale water-budget shift.

| Input Category | SVs | Median SV % Diff | Weighted Agg % Diff |
|----------------|----:|-----------------:|--------------------:|
| Rim Inflow | 228 | +7.0% | +8.9% |
| CalSimHydro | 657 | +0.0% | +0.8% |
| CalSimHydroEE | 16 | +110.3% | +89.9% |
| Climate | 56 | +1.1% | -0.1% |
| Delta Channel Depletion | 28 | -1.2% | -1.4% |
| Small Watersheds | 118 | -0.7% | -2.9% |
| Reservoir Evaporation | 95 | -2.2% | -1.2% |
| Reservoir Storage Curves | 9 | +0.2% | +2.8% |
| Tulare Groundwater Terms | 14 | -0.1% | -0.2% |
| Instream Flows | 4 | +0.8% | +1.4% |
| Upper Watershed Modules | 15 | +1.3% | +1.2% |
| Closure Terms | 21 | +0.0% | +24.1% |
| Day-Volume Fraction | 31 | +0.2% | -0.0% |
| Salinity | 5 | +1.4% | +5.2% |
| Other / Miscellaneous | 117 | +0.0% | +0.9% |

Key observations:

- **Rim inflow carries the dominant wet bias** (median +7%, weighted +9%), consistent with the
  +3.0% seen in the shorter Product A overlap and amplified here because the full 1,000-year
  ensemble samples the wetter post-1948 climate more heavily than the historical record. This signal
  propagates to the downstream flow-driven categories and to the CalSim run results below.
- **Model-driven categories stay close to baseline.** CalSimHydro (+0.0% median), Delta channel
  depletion (-1.2%), reservoir evaporation (-2.2%), and Tulare groundwater (-0.1%) all reproduce the
  baseline within a few percent, the same fidelity ranking found in Product A.
- **CalSimHydroEE shows large percentage differences** (+110% median) that reflect very small
  absolute external-element values, where modest ET shifts produce large relative changes. This
  mirrors the +83% reported in Product A and is not a basin-scale concern.
- **Closure terms and salinity show elevated weighted aggregates** driven by a few large terms and
  by the repeating-pattern fill applied to salinity, not by broad ensemble bias (their median
  per-variable differences are near zero).

### Water-year exceedance behavior

Beyond mean differences, the exceedance analysis checks whether each Product B trace preserves the
*shape* of the baseline distribution, that is, whether wet and dry water years land at the right
exceedance probabilities. The concept figure below illustrates the rank-shift metric, and the
per-section tab-set shows percent-difference and rank-shift curves for the principal flow groups.

![Water-year exceedance rank-shift concept](figures/results-product-b/input-distribution/wy_exceedance_rank_shift_concept.png)
*Rank-shift methodology. Each Product B water year is placed on the baseline exceedance curve, and
its displacement from the matching baseline percentile is measured.*

::::{tab-set}
:::{tab-item} Rim Inflow (Unimpaired)
![Rim unimpaired exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/RimUNIMP_pct_diff.png)
![Rim unimpaired rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/RimUNIMP_rank_shift.png)
:::
:::{tab-item} Rim Inflow (Total)
![Rim total exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/RimTotal_pct_diff.png)
![Rim total rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/RimTotal_rank_shift.png)
:::
:::{tab-item} CalSimHydro
![CalSimHydro exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/CalSimHydro_pct_diff.png)
![CalSimHydro rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/CalSimHydro_rank_shift.png)
:::
:::{tab-item} Delta Channel Depletion
![DCD exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/DCD_pct_diff.png)
![DCD rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/DCD_rank_shift.png)
:::
:::{tab-item} Reservoir Evaporation
![ResEvap exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/ResEvap_pct_diff.png)
![ResEvap rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/ResEvap_rank_shift.png)
:::
:::{tab-item} Small Watersheds
![SWS exceedance pct diff](figures/results-product-b/input-distribution/summary_term_exceedance/SWS_pct_diff.png)
![SWS rank shift](figures/results-product-b/input-distribution/summary_term_exceedance/SWS_rank_shift.png)
:::
::::

### Chunk-to-chunk spread

The ten traces are independent 100-year realizations, so their chunk means vary around the ensemble
mean. The figures below show, for representative categories, how the per-variable percent difference
and absolute difference are distributed across the ten chunks. Total basin-wide annual input volume
ranges from roughly 378,000 TAF (driest chunk, n02) to 396,000 TAF (wettest chunk, n08), a spread
of about 5% around the ensemble mean. The chunks are distinct hydrologic sequences rather than
repeats of one another.

::::{tab-set}
:::{tab-item} Rim Inflow
![Rim inflow chunk spread](figures/results-product-b/input-distribution/chunk_spread_by_category/Rim_Inflow.png)
:::
:::{tab-item} CalSimHydro
![CalSimHydro chunk spread](figures/results-product-b/input-distribution/chunk_spread_by_category/CalSimHydro.png)
:::
:::{tab-item} Reservoir Evaporation
![Reservoir evaporation chunk spread](figures/results-product-b/input-distribution/chunk_spread_by_category/Reservoir_Evaporation.png)
:::
:::{tab-item} Small Watersheds
![Small watersheds chunk spread](figures/results-product-b/input-distribution/chunk_spread_by_category/Small_Watersheds.png)
:::
::::

## CalSim run validation

The full Product B ensemble was run through CalSim 3 as ten 100-year traces, each reinitialized from
the common DCR 2023 baseline starting state (October 1, 1921). See
{doc}`CalSim Runs overview </source/calsim-run/overview>` for the rationale behind the 10 x 100-year
structure and the distributional (CDF-based) evaluation framing.

### Solver feasibility

Extended stochastic sequences pushed CalSim's operational rules outside their historical design
range. Eight of the ten traces initially failed during the San Joaquin restoration cycle, in four
distinct modes: high-flow Mendota Pool bookkeeping overflow (n01, n04, n05, n06), simultaneous
near-zero San Joaquin tributary inflows (n03, n07), a low-storage Friant restoration conflict (n09),
and a cold-start data extreme at the first timestep (n10). All were resolved. The first three modes
were fixed through targeted WRESL guards that activate only under out-of-range conditions, and n10
through a one-month baseline data restore. The full diagnosis, constraint-level evidence, and fixes
are in the {doc}`infeasibility report </source/calsim-run/sjr_infeasibility_report>`. These failures
are documented as operational edge cases for Phase II rather than input defects.

### Ensemble system performance

The table reports the historical baseline annual average against the range of the ten trace-level
annual averages, with the corresponding percent-difference bracket. The ensemble runs consistently
wetter than the historical baseline in the central tendency, propagating the rim-inflow wet bias.
The trace spread is wide enough that the bracket spans tens of percent for the Delta and storage
metrics.

| Group | Metric | Baseline Avg (TAF/yr) | Ensemble 10-Trace Avg Range (TAF/yr) | % Diff Bracket |
|-------|--------|---------:|---------:|---------:|
| Deliveries | CVP Total Delivery | 4,631 | 4,670 -- 4,992 | +0.8% to +7.8% |
| Deliveries | SWP Total Delivery | 2,393 | 2,502 -- 2,982 | +4.6% to +24.6% |
| Delta | Total Banks Exports | 2,484 | 2,593 -- 3,057 | +4.4% to +23.1% |
| Delta | Total Jones Exports | 2,468 | 2,496 -- 2,625 | +1.2% to +6.3% |
| Delta | SAC River at Freeport | 15,407 | 16,349 -- 18,884 | +6.1% to +22.6% |
| Delta | SJR at Vernalis | 2,607 | 2,389 -- 3,367 | -8.3% to +29.2% |
| Delta | Cache Slough | 2,475 | 2,570 -- 4,176 | +3.8% to +68.7% |
| Delta | Delta Inflow | 21,372 | 22,619 -- 27,410 | +5.8% to +28.3% |
| Delta | Delta Outflow | 15,310 | 16,284 -- 20,629 | +6.4% to +34.7% |
| Storage | Oroville | 1,896 | 1,969 -- 2,340 | +3.8% to +23.4% |
| Storage | Shasta | 2,877 | 2,977 -- 3,226 | +3.5% to +12.2% |
| Storage | San Luis (Total) | 639 | 663 -- 844 | +3.9% to +32.2% |

Although every trace averages wetter than history, individual traces reach single-year minima
*below* the historical worst year. CVP total delivery bottoms at 2,711 TAF (vs 2,967 historical),
SWP delivery at 274 TAF (vs 419), Banks exports at 421 TAF (vs 666), and Oroville storage at 26 TAF
(vs 171).

### Annual distribution (CDF) by metric

Each panel overlays the ten trace annual cumulative distribution functions against the historical
baseline CDF. The traces should bracket the baseline and extend its tails.

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery annual CDF](figures/results-product-b/calsim-run/annual_cdf/DEL_CVP_TOTAL.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery annual CDF](figures/results-product-b/calsim-run/annual_cdf/DEL_SWP_TOTAL.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports annual CDF](figures/results-product-b/calsim-run/annual_cdf/C_CAA003.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports annual CDF](figures/results-product-b/calsim-run/annual_cdf/C_DMC000.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport annual CDF](figures/results-product-b/calsim-run/annual_cdf/C_SAC048.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis annual CDF](figures/results-product-b/calsim-run/annual_cdf/C_SJR070.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow annual CDF](figures/results-product-b/calsim-run/annual_cdf/DELTAINFLOWFORNDOI.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow annual CDF](figures/results-product-b/calsim-run/annual_cdf/NDOI.png)
:::
:::{tab-item} Cache Slough
![Cache Slough annual CDF](figures/results-product-b/calsim-run/annual_cdf/C_CSL004A.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage annual CDF](figures/results-product-b/calsim-run/annual_cdf/S_OROVL.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage annual CDF](figures/results-product-b/calsim-run/annual_cdf/S_SHSTA.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage annual CDF](figures/results-product-b/calsim-run/annual_cdf/S_SLUIS_TOTAL.png)
:::
::::

### Per-trace distribution (block boxplots)

The boxplots show the annual distribution within each 100-year trace (n01--n10) alongside the
historical baseline, making trace-to-trace variability and outliers directly comparable.

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery block boxplot](figures/results-product-b/calsim-run/block_boxplots/DEL_CVP_TOTAL.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery block boxplot](figures/results-product-b/calsim-run/block_boxplots/DEL_SWP_TOTAL.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports block boxplot](figures/results-product-b/calsim-run/block_boxplots/C_CAA003.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports block boxplot](figures/results-product-b/calsim-run/block_boxplots/C_DMC000.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport block boxplot](figures/results-product-b/calsim-run/block_boxplots/C_SAC048.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis block boxplot](figures/results-product-b/calsim-run/block_boxplots/C_SJR070.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow block boxplot](figures/results-product-b/calsim-run/block_boxplots/DELTAINFLOWFORNDOI.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow block boxplot](figures/results-product-b/calsim-run/block_boxplots/NDOI.png)
:::
:::{tab-item} Cache Slough
![Cache Slough block boxplot](figures/results-product-b/calsim-run/block_boxplots/C_CSL004A.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage block boxplot](figures/results-product-b/calsim-run/block_boxplots/S_OROVL.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage block boxplot](figures/results-product-b/calsim-run/block_boxplots/S_SHSTA.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage block boxplot](figures/results-product-b/calsim-run/block_boxplots/S_SLUIS_TOTAL.png)
:::
::::

### Stitched 1,000-year time series

Stitching the ten traces end to end produces a continuous 1,000-year annual series for each metric.
The historical baseline is plotted first for reference, followed by traces n01 through n10 in
sequence, with the historical mean shown as a horizontal line. The series spans a wider range of
sustained wet and dry periods than the historical record.

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/DEL_CVP_TOTAL.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/DEL_SWP_TOTAL.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/C_CAA003.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/C_DMC000.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/C_SAC048.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/C_SJR070.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/DELTAINFLOWFORNDOI.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/NDOI.png)
:::
:::{tab-item} Cache Slough
![Cache Slough 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/C_CSL004A.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/S_OROVL.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/S_SHSTA.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage 1,000-year series](figures/results-product-b/calsim-run/timeseries_1000yr/S_SLUIS_TOTAL.png)
:::
::::

### Worst drought sequences (2- and 5-year)

For each metric, the postprocessing finds the driest 2-year and 5-year rolling-average window in
every trace and in the historical record. The panels overlay each trace's worst window (gray) on
the historical worst window (black), with the driest trace highlighted. They show how far the most
severe stochastic droughts fall below the worst sustained dry period in the historical record.

::::{tab-set}
:::{tab-item} CVP Total Delivery
![CVP Total Delivery worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/DEL_CVP_TOTAL_worst_2yr.png)
![CVP Total Delivery worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/DEL_CVP_TOTAL_worst_5yr.png)
:::
:::{tab-item} SWP Total Delivery
![SWP Total Delivery worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/DEL_SWP_TOTAL_worst_2yr.png)
![SWP Total Delivery worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/DEL_SWP_TOTAL_worst_5yr.png)
:::
:::{tab-item} Banks Exports
![Total Banks Exports worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/C_CAA003_worst_2yr.png)
![Total Banks Exports worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/C_CAA003_worst_5yr.png)
:::
:::{tab-item} Jones Exports
![Total Jones Exports worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/C_DMC000_worst_2yr.png)
![Total Jones Exports worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/C_DMC000_worst_5yr.png)
:::
:::{tab-item} SAC at Freeport
![SAC River at Freeport worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/C_SAC048_worst_2yr.png)
![SAC River at Freeport worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/C_SAC048_worst_5yr.png)
:::
:::{tab-item} SJR at Vernalis
![San Joaquin River at Vernalis worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/C_SJR070_worst_2yr.png)
![San Joaquin River at Vernalis worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/C_SJR070_worst_5yr.png)
:::
:::{tab-item} Delta Inflow
![Delta Inflow worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/DELTAINFLOWFORNDOI_worst_2yr.png)
![Delta Inflow worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/DELTAINFLOWFORNDOI_worst_5yr.png)
:::
:::{tab-item} Delta Outflow
![Delta Outflow worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/NDOI_worst_2yr.png)
![Delta Outflow worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/NDOI_worst_5yr.png)
:::
:::{tab-item} Cache Slough
![Cache Slough worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/C_CSL004A_worst_2yr.png)
![Cache Slough worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/C_CSL004A_worst_5yr.png)
:::
:::{tab-item} Oroville Storage
![Oroville Storage worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/S_OROVL_worst_2yr.png)
![Oroville Storage worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/S_OROVL_worst_5yr.png)
:::
:::{tab-item} Shasta Storage
![Shasta Storage worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/S_SHSTA_worst_2yr.png)
![Shasta Storage worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/S_SHSTA_worst_5yr.png)
:::
:::{tab-item} San Luis Storage
![Total San Luis Storage worst 2-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/2yr/S_SLUIS_TOTAL_worst_2yr.png)
![Total San Luis Storage worst 5-year sequence](figures/results-product-b/calsim-run/worst_window_sequences/5yr/S_SLUIS_TOTAL_worst_5yr.png)
:::
::::

### Range of 100-year block means

![Range of 100-year block means vs historical](figures/results-product-b/calsim-run/range/range_100yr_block_means_vs_historical.png)
*Distribution of 100-year block means across the ten traces relative to the historical baseline for
each metric. The whole-trace means cluster wetter than history, while the across-trace spread shows
how much a single 100-year planning sequence can deviate from the long-term central tendency.*

![Mean annual percent-difference heatmap](figures/results-product-b/calsim-run/range/heatmap_mean_annual.png)
*Mean annual percent difference from the historical baseline for each metric (rows) and trace
(columns). Warmer cells mark traces running wetter than history; the SJR-at-Vernalis row shows the
only consistent drier-than-history traces (n02, n07, n09).*

## Key takeaways

1. **The ensemble brackets and extends the historical record.** Trace means run wetter than the
   baseline while single-year extremes reach below the historical worst year for deliveries,
   exports, and carryover storage. This is the intended behavior for stochastic planning.

2. **The rim-inflow wet bias is the dominant input-side signal** (ensemble median +7%) and is the
   proximate cause of the wetter system-level deliveries, Delta flows, and storage. Reducing it
   depends on the WGEN sampling-pool and VIC-bias issues discussed in the
   {doc}`wrap-up </source/summary>`.

3. **Category fidelity matches Product A.** The same ranking holds. Model-driven terms
   (CalSimHydro, evaporation, DCD) track the baseline within a few percent, while small-absolute and
   index-based terms (CalSimHydroEE, salinity, closure terms) show large relative differences that
   are immaterial at basin scale.

4. **Stochastic extremes expose operational edge cases.** Eight of ten traces required WRESL fixes to
   complete the San Joaquin restoration cycle. These are feasibility limits of CalSim's historical-
   range operating rules, not input errors, and form a concrete Phase II refinement list (see the
   {doc}`infeasibility report </source/calsim-run/sjr_infeasibility_report>`).
