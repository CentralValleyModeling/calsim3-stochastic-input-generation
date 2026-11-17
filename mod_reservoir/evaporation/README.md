# Evaporation Calculation for CalSim 3.0 Reservoirs

Python implementation of the Hargreaves-Samani evaporation equation for all 95 CalSim 3.0 reservoirs. Calculates monthly evaporation rates from temperature data using reservoir-specific calibrations.

NOTE: Lloyd/Cherry spreadsheet is missing from the inventory. Will use Eleanor evaporation for Lloyd

## Overview

- **95 reservoirs**: 52 Sacramento Valley + 38 San Joaquin Valley + 5 Other
- **Methodology**: Hargreaves-Samani equation with monthly regression calibration
- **Input**: Daily Tmax and Tmin (°C) of one weather set (Historical_Unsplit, Product A or Product B) at the WGEN cell nearest each reservoir
- **Output**: Monthly evaporation (inches/month); Historical_Unsplit and Product A are delivered over WY1922-2018, Product B as 10 chunks labelled WY1922-2021
- **Validation**: 0.00% mean difference from Excel, 100% pass rate (all 95 reservoirs)

## File Structure

```
mod_reservoir/evaporation/
├── evaporation.py                          # Core calculation module
├── _0_extract_reservoir_database.py         # Extract parameters or query database
├── _1_excel_to_python_validation.py         # Validation script
├── _2_run_reservoir_evap.py                 # Evaporation of one weather set
└── README.md                                # This file

data/BASE/CalSim3/ReservoirEvaporationSpreadsheets/   # Original Excel spreadsheets (96 files)
├── Sacramento Valley/     # 52 reservoirs
├── San Joaquin Valley/    # 38 reservoirs
└── Other/                 # 5 reservoirs

data/GENERATED/mod_reservoir/evaporation/              # All generated outputs
├── reservoir_parameters.json              # Parameters for all 95 reservoirs
└── output/
    ├── _0_reservoir_database/             # Database exports
    │   └── reservoir_database.csv
    ├── _1_excel_to_python_validation/     # Validation outputs
    │   ├── validation_results.csv
    │   ├── figures/
    │   └── reservoir_details/             # 95 individual comparison CSVs
    └── _2_run_reservoir_evap/
        ├── Historical_Unsplit/, Product_A/
        │   ├── individual_reservoirs/{Region}/{CODE}.csv
        │   ├── combined_evaporation.csv
        │   ├── summary_statistics.csv
        │   └── figures/                   # Product A
        ├── _historical_unsplit_validation/_reservoir_evaporation_historicalUnsplit_1922_2018.csv
        ├── _product_a_validation/_reservoir_evaporation_productA_1922_2018.csv
        ├── _product_b_final/reservoir_evaporation_productB_n{01..10}.csv
        └── _compare_ab/                       # --compare-a
```

## Run Scripts

0. **`_0_extract_reservoir_database.py`** - Extract parameters from Excel or query database
1. **`_1_excel_to_python_validation.py`** - Validate Python vs Excel calculations
2. **`_2_run_reservoir_evap.py`** - Evaporation of one weather set (`--product historical|A|B`), with the delivery CSV of Historical_Unsplit and Product A

All scripts resolve input/output paths via `utils.paths` (`get_module_generated_dir`, `get_base_dir`).

## Quick Start

### 0. Extract Parameters (Optional)

The `reservoir_parameters.json` file is included in `data/GENERATED/mod_reservoir/evaporation/`. To regenerate from Excel spreadsheets:

```bash
python _0_extract_reservoir_database.py --extract  # Extract from 96 Excel files
python _0_extract_reservoir_database.py             # View database summary
```

### 1. Validate Against Excel

```bash
python _1_excel_to_python_validation.py                   # All reservoirs
python _1_excel_to_python_validation.py FOLSM SHSTA OROVL # Specific reservoirs
```

Expected: 0.00% mean difference, 100% pass rate across all 95 reservoirs.

### 2. Run a Weather Set

```bash
python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product historical         # Historical_Unsplit, all reservoirs
python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A                  # Product A, all reservoirs
python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product A FOLSM SHSTA OROVL  # Product A, specific reservoirs
python mod_reservoir/evaporation/_2_run_reservoir_evap.py --product B                  # Product B, all reservoirs
```

Outputs go to `data/GENERATED/mod_reservoir/evaporation/output/_2_run_reservoir_evap/`.

## Reservoir Codes

95 CalSim 3.0 reservoirs supported. Major reservoirs: SHSTA (Shasta), OROVL (Oroville), FOLSM (Folsom), TRNTY (Trinity), RVPHB (Rollins).

```python
from evaporation import get_all_reservoir_codes
codes = get_all_reservoir_codes()  # All 95 codes
```

## Input Data

`evaporation.reservoir_weather` reads the daily weather of a set at the WGEN cell nearest the reservoir through `utils.wgen` (`nearest_cell`, `read_met`; the set folders are `utils.paths.WEATHER_SETS`):
- Format: `<prefix>_LAT_LON` (`data` for Historical_Unsplit, `meteo` for Products A and B; 6 space-delimited columns: Year, Month, Day, Precip, Tmax, Tmin)
- Uses: Tmax (°C) and Tmin (°C) only
- Period: daily 1915-01-01 to 2018-12-31 for Historical_Unsplit and Product A; Product B rows follow the stamp calendar of `utils.wgen_calendar`

Excel spreadsheets at `data/BASE/CalSim3/ReservoirEvaporationSpreadsheets/`.

## Output Format

**Individual files**: `{CODE}.csv` with columns `date, evaporation_in`

**Combined**: `combined_evaporation.csv` (wide format, one column per reservoir)

**Summary**: `summary_statistics.csv` (reservoir, lat, lon, elevation, mean/annual/min/max evaporation)

## Methodology

**Hargreaves-Samani Equation**:
```
ET0 = Elev_Factor × 0.0023 × Ra × √(Tmax - Tmin) × (Tavg + 17.8) × Days / 25.4
```

**Monthly Calibration**:
```
ET_final = adjustment_factor × (ET_uncalibrated × slope[month] + intercept[month])
```

**Elevation Adjustment**: VLOOKUP-style temperature-indexed lookup (matches Excel exactly, no interpolation)

Each reservoir has unique Ra values, calibration factors, and adjustment parameters from original Excel spreadsheets.

## Example Usage

```python
from evaporation import EvaporationCalculator, reservoir_weather

# Single reservoir, Product A, WY1922-2018
calc = EvaporationCalculator('FOLSM')
daily = reservoir_weather('FOLSM', 'A')  # Year, Month, Day, precip, tmax, tmin of the nearest cell
wy = daily['Year'] + (daily['Month'] >= 10)
monthly_evap = calc.process_daily_to_monthly(daily[(wy >= 1922) & (wy <= 2018)])
```

## Validation Results

All 95 reservoirs: **0.00% mean difference** from Excel, **100% pass rate**

Key to exact match:
- VLOOKUP-style elevation adjustment (no interpolation)
- Identical monthly regression calibration
- Matching floating-point precision

Minor differences (<10^-14 %) are machine epsilon artifacts and negligible.
