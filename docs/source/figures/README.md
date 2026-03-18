# Documentation Figures

This directory contains figures for the CalSim Synthetic Hydroclimate documentation site.

## Figures In Use

### Section 2: Methods — Original Figures

- `s2-methods_wgen-algorithm-overview.png` - Overview of the weather regime-based stochastic weather generator algorithm showing model fitting and simulation phases
- `s2-methods_wgen-sampling-patterns.png` - WGEN sampling date patterns showing which historical dates are sampled for each simulation period with 4-year block structure
- `s2-methods_oroville-inflow-comparison.png` - Comparison of Oroville inflow for CalSim 3 historical, WGEN historical VIC, and 1000-year stochastic sequences with rolling mean comparisons
- `s2-methods_qm-validation-framework.png` - Quantile mapping validation framework showing VIC streamflow as basis and CalSim input as target with training/testing period split
- `s2-methods_qm-et-cdf-comparison.png` - Empirical CDF comparison for monthly reference ET at WBA 02 showing CalSim 3 historical, raw VIC output, and quantile-mapped VIC

### Section 2: Methods — Extracted from Presentations

- `s2-methods_wgen-jittering-mechanism.png` - WGEN jittering mechanism diagram
- `s2-methods_wgen-jittering-zscore.png` - WGEN jittering Z-score transformation
- `s2-methods_wgen-jittering-precip-simulation.png` - WGEN jittering effect on precipitation simulation
- `s2-methods_oroville-streamflow-1948-2018.png` - Oroville streamflow 1948-2018 (WGEN bias check)
- `s2-methods_oroville-precip-comparison.png` - Oroville precipitation comparison (WGEN bias check)
- `s2-methods_oroville-precip-extended.png` - Oroville precipitation extended period (WGEN bias check)
- `s2-methods_sac-huc4-wgen-paper.png` - Sacramento HUC4 from WGEN paper
- `s2-methods_calsimhydro-model-response.png` - CalSimHydro model response analysis overview

### Section 3: Input Categories — Original Figures

- `s3-inputs_calsimhydro-qm-et-response.png` - CalSimHydro response to quantile-mapped ET changes (1972-2018) showing +12% deep percolation bias
- `s3-inputs_calsimhydro-precipitation-response.png` - CalSimHydro response to WGEN precipitation changes showing -18% surface runoff bias
- `s3-inputs_small-watersheds-distribution.png` - Distribution of percent difference vs. groundwater recharge magnitude in small watersheds
- `s3-inputs_delta-channel-depletion-differences.png` - Delta Channel Depletion differences from historical baseline showing range of -166 to +6 TAF/yr
- `s3-inputs_closure-terms-wgen-sampling.png` - Distribution of dominant-month contribution to each WGEN month showing 46.5% perfect mapping

### Section 3: Input Categories — Extracted from Presentations

- `s3-inputs_rim-inflow-qm-folsom.png` - QM example for Folsom inflow
- `s3-inputs_rim-inflow-qm-folsom-detail.png` - QM example for Folsom inflow (detail view)
- `s3-inputs_rim-inflow-oroville-vic-vs-calsim.png` - Oroville streamflow VIC vs CalSim comparison
- `s3-inputs_calsimhydro-monthly-response.png` - CalSimHydro monthly response summation
- `s3-inputs_calsimhydro-monthly-deep-percolation.png` - CalSimHydro monthly deep percolation response
- `s3-inputs_calsimhydro-monthly-surface-runoff.png` - CalSimHydro monthly surface runoff response
- `s3-inputs_sjr-rebalance-annual.png` - SJR Rebalance annual response
- `s3-inputs_sjr-rebalance-decomposition.png` - SJR Rebalance decomposition
- `s3-inputs_calsimhydroee-overview.png` - CalSimHydroEE overview
- `s3-inputs_calsimhydroee-differences.png` - CalSimHydroEE differences from baseline
- `s3-inputs_calsimhydroee-differences-detail.png` - CalSimHydroEE differences (detail)
- `s3-inputs_calsimhydroee-pct-differences.png` - CalSimHydroEE percent differences
- `s3-inputs_calsimhydroee-pct-differences-detail.png` - CalSimHydroEE percent differences (detail)
- `s3-inputs_reservoir-evaporation-validation.png` - Reservoir evaporation validation
- `s3-inputs_reservoir-storage-curves.png` - Reservoir storage curves overview
- `s3-inputs_reservoir-storage-validation.png` - Reservoir storage validation
- `s3-inputs_reservoir-storage-wyt-alignment.png` - Reservoir storage WYT alignment
- `s3-inputs_mammoth-pool-qm-validation.png` - Mammoth Pool QM validation
- `s3-inputs_oroville-toc-reconstruction.png` - Oroville TOC reconstruction
- `s3-inputs_feather-mif-validation.png` - Feather MIF validation
- `s3-inputs_climate-validation-precip.png` - Climate validation: precipitation
- `s3-inputs_climate-validation-temperature.png` - Climate validation: temperature
- `s3-inputs_climate-validation-vpd.png` - Climate validation: VPD
- `s3-inputs_climate-basin-results-1.png` - Climate basin results (1 of 3)
- `s3-inputs_climate-basin-results-2.png` - Climate basin results (2 of 3)
- `s3-inputs_climate-basin-results-3.png` - Climate basin results (3 of 3)
- `s3-inputs_closure-terms-location-map.png` - Closure term locations from DCR 2023, Ch. 16
- `s3-inputs_closure-terms-correlation-meeting2.png` - Closure term correlation analysis (Progress Meeting 2)
- `s3-inputs_closure-terms-wgen-source-analysis.png` - WGEN source pair distribution analysis
- `s3-inputs_closure-terms-4yr-coverage.png` - Coverage ratio in 4-year blocks
- `s3-inputs_closure-terms-correlation-boxplots.png` - Closure term correlation box plots by 4-year block
- `s3-inputs_tulare-gw-best-examples.png` - Tulare GW best QM examples
- `s3-inputs_tulare-gw-best-gp19.png` - Tulare GW best GP-19 example
- `s3-inputs_tulare-gw-dp-best.png` - Tulare GW DP best example
- `s3-inputs_tulare-gw-dp-worst.png` - Tulare GW DP worst example
- `s3-inputs_other-ndoi-precip-accretion.png` - NDOI precipitation accretion
- `s3-inputs_other-return-flows-r60n.png` - Return flows R_60N
- `s3-inputs_other-return-flows-rfs71a.png` - Return flows R_RFS71A
- `s3-inputs_other-ebtml-loss.png` - EBTML loss

## PPT Extracts Archive

The `ppt_extracts/` subdirectory contains all raw images extracted from presentation files. The figures listed above were copied from this archive with descriptive names. The archive can be deleted once all needed figures are confirmed.

## Suggested New Figures

The following figures are suggested in the documentation but not yet created:

### Quantile Mapping Methodology

1. **qm-validation-framework.png** - Diagram showing VIC streamflow as basis and CalSim input as target, with training period (1921-1971) and testing period (1972-2018) labeled

2. **qm-product-a-vs-historical-comparison.png** - Scatter plot comparing Product A validation vs Historical VIC validation for a representative rim inflow location, demonstrating minor performance difference

3. **qm-cbd-hybrid-method-comparison.png** - Three-row comparison for Colusa Basin Drain:
   - Row 1: Time series showing actual, QM-only (with overshoots), WYT-only (too smooth), and hybrid (balanced)
   - Row 2: Scatter plot actual vs reconstructed for all three methods with R² values
   - Row 3: Monthly box plots by method showing hybrid eliminates extreme tails

4. **qm-method-selection-flowchart.png** - Decision tree flowchart showing methodology selection process based on correlation assessment and variable characteristics

### Reservoir Evaporation

5. **reservoir-evap-validation-boxplots.png** - Three-panel box plot comparison showing monthly evaporation distributions for all 95 reservoirs:
   - Panel 1: Original Excel output with historical temperature
   - Panel 2: Python output with historical temperature (exact match)
   - Panel 3: Python output with Product A temperature (slight reduction)
   - Color-code by region (Sacramento, San Joaquin, west side)

### Reservoir Storage

6. **mammoth-storage-exceedance-curves.png** - Exceedance probability curves for Mammoth Pool flood space at end-of-September and end-of-February, comparing historical vs reconstructed (WY 1972-2018). Include 10th, 50th, 90th percentiles

7. **oroville-wetness-index-scatter.png** - Scatter plot of wetness index vs flood pool storage (WY 1972-2018), showing:
   - Actual CalSim inputs (gray points)
   - Pre-sedimentation water control manual (dashed red line, max 750 TAF)
   - Post-sedimentation corrected (solid blue line, max 737.3 TAF)
   - Reconstructed values (blue points)

### Instream Flows

8. **sjr-restoration-validation.png** - Dual panels:
   - Panel 1: Time series WY 1972-2018 with actual and reconstructed, highlighting threshold crossings
   - Panel 2: Scatter plot colored by WYT with 1:1 line and 2.5 MAF / 0.4 MAF threshold regions

9. **feather-mif-flowchart.png** - Flowchart visualizing Condition 3 → Condition 1/2 decision logic with threshold values annotated. Include example water years and historical frequency overlay

### Climate

10. **climate-basin-validation-timeseries.png** - Three-panel comparison for representative watershed:
    - Panel 1: Temperature showing slight positive Product A bias
    - Panel 2: Precipitation showing slight negative Product A bias
    - Panel 3: VPD showing positive bias matching temperature

11. **climate-basin-map.png** - Map of 10 watershed basins with shading indicating Product A vs Historical precipitation difference. Overlay 26 point locations, highlight Trinity watershed

### Tulare Groundwater

12. **tulare-gw-four-panel-comparison.png** - Best and worst examples for both GP and DP terms:
   - Each panel: time series (WY 1972-2018) with inset box plot by WYT
   - Annotate R² and mean annual difference

### Other Variables

13. **tule-wetlands-scatter.png** - Scatter plot actual vs reconstructed TULE_WET_INDX colored by WYT, with 1:1 line, R² annotation, marginal histograms, and drought period highlighting

14. **cbd-hybrid-method-detailed.png** - Side-by-side time series for Colusa Basin Drain showing actual historical, QM-only with overshoots, WYT-only smoothness, and hybrid balance. Include R² and NSE for each

15. **pge-allocation-validation.png** - Dual panels:
    - Panel 1: Time series WY 1972-2018 with allocation ratio (step function) and Folsom runoff (area) on secondary axis
    - Panel 2: Scatter plot of annual Folsom runoff vs allocation with threshold boundaries

### Upper Watershed Modules

16. **upper-watershed-term-counts.png** - Stacked bar chart by module showing matched to existing inventory, filtered out, and requiring new generation

17. **american-storage-forecast-seasonal.png** - Seasonal pattern for three storage forecast terms with box plots by month colored by WYT, showing winter reduction/summer augmentation

18. **s-pedro-storage-validation.png** - Three panels:
    - Panel 1: Time series showing reconstructed S_PEDRO with smooth water year transitions
    - Panel 2: Monthly ΔS scatter (Tuolumne runoff vs storage change) with QM relationship
    - Panel 3: Storage trajectory for multi-year drought demonstrating drawdown/recovery

### Day Volume Fractions

19. **day-volume-rmse-heatmap.png** - RMSE matrix between pre-1955 years (rows) and post-1955 candidates (columns), with cells colored by match quality. Highlight perfect matches and 1948 transition

20. **day-volume-validation-timeseries.png** - Validation for 1921-1948 showing:
    - Four-river index (bars)
    - Matched historical year identifier (color-coded points)
    - Perfect match indicator (stars)
    - R²/NSE metric for imperfect matches (point size)

## Figure Naming Convention

Use descriptive kebab-case names that indicate content:
- Method prefix: `qm-` (quantile mapping), `wyt-` (water year type)
- Category: `reservoir-`, `instream-`, `climate-`, `tulare-`, etc.
- Content descriptor: `-validation`, `-comparison`, `-flowchart`, `-timeseries`, `-scatter`, `-map`, etc.
- Extension: `.png` or `.jpg`

## Figure Requirements

- High resolution (300 DPI minimum for publication)
- Clear axis labels with units
- Legend when multiple series shown
- Consistent color scheme across related figures
- Annotations for key thresholds, R² values, or notable features
- Title or caption describing what is shown
