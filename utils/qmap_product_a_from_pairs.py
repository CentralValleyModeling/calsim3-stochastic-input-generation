"""
Reusable Product A split-sample quantile-mapping validation
===========================================================
Driven by a ``qmap_pairs.csv`` file, this module trains quantile mapping on
the first half of the overlap period and validates on the second half.

Workflow per (target, predictor) pair
-------------------------------------
1. Read CalSim baseline DSS for predictor and target (full historical).
2. Train quantile mapping on the training window (default 1921-1971).
3. Load Product A QMAP'd predictor from a rim-inflow CSV for the
   simulation window (default 1972-2018).
4. Apply quantile mapping to produce a synthetic target.
5. Validate against the actual CalSim target (R2, NSE, PBIAS).
6. Write detail CSVs, CalSim-format validation CSVs, and three plot types.

"""
from __future__ import annotations

import os
import re
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from pydsstools.heclib.dss import HecDss

from utils.quantile_mapping import qmap_single

_REQUIRED_COLS = ["target_part_b", "target_part_c",
                  "predictor_part_b", "predictor_part_c"]
_OPTIONAL_COLS = ["lower_bound", "upper_bound", "allow_negative"]

# -- Defaults -----------------------------------------------------------------
TRAIN_START = "1921-10-01"
TRAIN_END = "1971-09-30"
SIM_START = "1971-10-01"
SIM_END = "2018-09-30"
DSS_READ_START = "1915-01-31"
DSS_READ_END = "2018-12-31"
ALLOW_NEGATIVE = False

MONTH_LABELS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

# -- Box-plot palette ---------------------------------------------------------
_BLUE = "#003D6B"
_LIGHT_BLUE = "#B0C4DE"
_MEDIAN_RED = "#8B0000"
_GRAY = "#5A5A5A"


# -- Text helpers -------------------------------------------------------------

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_token(value) -> str:
    return clean_text(value).upper()


def _date_range_me(start, end=None, **kwargs) -> pd.DatetimeIndex:
    """Return a month-end DatetimeIndex, compatible with old and new pandas.

    pandas >= 2.2 uses ``freq="ME"``; older versions require ``freq="M"``.
    Catches the ``ValueError`` that older pandas raises for an unknown
    frequency alias.
    """
    try:
        return pd.date_range(start, end, freq="ME", **kwargs)
    except ValueError:
        return pd.date_range(start, end, freq="M", **kwargs)


# -- Pair CSV reader ----------------------------------------------------------
    """Read and validate qmap_pairs.csv.

    Required columns:
      target_part_b, target_part_c, predictor_part_b, predictor_part_c

    Optional columns (created with defaults if missing):
      lower_bound, upper_bound, allow_negative (True/False, default False)
    """
    pair_csv = Path(pair_csv)
    df = pd.read_csv(pair_csv, skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in _REQUIRED_COLS if c not in df.columns]
    if missing:
        raise KeyError(f"qmap_pairs.csv missing required columns: {missing}")

    for col in _OPTIONAL_COLS:
        if col not in df.columns:
            df[col] = np.nan

    for col in _REQUIRED_COLS:
        df[col] = df[col].apply(clean_text)

    df["lower_bound"] = pd.to_numeric(df["lower_bound"], errors="coerce")
    df["upper_bound"] = pd.to_numeric(df["upper_bound"], errors="coerce")

    # Parse allow_negative: accept True/False/1/0/yes/no; default to False.
    if "allow_negative" in df.columns:
        _truthy = {"true", "yes", "t", "y"}
        df["allow_negative"] = (
            df["allow_negative"]
            .apply(lambda v: str(v).strip().lower() in _truthy if pd.notna(v) else False)
        )
    else:
        df["allow_negative"] = False

    df = df[
        (df["target_part_b"] != "")
        & (df["target_part_c"] != "")
        & (df["predictor_part_b"] != "")
        & (df["predictor_part_c"] != "")
    ].copy()

    if df.empty:
        raise ValueError(f"{pair_csv} has no valid rows.")

    dup_targets = df["target_part_b"].duplicated(keep=False)
    if dup_targets.any():
        dups = sorted(df.loc[dup_targets, "target_part_b"].astype(str).unique().tolist())
        raise ValueError(
            "target_part_b values must be unique because outputs are named "
            f"<target_part_b>_qmap_<ts>.csv. Duplicates: {dups}"
        )

    swap_mask = (
        df["lower_bound"].notna()
        & df["upper_bound"].notna()
        & (df["lower_bound"] > df["upper_bound"])
    )
    if swap_mask.any():
        lower_values = df.loc[swap_mask, "upper_bound"].to_numpy()
        upper_values = df.loc[swap_mask, "lower_bound"].to_numpy()
        df.loc[swap_mask, "lower_bound"] = lower_values
        df.loc[swap_mask, "upper_bound"] = upper_values
        print(f"  WARNING: swapped lower/upper bounds for "
              f"{int(swap_mask.sum())} row(s) in {pair_csv.name}")

    return df.reset_index(drop=True)


# -- Batch DSS reader ---------------------------------------------------------

def read_calsim_monthly_pairs(
    dssfile,
    specs,
    dss_read_start=DSS_READ_START,
    dss_read_end=DSS_READ_END,
):
    """Read multiple CalSim monthly DSS series keyed by (B-part, C-part).

    Returns ``dict[(B_upper, C_upper)] -> pd.Series`` with month-end index.
    """
    requested = {
        (norm_token(b), norm_token(c))
        for b, c in specs
        if clean_text(b) and clean_text(c)
    }
    if not requested:
        return {}

    full_idx = _date_range_me(dss_read_start, dss_read_end)
    out = {}

    with HecDss.Open(str(dssfile), version=6, catalog_flag=True) as dss:
        paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        bucket = {}

        for path in paths:
            parts = path.strip("/").split("/")
            if len(parts) != 6:
                continue
            key = (parts[1].strip().upper(), parts[2].strip().upper())
            if key in requested:
                bucket.setdefault(key, []).append(path)

        for key in sorted(requested):
            if key not in bucket:
                continue
            master = pd.Series(index=full_idx, dtype=float)
            for path in sorted(bucket[key],
                               key=lambda x: (x.strip("/").split("/")[3], x)):
                ts = dss.read_ts(path, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals = np.where(vals <= -900, np.nan, vals)
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1
                       ).to_timestamp("M")
                master.update(pd.Series(vals, index=idx))
            if master.notna().any():
                out[key] = master

    return out


# -- Series helpers -----------------------------------------------------------

def ser_to_df(series):
    """Convert a monthly Series with month-end index to (year, month, value)."""
    return pd.DataFrame({
        "year": series.index.year.astype(int),
        "month": series.index.month.astype(int),
        "value": pd.to_numeric(series.values, errors="coerce"),
    })


# -- Filesystem helpers -------------------------------------------------------

def _safe_makedirs(path):
    """Create directories, stripping the \\\\?\\ long-path prefix first.

    On Python 3.8 + Windows, ``os.makedirs`` cannot resolve the root of a
    ``\\\\?\\X:\\`` path, causing infinite recursion.  Stripping the prefix
    before the call avoids the issue without modifying ``utils/paths.py``.
    """
    s = str(path)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    os.makedirs(s, exist_ok=True)


def nse(sim, obs):
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


def pearson_r(a, b):
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


# -- Data loading -------------------------------------------------------------

def load_product_a_rim_series(csv_path, part_b, part_c):
    """Load a specific Part B + Part C series from the Product A rim inflow CSV.

    Returns a monthly ``pd.Series`` with month-end ``DatetimeIndex``.
    """
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path)
    mask_b = df["Part B"].str.upper().str.strip() == part_b.upper().strip()
    mask_c = df["Part C"].str.upper().str.strip() == part_c.upper().strip()
    sub = df.loc[mask_b & mask_c].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(
        sub["Year"].astype(str) + "-" + sub["Month"].astype(str) + "-01"
    )
    dates = dates + pd.offsets.MonthEnd(0)
    return pd.Series(sub["Value"].values.astype(float), index=dates).sort_index()


# -- Plot styling -------------------------------------------------------------

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
            "xtick.major.width": 0.5,
            "ytick.major.width": 0.5,
            "grid.linewidth": 0.35,
            "grid.alpha": 0.40,
            "lines.linewidth": 0.9,
            "legend.fontsize": 7,
            "legend.title_fontsize": 8,
            "legend.framealpha": 0.90,
            "legend.edgecolor": "0.55",
            "figure.titlesize": 8,
            "figure.titleweight": "bold",
            "mathtext.default": "regular",
        },
    )
    cb = list(sns.color_palette("colorblind"))
    cb[1] = (0.918, 0.341, 0.220)  # Vermillion+1 ~#EB5738
    return cb


# -- Plotting -----------------------------------------------------------------

def _plot_timeseries_cdf(common_sim, actual_vals, qmap_vals, target_b,
                         r2, nse_val, pbias, palette, plots_dir):
    """Two-panel figure: monthly time series (left) + non-exceedance CDF (right)."""
    _r2_str = f"{r2:.2f}" if np.isfinite(r2) else "N/A"
    _nse_str = f"{nse_val:.2f}" if np.isfinite(nse_val) else "N/A"
    _pbias_str = f"{pbias:.1f}%" if np.isfinite(pbias) else "N/A"
    _metric_lbl = (f"Product A:  R\u00b2={_r2_str}   "
                   f"NSE={_nse_str}   PBIAS={_pbias_str}")

    clr_hist = palette[0]
    clr_prod = palette[1]

    fig, (ax_ts, ax_cdf) = plt.subplots(
        nrows=1, ncols=2, figsize=(6.5, 3.25),
        gridspec_kw={"width_ratios": [1.6, 1]},
    )

    # -- Left: time series --
    ax_ts.plot(common_sim, actual_vals, color=clr_hist, linewidth=0.8,
               label="Historical", alpha=0.85)
    ax_ts.plot(common_sim, qmap_vals, color=clr_prod, linewidth=0.9,
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
        fontfamily="sans-serif",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="white", edgecolor="0.7",
            alpha=0.88,
        ),
    )

    # -- Right: CDF --
    for vals_arr, color, lbl in [
        (actual_vals, clr_hist, "Historical"),
        (qmap_vals, clr_prod, "Product A"),
    ]:
        arr = np.sort(np.asarray(vals_arr, dtype=float))
        cdf = np.arange(1, len(arr) + 1) / len(arr) * 100
        ax_cdf.plot(cdf, arr, color=color, linewidth=0.9, alpha=0.9,
                    label=lbl)
    ax_cdf.set_title("Non-Exceedance CDF")
    ax_cdf.set_xlabel("Non-Exceedance Probability (%)")
    ax_cdf.set_ylabel("")
    ax_cdf.set_xlim(0, 100)

    fig.suptitle(f"{target_b} (TAF)", y=1.02)
    fig.tight_layout()
    handles, labels = ax_ts.get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
        ncol=2,
        fontsize=7,
        frameon=False,
        handlelength=2.0,
        handletextpad=0.6,
        borderpad=0.7,
    )
    fig.savefig(os.path.join(plots_dir, f"{target_b}_timeseries.png"),
                dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot_monthly_box(detail, target_b, column, ylabel,
                      title_suffix, filename_suffix, plots_dir):
    """Monthly box plot in water-year order (Oct-Sep)."""
    months_list = list(range(10, 13)) + list(range(1, 10))
    box_data = [
        detail.loc[detail["Month"] == m, column].dropna().values
        for m in months_list
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    positions = list(range(1, len(months_list) + 1))
    ax.boxplot(
        box_data, positions=positions, widths=0.5,
        showfliers=False, patch_artist=True, showmeans=True,
        boxprops=dict(facecolor=_LIGHT_BLUE, edgecolor=_BLUE, linewidth=1.0),
        medianprops=dict(color=_MEDIAN_RED, linewidth=1.8),
        meanprops=dict(marker="D", markerfacecolor=_BLUE,
                       markeredgecolor=_BLUE, markersize=5),
        whiskerprops=dict(color=_BLUE, linewidth=1.0),
        capprops=dict(color=_BLUE, linewidth=1.0),
    )
    ax.axhline(0, color=_GRAY, linestyle="--", linewidth=1.4)
    ax.set_xticks(positions)
    ax.set_xticklabels([MONTH_LABELS[m - 1] for m in months_list],
                       fontsize=11, fontweight="medium")
    ax.set_xlabel("Month", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel(ylabel, fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title(f"{target_b}: {title_suffix}",
                 fontsize=14, fontweight="bold", pad=12)
    ax.tick_params(axis="both", labelsize=11)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5, color="#CCCCCC")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(plots_dir, f"{target_b}_{filename_suffix}.png"),
                dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# -- Main entry point ---------------------------------------------------------

def run_product_a_qmap_from_pairs(
    *,
    pair_csv,
    dss_file,
    product_a_rim_csv,
    output_dir,
    validation_dir,
    train_start=TRAIN_START,
    train_end=TRAIN_END,
    sim_start=SIM_START,
    sim_end=SIM_END,
    dss_read_start=DSS_READ_START,
    dss_read_end=DSS_READ_END,
    allow_negative=ALLOW_NEGATIVE,
):
    """Run Product A split-sample QM validation for all pairs in a CSV.

    Parameters
    ----------
    pair_csv : str or Path
        Path to qmap_pairs.csv (target/predictor definitions).
    dss_file : str or Path
        Path to CalSim baseline DSS.
    product_a_rim_csv : str or Path
        Path to Product A QMAP'd rim inflow CSV (simulation predictor source).
    output_dir : str or Path
        Directory for detail CSVs and ``_figures/`` subdirectory.
    validation_dir : str or Path
        Directory for CalSim-format validation CSVs.
    train_start, train_end : str
        Training period boundaries (default 1921-10 to 1971-09).
    sim_start, sim_end : str
        Simulation/validation period boundaries (default 1971-10 to 2018-09).
    dss_read_start, dss_read_end : str
        DSS read window boundaries.
    allow_negative : bool
        Fallback default when the CSV does not include an ``allow_negative``
        column.  Per-pair values in the CSV take precedence.

    Returns
    -------
    dict
        ``{pairs_requested, pairs_processed, pairs_skipped}``.
    """
    pair_csv = Path(pair_csv)
    product_a_rim_csv = Path(product_a_rim_csv)
    output_dir = str(output_dir)
    validation_dir = str(validation_dir)
    plots_dir = os.path.join(output_dir, "_figures")

    _safe_makedirs(output_dir)
    _safe_makedirs(plots_dir)
    _safe_makedirs(validation_dir)

    palette = _setup_plot_style()

    # -- Derive WY labels for output filenames --------------------------------
    _sim_start_dt = pd.Timestamp(sim_start)
    _sim_end_dt = pd.Timestamp(sim_end)
    _start_wy = _sim_start_dt.year + (1 if _sim_start_dt.month >= 10 else 0)
    _end_wy = _sim_end_dt.year + (1 if _sim_end_dt.month >= 10 else 0)

    # -- Load pair definitions ------------------------------------------------
    df_pairs = read_qmap_pairs(pair_csv)
    print(f"Loaded {len(df_pairs)} pair(s) from {pair_csv.name}")

    # -- Batch-read all needed DSS series -------------------------------------
    dss_specs = []
    for _, row in df_pairs.iterrows():
        dss_specs.append((row["predictor_part_b"], row["predictor_part_c"]))
        dss_specs.append((row["target_part_b"], row["target_part_c"]))

    print(f"Scanning DSS: {dss_file}")
    dss_data = read_calsim_monthly_pairs(
        dssfile=str(dss_file),
        specs=dss_specs,
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )
    print(f"  Read {len(dss_data)} monthly DSS series")

    # -- Process each pair ----------------------------------------------------
    pairs_processed = 0
    pairs_skipped = 0

    for _, row in df_pairs.iterrows():
        target_b = row["target_part_b"]
        target_c = row["target_part_c"]
        pred_b = row["predictor_part_b"]
        pred_c = row["predictor_part_c"]
        lb = row["lower_bound"]
        ub = row["upper_bound"]
        pair_allow_neg = row.get("allow_negative", allow_negative)

        print(f"\n{'='*60}")
        print(f"Target: {target_b} / {target_c}")
        print(f"Predictor: {pred_b} / {pred_c}")
        print(f"Bounds: [{lb}, {ub}]")

        # 1) Lookup CalSim DSS series
        pred_key = (pred_b.strip().upper(), pred_c.strip().upper())
        tgt_key = (target_b.strip().upper(), target_c.strip().upper())

        predictor_full = dss_data.get(pred_key)
        target_full = dss_data.get(tgt_key)

        if predictor_full is None or predictor_full.dropna().empty:
            print(f"  WARNING: No DSS data for predictor "
                  f"{pred_b}/{pred_c}, skipping.")
            pairs_skipped += 1
            continue
        if target_full is None or target_full.dropna().empty:
            print(f"  WARNING: No DSS data for target "
                  f"{target_b}/{target_c}, skipping.")
            pairs_skipped += 1
            continue

        # 2) Slice training period
        pred_train = predictor_full.loc[train_start:train_end].dropna()
        tgt_train = target_full.loc[train_start:train_end].dropna()

        common_train = pred_train.index.intersection(tgt_train.index)
        if common_train.empty:
            print("  WARNING: No common training months, skipping.")
            pairs_skipped += 1
            continue
        pred_train = pred_train.loc[common_train]
        tgt_train = tgt_train.loc[common_train]

        print(f"  Training: {len(pred_train)} months "
              f"({common_train.min().date()} to {common_train.max().date()})")

        # 3) Load Product A simulation predictor
        pred_sim = load_product_a_rim_series(
            product_a_rim_csv, pred_b, pred_c,
        )
        pred_sim = pred_sim.loc[sim_start:sim_end].dropna()

        if pred_sim.empty:
            print(f"  WARNING: No Product A data for predictor "
                  f"{pred_b}/{pred_c}, skipping.")
            pairs_skipped += 1
            continue

        tgt_actual = target_full.loc[sim_start:sim_end].dropna()
        common_sim = pred_sim.index.intersection(tgt_actual.index)
        if common_sim.empty:
            print("  WARNING: No common simulation months, skipping.")
            pairs_skipped += 1
            continue
        pred_sim = pred_sim.loc[common_sim]
        tgt_actual = tgt_actual.loc[common_sim]

        print(f"  Simulation: {len(pred_sim)} months "
              f"({common_sim.min().date()} to {common_sim.max().date()})")

        # 4) Quantile map
        qmap_result = qmap_single(
            ser_to_df(pred_sim),
            ser_to_df(pred_train),
            ser_to_df(tgt_train),
            allow_negative=pair_allow_neg,
        )
        qmap_vals = qmap_result["quantile_mapped_value"].values.astype(float)

        # 5) Clamp to bounds
        if np.isfinite(lb):
            qmap_vals = np.maximum(qmap_vals, lb)
        if np.isfinite(ub):
            qmap_vals = np.minimum(qmap_vals, ub)

        # 6) Metrics
        actual_vals = tgt_actual.values.astype(float)
        r = pearson_r(qmap_vals, actual_vals)
        r2 = r ** 2 if np.isfinite(r) else np.nan
        nse_val = nse(qmap_vals, actual_vals)
        obs_sum = np.nansum(actual_vals)
        pbias = ((np.nansum(qmap_vals - actual_vals) / obs_sum * 100)
                 if obs_sum != 0 else np.nan)

        print(f"  R2 = {r2:.3f}, NSE = {nse_val:.3f}, PBIAS = {pbias:.1f}%")

        # 7) Detail dataframe
        detail = pd.DataFrame({
            "target": target_b,
            "predictor": pred_b,
            "Year": common_sim.year.astype(int),
            "Month": common_sim.month.astype(int),
            "predictor_sim": pred_sim.values,
            "actual": actual_vals,
            "qmap": qmap_vals,
        })
        detail["error"] = detail["qmap"] - detail["actual"]
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = ((detail["qmap"] - detail["actual"])
                   / detail["actual"] * 100)
        pct[~np.isfinite(pct)] = np.nan
        detail["error_pct"] = pct

        # 8) Write detail CSV
        detail.to_csv(
            os.path.join(output_dir, f"{target_b}_qmap_validation.csv"),
            index=False,
        )

        # 9) Write CalSim-format validation CSV
        val_df = pd.DataFrame({
            "Part B": target_b,
            "Part C": target_c,
            "Year": common_sim.year.astype(int),
            "Month": common_sim.month.astype(int),
            "Value": qmap_vals,
        })
        val_csv = os.path.join(
            validation_dir,
            f"{target_b}_productA_{_start_wy}_{_end_wy}.csv",
        )
        val_df.to_csv(val_csv, index=False)
        print(f"  Wrote: {val_csv}")

        # 10-12) Plots
        _plot_timeseries_cdf(
            common_sim, actual_vals, qmap_vals, target_b,
            r2, nse_val, pbias, palette, plots_dir,
        )
        _plot_monthly_box(
            detail, target_b, "error", "Error (TAF)",
            "Monthly Error", "monthly_error", plots_dir,
        )
        _plot_monthly_box(
            detail, target_b, "error_pct", "Percent Error (%)",
            "Monthly Percent Error", "monthly_pct_error", plots_dir,
        )

        pairs_processed += 1

    print(f"\nDone: {pairs_processed} processed, {pairs_skipped} skipped "
          f"out of {len(df_pairs)} pair(s).")

    return {
        "pairs_requested": len(df_pairs),
        "pairs_processed": pairs_processed,
        "pairs_skipped": pairs_skipped,
    }
