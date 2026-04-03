"""
Extract Monthly Basin-Averaged Climate for UHH Locations
========================================================
Computes weighted-average monthly precipitation, temperature, and VPD for
UHH (Upper Headwater Hydrology) locations specified in reference/uhh_locations.csv.
Grid cell weights are read from mod_forcing/vic/reference/GridInfo/ files.
VPD is derived via quantile mapping from temperature using CalSim historical VPD.

Product A / Historical: one CSV per variable per location.
Product B: 10 long-format chunk CSVs per variable (100 WY each, Oct 1921 – Sep 2021).

Inputs
------
- reference/uhh_locations.csv
- mod_forcing/vic/reference/GridInfo/<location>_GridInfo.txt
- WGEN/Product_A/1/  or  WGEN/Product_B/1/  or  Historical_Climate/  (meteo files)
- reference/calsim_climate_sv.xlsx  (historical VPD target for quantile mapping)

Outputs
-------
- output/_2_uhh_basin_averages/product_a/PPT_<name>_UHH.csv
- output/_2_uhh_basin_averages/product_a/T<name>_UHH.csv
- output/_2_uhh_basin_averages/product_a/VPD<name>_UHH.csv
- output/_product_a_validation/_uhh_{precip,temperature,vpd}_productA_{start_wy}_{end_wy}.csv
- output/_product_b_final/_uhh_precip_productB_n01.csv ... n10.csv  (same pattern for temp/vpd)

Usage
-----
    cd mod_forcing/climate && python _2_uhh_basin_averages.py --source Historical
    cd mod_forcing/climate && python _2_uhh_basin_averages.py --source Product_A --scenario 1
    cd mod_forcing/climate && python _2_uhh_basin_averages.py --source Product_B --scenario 1

    # Validate Product A outputs against historical reference
    cd mod_forcing/climate && python _2_uhh_basin_averages.py --validate-outputs --scenario 1
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.quantile_mapping import qmap_single


def parse_grid_info_file(grid_info_path):
    """
    Parse a grid info file to extract grid cell coordinates and weights.
    
    Format: GridID  Latitude  Longitude  Weight1  Weight2
    
    Parameters:
    -----------
    grid_info_path : str or Path
        Path to grid info file
        
    Returns:
    --------
    pd.DataFrame with columns: grid_id, lat, lon, weight1, weight2
    """
    df = pd.read_csv(
        grid_info_path, 
        sep=r'\s+', 
        header=None,
        names=['grid_id', 'lat', 'lon', 'weight1', 'weight2']
    )
    return df


def find_meteo_file(lat, lon, data_folder):
    """
    Find the meteo file for a specific lat/lon coordinate.
    
    Parameters:
    -----------
    lat : float
        Latitude
    lon : float
        Longitude
    data_folder : str
        Path to folder containing meteo files
        
    Returns:
    --------
    str : Path to meteo file, or None if not found
    """
    # Format filename as meteo_LAT_LON
    expected_filename = f"meteo_{lat}_{lon}"
    meteo_path = os.path.join(data_folder, expected_filename)
    
    if os.path.exists(meteo_path):
        return meteo_path
    else:
        return None


def read_meteo_file(filepath, product_b=False):
    """
    Read a meteo file and return as a pandas DataFrame.
    
    File format: YEAR MONTH DAY PRECIP(mm) TMAX(C) TMIN(C)
    
    Parameters:
    -----------
    filepath : str
        Path to meteo file
    product_b : bool
        If True, skip pd.to_datetime (Product B years 1-1008 are below
        pandas Timestamp minimum ~1677). The caller assigns PeriodIndex.
        
    Returns:
    --------
    pd.DataFrame with columns: precip_mm, tmax_c, tmin_c, tavg_c
        (plus 'date' column when product_b=False)
    """
    data = pd.read_csv(
        filepath, 
        sep=r'\s+', 
        header=None,
        names=['year', 'month', 'day', 'precip_mm', 'tmax_c', 'tmin_c']
    )
    
    # Create date column only for Product A / Historical (Product B years are out of range)
    if not product_b:
        data['date'] = pd.to_datetime(data[['year', 'month', 'day']])
    
    # Calculate daily average temperature
    data['tavg_c'] = (data['tmax_c'] + data['tmin_c']) / 2.0
    
    return data


def calculate_basin_monthly_averages(grid_info_df, data_folder, date_index=None, product_b=False):
    """
    Calculate basin-averaged monthly precipitation and temperature.
    Uses weighted aggregation approach similar to small watersheds processing.

    For Product B, WGEN files have years 1-1008 (below pandas Timestamp min ~1677)
    so a daily PeriodIndex is used instead of parsing actual dates. No reindexing
    is performed; all rows in the file are used directly.

    Parameters:
    -----------
    grid_info_df : pd.DataFrame
        DataFrame with grid cell info (lat, lon, weights)
    data_folder : str
        Path to folder containing meteo files
    date_index : pd.DatetimeIndex, optional
        Full date range for Product A / Historical alignment
    product_b : bool
        If True, use PeriodIndex (no date alignment)

    Returns:
    --------
    pd.DataFrame with monthly basin-averaged precip and temp
    """
    weighted_precip_sum = None
    weighted_tavg_sum = None
    weight_total = 0.0

    for idx, row in grid_info_df.iterrows():
        lat = row['lat']
        lon = row['lon']
        weight = row['weight1']  # Using weight1 column

        # Find and read meteo file
        meteo_file = find_meteo_file(lat, lon, data_folder)

        if meteo_file is None:
            print(f"    Warning: No meteo file found for grid cell ({lat}, {lon}), skipping")
            continue

        # Read daily data
        daily_raw = read_meteo_file(meteo_file, product_b=product_b)

        if product_b:
            # Product B: years 1-1008 can't be parsed as Timestamps.
            # Assign a sequential PeriodIndex so resample() works correctly.
            n = len(daily_raw)
            period_idx = pd.period_range(start='2025-01-01', periods=n, freq='D')
            daily_data = pd.Series(daily_raw['precip_mm'].values, index=period_idx, name='precip_mm')
            tavg_s = pd.Series(
                ((daily_raw['tmax_c'].values + daily_raw['tmin_c'].values) / 2.0),
                index=period_idx, name='tavg_c'
            )
            precip_series = daily_data
            tavg_series = tavg_s
        else:
            daily_data = daily_raw.set_index('date')
            # Ensure full date coverage (fill missing with NaN)
            precip_series = daily_data.reindex(date_index)['precip_mm']
            tavg_series = daily_data.reindex(date_index)['tavg_c']

        # Apply weight and accumulate
        precip_contrib = precip_series * weight
        tavg_contrib = tavg_series * weight

        weighted_precip_sum = precip_contrib if weighted_precip_sum is None else (weighted_precip_sum + precip_contrib)
        weighted_tavg_sum = tavg_contrib if weighted_tavg_sum is None else (weighted_tavg_sum + tavg_contrib)
        weight_total += weight

    if weighted_precip_sum is None:
        raise ValueError("No valid meteo files found for any grid cells")

    # Normalize by total weight
    daily_precip_mm = weighted_precip_sum / weight_total
    daily_tavg_c = weighted_tavg_sum / weight_total

    if product_b:
        # PeriodIndex: resample with 'M' (not 'MS')
        monthly_precip_mm = daily_precip_mm.resample('M').sum()
        monthly_tavg_c = daily_tavg_c.resample('M').mean()
        monthly_df = pd.DataFrame({
            'year':          [p.year  for p in monthly_precip_mm.index],
            'month':         [p.month for p in monthly_precip_mm.index],
            'precip_inches': (monthly_precip_mm.values / 25.4),
            'tavg_f':        (monthly_tavg_c.values * 9 / 5) + 32,
        })
        # No 'date' column for Product B (synthetic year labels only)
    else:
        monthly_precip_mm = daily_precip_mm.resample('MS').sum()
        monthly_precip_inches = monthly_precip_mm / 25.4
        monthly_tavg_c = daily_tavg_c.resample('MS').mean()
        monthly_tavg_f = (monthly_tavg_c * 9 / 5) + 32
        monthly_df = pd.DataFrame({
            'year':          monthly_precip_inches.index.year,
            'month':         monthly_precip_inches.index.month,
            'precip_inches': monthly_precip_inches.values,
            'tavg_f':        monthly_tavg_f.values,
        })
        monthly_df['date'] = monthly_precip_inches.index

    return monthly_df


def read_uhh_locations(csv_file):
    """
    Read the UHH locations from CSV file.
    
    Parameters:
    -----------
    csv_file : str or Path
        Path to uhh_locations.csv
        
    Returns:
    --------
    pd.DataFrame with columns: location, grid_info_file
    """
    df = pd.read_csv(csv_file)
    # Strip whitespace from column names and values
    df.columns = df.columns.str.strip()
    df['location'] = df['location'].str.strip()
    df['grid_info_file'] = df['grid_info_file'].str.strip()
    return df


def read_target_vpd_data(excel_file, base_shorthand):
    """
    Read target historical VPD data for a specific location from CalSim climate SV Excel file.
    
    Parameters:
    -----------
    excel_file : Path
        Path to calsim_climate_sv.xlsx
    base_shorthand : str
        Base shorthand (e.g., 'FO', 'ME', 'OR')
        
    Returns:
    --------
    pd.DataFrame with columns: year, month, value (VPD in kPa)
    """
    # Construct VPD column name
    vpd_col_name = f"VPD{base_shorthand}_UHH"
    
    # Read Excel with multi-level headers (rows 0, 1, 4 are header rows)
    df = pd.read_excel(excel_file, sheet_name=0, header=[0,1,4])
    
    # Find the VPD column
    vpd_col = None
    for col in df.columns:
        if col[1] == vpd_col_name:
            vpd_col = col
            break
    
    if vpd_col is None:
        raise ValueError(f"VPD column '{vpd_col_name}' not found in Excel file")
    
    # Read dates from raw file - the date column with proper skipping
    # Headers and units are in rows 0-6, data starts at row 7 (0-indexed) = row 8 (1-indexed in Excel)
    df_raw = pd.read_excel(excel_file, sheet_name=0, header=None, skiprows=7)
    dates = pd.to_datetime(df_raw.iloc[:, 1], errors='coerce')  # Column 1 has dates
    
    # Extract VPD data - multi-level header read includes extra header rows in the data
    # Need to skip first 2 rows which are "KPA" and "PER-AVER"  
    vpd_values = df[vpd_col].values[2:]
    
    # Ensure arrays match in length
    min_len = min(len(dates), len(vpd_values))
    dates = dates.iloc[:min_len]
    vpd_values = vpd_values[:min_len]
    
    # Create DataFrame
    result = pd.DataFrame({
        'date': dates.values,
        'value': vpd_values
    })
    
    # Add year and month columns
    result['year'] = result['date'].dt.year
    result['month'] = result['date'].dt.month
    
    # Remove any rows with NaT dates or NaN values
    result = result.dropna(subset=['date', 'value'])
    
    return result[['year', 'month', 'value']]


def apply_vpd_quantile_mapping(temp_monthly, target_vpd, source_type):
    """
    Apply quantile mapping to generate VPD timeseries using temperature as basis.
    
    Parameters:
    -----------
    temp_monthly : pd.DataFrame
        Monthly temperature data with columns: year, month, tavg_f
    target_vpd : pd.DataFrame
        Target historical VPD data with columns: year, month, value (kPa)
    source_type : str
        'Product_A', 'Product_B', or 'Historical'
        
    Returns:
    --------
    pd.DataFrame with columns: year, month, vpd_kpa
    """
    # Prepare temperature data as basis simulation (full time series)
    temp_basis_sim = temp_monthly[['year', 'month', 'tavg_f']].copy()
    temp_basis_sim = temp_basis_sim.rename(columns={'tavg_f': 'value'})

    # Remove any NaN values from target VPD
    target_vpd = target_vpd.dropna(subset=['value'])

    if source_type == 'Product_B':
        # Product B has synthetic year labels (2025-3033) that don't overlap with
        # historical VPD years (1921-2018), so year-based filtering/merging won't work.
        # qmap_single builds independent per-month (1-12) distributions for basis
        # and target, so only the month labels need to be correct -- years are
        # irrelevant.  Product B months are already correct calendar months from
        # the PeriodIndex, so we use them directly (no label overwriting).
        # Use up to 1200 months (~100 WY), truncated to whichever series is shorter.
        n_calib = min(len(temp_basis_sim), len(target_vpd), 1200)
        basis_hist_temp = temp_basis_sim.iloc[:n_calib].copy().reset_index(drop=True)
        target_hist_vpd = target_vpd.iloc[:n_calib].copy().reset_index(drop=True)
    else:
        # Product_A / Historical: filter to calibration window then inner-merge
        calib_start = (1921, 10)
        calib_end   = (1971, 9)
        basis_hist_temp = temp_basis_sim[
            ((temp_basis_sim['year'] == calib_start[0]) & (temp_basis_sim['month'] >= calib_start[1])) |
            ((temp_basis_sim['year'] > calib_start[0]) & (temp_basis_sim['year'] < calib_end[0])) |
            ((temp_basis_sim['year'] == calib_end[0]) & (temp_basis_sim['month'] <= calib_end[1]))
        ].copy()
        target_hist_vpd = target_vpd[
            ((target_vpd['year'] == calib_start[0]) & (target_vpd['month'] >= calib_start[1])) |
            ((target_vpd['year'] > calib_start[0]) & (target_vpd['year'] < calib_end[0])) |
            ((target_vpd['year'] == calib_end[0]) & (target_vpd['month'] <= calib_end[1]))
        ].copy()
        # Inner-merge to align on matching year-month pairs
        calib_merged = basis_hist_temp[['year', 'month', 'value']].merge(
            target_hist_vpd[['year', 'month', 'value']],
            on=['year', 'month'], how='inner', suffixes=('_temp', '_vpd')
        )
        basis_hist_temp = calib_merged[['year', 'month', 'value_temp']].copy().rename(columns={'value_temp': 'value'})
        target_hist_vpd = calib_merged[['year', 'month', 'value_vpd']].copy().rename(columns={'value_vpd': 'value'})
    
    # Final verification
    if len(basis_hist_temp) != len(target_hist_vpd):
        raise ValueError(f"After alignment: Temperature has {len(basis_hist_temp)} months, VPD has {len(target_hist_vpd)} months")
    
    if len(basis_hist_temp) < 12:
        raise ValueError(f"Insufficient calibration data: only {len(basis_hist_temp)} months available (need at least 12)")
    
    if source_type == 'Product_B':
        print(f"    Calibration period: {len(basis_hist_temp)} months (positional alignment with historical VPD)")
    else:
        print(f"    Calibration period: {len(basis_hist_temp)} months ({calib_start} to {calib_end})")
    print(f"    Simulation period: {len(temp_basis_sim)} months")
    
    # Apply quantile mapping
    # Note: allow_negative=False to ensure VPD is non-negative
    vpd_mapped = qmap_single(
        basis_sim=temp_basis_sim,
        basis_hist=basis_hist_temp,
        target=target_hist_vpd,
        allow_negative=False
    )
    
    # Rename output column
    vpd_mapped = vpd_mapped.rename(columns={'quantile_mapped_value': 'vpd_kpa'})
    
    return vpd_mapped[['year', 'month', 'vpd_kpa']]


def process_location(shorthand, grid_info_file, grid_info_folder, data_folder, output_folder, date_index, args, excel_file):
    """
    Process a single UHH location: compute basin-averaged monthly data.
    Creates separate output files for precipitation (PPT_*), temperature (T*), and VPD (VPD*).
    
    Parameters:
    -----------
    shorthand : str
        Shorthand name of the location (e.g., 'FO_UHH', 'OR_UHH')
    grid_info_file : str
        Name of the grid info file
    grid_info_folder : Path
        Path to folder containing grid info files
    data_folder : str
        Path to folder containing meteo files
    output_folder : Path
        Path to output folder
    date_index : pd.DatetimeIndex
        Full date range for the analysis period
    args : argparse.Namespace
        Command-line arguments (needed to check source type)
    excel_file : Path
        Path to calsim_climate_sv.xlsx file with target VPD data
        
    Returns:
    --------
    dict : Summary information about the processing
    """
    # Mapping from shorthand to full name for PPT files
    name_mapping = {
        'FO': 'FOLS',
        'OR': 'OROV',
        'SH': 'SHAS',
        'YU': 'YUBA'
    }
    
    # Extract base shorthand (e.g., 'FO' from 'FO_UHH')
    base_shorthand = shorthand.replace('_UHH', '')
    
    # Construct location names
    # For precipitation: PPT_{full_name}_UHH
    if base_shorthand in name_mapping:
        ppt_location_name = f"PPT_{name_mapping[base_shorthand]}_UHH"
    else:
        ppt_location_name = f"PPT_{base_shorthand}_UHH"
    
    # For temperature: T{shorthand}_UHH
    temp_location_name = f"T{base_shorthand}_UHH"
    
    print(f"\nProcessing {shorthand}...")
    print(f"  Grid info file: {grid_info_file}")
    print(f"  Precipitation output: {ppt_location_name}")
    print(f"  Temperature output: {temp_location_name}")
    
    # Read grid info file
    grid_info_path = grid_info_folder / grid_info_file
    if not grid_info_path.exists():
        raise FileNotFoundError(f"Grid info file not found: {grid_info_path}")
    
    grid_info_df = parse_grid_info_file(grid_info_path)
    print(f"  Number of grid cells: {len(grid_info_df)}")
    print(f"  Total weight: {grid_info_df['weight1'].sum():.2f}")
    
    # Calculate basin-averaged monthly data
    monthly_data = calculate_basin_monthly_averages(
        grid_info_df, data_folder,
        date_index=date_index,
        product_b=(args.source == 'Product_B')
    )
    
    # Apply VPD quantile mapping using temperature as basis
    print(f"  Applying VPD quantile mapping...")
    try:
        target_vpd = read_target_vpd_data(excel_file, base_shorthand)
        print(f"    Target VPD data: {len(target_vpd)} months")
        
        vpd_data = apply_vpd_quantile_mapping(
            temp_monthly=monthly_data[['year', 'month', 'tavg_f']],
            target_vpd=target_vpd,
            source_type=args.source
        )
        # Merge VPD into monthly_data
        monthly_data = monthly_data.merge(vpd_data, on=['year', 'month'], how='left')
        vpd_enabled = True
        print(f"  VPD quantile mapping completed")
    except Exception as e:
        import traceback
        print(f"  Warning: VPD quantile mapping failed: {e}")
        print(f"  Error details:")
        traceback.print_exc()
        print(f"  Proceeding without VPD output")
        vpd_enabled = False
    
    # Construct VPD location name
    vpd_location_name = f"VPD{base_shorthand}_UHH"

    if args.source == 'Product_B':
        # For Product B, defer all file writing to write_product_b_chunks().
        # Return the full monthly_data so main() can compile across locations.
        print(f"  Product B: {len(monthly_data)} months loaded (will compile into chunks)")
    else:
        # For Product_A and Historical, save single files
        # Precipitation file
        ppt_data = monthly_data[['year', 'month', 'precip_inches', 'date']].copy()
        ppt_file = output_folder / f"{ppt_location_name}.csv"
        ppt_data.to_csv(ppt_file, index=False)
        print(f"  Precipitation saved: {ppt_file.name}")
        
        # Temperature file
        temp_data = monthly_data[['year', 'month', 'tavg_f', 'date']].copy()
        temp_file = output_folder / f"{temp_location_name}.csv"
        temp_data.to_csv(temp_file, index=False)
        print(f"  Temperature saved: {temp_file.name}")
        
        # VPD file (if available)
        if vpd_enabled:
            vpd_data_out = monthly_data[['year', 'month', 'vpd_kpa', 'date']].copy()
            vpd_file = output_folder / f"{vpd_location_name}.csv"
            vpd_data_out.to_csv(vpd_file, index=False)
            print(f"  VPD saved: {vpd_file.name}")
    
    # Return summary info
    summary = {
        'shorthand': shorthand,
        'ppt_location_name': ppt_location_name,
        'temp_location_name': temp_location_name,
        'vpd_location_name': vpd_location_name if vpd_enabled else 'N/A',
        'vpd_enabled': vpd_enabled,
        'grid_info_file': grid_info_file,
        'num_grid_cells': len(grid_info_df),
        'total_weight': grid_info_df['weight1'].sum(),
        'mean_monthly_precip_inches': monthly_data['precip_inches'].mean(),
        'mean_monthly_tavg_f': monthly_data['tavg_f'].mean(),
        'total_months': len(monthly_data),
        # Included for Product B chunk compilation; excluded when saving _summary.csv
        '_monthly_data': monthly_data,
    }
    if vpd_enabled:
        summary['mean_monthly_vpd_kpa'] = monthly_data['vpd_kpa'].mean()
    return summary


def create_validation_csv(
    source_dir: str = 'output/_2_uhh_basin_averages/product_a',
    validation_dir: str = 'output/_product_a_validation',
    start_wy: int = 1971,
    end_wy: int = 2018
):
    """
    Create combined validation CSVs from individual UHH basin average files.

    Reads processed PPT, T, and VPD CSVs and creates long-format CSVs
    with columns Part B, Part C, Year, Month, Value for the validation period.

    Parameters:
    -----------
    source_dir : str
        Directory containing individual PPT_*, T*, VPD* CSV files
    validation_dir : str
        Output directory for the validation CSVs
    start_wy : int
        Start water year (default: 1971)
    end_wy : int
        End water year (default: 2018)
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"Error: {source_path} not found. Run Product_A processing first.")
        return

    # Validation period: Oct of start_wy through Sep of end_wy
    start_date = pd.Timestamp(start_wy, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    print("=" * 80)
    print("Creating Validation CSVs — UHH Basin Averages")
    print("=" * 80)
    print(f"Period: WY {start_wy}-{end_wy} ({start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')})")
    print(f"Source: {source_path}")

    # Define the three variable types to process
    var_configs = [
        {
            'prefix': 'PPT_',
            'part_c': 'PRECIP',
            'value_col': 'precip_inches',
            'output_name': f'_uhh_precip_productA_{start_wy}_{end_wy}.csv',
            'label': 'Precipitation'
        },
        {
            'prefix': 'T',
            'part_c': 'Temperature',
            'value_col': 'tavg_f',
            'output_name': f'_uhh_temperature_productA_{start_wy}_{end_wy}.csv',
            'label': 'Temperature'
        },
        {
            'prefix': 'VPD',
            'part_c': 'VPD',
            'value_col': 'vpd_kpa',
            'output_name': f'_uhh_vpd_productA_{start_wy}_{end_wy}.csv',
            'label': 'VPD'
        }
    ]

    val_path = Path(validation_dir)
    val_path.mkdir(parents=True, exist_ok=True)

    for config in var_configs:
        print(f"\n--- {config['label']} ---")
        all_rows = []

        # Find matching CSV files (exclude _summary.csv)
        if config['prefix'] == 'T':
            # Temperature files: T*_UHH.csv but NOT TR, TU which could match PPT_TR etc.
            # Match files starting with T but not with PPT_ or VPD
            csv_files = sorted([
                f for f in source_path.glob('T*_UHH.csv')
                if not f.name.startswith('PPT_') and not f.name.startswith('VPD')
            ])
        else:
            csv_files = sorted(source_path.glob(f'{config["prefix"]}*_UHH.csv'))

        print(f"  Found {len(csv_files)} files")

        for csv_file in csv_files:
            location_name = csv_file.stem  # e.g., PPT_FOLS_UHH, TFO_UHH, VPDFO_UHH

            # Read individual CSV
            df = pd.read_csv(csv_file)
            df['date'] = pd.to_datetime(df['date'])

            # Filter to validation period
            mask = (df['date'] >= start_date) & (df['date'] <= end_date)
            df_filtered = df.loc[mask].copy()

            if df_filtered.empty:
                print(f"    {location_name}: no data in validation period, skipping")
                continue

            # Build long-format rows
            for _, row in df_filtered.iterrows():
                all_rows.append({
                    'Part B': location_name,
                    'Part C': config['part_c'],
                    'Year': int(row['year']),
                    'Month': int(row['month']),
                    'Value': round(row[config['value_col']], 6)
                })

            print(f"    {location_name}: {len(df_filtered)} months")

        if not all_rows:
            print(f"  No {config['label']} data found for the validation period.")
            continue

        # Write combined CSV
        output_df = pd.DataFrame(all_rows)
        output_file = val_path / config['output_name']
        output_df.to_csv(output_file, index=False)

        n_locations = output_df['Part B'].nunique()
        print(f"  Written: {output_file} ({n_locations} locations, {len(output_df)} rows)")

    print(f"\n{'=' * 80}")
    print(f"Validation CSVs complete.")
    print(f"{'=' * 80}")


###############################################################################
# Validation functions (integrated from _3_validate_uhh_outputs.py)
###############################################################################

def read_reference_data(excel_file, location_name, variable_type):
    """
    Read reference data from calsim_climate_sv.xlsx.
    
    Parameters:
    -----------
    excel_file : Path
        Path to calsim_climate_sv.xlsx
    location_name : str
        Full location name (e.g., 'PPT_FOLS_UHH', 'TFO_UHH', 'VPDFO_UHH')
    variable_type : str
        'precip', 'temp', or 'vpd'
        
    Returns:
    --------
    pd.DataFrame with columns: year, month, value
    """
    # Read Excel with multi-level headers
    df = pd.read_excel(excel_file, sheet_name=0, header=[0, 1, 4])
    
    # Find the column
    col_found = None
    for col in df.columns:
        if col[1] == location_name:
            col_found = col
            break
    
    if col_found is None:
        raise ValueError(f"Column '{location_name}' not found in Excel file")
    
    # Extract data - skip first 2 rows which are units and type info
    values = df[col_found].values[2:]
    
    # Read dates from raw file - data starts at row 8 (0-indexed row 7)
    df_raw = pd.read_excel(excel_file, sheet_name=0, header=None, skiprows=7)
    dates = pd.to_datetime(df_raw.iloc[:, 1], errors='coerce')
    
    # Ensure arrays match in length
    min_len = min(len(dates), len(values))
    dates = dates.iloc[:min_len]
    values = values[:min_len]
    
    # Create DataFrame
    result = pd.DataFrame({
        'date': dates.values,
        'value': values
    })
    
    # Add year and month
    result['year'] = result['date'].dt.year
    result['month'] = result['date'].dt.month
    
    # Convert value to numeric, coercing errors to NaN
    result['value'] = pd.to_numeric(result['value'], errors='coerce')
    
    # Remove NaNs
    result = result.dropna(subset=['date', 'value'])
    
    # For VPD only, filter to Oct-1971 through Sept-2018 (WY1972-2018)
    if variable_type == 'vpd':
        mask = (
            ((result['year'] == 1971) & (result['month'] >= 10)) |
            ((result['year'] > 1971) & (result['year'] < 2018)) |
            ((result['year'] == 2018) & (result['month'] <= 9))
        )
        result = result[mask]
    
    return result[['year', 'month', 'value']]


def read_output_data(output_file, variable_type):
    """
    Read output data from basin averages processing.
    
    Parameters:
    -----------
    output_file : Path
        Path to output CSV file
    variable_type : str
        'precip', 'temp', or 'vpd'
        
    Returns:
    --------
    pd.DataFrame with columns: year, month, value
    """
    df = pd.read_csv(output_file)
    
    value_col_map = {
        'precip': 'precip_inches',
        'temp': 'tavg_f',
        'vpd': 'vpd_kpa'
    }
    
    value_col = value_col_map[variable_type]
    
    result = df[['year', 'month', value_col]].rename(columns={value_col: 'value'})
    result['value'] = pd.to_numeric(result['value'], errors='coerce')
    result = result.dropna(subset=['value'])
    
    # For VPD only, filter to Oct-1971 through Sept-2018 (WY1972-2018)
    if variable_type == 'vpd':
        mask = (
            ((result['year'] == 1971) & (result['month'] >= 10)) |
            ((result['year'] > 1971) & (result['year'] < 2018)) |
            ((result['year'] == 2018) & (result['month'] <= 9))
        )
        result = result[mask]
    
    return result


def calculate_validation_statistics(df, variable_type):
    """
    Calculate average annual and average monthly statistics.
    
    Parameters:
    -----------
    df : pd.DataFrame
        DataFrame with columns: year, month, value
    variable_type : str
        'precip', 'temp', or 'vpd'
        
    Returns:
    --------
    dict with keys: 'annual_avg', 'monthly_avg' (dict by month)
    """
    if variable_type == 'precip':
        annual_totals = df.groupby('year')['value'].sum()
        annual_avg = annual_totals.mean()
    else:
        annual_means = df.groupby('year')['value'].mean()
        annual_avg = annual_means.mean()
    
    monthly_avg = df.groupby('month')['value'].mean().to_dict()
    
    return {
        'annual_avg': annual_avg,
        'monthly_avg': monthly_avg
    }


def compare_statistics(ref_stats, output_stats):
    """
    Compare reference and output statistics.
    """
    annual_diff = output_stats['annual_avg'] - ref_stats['annual_avg']
    annual_pct_diff = (annual_diff / ref_stats['annual_avg']) * 100 if ref_stats['annual_avg'] != 0 else np.nan
    
    monthly_diffs = {}
    monthly_pct_diffs = {}
    
    for month in range(1, 13):
        ref_val = ref_stats['monthly_avg'].get(month, np.nan)
        out_val = output_stats['monthly_avg'].get(month, np.nan)
        
        if not np.isnan(ref_val) and not np.isnan(out_val):
            diff = out_val - ref_val
            pct_diff = (diff / ref_val) * 100 if ref_val != 0 else np.nan
            monthly_diffs[month] = diff
            monthly_pct_diffs[month] = pct_diff
        else:
            monthly_diffs[month] = np.nan
            monthly_pct_diffs[month] = np.nan
    
    return {
        'annual_diff': annual_diff,
        'annual_pct_diff': annual_pct_diff,
        'monthly_diffs': monthly_diffs,
        'monthly_pct_diffs': monthly_pct_diffs
    }


def validate_location(location_shorthand, data_folder, excel_file, name_mapping):
    """
    Validate all three variables (precip, temp, VPD) for a single location.
    
    Returns:
    --------
    dict with validation results keyed by variable type
    """
    results = {}
    
    base_shorthand = location_shorthand.replace('_UHH', '')
    if base_shorthand in name_mapping:
        ppt_name = f"PPT_{name_mapping[base_shorthand]}_UHH"
    else:
        ppt_name = f"PPT_{base_shorthand}_UHH"
    temp_name = f"T{base_shorthand}_UHH"
    vpd_name = f"VPD{base_shorthand}_UHH"
    
    variables = [
        (ppt_name, ppt_name, 'precip', 'inches'),
        (temp_name, temp_name, 'temp', '°F'),
        (vpd_name, vpd_name, 'vpd', 'kPa')
    ]
    
    for output_name, ref_name, var_type, units in variables:
        output_file = data_folder / f"{output_name}.csv"
        
        if not output_file.exists():
            results[var_type] = {'error': f"Output file not found: {output_file}"}
            continue
        
        try:
            ref_data = read_reference_data(excel_file, ref_name, var_type)
            output_data = read_output_data(output_file, var_type)
            
            ref_stats = calculate_validation_statistics(ref_data, var_type)
            output_stats = calculate_validation_statistics(output_data, var_type)
            
            comparison = compare_statistics(ref_stats, output_stats)
            
            results[var_type] = {
                'ref_annual_avg': ref_stats['annual_avg'],
                'output_annual_avg': output_stats['annual_avg'],
                'annual_diff': comparison['annual_diff'],
                'annual_pct_diff': comparison['annual_pct_diff'],
                'ref_monthly_avg': ref_stats['monthly_avg'],
                'output_monthly_avg': output_stats['monthly_avg'],
                'monthly_diffs': comparison['monthly_diffs'],
                'monthly_pct_diffs': comparison['monthly_pct_diffs'],
                'units': units
            }
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"
            results[var_type] = {'error': error_msg}
    
    return results


def create_monthly_boxplots(all_monthly_data, output_folder, scenario):
    """
    Create monthly boxplots for all three variables across locations.
    """
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    var_configs = {
        'precip': {'title': 'Precipitation', 'ylabel': 'Precipitation (inches)'},
        'temp': {'title': 'Temperature', 'ylabel': 'Temperature (°F)'},
        'vpd': {'title': 'Vapor Pressure Deficit', 'ylabel': 'VPD (kPa)'}
    }
    
    for var_type, config in var_configs.items():
        if not all_monthly_data[var_type]:
            continue
        
        df = pd.DataFrame(all_monthly_data[var_type])
        
        ref_data = [df[df['month'] == m]['reference'].values for m in range(1, 13)]
        out_data = [df[df['month'] == m]['output'].values for m in range(1, 13)]
        
        fig, ax = plt.subplots(figsize=(6.5, 4))
        fig.set_size_inches(6.5, 4)
        
        positions_ref = [i - 0.2 for i in range(1, 13)]
        positions_out = [i + 0.2 for i in range(1, 13)]
        
        bp_ref = ax.boxplot(ref_data, positions=positions_ref, widths=0.35,
                           patch_artist=True, labels=[''] * 12)
        bp_out = ax.boxplot(out_data, positions=positions_out, widths=0.35,
                           patch_artist=True, labels=[''] * 12)
        
        for patch in bp_ref['boxes']:
            patch.set_facecolor('lightblue')
            patch.set_alpha(0.7)
        for patch in bp_out['boxes']:
            patch.set_facecolor('lightcoral')
            patch.set_alpha(0.7)
        
        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(month_names, fontsize=8)
        ax.set_xlabel('Month', fontsize=9)
        ax.set_ylabel(config['ylabel'], fontsize=9)
        ax.set_title(f'Monthly {config["title"]} Comparison Across All Locations\n' +
                    f'CalSim (Blue) vs {scenario} (Red)', fontsize=10, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')
        
        legend_elements = [Patch(facecolor='lightblue', alpha=0.7, label='CalSim'),
                          Patch(facecolor='lightcoral', alpha=0.7, label=scenario)]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
        
        plt.tight_layout()
        
        output_file = output_folder / f"monthly_boxplot_{var_type}.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()


def create_annual_comparison_plots(all_results, output_folder, locations, scenario):
    """
    Create bar plots comparing annual averages across locations for each variable.
    """
    var_configs = {
        'precip': {'title': 'Precipitation', 'ylabel': 'Annual Average (inches)'},
        'temp': {'title': 'Temperature', 'ylabel': 'Annual Average (°F)'},
        'vpd': {'title': 'Vapor Pressure Deficit', 'ylabel': 'Annual Average (kPa)'}
    }
    
    for var_type, config in var_configs.items():
        location_names = []
        ref_values = []
        out_values = []
        
        for location in locations:
            if location in all_results and 'error' not in all_results[location].get(var_type, {'error': ''}):
                location_names.append(location.replace('_UHH', ''))
                ref_values.append(all_results[location][var_type]['ref_annual_avg'])
                out_values.append(all_results[location][var_type]['output_annual_avg'])
        
        if not location_names:
            continue
        
        fig, ax = plt.subplots(figsize=(6.5, 4))
        fig.set_size_inches(6.5, 4)
        
        x = np.arange(len(location_names))
        width = 0.35
        
        ax.bar(x - width/2, ref_values, width, label='CalSim',
               color='lightblue', alpha=0.8, edgecolor='black', linewidth=0.5)
        ax.bar(x + width/2, out_values, width, label=scenario,
               color='lightcoral', alpha=0.8, edgecolor='black', linewidth=0.5)
        
        ax.set_xlabel('Location', fontsize=9)
        ax.set_ylabel(config['ylabel'], fontsize=9)
        ax.set_title(f'Annual Average {config["title"]} by Location\n' +
                    f'CalSim vs {scenario}', fontsize=10, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels(location_names, fontsize=8, rotation=0)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        output_file = output_folder / f"annual_comparison_{var_type}.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        plt.close()


def print_validation_report(location, results):
    """
    Print validation report for a location.
    """
    print(f"\n{'='*80}")
    print(f"VALIDATION REPORT: {location}")
    print(f"{'='*80}")
    
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    for var_type in ['precip', 'temp', 'vpd']:
        var_name = {'precip': 'PRECIPITATION', 'temp': 'TEMPERATURE', 'vpd': 'VPD'}[var_type]
        
        print(f"\n{var_name}:")
        print("-" * 80)
        
        if 'error' in results.get(var_type, {'error': ''}):
            print(f"  ERROR: {results[var_type]['error']}")
            continue
        
        res = results[var_type]
        units = res['units']
        
        print(f"\n  Annual Average:")
        print(f"    CalSim:        {res['ref_annual_avg']:10.4f} {units}")
        print(f"    Output:        {res['output_annual_avg']:10.4f} {units}")
        print(f"    Difference:    {res['annual_diff']:10.4f} {units} ({res['annual_pct_diff']:+.2f}%)")
        
        print(f"\n  Monthly Averages:")
        print(f"    Month    CalSim    Output       Diff        % Diff")
        print(f"    {'─'*60}")
        for month in range(1, 13):
            ref_val = res['ref_monthly_avg'].get(month, np.nan)
            out_val = res['output_monthly_avg'].get(month, np.nan)
            diff = res['monthly_diffs'].get(month, np.nan)
            pct_diff = res['monthly_pct_diffs'].get(month, np.nan)
            
            print(f"    {month_names[month-1]:3s}   {ref_val:10.4f}  {out_val:10.4f}  {diff:+10.4f}  {pct_diff:+8.2f}%")


def run_validate_outputs(scenario):
    """
    Run output validation against calsim_climate_sv.xlsx reference data.
    
    Parameters:
    -----------
    scenario : str
        Scenario number (e.g., '1')
    """
    script_dir = Path(__file__).parent.resolve()
    gen_dir = get_module_generated_dir("mod_forcing/climate")
    excel_file = script_dir / "reference" / "calsim_climate_sv.xlsx"
    if not excel_file.exists():
        excel_file = script_dir / "input" / "calsim_climate_sv.xlsx"
    data_folder = gen_dir / "output" / "_2_uhh_basin_averages" / "product_a"
    validation_folder = gen_dir / "output" / "_3_validation"
    validation_folder.mkdir(parents=True, exist_ok=True)
    
    if not excel_file.exists():
        raise FileNotFoundError(f"CalSim file not found: {excel_file}")
    if not data_folder.exists():
        raise FileNotFoundError(f"Data folder not found: {data_folder}")
    
    name_mapping = {
        'FO': 'FOLS',
        'OR': 'OROV',
        'SH': 'SHAS',
        'YU': 'YUBA'
    }
    
    locations = ['FO_UHH', 'ME_UHH', 'OR_UHH', 'SH_UHH', 'SJ_UHH',
                 'ST_UHH', 'TR_UHH', 'TU_UHH', 'WH_UHH', 'YU_UHH']
    
    print("="*80)
    print("UHH BASIN AVERAGES VALIDATION")
    print("="*80)
    print(f"Scenario: Product_A / {scenario}")
    print(f"CalSim file: {excel_file}")
    print(f"Data folder: {data_folder}")
    print(f"Validation output folder: {validation_folder}")
    
    all_results = {}
    all_monthly_data = {'precip': [], 'temp': [], 'vpd': []}
    
    for location in locations:
        try:
            results = validate_location(location, data_folder, excel_file, name_mapping)
            all_results[location] = results
            print_validation_report(location, results)
            
            for var_type in ['precip', 'temp', 'vpd']:
                if 'error' not in results.get(var_type, {'error': ''}):
                    res = results[var_type]
                    for month in range(1, 13):
                        if month in res['ref_monthly_avg'] and month in res['output_monthly_avg']:
                            all_monthly_data[var_type].append({
                                'location': location,
                                'month': month,
                                'reference': res['ref_monthly_avg'][month],
                                'output': res['output_monthly_avg'][month]
                            })
        except Exception as e:
            print(f"\nERROR validating {location}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"\nTotal locations validated: {len(locations)}")
    print(f"Successfully validated: {len([r for r in all_results.values() if not any('error' in v for v in r.values())])}")
    
    # Save detailed results to CSV
    summary_file = validation_folder / "validation_summary.csv"
    summary_rows = []
    
    for location, results in all_results.items():
        for var_type in ['precip', 'temp', 'vpd']:
            if 'error' not in results.get(var_type, {'error': ''}):
                res = results[var_type]
                summary_rows.append({
                    'location': location,
                    'variable': var_type,
                    'ref_annual_avg': res['ref_annual_avg'],
                    'output_annual_avg': res['output_annual_avg'],
                    'annual_diff': res['annual_diff'],
                    'annual_pct_diff': res['annual_pct_diff'],
                    'units': res['units']
                })
    
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_csv(summary_file, index=False)
        print(f"\nDetailed summary saved to: {summary_file}")
    
    # Generate plots
    print(f"\nGenerating monthly boxplots...")
    create_monthly_boxplots(all_monthly_data, validation_folder, scenario)
    print(f"Boxplots saved to: {validation_folder}")
    
    print(f"\nGenerating annual comparison plots...")
    create_annual_comparison_plots(all_results, validation_folder, locations, scenario)
    print(f"Annual comparison plots saved to: {validation_folder}")


def write_product_a_validation(summaries, output_folder, start_wy=1922, end_wy=2018):
    """
    Create combined long-format validation CSVs from processed Product A summaries.
    Output: _uhh_precip_productA_{start_wy}_{end_wy}.csv,
            _uhh_temperature_productA_{start_wy}_{end_wy}.csv,
            _uhh_vpd_productA_{start_wy}_{end_wy}.csv
    Format: Part B, Part C, Year, Month, Value
    """
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)
    output_path = Path(output_folder)

    var_configs = [
        {'col': 'precip_inches', 'part_c': 'PRECIP',      'name_key': 'ppt_location_name',  'file_stem': f'_uhh_precip_productA_{start_wy}_{end_wy}'},
        {'col': 'tavg_f',        'part_c': 'Temperature',  'name_key': 'temp_location_name', 'file_stem': f'_uhh_temperature_productA_{start_wy}_{end_wy}'},
        {'col': 'vpd_kpa',       'part_c': 'VPD',          'name_key': 'vpd_location_name',  'file_stem': f'_uhh_vpd_productA_{start_wy}_{end_wy}'},
    ]

    print(f"\nCreating Product A validation CSVs (WY {start_wy}-{end_wy})...")
    for vc in var_configs:
        col = vc['col']
        all_rows = []
        for s in summaries:
            md = s.get('_monthly_data')
            if md is None or col not in md.columns or 'date' not in md.columns:
                continue
            loc_name = s[vc['name_key']]
            if loc_name == 'N/A':
                continue
            mask = (md['date'] >= start_date) & (md['date'] <= end_date)
            df_f = md.loc[mask]
            for _, row in df_f.iterrows():
                all_rows.append({
                    'Part B': loc_name,
                    'Part C': vc['part_c'],
                    'Year': int(row['year']),
                    'Month': int(row['month']),
                    'Value': round(row[col], 6),
                })

        if not all_rows:
            print(f"  No data for {vc['part_c']} validation CSV.")
            continue

        output_df = pd.DataFrame(all_rows)
        output_file = output_path / f"{vc['file_stem']}.csv"
        output_df.to_csv(output_file, index=False)
        n_locations = output_df['Part B'].nunique()
        print(f"  {output_file.name} ({n_locations} locations, {len(output_df)} rows)")


def write_product_b_chunks(summaries: list, output_folder):
    """
    Compile all locations into 10 long-format chunk CSVs (100 WYs each).
    Skips first 9 months (Jan-Sep synthetic year 1) for WY alignment.
    Template dates: Oct 1921 – Sep 2021 (WY1922–2021).
    Writes three file sets: _uhh_precip_productB_n01..n10.csv,
                            _uhh_temperature_productB_n01..n10.csv,
                            _uhh_vpd_productB_n01..n10.csv
    Format: Part B, Part C, Year, Month, Value
    """
    skip_months     = 9     # Jan-Sep of synthetic year 1
    months_per_chunk = 1200 # 100 WYs × 12 months
    total_chunks    = 10
    total_needed    = skip_months + months_per_chunk * total_chunks

    date_template = pd.date_range('1921-10-31', periods=months_per_chunk, freq='ME')
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    var_configs = [
        {'col': 'precip_inches', 'part_c': 'PRECIP',      'name_key': 'ppt_location_name',  'file_stem': '_uhh_precip_productB'},
        {'col': 'tavg_f',        'part_c': 'TEMPERATURE',  'name_key': 'temp_location_name', 'file_stem': '_uhh_temperature_productB'},
        {'col': 'vpd_kpa',       'part_c': 'VPD',          'name_key': 'vpd_location_name',  'file_stem': '_uhh_vpd_productB'},
    ]

    print(f"\nWriting Product B chunk files ({total_chunks} chunks × {months_per_chunk} months)...")

    for vc in var_configs:
        col = vc['col']
        loc_data = {}
        for s in summaries:
            md = s.get('_monthly_data')
            if md is None or col not in md.columns:
                continue
            loc_name = s[vc['name_key']]
            if loc_name == 'N/A':
                continue
            vals = md[col].values
            if len(vals) < total_needed:
                print(f"  Warning: {loc_name} only {len(vals)} months (need {total_needed}), skipping")
                continue
            loc_data[loc_name] = vals

        if not loc_data:
            print(f"  Skipping {vc['file_stem']} — no valid locations")
            continue

        for i in range(total_chunks):
            rows = []
            for loc_name, vals in loc_data.items():
                chunk_vals = vals[
                    skip_months + i * months_per_chunk :
                    skip_months + (i + 1) * months_per_chunk
                ]
                for j, val in enumerate(chunk_vals):
                    rows.append({
                        'Part B': loc_name,
                        'Part C': vc['part_c'],
                        'Year':   int(date_template[j].year),
                        'Month':  int(date_template[j].month),
                        'Value':  val,
                    })
            chunk_df = pd.DataFrame(rows, columns=['Part B', 'Part C', 'Year', 'Month', 'Value'])
            out_file = output_path / f"{vc['file_stem']}_n{i+1:02d}.csv"
            chunk_df.to_csv(out_file, index=False)
            print(f"  Chunk {i+1:02d}/10: {out_file.name} ({len(loc_data)} locations)")

        print(f"  {vc['file_stem']}: {total_chunks} chunks written")

    print(f"Product B chunks: {output_folder}")


def parse_arguments():
    """
    Parse command-line arguments.
    
    Returns:
    --------
    argparse.Namespace : Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Extract monthly basin-averaged precip and temp for UHH locations'
    )
    parser.add_argument(
        '--source',
        type=str,
        required=False,
        choices=['Product_A', 'Product_B', 'Historical'],
        help='Weather data source: Product_A, Product_B, or Historical'
    )
    parser.add_argument(
        '--scenario',
        type=str,
        required=False,
        help='Scenario number (required for Product_A/Product_B, e.g., 1, 2, 3, ...)'
    )
    parser.add_argument(
        '--validate-outputs',
        action='store_true',
        dest='validate_outputs',
        help='Validate Product_A outputs against reference data in calsim_climate_sv.xlsx'
    )
    parser.add_argument(
        '--locations',
        type=str,
        default='reference/uhh_locations.csv',
        help='CSV file with UHH locations (default: reference/uhh_locations.csv)'
    )
    parser.add_argument(
        '--start_date',
        type=str,
        default='1920-10-01',
        help='Start date for analysis (default: 1920-10-01)'
    )
    parser.add_argument(
        '--end_date',
        type=str,
        default='2021-09-30',
        help='End date for analysis (default: 2021-09-30)'
    )
    
    args = parser.parse_args()
    
    # --source is required unless --validate-outputs is used
    if not args.validate_outputs and not args.source:
        parser.error("--source is required (or use --validate-outputs)")
    
    # Validate scenario requirement
    if args.source in ['Product_A', 'Product_B']:
        if not args.scenario:
            parser.error(f"--scenario is required when using source '{args.source}'")
    
    return args


def main():
    """
    Main function to extract monthly basin averages for UHH locations.
    """
    # Parse command-line arguments
    args = parse_arguments()
    
    # Handle --validate-outputs mode
    if args.validate_outputs:
        scenario = args.scenario if args.scenario else '1'
        run_validate_outputs(scenario)
        return
    
    # Set up paths
    script_dir = Path(__file__).parent.resolve()
    base_dir = get_base_dir()
    gen_dir = get_module_generated_dir("mod_forcing/climate")
    
    # Input files
    uhh_locations_file = script_dir / args.locations
    excel_file = script_dir / "reference" / "calsim_climate_sv.xlsx"
    if not excel_file.exists():
        excel_file = script_dir / "input" / "calsim_climate_sv.xlsx"
    repo_root = Path(__file__).resolve().parents[2]
    grid_info_folder = repo_root / "mod_forcing" / "vic" / "reference" / "GridInfo"
    
    # Build data path based on source type
    if args.source == "Historical":
        data_folder = base_dir / "Historical_Climate"
        output_folder = gen_dir / "output" / "_2_uhh_basin_averages" / "historical"
        script_output_folder = output_folder
    else:
        # Product_A or Product_B with scenario
        data_folder = base_dir / "WGEN" / args.source / args.scenario
        if args.source == 'Product_A':
            output_folder = gen_dir / "output" / "_2_uhh_basin_averages" / "product_a"
            script_output_folder = output_folder
        else:
            output_folder = gen_dir / "output" / "_product_b_final"
            script_output_folder = gen_dir / "output" / "_2_uhh_basin_averages" / "product_b"
    
    output_folder.mkdir(parents=True, exist_ok=True)
    script_output_folder.mkdir(parents=True, exist_ok=True)
    
    # Convert to string for file operations
    data_folder_str = str(data_folder)
    
    print("="*80)
    print("EXTRACTING MONTHLY BASIN AVERAGES FOR UHH LOCATIONS")
    print("="*80)
    print(f"Weather source: {args.source}")
    if args.scenario:
        print(f"Scenario: {args.scenario}")
    print(f"Data folder: {data_folder_str}")
    print(f"Grid info folder: {grid_info_folder}")
    print(f"Output folder: {output_folder}")
    
    # Check if data folder exists
    if not os.path.exists(data_folder_str):
        raise FileNotFoundError(f"Data folder not found: {data_folder_str}")
    
    # Check if grid info folder exists
    if not grid_info_folder.exists():
        raise FileNotFoundError(f"Grid info folder not found: {grid_info_folder}")
    
    # Create date index for full analysis period
    date_index = pd.date_range(start=args.start_date, end=args.end_date, freq='D')
    print(f"Analysis period: {args.start_date} to {args.end_date} ({len(date_index)} days)")
    
    # Read UHH locations
    print(f"\nReading UHH locations from: {uhh_locations_file}")
    locations_df = read_uhh_locations(uhh_locations_file)
    print(f"Found {len(locations_df)} watershed locations to process")
    
    # Process each location (each will create both PPT and T files)
    summaries = []
    for idx, row in locations_df.iterrows():
        try:
            summary = process_location(
                shorthand=row['location'],
                grid_info_file=row['grid_info_file'],
                grid_info_folder=grid_info_folder,
                data_folder=data_folder_str,
                output_folder=output_folder,
                date_index=date_index,
                args=args,
                excel_file=excel_file
            )
            summaries.append(summary)
        except Exception as e:
            print(f"  ERROR processing {row['location']}: {str(e)}")
            continue
    
    # Save summary file
    if summaries:
        # Compile Product B chunks across all locations before writing summary
        if args.source == 'Product_B':
            write_product_b_chunks(summaries, output_folder)
        elif args.source == 'Product_A':
            validation_dir = gen_dir / "output" / "_product_a_validation"
            validation_dir.mkdir(parents=True, exist_ok=True)
            write_product_a_validation(summaries, validation_dir)

        # Strip internal keys (prefixed _) before writing CSV
        summary_rows = [{k: v for k, v in s.items() if not k.startswith('_')} for s in summaries]
        summary_df = pd.DataFrame(summary_rows)
        summary_file = script_output_folder / "_summary.csv"
        summary_df.to_csv(summary_file, index=False)
        print(f"\n{'='*80}")
        print(f"Processing complete!")
        print(f"Successfully processed {len(summaries)} out of {len(locations_df)} locations")
        print(f"Summary saved to: {summary_file}")
        print(f"{'='*80}")
        
        # Print summary statistics
        print(f"\nSummary Statistics:")
        print(f"  Average number of grid cells per basin: {summary_df['num_grid_cells'].mean():.1f}")
        print(f"  Average monthly precip (across all basins): {summary_df['mean_monthly_precip_inches'].mean():.2f} inches")
        print(f"  Average monthly tavg (across all basins): {summary_df['mean_monthly_tavg_f'].mean():.2f} °F")
    else:
        print("\nNo locations were successfully processed.")


if __name__ == "__main__":
    main()
