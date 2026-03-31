#!/usr/bin/env python
"""
Compute Oroville rule-curve target storage from wetness index.

Inputs:
  1) <GENERATED>/mod_reservoir/storage_curves/output/_3_oroville_daily_precip/
     Oroville_Daily_Precip_ProductA_Scenario1.csv
      year, month, day, precip_inches

  2) <BASE>/CalSim3/__calsim_sv_default__.dss
     Part B: S_OROVLLEVEL5, Part C: STORAGE-LEVEL (monthly end-of-month series)

Wetness index:
  x_t = 0.97 * x_{t-1} + p_t
  where x_init_prevday is x on the day BEFORE the first record.
  So, first day uses: x[0] = 0.97 * x_init_prevday + precip[0]

Storage rule curve (Eq. interpretation with fixed dates):
  Let Smax = summer_pool_taf (constant)
  Let Smin(x_t) = Smax - reservation_TAF(x_t)

  For each day t (using season-year boundaries Sep15/Oct15/Mar31):
    - Sep15 <= t < Oct15: ramp from Smax down to Smin(x_t)
    - Oct15 <= t < Mar31: Smin(x_t)
    - Mar31 <= t < Sep15: min(Smax, Smin(x_t) + b*(t - Mar31))

Wetness-to-reservation method:
  Endpoints-only interpolation:
    compute reservation using ONLY endpoints:
      (3.5, 368.2) and (11.0, 737.3)
    i.e., linearly interpolate for wetness in (3.5, 11) and clamp outside.

Outputs:
  - Product A CSV:
      _product_a_validation/S_OROVLLEVEL5_productA_<WY1>_<WY2>.csv
        columns: Part B, Part C, Year, Month, Value
  - Excel workbook:
      oroville_level5.xlsx
        * sheet "daily": date, wetness_index, S_target_TAF
        * sheet "monthly": month_end, S_OROVLLEVEL5, S_target_eom_TAF
        * sheet "compare_level5": diffs vs Level-5
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

_gen = get_module_generated_dir("mod_reservoir/storage_curves")
INPUT_DIR = _gen / "output" / "_3_oroville_daily_precip"
OUTPUT_DIR = _gen / "output" / "_4_oroville_level5"
VALIDATION_DIR = _gen / "output" / "_product_a_validation"
DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"


def load_daily_precip_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df = df.copy()
    df["date"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=df["day"]))
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "precip_inches"]]


def load_level5(dss_path: Path, part_b: str = "S_OROVLLEVEL5",
                part_c: str = "STORAGE-LEVEL") -> pd.DataFrame:
    """Read S_OROVLLEVEL5 monthly series from a CalSim DSS file."""
    target_bc = (part_b.upper(), part_c.upper())
    with HecDss.Open(str(dss_path), version=6) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*/")
        matched = [
            p for p in all_paths
            if (p.strip("/").split("/")[1].upper(),
                p.strip("/").split("/")[2].upper()) == target_bc
        ]
        if not matched:
            raise ValueError(
                f"No DSS path found for B={part_b}, C={part_c} in {dss_path}"
            )
        master = {}
        for p in sorted(matched, key=lambda x: x.strip("/").split("/")[3]):
            ts = dss.read_ts(p, trim_missing=True)
            vals = np.asarray(ts.values, dtype=float)
            vals[vals <= -900] = np.nan
            idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
            master.update(pd.Series(vals, index=idx).to_dict())

    series = pd.Series(master, dtype=float).sort_index().dropna()
    return pd.DataFrame({"month_end": series.index, "S_OROVLLEVEL5": series.values})


def compute_wetness_index(precip: np.ndarray, x_init_prevday: float, a: float = 0.97) -> np.ndarray:
    """
    x_t = a*x_{t-1} + p_t

    First day:
      x[0] = a * x_init_prevday + precip[0]
    """
    precip = np.asarray(precip, dtype=float)
    x = np.zeros_like(precip, dtype=float)
    if precip.size == 0:
        return x

    x[0] = a * float(x_init_prevday) + precip[0]
    for i in range(1, len(precip)):
        x[i] = a * x[i - 1] + precip[i]
    return x


def compute_target_storage(
    dates: np.ndarray,
    smin: np.ndarray,
    smax: float,
    b_taf_per_day: float,
) -> np.ndarray:
    """
    Eq. (13) style seasonal rule curve using fixed dates (Sep15, Oct15, Mar31),
    with season-year handling so Oct15->Mar31 spans across calendar years.
    """
    S = np.zeros(len(dates), dtype=float)

    for i, d in enumerate(dates):
        # "season_year" = year containing Sep15 that STARTS the cycle for this date
        # If date is before Sep15 in a calendar year, it belongs to the cycle that started Sep15 of prior year.
        season_year = d.year if d >= dt.datetime(d.year, 9, 15) else d.year - 1

        sep15 = dt.datetime(season_year, 9, 15)
        oct15 = dt.datetime(season_year, 10, 15)
        mar31 = dt.datetime(season_year + 1, 3, 31)
        sep15_next = dt.datetime(season_year + 1, 9, 15)

        if sep15 <= d < oct15:
            # ramp down from Smax at Sep15 to Smin(x_t) at Oct15
            frac = (d - sep15).days / (oct15 - sep15).days
            S[i] = smax + frac * (smin[i] - smax)
        elif oct15 <= d < mar31:
            # flood season constant at Smin(x_t)
            S[i] = smin[i]
        else:
            # mar31 <= d < sep15_next  (refill/summer capped by Smax)
            days_since = (d - mar31).days  # Mar31 => 0
            S[i] = min(smax, smin[i] + b_taf_per_day * days_since)

    return S


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--input-dir", default=str(INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))

    parser.add_argument(
        "--daily-csv",
        default="Oroville_Daily_Precip_ProductA_Scenario1.csv",
        help="Daily precip input CSV filename (inside input-dir)",
    )
    parser.add_argument(
        "--dss-file",
        default=str(DEFAULT_DSS),
        help="CalSim DSS file containing S_OROVLLEVEL5",
    )

    parser.add_argument("--summer-pool-taf", type=float, default=3425.2)
    parser.add_argument("--b-taf-per-day", type=float, default=10.0)
    parser.add_argument("--xinit-prevday", type=float, default=3.5, help="Wetness index on day BEFORE first record (used only for first day)")

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_path = input_dir / args.daily_csv
    dss_path = Path(args.dss_file)

    for p in [daily_path, dss_path]:
        if not p.exists():
            raise FileNotFoundError(f"Required input not found: {p}")

    daily_in = load_daily_precip_csv(daily_path)
    level5 = load_level5(dss_path)

    dates = daily_in["date"].dt.to_pydatetime()
    precip = daily_in["precip_inches"].fillna(0.0).to_numpy(dtype=float)

    wet = compute_wetness_index(precip=precip, x_init_prevday=float(args.xinit_prevday), a=0.97)
    smax = float(args.summer_pool_taf)

    # -----------------
    # Endpoints-only interpolation
    # -----------------
    # reservation(wet) from ONLY two points:
    #   wet<=3.5 => 368.2
    #   wet>=11  => 737.3
    # linear in between
    res = np.interp(wet, [3.5, 11.0], [368.2, 737.3]).astype(float)

    smin = smax - res
    S_target = compute_target_storage(
        dates=np.array(dates, dtype=object),
        smin=smin,
        smax=smax,
        b_taf_per_day=float(args.b_taf_per_day),
    )

    # -----------------
    # Daily output (minimal)
    # -----------------
    daily_out = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "wetness_index": wet,
            "S_target_TAF": S_target,
        }
    )

    # -----------------
    # Monthly EOM -> Product A CSV
    # -----------------
    tmp = daily_out.set_index("date")
    monthly = tmp.resample("M").agg(
        S_target_eom_TAF=("S_target_TAF", "last"),
    ).reset_index().rename(columns={"date": "month_end"})

    # Merge with historical Level-5
    monthly = monthly.merge(level5, on="month_end", how="left")

    # Water year range
    monthly["WY"] = monthly["month_end"].dt.year + (monthly["month_end"].dt.month >= 10).astype(int)
    wy_min = int(monthly["WY"].min())
    wy_max = int(monthly["WY"].max())

    # Product A format: Part B, Part C, Year, Month, Value (from WY 1972)
    start_wy = 1972
    val_mask = monthly["WY"] >= start_wy
    val_monthly = monthly.loc[val_mask]
    val_df = pd.DataFrame({
        "Part B": "S_OROVLLEVEL5",
        "Part C": "STORAGE-LEVEL",
        "Year": val_monthly["month_end"].dt.year.values,
        "Month": val_monthly["month_end"].dt.month.values,
        "Value": val_monthly["S_target_eom_TAF"].values,
    })
    val_df = val_df.dropna(subset=["Value"])
    val_df = val_df.sort_values(["Part B", "Part C", "Year", "Month"]).reset_index(drop=True)

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = VALIDATION_DIR / f"S_OROVLLEVEL5_productA_{start_wy}_{wy_max}.csv"
    val_df.to_csv(out_csv, index=False)

    # -----------------
    # Excel workbook
    # -----------------
    # Compare sheet (months where Level-5 exists)
    compare = monthly.dropna(subset=["S_OROVLLEVEL5"]).copy()
    compare["diff_eom_TAF"] = compare["S_target_eom_TAF"] - compare["S_OROVLLEVEL5"]
    compare["abs_diff_eom_TAF"] = compare["diff_eom_TAF"].abs()

    out_xlsx = output_dir / "oroville_level5.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        daily_out.to_excel(writer, sheet_name="daily", index=False)
        monthly.drop(columns=["WY"]).to_excel(writer, sheet_name="monthly", index=False)
        compare.drop(columns=["WY"]).to_excel(writer, sheet_name="compare_level5", index=False)

    print(f"x_init_prevday used (only at start of record): {float(args.xinit_prevday):.3f}")
    print(f"Wrote: {out_csv}")
    print(f"Wrote: {out_xlsx}")


if __name__ == "__main__":
    main()
