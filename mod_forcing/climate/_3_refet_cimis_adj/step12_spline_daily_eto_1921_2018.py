# -*- coding: utf-8 -*-
"""
Step 12: Monthly ETo Table and Cubic Spline Daily ETo for 1921-2018
===================================================================
Original   : step12a_build_etocum_data_1921_2018.py and the macro workbook
             step12b_CS3_Table_9-xx_ETo_Spline2025_Oct1920.xlsm (Spline, Splint,
             ETo, EToCum and EToDaily sheets driven by the createdaily macro)
Project    : Reference ETo for CalSim3 using Historical_Unsplit (Product_A) weather data
Date       : 2026

PURPOSE
-------
Turn the Step 11 monthly reference ETo into the daily ETo that Step 14 feeds
to CUP+. One run gathers the monthly series of the CUP+ areas into a single
table, saves it as the EToCum workbook, and disaggregates it into daily
values with the cubic spline of the CUP spreadsheet model. This replaces the
manual procedure in which Step 12a built the EToCum input of the macro
workbook and the workbook's createdaily macro produced its EToDaily sheet.

SERIES
------
WBA_IDS, SR_IDS and SW_IDS below list the 172 CUP+ areas: 43 WBA, 12
subregions and 117 small watersheds. CUP+ has crop tables and precipitation
only for these. Step 11 also produces 9 other subregions and 34 other small
watersheds; CUP+ has no inputs for them and Step 14 would stop on them, so
they are not carried. Each series comes from the matching Step 11 table
(WBA_02 from the WBA table, WBA_SR_15 from SR_15 of the SR table, WBA_SW_3
from SW_3 of the SW table) under the name CUP+ uses. WBA_91 has no Step 0
weight table and hence no Step 11 series: its column is left blank in the
EToCum workbook, dropped from the daily csv, and skipped by Step 14.

SPLINE: WHAT THE MACRO WORKBOOK DID (replicated here)
-----------------------------------------------------
For every series and every calendar year, independently:

  1. ETo sheet     : mean daily ETo for each month = monthly total / days in
                     the month (29 for February in a leap year).
  2. Spline sheet  : the 12 monthly means are placed at fixed mid-month
                     positions X = 61, 92, 122, 153, 183, 214, 244, 275, 305,
                     336, 366, 397 (X = 47 is January 1 and X = 411 is
                     December 31). The knots are padded with the same year's
                     November and December at X = 1 and 32 and the same year's
                     January and February at X = 426 and 457. Second
                     derivatives follow the Numerical Recipes "spline" routine
                     as written in the sheet: end derivatives 0, end
                     coefficients -0.25, and the last second derivative taken
                     directly as the last u term.
  3. Splint sheet  : the cubic is evaluated at X = 47..411 using the bracket
                     [last knot below X, next knot]. January 1 and December 31
                     both receive the mean of the two spline values, and
                     January 2-5 and December 26-30 are linear ramps between
                     those end values and the spline.
  4. createdaily   : 365 values are appended per year. In a leap year the
                     last value is repeated, so February 29 receives the
                     spline value of day 60 and December 31 a copy of the
                     December 30 value.

The spline does not preserve the monthly totals. The curve passes through
the monthly mean near the middle of each month, so the daily values of a
month sum to more than the total in the winter trough and to less in the
summer peak. Over all series and years (checked 2026-10-27) the monthly
sums differ from the totals by 1.85% on average in absolute terms, within
-5.6% to +18.2% (the extreme is a January with 0.85 in of ETo); annual sums
stay within -0.26% to +0.09%.

INPUTS
------
  GENERATED/.../_3_refet_cimis_adj/step11/
    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_WBA.csv
    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SR.csv
    Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SW.csv
      one row per region, monthly ETo totals (inches) Jan-1921 .. Dec-2018

OUTPUTS  (written to GENERATED/.../_3_refet_cimis_adj/step12/)
-------
  Historical_Unsplit (Product_A)_EToCum_1921_2018.xlsx
      sheet EToCum: Date (month end) + monthly ETo totals (inches) for 172
      series, WBA_91 blank
  Historical_Unsplit (Product_A)_EToDaily_1921_2018.csv
      Date (m/d/yyyy) + daily ETo (inches/day) for 171 series,
      1921-01-01 through 2018-12-31. Step 14 copies it to the CUP+ eto.csv.

HOW TO RUN
----------
  conda activate csstochastic
  python step12_spline_daily_eto_1921_2018.py
"""
import calendar
import pathlib
import sys

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir


gen_dir = get_module_generated_dir("mod_forcing/climate")
STEP11_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step11"
STEP12_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step12"

STEP11_FILES = {
    "WBA": STEP11_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_WBA.csv",
    "SR": STEP11_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SR.csv",
    "SW": STEP11_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_timeseries_per_SW.csv",
}
ETOCUM_XLSX = STEP12_DIR / "Historical_Unsplit (Product_A)_EToCum_1921_2018.xlsx"
SHEET_NAME = "EToCum"
DAILY_CSV = STEP12_DIR / "Historical_Unsplit (Product_A)_EToDaily_1921_2018.csv"

START_YEAR = 1921
END_YEAR = 2018
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# The CUP+ areas. CUP+ has crop tables and precipitation only for these, and
# Step 14 stops on any other series, so the rest of Step 11 is not carried.
WBA_IDS = ["02", "03", "04", "05", "06", "07N", "07S", "08N", "08S", "09", "10",
           "11", "12", "13", "14", "15N", "15S", "16", "17N", "17S", "18", "19",
           "20", "21", "22", "23", "24", "25", "26N", "26S", "50", "60N", "60S",
           "61", "62", "63", "64", "71", "72", "73", "90",
           "91",        # no Step 0 weight table, so no Step 11 series: left blank
           "DETAW"]
SR_IDS = [1, 2, 6, 8, 10, 15, 16, 17, 18, 19, 20, 21]
SW_IDS = [3, 5, *range(6, 16), 20, 21, 25, 26, 28, 29, *range(30, 125), *range(126, 130)]

# Spline sheet, column E (X(I%)): Nov, Dec, Jan..Dec, Jan, Feb knot positions
KNOT_X = np.array([1, 32, 61, 92, 122, 153, 183, 214, 244, 275, 305, 336,
                   366, 397, 426, 457], dtype=float)
YP1 = 0.0                         # Spline!I1
YPN = 0.0                         # Spline!I2
END_COEFFICIENT = -0.25           # Spline!J4 and Spline!J19
FIRST_DAY_X = 47                  # Splint row 50, January 1
LAST_DAY_X = 411                  # Splint row 414, December 31
RAMP_DAYS = 5                     # Splint!R50 and Splint!R414 divide by 5


def month_ends():
    return pd.date_range(
        f"{START_YEAR}-01-01",
        periods=(END_YEAR - START_YEAR + 1) * 12,
        freq=pd.offsets.MonthEnd(),
    )


def month_columns():
    return [f"{month}-{year}" for year in range(START_YEAR, END_YEAR + 1)
            for month in MONTHS]


# ---------------------------------------------------------------------------
# Step 11 monthly series -> monthly table (EToCum workbook)
# ---------------------------------------------------------------------------
def load_step11_tables():
    """Step 11 monthly tables keyed by group ("WBA", "SR", "SW"), one row per region."""
    columns = month_columns()
    tables = {}
    for group, path in STEP11_FILES.items():
        id_column = f"{group}_ID"
        df = pd.read_csv(path, dtype={id_column: str})
        if list(df.columns) != [id_column] + columns:
            raise ValueError(
                f"{path.name} must contain {id_column} followed by the monthly columns "
                f"Jan-{START_YEAR} through Dec-{END_YEAR}."
            )
        tables[group] = df.set_index(id_column)
    return tables


def series_sources():
    """(CUP+ series name, Step 11 group, region id) for every series."""
    return ([(f"WBA_{wba}", "WBA", wba) for wba in WBA_IDS]
            + [(f"WBA_SR_{n}", "SR", f"SR_{n}") for n in SR_IDS]
            + [(f"WBA_SW_{n}", "SW", f"SW_{n}") for n in SW_IDS])


def build_monthly_table():
    """Monthly ETo totals (inches), month end index, one column per series.

    A series with no Step 11 data (WBA_91) is left blank.
    """
    tables = load_step11_tables()
    columns = {}
    for name, group, region in series_sources():
        table = tables[group]
        columns[name] = (table.loc[region].to_numpy(dtype=float)
                         if region in table.index else np.nan)
    return pd.DataFrame(columns, index=month_ends())


def write_etocum_workbook(monthly):
    output = monthly.reset_index(names="Date")
    with pd.ExcelWriter(ETOCUM_XLSX, engine="openpyxl", datetime_format="m/d/yyyy") as writer:
        output.to_excel(writer, sheet_name=SHEET_NAME, index=False)
        sheet = writer.sheets[SHEET_NAME]
        sheet.freeze_panes = "B2"
        sheet.column_dimensions["A"].width = 14


# ---------------------------------------------------------------------------
# monthly table -> daily ETo
# ---------------------------------------------------------------------------
def second_derivatives(y):
    """Spline!K4:K19 for knot values y of shape (16, n_series)."""
    x = KNOT_X
    n_knots = len(x)
    u = np.zeros_like(y)
    y2 = np.zeros_like(y)
    u[0] = (3 / (x[1] - x[0])) * ((y[1] - y[0]) / (x[1] - x[0]) - YP1)
    y2[0] = END_COEFFICIENT
    for i in range(1, n_knots - 1):
        sig = (x[i] - x[i - 1]) / (x[i + 1] - x[i - 1])
        p = sig * y2[i - 1] + 2
        u[i] = (6 * (((y[i + 1] - y[i]) / (x[i + 1] - x[i]))
                     - ((y[i] - y[i - 1]) / (x[i] - x[i - 1])))
                / (x[i + 1] - x[i - 1]) - sig * u[i - 1]) / p
        y2[i] = (sig - 1) / p
    u[-1] = (3 / (x[-1] - x[-2])) * (YPN - (y[-1] - y[-2])) / (x[-1] - x[-2])
    k = np.zeros_like(y)
    k[-1] = u[-1]                 # Spline!K19 = J19 * K20 + I19 with K20 blank
    for i in range(n_knots - 2, -1, -1):
        k[i] = y2[i] * k[i + 1] + u[i]
    return k


def spline_daily(monthly_means):
    """Splint!T50:T414 for monthly means of shape (12, n_series) -> (365, n_series)."""
    y = np.vstack([monthly_means[10:12], monthly_means, monthly_means[0:2]])
    k = second_derivatives(y)

    day_x = np.arange(FIRST_DAY_X, LAST_DAY_X + 1, dtype=float)
    khi = np.searchsorted(KNOT_X, day_x, side="left")     # first knot >= X
    klo = khi - 1
    h = KNOT_X[khi] - KNOT_X[klo]
    a = (KNOT_X[khi] - day_x) / h
    b = (day_x - KNOT_X[klo]) / h
    linear = a[:, None] * y[klo] + b[:, None] * y[khi]
    cubic = linear + (((a ** 3 - a)[:, None] * k[klo]
                       + (b ** 3 - b)[:, None] * k[khi])) * (h ** 2)[:, None] / 6

    daily = cubic.copy()
    first, last = 0, LAST_DAY_X - FIRST_DAY_X
    daily[first] = (cubic[first] + cubic[last]) / 2
    daily[last] = (cubic[first] + cubic[last]) / 2
    ramp_start = (cubic[first + RAMP_DAYS] - daily[first]) / RAMP_DAYS
    for i in range(first + 1, first + RAMP_DAYS):
        daily[i] = daily[i - 1] + ramp_start
    ramp_end = (daily[last] - cubic[last - RAMP_DAYS - 1]) / RAMP_DAYS
    for i in range(last - RAMP_DAYS, last):
        daily[i] = daily[i - 1] + ramp_end
    return daily


def disaggregate(monthly):
    """Daily ETo (inches/day) for every year of the monthly totals table."""
    blocks = []
    for year in range(START_YEAR, END_YEAR + 1):
        days = np.array([calendar.monthrange(year, month)[1] for month in range(1, 13)],
                        dtype=float)
        daily = spline_daily(monthly.loc[str(year)].to_numpy(dtype=float) / days[:, None])
        if calendar.isleap(year):
            daily = np.vstack([daily, daily[-1:]])     # Splint!T415 = N414
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        blocks.append(pd.DataFrame(daily, index=dates, columns=monthly.columns))
    return pd.concat(blocks)


def write_daily_csv(daily):
    """Date column as m/d/yyyy, the format Step 14 expects, followed by the series."""
    output = daily.copy()
    output.insert(0, "Date", [f"{d.month}/{d.day}/{d.year}" for d in output.index])
    output.to_csv(DAILY_CSV, index=False)


def main():
    monthly = build_monthly_table()
    blank = [name for name in monthly.columns if monthly[name].isna().all()]
    STEP12_DIR.mkdir(parents=True, exist_ok=True)
    write_etocum_workbook(monthly)
    print(f"EToCum workbook saved: {ETOCUM_XLSX}")
    print(f"Rows: {len(monthly)} ({monthly.index[0].date()} through {monthly.index[-1].date()})")
    print(f"Series: {monthly.shape[1] - len(blank)} populated; left blank (no Step 11 series): {blank}")

    daily = disaggregate(monthly.drop(columns=blank))
    write_daily_csv(daily)
    print(f"Daily ETo saved: {DAILY_CSV}")
    print(f"Rows: {len(daily)} ({daily.index[0].date()} through {daily.index[-1].date()})")
    print(f"Series: {daily.shape[1]}; dropped blank series: {blank}")


if __name__ == "__main__":
    main()
