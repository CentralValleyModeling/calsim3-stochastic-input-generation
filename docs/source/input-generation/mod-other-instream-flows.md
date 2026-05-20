# mod_other/instream_flows

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/instream_flows/`  
Minimum instream flow requirements
```


Minimum instream flow requirements for regulated rivers based on biological opinions, settlement agreements, and operational constraints. The two primary reconstructions cover San Joaquin River Restoration flows below Friant Dam and Feather River minimum flows below Oroville. Both implementations translate original agreement methodologies into algorithms applicable to synthetic unimpaired flow sequences.

## San Joaquin Restoration Flows

### Methodology

The San Joaquin River Restoration minimum instream flows follow the 2009 restoration settlement agreement, with implementation based on the original Excel workbook calculation methodology. The restoration releases divide into two components: non-pulse base flows providing year-round minimum requirements, and pulse flows adding elevated requirements during specific April periods. Monthly timestep calculations use weighted averages of both components.

Reverse-engineering the original Excel workbook proved essential for understanding the conditional logic governing release schedules. The workbook embeds extensive nested IF statements with threshold-dependent lookup tables that differ between normal and restoration year types. Converting this logic to algorithmic form required carefully tracing cell references through multiple worksheets, with particular attention to edge cases near threshold boundaries where small differences in annual runoff can trigger substantially different release schedules.

Unimpaired runoff into Lake Millerton serves as the sole input variable, with threshold logic determining release requirements. Below 400 TAF annual runoff, minimum base flow requirements apply. Above 2.5 MAF annual runoff, the restoration schedule reaches maximum flow levels. Between these thresholds, linear interpolation provides intermediate flow requirements. The non-pulse component covers the first 14-15 days of April, while pulse flows apply to remaining days, with monthly values computed as day-weighted averages.

### Results

Validation over WY 1972-2018 achieves R^2 values between 0.85 and 0.90, demonstrating strong performance. Observed differences stem from differences in unimpaired inflow projections between CalSim baseline inputs and reconstructed VIC-based values. Years showing spikes in residuals correspond to cases where CalSim input annual runoff exceeded the 2.5 MAF threshold while reconstructed values remained below, or vice versa for low flow conditions. These threshold crossings create discrete step changes that explain apparent discrepancies while validating correct algorithm implementation.

:::{admonition} Suggested Plot
:class: note
Dual panels showing: (1) Time series of San Joaquin Restoration flows WY 1972-2018 with actual (gray) and reconstructed (blue) values, highlighting years where threshold crossings explain differences. (2) Scatter plot of actual vs reconstructed colored by WYT, with 1:1 line and 2.5 MAF / 0.4 MAF threshold regions annotated.
:::


## Feather River Minimum Flows

### Methodology

Feather River minimum instream flows implement the 1983 agreement between DWR and the Department of Fish and Game. The agreement specifies four conditions with criteria determining minimum required flows ranging from 750 to 2,500 CFS depending on water availability indicators. The reconstruction implements Conditions 1 through 3 (750--1,700 CFS); Condition 4 (2,500 CFS) was excluded as it was never triggered in the historical record. The reconstruction translates this reference table structure into algorithmic threshold logic using Oroville unimpaired runoff as the primary predictor.

![Feather River MIF Requirements Table](figures/s3-inputs_feather-mif-table.png)
*Minimum flow requirements for the Feather River from the 1983 DWR--DFG agreement. Conditions 1--3 are implemented in the reconstruction; Condition 4 was excluded as it was never triggered in the historical record.*

#### Threshold Logic

The flowchart logic begins with Condition 3, calculating average annual Oroville unimpaired runoff for the previous water year. If runoff falls below 28% of 4.4 MAF (approximately 1.23 MAF), Condition 3 applies with 900 CFS October through February and 750 CFS March through September. If above this threshold, the algorithm calculates a two-year rolling average. Two-year average runoff below 73% of 4.4 MAF (approximately 3.21 MAF) maintains Condition 3. Above this threshold, the logic transitions to Conditions 1 and 2, distinguished by an April-July cumulative runoff threshold at 55% of 1.9 MAF (approximately 1.05 MAF). This creates a hierarchical decision structure with increasingly restrictive conditions as water availability declines.

Developing this flowchart required careful interpretation of the 1983 agreement language, which describes conditions in legal prose rather than algorithmic notation. The translation from agreement text to threshold logic was discussed extensively during the November and December progress meetings, with particular attention to whether the rolling average should be computed on a water year or calendar year basis (water year was selected as more hydrologically meaningful) and how to handle the first year of simulation where no prior-year data exists.

![Feather MIF Flowchart](figures/s3-inputs_feather-mif-flowchart.png)
*Feather River minimum instream flow decision logic based on the 1983 DWR--DFG agreement. Orange boxes are calculation steps; teal diamonds are threshold decisions; gray boxes are the resulting minimum flow conditions for the current water year.*

#### Threshold Optimization

Original agreement language referenced Oroville storage (preprocessed), but the reconstruction uses Oroville unimpaired runoff as a more direct hydrologic indicator applicable to synthetic sequences. The three key thresholds (28% of 4.4 MAF annual, 73% of 4.4 MAF two-year rolling, 55% of 1.9 MAF April-July cumulative) were optimized to maximize correspondence with actual CalSim inputs. Condition 4, representing an upper cap never exceeded in historical MIF values (which never exceeded 1,700 CFS), was excluded from the reconstruction logic.

#### Condition 4 Decision

Condition 4 from the original 1983 agreement was deliberately excluded from the reconstruction. Historical analysis showed that actual minimum instream flow values never exceeded 1,700 CFS, well below Condition 4 thresholds that would require 2,500 CFS. Including rarely or never-triggered conditions in the logic introduces unnecessary complexity and potential for spurious activations in synthetic sequences. The three-condition framework (Conditions 1, 2, 3) captures the full range of historical behavior while maintaining defensible thresholds grounded in observed operations.

### Results

The reconstructed Feather River minimum flows achieve R^2 = 0.89 over the validation period, indicating strong replication of historical patterns. The threshold-based approach successfully captures the discrete operational rules while remaining applicable to novel hydrologic sequences not present in the training data.

![Feather MIF Validation](figures/s3-inputs_feather-mif-validation.png)
*Feather River minimum required flow (CFS) validation, 1921--2021. Actual CalSim input DSS (blue) is available from approximately 1950 onward; reconstructed values (orange) cover the full period. Flow values step between discrete threshold levels (750, 800, 900, 1,000, 1,200, and 1,700 CFS) determined by the three-condition logic based on annual Oroville inflow. Strong agreement in the overlap period (R^2 = 0.89).*
