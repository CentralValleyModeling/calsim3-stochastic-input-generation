"""
Postprocess Product A Reservoir Evaporation for CalSim Validation

Creates a combined long-format validation CSV from individual reservoir
evaporation files produced by _2_run_product_a.py.

Output format: Part B, Part C, Year, Month, Value
Output file:   output/_calsim_historical_validation/_reservoir_evaporation_productA_{start_wy}_{end_wy}.csv

Usage:
    python _2_postprocess_for_calsim_validation.py                  # Default WY 1972-2018
    python _2_postprocess_for_calsim_validation.py 1922 2018        # Custom period
"""

import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_gen = get_module_generated_dir("mod_reservoir/evaporation")


def create_validation_csv(
    output_dir=None,
    validation_dir=None,
    start_wy: int = 1972,
    end_wy: int = 2018
):
    """
    Create a combined validation CSV from individual reservoir files.

    Reads processed individual reservoir CSVs and creates a long-format CSV
    with columns Part B, Part C, Year, Month, Value for the validation period.

    Parameters:
    -----------
    output_dir : path-like, optional
        Directory containing individual_reservoirs/ subfolders
    validation_dir : path-like, optional
        Output directory for the validation CSV
    start_wy : int
        Start water year (default: 1972)
    end_wy : int
        End water year (default: 2018)
    """
    if output_dir is None:
        output_dir = _gen / 'output' / '_2_run_reservoir_evap' / 'Product_A'
    if validation_dir is None:
        validation_dir = _gen / 'output' / '_calsim_historical_validation'
    individual_dir = Path(output_dir) / 'individual_reservoirs'
    if not individual_dir.exists():
        print(f"Error: {individual_dir} not found. Run _2_run_product_a.py first.")
        return

    # Validation period: Oct of start_wy through Sep of end_wy
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    print("=" * 80)
    print("Creating Validation CSV")
    print("=" * 80)
    print(f"Period: WY {start_wy}-{end_wy} ({start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')})")
    print(f"Source: {individual_dir}")

    all_rows = []

    # Iterate through region subfolders
    for region_dir in sorted(individual_dir.iterdir()):
        if not region_dir.is_dir():
            continue

        region_name = region_dir.name.replace('_', ' ')
        csv_files = sorted(region_dir.glob('*.csv'))
        print(f"\n  {region_name}: {len(csv_files)} reservoirs")

        for csv_file in csv_files:
            reservoir_code = csv_file.stem

            # Read individual reservoir CSV (index is date, column is evaporation_in)
            df = pd.read_csv(csv_file, index_col=0, parse_dates=True)

            # Filter to validation period
            mask = (df.index >= start_date) & (df.index <= end_date)
            df_filtered = df.loc[mask].copy()

            if len(df_filtered) == 0:
                print(f"    {reservoir_code}: no data in validation period")
                continue

            # Build long-format rows
            part_b = f'ER_{reservoir_code}'
            part_c = 'EVAPORATION-RATE'

            for date, row in df_filtered.iterrows():
                all_rows.append({
                    'Part B': part_b,
                    'Part C': part_c,
                    'Year': date.year,
                    'Month': date.month,
                    'Value': row['evaporation_in']
                })

            print(f"    {reservoir_code}: {len(df_filtered)} months")

    if len(all_rows) == 0:
        print("\nNo data found for validation period.")
        return

    # Create output DataFrame
    result_df = pd.DataFrame(all_rows)
    result_df = result_df.sort_values(['Part B', 'Year', 'Month']).reset_index(drop=True)

    # Save
    val_path = Path(validation_dir)
    val_path.mkdir(parents=True, exist_ok=True)
    output_file = val_path / f'_reservoir_evaporation_productA_{start_wy}_{end_wy}.csv'
    result_df.to_csv(output_file, index=False)

    n_reservoirs = result_df['Part B'].nunique()
    print(f"\n{'=' * 80}")
    print(f"Validation CSV: {output_file}")
    print(f"  {n_reservoirs} reservoirs × {len(result_df)} total rows")
    print(f"  Period: WY {start_wy}-{end_wy}")
    print("=" * 80)


def main():
    """Main entry point."""
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if len(args) >= 2:
        start_wy = int(args[0])
        end_wy = int(args[1])
        print(f"\nCustom period: WY {start_wy}-{end_wy}\n")
        create_validation_csv(start_wy=start_wy, end_wy=end_wy)
    else:
        create_validation_csv()


if __name__ == '__main__':
    main()
