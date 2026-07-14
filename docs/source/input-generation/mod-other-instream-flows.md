# mod_other/instream_flows

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/instream_flows/`  
Instream flow and restoration release requirements
```


Instream flow and restoration release requirements for regulated rivers based on biological opinions, settlement agreements, and operational constraints. The two primary reconstructions cover San Joaquin River Restoration flows below Friant Dam and Feather River minimum flows below Oroville. Both implementations translate original agreement methodologies into algorithms applicable to synthetic unimpaired flow sequences.

## San Joaquin River Restoration Flows

### Methodology

The San Joaquin River Restoration release requirements follow the runoff based year type structure of the restoration settlement, as summarized in the 2017 Restoration Flow Guidelines (Version 2.0), with implementation from the original Excel workbook used to generate the CalSim baseline inputs. The restoration releases divide into two CalSim input series: non-pulse base flows (REST_REQ_NP) providing minimum requirements throughout the year, and pulse flows (REST_REQ_P) adding elevated requirements during the second half of April.

Reverse engineering the workbook proved essential for understanding the conditional logic governing release schedules. The workbook embeds extensive nested IF statements and lookup tables keyed to six restoration year types, ranging from Critical-Low through Wet, plus transitional schedules between adjacent types. Converting this logic to algorithmic form required carefully tracing cell references through multiple worksheets, with particular attention to edge cases near threshold boundaries where small differences in annual runoff can trigger substantially different release schedules.

Unimpaired runoff into Millerton Lake serves as the sole input variable, and the reconstruction maps it to release requirements in two stages. First, the water year (October through September) runoff total sets an annual release allocation by restoration year type:

| Water year runoff (TAF) | Restoration year type | Annual release allocation (TAF) |
|---|---|---|
| below 400 | Critical-Low | 116.9 |
| 400 to 670 | Critical-High | 187.8 |
| 670 to 930 | Dry | 272.3 to 330.3, interpolated |
| 930 to 1,450 | Normal-Dry | 330.3 to 400.3, interpolated |
| 1,450 to 2,500 | Normal-Wet | 400.3 to 547.4, interpolated |
| 2,500 and above | Wet | 673.5 |

The allocation jumps discretely at the 400 TAF, 670 TAF, and 2.5 MAF thresholds, while the 930 TAF and 1,450 TAF breakpoints change only the interpolation slope. Second, the annual allocation maps to a flow schedule by interpolating between twelve reference schedules matching the Friant Dam default restoration flow schedules in Appendix C of the Guidelines, each specifying flow rates over twelve sub-annual blocks (half-month blocks in March and April, a three-way split of November, and multi-month blocks elsewhere). The schedule spans a restoration year running March through February, keyed to the corresponding water year runoff total. Monthly CalSim inputs follow from weighting the block flow rates by their days in each month, with rates rounded to whole CFS. In April the pulse component covers the final 16 days of the month and the non-pulse component takes the remainder. This encoding follows the CalSim workbook rather than the Guidelines, which define the pulse block as April 16-30, a period of 15 days. The workbook applies the pulse rate over 16 days and assigns the remaining volume to the non-pulse series; the discrepancy reallocates volume between the two series without altering the April total. The reconstruction retains the workbook convention to preserve consistency with the CalSim baseline inputs.


### Results

Two comparisons validate the reconstruction. The first isolates algorithm fidelity: driving the reconstruction with the same unimpaired flow series underlying the CalSim baseline reproduces the actual inputs over WY 1922-2021 with NSE of 0.99 for both the non-pulse and pulse components. Residuals exceeding 1 TAF occur in fewer than 4% of months, confined to restoration years 2004 and later where the baseline inputs depart from the pure settlement schedule.

The second comparison drives the reconstruction with the VIC-based unimpaired flows underlying Product A. In each figure below the left panel compares the reconstructed Product A series with the historical CalSim input, and the right compares their non-exceedance distributions. Over WY 1972-2018 the reconstruction achieves NSE = 0.88 for the monthly non-pulse series and NSE = 0.77 for the April pulse values. Because the algorithm itself is near exact, these differences stem from differences between the CalSim baseline and VIC-based estimates of unimpaired Millerton runoff. Non-pulse spikes correspond to years where the two runoff estimates fall on opposite sides of a schedule threshold (shaded gray in the non-pulse figure), most visibly at the 2.5 MAF threshold where the May and June requirements step to their maximum. Pulse differences instead track runoff disagreement across the steep continuous ramp in the April schedule, which climbs from 350 to 4,000 CFS as the annual allocation moves between the Normal-Dry and Normal-Wet reference schedules, so the pulse remains sensitive even when no threshold is crossed. Both behaviors follow directly from the schedule structure, confirming correct algorithm implementation. The negative PBIAS values reflect the VIC-based runoff falling below the CalSim estimate in most divergent years.

![REST_REQ_NP reconstruction](figures/s3-inputs_sjr-rest-req-np-validation.png)
*`REST_REQ_NP` non-pulse restoration requirement reconstruction (WY 1972-2018). NSE = 0.88, PBIAS = -4.7%; Product A (orange) vs historical (blue). Gray bands mark restoration years where the CalSim and VIC-based annual runoff fall on opposite sides of a schedule threshold (400 TAF, 670 TAF, or 2.5 MAF).*

![REST_REQ_P reconstruction](figures/s3-inputs_sjr-rest-req-p-validation.png)
*`REST_REQ_P` pulse restoration requirement reconstruction, April values (WY 1972-2018; pulse flows apply only during April). NSE = 0.77, PBIAS = -12.2%; Product A (orange) vs historical (blue). Differences track runoff disagreement across the steep April ramp of the release schedules rather than threshold crossings.*


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
