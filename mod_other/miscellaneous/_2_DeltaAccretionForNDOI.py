"""
Delta Accretion for NDOI - Direct Calculation from Daily Precipitation
======================================================================
DELTAACCRETIONFORNDOI/FLOW (TAF) for CalSim 3.0 from the monthly precipitation of one weather set
at the grid cell nearest Stockton Fire Station 4 (CNRFC SCKC1, 38.00 N, 121.32 W).

Formula (column J of the "Direct Calculation" tab of
<generated>/mod_other/miscellaneous/term_development/DELTAACCRETIONFORNDOI/
Reconstructed_DeltaAccretionForNDOI_Directly.xlsx):

    TAF = (precip_in / 12) * DELTA_AREA * (DELTA_AREA / watershed_area) / 1000
    precip_in = precip_mm * 0.0393701, DELTA_AREA = 679,699 acres

Watershed area, Historical_Unsplit and Product A: 682,230 acres to WY1955, 738,000 acres
WY1956-1980, 682,230 acres from WY1981. Product B: 682,230 acres throughout.

Inputs
------
- WGEN daily precipitation of the --product set at the nearest cell (utils.wgen.nearest_cell,
  read_met), summed by month (Product B by stamp month, labelled by chunk)

Outputs
-------
Under <generated>/mod_other/miscellaneous/output/:
- _historical_unsplit_validation/_deltaaccretionforndoi_historicalUnsplit_1922_2018.csv
- _product_a_validation/_deltaaccretionforndoi_productA_1922_2018.csv
- _product_b_final/_deltaaccretionforndoi_productB_1922_2021_qmo_n01.csv ... _n10.csv

Delivery and chunk CSVs: Part B, Part C, Year, Month, Value.

Dependencies
------------
utils.paths, utils.csv_io, utils.wgen, utils.wgen_calendar

Usage
-----
    python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product historical
    python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product A
    python mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py --product B
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.csv_io import write_delivery_csv
from utils.paths import WEATHER_SETS, delivery_dir, get_module_generated_dir
from utils.wgen import nearest_cell, read_met
from utils.wgen_calendar import monthly, write_chunk_csvs

# -- Constants ----------------------------------------------------------------
TARGET_LAT   = 38.00      # Stockton Fire Station No. 4 latitude (degN)
TARGET_LON   = -121.32    # Stockton Fire Station No. 4 longitude (degW, negative)

PART_B       = 'DELTAACCRETIONFORNDOI'
PART_C       = 'FLOW'

DELTA_AREA   = 679_699    # Delta Service Area (acres)
MM_TO_IN     = 0.0393701  # mm -> inches

# Watershed area by water year (single series)
AREA_PRE1955   = 682_230  # WY1955 and earlier
AREA_1955_1980 = 738_000  # WY1956 - WY1980
AREA_POST1980  = 682_230  # WY1981 onwards

# Product B fixed area
AREA_PRODUCT_B = 682_230

_GEN_DIR = get_module_generated_dir("mod_other/miscellaneous")
OUTPUT_B_DIR = _GEN_DIR / "output" / "_product_b_final"


def taf(precip_mm: np.ndarray, wy: np.ndarray, product: str) -> np.ndarray:
    """Monthly precipitation (mm) to TAF with the spreadsheet formula."""
    precip_in = precip_mm * MM_TO_IN
    if product == 'B':
        area = np.full(len(precip_in), AREA_PRODUCT_B, dtype=float)
    else:
        area = np.where(wy <= 1955, AREA_PRE1955,
                        np.where(wy <= 1980, AREA_1955_1980, AREA_POST1980)).astype(float)
    return (precip_in / 12) * DELTA_AREA * (DELTA_AREA / area) / 1000


def main():
    parser = argparse.ArgumentParser(description='Calculate DELTAACCRETIONFORNDOI from daily precipitation.')
    parser.add_argument('--product', choices=list(WEATHER_SETS), required=True,
                        help='Weather set: historical (Historical_Unsplit), A or B')
    product = parser.parse_args().product

    print('\n' + '=' * 72)
    print(WEATHER_SETS[product]['name'])
    print('=' * 72)
    lat, lon, path, dist = nearest_cell(product, TARGET_LAT, TARGET_LON)
    print(f'  Nearest grid cell: {path.name}  (distance = {dist:.5f} deg)')
    m = monthly(product, read_met(product, path, usecols=['precip']), 'sum')
    m['Value'] = taf(m['precip'].to_numpy(), m['WY'].to_numpy(), product)
    m = m.assign(**{'Part B': PART_B, 'Part C': PART_C})
    print(f'  Monthly totals: {len(m)} months')

    if product == 'B':
        paths = write_chunk_csvs(m, OUTPUT_B_DIR, '_deltaaccretionforndoi_productB_1922_2021_qmo')
        print(f'  Wrote {len(paths)} chunks to {OUTPUT_B_DIR}')
    else:
        out = write_delivery_csv(m[['Part B', 'Part C', 'Year', 'Month', 'Value']],
                                 delivery_dir(_GEN_DIR / 'output', product), '_deltaaccretionforndoi', product)
        print(f'  Wrote: {out.name}')
    v = m['Value']
    print(f'  Value range: [{v.min():.3f}, {v.max():.3f}] TAF  (mean {v.mean():.3f} TAF)')

    print('\n' + '=' * 72)
    print('Done.')
    print('=' * 72)


if __name__ == '__main__':
    main()
