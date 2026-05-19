"""
Extract Monthly Precipitation for PP Point Locations
====================================================
Extracts monthly precipitation time series from WGEN weather data for all
PP point locations specified in reference/pp_point_locations.csv.
Finds the nearest VIC grid cell for each lat/lon and aggregates daily → monthly.

Product A: one CSV per location.
Product B: 10 long-format chunk CSVs (100 WY each, Oct 1921 – Sep 2021).

Inputs
------
- reference/pp_point_locations.csv
- WGEN/Product_A/1/  or  WGEN/Product_B/1/  or  Historical_Climate/  (meteo files)

Outputs
-------
- output/_1_pp_point_locations/product_a/<location>_monthly_precip.csv
- output/_product_a_validation/_pp_precip_productA_{start_wy}_{end_wy}.csv
- output/_product_b_final/_pp_precip_productB_n01.csv ... n10.csv
- output/_1_pp_point_locations/{source}/_summary.csv

Usage
-----
    cd mod_forcing/climate && python _1_pp_point_locations.py --source Product_A --scenario 1
    cd mod_forcing/climate && python _1_pp_point_locations.py --source Product_B --scenario 1
    cd mod_forcing/climate && python _1_pp_point_locations.py --source Historical
"""

import argparse
import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


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


def read_meteo_file(filepath, product_b=False):
    """
    Read a meteo file and return as a pandas DataFrame.
    
    File format: YEAR MONTH DAY PRECIP(mm) TMAX(C) WIND(m/s)
    
    Parameters:
    -----------
    filepath : str
        Path to meteo file
    product_b : bool
        If True, assign a PeriodIndex instead of parsing dates
        (Product B years 1-1008 are below pandas Timestamp min ~1677)
        
    Returns:
    --------
    pd.DataFrame with 'precip_mm' column and appropriate index
    """
    data = pd.read_csv(filepath, sep=r'\s+', header=None,
                       names=['year', 'month', 'day', 'precip_mm', 'tmax_c', 'wind_ms'])
    
    if product_b:
        data.index = pd.period_range(start='2025-01-01', periods=len(data), freq='D')
    else:
        data['date'] = pd.to_datetime(data[['year', 'month', 'day']])
    
    return data


def calculate_monthly_precip(daily_data, product_b=False):
    """
    Calculate monthly precipitation totals from daily data.
    
    Parameters:
    -----------
    daily_data : pd.DataFrame
        DataFrame with 'precip_mm' column; DatetimeIndex (Product A/Hist)
        or PeriodIndex (Product B)
    product_b : bool
        If True, input has PeriodIndex; use 'M' instead of 'MS'
        
    Returns:
    --------
    pd.DataFrame with monthly precipitation totals
    """
    if product_b:
        monthly_precip = daily_data['precip_mm'].resample('M').sum()
        monthly_precip_inches = monthly_precip / 25.4
        monthly_df = pd.DataFrame({
            'year':          [p.year  for p in monthly_precip_inches.index],
            'month':         [p.month for p in monthly_precip_inches.index],
            'precip_inches': monthly_precip_inches.values,
        })
    else:
        daily_indexed = daily_data.set_index('date')
        monthly_precip = daily_indexed['precip_mm'].resample('MS').sum()
        monthly_precip_inches = monthly_precip / 25.4
        monthly_df = pd.DataFrame({
            'year':          monthly_precip_inches.index.year,
            'month':         monthly_precip_inches.index.month,
            'precip_inches': monthly_precip_inches.values,
        })
        monthly_df['date'] = monthly_precip_inches.index
    
    return monthly_df


def read_point_locations(csv_file):
    """
    Read the PP point locations from CSV file.
    
    Parameters:
    -----------
    csv_file : str or Path
        Path to pp_point_locations.csv
        
    Returns:
    --------
    pd.DataFrame with columns: location_name, lat, lon
    """
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    df = df.rename(columns={'location': 'location_name', 'latitude': 'lat', 'longitude': 'lon'})
    df['location_name'] = df['location_name'].str.strip()
    df['lat'] = df['lat'].astype(str).str.strip().astype(float)
    df['lon'] = df['lon'].astype(str).str.strip().astype(float)
    return df


def process_location(location_name, target_lat, target_lon, data_folder, output_folder, product_b=False):
    """
    Process a single location: find nearest grid cell, extract monthly precip, and save.
    For Product B, file saving is deferred to write_product_b_chunks().
    
    Parameters:
    -----------
    location_name : str
        Name of the location
    target_lat : float
        Target latitude
    target_lon : float
        Target longitude
    data_folder : str
        Path to folder containing meteo files
    output_folder : Path
        Path to output folder
    product_b : bool
        If True, skip individual file saving; embed monthly data in return dict
        
    Returns:
    --------
    dict : Summary information about the processing
    """
    print(f"\nProcessing {location_name}...")
    print(f"  Target location: {target_lat}°N, {target_lon}°E")
    
    # Find nearest grid cell
    nearest_file, nearest_lat, nearest_lon, distance = find_nearest_grid_cell(
        target_lat, target_lon, data_folder
    )
    
    print(f"  Nearest grid cell: {nearest_lat}°N, {nearest_lon}°E")
    print(f"  Distance: {distance:.4f}° (~{distance * 111:.2f} km)")
    
    # Read the meteo file
    daily_data = read_meteo_file(nearest_file, product_b=product_b)
    
    # Calculate monthly precipitation
    monthly_precip = calculate_monthly_precip(daily_data, product_b=product_b)
    
    if product_b:
        print(f"  Product B: {len(monthly_precip)} months loaded (will compile into chunks)")
    else:
        # Save to CSV
        output_file = output_folder / f"{location_name}_monthly_precip.csv"
        monthly_precip.to_csv(output_file, index=False)
        print(f"  Output saved: {output_file.name}")
    
    # Return summary info
    return {
        'location_name': location_name,
        'target_lat': target_lat,
        'target_lon': target_lon,
        'grid_lat': nearest_lat,
        'grid_lon': nearest_lon,
        'distance_deg': distance,
        'distance_km': distance * 111,
        'mean_monthly_precip_inches': monthly_precip['precip_inches'].mean(),
        'total_months': len(monthly_precip),
        '_monthly_data': monthly_precip,  # retained for Product B chunk compilation
    }


def write_product_a_validation(summaries, output_folder, start_wy=1922, end_wy=2018):
    """
    Create combined long-format validation CSV from processed Product A summaries.
    Output: _pp_precip_productA_{start_wy}_{end_wy}.csv
    Format: Part B, Part C, Year, Month, Value
    """
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    all_rows = []
    for s in summaries:
        md = s.get('_monthly_data')
        if md is None or 'date' not in md.columns:
            continue
        mask = (md['date'] >= start_date) & (md['date'] <= end_date)
        df_filtered = md.loc[mask]
        for _, row in df_filtered.iterrows():
            all_rows.append({
                'Part B': s['location_name'],
                'Part C': 'PRECIP',
                'Year': int(row['year']),
                'Month': int(row['month']),
                'Value': round(row['precip_inches'], 6),
            })

    if not all_rows:
        print("  No data found for Product A validation period.")
        return

    output_df = pd.DataFrame(all_rows)
    output_file = Path(output_folder) / f"_pp_precip_productA_{start_wy}_{end_wy}.csv"
    output_df.to_csv(output_file, index=False)
    n_locations = output_df['Part B'].nunique()
    print(f"\n  Validation CSV: {output_file.name} ({n_locations} locations, {len(output_df)} rows)")


def write_product_b_chunks(summaries: list, output_folder):
    """
    Compile all locations into 10 long-format chunk CSVs (100 WYs each).
    Skips first 9 months (Jan-Sep synthetic year 1) for WY alignment.
    Template dates: Oct 1921 – Sep 2021 (WY1922–2021).
    Output: _pp_precip_productB_n01.csv ... _pp_precip_productB_n10.csv
    Format: Part B, Part C, Year, Month, Value
    """
    skip_months      = 9     # Jan-Sep of synthetic year 1
    months_per_chunk = 1200  # 100 WYs × 12 months
    total_chunks     = 10
    total_needed     = skip_months + months_per_chunk * total_chunks

    date_template = pd.date_range('1921-10-31', periods=months_per_chunk, freq='ME')
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    # Collect per-location arrays
    loc_data = {}
    for s in summaries:
        md = s.get('_monthly_data')
        if md is None:
            continue
        vals = md['precip_inches'].values
        if len(vals) < total_needed:
            print(f"  Warning: {s['location_name']} only {len(vals)} months (need {total_needed}), skipping")
            continue
        loc_data[s['location_name']] = vals

    if not loc_data:
        print("  No valid locations for Product B chunk output.")
        return

    print(f"\nWriting Product B chunk files ({total_chunks} chunks × {months_per_chunk} months)...")
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
                    'Part C': 'PRECIP',
                    'Year':   int(date_template[j].year),
                    'Month':  int(date_template[j].month),
                    'Value':  val,
                })
        chunk_df = pd.DataFrame(rows, columns=['Part B', 'Part C', 'Year', 'Month', 'Value'])
        out_file = output_path / f"_pp_precip_productB_n{i+1:02d}.csv"
        chunk_df.to_csv(out_file, index=False)
        print(f"  Chunk {i+1:02d}/10: {out_file.name} ({len(loc_data)} locations)")

    print(f"Product B chunks: {output_folder}")


def parse_arguments():
    """
    Parse command-line arguments.
    
    Returns:
    --------
    argparse.Namespace : Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Extract monthly precipitation for PP point locations from WGEN weather data'
    )
    parser.add_argument(
        '--source',
        type=str,
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
        '--locations',
        type=str,
        default='input/pp_point_locations.csv',
        help='CSV file with point locations (default: input/pp_point_locations.csv)'
    )
    
    args = parser.parse_args()
    
    # Validate: --source is required
    if not args.source:
        parser.error('--source is required')
    if args.source in ['Product_A', 'Product_B'] and not args.scenario:
        parser.error(f"--scenario is required when using source '{args.source}'")
    
    return args


def main():
    """
    Main function to extract monthly precipitation for all PP point locations.
    """
    # Parse command-line arguments
    args = parse_arguments()
    
    # Set up paths
    script_dir = Path(__file__).parent.resolve()
    base_dir = get_base_dir()
    gen_dir = get_module_generated_dir("mod_forcing/climate")
    
    # Input files
    point_locations_file = script_dir / "reference" / Path(args.locations).name
    if not point_locations_file.exists():
        point_locations_file = script_dir / args.locations
    
    # Build data path based on source type
    if args.source == "Historical":
        # Historical data is in Historical_Climate folder, not WGEN
        data_folder = base_dir / "Historical_Climate"
        output_folder = gen_dir / "output" / "_1_pp_point_locations" / "historical"
        script_output_folder = output_folder
    else:
        # Product_A or Product_B with scenario
        data_folder = base_dir / "WGEN" / args.source / args.scenario
        if args.source == 'Product_A':
            output_folder = gen_dir / "output" / "_1_pp_point_locations" / "product_a"
            script_output_folder = output_folder
        else:
            output_folder = gen_dir / "output" / "_product_b_final"
            script_output_folder = gen_dir / "output" / "_1_pp_point_locations" / "product_b"

    output_folder.mkdir(parents=True, exist_ok=True)
    script_output_folder.mkdir(parents=True, exist_ok=True)
    data_folder_str = str(data_folder)
    print("="*80)
    print("EXTRACTING MONTHLY PRECIPITATION FOR PP POINT LOCATIONS")
    print("="*80)
    print(f"Weather source: {args.source}")
    if args.scenario:
        print(f"Scenario: {args.scenario}")
    print(f"Data folder: {data_folder_str}")
    print(f"Output folder: {output_folder}")
    
    # Check if data folder exists
    if not os.path.exists(data_folder_str):
        raise FileNotFoundError(f"Data folder not found: {data_folder_str}")
    
    # Read point locations
    print(f"\nReading point locations from: {point_locations_file}")
    locations_df = read_point_locations(point_locations_file)
    print(f"Found {len(locations_df)} locations to process")
    
    # Process each location
    summaries = []
    product_b = (args.source == 'Product_B')
    for idx, row in locations_df.iterrows():
        try:
            summary = process_location(
                location_name=row['location_name'],
                target_lat=row['lat'],
                target_lon=row['lon'],
                data_folder=data_folder_str,
                output_folder=output_folder,
                product_b=product_b,
            )
            summaries.append(summary)
        except Exception as e:
            print(f"  ERROR processing {row['location_name']}: {str(e)}")
            continue
    
    # Save summary file
    if summaries:
        if product_b:
            write_product_b_chunks(summaries, output_folder)
        else:
            validation_dir = gen_dir / "output" / "_product_a_validation"
            validation_dir.mkdir(parents=True, exist_ok=True)
            write_product_a_validation(summaries, validation_dir)

        # Strip internal keys before writing summary CSV
        summary_rows = [{k: v for k, v in s.items() if not k.startswith('_')} for s in summaries]
        summary_df = pd.DataFrame(summary_rows)
        summary_file = script_output_folder / "_summary.csv"
        summary_df.to_csv(summary_file, index=False)
        print(f"\n{'='*80}")
        print("Processing complete!")
        print(f"Successfully processed {len(summaries)} out of {len(locations_df)} locations")
        print(f"Summary saved to: {summary_file}")
        print(f"{'='*80}")
        
        # Print summary statistics
        print("\nSummary Statistics:")
        print(f"  Mean distance to grid cell: {summary_df['distance_km'].mean():.2f} km")
        print(f"  Max distance to grid cell: {summary_df['distance_km'].max():.2f} km")
        print(f"  Average monthly precip (across all locations): {summary_df['mean_monthly_precip_inches'].mean():.2f} inches")
    else:
        print("\nNo locations were successfully processed.")


if __name__ == "__main__":
    main()
