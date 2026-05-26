#!/usr/bin/env python
"""
Compute Oroville Rule-Curve Level 5 Storage
===========================================
Computes Oroville rule-curve Level 5 storage from the wetness index for
Product A and/or Product B.

Usage:
    python _4_oroville_level5.py                        # Both Product A and B (default)
    python _4_oroville_level5.py --product A            # Product A only
    python _4_oroville_level5.py --product B            # Product B only
    python _4_oroville_level5.py --product B --chunks 1 2 3  # Product B, specific chunks

Inputs:
  Product A:
    <GENERATED>/mod_reservoir/storage_curves/output/_3_oroville_daily_precip/
      Oroville_Daily_Precip_ProductA_Scenario1.csv  (year, month, day, precip_inches)
  Product B:
    <GENERATED>/mod_reservoir/storage_curves/output/_3_oroville_daily_precip/
      oroville_daily_precip_productB_n01.csv ... n10.csv  (year, month, day, precip_inches)
  Historical comparison (Product A only):
    <BASE>/CalSim3/__calsim_sv_default__.dss
      Part B: S_OROVLLEVEL5, Part C: STORAGE-LEVEL (monthly end-of-month series)

Outputs:
  Product A:
    _product_a_validation/S_OROVLLEVEL5_productA_<WY1>_<WY2>.csv
      columns: Part B, Part C, Year, Month, Value
    _4_oroville_level5/oroville_level5.xlsx
      sheets: daily, monthly, compare_level5
    _4_oroville_level5/plots/S_OROVLLEVEL5_timeseries.png
      Product A vs Historical: monthly time series + non-exceedance CDF
      with R2 / NSE / PBIAS over the full overlapping period.
  Product B:
    _product_b_final/S_OROVLLEVEL5_productB_n01.csv ... n10.csv
      columns: Part B, Part C, Year, Month, Value

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

Dependencies:
  _3_oroville_daily_precip.py (produces the daily precip input CSVs)
"""

from __future__ import annotations

import argparse
import datetime as dt
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import get_base_dir, get_module_generated_dir

_gen = get_module_generated_dir("mod_reservoir/storage_curves")
INPUT_DIR = _gen / "output" / "_3_oroville_daily_precip"
OUTPUT_DIR = _gen / "output" / "_4_oroville_level5"
VALIDATION_DIR = _gen / "output" / "_product_a_validation"
PRODUCT_B_DIR = _gen / "output" / "_product_b_final"
DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
N_CHUNKS = 10


def load_daily_precip_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(
        dict(year=df["year"], month=df["month"], day=df["day"]),
        errors="coerce",
    )
    # Drop invalid dates (e.g. Feb 29 on non-leap years from WGEN)
    df = df.dropna(subset=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df[["date", "precip_inches"]]


def load_level5(dss_path: Path, part_b: str = "S_OROVLLEVEL5",
                part_c: str = "STORAGE-LEVEL") -> pd.DataFrame:
    """Read S_OROVLLEVEL5 monthly series from a CalSim DSS file."""
    target_bc = (part_b.upper(), part_c.upper())
    with dss_io.open_dss(dss_path, version=6, catalog_flag=False) as dss:
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
    Seasonal rule curve using fixed dates (Sep15, Oct15, Mar31),
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


def compute_storage_from_precip(daily_csv_path: Path, smax: float, b_taf_per_day: float,
                      x_init_prevday: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full pipeline for one precip CSV and return monthly EOM DataFrame."""
    daily_in = load_daily_precip_csv(daily_csv_path)
    dates = daily_in["date"].dt.to_pydatetime()
    precip = daily_in["precip_inches"].fillna(0.0).to_numpy(dtype=float)

    wet = compute_wetness_index(precip=precip, x_init_prevday=x_init_prevday, a=0.97)

    res = np.interp(wet, [3.5, 11.0], [368.2, 737.3]).astype(float)
    smin = smax - res
    S_target = compute_target_storage(
        dates=np.array(dates, dtype=object),
        smin=smin,
        smax=smax,
        b_taf_per_day=b_taf_per_day,
    )

    daily_out = pd.DataFrame({
        "date": pd.to_datetime(dates),
        "wetness_index": wet,
        "S_target_TAF": S_target,
    })

    tmp = daily_out.set_index("date")
    monthly = tmp.resample("ME").agg(
        S_target_eom_TAF=("S_target_TAF", "last"),
    ).reset_index().rename(columns={"date": "month_end"})

    return daily_out, monthly


def _process_one_chunk(csv_path: Path, smax: float, b_taf_per_day: float,
                       x_init_prevday: float, out_csv: Path) -> str:
    """Process a single Product B chunk. Top-level for ProcessPoolExecutor."""
    _, monthly_b = compute_storage_from_precip(csv_path, smax, b_taf_per_day, x_init_prevday)
    val_df = pd.DataFrame({
        "Part B": "S_OROVLLEVEL5",
        "Part C": "STORAGE-LEVEL",
        "Year": monthly_b["month_end"].dt.year.values,
        "Month": monthly_b["month_end"].dt.month.values,
        "Value": monthly_b["S_target_eom_TAF"].values,
    })
    val_df = val_df.dropna(subset=["Value"])
    val_df = val_df.sort_values(["Part B", "Part C", "Year", "Month"]).reset_index(drop=True)
    val_df.to_csv(out_csv, index=False)
    return str(out_csv)


def _nse(sim: np.ndarray, obs: np.ndarray) -> float:
    """Nash-Sutcliffe efficiency."""
    sim = np.asarray(sim, dtype=float)
    obs = np.asarray(obs, dtype=float)
    m = np.isfinite(sim) & np.isfinite(obs)
    if m.sum() < 2:
        return np.nan
    sim, obs = sim[m], obs[m]
    den = np.sum((obs - np.mean(obs)) ** 2)
    if den == 0:
        return np.nan
    return 1 - np.sum((obs - sim) ** 2) / den


def _pearson_r(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation coefficient."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2:
        return np.nan
    a, b = a[m], b[m]
    if np.nanstd(a) == 0 or np.nanstd(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def _setup_plot_style():
    """Apply seaborn theme and return the colour palette."""
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font_scale=1.0,
        rc={
            "figure.dpi": 200,
            "savefig.dpi": 300,
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "Calibri", "DejaVu Sans"],
            "font.size": 8,
            "axes.titlesize": 8,
            "axes.titleweight": "semibold",
            "axes.labelsize": 8,
            "axes.labelweight": "medium",
            "axes.edgecolor": "0.25",
            "axes.linewidth": 0.6,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "grid.linewidth": 0.35,
            "grid.alpha": 0.40,
            "lines.linewidth": 0.9,
            "legend.fontsize": 7,
            "figure.titlesize": 8,
            "figure.titleweight": "bold",
        },
    )
    cb = list(sns.color_palette("colorblind"))
    cb[1] = (0.918, 0.341, 0.220)
    return cb


def _plot_product_a_vs_historical(dates, actual_vals, qmap_vals, target_b,
                                  r2, nse_val, pbias, palette, out_path: Path) -> None:
    """Two-panel figure: monthly time series (left) + non-exceedance CDF (right)."""
    _r2_str = f"{r2:.2f}" if np.isfinite(r2) else "N/A"
    _nse_str = f"{nse_val:.2f}" if np.isfinite(nse_val) else "N/A"
    _pbias_str = f"{pbias:.1f}%" if np.isfinite(pbias) else "N/A"
    _metric_lbl = (f"R2={_r2_str}   "
                   f"NSE={_nse_str}   PBIAS={_pbias_str}")

    clr_hist = palette[0]
    clr_prod = palette[1]

    fig, (ax_ts, ax_cdf) = plt.subplots(
        nrows=1, ncols=2, figsize=(6.5, 3.25),
        gridspec_kw={"width_ratios": [1.6, 1]},
    )

    ax_ts.plot(dates, actual_vals, color=clr_hist, linewidth=0.8,
               label="Historical", alpha=0.85)
    ax_ts.plot(dates, qmap_vals, color=clr_prod, linewidth=0.9,
               label="Product A", alpha=0.85)
    ax_ts.set_title("Monthly Time Series")
    ax_ts.set_xlabel("Date")
    ax_ts.set_ylabel("TAF")
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(10))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate(rotation=35, ha="right")
    ax_ts.text(
        0.02, 0.97, _metric_lbl,
        transform=ax_ts.transAxes,
        va="top", ha="left", fontsize=7,
        bbox=dict(boxstyle="round,pad=0.35",
                  facecolor="white", edgecolor="0.7", alpha=0.88),
    )

    for vals_arr, color, lbl in [
        (actual_vals, clr_hist, "Historical"),
        (qmap_vals, clr_prod, "Product A"),
    ]:
        arr = np.sort(np.asarray(vals_arr, dtype=float))
        cdf = np.arange(1, len(arr) + 1) / len(arr) * 100
        ax_cdf.plot(cdf, arr, color=color, linewidth=0.9, alpha=0.9, label=lbl)
    ax_cdf.set_title("Non-Exceedance CDF")
    ax_cdf.set_xlabel("Non-Exceedance Probability (%)")
    ax_cdf.set_xlim(0, 100)

    fig.suptitle(f"{target_b} (TAF)", y=1.02)
    fig.tight_layout()
    handles, labels = ax_ts.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left",
               bbox_to_anchor=(0.01, 0.99), ncol=2, fontsize=7, frameon=False)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute Oroville rule-curve level5 storage from wetness index.",
    )
    parser.add_argument(
        "--product", choices=["A", "B"], required=True,
        help='Product to generate: A (historical 1921-2018) or B (stochastic 1000-yr chunks).',
    )
    parser.add_argument(
        "--chunks", nargs="+", type=int,
        default=list(range(1, N_CHUNKS + 1)),
        help="Chunk numbers to process for Product B, 1-10 (default: all)",
    )

    args = parser.parse_args()

    input_dir = INPUT_DIR
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    smax = 3425.2
    b_taf = 10.0
    x_init = 3.5

    # =====================
    # Product A
    # =====================
    if args.product == "A":
        daily_path = input_dir / "Oroville_Daily_Precip_ProductA_Scenario1.csv"
        dss_path = DEFAULT_DSS

        for p in [daily_path, dss_path]:
            if not p.exists():
                raise FileNotFoundError(f"Required input not found: {p}")

        daily_out, monthly = compute_storage_from_precip(daily_path, smax, b_taf, x_init)
        level5 = load_level5(dss_path)

        # Merge with historical Level-5
        monthly = monthly.merge(level5, on="month_end", how="left")

        # Water year range
        monthly["WY"] = monthly["month_end"].dt.year + (monthly["month_end"].dt.month >= 10).astype(int)
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

        # Excel workbook
        compare = monthly.dropna(subset=["S_OROVLLEVEL5"]).copy()
        compare["diff_eom_TAF"] = compare["S_target_eom_TAF"] - compare["S_OROVLLEVEL5"]
        compare["abs_diff_eom_TAF"] = compare["diff_eom_TAF"].abs()

        out_xlsx = output_dir / "oroville_level5.xlsx"
        with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
            daily_out.to_excel(writer, sheet_name="daily", index=False)
            monthly.drop(columns=["WY"]).to_excel(writer, sheet_name="monthly", index=False)
            compare.drop(columns=["WY"]).to_excel(writer, sheet_name="compare_level5", index=False)

        # Product A vs Historical comparison figure (timeseries + CDF)
        plots_dir = output_dir / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)
        cmp = compare.dropna(subset=["S_OROVLLEVEL5", "S_target_eom_TAF"])
        if not cmp.empty:
            dates = pd.DatetimeIndex(cmp["month_end"].values)
            actual_vals = cmp["S_OROVLLEVEL5"].to_numpy(dtype=float)
            qmap_vals = cmp["S_target_eom_TAF"].to_numpy(dtype=float)
            r = _pearson_r(qmap_vals, actual_vals)
            r2 = r ** 2 if np.isfinite(r) else np.nan
            nse_val = _nse(qmap_vals, actual_vals)
            obs_sum = np.nansum(actual_vals)
            pbias = ((np.nansum(qmap_vals - actual_vals) / obs_sum * 100)
                     if obs_sum != 0 else np.nan)
            palette = _setup_plot_style()
            fig_path = plots_dir / "S_OROVLLEVEL5_timeseries.png"
            _plot_product_a_vs_historical(
                dates, actual_vals, qmap_vals, "S_OROVLLEVEL5",
                r2, nse_val, pbias, palette, fig_path,
            )
            print(f"Wrote: {fig_path}")
            print(f"  R2 = {r2:.3f}, NSE = {nse_val:.3f}, PBIAS = {pbias:.1f}%")

        print(f"x_init_prevday used (only at start of record): {x_init}")
        print(f"Wrote: {out_csv}")
        print(f"Wrote: {out_xlsx}")

    # =====================
    # Product B
    # =====================
    if args.product == "B":
        PRODUCT_B_DIR.mkdir(parents=True, exist_ok=True)

        # Build work list
        jobs = []
        for chunk_num in args.chunks:
            chunk_tag = f"n{chunk_num:02d}"
            csv_path = input_dir / f"oroville_daily_precip_productB_{chunk_tag}.csv"
            if not csv_path.exists():
                print(f"  WARNING: {csv_path} not found, skipping chunk {chunk_tag}")
                continue
            out_csv = PRODUCT_B_DIR / f"S_OROVLLEVEL5_productB_{chunk_tag}.csv"
            jobs.append((chunk_tag, csv_path, out_csv))

        if not jobs:
            print("  No Product B chunk files found.")
        else:
            n_workers = min(N_CHUNKS, len(jobs))
            print(f"  Processing {len(jobs)} chunks ({n_workers} workers) ...")
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                futures = {
                    pool.submit(_process_one_chunk, csv_path, smax, b_taf, x_init, out_csv): tag
                    for tag, csv_path, out_csv in jobs
                }
                for fut in as_completed(futures):
                    futures[fut]
                    result = fut.result()  # raises if the worker failed
                    print(f"  Wrote: {result}")


if __name__ == "__main__":
    main()
