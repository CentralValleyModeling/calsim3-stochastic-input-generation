"""
Postprocess Climate Outputs for CalSim Historical Validation
============================================================
Compiles Product A outputs from PP point locations and UHH basin averages
into long-format validation CSVs consumed by _99_SV_Compile.

Inputs
------
- output/_1_pp_point_locations/product_a/1/*_monthly_precip.csv
- output/_2_uhh_basin_averages/product_a/1/PPT_*.csv, T*.csv, VPD*.csv

Outputs
-------
- output/_calsim_historical_validation/_pp_precip_productA_{start_wy}_{end_wy}.csv
- output/_calsim_historical_validation/_uhh_precip_productA_{start_wy}_{end_wy}.csv
- output/_calsim_historical_validation/_uhh_temperature_productA_{start_wy}_{end_wy}.csv
- output/_calsim_historical_validation/_uhh_vpd_productA_{start_wy}_{end_wy}.csv

Usage
-----
    cd mod_forcing/climate && python _3_postprocess_all_for_calsim_validation.py
    cd mod_forcing/climate && python _3_postprocess_all_for_calsim_validation.py 1922 2018
"""

import sys
import pandas as pd
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import get_module_generated_dir

# ── CONSTANTS ───────────────────────────────────────────────────────────
_GEN_DIR = get_module_generated_dir("mod_climate")
VALIDATION_DIR = _GEN_DIR / 'output' / '_calsim_historical_validation'
PP_SOURCE_DIR = _GEN_DIR / 'output' / '_1_pp_point_locations' / 'product_a' / '1'
UHH_SOURCE_DIR = _GEN_DIR / 'output' / '_2_uhh_basin_averages' / 'product_a' / '1'


def create_pp_validation_csv(
    source_dir: Path = PP_SOURCE_DIR,
    validation_dir: Path = VALIDATION_DIR,
    start_wy: int = 1972,
    end_wy: int = 2018
):
    """
    Create a combined validation CSV from individual PP point location files.

    Reads processed individual location CSVs and creates a long-format CSV
    with columns Part B, Part C, Year, Month, Value for the validation period.

    Parameters:
    -----------
    source_dir : Path
        Directory containing individual *_monthly_precip.csv files
    validation_dir : Path
        Output directory for the validation CSV
    start_wy : int
        Start water year (default: 1972)
    end_wy : int
        End water year (default: 2018)
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"Error: {source_path} not found. Run _1_pp_point_locations.py first.")
        return

    # Validation period: Oct of start_wy through Sep of end_wy
    start_date = pd.Timestamp(start_wy-1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    print("=" * 80)
    print("Creating Validation CSV — PP Point Locations")
    print("=" * 80)
    print(f"Period: WY {start_wy}-{end_wy} ({start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')})")
    print(f"Source: {source_path}")

    all_rows = []
    csv_files = sorted(source_path.glob('*_monthly_precip.csv'))
    print(f"Found {len(csv_files)} location files")

    for csv_file in csv_files:
        location_name = csv_file.stem.replace('_monthly_precip', '')

        # Read individual location CSV (columns: year, month, precip_inches, date)
        df = pd.read_csv(csv_file)
        df['date'] = pd.to_datetime(df['date'])

        # Filter to validation period
        mask = (df['date'] >= start_date) & (df['date'] <= end_date)
        df_filtered = df.loc[mask].copy()

        if df_filtered.empty:
            print(f"  {location_name}: no data in validation period, skipping")
            continue

        # Build long-format rows: Part B, Part C, Year, Month, Value
        for _, row in df_filtered.iterrows():
            all_rows.append({
                'Part B': location_name,
                'Part C': 'PRECIP',
                'Year': int(row['year']),
                'Month': int(row['month']),
                'Value': round(row['precip_inches'], 6)
            })

        print(f"  {location_name}: {len(df_filtered)} months")

    if not all_rows:
        print("\nNo data found for the validation period.")
        return

    # Write combined CSV
    val_path = Path(validation_dir)
    val_path.mkdir(parents=True, exist_ok=True)

    output_df = pd.DataFrame(all_rows)
    output_file = val_path / f"_pp_precip_productA_{start_wy}_{end_wy}.csv"
    output_df.to_csv(output_file, index=False)

    n_locations = output_df['Part B'].nunique()
    print(f"\n  Written: {output_file} ({n_locations} locations, {len(output_df)} rows)")


def create_uhh_validation_csv(
    source_dir: Path = UHH_SOURCE_DIR,
    validation_dir: Path = VALIDATION_DIR,
    start_wy: int = 1972,
    end_wy: int = 2018
):
    """
    Create combined validation CSVs from individual UHH basin average files.

    Reads processed PPT, T, and VPD CSVs and creates long-format CSVs
    with columns Part B, Part C, Year, Month, Value for the validation period.

    Parameters:
    -----------
    source_dir : Path
        Directory containing individual PPT_*, T*, VPD* CSV files
    validation_dir : Path
        Output directory for the validation CSVs
    start_wy : int
        Start water year (default: 1972)
    end_wy : int
        End water year (default: 2018)
    """
    source_path = Path(source_dir)
    if not source_path.exists():
        print(f"Error: {source_path} not found. Run _2_uhh_basin_averages.py first.")
        return

    # Validation period: Oct of start_wy through Sep of end_wy
    start_date = pd.Timestamp(start_wy-1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    print("\n" + "=" * 80)
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
            # Temperature files: T*_UHH.csv but NOT PPT_ or VPD prefixed
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


def main():
    """Main entry point — runs both PP and UHH validation."""
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    start_wy = int(args[0]) if len(args) >= 1 else 1972
    end_wy = int(args[1]) if len(args) >= 2 else 2018

    if len(args) >= 1:
        print(f"\nCustom period: WY {start_wy}-{end_wy}\n")

    create_pp_validation_csv(start_wy=start_wy, end_wy=end_wy)
    create_uhh_validation_csv(start_wy=start_wy, end_wy=end_wy)

    print(f"\n{'=' * 80}")
    print("All validation CSVs complete.")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
