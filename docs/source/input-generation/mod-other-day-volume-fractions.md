# mod_other/day_volume_fractions

```{admonition} Repository Module
:class: tip

**Module:** `mod_other/day_volume_fractions/`  
Monthly-to-daily disaggregation fractions
```


Daily disaggregation factors that convert CalSim monthly volumes into daily flow patterns while preserving each monthly volume.

## Methodology

Day volume fractions provide the temporal disaggregation necessary to represent within-month flow variations in a model that operates on monthly timesteps. CalSim calculates monthly water balances and operations, but many regulatory requirements, hydropower scheduling decisions, and water quality considerations require sub-monthly resolution. The day volume fractions act as shape factors that distribute monthly totals across 28-31 daily bins while preserving monthly sums.

The day-volume-fraction methodology follows the donor-year convention documented in the DCR2023 CalSim 3 WRESL implementation. Comments in that code describe two rules: daily flows follow patterns defined as volume fraction time series from 1955-2003 historical Sacramento River flows at Freeport, and each water year from 1921 to 1954 borrows the pattern of a 1955-2003 year with similar total unimpaired Delta Inflow volume. The record extends through 2021, with the post-2003 years carried forward as observation-based patterns. This structure reflects data availability, where pre-1955 daily records required reconstruction while 1955 onward benefited from gauge observations.

The series provides up to 31 daily bins (Day 1 through Day 31) whose fractions sum to 1.0 across each month's actual days. The disaggregation applies after CalSim monthly operations determine total monthly volumes, with day fractions distributing that total across daily timesteps for sub-monthly analysis. This maintains consistency between monthly water balance calculations and daily operational simulations.

### Reverse Engineering the Bootstrapping

The WRESL code documents the donor-year convention but not the exact flow index used to choose donor years. Reconstruction proceeded in two parts: recover the donor years CalSim actually assigned, then find the index that reproduces those donor-year pairings.

**Step 1: Recover the assigned donor years.** Each pre-1955 year's daily pattern was compared against every 1955-2003 year, using root mean squared error (RMSE). When the RMSE is near zero, the two patterns are the same, which reveals the donor year CalSim borrowed from. The day volume fractions for water year 1922, for example, were borrowed from 1975. Exact donors were found for every year from 1921 to 1948 (27 years in total). Years 1949 to 1954 had no exact match in the pool, suggesting these years may have been built by a different method or from different source records.

**Step 2: Characterize 2003-2021 Extension.** Comparing 1955-2003 patterns against 2004-2021 found no exact matches, confirming that the post-2003 years are an observation-based continuation rather than borrowed. All of 1955-2021 can therefore serve as donor candidates, expanding the pool beyond the documented 1955-2003 window for generating the synthetic (Product B) sequences

**Step 3: Reconstruct the matching index.** The WRESL note says each pre-1955 year was matched to a 1955-2003 year with similar total unimpaired Delta inflow, which points to the Sacramento River as the main driver. To test this, each candidate index was used to pair every pre-1949 year with its closest 1955-2003 year, and that pick was checked against the donor CalSim 3 actually used. The counts below are how many of the 27 known donors each index reproduced:

- Four-river Sacramento index (Folsom, Oroville, Sacramento River at Bend Bridge, Yuba): 7 of 27.
- Eight-river index (the four Sacramento rivers plus Stanislaus, Tuolumne, Merced, and San Joaquin): 16 of 27.
- Eight-river index plus selected local inflows: up to 17 of 27.
- Eight-river index plus a bootstrapped best subset of extra inflows: 25 of 27 at best, leaving two unmatched.

Although Freeport lies upstream of the San Joaquin confluence, so a Sacramento index might be expected to suffice, adding the San Joaquin rivers more than doubled the matches (7 to 16). This study uses the last index above: a water year (Oct-Sep) sum of the eight unimpaired rivers plus six extra inflows (`I_LJC022`, `I_CLV026`, `I_SFM005`, `I_MOK079`, `I_CMCHE`, `I_PTH070`), listed in `reference_inflows.csv`.

**A weak hydrologic signal.** The unimpaired flow index only selects which year to borrow from. The borrowed daily fractions themselves describe impaired flow at the weirs, governed by upstream operations rather than unimpaired runoff. February day volume fractions over 1955-2021 show no clear separation by water year type or by February 8-river inflow, so wet and dry years do not take on distinct daily shapes. The within-month pattern is largely operations driven, which is why no flow index fully explains the donor assignments: the quantity being shaped is only weakly related to the index used to choose the donor.

![February day volume fractions by water year type and by February 8-river inflow](figures/s3-inputs_dvf-february-patterns.png)

_February day volume fractions, water years 1955-2021. Left: the average pattern by water year type (W, AN, BN, D, C); the curves overlap with no clear ordering. Right: individual water years colored by February 8-river inflow; wet (blue) and dry (red) years do not separate into distinct shapes. If flow magnitude controlled the daily pattern, the colors would sort into different shapes, but instead the spread looks like noise, consistent with an operations-driven impaired signal._


### Stochastic Application

For stochastic Product B generation, the expanded observation pool from 1955-2021 (or potentially 1955-2003 depending on extension assessment) provides bootstrap candidates. Each synthetic water year gets matched to the historical year with nearest flow index match, then borrows that year's day volume fraction pattern. This preserves realistic within-month flow distributions while allowing the monthly totals to follow synthetic hydrology.

The matching process emphasizes annual unimpaired flow sums as the primary similarity metric, capturing overall wetness conditions that correlate with runoff timing patterns. Wet years tend to have earlier snowmelt and storm-driven peaks, while dry years show constrained, late-season patterns. Matching on annual sum preserves these relationships even though specific storm timing differs between synthetic and historical sequences.

```{mermaid}
flowchart TD
    SYN["Synthetic Water Year<br/>(Product B)"] --> CALC_IDX["Calculate Flow Index<br/>(8-river annual sum)"]
    CALC_IDX --> MATCH["Find Nearest Historical Year<br/>by Flow Index Distance"]

    subgraph POOL["Historical Observation Pool (1955-2021)"]
        direction LR
        Y55["1955"] ~~~ Y70["1970"] ~~~ Y90["1990"] ~~~ Y21["2021"]
    end

    MATCH --> POOL
    POOL --> BEST["Best-Match Historical Year"]
    BEST --> BORROW["Borrow Day Volume<br/>Fraction Pattern<br/>(Days 1-30 per month)"]
    BORROW --> OUTPUT["Synthetic DVF<br/>(fractions sum to 1.0<br/>per month)"]

    style SYN fill:#264653,color:#fff
    style OUTPUT fill:#2d6a4f,color:#fff
    style POOL fill:#f0f4f8,stroke:#264653
```

_Day volume fraction bootstrap methodology. Each synthetic year is matched to the historical year with the nearest flow index, then borrows that year's within-month disaggregation pattern._

## Results

### Validation

Primary validation metric focuses on exact water year matches where possible, since perfect replication of assigned year indicates correct methodology application. For years without exact matches, secondary metrics include R^2 or Nash-Sutcliffe Efficiency of monthly volume fractions, assessing how well the borrowed pattern reproduces the target distribution.

The 1921-1948 validation period provides critical ground truth since exact matching demonstrates methodology success. Achieving perfect matches for majority of years in this period confirms the bootstrap approach works as documented. Remaining scatter for some years suggests potential refinements (calendar year aggregation, eight-river index, alternative Sacramento components) that warrant investigation.

:::{admonition} Suggested Plot
:class: note
Comparison matrix showing RMSE heatmap between pre-1955 years (rows) and post-1955 candidates (columns), with cells colored by match quality (white = exact match, blue gradient = increasing RMSE). Overlay annotations indicating which years achieved perfect matches and highlighting the 1948 transition. Include marginal plots showing four-river and eight-river index values for pattern assessment.
:::

:::{admonition} Suggested Plot
:class: note
Validation time series for 1921-1948 showing: (1) Four-river index for each year (bars), (2) matched historical year identifier (color-coded points), (3) perfect match indicator (star symbols), (4) R^2/NSE metric for imperfect matches (point size). This visualization demonstrates matching success rate and identifies years requiring either index refinement or acceptance of approximate matches.
:::

### Alternative Continuous Approach

Discussion explored replacing discrete year-to-year stitching with continuous interpolation. Instead of selecting the single best-matching historical year for each synthetic year, a fitted relationship between flow index and day fraction patterns could enable interpolation. This would provide more variability in stochastic outputs rather than limiting to discrete historical patterns. However, the discrete bootstrap approach maintains physical realism by using only observed patterns, avoiding potential artifacts from interpolation between years with different storm structures. The discrete method was retained as primary approach with continuous interpolation remaining an alternative for future exploration.
