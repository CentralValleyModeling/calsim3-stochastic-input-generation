
# Day Volume Fractions

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/day_volume_fractions/`  
Monthly-to-daily disaggregation fractions
```


Daily disaggregation factors converting monthly CalSim values to daily timesteps for within-month operational analysis.

## Methodology

Day volume fractions provide the temporal disaggregation necessary to represent within-month flow variations in a model that operates on monthly timesteps. CalSim calculates monthly water balances and operations, but many regulatory requirements, hydropower scheduling decisions, and water quality considerations require sub-monthly resolution. The day volume fractions act as shape factors that distribute monthly totals across 30 daily bins while preserving monthly sums.

The original methodology documented in project files establishes three distinct periods: 1921-1954 employs bootstrapping from 1955-2003 observations based on hydrologic similarity, 1955-2003 uses observation-based patterns from Freeport flows, and 2003-2021 extends the series using matching approaches. This structure reflects data availability, where pre-1955 daily records required reconstruction while post-1955 benefited from gauge observations.

Day 1 through Day 30 values represent fractions summing to 1.0 for each month, not a single monthly value repeated 30 times. The disaggregation applies after CalSim monthly operations determine total monthly volumes, with day fractions distributing that total across daily timesteps for sub-monthly analysis. This maintains consistency between monthly water balance calculations and daily operational simulations.

### Reverse Engineering the Bootstrapping

The reconstruction required reverse-engineering the bootstrapping methodology from incomplete documentation and partial descriptions. A four-step validation process systematically confirmed the approach and identified key matching criteria.

**Step 1: Confirm 1921-1948 Bootstrapping.** Initial analysis compared day volume fraction patterns for 1921-1954 to the 1955-2003 observation pool, calculating root mean squared error between each pre-1955 year and all post-1955 candidates. Results through 1948 showed RMSE values in the millionths, indicating essentially perfect matches and confirming successful bootstrapping. However, 1948 onwards showed matches diverging significantly, suggesting either different methodology or data transition issues in that period.

**Step 2: Characterize 2003-2021 Extension.** Comparison of 1955-2003 patterns to 2003-2021 extension found no exact matches. This confirms that the extension period uses observation-based methodology continuing the post-2003 record rather than bootstrapping from earlier years. For stochastic run generation, this implies all years 1955-2021 can potentially serve as bootstrap sources, expanding the sampling pool beyond just 1955-2003.

**Step 3: Test Four-River Index Matching.** Documentation indicated matching should use "total unimpaired delta inflow," suggesting Sacramento River as primary control. Testing employed the four-river index consisting of Folsom, Oroville, Shasta (or SRBB), and Yuba unimpaired runoff summed annually. Matching synthetic years to historical years by nearest annual four-river sum produced perfect agreement for 7 years with Step 1 results. However, substantial scatter remained for other years, indicating the four-river index alone does not fully explain matching logic.

**Step 4: Investigate Eight-River Index and Calendar Year.** Sacramento River at Freeport location examination on maps shows purely Sacramento basin influence, with San Joaquin joining the system downstream. This suggests Sacramento-only indices should suffice. However, testing expanded to eight-river index adding Stanislaus, Tuolumne, Merced, and San Joaquin to capture total Central Valley unimpaired runoff. Both annual aggregation bases were tested: water year (Oct–Sep) and calendar year (Jan–Dec). The October progress meeting discussions explored whether calendar year aggregation might better align with the DWR fiscal year or federal water year planning conventions used when the original methodology was developed in the early 2000s.

Additional refinements under consideration include substituting SRBB (Shasta River Bend Bridge) for Shasta reservoir inflow to better represent valley floor conditions, and potentially adding Whiskey Town flows. Trinity River is unlikely to contribute since it drains to the Pacific with CVP diversions via tunnel to Whiskey Town rather than direct Sacramento contribution. The January progress meetings confirmed that RMSE validation against known matches provides the definitive test for selecting among these index variants.

### Sacramento vs Total Delta Inflow

The tension between Sacramento-specific indicators (Freeport location, four-river Sacramento index) and total Delta inflow (eight-river including San Joaquin) reflects uncertainty about which hydrologic region dominates day volume fraction patterns. Physically, Freeport captures Sacramento contributions before San Joaquin confluence, suggesting Sacramento indices should suffice. However, if downstream operations or Delta position influences the Freeport observation patterns, total inflow may provide better matching. Validation testing will resolve this question by identifying which index produces superior reconstruction of 1921-1948 patterns.

### Stochastic Application

For stochastic Product B generation, the expanded observation pool from 1955-2021 (or potentially 1955-2003 depending on extension assessment) provides bootstrap candidates. Each synthetic water year gets matched to the historical year with nearest flow index match, then borrows that year's day volume fraction pattern. This preserves realistic within-month flow distributions while allowing the monthly totals to follow synthetic hydrology.

The matching process emphasizes annual unimpaired flow sums as the primary similarity metric, capturing overall wetness conditions that correlate with runoff timing patterns. Wet years tend to have earlier snowmelt and storm-driven peaks, while dry years show constrained, late-season patterns. Matching on annual sum preserves these relationships even though specific storm timing differs between synthetic and historical sequences.

```{mermaid}
flowchart TD
    SYN["Synthetic Water Year\n(Product B)"] --> CALC_IDX["Calculate Flow Index\n(8-river annual sum)"]
    CALC_IDX --> MATCH["Find Nearest Historical Year\nby Flow Index Distance"]

    subgraph POOL["Historical Observation Pool (1955-2021)"]
        direction LR
        Y55["1955"] ~~~ Y70["1970"] ~~~ Y90["1990"] ~~~ Y21["2021"]
    end

    MATCH --> POOL
    POOL --> BEST["Best-Match Historical Year"]
    BEST --> BORROW["Borrow Day Volume\nFraction Pattern\n(Days 1-30 per month)"]
    BORROW --> OUTPUT["Synthetic DVF\n(fractions sum to 1.0\nper month)"]

    style SYN fill:#264653,color:#fff
    style OUTPUT fill:#2d6a4f,color:#fff
    style POOL fill:#f0f4f8,stroke:#264653
```

_Day volume fraction bootstrap methodology. Each synthetic year is matched to the historical year with the nearest flow index, then borrows that year's within-month disaggregation pattern._

## Results

### Validation

Primary validation metric focuses on exact water year matches where possible, since perfect replication of assigned year indicates correct methodology application. For years without exact matches, secondary metrics include R² or Nash-Sutcliffe Efficiency of monthly volume fractions, assessing how well the borrowed pattern reproduces the target distribution.

The 1921-1948 validation period provides critical ground truth since exact matching demonstrates methodology success. Achieving perfect matches for majority of years in this period confirms the bootstrap approach works as documented. Remaining scatter for some years suggests potential refinements (calendar year aggregation, eight-river index, alternative Sacramento components) that warrant investigation.

:::note Suggested Plot
Comparison matrix showing RMSE heatmap between pre-1955 years (rows) and post-1955 candidates (columns), with cells colored by match quality (white = exact match, blue gradient = increasing RMSE). Overlay annotations indicating which years achieved perfect matches and highlighting the 1948 transition. Include marginal plots showing four-river and eight-river index values for pattern assessment.
:::

:::note Suggested Plot
Validation time series for 1921-1948 showing: (1) Four-river index for each year (bars), (2) matched historical year identifier (color-coded points), (3) perfect match indicator (star symbols), (4) R²/NSE metric for imperfect matches (point size). This visualization demonstrates matching success rate and identifies years requiring either index refinement or acceptance of approximate matches.
:::

### Alternative Continuous Approach

Discussion explored replacing discrete year-to-year stitching with continuous interpolation. Instead of selecting the single best-matching historical year for each synthetic year, a fitted relationship between flow index and day fraction patterns could enable interpolation. This would provide more variability in stochastic outputs rather than limiting to discrete historical patterns. However, the discrete bootstrap approach maintains physical realism by using only observed patterns, avoiding potential artifacts from interpolation between years with different storm structures. The discrete method was retained as primary approach with continuous interpolation remaining an alternative for future exploration.
