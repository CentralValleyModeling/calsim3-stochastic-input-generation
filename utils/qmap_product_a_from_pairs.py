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

import numpy as np
import pandas as pd

from utils import csv_io, dss_io
from utils.validation_plots import (
    Series, format_metric_line, nse, pbias, plot_monthly_box, plot_ts_cdf, r2,
)
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


# -- Text helpers -------------------------------------------------------------

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def norm_token(value) -> str:
    return clean_text(value).upper()


# -- Pair CSV reader ----------------------------------------------------------
def read_qmap_pairs(pair_csv: str | Path) -> pd.DataFrame:
    """Read and validate qmap_pairs.csv.

    Required columns:
      target_part_b, target_part_c, predictor_part_b, predictor_part_c

    Optional columns (created with defaults if missing):
      lower_bound, upper_bound, allow_negative (True/False, default False)
    """
    pair_csv = Path(pair_csv)
    df = csv_io.read_sv_csv(pair_csv)

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
    Thin wrapper over ``utils.dss_io``; opens the DSS file directly (no
    junction, ``catalog_flag=True``) to preserve this engine's historical
    behavior of reading the long-path-prefixed file directly.
    """
    requested = {
        (norm_token(b), norm_token(c))
        for b, c in specs
        if clean_text(b) and clean_text(c)
    }
    if not requested:
        return {}

    with dss_io.open_dss(str(dssfile), version=6, catalog_flag=True,
                         use_junction=False) as dss:
        return dss_io.read_monthly_series(
            dss, requested, dss_read_start, dss_read_end,
        )


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
    """Delegates to ``utils.dss_io.safe_makedirs`` (faithful copy)."""
    dss_io.safe_makedirs(path)


# -- Data loading -------------------------------------------------------------

def load_product_a_rim_series(csv_path, part_b, part_c):
    """Load a specific Part B + Part C series from the Product A rim inflow CSV.

    Returns a monthly ``pd.Series`` with month-end ``DatetimeIndex``.
    Delegates to ``utils.csv_io.load_sv_series`` (faithful copy).
    """
    return csv_io.load_sv_series(csv_path, part_b, part_c)


# -- Plotting -----------------------------------------------------------------

def _plot_timeseries_cdf(common_sim, actual_vals, qmap_vals, target_b,
                         r2_val, nse_val, pbias_val, plots_dir):
    """Two-panel figure: monthly time series (left) + non-exceedance CDF (right).

    Thin wrapper over ``utils.validation_plots.plot_ts_cdf`` that supplies the
    pre-computed Product A vs Historical metrics as a single annotation line.
    """
    plot_ts_cdf(
        series=[
            Series("Historical", common_sim, actual_vals, linewidth=0.8),
            Series("Product A", common_sim, qmap_vals),
        ],
        title=f"{target_b} (TAF)",
        metric_lines=[format_metric_line(r2_val, nse_val, pbias_val)],
        out_path=os.path.join(plots_dir, f"{target_b}_timeseries.png"),
    )


def _plot_monthly_box(detail, target_b, column, ylabel,
                      title_suffix, filename_suffix, plots_dir):
    """Thin wrapper over ``utils.validation_plots.plot_monthly_box``."""
    plot_monthly_box(
        detail, value_col=column, ylabel=ylabel,
        title=f"{target_b}: {title_suffix}",
        out_path=os.path.join(plots_dir, f"{target_b}_{filename_suffix}.png"),
    )


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
        Directory for detail CSVs and ``figures/product_a/`` subdirectory.
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
    plots_dir = os.path.join(output_dir, "figures", "product_a")

    _safe_makedirs(output_dir)
    _safe_makedirs(plots_dir)
    _safe_makedirs(validation_dir)

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
        r2_val = r2(actual_vals, qmap_vals)
        nse_val = nse(actual_vals, qmap_vals)
        pbias_val = pbias(actual_vals, qmap_vals)

        print(f"  R2 = {r2_val:.3f}, NSE = {nse_val:.3f}, PBIAS = {pbias_val:.1f}%")

        # 7) Detail dataframe
        detail = pd.DataFrame({
            "target_historical_train": target_b,
            "basis_historical_train": pred_b,
            "year": common_sim.year.astype(int),
            "month": common_sim.month.astype(int),
            "basis_qm_sim": pred_sim.values,
            "target_historical_sim": actual_vals,
            "target_qm_sim": qmap_vals,
        })
        detail["error"] = detail["target_qm_sim"] - detail["target_historical_sim"]
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = ((detail["target_qm_sim"] - detail["target_historical_sim"])
                   / detail["target_historical_sim"] * 100)
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
            r2_val, nse_val, pbias_val, plots_dir,
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
