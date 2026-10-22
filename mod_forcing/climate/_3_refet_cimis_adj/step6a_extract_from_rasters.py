# -*- coding: utf-8 -*-
"""
Manual Step 6.0: Extract CIMIS ETo from Rasters (rasterio = ArcPy replacement)
===============================================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 6.0
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Author     : DWR
Date       : 2026

WHAT THIS SCRIPT DOES
----------------------
Open-source replacement for the original ArcPy Step 6:

    ArcPy (original)                    | rasterio (this script)
    ------------------------------------|----------------------------------------
    arcpy.Raster(asc_path)              | rasterio.open(/vsigzip/path)
    arcpy.sa.ExtractValuesToPoints()    | src.sample([(lon, lat), ...])
    Group by month, average             | pandas groupby + mean (unchanged)
    Write CSV                           | pandas to_csv (unchanged)

INPUT
-----
  CIMIS_RASTER_DIR : cimis_eto_rasters/ subfolder populated by
    step6_download_cimis_rasters.py.
    Filename format : ETo_YYYYMMDD.asc.gz
    Format          : ESRI ASCII Grid, gzip-compressed
    CRS             : California Albers NAD83 (EPSG:3310) -- no CRS in file;
                      falls back to CIMIS_ASC_CRS config variable.
    NoData          : cells outside California return NaN (skipped).

    Historical_Unsplit (Product_A) directory: grid coordinates parsed from filenames.

  Period: CIMIS_START_YEAR through CIMIS_END_YEAR (default 2004-2021).

  *** PREREQUISITE: run step6_download_cimis_rasters.py first. ***

OUTPUT (written to the configured output folder)
------------------------------------------------
    CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_2004.csv
    ... one file per year through CIMIS_END_YEAR
    CIMIS_MonthlyAvg_ETo_mmperday_Historical_Unsplit (Product_A)_grid.csv (overall average)
    rows : one per Historical_Unsplit (Product_A) grid cell (lon, lat)
      cols : lon, lat, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
      units: mm/day
      --> Numerator of F1 = CIMIS_avg / PRISM_HS_avg in Step 7

  CELL VALUES:
    numeric  -- that year's monthly average CIMIS ETo (mm/day) at that grid point.
    NaN      -- cell is outside the Spatial CIMIS domain (CIMIS covers California
                only; Historical_Unsplit (Product_A) extends into Nevada, Arizona, and Mexico). These
                cells have no CIMIS data and are carried as NaN through Step 7
                (F1 = 1.0 applied, i.e. no bias correction for those cells).
    NOTE: prior to the bounds-check fix, out-of-bounds cells incorrectly showed
          as 0.0 because rasterio returns a 0-fill for coordinates outside the
          raster extent. The fix explicitly excludes those coordinates.

ENVIRONMENT
-----------
  conda activate eto_env   (rasterio required -- see environment.yml)

HOW TO RUN
----------
  1. python step6_download_cimis_rasters.py   (downloads rasters -- run once)
  2. python step6_extract_from_rasters.py
"""

import gzip as _gzip
import os
import re
import sys
import pathlib
import tempfile
from datetime import date, timedelta

import numpy as np
import pandas as pd
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform as warp_transform
from tqdm import tqdm

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

_GZIP_MAGIC = b'\x1f\x8b'

# =============================================================================
# CONFIGURATION
# =============================================================================
# Set up paths
script_dir = pathlib.Path(__file__).parent.resolve()
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")

# Folder populated by step6_download_cimis_rasters.py
CIMIS_RASTER_DIR = base_dir / "CIMIS" / "cimis_eto_rasters" 

GRID_DATA_DIR = base_dir / "WGEN" / "Historical_Unsplit" 

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step6" / "CIMIS_MonthlyAvg_ETo" 

CIMIS_START_YEAR = 2004
CIMIS_END_YEAR   = 2023
CIMIS_OUTPUT_SUFFIX = ""

# Regex to extract date from filenames produced by step6B_download_cimis_rasters.py.
# Format: ETo_YYYYMMDD.asc.gz  (change if you used a different naming scheme)
FILENAME_PATTERN = r"ETo_(\d{4})(\d{2})(\d{2})\.asc\.gz$"

# CRS of the downloaded CIMIS .asc rasters.  ESRI ASCII Grid files have no
# embedded projection; CIMIS Spatial data uses California Albers (NAD83).
CIMIS_ASC_CRS = "EPSG:3310"

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

NODATA_FILL = np.nan

# =============================================================================


def scan_grid_cells(data_dir):
    pattern = re.compile(r"^data_([-\d.]+)_([-\d.]+)$")
    cells = []
    for fname in os.listdir(data_dir):
        m = pattern.match(fname)
        if m:
            cells.append({"lat": float(m.group(1)), "lon": float(m.group(2))})
    if not cells:
        raise FileNotFoundError(f"No data_{{lat}}_{{lon}} files in:\n  {data_dir}")
    print(f"  Historical_Unsplit (Product_A) cells: {len(cells):,}")
    return pd.DataFrame(cells)


def index_rasters(raster_dir, fname_pattern):
    """Return dict: date -> Path for all rasters matching FILENAME_PATTERN."""
    rx = re.compile(fname_pattern)
    index = {}
    for fname in os.listdir(raster_dir):
        m = rx.search(fname)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                dt = date(y, mo, d)
                if CIMIS_START_YEAR <= dt.year <= CIMIS_END_YEAR:
                    index[dt] = raster_dir / fname
            except ValueError:
                pass
    return index


def reproject_coords(lons, lats, src_crs, dst_crs):
    """Reproject WGS84 lon/lat to the raster CRS for sampling."""
    if dst_crs == CRS.from_epsg(4326):
        return list(lons), list(lats)
    xs, ys = warp_transform("EPSG:4326", dst_crs, list(lons), list(lats))
    return xs, ys


def _open_path(raster_path):
    """Return open-path string; for .gz files verify gzip magic first.
    Returns None if file has .gz extension but is plain ASCII (needs temp-file fallback)."""
    s = str(raster_path)
    if s.endswith(".gz"):
        with open(raster_path, 'rb') as f:
            if f.read(2) == _GZIP_MAGIC:
                return "/vsigzip/" + s.replace("\\", "/")
        return None  # plain ASCII saved with .gz extension
    return s


def extract_one_raster(raster_path, xs, ys, nodata):
    """Sample an ESRI ASCII Grid without repeated GDAL access."""
    is_gzip = False
    if str(raster_path).endswith(".gz"):
        with open(raster_path, "rb") as raw_file:
            is_gzip = raw_file.read(2) == _GZIP_MAGIC
    opener = _gzip.open if is_gzip else open
    with opener(raster_path, "rt") as fh:
        header = {}
        for _ in range(6):
            key, value = fh.readline().split(maxsplit=1)
            header[key.lower()] = float(value)
        data = np.fromstring(fh.read(), sep=" ")

    ncols, nrows = int(header["ncols"]), int(header["nrows"])
    data = data.reshape((nrows, ncols))
    cellsize = header["cellsize"]
    xs_a, ys_a = np.asarray(xs), np.asarray(ys)
    cols = np.floor((xs_a - header["xllcorner"]) / cellsize).astype(int)
    top = header["yllcorner"] + nrows * cellsize
    rows = np.floor((top - ys_a) / cellsize).astype(int)
    in_bounds = ((rows >= 0) & (rows < nrows) &
                 (cols >= 0) & (cols < ncols))
    raw = np.full(len(xs_a), np.nan)
    if in_bounds.any():
        vals = data[rows[in_bounds], cols[in_bounds]]
        vals[vals == header.get("nodata_value", nodata)] = np.nan
        raw[in_bounds] = vals
    return raw


def main():
    print("=" * 60)
    print("Manual Step 6 Option B: CIMIS Raster Extraction (rasterio)")
    print("=" * 60)

    if not CIMIS_RASTER_DIR.exists():
        raise FileNotFoundError(
            f"\nRaster directory not found:\n  {CIMIS_RASTER_DIR}\n\n"
            "Download Spatial CIMIS ETo rasters first -- see NOTES.txt"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/4] Scanning Historical_Unsplit (Product_A) grid cells ...")
    df_cells = scan_grid_cells(GRID_DATA_DIR)
    n_cells  = len(df_cells)

    print(f"\n[2/4] Indexing CIMIS rasters in:\n  {CIMIS_RASTER_DIR}")
    raster_index = index_rasters(CIMIS_RASTER_DIR, FILENAME_PATTERN)
    n_rasters    = len(raster_index)
    if n_rasters == 0:
        raise FileNotFoundError(
            f"No rasters matched pattern '{FILENAME_PATTERN}' in:\n  {CIMIS_RASTER_DIR}\n"
            "Check FILENAME_PATTERN in this script."
        )
    print(f"  Found {n_rasters:,} raster files "
          f"({CIMIS_START_YEAR}-{CIMIS_END_YEAR})")

    rasters_by_year = {year: [] for year in range(CIMIS_START_YEAR, CIMIS_END_YEAR + 1)}
    for dt, path in raster_index.items():
        rasters_by_year[dt.year].append((dt, path))
    missing_years = [year for year, paths in rasters_by_year.items() if not paths]
    if missing_years:
        raise FileNotFoundError(
            "No CIMIS rasters found for year(s): "
            + ", ".join(str(year) for year in missing_years)
        )

    print(f"\n[3/4] Extracting annual monthly averages at {n_cells:,} "
          f"Historical_Unsplit (Product_A) cells ...")

    # Reproject coordinates to match raster CRS.
    # .asc files carry no CRS metadata; fall back to the configured CIMIS_ASC_CRS.
    first_path = next(iter(raster_index.values()))
    first_open = _open_path(first_path)
    if first_open is None:
        raster_crs = CRS.from_string(CIMIS_ASC_CRS)
    else:
        with rasterio.open(first_open) as src:
            raster_crs = src.crs or CRS.from_string(CIMIS_ASC_CRS)
    xs, ys = reproject_coords(
        df_cells["lon"].values, df_cells["lat"].values,
        "EPSG:4326", raster_crs
    )

    # Accumulate overall multi-year sums and counts across all years
    overall_sums   = {m: np.zeros(n_cells) for m in range(1, 13)}
    overall_counts = {m: np.zeros(n_cells) for m in range(1, 13)}

    print(f"\n[4/4] Computing monthly averages and writing yearly outputs ...")
    for year in range(CIMIS_START_YEAR, CIMIS_END_YEAR + 1):
        monthly_sums   = {m: np.zeros(n_cells) for m in range(1, 13)}
        monthly_counts = {m: np.zeros(n_cells) for m in range(1, 13)}

        for dt, path in tqdm(sorted(rasters_by_year[year]), desc=f"Processing {year}"):
            try:
                vals = extract_one_raster(path, xs, ys, NODATA_FILL)
            except Exception as exc:
                print(f"  [WARN] {path.name}: {exc} -- skipped")
                continue
            mo = dt.month
            valid_mask = ~np.isnan(vals)
            monthly_sums[mo][valid_mask]   += vals[valid_mask]
            monthly_counts[mo][valid_mask] += 1
            overall_sums[mo][valid_mask]   += vals[valid_mask]
            overall_counts[mo][valid_mask] += 1

        records = []
        for i, row in df_cells.iterrows():
            rec = {"lon": row["lon"], "lat": row["lat"]}
            for m_idx, m_name in enumerate(MONTH_NAMES, start=1):
                cnt = monthly_counts[m_idx][i]
                rec[m_name] = (
                    round(monthly_sums[m_idx][i] / cnt, 4)
                    if cnt > 0 else np.nan
                )
            records.append(rec)

        df_out = pd.DataFrame(records)
        out_csv = OUTPUT_DIR / (
            f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}"
            f"{CIMIS_OUTPUT_SUFFIX}.csv"
        )
        df_out.to_csv(out_csv, index=False, na_rep='NaN')

        print(f"\n{year} monthly average CIMIS ETo (mm/day) across {n_cells:,} cells:")
        print(f"  {'Month':<6}  {'Mean':>7}  {'Min':>7}  {'Max':>7}  {'Valid cells':>12}")
        for m_idx, m_name in enumerate(MONTH_NAMES, start=1):
            col = df_out[m_name].dropna()
            cnt = monthly_counts[m_idx].astype(int).min()
            if not col.empty:
                print(f"  {m_name:<6}  {col.mean():7.4f}  {col.min():7.4f}  {col.max():7.4f}  {cnt:12d} days")
        print(f"  Wrote {out_csv.name}")

    # Also write overall multi-year average file
    records_all = []
    for i, row in df_cells.iterrows():
        rec = {"lon": row["lon"], "lat": row["lat"]}
        for m_idx, m_name in enumerate(MONTH_NAMES, start=1):
            cnt = overall_counts[m_idx][i]
            rec[m_name] = (
                round(overall_sums[m_idx][i] / cnt, 4)
                if cnt > 0 else np.nan
            )
        records_all.append(rec)

    df_out_all = pd.DataFrame(records_all)
    out_all_csv = OUTPUT_DIR / (
        "CIMIS_MonthlyAvg_ETo_mmperday_Historical_Unsplit (Product_A)_grid"
        f"{CIMIS_OUTPUT_SUFFIX}.csv"
    )
    df_out_all.to_csv(out_all_csv, index=False, na_rep='NaN')
    print(f"\nWrote multi-year average: {out_all_csv.name}")

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
