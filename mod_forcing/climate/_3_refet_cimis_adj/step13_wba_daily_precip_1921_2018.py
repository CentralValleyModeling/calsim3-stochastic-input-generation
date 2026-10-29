# -*- coding: utf-8 -*-
"""
Step 13: Daily Precipitation per WBA, SR and SW for 1921-2018
=============================================================
Project : Reference ETo for CalSim3 using Historical_Unsplit weather data
Author  : DWR
Date    : 2026

PURPOSE
-------
Builds the daily precipitation table that PyCUP reads in Step 14 from the same
Historical_Unsplit weather and Step 0 grid weights as the ETo of Steps 10-12:

    P_poly(d) = sum_k(percent[k] * P_k(d)) / sum_k(percent[k])

where P_k is the daily precipitation of grid cell k. Dividing by the weight
sum keeps the result a mean where part of a polygon lies outside the grid.

INPUTS
------
  1. Historical_Unsplit directory: BASE/WGEN/Historical_Unsplit/data_{lat}_{lon}
     Columns: Year Month Day Precip(mm) Tmax(C) Tmin(C)
  2. Step 0 weights: GENERATED/.../_3_refet_cimis_adj/step0/WTable_*.csv

OUTPUT (written to GENERATED/.../_3_refet_cimis_adj/step13/)
------------------------------------------------------------
  Historical_Unsplit_precip_daily_1921_2018.csv
    Date (01JAN1921 ... 31DEC2018), then one column per polygon named as in
    the Step 12 ETo tables (WBA_02, ..., WBA_SR_1, ..., WBA_SW_1, ...)
    units: inches/day
"""

import pathlib
import sys

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

# =============================================================================
# CONFIGURATION
# =============================================================================
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")

GRID_DATA_DIR = base_dir / "WGEN" / "Historical_Unsplit"
WTABLE_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step0"
OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step13"
OUTPUT_CSV = OUTPUT_DIR / "Historical_Unsplit_precip_daily_1921_2018.csv"

START_DATE = "1921-01-01"
END_DATE = "2018-12-31"
MM_PER_INCH = 25.4

# =============================================================================


def polygon_sort_key(poly_id):
    """WBAs first, then SR and SW in numeric order."""
    for group, prefix in enumerate(("SR_", "SW_"), start=1):
        if poly_id.startswith(prefix):
            return (group, int(poly_id[len(prefix):]), poly_id)
    return (0, 0, poly_id)


def load_weights():
    """Step 0 weight tables keyed by polygon ID (WTable_{id}.csv)."""
    weights = {}
    for path in WTABLE_DIR.glob("WTable_*.csv"):
        table = pd.read_csv(path, skiprows=2)
        table.columns = ["Lon", "Lat", "pct_k"]
        weights[path.stem[len("WTable_"):]] = table
    if not weights:
        raise FileNotFoundError(f"No WTable_*.csv in {WTABLE_DIR}. Run Step 0 first.")
    return {poly_id: weights[poly_id] for poly_id in sorted(weights, key=polygon_sort_key)}


def read_cell_precip(path, dates):
    """Daily precipitation of one grid cell in inches, on the given dates."""
    met = pd.read_csv(path, sep=r"\s+", header=None, usecols=[0, 1, 2, 3],
                      names=["year", "month", "day", "precip"])
    met.index = pd.to_datetime(met[["year", "month", "day"]])
    precip = met["precip"].reindex(dates).to_numpy() / MM_PER_INCH
    if np.isnan(precip).any():
        raise ValueError(f"{path.name} does not cover {START_DATE} to {END_DATE}")
    return precip


def main():
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    weights = load_weights()
    poly_ids = list(weights)

    # Each grid cell is read once and added to every polygon it overlaps.
    cell_polys = {}
    for i, poly_id in enumerate(poly_ids):
        for lon, lat, pct in weights[poly_id].itertuples(index=False):
            cell_polys.setdefault((round(lat, 5), round(lon, 5)), []).append((i, pct))
    print(f"Polygons: {len(poly_ids)}  Grid cells: {len(cell_polys):,}")

    totals = np.zeros((len(poly_ids), len(dates)))
    for n, ((lat, lon), members) in enumerate(sorted(cell_polys.items()), start=1):
        path = GRID_DATA_DIR / f"data_{lat:.5f}_{lon:.5f}"
        if not path.is_file():
            raise FileNotFoundError(f"Grid cell weighted in Step 0 has no weather file: {path}")
        precip = read_cell_precip(path, dates)
        for i, pct in members:
            totals[i] += pct * precip
        if n % 250 == 0:
            print(f"  Cells read: {n:,}/{len(cell_polys):,}")

    weight_sums = np.array([weights[poly_id]["pct_k"].sum() for poly_id in poly_ids])
    table = pd.DataFrame((totals / weight_sums[:, None]).T,
                         columns=[f"WBA_{poly_id}" for poly_id in poly_ids])
    table.insert(0, "Date", dates.strftime("%d%b%Y").str.upper())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT_CSV, index=False, float_format="%.6f")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
