"""
Extract Monthly Precipitation for PP Point Locations
====================================================
Monthly precipitation (inches) at each PP point location of reference/pp_point_locations.csv,
summed from the daily weather of the nearest grid cell (utils.wgen.nearest_cell).

Inputs
------
- reference/pp_point_locations.csv (location, latitude, longitude)
- daily weather of the --product set (utils.wgen.read_met): WGEN Historical_Unsplit,
  Product_A/1 or Product_B/1, or <base>/Historical_Climate_LTO/1_Historical

Outputs
-------
Under <generated>/mod_forcing/climate/output/:
- _1_pp_point_locations/<Historical_Unsplit|Product_A|LTO>/<location>_monthly_precip.csv
  (year, month, precip_inches, date)
- _1_pp_point_locations/<set name>/_summary.csv (nearest cell, distance, mean monthly precip)
- _historical_unsplit_validation/_pp_precip_historicalUnsplit_1922_2018.csv
- _product_a_validation/_pp_precip_productA_1922_2018.csv
- Product B: _product_b_final/_pp_precip_productB_n01.csv ... _n10.csv, labelled WY1922-2021

Delivery and chunk files are SV format, Part B the location, Part C PRECIP.

Dependencies
------------
utils.paths, utils.csv_io, utils.wgen, utils.wgen_calendar

Usage
-----
    python mod_forcing/climate/_1_pp_point_locations.py --product historical
    python mod_forcing/climate/_1_pp_point_locations.py --product A
    python mod_forcing/climate/_1_pp_point_locations.py --product B
    python mod_forcing/climate/_1_pp_point_locations.py --product LTO
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.csv_io import write_delivery_csv
from utils.paths import DELIVERY, delivery_dir, get_module_generated_dir
from utils.wgen import SETS, nearest_cell, read_met, set_name
from utils.wgen_calendar import monthly, write_chunk_csvs

def calculate_monthly_precip(product, path):
    """Monthly precipitation (inches) of one cell as a labelled table: chunk, year, month,
    precip_inches, and the month's first day as date (single series only)."""
    m = monthly(product, read_met(product, path, usecols=["precip"]), "sum")
    out = pd.DataFrame({"chunk": m["chunk"], "year": m["Year"], "month": m["Month"],
                        "precip_inches": m["precip"] / 25.4})
    if product != "B":
        out["date"] = pd.to_datetime(dict(year=out["year"], month=out["month"], day=1))
    return out


def read_point_locations(csv_file):
    """
    Read the PP point locations from CSV file.

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


def process_location(location_name, target_lat, target_lon, product, output_folder):
    """
    Process a single location: find nearest grid cell, extract monthly precip, and save the
    per-location CSV (single series only; Product B goes to write_product_b_chunks).

    Returns:
    --------
    dict : Summary information about the processing, with the monthly table under
    '_monthly_data'
    """
    print(f"\nProcessing {location_name}...")
    print(f"  Target location: {target_lat}degN, {target_lon}degE")

    nearest_lat, nearest_lon, nearest_file, distance = nearest_cell(product, target_lat, target_lon)
    print(f"  Nearest grid cell: {nearest_lat}degN, {nearest_lon}degE")
    print(f"  Distance: {distance:.4f}deg (~{distance * 111:.2f} km)")

    monthly_precip = calculate_monthly_precip(product, nearest_file)

    if product == "B":
        print(f"  Product B: {len(monthly_precip)} months loaded (will compile into chunks)")
    else:
        output_file = output_folder / f"{location_name}_monthly_precip.csv"
        monthly_precip.drop(columns="chunk").to_csv(output_file, index=False)
        print(f"  Output saved: {output_file.name}")

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
        '_monthly_data': monthly_precip,
    }


def _sv_rows(summaries):
    """The monthly tables of all locations in SV format (Part B = location, Part C = PRECIP),
    with their chunk."""
    return pd.concat([pd.DataFrame({
        'chunk': s['_monthly_data']['chunk'],
        'Part B': s['location_name'],
        'Part C': 'PRECIP',
        'Year': s['_monthly_data']['year'],
        'Month': s['_monthly_data']['month'],
        'Value': s['_monthly_data']['precip_inches'],
    }) for s in summaries], ignore_index=True)


def write_delivery(summaries, output_root, product):
    """The delivery CSV of a single series over DELIVERY_WY (values rounded to 6 decimals)."""
    df = _sv_rows(summaries).drop(columns="chunk")
    df['Value'] = df['Value'].map(lambda v: round(v, 6))
    out = write_delivery_csv(df, delivery_dir(output_root, product), "_pp_precip", product)
    print(f"\n  Delivery CSV: {out.name} ({df['Part B'].nunique()} locations)")


def write_product_b_chunks(summaries, output_folder):
    """The 10 long-format chunk CSVs (Part B, Part C, Year, Month, Value), each labelled
    WY1922-2021 (utils.wgen_calendar)."""
    paths = write_chunk_csvs(_sv_rows(summaries), output_folder, "_pp_precip_productB")
    print(f"\nProduct B chunks: {len(paths)} files in {output_folder}")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Extract monthly precipitation for PP point locations from gridded weather'
    )
    parser.add_argument('--product', choices=SETS, required=True,
                        help='Weather set: historical (WGEN Historical_Unsplit), A, B '
                             '(WGEN scenario 1) or LTO (Historical_Climate_LTO)')
    parser.add_argument(
        '--locations',
        type=str,
        default='reference/pp_point_locations.csv',
        help='CSV file with point locations (default: reference/pp_point_locations.csv)'
    )
    return parser.parse_args()


def main():
    """
    Main function to extract monthly precipitation for all PP point locations.
    """
    args = parse_arguments()
    product = args.product

    script_dir = Path(__file__).parent.resolve()
    gen_dir = get_module_generated_dir("mod_forcing/climate")

    point_locations_file = script_dir / "reference" / Path(args.locations).name
    if not point_locations_file.exists():
        point_locations_file = script_dir / args.locations

    script_output_folder = gen_dir / "output" / "_1_pp_point_locations" / set_name(product)
    script_output_folder.mkdir(parents=True, exist_ok=True)
    print("="*80)
    print("EXTRACTING MONTHLY PRECIPITATION FOR PP POINT LOCATIONS")
    print("="*80)
    print(f"Weather set: {set_name(product)}")
    print(f"Output folder: {script_output_folder}")

    print(f"\nReading point locations from: {point_locations_file}")
    locations_df = read_point_locations(point_locations_file)
    print(f"Found {len(locations_df)} locations to process")

    summaries, failed = [], []
    for idx, row in locations_df.iterrows():
        try:
            summaries.append(process_location(
                location_name=row['location_name'],
                target_lat=row['lat'],
                target_lon=row['lon'],
                product=product,
                output_folder=script_output_folder,
            ))
        except Exception as e:
            print(f"  ERROR processing {row['location_name']}: {str(e)}")
            failed.append(row['location_name'])
    if failed:
        raise SystemExit(f"{len(failed)} location(s) failed, so their SVs would be missing: {failed}")

    if summaries:
        if product == "B":
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
        print(f"  Mean distance to grid cell: {summary_df['distance_km'].mean():.2f} km")
        print(f"  Max distance to grid cell: {summary_df['distance_km'].max():.2f} km")
        print(f"  Average monthly precip (across all locations): {summary_df['mean_monthly_precip_inches'].mean():.2f} inches")
    else:
        print("\nNo locations were successfully processed.")


if __name__ == "__main__":
    main()
