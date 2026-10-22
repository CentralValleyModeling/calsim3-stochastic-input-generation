# -*- coding: utf-8 -*-
"""
Manual Step 7.0: F1 Adjustment Factor and Adjusted Ref ETo -- Historical_Unsplit (Product_A)
========================================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 7.0
Original   : CS3Domain_F1_Calculation_for_Ref_ETo.xlsx (manual spreadsheet steps i-v)
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Author     : DWR
Date       : 2026

MANUAL STEP 7 PROCEDURE (Sections 7.3 i-v)
-------------------------------------------
  i.   Copy Step 5 H-S ETo time series into Excel (CS3_Domain_ETo_PRISM_HS_Monthly sheet).
  ii.  Compute long-term monthly average H-S ETo for 2004-2021
       (MonthlyAvgPRISM_HSETo_2004_2021 sheet) -- this is the DENOMINATOR of F1.
  iii. Copy Step 6 CIMIS monthly averages into Excel
       (MonthlyAvgSpatialCIMIS_ETo sheet) -- this is the NUMERATOR of F1.
  iv.  Compute F1 = CIMIS_monthly_avg / HS_monthly_avg  per cell per month.
  v.   Multiply full H-S time series by F1 to get corrected ETo.

Historical_Unsplit (Product_A) Adaptation
---------------------
Steps i-v must be recomputed using Historical_Unsplit (Product_A) values.
The pre-computed F1 in the Excel (Factor(F1) sheet) CANNOT be used directly
because its denominator is PRISM H-S averages, not Historical_Unsplit (Product_A) H-S averages.
The bias F1 corrects depends on how well H-S performs with the actual
temperature inputs; PRISM and Historical_Unsplit (Product_A) temperatures
differ, so their H-S estimates differ, and F1 must be recomputed accordingly.

  Step i  (manual -> this script):
    Load full Historical_Unsplit (Product_A) H-S ETo time series from Step 5 output.

  Step ii (manual -> this script):
    Compute monthly average Historical_Unsplit (Product_A) H-S ETo over the overlap period
    2004-2018 (Historical_Unsplit ends 2018; CIMIS coverage 2004-2021, overlap = 2004-2018).
    Units: convert inches/month to mm/day for the F1 ratio.

  Step iii (manual -> this script):
        Load the Step 6 annual CIMIS averages for 2004-2018, already at
        Historical_Unsplit (Product_A) grid points, and average them by month.
        Step 6 also provides 2019-2023, but those years are excluded because the
        Historical_Unsplit (Product_A) H-S denominator ends in 2018.

  Step iv (manual -> this script):
        F1 = CIMIS_monthly_avg / Historical_Unsplit (Product_A) H-S monthly average
            per cell per month.

  Step v  (manual -> this script):
    Multiply the full Historical_Unsplit (Product_A) H-S time series (1921-2018) by F1.

INPUTS
------
        Step 5 output: Historical_Unsplit (Product_A)_ETo_monthly_inpermonth.csv (inches/month, 1921-2018)
        CIMIS source: annual Step 6 CSVs in
            OneDrive/.../CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_Per_Year/
            CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_2004.csv through _2018.csv

OUTPUTS (written to output/)
-----------------------------
    Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv
      Same structure as Step 5 output (Lon Lat Jan-1915 ... Dec-2018).
      Each value multiplied by its cell+month F1 factor.
      Units: inches/month  --> input for Step 8

    Historical_Unsplit (Product_A)_F1_table.csv
    The F1 factor computed for each Historical_Unsplit (Product_A) cell and each calendar month.
      Lon, Lat, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec

    Historical_Unsplit (Product_A)_HS_monthly_avg_mmperday.csv
    Diagnostic: Historical_Unsplit (Product_A) H-S monthly avg (2004-2018) used as F1 denominator.

ENVIRONMENT
-----------
  conda activate eto_env  (scipy + openpyxl required)

HOW TO RUN
----------
  python step7_apply_f1_adjustment.py
  Prerequisites: Step 5 must be run first.
                 Step 6 annual output files for 2004-2018 must be present.
"""

import calendar
import sys
import pathlib
from datetime import datetime

import numpy as np
import pandas as pd

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

STEP5_CSV = (
    gen_dir / "output" / "_3_refet_cimis_adj" / "step5"
    / "Historical_Unsplit (Product_A)_ETo_monthly_inpermonth.csv"
)

STEP6_CIMIS_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step6" / "CIMIS_MonthlyAvg_ETo"

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step7"

# Use only the overlap period; the Historical_Unsplit (Product_A) H-S series ends in 2018.
F1_START_YEAR = 2004
F1_END_YEAR   = 2018
FULL_START_YEAR = 1921
FULL_END_YEAR   = 2018

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# =============================================================================


def parse_col(col):
    """Return (month_name, year) from a column like 'Jan-1915'."""
    parts = col.split("-")
    return parts[0], int(parts[1])


def load_step5(csv_path):
    print(f"Reading Step 5 ETo from:\n  {csv_path}")
    df = pd.read_csv(csv_path)
    id_cols   = ["Lon", "Lat"]
    data_cols = [c for c in df.columns if c not in id_cols]
    print(f"  Cells: {len(df):,}  Monthly columns: {len(data_cols):,}")
    return df, id_cols, data_cols


def compute_hs_monthly_avg(df_eto, id_cols, data_cols):
    """
    Manual step ii: compute long-term monthly avg Historical_Unsplit (Product_A) H-S ETo (mm/day)
    over F1_START_YEAR to F1_END_YEAR.
    Returns array shape (n_cells, 12) in mm/day and a diagnostic DataFrame.
    """
    print(f"\nStep ii -- Historical_Unsplit (Product_A) H-S monthly avg ({F1_START_YEAR}-{F1_END_YEAR}) ...")
    n_cells = len(df_eto)
    hs_sum  = np.zeros((n_cells, 12))
    counts  = np.zeros(12, dtype=int)

    for col in data_cols:
        m_name, yr = parse_col(col)
        if m_name not in MONTH_NAMES:
            continue
        if not (F1_START_YEAR <= yr <= F1_END_YEAR):
            continue
        m_idx = MONTH_NAMES.index(m_name)
        days  = calendar.monthrange(yr, m_idx + 1)[1]
        hs_sum[:, m_idx] += df_eto[col].values * 25.4 / days  # inches/month -> mm/day
        counts[m_idx]    += 1

    hs_avg = np.where(counts > 0, hs_sum / counts, 0.0)
    print(f"  Years averaged per month: {counts.tolist()}")

    df_diag = df_eto[id_cols].copy()
    for m_idx, m_name in enumerate(MONTH_NAMES):
        df_diag[m_name] = hs_avg[:, m_idx].round(4)
    return hs_avg, df_diag


def load_cimis_monthly_avg(df_eto):
    """
    Average Step 6's annual CIMIS monthly averages over the F1 overlap period.
    Returns an array shaped (n_cells, 12) in mm/day.
    """
    years = range(F1_START_YEAR, F1_END_YEAR + 1)
    annual_values = []
    missing_paths = []

    for year in years:
        csv_path = STEP6_CIMIS_DIR / f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}.csv"
        if not csv_path.is_file():
            missing_paths.append(csv_path)

    if missing_paths:
        missing_list = "\n  ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(
            f"Missing Step 6 annual CIMIS files for {F1_START_YEAR}-{F1_END_YEAR}:\n  {missing_list}\n"
            "Run Step 6 extraction for each overlap year before Step 7."
        )

    for year in range(F1_START_YEAR, F1_END_YEAR + 1):
        csv_path = STEP6_CIMIS_DIR / f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}.csv"
        df_c = pd.read_csv(csv_path).rename(columns={"lon": "Lon", "lat": "Lat"})
        required_columns = ["Lon", "Lat"] + MONTH_NAMES
        missing_columns = [column for column in required_columns if column not in df_c.columns]
        if missing_columns:
            raise ValueError(
                f"Step 6 CIMIS file has missing columns {missing_columns}:\n  {csv_path}"
            )
        df_merged = df_eto[["Lon","Lat"]].merge(
            df_c[required_columns],
            on=["Lon","Lat"], how="left", validate="one_to_one"
        )
        annual_values.append(df_merged[MONTH_NAMES].to_numpy(dtype=float))

    values = np.stack(annual_values, axis=0)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).sum(axis=0)
    counts = valid.sum(axis=0)
    cimis_avg = np.full(totals.shape, np.nan, dtype=float)
    np.divide(totals, counts, out=cimis_avg, where=counts > 0)

    missing_cells = (~np.isfinite(cimis_avg).all(axis=1)).sum()
    print(
        f"\nStep iii -- CIMIS averaged from Step 6 annual files "
        f"({F1_START_YEAR}-{F1_END_YEAR}) in:\n  {STEP6_CIMIS_DIR}"
    )
    print(f"  Matched {len(df_eto) - missing_cells:,} / {len(df_eto):,} cells")
    return cimis_avg


def compute_f1(hs_avg, cimis_avg, df_eto, id_cols):
    """
    Manual step iv: F1 = CIMIS_monthly_avg / Historical_Unsplit (Product_A) H-S monthly avg.
    Sets all F1 values to 1.0 for rows with missing CIMIS coverage, and also
    sets F1 = 1.0 where the denominator is zero.
    """
    # A row with any missing month is outside the CIMIS domain. Do not apply
    # a partial correction to a Historical_Unsplit (Product_A) cell that lacks CIMIS coverage.
    outside_cimis = ~np.isfinite(cimis_avg).all(axis=1)
    valid_cimis = np.isfinite(cimis_avg) & ~outside_cimis[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where(
            (hs_avg > 0) & valid_cimis,
            cimis_avg / hs_avg,
            1.0,
        )

    df_f1 = df_eto[id_cols].copy()
    for m_idx, m_name in enumerate(MONTH_NAMES):
        df_f1[m_name] = f1[:, m_idx].round(6)
    return f1, df_f1


def apply_f1_to_series(df_eto, id_cols, data_cols, f1):
    """Manual step v: multiply full time series by F1 per calendar month."""
    df_corrected = df_eto[id_cols].copy()
    for col in data_cols:
        m_name, _ = parse_col(col)
        if m_name in MONTH_NAMES:
            m_idx = MONTH_NAMES.index(m_name)
            df_corrected[col] = (df_eto[col].values * f1[:, m_idx]).round(6)
        else:
            df_corrected[col] = df_eto[col]
    return df_corrected


def main():
    print("=" * 60)
    print("Manual Step 7: F1 Adjustment Factor -- Historical_Unsplit (Product_A)")
    print(f"  F1 period   : {F1_START_YEAR}-{F1_END_YEAR}")
    print(f"  CIMIS source: Step 6 annual files ({F1_START_YEAR}-{F1_END_YEAR})")
    print("=" * 60)

    if not STEP5_CSV.exists():
        raise FileNotFoundError(
            f"Step 5 output not found. Run Step 5 first.\n  {STEP5_CSV}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_eto, id_cols, data_cols = load_step5(STEP5_CSV)
    years = [parse_col(col)[1] for col in data_cols]
    if min(years) != FULL_START_YEAR or max(years) != FULL_END_YEAR:
        raise ValueError(
            f"Step 5 input must cover exactly {FULL_START_YEAR}-{FULL_END_YEAR}; "
            f"found {min(years)}-{max(years)}"
        )
    hs_avg, df_hs_diag         = compute_hs_monthly_avg(df_eto, id_cols, data_cols)
    cimis_avg                  = load_cimis_monthly_avg(df_eto)

    print("\nStep iv -- Computing F1 = CIMIS_avg / Historical_Unsplit (Product_A) H-S avg ...")
    f1, df_f1 = compute_f1(hs_avg, cimis_avg, df_eto, id_cols)

    print("Step v  -- Applying F1 to full 1915-2018 time series ...")
    df_corrected = apply_f1_to_series(df_eto, id_cols, data_cols, f1)

    non_id = [c for c in df_corrected.columns if c not in id_cols]
    try:
        non_id = sorted(non_id, key=lambda s: datetime.strptime(s, "%b-%Y"))
    except ValueError:
        pass
    df_corrected = df_corrected[id_cols + non_id]

    out_corr = OUTPUT_DIR / "Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv"
    out_f1   = OUTPUT_DIR / "Historical_Unsplit (Product_A)_F1_table.csv"
    out_hs   = OUTPUT_DIR / "Historical_Unsplit (Product_A)_HS_monthly_avg_mmperday.csv"
    df_corrected.to_csv(out_corr, index=False)
    df_f1.to_csv(out_f1,          index=False)
    df_hs_diag.to_csv(out_hs,     index=False)

    print(f"\nF1 summary (across all {len(df_f1):,} Historical_Unsplit (Product_A) cells):")
    print(f"  {'Month':<6}  {'F1 mean':>8}  {'F1 min':>8}  {'F1 max':>8}")
    print(f"  {'-'*36}")
    for m_name in MONTH_NAMES:
        col = df_f1[m_name]
        print(f"  {m_name:<6}  {col.mean():8.4f}  {col.min():8.4f}  {col.max():8.4f}")

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print(f"  {out_corr.name}  --> input for Step 8")
    print(f"  {out_f1.name}")
    print(f"  {out_hs.name}")
    print("Done.")


if __name__ == "__main__":
    main()
