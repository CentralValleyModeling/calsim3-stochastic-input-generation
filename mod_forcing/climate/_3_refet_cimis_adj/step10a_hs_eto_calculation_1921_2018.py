# -*- coding: utf-8 -*-
"""
Manual Step 5.0: Ref ETo Calculation (Hargreaves-Samani Equation) -- Historical_Unsplit (Product_A)
================================================================================
Manual ref : User_Manual_CS3_Domain_v2.pdf, Section 5.0
Original   : H-S_RefETo_PRISM_optimized_lat_lon_monthlyavg_Ra_v4_final_mod.py
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Author     : DWR
Date       : 2026

MANUAL STEP 5 PURPOSE (from manual Section 5.1)
------------------------------------------------
Calculate reference evapotranspiration (ETo) using temperature data.
The script processes station metadata, extracts temperature values,
computes solar radiation (Ra), and derives daily and monthly ETo values.

Historical_Unsplit (Product_A) Adaptation
---------------------
    Manual (PRISM)                     | Historical_Unsplit (Product_A)
  -----------------------------------|------------------------------------------
  Station metadata from DBF/CSV      | Lat/lon parsed from data_{lat}_{lon} filenames
  Monthly Tmax/Tmin wide-format CSVs | Daily Tmax/Tmin per-cell text files
  Monthly Ra * monthly mean temps    | Daily Ra * daily temps -> sum to monthly
    Date range: 1920-2023              | Date range: 1921-2018 final output

HARGREAVES-SAMANI FORMULA (unchanged)
---------------------------------------
    ETo (mm/day) = 0.0023 * Ra * (Tmean + 17.8) * sqrt(Tmax - Tmin)
    Ra = extraterrestrial radiation (MJ/m2/day) / 2.45
    Period = 365.25 days (matches original VBA implementation)

INPUTS
------
    Historical_Unsplit (Product_A) directory:
    Each file: data_{lat}_{lon}  (whitespace-separated, no header)
    Columns  : Year  Month  Day  Precip(mm)  Tmax(C)  Tmin(C)
    Period   : 1915-01-01 to 2018-12-31; output is limited to 1921-2018

OUTPUTS  (written to output/)
------------------------------
    Historical_Unsplit (Product_A)_ETo_monthly_inpermonth.csv
    rows = grid cells, cols = Lon Lat Jan-1921 Feb-1921 ... Dec-2018
      units: inches/month  --> input for Step 6-7 (F1 correction)

    Historical_Unsplit (Product_A)_monthly_Ra.csv
      rows = grid cells, cols = Lon Lat Jan Feb ... Dec
      monthly average Ra from 1921 reference year

    Historical_Unsplit (Product_A)_daily_Ra_1921.csv
      long format: Lon Lat Date Daily_Ra  (365 rows per cell)

ENVIRONMENT
-----------
  conda env create -f environment.yml
  conda activate eto_env

HOW TO RUN
----------
  python step5_hs_eto_calculation.py
  Runtime: ~5-20 min (all CPU cores used via multiprocessing)
"""

import os
import re
import sys
import pathlib
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count

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

GRID_DATA_DIR = base_dir / "WGEN" / "Historical_Unsplit"

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step10"

START_DATE = "1921-01-01"
END_DATE   = "2018-12-31"

# =============================================================================

_DAYS_1921 = [datetime(1921, 1, 1) + timedelta(days=i) for i in range(365)]
_CUM_DAYS  = np.insert(
    np.cumsum([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]), 0, 0
)
_MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun",
                "Jul","Aug","Sep","Oct","Nov","Dec"]


def calculate_ra_vectorized(lat_deg, dates):
    """Ra (MJ/m2/day) / lambda=2.45 -- period=365.25 matches original VBA."""
    phi     = np.radians(lat_deg)
    J       = np.array([d.timetuple().tm_yday for d in dates], dtype=float)
    dr      = 1 + 0.033 * np.cos(2 * np.pi * J / 365.25)
    delta   = 0.409 * np.sin(2 * np.pi * J / 365.25 - 1.39)
    omega_s = np.arccos(-np.tan(phi) * np.tan(delta))
    Ra_mj   = (24 * 60 / np.pi) * 0.0820 * dr * (
        omega_s * np.sin(phi) * np.sin(delta)
        + np.cos(phi) * np.cos(delta) * np.sin(omega_s)
    )
    return Ra_mj / 2.45


def scan_grid_files(data_dir):
    pattern = re.compile(r"^data_([-\d.]+)_([-\d.]+)$")
    cells = []
    for fname in os.listdir(data_dir):
        m = pattern.match(fname)
        if m:
            cells.append({
                "lat":  float(m.group(1)),
                "lon":  float(m.group(2)),
                "path": str(data_dir / fname),
            })
    return cells


def process_cell(cell):
    lat, lon = cell["lat"], cell["lon"]
    try:
        df = pd.read_csv(
            cell["path"], sep=r"\s+", header=None,
            names=["year","month","day","precip","tmax","tmin"],
            dtype={"year":int,"month":int,"day":int,
                   "precip":float,"tmax":float,"tmin":float},
        )
        df["date"] = pd.to_datetime(df[["year","month","day"]])
        df = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)].reset_index(drop=True)
    except Exception as exc:
        print(f"  [SKIP] {os.path.basename(cell['path'])}: {exc}")
        return None

    if df.empty:
        return None

    dates    = df["date"].tolist()
    ra_daily = calculate_ra_vectorized(lat, dates)
    delta_t  = np.maximum(df["tmax"].values - df["tmin"].values, 0.0)
    tmean    = (df["tmax"].values + df["tmin"].values) / 2.0
    eto_mm   = np.where(delta_t > 0,
                        0.0023 * ra_daily * (tmean + 17.8) * np.sqrt(delta_t), 0.0)

    df["eto_mm"] = eto_mm
    monthly_eto = {
        period.strftime("%b-%Y"): round(float(total) / 25.4, 4)
        for period, total in df.groupby(df["date"].dt.to_period("M"))["eto_mm"].sum().items()
    }

    ra_1921    = calculate_ra_vectorized(lat, _DAYS_1921)
    monthly_ra = {
        name: round(float(np.mean(ra_1921[_CUM_DAYS[i]:_CUM_DAYS[i+1]])), 4)
        for i, name in enumerate(_MONTH_NAMES)
    }
    daily_ra_rows = [
        [lon, lat, _DAYS_1921[i].strftime("%Y-%m-%d"), round(float(ra_1921[i]), 4)]
        for i in range(365)
    ]

    base = {"Lon": lon, "Lat": lat}
    return (
        {**base, **monthly_eto},
        {**base, **monthly_ra},
        daily_ra_rows,
    )


def main():
    print("=" * 60)
    print("Manual Step 5: H-S ETo Calculation -- Historical_Unsplit (Product_A)")
    print(f"Period: {START_DATE}  to  {END_DATE}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nScanning grid files:\n  {GRID_DATA_DIR}")
    cells = scan_grid_files(GRID_DATA_DIR)
    if not cells:
        raise FileNotFoundError(f"No data_{{lat}}_{{lon}} files found in:\n  {GRID_DATA_DIR}")
    print(f"  Found {len(cells):,} cells")

    # OneDrive cloud-only placeholders have zero size; catch this before the
    # multiprocessing pool silently skips thousands of files with Errno 22.
    placeholder = [c for c in cells if os.path.getsize(c["path"]) == 0]
    if placeholder:
        raise OSError(
            f"\n{len(placeholder):,} of {len(cells):,} grid files are OneDrive "
            f"cloud-only placeholders (0 bytes).\n"
            "Fix: right-click the Historical_Unsplit folder in File Explorer\n"
            "     → 'Always keep on this device'  and wait for OneDrive to sync.\n"
            f"Example file: {os.path.basename(placeholder[0]['path'])}"
        )

    print(f"\nProcessing with {cpu_count()} workers ...")
    with Pool() as pool:
        results = pool.map(process_cell, cells)
    results = [r for r in results if r is not None]
    print(f"  {len(results):,} cells completed")

    df_meto = pd.DataFrame([r[0] for r in results])
    id_cols = ["Lon", "Lat"]
    date_cols = sorted(
        [c for c in df_meto.columns if c not in id_cols],
        key=lambda s: datetime.strptime(s, "%b-%Y"),
    )
    df_meto = df_meto[id_cols + date_cols]

    df_mra = pd.DataFrame([r[1] for r in results])
    df_dra = pd.DataFrame(
        sum([r[2] for r in results], []),
        columns=["Lon","Lat","Date","Daily_Ra"],
    )

    df_meto.to_csv(OUTPUT_DIR / "Historical_Unsplit (Product_A)_ETo_monthly_inpermonth.csv", index=False)
    df_mra.to_csv(OUTPUT_DIR / "Historical_Unsplit (Product_A)_monthly_Ra.csv",             index=False)
    df_dra.to_csv(OUTPUT_DIR / "Historical_Unsplit (Product_A)_daily_Ra_1921.csv",          index=False)

    print(f"\nOutputs written to: {OUTPUT_DIR}")
    print("  Historical_Unsplit (Product_A)_ETo_monthly_inpermonth.csv  --> input for Step 6-7")
    print("  Historical_Unsplit (Product_A)_monthly_Ra.csv")
    print("  Historical_Unsplit (Product_A)_daily_Ra_1921.csv")
    print("Done.")


if __name__ == "__main__":
    main()
