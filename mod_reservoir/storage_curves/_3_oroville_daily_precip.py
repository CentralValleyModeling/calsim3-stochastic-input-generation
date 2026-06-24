"""
Extract Daily Basin-Averaged Precipitation for Oroville / Feather River
======================================================================
Computes grid-weighted daily basin-average precipitation (inches) for the
Oroville/Feather River basin from WGEN weather data, using grid weights from
CS3_8RI_OROVI_GridInfo.txt.

For Product_B: 10 chunk CSVs of 100 water years each (WY1922-WY2021); skips
Jan-Sep of Year 1 to align to the October water-year start.
For Product_A and Historical: single output files.

Inputs
------
- WGEN weather data (Product_A / Product_B / Historical)
- mod_forcing/vic/reference/GridInfo/CS3_8RI_OROVI_GridInfo.txt (override with --grid_info)

Outputs
-------
- <generated>/output/_3_oroville_daily_precip/  (daily precip CSVs)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
    python _3_oroville_daily_precip.py --source Product_A
    python _3_oroville_daily_precip.py --source Product_B
    python _3_oroville_daily_precip.py --source Historical
    python _3_oroville_daily_precip.py --compare
    python _3_oroville_daily_precip.py --source Product_B --compare
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

_gen = get_module_generated_dir("mod_reservoir/storage_curves")
_ref = Path(__file__).resolve().parents[2] / 'mod_forcing' / 'vic' / 'reference' / 'GridInfo'


def parse_grid_info_file(grid_info_path):
    """
    Parse the Oroville grid info file to extract grid cell coordinates and weights.
    
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
    data_folder : Path or str
        Path to folder containing meteo files

    Returns:
    --------
    Path or None
    """
    data_folder = Path(data_folder)
    # WGEN files: meteo_LAT_LON; Historical files: data_LAT_LON
    meteo_path = data_folder / f"meteo_{lat}_{lon}"
    data_path = data_folder / f"data_{lat}_{lon}"

    if meteo_path.exists():
        return meteo_path
    elif data_path.exists():
        return data_path
    return None


def read_meteo_file(filepath):
    """
    Read a meteo file and return as a pandas DataFrame.
    
    File format: YEAR MONTH DAY PRECIP(mm) TMAX(C) TMIN(C)
    
    Parameters:
    -----------
    filepath : str
        Path to meteo file
        
    Returns:
    --------
    pd.DataFrame with columns: date, precip_mm
    """
    data = pd.read_csv(
        filepath, 
        sep=r'\s+', 
        header=None,
        names=['year', 'month', 'day', 'precip_mm', 'tmax_c', 'tmin_c']
    )
    
    # Create date column
    data['date'] = pd.to_datetime(data[['year', 'month', 'day']])
    
    return data[['date', 'precip_mm']]


def calculate_basin_daily_precipitation(grid_info_df, data_folder, date_index):
    """
    Calculate basin-averaged daily precipitation using weighted aggregation.
    
    Parameters:
    -----------
    grid_info_df : pd.DataFrame
        DataFrame with grid cell info (lat, lon, weights)
    data_folder : str
        Path to folder containing meteo files
    date_index : pd.DatetimeIndex
        Full date range for the analysis period
        
    Returns:
    --------
    pd.DataFrame with daily basin-averaged precipitation
    """
    weighted_precip_sum = None
    weight_total = 0.0
    
    print(f"  Processing {len(grid_info_df)} grid cells...")
    
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
        daily_data = read_meteo_file(meteo_file)
        daily_data = daily_data.set_index('date')
        
        # Ensure full date coverage (fill missing with NaN)
        precip_series = daily_data.reindex(date_index)['precip_mm']
        
        # Apply weight and accumulate
        precip_contrib = precip_series * weight
        
        weighted_precip_sum = precip_contrib if weighted_precip_sum is None else (weighted_precip_sum + precip_contrib)
        weight_total += weight
    
    if weighted_precip_sum is None:
        raise ValueError("No valid meteo files found for any grid cells")
    
    # Normalize by total weight
    daily_precip_mm = weighted_precip_sum / weight_total
    
    # Convert to inches
    daily_precip_inches = daily_precip_mm / 25.4
    
    # Create output DataFrame
    daily_df = pd.DataFrame({
        'year': daily_precip_inches.index.year,
        'month': daily_precip_inches.index.month,
        'day': daily_precip_inches.index.day,
        'precip_inches': daily_precip_inches.values
    })
    daily_df['date'] = daily_precip_inches.index
    
    return daily_df


def calculate_basin_daily_precip_product_b(grid_info_df, data_folder):
    """
    Compute basin-averaged daily precipitation for Product B.

    Product B WGEN files use synthetic years starting at 1 (below pandas
    Timestamp minimum), so dates cannot be parsed with pd.to_datetime.
    Reads raw numeric data, computes the weighted basin average, and returns
    a DataFrame with the original synthetic Year/Month/Day columns intact.

    Parameters
    ----------
    grid_info_df : pd.DataFrame
        Grid cell info with columns lat, lon, weight1.
    data_folder : Path or str
        Directory containing WGEN meteo files (meteo_LAT_LON).

    Returns
    -------
    pd.DataFrame with columns: Year, Month, Day, precip_inches
    """
    data_folder = Path(data_folder)
    weighted_precip = None
    weight_total = 0.0
    ymd = None

    print(f"  Processing {len(grid_info_df)} grid cells...")
    for _, row in grid_info_df.iterrows():
        lat, lon, weight = row['lat'], row['lon'], row['weight1']
        f = data_folder / f"meteo_{lat}_{lon}"
        if not f.exists():
            print(f"    Warning: meteo_{lat}_{lon} not found, skipping")
            continue
        raw = np.loadtxt(f)
        if ymd is None:
            ymd = raw[:, :3].astype(int)
        contrib = raw[:, 3] * weight
        weighted_precip = contrib if weighted_precip is None else weighted_precip + contrib
        weight_total += weight

    if weighted_precip is None:
        raise ValueError("No valid meteo files found for any grid cells")

    daily_in = (weighted_precip / weight_total) / 25.4
    return pd.DataFrame({
        'Year': ymd[:, 0],
        'Month': ymd[:, 1],
        'Day': ymd[:, 2],
        'precip_inches': daily_in,
    })


_MONTH_NAMES = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
}


def compare_product_a_vs_b(output_dir=None):
    """
    Compare monthly average daily precipitation between Product A and Product B.

    Reads pre-generated outputs from disk:
      - Product A: Oroville_Daily_Precip_ProductA_Scenario1.csv
      - Product B: oroville_daily_precip_productB_n01.csv ... n10.csv

    Computes mean daily precip (inches/day) by calendar month for each product
    and writes comparison_monthly_avg.csv to _compare_ab/.

    Parameters
    ----------
    output_dir : path-like, optional
        Directory containing the generated CSV files
        (default: _gen/output/_3_oroville_daily_precip).
    """
    if output_dir is None:
        output_dir = _gen / 'output' / '_3_oroville_daily_precip'
    output_dir = Path(output_dir)
    compare_dir = output_dir / '_compare_ab'

    print("\n" + "=" * 70)
    print("Product A vs Product B -- Oroville Daily Precipitation")
    print("=" * 70)

    # ------------------------------------------------------------------ #
    # Load Product A
    # ------------------------------------------------------------------ #
    pa_files = sorted(output_dir.glob('Oroville_Daily_Precip_ProductA_Scenario*.csv'))
    if not pa_files:
        print(f"Error: No Product A file found in {output_dir}")
        print("Run with --source Product_A first.")
        return
    pa_file = pa_files[0]
    pa_df = pd.read_csv(pa_file)
    pa_monthly = pa_df.groupby('month')['precip_inches'].mean()
    print(f"Product A: {pa_file.name}  ({len(pa_df)} days)")

    # ------------------------------------------------------------------ #
    # Load Product B chunks
    # ------------------------------------------------------------------ #
    pb_files = sorted(output_dir.glob('oroville_daily_precip_productB_n*.csv'))
    if not pb_files:
        print(f"Error: No Product B chunk files found in {output_dir}")
        print("Run with --source Product_B first.")
        return

    chunk_dfs = {}
    for f in pb_files:
        label = f.stem.split('_')[-1]   # e.g. 'n01'
        chunk_dfs[label] = pd.read_csv(f)
    chunk_labels = sorted(chunk_dfs.keys())
    print(f"Product B: {len(chunk_labels)} chunks ({', '.join(chunk_labels)})")

    # ------------------------------------------------------------------ #
    # Build comparison table
    # ------------------------------------------------------------------ #
    rows = []
    for m in range(1, 13):
        row = {
            'month': m,
            'month_name': _MONTH_NAMES[m],
            'ProductA_mean_in_day': pa_monthly.get(m, np.nan),
        }
        for label, df in chunk_dfs.items():
            row[label] = df[df['month'] == m]['precip_inches'].mean()
        rows.append(row)

    col_order = ['month', 'month_name', 'ProductA_mean_in_day'] + chunk_labels
    table = pd.DataFrame(rows)[col_order]

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #
    compare_dir.mkdir(parents=True, exist_ok=True)
    out_file = compare_dir / 'comparison_monthly_avg.csv'
    table.to_csv(out_file, index=False)
    print(f"\nSaved: {out_file}")

    # Print to console
    chunk_hdr = ''.join(f'  {lbl:>8}' for lbl in chunk_labels)
    hdr = f"  {'Month':<5}  {'Product A':>12}{chunk_hdr}"
    sep = "  " + "-" * (len(hdr) - 2)
    print("\nMean daily precip by calendar month (inches/day):")
    print(hdr)
    print(sep)
    for _, row in table.iterrows():
        chunk_vals = ''.join(f"  {row[lbl]:>8.4f}" for lbl in chunk_labels)
        print(
            f"  {row['month_name']:<5}  "
            f"{row['ProductA_mean_in_day']:>12.4f}"
            f"{chunk_vals}"
        )


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Extract daily basin-averaged precipitation for Oroville basin'
    )

    parser.add_argument(
        '--source',
        type=str,
        default=None,
        choices=['Product_A', 'Product_B', 'Historical'],
        help='Data source: Product_A, Product_B, or Historical'
    )

    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare monthly averages between pre-generated Product A and Product B outputs'
    )

    parser.add_argument(
        '--scenario',
        type=int,
        default=1,
        help='WGEN scenario subfolder number (default: 1; ignored for Historical)'
    )

    parser.add_argument(
        '--grid_info',
        type=str,
        default=None,
        help='Path to grid info file (default: reference/CS3_8RI_OROVI_GridInfo.txt)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()

    if not args.source and not args.compare:
        print("No action specified. Use --source {{Product_A,Product_B,Historical}} or --compare.")
        return

    # Output directory (shared by all modes)
    output_dir = _gen / 'output' / '_3_oroville_daily_precip'
    output_dir.mkdir(parents=True, exist_ok=True)

    # --compare: read pre-generated outputs, produce comparison table
    if args.compare:
        compare_product_a_vs_b(output_dir=output_dir)
        if not args.source:
            return

    if not args.source:
        return

    # Grid info file
    grid_info_path = Path(args.grid_info) if args.grid_info else _ref / 'CS3_8RI_OROVI_GridInfo.txt'
    if not grid_info_path.exists():
        raise FileNotFoundError(f"Grid info file not found: {grid_info_path}")

    # Data folder
    if args.source == 'Historical':
        data_folder = get_base_dir() / 'Historical_Climate_LTO' / '1_Historical'
    else:
        data_folder = get_base_dir() / 'WGEN' / args.source / str(args.scenario)

    if not data_folder.exists():
        raise FileNotFoundError(f"Data folder not found: {data_folder}")
    
    print("Processing Oroville basin daily precipitation")
    print(f"  Source: {args.source}")
    if args.source != 'Historical':
        print(f"  Scenario: {args.scenario}")
    print(f"  Grid info: {grid_info_path}")
    print(f"  Data folder: {data_folder}")
    print(f"  Output folder: {output_dir}")
    
    # Read grid info
    print("\nReading grid info file...")
    grid_info_df = parse_grid_info_file(grid_info_path)
    print(f"  Found {len(grid_info_df)} grid cells")
    print(f"  Total weight: {grid_info_df['weight1'].sum():.2f}")
    
    # Determine date range (Product A and Historical only)
    if args.source == 'Historical':
        start_date = '1915-10-01'
        end_date = '2015-09-30'
        print(f"\nDate range: {start_date} to {end_date}")
    elif args.source == 'Product_A':
        start_date = '1915-10-01'
        end_date = '2018-09-30'
        print(f"\nDate range: {start_date} to {end_date}")

    # Process data
    if args.source == 'Product_B':
        # Read full 1000-year sequence using raw synthetic year numbers
        # (years 1-1008 are below pandas Timestamp minimum and cannot be parsed directly)
        print("\nReading Product B daily data (full 1000-year sequence)...")
        daily_df = calculate_basin_daily_precip_product_b(grid_info_df, data_folder)

        # Skip Jan-Sep of year 1 to align to October water year start
        daily_df = daily_df[
            ~((daily_df['Year'] == 1) & (daily_df['Month'] < 10))
        ].reset_index(drop=True)

        # Assign synthetic water year
        daily_df['WY'] = np.where(daily_df['Month'] >= 10, daily_df['Year'] + 1, daily_df['Year'])

        # Chunk into 10 groups of 100 water years (same convention as rim inflow chunker)
        wys = sorted(daily_df['WY'].unique())
        wys_per_chunk = 100
        print(f"\nWriting 10 chunks of {wys_per_chunk} water years each (WY1922-WY2021 template)...")
        for k in range(10):
            wy_chunk = set(wys[k * wys_per_chunk: (k + 1) * wys_per_chunk])
            chunk = daily_df[daily_df['WY'].isin(wy_chunk)].copy()

            # Relabel years to template Oct 1921 - Sep 2021 (WY1922-WY2021).
            # Chunk k starts at Oct of synthetic year (1 + 100k); map that to 1921.
            year_offset = 1920 - 100 * k
            chunk['year'] = chunk['Year'] + year_offset

            out = chunk[['year', 'Month', 'Day', 'precip_inches']].rename(
                columns={'Month': 'month', 'Day': 'day'}
            )
            output_file = output_dir / f'oroville_daily_precip_productB_n{k+1:02d}.csv'
            out.to_csv(output_file, index=False)
            print(f"  Chunk {k+1:02d}/10: {len(out)} days | WY1922-WY2021 | {output_file.name}")

        print(f"\nProduct B outputs: {output_dir}")

    else:
        # Product_A or Historical: single continuous output
        date_index = pd.date_range(start=start_date, end=end_date, freq='D')

        print("\nCalculating basin-averaged precipitation...")
        daily_df = calculate_basin_daily_precipitation(grid_info_df, str(data_folder), date_index)

        # Save output
        if args.source == 'Historical':
            output_file = output_dir / 'Oroville_Daily_Precip_Historical.csv'
        else:
            output_file = output_dir / f'Oroville_Daily_Precip_ProductA_Scenario{args.scenario}.csv'

        daily_df[['year', 'month', 'day', 'precip_inches']].to_csv(output_file, index=False)

        print(f"\nSaved: {output_file}")
        print(f"  Years: {daily_df['year'].min()} to {daily_df['year'].max()}")
        print(f"  Records: {len(daily_df)}")
        print(f"  Mean daily precip: {daily_df['precip_inches'].mean():.4f} inches")
        print(f"  Total precip: {daily_df['precip_inches'].sum():.2f} inches")


if __name__ == "__main__":
    main()
