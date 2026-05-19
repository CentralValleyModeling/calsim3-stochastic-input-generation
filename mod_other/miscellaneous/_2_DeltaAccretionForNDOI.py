# -*- coding: utf-8 -*-
"""
Delta Accretion for NDOI - Direct Calculation from WGEN Precipitation
=====================================================================
Calculates the Delta precipitation accretion term (DELTAACCRETIONFORNDOI) for
CalSim 3.0 using WGEN precipitation for the grid cell nearest to:

    Station: STOCKTON FIRE STA 4  (CNRFC ID: SCKC1)
    Latitude: 38.00degN, Longitude: 121.32degW

Formula (replicates "Direct Calculation" tab of
    ./data/GENERATED/mod_other/miscellaneous/term_development/DELTAACCRETIONFORNDOI/
    Reconstructed_DeltaAccretionForNDOI_Directly.xlsx, column J):

    TAF = (precip_in / 12) * DELTA_AREA * (DELTA_AREA / watershed_area) / 1000

    where  precip_in = precip_mm * 0.0393701

Product A - time-period based watershed area adjustments:
    Before Oct 1, 1955  -> watershed_area = 682,230 acres
    Oct 1955 - Sep 1980 -> watershed_area = 738,000 acres
    Oct 1980 onwards    -> watershed_area = 682,230 acres

Product B - fixed area ratio (final period):
    Always              -> watershed_area = 682,230 acres

Outputs
-------
    output/_product_a_validation/
        _deltaaccretionforndoi_productA_1922_2018.csv

    output/_product_b_final/
        _deltaaccretionforndoi_productB_1922_2021_qmo_n01.csv
        ...
        _deltaaccretionforndoi_productB_1922_2021_qmo_n10.csv

CSV format: Part B, Part C, Year, Month, Value

Usage
-----
    python _2_DeltaAccretionForNDOI.py                  # run both (default)
    python _2_DeltaAccretionForNDOI.py --product A      # Product A only
    python _2_DeltaAccretionForNDOI.py --product B      # Product B only
    python _2_DeltaAccretionForNDOI.py --product both   # both (explicit)
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

# -- Constants ----------------------------------------------------------------
TARGET_LAT   = 38.00      # Stockton Fire Station No. 4 latitude (degN)
TARGET_LON   = -121.32    # Stockton Fire Station No. 4 longitude (degW, negative)

PART_B       = 'DELTAACCRETIONFORNDOI'
PART_C       = 'FLOW'

DELTA_AREA   = 679_699    # Delta Service Area (acres)
MM_TO_IN     = 0.0393701  # mm -> inches

# Watershed area by period (Product A)
AREA_PRE1955   = 682_230  # Oct 1930 - Sep 1955
AREA_1955_1980 = 738_000  # Oct 1955 - Sep 1980
AREA_POST1980  = 682_230  # Oct 1980 onwards

# Product B fixed area
AREA_PRODUCT_B = 682_230

# -- Directories ---------------------------------------------------------------
_GEN_DIR     = get_module_generated_dir("mod_other/miscellaneous")
WGEN_A_DIR   = get_base_dir() / "WGEN" / "Product_A" / "1"
WGEN_B_DIR   = get_base_dir() / "WGEN" / "Product_B" / "1"
OUTPUT_A_DIR = _GEN_DIR / "output" / "_product_a_validation"
OUTPUT_B_DIR = _GEN_DIR / "output" / "_product_b_final"

# -- Helpers -------------------------------------------------------------------

def find_nearest_wgen_file(wgen_dir: str, target_lat: float, target_lon: float) -> str:
    """Return the path to the nearest WGEN meteo file to (target_lat, target_lon)."""
    files = [f for f in os.listdir(wgen_dir) if f.startswith('meteo_')]
    if not files:
        raise FileNotFoundError(f'No WGEN meteo files found in: {wgen_dir}')

    best_file, best_dist = None, float('inf')
    for fname in files:
        parts = fname.split('_')
        try:
            lat = float(parts[1])
            lon = float(parts[2])
        except (IndexError, ValueError):
            continue
        dist = (lat - target_lat) ** 2 + (lon - target_lon) ** 2
        if dist < best_dist:
            best_dist, best_file = dist, fname

    print(f'  Nearest grid cell: {best_file}  (distance = {best_dist**0.5:.5f} deg)')
    return os.path.join(wgen_dir, best_file)


def read_wgen_daily(filepath: str) -> pd.DataFrame:
    """Read a WGEN meteo file (whitespace-separated, no header).

    Columns returned: year, month, day, pr [mm/day], tmax, tmin
    """
    return pd.read_csv(
        filepath,
        sep=r'\s+', engine='python', header=None,
        names=['year', 'month', 'day', 'pr', 'tmax', 'tmin'],
    )


def calc_taf_vectorized(precip_mm_series: np.ndarray,
                        dates: pd.DatetimeIndex,
                        product_b: bool = False) -> np.ndarray:
    """Convert monthly precipitation (mm) to TAF using the spreadsheet formula.

    Product B uses a fixed area; Product A uses time-period based areas.
    """
    precip_in = precip_mm_series * MM_TO_IN

    if product_b:
        area = np.full(len(precip_in), AREA_PRODUCT_B, dtype=float)
    else:
        cutoff_1955 = pd.Timestamp('1955-10-01')
        cutoff_1980 = pd.Timestamp('1980-10-01')
        area = np.where(
            dates < cutoff_1955, AREA_PRE1955,
            np.where(dates < cutoff_1980, AREA_1955_1980, AREA_POST1980)
        ).astype(float)

    return (precip_in / 12) * DELTA_AREA * (DELTA_AREA / area) / 1000


def write_sv_csv(df: pd.DataFrame, filepath: str) -> None:
    """Write a standard CalSim SV CSV (Part B, Part C, Year, Month, Value)."""
    df.to_csv(filepath, index=False)
    print(f'  Wrote: {os.path.basename(filepath)}')
    print(f'  Rows : {len(df)}  |  Value range: '
          f'[{df["Value"].min():.3f}, {df["Value"].max():.3f}] TAF  '
          f'(mean {df["Value"].mean():.3f} TAF)')


def run_product_a():
    """Process Product A: WGEN 1915-2018, time-period area adjustments."""
    os.makedirs(OUTPUT_A_DIR, exist_ok=True)

    # -- PRODUCT A --------------------------------------------------------------
    print('\n' + '=' * 72)
    print('PRODUCT A')
    print('=' * 72)

    # --- Find and read nearest WGEN file ----------------------------------------
    wgen_a_path = find_nearest_wgen_file(WGEN_A_DIR, TARGET_LAT, TARGET_LON)
    print(f'  Reading: {os.path.basename(wgen_a_path)}')
    df_a = read_wgen_daily(wgen_a_path)
    print(f'  Daily rows : {len(df_a):,}')
    print(f'  Date range : {int(df_a["year"].iloc[0])}-{int(df_a["month"].iloc[0]):02d}'
          f' to {int(df_a["year"].iloc[-1])}-{int(df_a["month"].iloc[-1]):02d}')

    # --- Aggregate daily -> monthly mm ---------------------------------------
    dates_a = pd.to_datetime(dict(
        year=df_a['year'].astype(int),
        month=df_a['month'].astype(int),
        day=df_a['day'].astype(int),
    ))
    ts_a = pd.Series(df_a['pr'].values, index=dates_a)
    monthly_a = ts_a.resample('M').sum()
    print(f'  Monthly totals: {len(monthly_a)} months')

    # --- Apply formula -------------------------------------------------------
    taf_a = calc_taf_vectorized(monthly_a.values, monthly_a.index, product_b=False)
    taf_a = pd.Series(taf_a, index=monthly_a.index)

    # --- Filter to WY 1922-2018 (Oct 1921 - Sep 2018) -----------------------
    mask_a = (taf_a.index >= pd.Timestamp('1921-10-01')) & \
             (taf_a.index <= pd.Timestamp('2018-09-30'))
    taf_a = taf_a.loc[mask_a]
    print(f'  After WY 1922-2018 filter: {len(taf_a)} months (expect {97*12})')

    # --- Output --------------------------------------------------------------
    out_a = pd.DataFrame({
        'Part B': PART_B,
        'Part C': PART_C,
        'Year':   taf_a.index.year,
        'Month':  taf_a.index.month,
        'Value':  taf_a.values,
    })
    write_sv_csv(out_a, os.path.join(OUTPUT_A_DIR, '_deltaaccretionforndoi_productA_1922_2018.csv'))


def run_product_b():
    """Process Product B: WGEN 1000-year stochastic, fixed area ratio."""
    os.makedirs(OUTPUT_B_DIR, exist_ok=True)

    print('\n' + '=' * 72)
    print('PRODUCT B')
    print('=' * 72)

    # --- Find and read nearest WGEN file ----------------------------------------
    wgen_b_path = find_nearest_wgen_file(WGEN_B_DIR, TARGET_LAT, TARGET_LON)
    print(f'  Reading: {os.path.basename(wgen_b_path)}')
    df_b = read_wgen_daily(wgen_b_path)
    print(f'  Daily rows : {len(df_b):,}')
    print(f'  Year range : {int(df_b["year"].iloc[0])} to {int(df_b["year"].iloc[-1])} (synthetic)')

    # --- Aggregate daily -> monthly mm ------------------------------------------
    # Product B uses sequential synthetic years (1, 2, ..., ~1008).
    # Group by (year, month) directly -- avoids Timestamp overflow for large years.
    print('  Aggregating daily -> monthly...')
    df_b['_ym'] = df_b['year'].astype(int) * 100 + df_b['month'].astype(int)
    monthly_b_mm = df_b.groupby('_ym', sort=True)['pr'].sum()
    print(f'  Monthly totals: {len(monthly_b_mm)} months')

    # --- Apply formula (fixed area, Product B) ----------------------------------
    taf_b_vals = calc_taf_vectorized(
        monthly_b_mm.values,
        dates=None,       # not used when product_b=True
        product_b=True,
    )
    # Plain integer-indexed Series for chunking
    monthly_b = pd.Series(taf_b_vals)

    # --- Chunk into 10 x 100 water years ----------------------------------------
    MONTHS_PER_CHUNK = 100 * 12   # 1200
    TOTAL_CHUNKS     = 10
    SKIP_MONTHS      = 9          # skip Jan-Sep of synthetic year 1 (align to Oct)
    TOTAL_NEEDED     = SKIP_MONTHS + MONTHS_PER_CHUNK * TOTAL_CHUNKS  # 12009

    if len(monthly_b) < TOTAL_NEEDED:
        raise ValueError(
            f'Product B has {len(monthly_b)} months; need >= {TOTAL_NEEDED}.'
        )

    aligned_b = monthly_b.iloc[SKIP_MONTHS:].values

    # Build WY date template: WY 1922-2021  (Oct 1921 - Sep 2021), 1200 rows
    wy_years, wy_months = [], []
    for wy in range(1922, 2022):           # WY 1922 ... WY 2021
        for m in [10, 11, 12]:            # Oct-Dec of prior calendar year
            wy_years.append(wy - 1)
            wy_months.append(m)
        for m in range(1, 10):            # Jan-Sep of WY calendar year
            wy_years.append(wy)
            wy_months.append(m)
    wy_years  = np.array(wy_years)
    wy_months = np.array(wy_months)

    print(f'  Writing {TOTAL_CHUNKS} chunks x {MONTHS_PER_CHUNK // 12} water years...')
    base_name = '_deltaaccretionforndoi_productB_1922_2021'

    for i in range(TOTAL_CHUNKS):
        start    = i * MONTHS_PER_CHUNK
        end      = start + MONTHS_PER_CHUNK
        chunk_df = pd.DataFrame({
            'Part B': PART_B,
            'Part C': PART_C,
            'Year':   wy_years,
            'Month':  wy_months,
            'Value':  aligned_b[start:end],
        })
        fname = f'{base_name}_qmo_n{i + 1:02d}.csv'
        fpath = os.path.join(OUTPUT_B_DIR, fname)
        chunk_df.to_csv(fpath, index=False)
        print(f'    Chunk {i + 1:02d}/10 -> {fname}')

    print('\nProduct B stats:')
    print(f'  Value range: [{aligned_b[:MONTHS_PER_CHUNK * TOTAL_CHUNKS].min():.3f}, '
          f'{aligned_b[:MONTHS_PER_CHUNK * TOTAL_CHUNKS].max():.3f}] TAF  '
          f'(mean {aligned_b[:MONTHS_PER_CHUNK * TOTAL_CHUNKS].mean():.3f} TAF)')


# -------------------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------------------
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Calculate DELTAACCRETIONFORNDOI from WGEN precipitation.'
    )
    parser.add_argument(
        '--product', choices=['A', 'B', 'both'], default='both',
        help='Which product to run: A, B, or both (default: both)'
    )
    args = parser.parse_args()

    if args.product in ('A', 'both'):
        run_product_a()
    if args.product in ('B', 'both'):
        run_product_b()

    print('\n' + '=' * 72)
    print('Done.')
    print('=' * 72)
