"""
Extract monthly precipitation time series from WGEN weather data
for a specified lat/lon location (finds nearest grid cell).

Usage:
    python _extract_monthly_precip_for_point.py 38.0 -121.32
    python _extract_monthly_precip_for_point.py 38.0 -121.32 --product B
    python _extract_monthly_precip_for_point.py 38.0 -121.32 --product A --output path/to/output

Product A: Single output file for the full period.
Product B: 10 chunked output files (100 water years each), skipping the
           first 9 months for Oct water year alignment.

Author: Created 2025-12-23
"""

import os
import sys
import glob
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import get_base_dir


def find_nearest_grid_cell(target_lat, target_lon, data_folder):
    """
    Find the nearest grid cell file to the target lat/lon coordinates.
    
    Parameters:
    -----------
    target_lat : float
        Target latitude
    target_lon : float
        Target longitude
    data_folder : str or Path
        Path to folder containing meteo files
        
    Returns:
    --------
    tuple : (nearest_file, nearest_lat, nearest_lon, distance)
    """
    meteo_files = glob.glob(os.path.join(data_folder, "meteo_*"))
    
    if not meteo_files:
        raise FileNotFoundError(f"No meteo files found in {data_folder}")
    
    # Parse lat/lon from filenames
    grid_points = []
    for filepath in meteo_files:
        filename = os.path.basename(filepath)
        # Format: meteo_LAT_LON
        parts = filename.split('_')
        if len(parts) == 3:
            try:
                lat = float(parts[1])
                lon = float(parts[2])
                grid_points.append((filepath, lat, lon))
            except ValueError:
                continue
    
    if not grid_points:
        raise ValueError("Could not parse any valid grid coordinates from filenames")
    
    # Calculate distances and find nearest
    min_distance = float('inf')
    nearest_file = None
    nearest_lat = None
    nearest_lon = None
    
    for filepath, lat, lon in grid_points:
        # Simple Euclidean distance (for small areas, good enough)
        distance = np.sqrt((lat - target_lat)**2 + (lon - target_lon)**2)
        if distance < min_distance:
            min_distance = distance
            nearest_file = filepath
            nearest_lat = lat
            nearest_lon = lon
    
    return nearest_file, nearest_lat, nearest_lon, min_distance


def read_meteo_file(filepath):
    """
    Read a meteo file and return as a pandas DataFrame.
    
    File format: YEAR MONTH DAY PRECIP(mm) TMAX(C) WIND(m/s)
    
    Parameters:
    -----------
    filepath : str
        Path to meteo file
        
    Returns:
    --------
    pd.DataFrame with columns: date, precip_mm, tmax_c, wind_ms
    """
    # Read the data
    data = pd.read_csv(filepath, sep=r'\s+', header=None,
                       names=['year', 'month', 'day', 'precip_mm', 'tmax_c', 'wind_ms'])
    
    # Create date column
    data['date'] = pd.to_datetime(data[['year', 'month', 'day']])
    
    return data


def calculate_monthly_precip(daily_data):
    """
    Calculate monthly precipitation totals from daily data.
    
    Parameters:
    -----------
    daily_data : pd.DataFrame
        DataFrame with 'date' and 'precip_mm' columns
        
    Returns:
    --------
    pd.DataFrame with monthly precipitation totals
    """
    # Set date as index
    daily_data = daily_data.set_index('date')
    
    # Resample to monthly and sum precipitation
    monthly_precip = daily_data['precip_mm'].resample('MS').sum()
    
    # Convert to DataFrame
    monthly_df = pd.DataFrame({
        'year': monthly_precip.index.year,
        'month': monthly_precip.index.month,
        'precip_mm': monthly_precip.values
    })
    monthly_df['date'] = monthly_precip.index
    
    return monthly_df


def assign_water_year(df):
    """Add a water_year column (Oct-Sep). Oct-Dec belong to the next WY."""
    df = df.copy()
    df['water_year'] = df['year'] + (df['month'] >= 10).astype(int)
    return df


def save_product_b_chunks(monthly_precip, output_folder, base_name, wy_per_chunk=100):
    """
    Split Product B monthly precip into 10 × 100-WY chunks.

    Skips the first 9 months (Jan-Sep of year 1) so output starts at Oct
    of the first water year.  Files are named *_n01.csv through *_n10.csv.

    Parameters:
    -----------
    monthly_precip : pd.DataFrame
        Full monthly precipitation DataFrame
    output_folder : Path
        Output directory
    base_name : str
        Base filename (without _nXX.csv)
    wy_per_chunk : int
        Water years per chunk (default 100)
    """
    df = assign_water_year(monthly_precip)

    # Skip first 9 months for Oct WY alignment
    first_oct = df.loc[df['month'] == 10].iloc[0].name
    df = df.loc[first_oct:]

    all_wys = sorted(df['water_year'].unique())
    n_chunks = len(all_wys) // wy_per_chunk

    for i in range(n_chunks):
        chunk_wys = all_wys[i * wy_per_chunk : (i + 1) * wy_per_chunk]
        chunk = df[df['water_year'].isin(chunk_wys)].drop(columns='water_year')
        chunk_file = output_folder / f"{base_name}_n{i+1:02d}.csv"
        chunk.to_csv(chunk_file, index=False)
        print(f"  Chunk {i+1:02d}: WY {chunk_wys[0]}-{chunk_wys[-1]}  →  {chunk_file.name}")


def main():
    """
    Main function to extract monthly precipitation for specified location.
    """
    parser = argparse.ArgumentParser(
        description='Extract monthly precipitation for a lat/lon point from WGEN data.'
    )
    parser.add_argument('lat', type=float, help='Target latitude (e.g. 38.0)')
    parser.add_argument('lon', type=float, help='Target longitude (e.g. -121.32)')
    parser.add_argument('--product', type=str, default='A', choices=['A', 'B'],
                        help='Product type: A (historical-length) or B (1000-yr stochastic). Default: A')
    parser.add_argument('--output', type=str, default=None,
                        help='Output folder path. Default: ./output')
    args = parser.parse_args()

    TARGET_LAT = args.lat
    TARGET_LON = args.lon
    product = args.product.upper()

    # Data folder path
    data_folder = get_base_dir() / "WGEN" / f"Product_{product}" / "1"
    
    # Convert to string for file operations
    data_folder_str = str(data_folder)
    
    # Output folder
    script_dir = Path(__file__).parent.resolve()
    if args.output:
        output_folder = Path(args.output)
    else:
        output_folder = script_dir / "output"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    print(f"Product: {product}")
    print(f"Target location: {TARGET_LAT}°N, {TARGET_LON}°E")
    print(f"Data folder: {data_folder_str}")
    print(f"Output folder: {output_folder}")
    
    if not os.path.exists(data_folder_str):
        raise FileNotFoundError(f"Data folder not found: {data_folder_str}")

    # Find nearest grid cell
    nearest_file, nearest_lat, nearest_lon, distance = find_nearest_grid_cell(
        TARGET_LAT, TARGET_LON, data_folder_str
    )
    
    print(f"\nNearest grid cell found:")
    print(f"  Location: {nearest_lat}°N, {nearest_lon}°E")
    print(f"  Distance: {distance:.4f}° (~{distance * 111:.2f} km)")
    print(f"  File: {os.path.basename(nearest_file)}")
    
    # Read the meteo file
    print(f"\nReading daily data...")
    daily_data = read_meteo_file(nearest_file)
    print(f"  Data period: {daily_data['date'].min()} to {daily_data['date'].max()}")
    print(f"  Total days: {len(daily_data)}")
    
    # Calculate monthly precipitation
    print(f"\nCalculating monthly precipitation...")
    monthly_precip = calculate_monthly_precip(daily_data)
    print(f"  Total months: {len(monthly_precip)}")

    # Save output
    base_name = f"monthly_precip_{TARGET_LAT}_{TARGET_LON}"
    if product == 'B':
        print(f"\nSplitting into 100-WY chunks...")
        save_product_b_chunks(monthly_precip, output_folder, base_name)
    else:
        output_file = output_folder / f"{base_name}.csv"
        monthly_precip.to_csv(output_file, index=False)
        print(f"\nOutput saved to: {output_file}")
    
    # Print summary statistics
    print(f"\nSummary Statistics:")
    print(f"  Mean monthly precip: {monthly_precip['precip_mm'].mean():.2f} mm")
    print(f"  Min monthly precip: {monthly_precip['precip_mm'].min():.2f} mm")
    print(f"  Max monthly precip: {monthly_precip['precip_mm'].max():.2f} mm")
    print(f"  Total precip: {monthly_precip['precip_mm'].sum():.2f} mm")


if __name__ == "__main__":
    main()
