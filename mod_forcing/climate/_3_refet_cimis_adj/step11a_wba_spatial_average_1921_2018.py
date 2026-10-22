# -*- coding: utf-8 -*-
"""
Step 11a: Historical_Unsplit (Product_A) ETo Spatial Average for 1921-2018
=================================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 8.0
Original   : H-S_RefETo_PRISM_CIMIS_WBAs_SR_SW_SpatialAvg_Monthly.py
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Author     : DWR
Date       : 2026

MANUAL STEP 8 PURPOSE (from manual Section 8.1)
------------------------------------------------
Compute area-weighted spatial average monthly ETo for each of the 42
CalSim3 Water Budget Areas (WBAs) using intersection weights between the
grid and the WBA polygons.

Equivalent PRISM step:
  Reads:  GridETo_PRISM_CIMIS_inpermonth (from CS3Domain_F1... Excel)
          WTable_*.csv (one per WBA, area-weighted grid fractions)
  Output: Spatial_Average_ETo_inpermonth.csv (12-column, 42-row monthly avg)

Historical_Unsplit (Product_A) ADAPTATION
---------------------
    Reads F1-corrected monthly ETo from Step 10b (Lon Lat mon-YYYY, 1921-2018)
        WBA, SR, and SW weights: GENERATED/.../_3_refet_cimis_adj/step0/WTable_*.csv
    Output: one row per polygon and 12 long-term monthly averages

INPUTS
------
    1. Step 10b output:
    Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv
             (written to GENERATED/.../_3_refet_cimis_adj/step10/)

    2. Step 0 generated weights:
             GENERATED/.../_3_refet_cimis_adj/step0/WTable_*.csv
         The current outputs contain 42 WBA, 21 SR, and 151 SW weight tables.
         Each CSV has 3 columns (skiprows=2, then header row):
         long[k], lati[k], percent[k]
     where percent[k] = (area of cell_k ∩ WBA) / (total WBA area) × 100

OUTPUTS  (written to GENERATED/.../_3_refet_cimis_adj/step11/)
------------------------------
    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_WBA.csv
      rows = 42 WBAs
            cols = WBA_ID, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec
            units: inches/month (long-term monthly average across 1921-2018)
      --> Required input for Step 9 (Spline Disaggregation)

    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_SR.csv
        One row for each of the 21 Subregions.

    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_per_SW.csv
        One row for each weighted Small Watershed (currently 151).

ENVIRONMENT
-----------
  conda activate eto_env

HOW TO RUN
----------
    python step11a_wba_spatial_average_1921_2018.py
    Prerequisites: Step 10b and Step 0 must be run first.
"""

import sys
import pathlib
import pandas as pd
import numpy as np
import re

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir

# =============================================================================
# CONFIGURATION
# =============================================================================

gen_dir = get_module_generated_dir("mod_forcing/climate")

STEP10_CSV = (
    gen_dir / "output" / "_3_refet_cimis_adj" / "step10"
    / "Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv"
)

WTABLE_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step0"

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step11"
START_YEAR = 1921
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
    if not data_cols:
        raise ValueError(f"No monthly data found for {START_YEAR}-{END_YEAR}")
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


def spatial_average(df_avg, wtable_dir, glob_pattern, id_col):
    """Compute weighted average monthly ETo for polygons matched by glob_pattern."""
    poly_files = sorted(pathlib.Path(wtable_dir).glob(glob_pattern))
    if not poly_files:
        print(f"  [SKIP] No files matching '{glob_pattern}' in {wtable_dir}")
        return pd.DataFrame()
    print(f"  Weight files found: {len(poly_files)}")

    df_avg_indexed = df_avg.set_index(["Lon", "Lat"])

    records = []
    for fp in poly_files:
        # Derive ID from filename: WTable_{prefix}{id}.csv -> strip prefix by glob pattern
        stem = fp.stem  # e.g. "WTable_SR_3" or "WTable_02"
        poly_id = stem[len("WTable_"):] if stem.startswith("WTable_") else stem
        df_w = load_wtable(fp)
        if df_w.empty:
            continue

        avg = {}
        total_w = 0.0
        for _, row in df_w.iterrows():
            key = (round(row["Lon"], 6), round(row["Lat"], 6))
            try:
                eto_row = df_avg_indexed.loc[key]
            except KeyError:
                dists = ((df_avg["Lon"] - row["Lon"])**2 +
                         (df_avg["Lat"] - row["Lat"])**2).values
                eto_row = df_avg.iloc[np.argmin(dists)][MONTH_NAMES]

            w = row["pct_k"]
            for m in MONTH_NAMES:
                avg[m] = avg.get(m, 0.0) + float(eto_row[m]) * w
            total_w += w

        if total_w > 0:
            for m in MONTH_NAMES:
                avg[m] = round(avg[m] / total_w, 4)

        avg[id_col] = poly_id
        records.append(avg)

    if not records:
        return pd.DataFrame()
    df_out = pd.DataFrame(records)
    return df_out[[id_col] + MONTH_NAMES]


def spatial_timeseries(df_eto, wtable_dir, glob_pattern, id_col, data_cols):
    """Compute every dated spatial value for polygon tables matching glob_pattern."""
    poly_files = sorted(pathlib.Path(wtable_dir).glob(glob_pattern))
    if not poly_files:
        print(f"  [SKIP] No files matching '{glob_pattern}' in {wtable_dir}")
        return pd.DataFrame()
    print(f"  Weight files found: {len(poly_files)}")

    source_index = df_eto.set_index(["Lon", "Lat"])
    source_coordinates = df_eto[["Lon", "Lat"]].to_numpy(dtype=float)
    records = []
    for fp in poly_files:
        stem = fp.stem
        poly_id = stem[len("WTable_"):] if stem.startswith("WTable_") else stem
        weights = load_wtable(fp)
        if weights.empty:
            continue

        weight_index = pd.MultiIndex.from_frame(weights[["Lon", "Lat"]])
        positions = source_index.index.get_indexer(weight_index)
        for weight_index_position in np.flatnonzero(positions < 0):
            coordinate = weights.iloc[weight_index_position][["Lon", "Lat"]].to_numpy(dtype=float)
            distances = ((source_coordinates - coordinate) ** 2).sum(axis=1)
            positions[weight_index_position] = int(np.argmin(distances))

        values = df_eto.iloc[positions][data_cols].to_numpy(dtype=float)
        weight_values = weights["pct_k"].to_numpy(dtype=float)
        valid = np.isfinite(values)
        weighted_totals = np.where(valid, values, 0.0).T @ weight_values
        valid_weights = valid.T @ weight_values
        spatial_values = np.divide(
            weighted_totals,
            valid_weights,
            out=np.full(len(data_cols), np.nan),
            where=valid_weights > 0,
        )
        if not np.isfinite(spatial_values).all():
            missing = [data_cols[i] for i in np.flatnonzero(~np.isfinite(spatial_values))[:5]]
            raise ValueError(f"{poly_id}: missing weighted values for {missing}")
        record = {id_col: poly_id}
        record.update(zip(data_cols, spatial_values))
        records.append(record)

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)[[id_col] + data_cols]


def main():
    print("=" * 60)
    print("Step 11a: WBA / SR / SW Spatial Average -- Historical_Unsplit (Product_A) F1-corrected")
    print("=" * 60)

    if not STEP10_CSV.exists():
        raise FileNotFoundError(
            f"Step 10b output not found. Run Step 10b first.\n  {STEP10_CSV}"
        )
    if not WTABLE_DIR.exists():
        raise FileNotFoundError(
            f"WTable directory not found. Run Step 0 first.\n  {WTABLE_DIR}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_eto, id_cols, data_cols = load_eto(STEP10_CSV)

    print("\nComputing long-term monthly averages per grid cell ...")
    df_avg = compute_monthly_longterm_avg(df_eto, id_cols, data_cols)

    # --- WBAs (WTable_[^SR_][^SW_]*.csv, i.e. no SR_/SW_ prefix) ----------
    print("\n[1/3] WBA spatial averages (WTable_*.csv excluding SR/SW) ...")
    # Exclude SR and SW files by matching only filenames without those prefixes
    wba_files = [f for f in sorted(WTABLE_DIR.glob("WTable_*.csv"))
                 if not f.stem.startswith("WTable_SR_")
                 and not f.stem.startswith("WTable_SW_")]
    df_avg_indexed = df_avg.set_index(["Lon", "Lat"])
    if wba_files:
        print(f"  Weight files found: {len(wba_files)}")
        records = []
        for fp in wba_files:
            poly_id = fp.stem[len("WTable_"):]
            df_w = load_wtable(fp)
            if df_w.empty:
                continue
            avg = {}; total_w = 0.0
            for _, row in df_w.iterrows():
                key = (round(row["Lon"], 6), round(row["Lat"], 6))
                try:
                    eto_row = df_avg_indexed.loc[key]
                except KeyError:
                    dists = ((df_avg["Lon"] - row["Lon"])**2 +
                             (df_avg["Lat"] - row["Lat"])**2).values
                    eto_row = df_avg.iloc[np.argmin(dists)][MONTH_NAMES]
                w = row["pct_k"]
                for m in MONTH_NAMES:
                    avg[m] = avg.get(m, 0.0) + float(eto_row[m]) * w
                total_w += w
            if total_w > 0:
                for m in MONTH_NAMES:
                    avg[m] = round(avg[m] / total_w, 4)
            avg["WBA_ID"] = poly_id
            records.append(avg)
        df_wba = pd.DataFrame(records)[["WBA_ID"] + MONTH_NAMES]
    else:
        df_wba = pd.DataFrame()

    # --- Subregions (SR) --------------------------------------------------
    print("\n[2/3] Subregion (SR) spatial averages (WTable_SR_*.csv) ...")
    df_sr = spatial_average(df_avg, WTABLE_DIR, "WTable_SR_*.csv", id_col="SR_ID")

    # --- Small Watersheds (SW) --------------------------------------------
    print("\n[3/3] Small Watershed (SW) spatial averages (WTable_SW_*.csv) ...")
    df_sw = spatial_average(df_avg, WTABLE_DIR, "WTable_SW_*.csv", id_col="SW_ID")

    print("\nComputing dated spatial series for 1921-2018 ...")
    df_wba_timeseries = spatial_timeseries(
        df_eto, WTABLE_DIR, "WTable_*.csv", id_col="WBA_ID",
        data_cols=data_cols,
    )
    if not df_wba_timeseries.empty:
        df_wba_timeseries = df_wba_timeseries[
            ~df_wba_timeseries["WBA_ID"].astype(str).str.startswith(("SR_", "SW_"))
        ].copy()
    df_sr_timeseries = spatial_timeseries(
        df_eto, WTABLE_DIR, "WTable_SR_*.csv", id_col="SR_ID",
        data_cols=data_cols,
    )
    df_sw_timeseries = spatial_timeseries(
        df_eto, WTABLE_DIR, "WTable_SW_*.csv", id_col="SW_ID",
        data_cols=data_cols,
    )

    # --- Write outputs ----------------------------------------------------
    out_wba = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_WBA.csv"
    out_sr  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SR.csv"
    out_sw  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SW.csv"
    out_wba_timeseries = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_WBA.csv"
    out_sr_timeseries  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SR.csv"
    out_sw_timeseries  = OUTPUT_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SW.csv"

    if not df_wba.empty:
        df_wba.to_csv(out_wba, index=False)
    if not df_sr.empty:
        df_sr.to_csv(out_sr, index=False)
    if not df_sw.empty:
        df_sw.to_csv(out_sw, index=False)
    if not df_wba_timeseries.empty:
        df_wba_timeseries.to_csv(out_wba_timeseries, index=False, float_format="%.6f")
    if not df_sr_timeseries.empty:
        df_sr_timeseries.to_csv(out_sr_timeseries, index=False, float_format="%.6f")
    if not df_sw_timeseries.empty:
        df_sw_timeseries.to_csv(out_sw_timeseries, index=False, float_format="%.6f")

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    output_sets = [
        ("WBA monthly average", df_wba, out_wba),
        ("SR monthly average", df_sr, out_sr),
        ("SW monthly average", df_sw, out_sw),
        ("WBA monthly timeseries", df_wba_timeseries, out_wba_timeseries),
        ("SR monthly timeseries", df_sr_timeseries, out_sr_timeseries),
        ("SW monthly timeseries", df_sw_timeseries, out_sw_timeseries),
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
