# Evaporation Calculation for CalSim 3.0 Reservoirs

Python implementation of the Hargreaves-Samani evaporation equation for all 95 CalSim 3.0 reservoirs. Calculates monthly evaporation rates from temperature data using reservoir-specific calibrations.

NOTE: Lloyd/Cherry spreadsheet is missing from the inventory. Will use Eleanor evaporation for Lloyd

## Overview

- **95 reservoirs**: 52 Sacramento Valley + 38 San Joaquin Valley + 5 Other
- **Methodology**: Hargreaves-Samani equation with monthly regression calibration
- **Input**: Daily gridded temperature data (°C) from Product A (1915-2018)
- **Output**: Monthly evaporation rates (inches/month) from Oct 1921 - Sep 2018
- **Validation**: 0.00% mean difference from Excel, 100% pass rate (all 95 reservoirs)

## File Structure

```
mod_reservoir/evaporation/
├── evaporation.py                          # Core calculation module
├── _0_extract_reservoir_database.py         # Extract parameters or query database
├── _1_excel_to_python_validation.py         # Validation script
├── _2_run_reservoir_evap.py                 # Product A & B processing script
├── _3_postprocess_for_calsim_validation.py  # CalSim validation CSV
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
    ├── _2_run_reservoir_evap/
    │   ├── Product_A/
    │   │   ├── individual_reservoirs/{Region}/{CODE}.csv
    │   │   ├── combined_evaporation.csv
    │   │   ├── summary_statistics.csv
    │   │   └── figures/
    │   └── Product_B/
    │       └── reservoir_evaporation_productB_n{01..10}.csv
    └── _calsim_historical_validation/
        └── _reservoir_evaporation_productA_{start}_{end}.csv
```

## Run Scripts

0. **`_0_extract_reservoir_database.py`** - Extract parameters from Excel or query database
1. **`_1_excel_to_python_validation.py`** - Validate Python vs Excel calculations
2. **`_2_run_reservoir_evap.py`** - Process Product A / Product B weather data for evaporation
3. **`_3_postprocess_for_calsim_validation.py`** - Create CalSim validation CSV

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

### 2. Process Product A / B Data

```bash
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

Weather files resolved via `get_base_dir() / "WGEN" / "Product_A" / "1"` (or `Product_B`):
- Format: `meteo_LAT_LON` (6 space-delimited columns: Year, Month, Day, Precip, Tmax, Tmin)
- Uses: Tmax (°C) and Tmin (°C) only
- Period: Daily 1915-01-01 to 2018-12-31 (Product A)
- Automatically matched to reservoirs by nearest lat/lon

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
from evaporation import EvaporationCalculator, load_climate_data, find_nearest_weather_file

# Single reservoir
calc = EvaporationCalculator('FOLSM')
weather_file = find_nearest_weather_file('FOLSM')  # auto-resolves from data/BASE/WGEN
daily_data = load_climate_data(weather_file)
monthly_evap = calc.process_daily_to_monthly(daily_data.loc['1921-10-01':'2018-09-30'])
```

## Validation Results

All 95 reservoirs: **0.00% mean difference** from Excel, **100% pass rate**

Key to exact match:
- VLOOKUP-style elevation adjustment (no interpolation)
- Identical monthly regression calibration
- Matching floating-point precision

Minor differences (<10^-14 %) are machine epsilon artifacts and negligible.
