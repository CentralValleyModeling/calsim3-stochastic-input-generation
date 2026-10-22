# -*- coding: utf-8 -*-
"""
Manual Step 8.0: Ref ETo Spatial Average for WBAs, SRs, and SWs
===============================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 8.0
Original   : H-S_RefETo_PRISM_CIMIS_WBAs_SR_SW_SpatialAvg_Monthly.py
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Author     : DWR
Date       : 2026

MANUAL STEP 8 PURPOSE (from manual Section 8.1)
------------------------------------------------
Compute area-weighted spatial average monthly ETo for the 42 CalSim3 Water
Budget Areas (WBAs), 21 Subregions (SRs), and all weighted Small Watersheds
(SWs) using Step 0 grid-polygon intersection weights.

Equivalent PRISM step:
  Reads:  GridETo_PRISM_CIMIS_inpermonth (from CS3Domain_F1... Excel)
          WTable_*.csv (one per WBA, area-weighted grid fractions)
  Output: Spatial_Average_ETo_inpermonth.csv (12-column, 42-row monthly avg)

Historical_Unsplit (Product_A) ADAPTATION
---------------------
  Reads F1-corrected monthly ETo from Step 6-7 (same format: Lon Lat mon-YYYY...)
    Weights: Step0_GridWeights_WBA_SR_SW/output/*.csv
    Output: one row per WBA, SR, or SW, with its ID and 12 monthly averages

INPUTS
------
  1. Step 6-7 output:
    Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv
       (written to Step7_F1_Adjustment/output/ by step7_apply_f1_adjustment.py)

    2. Step0_GridWeights_WBA_SR_SW/output/*.csv  --  one CSV per WBA, SR, or SW polygon
     -----------------------------------------------------------------------
     These files are NOT included in the repo. They must be generated ONCE
     by running:

         conda activate eto_env
         cd Step0_GridWeights_WBA_SR_SW
         python step0_build_wba_grid_weights.py

    That script intersects the 1/16-degree Historical_Unsplit (Product_A) grid (13,787 cells) with
     the 42 WBA polygons in EPSG:3310 (California Albers Equal Area) and writes:

         output/WTable_02.csv
         output/WTable_03.csv
         ...
         output/WTable_DETAW.csv

     Each CSV has 3 columns (skiprows=2, then header row):
         long[k], lati[k], percent[k]
     where percent[k] = (area of cell_k ∩ WBA) / (total WBA area) × 100

     Required inputs for step1:
    - WBA GeoJSON: Step8_WBA_SR_SW_Spatial_Average/input/CS3_WBAs.geojson
    - Historical_Unsplit (Product_A) data directory (filenames encode lat/lon)

    The WTABLE_DIR constant below points to this subfolder automatically.
    This is a one-time operation; the same files support WBA, SR, and SW runs.

OUTPUTS  (written to output/)
------------------------------
    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_WBA.csv
      rows = 42 WBAs
      cols = WBA_ID, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
      units: inches/month (long-term monthly average across all years)
      --> Required input for Step 9 (Spline Disaggregation)

    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_SR.csv
      rows = 21 Subregions; columns = SR_ID and Jan-Dec

    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_SW.csv
      rows = one per weighted Small Watershed (currently 151); columns = SW_ID and Jan-Dec

ENVIRONMENT
-----------
  conda activate eto_env

HOW TO RUN
----------
  python step8_wba_spatial_average.py
  Prerequisites: Step 5 and Step 6-7 must be run first.
"""

import pathlib
import sys
import pandas as pd
import numpy as np
import re

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

# =============================================================================
# CONFIGURATION
# =============================================================================
# Set up paths
script_dir = pathlib.Path(__file__).parent.resolve()
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")

STEP7_CSV = (
    gen_dir / "output" / "_3_refet_cimis_adj" / "step7"
    / "Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv"
)

WTABLE_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step0"

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step8"
START_YEAR = 2004
END_YEAR = 2018

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# =============================================================================


def load_eto(csv_path):
    print(f"Reading F1-corrected ETo from:\n  {csv_path}")
    df = pd.read_csv(csv_path)
    id_cols   = ["Lon", "Lat"]
    data_cols = [c for c in df.columns if c not in id_cols]
    data_cols = [c for c in data_cols
                 if START_YEAR <= int(c.split("-")[1]) <= END_YEAR]
    expected = [
        f"{month}-{year}"
        for year in range(START_YEAR, END_YEAR + 1)
        for month in MONTH_NAMES
    ]
    if data_cols != expected:
        raise ValueError(
            f"Input must contain exactly Jan-{START_YEAR} through Dec-{END_YEAR}"
        )
    print(f"  Cells: {len(df):,}  Monthly columns: {len(data_cols):,}")
    return df, id_cols, data_cols


def compute_monthly_longterm_avg(df_eto, id_cols, data_cols):
    """
    For each grid cell, average all years for each calendar month.
    Returns DataFrame: rows=cells, cols=Lon Lat Jan Feb ... Dec
    """
    df_avg = df_eto[id_cols].copy()
    for m in MONTH_NAMES:
        m_cols = [c for c in data_cols if c.split("-")[0] == m]
        df_avg[m] = df_eto[m_cols].mean(axis=1).round(4)
    return df_avg


def load_wtable(csv_path):
    """
    WTable CSVs: skiprows=2 (first two rows are metadata),
    then: Lon, Lat, pct_k (area fraction within WBA).
    """
    df = pd.read_csv(csv_path, skiprows=2)
    df.columns = ["Lon", "Lat", "pct_k"]
    df = df.apply(pd.to_numeric, errors="coerce")
    return df.dropna()


def weighted_values(df_values, df_weights, value_columns):
    """Compute area-weighted values for one polygon's grid-cell weight table."""
    lookup = df_values.set_index(["Lon", "Lat"])
    weight_index = pd.MultiIndex.from_frame(df_weights[["Lon", "Lat"]])
    positions = lookup.index.get_indexer(weight_index)
    for idx in np.flatnonzero(positions < 0):
        distance = (
            (df_values["Lon"] - df_weights.iloc[idx]["Lon"]) ** 2
            + (df_values["Lat"] - df_weights.iloc[idx]["Lat"]) ** 2
        ).to_numpy()
        positions[idx] = int(np.argmin(distance))

    values = lookup.iloc[positions][value_columns].to_numpy(dtype=float)
    weights = df_weights["pct_k"].to_numpy(dtype=float)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).T @ weights
    valid_weights = valid.T @ weights
    return np.divide(
        totals,
        valid_weights,
        out=np.full(len(value_columns), np.nan),
        where=valid_weights > 0,
    )


def spatial_average_files(df_values, poly_files, id_col, value_columns, decimals=None):
    """Compute weighted values for the supplied polygon weight tables."""
    if not poly_files:
        return pd.DataFrame()
    print(f"  Weight files found: {len(poly_files)}")

    records = []
    for fp in poly_files:
        stem = fp.stem
        poly_id = stem[len("WTable_"):] if stem.startswith("WTable_") else stem
        df_w = load_wtable(fp)
        if df_w.empty:
            continue
        values = weighted_values(df_values, df_w, value_columns)
        if not np.isfinite(values).all():
            missing = [value_columns[i] for i in np.flatnonzero(~np.isfinite(values))[:5]]
            raise ValueError(f"{poly_id}: missing weighted values for {missing}")
        if decimals is not None:
            values = np.round(values, decimals)
        record = dict(zip(value_columns, values))
        record[id_col] = poly_id
        records.append(record)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)[[id_col] + value_columns]


def spatial_average(df_values, wtable_dir, glob_pattern, id_col,
                    value_columns=MONTH_NAMES, decimals=4):
    """Compute weighted values for polygon tables matching glob_pattern."""
    poly_files = sorted(pathlib.Path(wtable_dir).glob(glob_pattern))
    if not poly_files:
        print(f"  [SKIP] No files matching '{glob_pattern}' in {wtable_dir}")
        return pd.DataFrame()
    return spatial_average_files(
        df_values, poly_files, id_col, value_columns, decimals=decimals
    )


def main():
    print("=" * 60)
    print("Manual Step 8: WBA / SR / SW Spatial Average (F1-corrected)")
    print("=" * 60)

    if not STEP7_CSV.exists():
        raise FileNotFoundError(
            f"Step 7 output not found. Run Step 7 first.\n  {STEP7_CSV}"
        )
    if not WTABLE_DIR.exists():
        raise FileNotFoundError(
            f"WTable directory not found. Run Step 0 first.\n  {WTABLE_DIR}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_eto, id_cols, data_cols = load_eto(STEP7_CSV)

    print("\nComputing 12-month averages per grid cell ...")
    df_avg = compute_monthly_longterm_avg(df_eto, id_cols, data_cols)

    # --- WBAs (WTable_[^SR_][^SW_]*.csv, i.e. no SR_/SW_ prefix) ----------
    print("\n[1/3] WBA spatial averages (WTable_*.csv excluding SR/SW) ...")
    # Exclude SR and SW files by matching only filenames without those prefixes
    wba_files = [f for f in sorted(WTABLE_DIR.glob("WTable_*.csv"))
                 if not f.stem.startswith("WTable_SR_")
                 and not f.stem.startswith("WTable_SW_")]
    df_avg_indexed = df_avg.set_index(["Lon", "Lat"])
    df_wba = spatial_average_files(
        df_avg, wba_files, id_col="WBA_ID", value_columns=MONTH_NAMES,
        decimals=4,
    )
    df_wba_timeseries = spatial_average_files(
        df_eto, wba_files, id_col="WBA_ID", value_columns=data_cols,
    )

    # --- Subregions (SR) --------------------------------------------------
    print("\n[2/3] Subregion (SR) spatial averages (WTable_SR_*.csv) ...")
    df_sr = spatial_average(df_avg, WTABLE_DIR, "WTable_SR_*.csv", id_col="SR_ID")
    df_sr_timeseries = spatial_average(
        df_eto, WTABLE_DIR, "WTable_SR_*.csv", id_col="SR_ID",
        value_columns=data_cols, decimals=None,
    )

    # --- Small Watersheds (SW) --------------------------------------------
    print("\n[3/3] Small Watershed (SW) spatial averages (WTable_SW_*.csv) ...")
    df_sw = spatial_average(df_avg, WTABLE_DIR, "WTable_SW_*.csv", id_col="SW_ID")
    df_sw_timeseries = spatial_average(
        df_eto, WTABLE_DIR, "WTable_SW_*.csv", id_col="SW_ID",
        value_columns=data_cols, decimals=None,
    )

    # --- Write outputs ----------------------------------------------------
    out_wba = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_WBA.csv"
    out_sr  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SR.csv"
    out_sw  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SW.csv"
    out_wba_ts = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_WBA.csv"
    out_sr_ts  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SR.csv"
    out_sw_ts  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SW.csv"

    if not df_wba.empty:
        df_wba.to_csv(out_wba, index=False)
    if not df_sr.empty:
        df_sr.to_csv(out_sr, index=False)
    if not df_sw.empty:
        df_sw.to_csv(out_sw, index=False)
    if not df_wba_timeseries.empty:
        df_wba_timeseries.to_csv(out_wba_ts, index=False, float_format="%.6f")
    if not df_sr_timeseries.empty:
        df_sr_timeseries.to_csv(out_sr_ts, index=False, float_format="%.6f")
    if not df_sw_timeseries.empty:
        df_sw_timeseries.to_csv(out_sw_ts, index=False, float_format="%.6f")

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    output_sets = [
        ("WBA monthly average", df_wba, out_wba),
        ("SR monthly average", df_sr, out_sr),
        ("SW monthly average", df_sw, out_sw),
        ("WBA monthly timeseries", df_wba_timeseries, out_wba_ts),
        ("SR monthly timeseries", df_sr_timeseries, out_sr_ts),
        ("SW monthly timeseries", df_sw_timeseries, out_sw_ts),
    ]
    for label, df, path in output_sets:
        if not df.empty:
            print(f"  {path.name}  ({len(df)} {label} rows; {len(df.columns) - 1} values per row)")
    print("\nWBA summary (inches/month):")
    if not df_wba.empty:
        print(df_wba.to_string(index=False))
    print("Done.")


if __name__ == "__main__":
    main()
