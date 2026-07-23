# Overview

Once all input categories are complete, the stochastic inputs are tested through full CalSim 3 model runs. This phase moves from individual component validations to system-level performance. It has two purposes: to confirm that the stochastic inputs interact correctly within the full model framework, and to produce the 1,000-year ensemble that is the primary project deliverable (Product B).

## Stochastic simulation approach

The project uses a **10 × 100-year run** structure:

- Total simulation period: 1,000 years
- Divided into 10 traces of 100 water years each
- Each trace starts with the same CalSim Baseline initial conditions (October 1 1921)

This chunked structure was selected over a single continuous 1,000-year run for both practical and analytical reasons. Analytically, the 10-trace structure enables presentation as 10 cumulative distribution functions (CDFs) rather than a single continuous 1,000-year time series. This CDF framing is more appropriate for stochastic planning: decision-makers examine the range and distribution of outcomes across traces rather than treating the synthetic sequence as a literal prediction of future chronological conditions.

From a practical standpoint, the reinitialization between traces ensures that each 100-year segment begins from a common reference state rather than inheriting potentially unrealistic conditions from the end of the previous trace. This prevents artifact propagation where an extreme drought ending one trace could bias operations at the start of the next. The starting conditions match the DCR 2023 benchmark initialization, which provides a consistent baseline for comparison.

Product B file chunking aligns with this structure: each input category produces 10 CSV files (`*_n01.csv` through `*_n10.csv`), with the first 9 months of each chunk skipped to align with October water year start. This water year alignment ensures that CalSim operational rules referencing annual or seasonal totals operate correctly from the first complete water year of each trace.

## Evaluation metrics

Outputs are compared against DCR 2023 benchmark run across multiple performance dimensions:

- **Delta flows and exports**: Net Delta Outflow Index, export limits, salinity compliance
- **Water deliveries**: State Water Project and Central Valley Project contractor allocations, shortage frequency and magnitude
- **Reservoir storage patterns**: Seasonal drawdown-refill cycles, end-of-September carryover storage distributions, drought storage trajectories

The evaluation framework emphasizes distributional comparison rather than year-by-year matching. Since the stochastic sequence represents plausible alternative hydrology rather than a prediction, success is measured by whether the 10-trace ensemble produces reasonable distributions of key performance metrics. The 10 CDFs should bracket the DCR CalSim Historical benchmark and extend into more extreme conditions (longer droughts, larger floods) that the historical record cannot sample.

## Model infeasibilities

Extended stochastic sequences may trigger CalSim operational rule interactions that rarely or never occur in historical-length simulations. Multi-year droughts exceeding historical severity can deplete carryover storage to levels where operational rules conflict, producing solver infeasibilities. Similarly, unprecedented wet sequences may fill storage to levels where flood control and environmental flow requirements interact in untested ways.

These infeasibilities are not necessarily errors in the stochastic inputs. They may reveal legitimate edge cases in CalSim's operational logic that warrant model refinement. Documentation of infeasibility patterns during the CalSim run phase provides useful feedback for Phase II planning, where operational rule modifications may be needed to handle the expanded hydrologic range that stochastic analysis explores.


