# Overview

This section documents input generation across 15 input categories comprising 1,733 study variables for CalSim 3 stochastic generation. The categories cover hydrologic drivers, water management constraints, and operational rules.

## Input generation summary by category

Table 1 shows the final inventory of input categories and variable counts extracted from the master CalSim SV inventory. The following high-level observations can be drawn from the input inventory counts:

1. **Hydrology modules dominate the variable count.** Watershed and valley floor hydrology collectively account for 1,256 of 1,733 variables (72%).

2. **Most variables require stochastic generation.** Of the 1,733 total, 1,465 (85%) require active generation from synthetic climate inputs. The remaining variables are either constant or repeating (130) or not used in the current baseline (138).

3. **Upper Watershed Modules are largely pre-covered.** Despite 104 total variables, only 13 require new generation; the remaining 89 are already produced dynamically in the CalSim run with the upper watershed modules turned on, and 3 are held constant.

4. **Miscellaneous variables are predominantly constant or repeating.** The Other category (143 variables) contains 111 constant or repeating values. Similarly, all 5 Salinity variables use repeating historical patterns.
   
**Table 1. CalSim 3 Stochastic Input Categories and Variable Counts**

_Total = total variables; Generate = requiring stochastic generation; Const./Rep. = constant or repeating; Not Used = not active in DCR 2023 baseline or missing historical data._

**Hydrology (mod_hydrology)**

| Category | Total | Generate | Const./Rep. | Not Used |
|----------|------:|--------:|------------:|---------:|
| [Rim Inflow](mod-hydrology-rim-inflow.md) | 241 | 227 | 0 | 14 |
| [CalSimHydro](mod-hydrology-calsimhydro.md) | 746 | 746 | 0 | 0 |
| [CalSimHydroEE](mod-hydrology-calsimhydro-ee.md) | 17 | 17 | 0 | 0 |
| [Small Watersheds](mod-hydrology-small-watersheds.md) | 210 | 210 | 0 | 0 |
| [Delta Channel Depletion](mod-hydrology-delta-channel-depletion.md) | 28 | 28 | 0 | 0 |
| [Tulare Groundwater Terms](mod-hydrology-tulare-gw.md) | 14 | 14 | 0 | 0 |
| **Subtotal** | **1,256** | **1,242** | **0** | **14** |

_Water year type classification (Sac 40-30-30, SJ 60-20-20) is computed from these rim inflows in `mod_hydrology/water_year_types/` and consumed by several downstream modules. See [Water Year Types](mod-hydrology-water-year-types.md) for details._

**Reservoir (mod_reservoir)**

| Category | Total | Generate | Const./Rep. | Not Used |
|----------|------:|--------:|------------:|---------:|
| [Reservoir Evaporation](mod-reservoir-evaporation.md) | 96 | 95 | 0 | 1 |
| [Reservoir Storage Curves](mod-reservoir-storage-curves.md) | 9 | 7 | 2 | 0 |
| **Subtotal** | **105** | **102** | **2** | **1** |

**Forcing (mod_forcing)**

| Category | Total | Generate | Const./Rep. | Not Used |
|----------|------:|--------:|------------:|---------:|
| [Climate](mod-forcing-climate.md) | 57 | 56 | 0 | 1 |
| **Subtotal** | **57** | **56** | **0** | **1** |

**Other Modules (mod_other)**

| Category | Total | Generate | Const./Rep. | Not Used |
|----------|------:|--------:|------------:|---------:|
| [Instream Flows](mod-other-instream-flows.md) | 6 | 3 | 1 | 2 |
| [Upper Watershed Modules](mod-other-upper-watershed.md) | 104 | 12 | 3 | 89 |
| [Day Volume Fractions](mod-other-day-volume-fractions.md) | 31 | 31 | 0 | 0 |
| [Closure Terms](mod-other-closure-terms.md) | 26 | 13 | 8 | 5 |
| [Salinity](mod-other-salinity.md) | 5 | 0 | 5 | 0 |
| [Other Variables](mod-other-other-variables.md) | 143 | 6 | 111 | 26 |
| **Subtotal** | **315** | **65** | **128** | **122** |

**Total: 1,733 variables (1,465 generated, 130 constant/repeating, 138 not used).**

## Data flow pipeline

The diagram below shows the processing pipeline from WGEN climate generation through final DSS compilation. Modules are organized by processing tier, where each tier depends on outputs from the tier above.

```{mermaid}
flowchart TD
    classDef wgen fill:#F9E79F,stroke:#B7950B,color:#000
    classDef forcing fill:#AED6F1,stroke:#1A5276,color:#000
    classDef hydrology fill:#A9DFBF,stroke:#1E8449,color:#000
    classDef wyt fill:#D5F5E3,stroke:#1E8449,color:#000
    classDef reservoir fill:#FAD7A0,stroke:#A04000,color:#000
    classDef other fill:#D7BDE2,stroke:#6C3483,color:#000
    classDef postproc fill:#D5D8DC,stroke:#424949,color:#000

    WGEN["WGEN<br/>Synthetic Climate<br/>(Temp + Precip)"]:::wgen

    subgraph Tier1["Tier 1: Forcing (mod_forcing)"]
        VIC["VIC Hydrologic Model"]:::forcing
        CLIMATE["Climate<br/>56 vars"]:::forcing
    end

    subgraph Tier2["Tier 2: Core Hydrology (mod_hydrology)"]
        CSHYDRO["CalSimHydro<br/>746 vars"]:::hydrology
        CSHYDRO_EE["CalSimHydroEE<br/>17 vars"]:::hydrology
        RIM["Rim Inflow<br/>227 vars"]:::hydrology
        SWS["Small Watersheds<br/>210 vars"]:::hydrology
        DCD["Delta Channel<br/>Depletion<br/>28 vars"]:::hydrology
    end

    subgraph Tier3["Tier 3: Water Year Types (mod_hydrology)"]
        WYT["Water Year Types<br/>Sac 40-30-30 / SJ 60-20-20"]:::wyt
    end

    subgraph Tier4["Tier 4: Dependent Modules"]
        EVAP["Reservoir Evap<br/>95 vars"]:::reservoir
        STORAGE["Storage Curves<br/>7 vars"]:::reservoir
        TULARE["Tulare GW<br/>14 vars"]:::hydrology
        INSTREAM["Instream Flows<br/>3 vars"]:::other
        UPPER["Upper Watershed<br/>12 vars"]:::other
        DVF["Day Volume<br/>Fractions<br/>31 vars"]:::other
        CLOSURE["Closure Terms<br/>13 vars"]:::other
        OTHER["Other / Misc<br/>6 vars"]:::other
    end

    subgraph Tier5["Tier 5: Final Compilation (postprocessing)"]
        COMPILE["sv_compile<br/>Product A / Product B DSS"]:::postproc
    end

    WGEN --> VIC
    WGEN --> CLIMATE
    WGEN --> CSHYDRO
    WGEN --> CSHYDRO_EE
    WGEN --> SWS
    WGEN --> DCD
    WGEN --> EVAP
    WGEN -->|"Dates"| CLOSURE
    VIC -->|"QMap (Flow)"| RIM
    VIC -->|"QMap (ET)"| CSHYDRO
    RIM --> WYT
    WYT --> TULARE
    WYT --> UPPER
    WYT --> OTHER
    WYT --> STORAGE
    RIM --> INSTREAM
    RIM --> UPPER
    RIM --> DVF
    RIM --> STORAGE
    CLIMATE --> COMPILE
    Tier2 --> COMPILE
    Tier3 --> COMPILE
    Tier4 --> COMPILE

    %% Arrow colors by source (linkStyle indices are 0-based, in order of appearance above)
    %% WGEN arrows: 0-7 (gold)
    linkStyle 0,1,2,3,4,5,6,7 stroke:#B7950B,stroke-width:1.5px
    %% VIC arrows: 8-9 (blue)
    linkStyle 8,9 stroke:#1A5276,stroke-width:1.5px
    %% RIM arrows: 10,15,16,17,18 (green)
    linkStyle 10,15,16,17,18 stroke:#1E8449,stroke-width:1.5px
    %% WYT arrows: 11-14 (light green)
    linkStyle 11,12,13,14 stroke:#52BE80,stroke-width:1.5px
    %% compile arrows: 19-22 (gray)
    linkStyle 19,20,21,22 stroke:#717D7E,stroke-width:1.5px
```

_Data flow from WGEN through processing tiers to final DSS compilation. Arrows indicate data dependencies between modules._




