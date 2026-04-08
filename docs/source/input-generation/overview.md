# Overview

This section documents input generation across 15 input categories comprising 1,733 study variables for CalSim 3 stochastic generation. Each category represents a distinct component of California's water system modeling framework, from primary hydrologic drivers to water management constraints and operational rules.

## Input Generation Summary by Category

Table 1 shows the final inventory of input categories and variable counts extracted from the master CalSim SV inventory. The following high-level observations can be drawn from the input inventory counts:

1. **CalSimHydro dominates the variable count.** Sacramento Valley hydrology accounts for 746 of 1,733 variables (43%), reflecting the spatial resolution of water budget accounting across dozens of water balance areas. Together with Rim Inflow and Small Watersheds, these three hydrologic categories comprise 69% of all study variables.

2. **Most variables require stochastic generation.** Of the 1,733 total, 1,465 (85%) require active generation from synthetic climate inputs. The remaining variables are either constant or repeating (130), not used in the current baseline (106), or have zero/missing values (32).

3. **Upper Watershed Modules are largely pre-covered.** Despite 104 total variables, only 12 require new generation; the remaining 89 are already produced by other categories in the main inventory, and 3 are held constant. This cross-category overlap was identified through systematic inventory reconciliation.

4. **Miscellaneous variables are predominantly constant.** The Other category (143 variables) contains 111 constant or repeating values. Similarly, all 5 Salinity variables use repeating historical patterns.
   
**Table 1. CalSim 3 Stochastic Input Categories and Variable Counts**

| Category | Total | Generate | Missing | Const./Rep. | Not Used | Description |
|----------|------:|-------:|--------:|--------------:|---------:|-------------|
| **Rim Inflow** | 241 | 227 | 13 | 0 | 1 | Unimpaired inflows to major rim reservoirs, quantile mapped from VIC (`mod_hydrology/rim_inflow`) |
| **CalSimHydro** | 746 | 746 | 0 | 0 | 0 | Sacramento Valley hydrology: precipitation, ET, deep percolation, runoff (`mod_hydrology/calsimhydro`) |
| **CalSimHydroEE** | 17 | 17 | 0 | 0 | 0 | External Elements boundary conditions for groundwater recharge (`mod_hydrology/calsimhydro_ee`) |
| **Small Watersheds** | 210 | 210 | 0 | 0 | 0 | Small tributary contributions not resolved by VIC (`mod_hydrology/small_watersheds`) |
| **Delta Channel Depletion** | 28 | 28 | 0 | 0 | 0 | Delta agricultural demands via DETAW/DCD (`mod_hydrology/delta_channel_depletion`) |
| **Reservoir Evaporation** | 96 | 95 | 1 | 0 | 0 | Evaporation from 95 major reservoirs using Hargreaves-Samani (`mod_reservoir/evaporation`) |
| **Reservoir Storage Curves** | 9 | 7 | 0 | 2 | 0 | Storage-based terms (Oroville, Mammoth) aligned to rule curves (`mod_reservoir/storage_curves`) |
| **Instream Flows** | 6 | 3 | 0 | 1 | 2 | Minimum flow requirements: San Joaquin Restoration, Feather River (`mod_other/instream_flows`) |
| **Climate** | 57 | 56 | 0 | 0 | 1 | Point locations and basin averages for climate metrics (`mod_forcing/climate`) |
| **Upper Watershed Modules** | 104 | 12 | 0 | 3 | 89 | Preprocessed variables for upper watershed operations (`mod_other/upper_watershed`) |
| **Day-Volume Fraction** | 31 | 31 | 0 | 0 | 0 | Monthly-to-daily disaggregation fractions (`mod_other/day_volume_fractions`) |
| **Closure Terms** | 26 | 13 | 5 | 8 | 0 | Water balance closure adjustments (`mod_other/closure_terms`) |
| **Tulare Groundwater Terms** | 14 | 14 | 0 | 0 | 0 | Groundwater correlations for Tulare Basin (`mod_hydrology/tulare_gw_terms`) |
| **Salinity** | 5 | 0 | 0 | 5 | 0 | Delta salinity boundary conditions, constant/repeating (`inventory/screening/salinity`) |
| **Other** | 143 | 6 | 13 | 111 | 13 | Miscellaneous operational variables: B120 forecasts, WYT indexes, etc. (`mod_other/miscellaneous`) |
| **TOTAL** | **1,733** | **1,465** | **32** | **130** | **106** | Complete study variable set |

_Note: Total = total variables in category; Generate = variables requiring stochastic generation; Missing = variables with missing data in historical record; Constant/Rep. = variables held constant or using repeating patterns (not stochastically generated); Not Used = variables not used in DCR 2023 baseline or dynamic in CalSim 3._

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

Water year type classification (Sac 40-30-30, SJ 60-20-20) is computed in `mod_hydrology/water_year_types/` and consumed by Tiers 4-5. Upstream forcing (VIC model, wind processing) is in `mod_forcing/vic/`. Final DSS compilation and validation are in `postprocessing/sv_compile/`. Shared utilities (quantile mapping, flow indices, WYT framework) are in `utils/`.



