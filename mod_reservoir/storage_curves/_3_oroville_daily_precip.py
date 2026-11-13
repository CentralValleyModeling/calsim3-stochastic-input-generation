"""
Extract Daily Basin-Averaged Precipitation for Oroville / Feather River
======================================================================
Daily basin-average precipitation (inches) for the Oroville/Feather River basin from the daily
weather of one set (``utils.wgen``), each grid cell of CS3_8RI_OROVI_GridInfo.txt weighted by
its area inside the basin.

Historical_Unsplit, Product A and LTO give one series over ``WINDOWS``. Product B gives 10
chunk CSVs of 100 water years each, cut by ``utils.wgen_calendar.chunk_days`` and labelled in
order with the days of WY1922-WY2021.

Inputs
------
- The daily weather of the set (``utils.wgen.read_met``)
- mod_forcing/climate/reference/GridInfo/CS3_8RI_OROVI_GridInfo.txt (override with --grid_info)

Outputs
-------
- <generated>/output/_3_oroville_daily_precip/Oroville_Daily_Precip_<set>.csv, <set> being
  Historical_Unsplit, Product_A or LTO (year, month, day, precip_inches)
- <generated>/output/_3_oroville_daily_precip/oroville_daily_precip_productB_n01.csv ... n10.csv
- <generated>/output/_3_oroville_daily_precip/_compare_ab/comparison_monthly_avg.csv (--compare)

Usage
-----
    python _3_oroville_daily_precip.py --product historical
    python _3_oroville_daily_precip.py --product A
    python _3_oroville_daily_precip.py --product B
    python _3_oroville_daily_precip.py --product LTO
    python _3_oroville_daily_precip.py --compare
    python _3_oroville_daily_precip.py --product B --compare
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir
from utils.wgen import SETS, dates, met_path, set_name, weighted_daily
from utils.wgen_calendar import LABEL_DAYS, N_CHUNKS, chunk_days

_gen = get_module_generated_dir("mod_reservoir/storage_curves")
_ref = Path(__file__).resolve().parents[2] / 'mod_forcing' / 'climate' / 'reference' / 'GridInfo'

#: Days of each single series
WINDOWS = {
    'historical': ('1915-10-01', '2018-09-30'),
    'A': ('1915-10-01', '2018-09-30'),
    'LTO': ('1915-10-01', '2015-09-30'),
}

_MONTH_NAMES = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec',
}


def single_file(product: str) -> str:
    return f'Oroville_Daily_Precip_{set_name(product)}.csv'


def parse_grid_info_file(grid_info_path):
    """The basin's cells: grid_id, lat, lon, cell_area and basin_area (km2; basin_area, the
    part of the cell inside the basin, is its weight)."""
    return pd.read_csv(grid_info_path, sep=r'\s+', header=None,
                       names=['grid_id', 'lat', 'lon', 'cell_area', 'basin_area'])


def basin_daily_precip(grid_info_df, product):
    """Weighted basin-average daily precipitation (inches): Year, Month, Day and precip_inches
    on the rows of the weather files (stamp days for Product B)."""
    print(f"  Processing {len(grid_info_df)} grid cells...")
    daily = weighted_daily(product, [(met_path(product, row.lat, row.lon), row.basin_area)
                                     for row in grid_info_df.itertuples(index=False)], ['precip'])
    return daily[['Year', 'Month', 'Day']].assign(precip_inches=daily['precip'] / 25.4)


def write_single(daily, product, output_dir):
    start, end = WINDOWS[product]
    s = pd.Series(daily['precip_inches'].to_numpy(), index=dates(daily)).reindex(
        pd.date_range(start, end, freq='D'))
    out = pd.DataFrame({'year': s.index.year, 'month': s.index.month, 'day': s.index.day,
                        'precip_inches': s.to_numpy()})
    output_file = output_dir / single_file(product)
    out.to_csv(output_file, index=False)
    print(f"\nSaved: {output_file}")
    print(f"  Days: {start} to {end} ({len(out)})")
    print(f"  Mean daily precip: {out['precip_inches'].mean():.4f} inches")


def write_product_b(daily, output_dir):
    """Each chunk's 36,525 stamp days labelled in order with the days of WY1922-2021."""
    print(f"\nWriting {N_CHUNKS} chunks of 100 water years each (WY1922-WY2021 template)...")
    for k in range(1, N_CHUNKS + 1):
        first, n_days = chunk_days(k)
        assert n_days == len(LABEL_DAYS)
        out = pd.DataFrame({
            'year': LABEL_DAYS.year,
            'month': LABEL_DAYS.month,
            'day': LABEL_DAYS.day,
            'precip_inches': daily['precip_inches'].to_numpy()[first:first + n_days],
        })
        output_file = output_dir / f'oroville_daily_precip_productB_n{k:02d}.csv'
        out.to_csv(output_file, index=False)
        print(f"  Chunk {k:02d}/{N_CHUNKS}: {len(out)} days | WY1922-WY2021 | {output_file.name}")


def compare_product_a_vs_b(output_dir=None):
    """
    Mean daily precipitation (inches/day) by calendar month of the pre-generated Product A
    series and of each Product B chunk, written to _compare_ab/comparison_monthly_avg.csv.
    """
    output_dir = Path(output_dir or _gen / 'output' / '_3_oroville_daily_precip')
    compare_dir = output_dir / '_compare_ab'

    print("\n" + "=" * 70)
    print("Product A vs Product B -- Oroville Daily Precipitation")
    print("=" * 70)

    pa_file = output_dir / single_file('A')
    if not pa_file.exists():
        print(f"Error: {pa_file} not found. Run with --product A first.")
        return
    pa_df = pd.read_csv(pa_file)
    pa_monthly = pa_df.groupby('month')['precip_inches'].mean()
    print(f"Product A: {pa_file.name}  ({len(pa_df)} days)")

    pb_files = [f for f in (output_dir / f'oroville_daily_precip_productB_n{k:02d}.csv'
                            for k in range(1, N_CHUNKS + 1)) if f.exists()]
    if not pb_files:
        print(f"Error: No Product B chunk files found in {output_dir}. Run with --product B first.")
        return
    chunk_dfs = {f.stem.split('_')[-1]: pd.read_csv(f) for f in pb_files}
    chunk_labels = sorted(chunk_dfs)
    print(f"Product B: {len(chunk_labels)} chunks ({', '.join(chunk_labels)})")

    rows = []
    for m in range(1, 13):
        row = {'month': m, 'month_name': _MONTH_NAMES[m],
               'ProductA_mean_in_day': pa_monthly.get(m, np.nan)}
        for lbl, df in chunk_dfs.items():
            row[lbl] = df[df['month'] == m]['precip_inches'].mean()
        rows.append(row)
    table = pd.DataFrame(rows)[['month', 'month_name', 'ProductA_mean_in_day'] + chunk_labels]

    compare_dir.mkdir(parents=True, exist_ok=True)
    out_file = compare_dir / 'comparison_monthly_avg.csv'
    table.to_csv(out_file, index=False)
    print(f"\nSaved: {out_file}")

    chunk_hdr = ''.join(f'  {lbl:>8}' for lbl in chunk_labels)
    hdr = f"  {'Month':<5}  {'Product A':>12}{chunk_hdr}"
    sep = "  " + "-" * (len(hdr) - 2)
    print("\nMean daily precip by calendar month (inches/day):")
    print(hdr)
    print(sep)
    for _, row in table.iterrows():
        chunk_vals = ''.join(f"  {row[lbl]:>8.4f}" for lbl in chunk_labels)
        print(f"  {row['month_name']:<5}  {row['ProductA_mean_in_day']:>12.4f}{chunk_vals}")


def parse_arguments():
    parser = argparse.ArgumentParser(description='Extract daily basin-averaged precipitation for Oroville basin')
    parser.add_argument('--product', choices=SETS, default=None,
                        help='Weather set: historical (Historical_Unsplit), A, B or LTO '
                             '(Historical_Climate_LTO)')
    parser.add_argument('--compare', action='store_true',
                        help='Compare monthly averages between pre-generated Product A and Product B outputs')
    parser.add_argument('--grid_info', type=str, default=None,
                        help='Path to grid info file (default: reference/CS3_8RI_OROVI_GridInfo.txt)')
    args = parser.parse_args()
    if not args.product and not args.compare:
        parser.error("use --product and/or --compare")
    return args


def main():
    args = parse_arguments()
    output_dir = _gen / 'output' / '_3_oroville_daily_precip'
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.compare:
        compare_product_a_vs_b(output_dir=output_dir)
    if not args.product:
        return

    grid_info_path = Path(args.grid_info) if args.grid_info else _ref / 'CS3_8RI_OROVI_GridInfo.txt'
    if not grid_info_path.exists():
        raise FileNotFoundError(f"Grid info file not found: {grid_info_path}")

    print("Processing Oroville basin daily precipitation")
    print(f"  Weather set: {set_name(args.product)}")
    print(f"  Grid info: {grid_info_path}")
    print(f"  Output folder: {output_dir}")
    grid_info_df = parse_grid_info_file(grid_info_path)
    print(f"  Found {len(grid_info_df)} grid cells, basin area {grid_info_df['basin_area'].sum():.1f} km2")

    daily = basin_daily_precip(grid_info_df, args.product)
    if args.product == 'B':
        write_product_b(daily, output_dir)
    else:
        write_single(daily, args.product, output_dir)


if __name__ == "__main__":
    main()
