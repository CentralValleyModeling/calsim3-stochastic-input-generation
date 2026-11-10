# -*- coding: utf-8 -*-
"""
Step 10b: Extended F1 Adjustment and Corrected Ref ETo -- Product_A
========================================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 7.0
Original   : CS3Domain_F1_Calculation_for_Ref_ETo.xlsx (manual spreadsheet steps i-v)
Project    : Reference ETo for CalSim3 using Product_A weather data
Author     : DWR
Date       : 2026

EXTENDED MANUAL STEP 7 PROCEDURE (Sections 7.3 i-v)
-------------------------------------------
  i.   Copy Step 5 H-S ETo time series into Excel (CS3_Domain_ETo_PRISM_HS_Monthly sheet).
  ii.  Compute long-term monthly average H-S ETo for 2004-2021
       (MonthlyAvgPRISM_HSETo_2004_2021 sheet) -- this is the DENOMINATOR of F1.
  iii. Copy Step 6 CIMIS monthly averages into Excel
       (MonthlyAvgSpatialCIMIS_ETo sheet) -- this is the NUMERATOR of F1.
  iv.  Compute F1 = CIMIS_monthly_avg / HS_monthly_avg  per cell per month.
  v.   Multiply full H-S time series by F1 to get corrected ETo.

Product_A Adaptation
---------------------
Steps i-v must be recomputed using Product_A values.
The pre-computed F1 in the Excel (Factor(F1) sheet) CANNOT be used directly
because its denominator is PRISM H-S averages, not Product_A H-S averages.
The bias F1 corrects depends on how well H-S performs with the actual
temperature inputs; PRISM and Product_A temperatures
differ, so their H-S estimates differ, and F1 must be recomputed accordingly.

  Step i  (manual -> this script):
        Load full Product_A H-S ETo time series from Step 10a's generated output.

  Step ii (manual -> this script):
    Compute monthly average Product_A H-S ETo over the overlap period
        2004-2018 for the F1 denominator.
    Units: convert inches/month to mm/day for the F1 ratio.
    Separately compute the 1920-2018 H-S average for Step 10c maps.

    Step iii (manual -> this script):
        Read Step 6 annual CIMIS files from the generated Step 6 output and average
        2004-2018 by month, the available overlap with CIMIS. The files are already
        at Product_A grid points.

  Step iv (manual -> this script):
    F1 = CIMIS_monthly_avg / Product_A H-S monthly avg per cell per month.

  Step v  (manual -> this script):
    Multiply the full Product_A H-S time series (1920-2018) by F1.

INPUTS
------
    Step 10a output: GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step10/
        Product_A_ETo_monthly_inpermonth.csv (inches/month, 1920-2018)
    Step 6 annual CIMIS files: GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/
        step6/CIMIS_MonthlyAvg_ETo/CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_YYYY.csv

    Step 0 WTable files are not inputs to Step 10b. They contain polygon weights
    used later by Step 8; Step 10b instead uses the same underlying grid coordinates.

OUTPUTS (written to GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step10/)
-----------------------------
    Product_A_ETo_F1corrected_monthly_inpermonth.csv
      Same structure as Step 10a output (Lon Lat Jan-1920 ... Dec-2018).
      Each value multiplied by its cell+month F1 factor.
      Units: inches/month  --> input for Step 11a

    Product_A_F1_table.csv
    The F1 factor computed for each Product_A cell and each calendar month.
      Lon, Lat, Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec

    Product_A_HS_monthly_avg_mmperday.csv
    Diagnostic: uncorrected H-S monthly avg (1920-2018) for Step 10c maps.

    Product_A_HS_monthly_avg_mmperday_2004_2018.csv
    Diagnostic: uncorrected H-S monthly avg (2004-2018) used as F1 denominator.

ENVIRONMENT
-----------
    conda activate eto_env  (pandas + numpy required)

HOW TO RUN
----------
    python step10b_apply_f1_adjustment_1921_2018.py
    Prerequisites: Step 10a must be run first.
                                 Step 6 annual CIMIS files for 2004-2018 must be generated.
"""

import calendar
import sys
import pathlib
from datetime import datetime

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir

# =============================================================================
# CONFIGURATION
# =============================================================================

gen_dir = get_module_generated_dir("mod_forcing/climate")

STEP10A_CSV = (
    gen_dir / "output" / "_3_refet_cimis_adj" / "step10"
    / "Product_A_ETo_monthly_inpermonth.csv"
)

STEP6_CIMIS_DIR = (
    gen_dir / "output" / "_3_refet_cimis_adj" / "step6"
    / "CIMIS_MonthlyAvg_ETo"
)

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step10"

# Both F1 averages use the overlapping CIMIS and H-S period.
F1_START_YEAR = 2004
F1_END_YEAR   = 2018
FULL_START_YEAR = 1920
FULL_END_YEAR   = 2018

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
               "Jul","Aug","Sep","Oct","Nov","Dec"]

# =============================================================================


def parse_col(col):
    """Return (month_name, year) from a column like 'Jan-1915'."""
    parts = col.split("-")
    return parts[0], int(parts[1])


def load_step5(csv_path):
    print(f"Reading Step 10a ETo from:\n  {csv_path}")
    df = pd.read_csv(csv_path)
    id_cols   = ["Lon", "Lat"]
    data_cols = [c for c in df.columns if c not in id_cols]
    print(f"  Cells: {len(df):,}  Monthly columns: {len(data_cols):,}")
    return df, id_cols, data_cols


def compute_hs_monthly_avg(df_eto, id_cols, data_cols, start_year, end_year):
    """
    Compute monthly average H-S ETo (mm/day) over the specified years.
    Returns array shape (n_cells, 12) in mm/day and a diagnostic DataFrame.
    """
    print(f"\nStep ii -- Product_A H-S monthly avg ({start_year}-{end_year}) ...")
    n_cells = len(df_eto)
    hs_sum  = np.zeros((n_cells, 12))
    counts  = np.zeros(12, dtype=int)

    for col in data_cols:
        m_name, yr = parse_col(col)
        if m_name not in MONTH_NAMES:
            continue
        if not (start_year <= yr <= end_year):
            continue
        m_idx = MONTH_NAMES.index(m_name)
        days  = calendar.monthrange(yr, m_idx + 1)[1]
        hs_sum[:, m_idx] += df_eto[col].values * 25.4 / days  # inches/month -> mm/day
        counts[m_idx]    += 1

    expected_count = end_year - start_year + 1
    if not np.all(counts == expected_count):
        raise ValueError(
            f"H-S ETo must contain every month from {start_year} through {end_year}; "
            f"found monthly counts {counts.tolist()}."
        )
    hs_avg = hs_sum / counts
    print(f"  Years averaged per month: {counts.tolist()}")

    df_diag = df_eto[id_cols].copy()
    for m_idx, m_name in enumerate(MONTH_NAMES):
        df_diag[m_name] = hs_avg[:, m_idx].round(4)
    return hs_avg, df_diag


def load_cimis_monthly_avg(df_eto):
    """
    Average Step 6 annual CIMIS monthly averages over the F1 overlap period.
    Returns an (n_cells, 12) array in mm/day.
    """
    years = range(F1_START_YEAR, F1_END_YEAR + 1)
    annual_paths = {
        year: STEP6_CIMIS_DIR / f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}.csv"
        for year in years
    }
    missing_paths = [path for path in annual_paths.values() if not path.is_file()]
    if missing_paths:
        missing_list = "\n  ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(
            f"Missing Step 6 annual CIMIS files for {F1_START_YEAR}-{F1_END_YEAR}:\n"
            f"  {missing_list}\n"
            "Make the files available locally or sync them, then rerun Step 10b."
        )

    annual_values = []
    required_columns = ["Lon", "Lat"] + MONTH_NAMES
    for year, csv_path in annual_paths.items():
        df_c = pd.read_csv(csv_path).rename(columns={"lon": "Lon", "lat": "Lat"})
        missing_columns = [column for column in required_columns if column not in df_c.columns]
        if missing_columns:
            raise ValueError(f"Missing columns {missing_columns} in Step 6 file:\n  {csv_path}")
        df_merged = df_eto[["Lon", "Lat"]].merge(
            df_c[required_columns],
            on=["Lon", "Lat"], how="left", validate="one_to_one"
        )
        annual_values.append(df_merged[MONTH_NAMES].to_numpy(dtype=float))

    values = np.stack(annual_values, axis=0)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).sum(axis=0)
    counts = valid.sum(axis=0)
    cimis_avg = np.full(totals.shape, np.nan, dtype=float)
    np.divide(totals, counts, out=cimis_avg, where=counts > 0)

    missing = (~np.isfinite(cimis_avg).all(axis=1)).sum()
    print(
        f"\nStep iii -- CIMIS averaged from Step 6 annual files ({F1_START_YEAR}-{F1_END_YEAR}):\n"
        f"  {STEP6_CIMIS_DIR}"
    )
    print(f"  Matched {len(df_eto) - missing:,} / {len(df_eto):,} cells")
    return cimis_avg


def compute_f1(hs_avg, cimis_avg, df_eto, id_cols):
    """
    Manual step iv: F1 = CIMIS_monthly_avg / Product_A H-S monthly avg.
    Sets all F1 values to 1.0 for rows with missing CIMIS coverage, and also
    sets F1 = 1.0 where the denominator is zero.
    """
    # A row with any missing month is outside the CIMIS domain. Do not apply
    # a partial correction to a Product_A cell that lacks CIMIS coverage.
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
    print("Step 10b: Extended F1 Adjustment -- Product_A")
    print(f"  F1 H-S and CIMIS averages: {F1_START_YEAR}-{F1_END_YEAR}")
    print(f"  H-S map average         : {FULL_START_YEAR}-{FULL_END_YEAR}")
    print(f"  CIMIS source: Step 6 annual files ({F1_START_YEAR}-{F1_END_YEAR})")
    print("=" * 60)

    if not STEP10A_CSV.exists():
        raise FileNotFoundError(
            f"Step 10a output not found. Run Step 10a first.\n  {STEP10A_CSV}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_eto, id_cols, data_cols = load_step5(STEP10A_CSV)
    years = [parse_col(col)[1] for col in data_cols]
    if min(years) != FULL_START_YEAR or max(years) != FULL_END_YEAR:
        raise ValueError(
            f"Step 10a input must cover exactly {FULL_START_YEAR}-{FULL_END_YEAR}; "
            f"found {min(years)}-{max(years)}"
        )
    hs_avg, df_hs_f1_diag = compute_hs_monthly_avg(
        df_eto, id_cols, data_cols, F1_START_YEAR, F1_END_YEAR
    )
    _, df_hs_diag = compute_hs_monthly_avg(
        df_eto, id_cols, data_cols, FULL_START_YEAR, FULL_END_YEAR
    )
    cimis_avg = load_cimis_monthly_avg(df_eto)

    print("\nStep iv -- Computing F1 = CIMIS_avg / Product_A H-S avg ...")
    f1, df_f1 = compute_f1(hs_avg, cimis_avg, df_eto, id_cols)

    print(f"Step v  -- Applying F1 to full {FULL_START_YEAR}-{FULL_END_YEAR} time series ...")
    df_corrected = apply_f1_to_series(df_eto, id_cols, data_cols, f1)

    non_id = [c for c in df_corrected.columns if c not in id_cols]
    try:
        non_id = sorted(non_id, key=lambda s: datetime.strptime(s, "%b-%Y"))
    except ValueError:
        pass
    df_corrected = df_corrected[id_cols + non_id]

    out_corr = OUTPUT_DIR / "Product_A_ETo_F1corrected_monthly_inpermonth.csv"
    out_f1   = OUTPUT_DIR / "Product_A_F1_table.csv"
    out_hs   = OUTPUT_DIR / "Product_A_HS_monthly_avg_mmperday.csv"
    out_hs_f1 = OUTPUT_DIR / (
        f"Product_A_HS_monthly_avg_mmperday_{F1_START_YEAR}_{F1_END_YEAR}.csv"
    )
    df_corrected.to_csv(out_corr, index=False)
    df_f1.to_csv(out_f1,          index=False)
    df_hs_diag.to_csv(out_hs,     index=False)
    df_hs_f1_diag.to_csv(out_hs_f1, index=False)

    print(f"\nF1 summary (across all {len(df_f1):,} Product_A cells):")
    print(f"  {'Month':<6}  {'F1 mean':>8}  {'F1 min':>8}  {'F1 max':>8}")
    print(f"  {'-'*36}")
    for m_name in MONTH_NAMES:
        col = df_f1[m_name]
        print(f"  {m_name:<6}  {col.mean():8.4f}  {col.min():8.4f}  {col.max():8.4f}")

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print(f"  {out_corr.name}  --> input for Step 11a")
    print(f"  {out_f1.name}")
    print(f"  {out_hs.name}")
    print(f"  {out_hs_f1.name}")
    print("Done.")


if __name__ == "__main__":
    main()
