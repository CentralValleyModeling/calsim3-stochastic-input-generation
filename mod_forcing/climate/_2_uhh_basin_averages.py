"""
Extract Monthly Basin-Averaged Climate for UHH Locations
========================================================
Computes weighted-average monthly precipitation, temperature, and VPD for
UHH (Upper Headwater Hydrology) locations specified in reference/uhh_locations.csv.
Grid cell weights are read from reference/GridInfo/ files.
VPD is derived via quantile mapping from temperature using CalSim historical VPD.

Historical_Unsplit, Product A, LTO: one CSV per variable per location; the first two also
write delivery CSVs. Product B: 10 long-format chunk CSVs per variable (100 WY each, Oct 1921 -
Sep 2021). The weather is read through utils.wgen and labelled by utils.wgen_calendar.

Inputs
------
- reference/uhh_locations.csv
- reference/GridInfo/<location>_GridInfo.txt
- BASE/WGEN/<Historical_Unsplit | Product_A/1 | Product_B/1>, or BASE/Historical_Climate_LTO
- reference/calsim_climate_sv.xlsx  (historical VPD target for quantile mapping)

Outputs
-------
- output/_2_uhh_basin_averages/<Historical_Unsplit|Product_A|LTO>/PPT_<name>_UHH.csv,
  T<name>_UHH.csv, VPD<name>_UHH.csv
- output/_historical_unsplit_validation/_uhh_{precip,temperature,vpd}_historicalUnsplit_1922_2018.csv
- output/_product_a_validation/_uhh_{precip,temperature,vpd}_productA_1922_2018.csv
- output/_product_b_final/_uhh_precip_productB_n01.csv ... n10.csv  (same pattern for temp/vpd)

Usage
-----
    python mod_forcing/climate/_2_uhh_basin_averages.py --product historical
    python mod_forcing/climate/_2_uhh_basin_averages.py --product A
    python mod_forcing/climate/_2_uhh_basin_averages.py --product B
    python mod_forcing/climate/_2_uhh_basin_averages.py --product LTO

    # Validate Product A outputs against historical reference
    python mod_forcing/climate/_2_uhh_basin_averages.py --validate-outputs
"""

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
from utils import dss_io
from utils.csv_io import write_delivery_csv
from utils.paths import DELIVERY, WEATHER_SETS, delivery_dir, get_base_dir, get_module_generated_dir
from utils.wgen import SETS, met_path, read_met, set_name
from utils.wgen_calendar import (CHUNK_MONTHS, N_CHUNKS, label as calendar_label, month_totals,
                                 water_year, write_chunk_csvs)
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


def calculate_basin_monthly_averages(grid_info_df, product, date_index=None):
    """
    Basin-averaged monthly precipitation (inches) and temperature (degF), weighted by the
    grid info's weight1 column, from the daily weather of each cell (utils.wgen).

    A single series (Historical_Unsplit, Product A, LTO) is aligned to ``date_index`` first,
    and its days outside the files' span are left out, so the series ends with the weather
    (December 2018 for Historical_Unsplit and Product A). Product B stays on its stamp days
    and months (utils.wgen_calendar); every cell must list the same days.

    Returns:
    --------
    pd.DataFrame with year, month (stamp months for Product B), precip_inches, tavg_f, and
    date (single series only)
    """
    weighted_precip_sum = None
    weighted_tavg_sum = None
    weight_total = 0.0
    days = None

    for _, row in grid_info_df.iterrows():
        weight = row['weight1']
        path = met_path(product, row['lat'], row['lon'])
        if not path.exists():
            raise FileNotFoundError(f"no weather file for grid cell ({row['lat']}, {row['lon']}): {path}")
        w = read_met(product, path)
        tavg = (w['tmax'] + w['tmin']) / 2.0
        if product == "B":
            if days is None:
                days = w[['Year', 'Month', 'Day']]
            elif not np.array_equal(days.to_numpy(), w[['Year', 'Month', 'Day']].to_numpy()):
                raise ValueError(f"{path}: its days differ from the basin's first cell")
            precip_series = w['precip'].reset_index(drop=True)
            tavg_series = tavg.reset_index(drop=True)
        else:
            dates = pd.to_datetime(w[['Year', 'Month', 'Day']].rename(columns=str.lower))
            precip_series = pd.Series(w['precip'].to_numpy(), index=dates).reindex(date_index)
            tavg_series = pd.Series(tavg.to_numpy(), index=dates).reindex(date_index)

        precip_contrib = precip_series * weight
        tavg_contrib = tavg_series * weight
        weighted_precip_sum = precip_contrib if weighted_precip_sum is None else (weighted_precip_sum + precip_contrib)
        weighted_tavg_sum = tavg_contrib if weighted_tavg_sum is None else (weighted_tavg_sum + tavg_contrib)
        weight_total += weight

    if weighted_precip_sum is None:
        raise ValueError("No grid cells in the grid info")

    if product == "B":
        daily = days.reset_index(drop=True).assign(precip=weighted_precip_sum.to_numpy() / weight_total,
                                                   tavg=weighted_tavg_sum.to_numpy() / weight_total)
    else:
        daily = pd.DataFrame({'Year': date_index.year, 'Month': date_index.month, 'Day': date_index.day,
                              'precip': weighted_precip_sum.to_numpy() / weight_total,
                              'tavg': weighted_tavg_sum.to_numpy() / weight_total}
                             ).dropna(subset=['precip'])   # a month sum would count them as 0
    m = month_totals(daily, {'precip': 'sum', 'tavg': 'mean'})
    monthly_df = pd.DataFrame({
        'year':          m['Year'],
        'month':         m['Month'],
        'precip_inches': m['precip'].to_numpy() / 25.4,
        'tavg_f':        (m['tavg'].to_numpy() * 9 / 5) + 32,
    })
    if product != "B":
        monthly_df['date'] = pd.to_datetime(dict(year=monthly_df['year'], month=monthly_df['month'], day=1))
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
        The weather set: 'historical', 'A', 'B' or 'LTO'
        
    Returns:
    --------
    pd.DataFrame with columns: year, month, vpd_kpa
    """
    # Prepare temperature data as basis simulation (full time series)
    temp_basis_sim = temp_monthly[['year', 'month', 'tavg_f']].copy()
    temp_basis_sim = temp_basis_sim.rename(columns={'tavg_f': 'value'})

    # Remove any NaN values from target VPD
    target_vpd = target_vpd.dropna(subset=['value'])

    if source_type == 'B':
        # Product B has stamp year labels (1-1008) that don't overlap with
        # historical VPD years (1921-2018), so year-based filtering/merging won't work.
        # qmap_single builds independent per-month (1-12) distributions for basis
        # and target, so only the month labels need to be correct -- years are
        # irrelevant.  Product B months are the stamp months (utils.wgen_calendar),
        # so we use them directly (no label overwriting).
        # Use up to one chunk's length (100 WY), truncated to whichever series is shorter.
        n_calib = min(len(temp_basis_sim), len(target_vpd), CHUNK_MONTHS)
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
    
    if source_type == 'B':
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


def process_location(shorthand, grid_info_file, grid_info_folder, product, output_folder, date_index, excel_file):
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
    product : str
        The weather set ('historical', 'A', 'B', 'LTO')
    output_folder : Path
        Path to output folder
    date_index : pd.DatetimeIndex
        Full date range for the analysis period
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
        grid_info_df, product,
        date_index=date_index,
    )
    
    # Apply VPD quantile mapping using temperature as basis
    print("  Applying VPD quantile mapping...")
    try:
        target_vpd = read_target_vpd_data(excel_file, base_shorthand)
        print(f"    Target VPD data: {len(target_vpd)} months")
        
        vpd_data = apply_vpd_quantile_mapping(
            temp_monthly=monthly_data[['year', 'month', 'tavg_f']],
            target_vpd=target_vpd,
            source_type=product
        )
        # Merge VPD into monthly_data
        monthly_data = monthly_data.merge(vpd_data, on=['year', 'month'], how='left')
        vpd_enabled = True
        print("  VPD quantile mapping completed")
    except Exception as e:
        import traceback
        print(f"  Warning: VPD quantile mapping failed: {e}")
        print("  Error details:")
        traceback.print_exc()
        print("  Proceeding without VPD output")
        vpd_enabled = False
    
    # Construct VPD location name
    vpd_location_name = f"VPD{base_shorthand}_UHH"

    if product == 'B':
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
        (temp_name, temp_name, 'temp', 'degF'),
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
        'temp': {'title': 'Temperature', 'ylabel': 'Temperature (degF)'},
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
        'temp': {'title': 'Temperature', 'ylabel': 'Annual Average (degF)'},
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
        
        print("\n  Annual Average:")
        print(f"    CalSim:        {res['ref_annual_avg']:10.4f} {units}")
        print(f"    Output:        {res['output_annual_avg']:10.4f} {units}")
        print(f"    Difference:    {res['annual_diff']:10.4f} {units} ({res['annual_pct_diff']:+.2f}%)")
        
        print("\n  Monthly Averages:")
        print("    Month    CalSim    Output       Diff        % Diff")
        print(f"    {'-'*60}")
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
    data_folder = gen_dir / "output" / "_2_uhh_basin_averages" / set_name("A")
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
    print(f"Weather set: {scenario}")
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
    print("\nGenerating monthly boxplots...")
    create_monthly_boxplots(all_monthly_data, validation_folder, scenario)
    print(f"Boxplots saved to: {validation_folder}")
    
    print("\nGenerating annual comparison plots...")
    create_annual_comparison_plots(all_results, validation_folder, locations, scenario)
    print(f"Annual comparison plots saved to: {validation_folder}")


#: Per variable: the monthly column, its file stem, the location-name key of the summary and the
#: Part C of the delivery CSVs and of Product B's chunks.
VARIABLES = [
    {'col': 'precip_inches', 'stem': '_uhh_precip',      'name_key': 'ppt_location_name',
     'part_c': 'PRECIP',      'part_c_b': 'PRECIP'},
    {'col': 'tavg_f',        'stem': '_uhh_temperature', 'name_key': 'temp_location_name',
     'part_c': 'Temperature', 'part_c_b': 'TEMPERATURE'},
    {'col': 'vpd_kpa',       'stem': '_uhh_vpd',         'name_key': 'vpd_location_name',
     'part_c': 'VPD',         'part_c_b': 'VPD'},
]


def _sv_rows(summaries, var, part_c):
    """The monthly series of one variable across locations in SV format (Part B = location),
    by file month; locations without the variable are skipped."""
    frames = []
    for s in summaries:
        md = s.get('_monthly_data')
        if md is None or var['col'] not in md.columns or s[var['name_key']] == 'N/A':
            continue
        frames.append(pd.DataFrame({'Part B': s[var['name_key']], 'Part C': part_c,
                                    'Year': md['year'], 'Month': md['month'],
                                    'Value': md[var['col']]}))
    return pd.concat(frames, ignore_index=True) if frames else None


def write_delivery(summaries, output_root, product):
    """The delivery CSVs of a single series over DELIVERY_WY (values rounded to 6 decimals)."""
    print(f"\nWriting the {WEATHER_SETS[product]['name']} delivery CSVs...")
    for var in VARIABLES:
        df = _sv_rows(summaries, var, var['part_c'])
        if df is None:
            print(f"  No data for {var['part_c']} delivery CSV.")
            continue
        df['Value'] = df['Value'].map(lambda v: round(v, 6))
        out = write_delivery_csv(df, delivery_dir(output_root, product), var['stem'], product)
        print(f"  {out.name} ({df['Part B'].nunique()} locations)")


def write_product_b_chunks(summaries: list, output_folder):
    """The 10 long-format chunk CSVs per variable, each labelled WY1922-2021
    (utils.wgen_calendar): _uhh_precip_productB_n01..n10.csv, _uhh_temperature_productB_*,
    _uhh_vpd_productB_*."""
    print("\nWriting Product B chunk files...")
    for var in VARIABLES:
        df = _sv_rows(summaries, var, var['part_c_b'])
        if df is None:
            print(f"  Skipping {var['stem']}_productB - no valid locations")
            continue
        labelled = pd.concat([calendar_label('B', g.drop(columns=['Part B', 'Part C'])).assign(
            **{'Part B': key[0], 'Part C': key[1]}) for key, g in df.groupby(['Part B', 'Part C'], sort=False)],
            ignore_index=True)
        paths = write_chunk_csvs(labelled, output_folder, f"{var['stem']}_productB")
        print(f"  {var['stem']}_productB: {len(paths)} chunks written")
    print(f"Product B chunks: {output_folder}")

###############################################################################
# Historical vs Product B comparison (annual WY precip boxplots)
###############################################################################

# Location groupings for aggregate figures
_SAC_VALLEY_LOCS = ['FO_UHH', 'OR_UHH', 'SH_UHH', 'YU_UHH']  # excludes TR, WH
_SJ_VALLEY_LOCS = ['ME_UHH', 'SJ_UHH', 'ST_UHH', 'TU_UHH']
_ALL_LOCS = _SAC_VALLEY_LOCS + _SJ_VALLEY_LOCS               # excludes TR, WH

# PPT file naming: base shorthand -> full name used in PPT_*_UHH.csv
_PPT_NAME_MAPPING = {'FO': 'FOLS', 'OR': 'OROV', 'SH': 'SHAS', 'YU': 'YUBA'}


def _ppt_filename_stem(shorthand: str) -> str:
    """Return the PPT file stem (without extension) for a given UHH shorthand."""
    base = shorthand.replace('_UHH', '')
    full = _PPT_NAME_MAPPING.get(base, base)
    return f"PPT_{full}_UHH"


def _basin_weight_from_gridinfo(grid_info_folder: Path, grid_info_file: str) -> float:
    """Return total basin area weight (sum of weight1) for a UHH basin."""
    df = parse_grid_info_file(grid_info_folder / grid_info_file)
    return float(df['weight1'].sum())


def _historical_wy_totals_from_dss(ppt_part_b: str, start_wy: int = 1922, end_wy: int = 2021) -> pd.DataFrame:
    """Read monthly historical precip (inches) for a UHH Part B from the default
    CalSim SV DSS (__calsim_sv_default__.dss) and aggregate to WY totals.

    Returns DataFrame with columns: WY, precip_inches.
    """
    dss_file = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
    if not dss_file.exists():
        raise FileNotFoundError(f"Default CalSim SV DSS not found: {dss_file}")

    b_target = ppt_part_b.strip().upper()
    c_target = "PRECIP"

    # Direct open (no junction, catalog_flag=True) matches this function's
    # historical HecDss.Open call.  The bespoke single-pair match, ValueError,
    # and full_idx are kept verbatim -- dss_io.read_monthly_series's notna()
    # gate would change the "paths exist but all-NaN" edge case.
    with dss_io.open_dss(str(dss_file), version=6, catalog_flag=True,
                         use_junction=False) as dss:
        paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        matches = []
        for p in paths:
            parts = p.strip("/").split("/")
            if len(parts) != 6:
                continue
            if parts[1].strip().upper() == b_target and parts[2].strip().upper() == c_target:
                matches.append(p)
        if not matches:
            raise ValueError(f"No DSS paths found for Part B='{ppt_part_b}', Part C='PRECIP'")

        full_idx = pd.date_range("1900-01-31", "2025-12-31", freq="ME")
        master = pd.Series(index=full_idx, dtype=float)
        for path in sorted(matches, key=lambda x: (x.strip("/").split("/")[3], x)):
            ts = dss.read_ts(path, trim_missing=True)
            vals = dss_io.apply_sentinel(ts.values)
            # DSS stores period-end timestamps; shift back one month so index is the data month.
            idx = dss_io.eom_index(ts.pytimes)
            master.update(pd.Series(vals, index=idx))

    s = master.dropna()
    df = pd.DataFrame({
        "year": s.index.year,
        "month": s.index.month,
        "precip_inches": s.values,
    })
    df["WY"] = water_year(df["year"], df["month"])
    df = df[(df["WY"] >= start_wy) & (df["WY"] <= end_wy)]
    counts = df.groupby("WY").size()
    complete_wys = counts[counts == 12].index
    df = df[df["WY"].isin(complete_wys)]
    wy_tot = df.groupby("WY", as_index=False)["precip_inches"].sum().reset_index(drop=True)
    return wy_tot


def _long_format_wy_totals(csv_path: Path) -> dict:
    """Read a long-format SV precip CSV and return WY totals per Part B location.

    Format: Part B, Part C, Year, Month, Value. Used for both Product B chunk
    files and the Product A validation CSV (identical format). Returns
    dict[location_name -> DataFrame(WY, precip_inches)], keeping only complete
    (12-month) water years.
    """
    df = pd.read_csv(csv_path)
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    df = df.dropna(subset=['Value'])
    df['WY'] = water_year(df['Year'], df['Month'])
    out: dict = {}
    for loc_name, sub in df.groupby('Part B'):
        counts = sub.groupby('WY').size()
        complete_wys = counts[counts == 12].index
        sub = sub[sub['WY'].isin(complete_wys)]
        wy_tot = sub.groupby('WY', as_index=False)['Value'].sum()
        wy_tot = wy_tot.rename(columns={'Value': 'precip_inches'})
        out[loc_name] = wy_tot.reset_index(drop=True)
    return out


def _area_weighted_mean(per_loc_wy: dict, weights: dict) -> pd.DataFrame:
    """Compute area-weighted mean WY precip across multiple locations.

    Parameters
    ----------
    per_loc_wy : dict[str, pd.DataFrame]
        Mapping shorthand -> DataFrame with columns WY, precip_inches.
    weights : dict[str, float]
        Mapping shorthand -> basin area weight.

    Returns
    -------
    pd.DataFrame with columns: WY, precip_inches (area-weighted basin mean).
    """
    locs = [s for s in per_loc_wy if not per_loc_wy[s].empty]
    if not locs:
        return pd.DataFrame(columns=['WY', 'precip_inches'])
    merged = None
    for s in locs:
        sub = per_loc_wy[s].rename(columns={'precip_inches': s})
        merged = sub if merged is None else merged.merge(sub, on='WY', how='inner')
    total_w = sum(weights[s] for s in locs)
    weighted = sum(merged[s] * weights[s] for s in locs) / total_w
    return pd.DataFrame({'WY': merged['WY'], 'precip_inches': weighted})


def _plot_hist_vs_productB_box(
    hist_wy: pd.DataFrame,
    block_wy_list: list,
    title: str,
    out_png: Path,
    unit: str = "inches",
    productA_wy: pd.DataFrame = None,
):
    """Create boxplot: historical (+ Product A) + n01..n10 annual WY precip totals.

    When ``productA_wy`` is provided (and non-empty), a Product A box is drawn
    between the historical box and the Product B blocks.

    Styled to match _productB_postproc.plot_summary_boxplots.
    """
    # Match _productB_postproc.plot_summary_boxplots palette exactly
    _DWR_BLUE = "#003D6B"
    _DWR_LIGHT_BLUE = "#B0C4DE"
    _DWR_GRAY = "#5A5A5A"
    _DWR_HIST_FACE = "#F0F0F0"  # pale grey to mirror productB_postproc historical style
    _DWR_HIST_EDGE = _DWR_GRAY
    _DWR_PRODA_FACE = "#F2C57C"  # warm gold: distinct from grey historical and blue Product B
    _DWR_PRODA_EDGE = "#A86A12"

    hist_vals = hist_wy['precip_inches'].dropna().to_numpy(dtype=float)
    block_data = [bw['precip_inches'].dropna().to_numpy(dtype=float) for bw in block_wy_list]

    has_proda = productA_wy is not None and not productA_wy.empty
    proda_vals = (productA_wy['precip_inches'].dropna().to_numpy(dtype=float)
                  if has_proda else None)

    # Position layout: Historical=1, [Product A=2], then the Product B blocks.
    pos_hist = 1
    next_pos = 2
    pos_proda = None
    labels = ['Hist']
    if has_proda:
        pos_proda = next_pos
        labels.append('ProdA')
        next_pos += 1
    block_positions = list(range(next_pos, next_pos + len(block_data)))
    labels += [f'n{i:02d}' for i in range(1, len(block_data) + 1)]

    fig, ax = plt.subplots(figsize=(11, 5))

    # Historical box (pale grey) with grey median line
    ax.boxplot(
        [hist_vals], positions=[pos_hist], widths=0.5, showfliers=True,
        patch_artist=True, showmeans=True,
        boxprops=dict(facecolor=_DWR_HIST_FACE, edgecolor=_DWR_HIST_EDGE, linewidth=1.0),
        medianprops=dict(color=_DWR_GRAY, linewidth=1.8),
        meanprops=dict(marker="D", markerfacecolor=_DWR_BLUE,
                       markeredgecolor=_DWR_BLUE, markersize=5),
        whiskerprops=dict(color=_DWR_HIST_EDGE, linewidth=1.0),
        capprops=dict(color=_DWR_HIST_EDGE, linewidth=1.0),
        flierprops=dict(marker="o", markerfacecolor=_DWR_GRAY,
                        markeredgecolor=_DWR_GRAY, markersize=3, alpha=0.5),
    )

    # Product A box (warm gold) with grey median line
    if has_proda:
        ax.boxplot(
            [proda_vals], positions=[pos_proda], widths=0.5, showfliers=True,
            patch_artist=True, showmeans=True,
            boxprops=dict(facecolor=_DWR_PRODA_FACE, edgecolor=_DWR_PRODA_EDGE, linewidth=1.0),
            medianprops=dict(color=_DWR_GRAY, linewidth=1.8),
            meanprops=dict(marker="D", markerfacecolor=_DWR_PRODA_EDGE,
                           markeredgecolor=_DWR_PRODA_EDGE, markersize=5),
            whiskerprops=dict(color=_DWR_PRODA_EDGE, linewidth=1.0),
            capprops=dict(color=_DWR_PRODA_EDGE, linewidth=1.0),
            flierprops=dict(marker="o", markerfacecolor=_DWR_PRODA_EDGE,
                            markeredgecolor=_DWR_PRODA_EDGE, markersize=3, alpha=0.5),
        )

    # Product B block boxes with grey median line
    ax.boxplot(
        block_data, positions=block_positions, widths=0.5, showfliers=True,
        patch_artist=True, showmeans=True,
        boxprops=dict(facecolor=_DWR_LIGHT_BLUE, edgecolor=_DWR_BLUE, linewidth=1.0),
        medianprops=dict(color=_DWR_GRAY, linewidth=1.8),
        meanprops=dict(marker="D", markerfacecolor=_DWR_BLUE,
                       markeredgecolor=_DWR_BLUE, markersize=5),
        whiskerprops=dict(color=_DWR_BLUE, linewidth=1.0),
        capprops=dict(color=_DWR_BLUE, linewidth=1.0),
        flierprops=dict(marker="o", markerfacecolor=_DWR_GRAY,
                        markeredgecolor=_DWR_GRAY, markersize=3, alpha=0.5),
    )

    if hist_vals.size:
        hist_mean = float(np.mean(hist_vals))
        ax.axhline(hist_mean, color=_DWR_GRAY, linestyle="--", linewidth=1.4,
                   label=f"Historical Mean ({hist_mean:,.1f} {unit})")

    all_positions = [pos_hist] + ([pos_proda] if has_proda else []) + block_positions
    ax.set_xticks(all_positions)
    ax.set_xticklabels(labels, fontsize=11, fontweight="medium")
    ax.set_xlabel("Historical / Product A / Product B Block", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel(f"Annual WY Precipitation ({unit})", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.tick_params(axis="both", labelsize=11)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5, color="#CCCCCC")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(frameon=True, loc="best", fontsize=10,
              edgecolor="#CCCCCC", fancybox=False, framealpha=0.9)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def run_compare_historical_productB(args):
    """Compare historical annual WY precip vs Product A and Product B (n01-n10) boxplots.

    The Product A box (single historical-length realization) is included when the
    Product A validation CSV (output/_product_a_validation/_uhh_precip_productA_*.csv)
    is available; otherwise only Historical and the Product B blocks are drawn.

    Produces:
      - one figure per UHH location
      - Sac Valley aggregate (area-weighted; excludes TR, WH)
      - SJ Valley aggregate (area-weighted)
      - All aggregate (area-weighted; excludes TR, WH)
    """
    script_dir = Path(__file__).parent.resolve()
    gen_dir = get_module_generated_dir("mod_forcing/climate")
    repo_root = Path(__file__).resolve().parents[2]
    grid_info_folder = repo_root / "mod_forcing" / "climate" / "reference" / "GridInfo"

    productB_dir = gen_dir / "output" / "_product_b_final"
    if not productB_dir.exists():
        raise FileNotFoundError(f"Product B folder not found: {productB_dir}")

    out_dir = gen_dir / "output" / "_2_uhh_basin_averages" / set_name("B") / "_compare_historical_productB"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read UHH locations table
    locations_df = read_uhh_locations(script_dir / args.locations)

    # Load historical WY totals (from __calsim_sv_default__.dss) and area weights per location
    hist_wy_by_loc: dict = {}
    weights_by_loc: dict = {}
    ppt_name_by_loc: dict = {}
    print("\nLoading historical WY precip totals from __calsim_sv_default__.dss ...")
    for _, row in locations_df.iterrows():
        shorthand = row['location']
        stem = _ppt_filename_stem(shorthand)
        try:
            hist_wy_by_loc[shorthand] = _historical_wy_totals_from_dss(stem)
        except Exception as e:
            print(f"  WARNING: could not read DSS historical for {shorthand} ({stem}): {e}")
            continue
        weights_by_loc[shorthand] = _basin_weight_from_gridinfo(grid_info_folder, row['grid_info_file'])
        ppt_name_by_loc[shorthand] = stem
        print(f"  {shorthand}: {len(hist_wy_by_loc[shorthand])} WYs, weight={weights_by_loc[shorthand]:.2f}")

    # Load Product B WY totals per chunk per location
    chunk_files = [f for f in (productB_dir / f"_uhh_precip_productB_n{k:02d}.csv"
                               for k in range(1, N_CHUNKS + 1)) if f.exists()]
    if not chunk_files:
        raise FileNotFoundError(f"No Product B precip chunk files found in {productB_dir}")

    # per_loc_chunks[shorthand] = list of DataFrames (one per chunk, in order)
    per_loc_chunks: dict = {s: [] for s in hist_wy_by_loc}
    for chunk_csv in chunk_files:
        print(f"  Reading {chunk_csv.name}...")
        chunk_totals = _long_format_wy_totals(chunk_csv)
        empty = pd.DataFrame(columns=['WY', 'precip_inches'])
        for shorthand in hist_wy_by_loc:
            loc_name = ppt_name_by_loc[shorthand]
            per_loc_chunks[shorthand].append(chunk_totals.get(loc_name, empty))

    # Load Product A WY totals per location (single historical-length realization,
    # WY ~1922-2018) from the Product A validation CSV, if present. Same long
    # format as the Product B chunks, so it reads with the same helper.
    empty_wy = pd.DataFrame(columns=['WY', 'precip_inches'])
    productA_by_loc: dict = {}
    productA_val_dir = delivery_dir(gen_dir / "output", "A")
    productA_files = sorted(productA_val_dir.glob("_uhh_precip_productA_*.csv"))
    if productA_files:
        productA_csv = productA_files[-1]
        print(f"\nLoading Product A WY precip totals from {productA_csv.name} ...")
        productA_totals = _long_format_wy_totals(productA_csv)
        for shorthand in hist_wy_by_loc:
            loc_name = ppt_name_by_loc[shorthand]
            if loc_name in productA_totals:
                productA_by_loc[shorthand] = productA_totals[loc_name]
                print(f"  {shorthand}: {len(productA_by_loc[shorthand])} WYs")
    else:
        print(f"\nNo Product A validation CSV in {productA_val_dir} "
              "(_uhh_precip_productA_*.csv); Product A box will be omitted.")

    # --- Per-location figures ---
    print("\nGenerating per-location comparison figures...")
    for shorthand in hist_wy_by_loc:
        hist_wy = hist_wy_by_loc[shorthand]
        block_list = per_loc_chunks[shorthand]
        proda_wy = productA_by_loc.get(shorthand)
        title = f"Annual WY Precipitation - {shorthand}"
        out_png = out_dir / f"boxplot_precip_hist_vs_productB_{shorthand}.png"
        _plot_hist_vs_productB_box(hist_wy, block_list, title, out_png, productA_wy=proda_wy)
        print(f"  {out_png.name}")

    # --- Aggregate figures (area-weighted) ---
    aggregate_groups = [
        ("SacValley", "Sacramento Valley UHH Locations", _SAC_VALLEY_LOCS),
        ("SJValley", "San Joaquin Valley UHH Locations", _SJ_VALLEY_LOCS),
        ("All", "All UHH Locations", _ALL_LOCS),
    ]

    print("\nGenerating aggregate comparison figures...")
    for tag, label, locs in aggregate_groups:
        available = [s for s in locs if s in hist_wy_by_loc]
        if not available:
            print(f"  Skipping {tag}: no data for any of {locs}")
            continue
        w = {s: weights_by_loc[s] for s in available}

        # Aggregate historical: area-weighted mean of basin WY totals
        hist_per_loc = {s: hist_wy_by_loc[s] for s in available}
        hist_agg = _area_weighted_mean(hist_per_loc, w)

        # Aggregate Product A (area-weighted) when any group location has it
        proda_agg = None
        if any(s in productA_by_loc for s in available):
            proda_per_loc = {s: productA_by_loc.get(s, empty_wy) for s in available}
            proda_agg = _area_weighted_mean(proda_per_loc, w)

        # Aggregate Product B per chunk
        n_chunks = len(chunk_files)
        block_agg_list = []
        for i in range(n_chunks):
            chunk_per_loc = {s: per_loc_chunks[s][i] for s in available}
            block_agg_list.append(_area_weighted_mean(chunk_per_loc, w))

        title = f"Annual WY Precipitation - {label}"
        out_png = out_dir / f"boxplot_precip_hist_vs_productB_{tag}.png"
        _plot_hist_vs_productB_box(hist_agg, block_agg_list, title, out_png, productA_wy=proda_agg)
        print(f"  {out_png.name}")

    # Build stats table: rows = location (+ aggregates), columns = scenario stats
    # -------------------------------------------------------------------
    # Helper to compute stats for a single WY series
    def _stats(v: pd.Series) -> dict:
        if len(v) == 0:
            return {'mean': np.nan, 'min': np.nan, 'max': np.nan, 'n': 0}
        return {'mean': float(v.mean()), 'min': float(v.min()),
                'max': float(v.max()), 'n': int(len(v))}

    # Each section: (label, historical series, Product A series or None, list of block series)
    # All locations from the per-location loop, then the three aggregates
    stat_sections: list = []
    for shorthand in hist_wy_by_loc:
        proda = productA_by_loc.get(shorthand)
        stat_sections.append((
            shorthand,
            hist_wy_by_loc[shorthand]['precip_inches'],
            proda['precip_inches'] if proda is not None and not proda.empty else None,
            [bw['precip_inches'] for bw in per_loc_chunks[shorthand]],
        ))
    # Aggregates (same computation used for figures)
    for tag, _label, locs in aggregate_groups:
        available = [s for s in locs if s in hist_wy_by_loc]
        if not available:
            continue
        w = {s: weights_by_loc[s] for s in available}
        hist_agg_s = _area_weighted_mean({s: hist_wy_by_loc[s] for s in available}, w)
        proda_agg_s = None
        if any(s in productA_by_loc for s in available):
            proda_agg_s = _area_weighted_mean(
                {s: productA_by_loc.get(s, empty_wy) for s in available}, w)
        block_agg_s = []
        for i in range(len(chunk_files)):
            block_agg_s.append(_area_weighted_mean({s: per_loc_chunks[s][i] for s in available}, w))
        stat_sections.append((
            f"[{tag}]",
            hist_agg_s['precip_inches'],
            proda_agg_s['precip_inches'] if proda_agg_s is not None and not proda_agg_s.empty else None,
            [b['precip_inches'] for b in block_agg_s],
        ))

    # Build tidy stats rows
    stats_rows = []
    n_chunks = len(chunk_files)
    for loc_label, hist_series, proda_series, block_series_list in stat_sections:
        h = _stats(hist_series)
        row = {
            'location': loc_label,
            'Historical_mean_in': h['mean'],
            'Historical_min_in': h['min'],
            'Historical_max_in': h['max'],
            'Historical_n_WYs': h['n'],
        }
        p = _stats(proda_series if proda_series is not None else pd.Series(dtype=float))
        row['ProductA_mean_in'] = p['mean']
        row['ProductA_min_in'] = p['min']
        row['ProductA_max_in'] = p['max']
        row['ProductA_n_WYs'] = p['n']
        for i, bv in enumerate(block_series_list, start=1):
            s = _stats(bv)
            tag = f'n{i:02d}'
            row[f'{tag}_mean_in'] = s['mean']
            row[f'{tag}_min_in'] = s['min']
            row[f'{tag}_max_in'] = s['max']
        stats_rows.append(row)

    if stats_rows:
        stats_csv = out_dir / "_annual_precip_stats.csv"
        pd.DataFrame(stats_rows).to_csv(stats_csv, index=False)
        print(f"\nStats table: {stats_csv}")

    print(f"\nFigures saved to: {out_dir}")


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
    parser.add_argument('--product', choices=SETS,
                        help='Weather set: historical (WGEN Historical_Unsplit), A, B '
                             '(WGEN scenario 1) or LTO (Historical_Climate_LTO)')
    parser.add_argument(
        '--validate-outputs',
        action='store_true',
        dest='validate_outputs',
        help='Validate Product_A outputs against reference data in calsim_climate_sv.xlsx'
    )
    parser.add_argument(
        '--compare-historical-productB',
        action='store_true',
        dest='compare_historical_productB',
        help='Compare historical annual WY precipitation against Product A and Product B '
             '(n01-n10) boxplots. The Product A box is included when its delivery CSV is '
             'available. Generates one figure per UHH location plus area-weighted aggregates '
             'for the Sacramento Valley, San Joaquin Valley, and all UHH locations '
             '(TR and WH excluded).'
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
        help='Start date of a single series (default: 1920-10-01)'
    )
    parser.add_argument(
        '--end_date',
        type=str,
        default='2021-09-30',
        help='End date of a single series (default: 2021-09-30)'
    )

    args = parser.parse_args()

    # --product is required unless a standalone action is used
    standalone = args.validate_outputs or args.compare_historical_productB
    if not standalone and not args.product:
        parser.error("--product is required (or use --validate-outputs / --compare-historical-productB)")
    return args


def main():
    """
    Main function to extract monthly basin averages for UHH locations.
    """
    args = parse_arguments()

    if args.validate_outputs:
        run_validate_outputs(set_name("A"))
        return

    if args.compare_historical_productB:
        run_compare_historical_productB(args)
        return

    product = args.product
    script_dir = Path(__file__).parent.resolve()
    gen_dir = get_module_generated_dir("mod_forcing/climate")

    uhh_locations_file = script_dir / args.locations
    excel_file = script_dir / "reference" / "calsim_climate_sv.xlsx"
    if not excel_file.exists():
        excel_file = script_dir / "input" / "calsim_climate_sv.xlsx"
    repo_root = Path(__file__).resolve().parents[2]
    grid_info_folder = repo_root / "mod_forcing" / "climate" / "reference" / "GridInfo"

    script_output_folder = gen_dir / "output" / "_2_uhh_basin_averages" / set_name(product)
    script_output_folder.mkdir(parents=True, exist_ok=True)

    print("="*80)
    print("EXTRACTING MONTHLY BASIN AVERAGES FOR UHH LOCATIONS")
    print("="*80)
    print(f"Weather set: {set_name(product)}")
    print(f"Grid info folder: {grid_info_folder}")
    print(f"Output folder: {script_output_folder}")

    if not grid_info_folder.exists():
        raise FileNotFoundError(f"Grid info folder not found: {grid_info_folder}")

    date_index = None
    if product != 'B':
        date_index = pd.date_range(start=args.start_date, end=args.end_date, freq='D')
        print(f"Analysis period: {args.start_date} to {args.end_date} ({len(date_index)} days)")

    print(f"\nReading UHH locations from: {uhh_locations_file}")
    locations_df = read_uhh_locations(uhh_locations_file)
    print(f"Found {len(locations_df)} watershed locations to process")

    summaries, failed = [], []
    for idx, row in locations_df.iterrows():
        try:
            summaries.append(process_location(
                shorthand=row['location'],
                grid_info_file=row['grid_info_file'],
                grid_info_folder=grid_info_folder,
                product=product,
                output_folder=script_output_folder,
                date_index=date_index,
                excel_file=excel_file
            ))
        except Exception as e:
            print(f"  ERROR processing {row['location']}: {str(e)}")
            failed.append(row['location'])
    if failed:
        raise SystemExit(f"{len(failed)} location(s) failed, so their SVs would be missing: {failed}")

    if summaries:
        if product == 'B':
            write_product_b_chunks(summaries, gen_dir / "output" / "_product_b_final")
        elif product in DELIVERY:
            write_delivery(summaries, gen_dir / "output", product)

        summary_rows = [{k: v for k, v in s.items() if not k.startswith('_')} for s in summaries]
        summary_df = pd.DataFrame(summary_rows)
        summary_file = script_output_folder / "_summary.csv"
        summary_df.to_csv(summary_file, index=False)
        print(f"\n{'='*80}")
        print("Processing complete!")
        print(f"Successfully processed {len(summaries)} out of {len(locations_df)} locations")
        print(f"Summary saved to: {summary_file}")
        print(f"{'='*80}")

        print("\nSummary Statistics:")
        print(f"  Average number of grid cells per basin: {summary_df['num_grid_cells'].mean():.1f}")
        print(f"  Average monthly precip (across all basins): {summary_df['mean_monthly_precip_inches'].mean():.2f} inches")
        print(f"  Average monthly tavg (across all basins): {summary_df['mean_monthly_tavg_f'].mean():.2f} degF")
    else:
        print("\nNo locations were successfully processed.")


if __name__ == "__main__":
    main()
