# Overview

This section documents input generation across 15 input categories comprising 1,733 study variables for CalSim 3 stochastic generation. Each category represents a distinct component of California's water system modeling framework, from primary hydrologic drivers to water management constraints and operational rules.

## Input Generation Summary by Category

Table 1 shows the final inventory of input categories and variable counts extracted from the master CalSim SV inventory. The following high-level observations can be drawn from the input inventory counts:

1. **Hydrology modules dominate the variable count.** Watershed and valley floor hydrology collectively account for 1,256 of 1,733 variables (72%).

2. **Most variables require stochastic generation.** Of the 1,733 total, 1,465 (85%) require active generation from synthetic climate inputs. The remaining variables are either constant or repeating (130), not used in the current baseline (106), or have zero/missing values (32).

3. **Upper Watershed Modules are largely pre-covered.** Despite 104 total variables, only 12 require new generation; the remaining 89 are already produced dynamically in the CalSim run with the upper watershed modules turned on, and 3 are held constant.

4. **Miscellaneous variables are predominantly constant or repeating.** The Other category (143 variables) contains 111 constant or repeating values. Similarly, all 5 Salinity variables use repeating historical patterns.
   
**Table 1. CalSim 3 Stochastic Input Categories and Variable Counts**

_Total = total variables; Generate = requiring stochastic generation; Missing = missing historical data; Const./Rep. = constant or repeating; Not Used = not active in DCR 2023 baseline._

**Hydrology (mod_hydrology)**

| Category | Total | Generate | Missing | Const./Rep. | Not Used |
|----------|------:|--------:|--------:|------------:|---------:|
| [Rim Inflow](mod-hydrology-rim-inflow.md) | 241 | 227 | 13 | 0 | 1 |
| [CalSimHydro](mod-hydrology-calsimhydro.md) | 746 | 746 | 0 | 0 | 0 |
| [CalSimHydroEE](mod-hydrology-calsimhydro-ee.md) | 17 | 17 | 0 | 0 | 0 |
| [Small Watersheds](mod-hydrology-small-watersheds.md) | 210 | 210 | 0 | 0 | 0 |
| [Delta Channel Depletion](mod-hydrology-delta-channel-depletion.md) | 28 | 28 | 0 | 0 | 0 |
| [Tulare Groundwater Terms](mod-hydrology-tulare-gw.md) | 14 | 14 | 0 | 0 | 0 |
| **Subtotal** | **1,256** | **1,242** | **13** | **0** | **1** |

_Water year type classification (Sac 40-30-30, SJ 60-20-20) is computed from these rim inflows in `mod_hydrology/water_year_types/` and consumed by several downstream modules. See [Water Year Types](mod-hydrology-water-year-types.md) for details._

**Reservoir (mod_reservoir)**

| Category | Total | Generate | Missing | Const./Rep. | Not Used |
|----------|------:|--------:|--------:|------------:|---------:|
| [Reservoir Evaporation](mod-reservoir-evaporation.md) | 96 | 95 | 1 | 0 | 0 |
| [Reservoir Storage Curves](mod-reservoir-storage-curves.md) | 9 | 7 | 0 | 2 | 0 |
| **Subtotal** | **105** | **102** | **1** | **2** | **0** |

**Forcing (mod_forcing)**

| Category | Total | Generate | Missing | Const./Rep. | Not Used |
|----------|------:|--------:|--------:|------------:|---------:|
| [Climate](mod-forcing-climate.md) | 57 | 56 | 0 | 0 | 1 |
| **Subtotal** | **57** | **56** | **0** | **0** | **1** |

**Other Modules (mod_other)**

| Category | Total | Generate | Missing | Const./Rep. | Not Used |
|----------|------:|--------:|--------:|------------:|---------:|
| [Instream Flows](mod-other-instream-flows.md) | 6 | 3 | 0 | 1 | 2 |
| [Upper Watershed Modules](mod-other-upper-watershed.md) | 104 | 12 | 0 | 3 | 89 |
| [Day Volume Fractions](mod-other-day-volume-fractions.md) | 31 | 31 | 0 | 0 | 0 |
| [Closure Terms](mod-other-closure-terms.md) | 26 | 13 | 5 | 8 | 0 |
| [Salinity](mod-other-salinity.md) | 5 | 0 | 0 | 5 | 0 |
| [Other Variables](mod-other-other-variables.md) | 143 | 6 | 13 | 111 | 13 |
| **Subtotal** | **315** | **65** | **18** | **128** | **104** |

**TOTAL: 1,733 variables -- 1,465 generated, 130 constant/repeating, 32 missing, 106 not used.**

## Data Flow Pipeline

The diagram below illustrates the end-to-end processing pipeline from WGEN climate generation through final DSS compilation. Modules are organized by processing tier, where each tier depends on outputs from the tier above.

```{mermaid}
flowchart TD
    WGEN["WGEN<br/>Synthetic Climate<br/>(Temp + Precip)"]

    subgraph Tier1["Tier 1: Forcing"]
        VIC["VIC Hydrologic Model<br/>(mod_forcing/vic)"]
    end

    subgraph Tier2["Tier 2: Climate Extraction"]
        CLIMATE["Climate<br/>56 vars<br/>(mod_forcing/climate)"]
    end

    subgraph Tier3["Tier 3: Core Hydrology"]
        CSHYDRO["CalSimHydro<br/>746 vars"]
        CSHYDRO_EE["CalSimHydroEE<br/>17 vars"]
        RIM["Rim Inflow<br/>227 vars"]
        SWS["Small Watersheds<br/>210 vars"]
        DCD["Delta Channel<br/>Depletion<br/>28 vars"]
    end

    subgraph Tier4["Tier 4: Water Year Types"]
        WYT["Sac 40-30-30<br/>SJ 60-20-20<br/>(water_year_types)"]
    end

    subgraph Tier5["Tier 5: Dependent Modules"]
        EVAP["Reservoir Evap<br/>95 vars"]
        STORAGE["Storage Curves<br/>7 vars"]
        TULARE["Tulare GW<br/>14 vars"]
        INSTREAM["Instream Flows<br/>3 vars"]
        UPPER["Upper Watershed<br/>12 vars"]
        DVF["Day Volume<br/>Fractions<br/>31 vars"]
        CLOSURE["Closure Terms<br/>13 vars"]
        OTHER["Other / Misc<br/>6 vars"]
    end

    subgraph Tier6["Tier 6: Final Compilation"]
        COMPILE["sv_compile<br/>(postprocessing)<br/>Product A / Product B DSS"]
    end

    WGEN --> VIC
    WGEN --> CLIMATE
    WGEN --> CSHYDRO
    WGEN --> CSHYDRO_EE
    WGEN --> SWS
    WGEN --> DCD
    WGEN --> EVAP
    WGEN --> CLOSURE
    VIC --> RIM
    VIC --> CSHYDRO
    RIM --> WYT
    WYT --> TULARE
    WYT --> UPPER
    WYT --> OTHER
    RIM --> INSTREAM
    RIM --> UPPER
    RIM --> DVF
    RIM --> STORAGE
    Tier3 --> COMPILE
    Tier4 --> COMPILE
    Tier5 --> COMPILE
    Tier2 --> COMPILE
```

_Data flow from WGEN through processing tiers to final DSS compilation. Arrows indicate data dependencies between modules._




