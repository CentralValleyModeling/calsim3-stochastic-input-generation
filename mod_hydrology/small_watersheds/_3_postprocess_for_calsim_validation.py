"""
Postprocess Small Watersheds for CalSim Validation.

Creates a long-format validation CSV from the merged SmallWatersheds postprocess
output (SmallWatersheds_2DSS.csv) using the VIC_Precip (Product A) scenario.
Converts AF to TAF and filters to the specified water-year window.

Output format: Part B, Part C, Year, Month, Value
Output file:   <GENERATED>/mod_hydrology/small_watersheds/output/product_a_historical_validation/
               _smallwatersheds_productA_{start_wy}_{end_wy}.csv

Usage
-----
Default period (WY 1972-2018):
    python _3_postprocess_for_calsim_validation.py

Custom period:
    python _3_postprocess_for_calsim_validation.py 1922 2018
"""

import os
import sys
import pandas as pd
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_GEN_DIR = get_module_generated_dir("mod_hydrology/small_watersheds")


# ── CONSTANTS ───────────────────────────────────────────────────────────
SOURCE_CSV = str(_GEN_DIR / "output" / "_2_postprocess_run" / "SmallWatersheds_2DSS.csv")
VALIDATION_DIR = str(_GEN_DIR / "output" / "product_a_historical_validation")


def create_validation_csv(
    source_csv=None,
    output_dir=None,
    start_wy=1972,
    end_wy=2018
):
    """
    Create validation CSV from SmallWatersheds postprocess output.

    Reads the merged postprocess CSV (SmallWatersheds_2DSS.csv) and filters the
    VIC_Precip (Product A) scenario to the CalSim validation period.  Outputs in
    standard CalSim validation format: Part B, Part C, Year, Month, Value.

    Parameters
    ----------
    source_csv : str, optional
        Path to SmallWatersheds_2DSS.csv.
        Defaults to output/_2_postprocess_run/SmallWatersheds_2DSS.csv
    output_dir : str, optional
        Output directory for validation CSV.
        Defaults to output/product_a_historical_validation
    start_wy : int
        Start water year (default: 1972)
    end_wy : int
        End water year (default: 2018)
    """
    if source_csv is None:
        source_csv = SOURCE_CSV
    if output_dir is None:
        output_dir = VALIDATION_DIR

    os.makedirs(output_dir, exist_ok=True)

    print("=" * 80)
    print("Creating Validation CSV — Small Watersheds")
    print("=" * 80)

    # Read the postprocessed CSV
    if not os.path.exists(source_csv):
        print(f"Error: {source_csv} not found. Run _2_postprocess_run_SmallWatersheds.py first.")
        return

    df = pd.read_csv(source_csv)
    df['Date'] = pd.to_datetime(df['Date'])

    # WY N starts Oct of year N-1 and ends Sep of year N
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date   = pd.Timestamp(end_wy, 9, 30)

    print(f"Period : WY {start_wy}–{end_wy}  "
          f"({start_date.strftime('%b %Y')} – {end_date.strftime('%b %Y')})")
    print(f"Source : {source_csv}")

    # Filter to validation period
    mask = (df['Date'] >= start_date) & (df['Date'] <= end_date)
    df_filtered = df.loc[mask].copy()

    if df_filtered.empty:
        print("No data found in the validation period.")
        return

    # Build validation DataFrame using VIC_Precip (Product A) values
    # SmallWatersheds DSS outputs in AF; CalSim baseline expects TAF → divide by 1000
    val_df = pd.DataFrame({
        'Part B': df_filtered['PartB'].values,
        'Part C': df_filtered['PartC'].values,
        'Year':   df_filtered['Date'].dt.year.values,
        'Month':  df_filtered['Date'].dt.month.values,
        'Value':  df_filtered['VIC_Precip'].values / 1000.0   # AF → TAF
    })

    # Drop rows with NaN values
    val_df = val_df.dropna(subset=['Value'])

    # Sort by Part B, Part C, Year, Month
    val_df = val_df.sort_values(
        by=['Part B', 'Part C', 'Year', 'Month']
    ).reset_index(drop=True)

    # Save
    output_file = os.path.join(
        output_dir, f"_smallwatersheds_productA_{start_wy}_{end_wy}.csv"
    )
    val_df.to_csv(output_file, index=False)

    n_variables = val_df.groupby(['Part B', 'Part C']).ngroups
    print(f"\n  Written   : {output_file}")
    print(f"  Variables : {n_variables}")
    print(f"  Rows      : {len(val_df)}")
    print(f"  Date range: "
          f"{df_filtered['Date'].min().strftime('%Y-%m')} – "
          f"{df_filtered['Date'].max().strftime('%Y-%m')}")
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
