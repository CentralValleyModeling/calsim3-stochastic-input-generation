# -*- coding: utf-8 -*-
"""
Step 13: Daily Precipitation per WBA, SR and SW for 1920-2018
=============================================================
Project : Reference ETo for CalSim3 using Product_A weather data
Author  : DWR
Date    : 2026

PURPOSE
-------
Builds the daily precipitation table that PyCUP reads in Step 14 from the same
Product_A weather and Step 0 grid weights as the ETo of Steps 10-12:

    P_poly(d) = sum_k(percent[k] * P_k(d)) / sum_k(percent[k])

where P_k is the daily precipitation of grid cell k. Dividing by the weight
sum keeps the result a mean where part of a polygon lies outside the grid.

INPUTS
------
  1. Product_A directory: BASE/WGEN/Product_A/1/meteo_{lat}_{lon}
     Columns: Year Month Day Precip(mm) Tmax(C) Tmin(C)
  2. Step 0 weights: GENERATED/.../_3_refet_cimis_adj/step0/WTable_*.csv

OUTPUT (written to GENERATED/.../_3_refet_cimis_adj/step13/)
------------------------------------------------------------
  Product_A_precip_daily_1921_2018.csv
    Date (01JAN1920 ... 31DEC2018), then one column per polygon named as in
    the Step 12 ETo tables (WBA_02, ..., WBA_SR_1, ..., WBA_SW_1, ...)
    units: inches/day. The filename is retained for Step 14 compatibility.
  CS3_DailyPrecipitation2022.dss
    Daily 1DAY PER-CUM precipitation in IN/DAY for all WBA records in the
    reference DSS, from 01JAN1920 through 31DEC2018.
"""

import pathlib
import sys

import numpy as np
import pandas as pd
from pydsstools.core import TimeSeriesContainer

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils import dss_io
from utils.paths import get_base_dir, get_module_generated_dir

# =============================================================================
# CONFIGURATION
# =============================================================================
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")

GRID_DATA_DIR = base_dir / "WGEN" / "Product_A" / "1"
WTABLE_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step0"
OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step13"
OUTPUT_CSV = OUTPUT_DIR / "Product_A_precip_daily_1921_2018.csv"
OUTPUT_DSS = OUTPUT_DIR / "CS3_DailyPrecipitation2022.dss"
REFERENCE_DSS = (
    base_dir / "CalSim3" / "CSHydro_Existing"
    / "inputDSS" / "CS3_DailyPrecipitation2022.dss"
)

START_DATE = "1920-01-01"
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


def write_daily_precipitation_dss(csv_path, reference_dss_path, output_dss_path):
    """Write annual WBA daily precipitation records using the reference DSS paths."""
    table = pd.read_csv(csv_path)
    if "Date" not in table.columns:
        raise ValueError(f"Precipitation CSV has no Date column: {csv_path}")

    dates = pd.DatetimeIndex(pd.to_datetime(table["Date"], format="%d%b%Y"))
    expected_dates = pd.date_range(START_DATE, END_DATE, freq="D")
    if not dates.equals(expected_dates):
        raise ValueError(
            f"Precipitation CSV dates must exactly cover {START_DATE} through "
            f"{END_DATE}; got {len(dates)} rows."
        )

    if not reference_dss_path.is_file():
        raise FileNotFoundError(f"Reference precipitation DSS not found: {reference_dss_path}")
    with dss_io.open_dss(reference_dss_path, catalog_flag=False) as reference:
        reference_paths = reference.getPathnameList(
            "/*/*/PRECIP/01JAN1920/1DAY/PRECIPITATION/"
        ) or []
    reference_path_by_header = {}
    for pathname in reference_paths:
        parts = pathname.strip("/").split("/")
        if len(parts) != 6 or not parts[1].startswith("WBA"):
            continue
        reference_path_by_header[f"WBA_{parts[1][3:]}"] = pathname

    if "WBA_DETAW" in table.columns:
        template_parts = next(iter(reference_path_by_header.values())).strip("/").split("/")
        template_parts[1] = "WBADETAW"
        reference_path_by_header["WBA_DETAW"] = "/" + "/".join(template_parts) + "/"

    csv_wba_headers = {
        column for column in table.columns
        if column.startswith("WBA_")
        and not column.startswith(("WBA_SR_", "WBA_SW_"))
    }
    missing_headers = sorted(set(reference_path_by_header) - csv_wba_headers)
    extra_headers = sorted(csv_wba_headers - set(reference_path_by_header))
    if missing_headers or extra_headers:
        raise ValueError(
            "Precipitation CSV and reference DSS WBA sets differ; "
            f"missing={missing_headers}, extra={extra_headers}."
        )

    values = table[sorted(reference_path_by_header)].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(values.to_numpy(dtype=float)).all():
        raise ValueError("Precipitation CSV contains missing or nonnumeric WBA values.")

    output_dss_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".dss", ".dsc", ".dsd"):
        existing_file = output_dss_path.with_suffix(suffix)
        if existing_file.exists():
            existing_file.unlink()

    expected_pathnames = []
    with dss_io.open_dss(output_dss_path, version=6, catalog_flag=False) as output:
        for header, reference_path in reference_path_by_header.items():
            parts = reference_path.strip("/").split("/")
            for year in range(dates[0].year, dates[-1].year + 1):
                pathname_parts = parts.copy()
                pathname_parts[3] = f"01JAN{year}"
                pathname = "/" + "/".join(pathname_parts) + "/"
                year_mask = dates.year == year
                year_values = values.loc[year_mask, header].to_numpy(dtype=float)

                tsc = TimeSeriesContainer()
                tsc.pathname = pathname
                tsc.startDateTime = f"01JAN{year} 24:00:00"
                tsc.numberValues = len(year_values)
                tsc.units = "IN/DAY"
                tsc.type = "PER-CUM"
                tsc.interval = 86400
                tsc.values = year_values
                output.put_ts(tsc)
                expected_pathnames.append(pathname.upper())

        written_pathnames = {
            pathname.upper()
            for pathname in output.getPathnameList(
                "/*/*/PRECIP/*/1DAY/PRECIPITATION/"
            ) or []
        }
        missing_pathnames = sorted(set(expected_pathnames) - written_pathnames)
        if missing_pathnames:
            raise ValueError(
                f"Output DSS is missing {len(missing_pathnames)} expected WBA "
                f"precipitation records; first missing: {missing_pathnames[0]}"
            )

    print(
        f"Wrote {len(expected_pathnames)} daily WBA records to {output_dss_path}"
    )


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
        path = GRID_DATA_DIR / f"meteo_{lat:.5f}_{lon:.5f}"
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
    write_daily_precipitation_dss(OUTPUT_CSV, REFERENCE_DSS, OUTPUT_DSS)


if __name__ == "__main__":
    main()
