from __future__ import annotations

"""
Reusable utilities for Product-B quantile mapping driven by qmap_pairs.csv for non-rimflow/non-ET terms.

This module is designed so multiple workflows can reuse the same logic while
supplying different qmap_pairs.csv files from different directories.

Core assumptions
----------------
- Training basis and target are both read from a CalSim DSS file using the
  B-part and C-part specified in qmap_pairs.csv.
- Simulation basis files are monthly Product-B CSVs stored as:
      <predictor_part_b>_qmo_<timeseries>.csv
- Simulation value column is ``qmap_postAdj``.
- Output files are written as:
      <target_part_b>_qmap_<timeseries>.csv
"""

import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

from utils.quantile_mapping import qmap_single

# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
PRODUCT_B_START = pd.Timestamp("1921-10-31")
PRODUCT_B_END = pd.Timestamp("2021-09-30")
DSS_READ_START = "1915-01-31"
DSS_READ_END = "2021-12-31"
TRAIN_START = "1921-10-01"
TRAIN_END = "2021-09-30"
OUTPUT_TAG = "qmap"
SIM_VALUE_COLUMN = "qmap_postAdj"

# -----------------------------------------------------------------------------
# Basic helpers
# -----------------------------------------------------------------------------

def ser_to_df(series: pd.Series) -> pd.DataFrame:
    """Convert a monthly Series with month-end index to (year, month, value)."""
    return pd.DataFrame(
        {
            "year": series.index.year.astype(int),
            "month": series.index.month.astype(int),
            "value": pd.to_numeric(series.values, errors="coerce"),
        }
    )

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _date_range_me(start, end=None, **kwargs) -> pd.DatetimeIndex:
    """Month-end DatetimeIndex (pandas 2.2+ ``freq="ME"``)."""
    return pd.date_range(start, end, freq="ME", **kwargs)


def norm_token(value) -> str:
    return clean_text(value).upper()


def norm_colname(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def timeseries_sort_key(label: str):
    """Numeric ordering for labels like n01, n02, ..., n10 or 01, 02, ..., 10."""
    s = str(label)
    m = re.search(r"(\d+)", s)
    if m:
        return (int(m.group(1)), s)
    return (10**9, s)


def find_timeseries_in_dir(sim_dir: str | Path) -> list[str]:
    """Detect Product-B timeseries labels from filenames containing ``_qmo_``."""
    sim_dir = Path(sim_dir)
    timeseries_list: set[str] = set()

    if not sim_dir.exists():
        return []

    for file in sim_dir.iterdir():
        if not file.is_file() or file.suffix.lower() != ".csv":
            continue
        if "_qmo_" not in file.stem:
            continue
        _, ts = file.stem.split("_qmo_", 1)
        timeseries_list.add(ts)

    return sorted(timeseries_list, key=timeseries_sort_key)


def build_output_filename(target_partb: str, timeseries: str, output_tag: str = OUTPUT_TAG) -> str:
    return f"{target_partb}_{output_tag}_{timeseries}.csv"


# -----------------------------------------------------------------------------
# qmap_pairs.csv handling
# -----------------------------------------------------------------------------
_REQUIRED_COLS = ["target_part_b", "target_part_c", "predictor_part_b", "predictor_part_c"]
_OPTIONAL_COLS = ["lower_bound", "upper_bound"]


def read_qmap_pairs(pair_csv: str | Path) -> pd.DataFrame:
    """
    Read and validate qmap_pairs.csv.

    Required columns:
      target_part_b, target_part_c, predictor_part_b, predictor_part_c

    Optional columns (created as NaN if missing):
      lower_bound, upper_bound
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

    # Keep only rows with all DSS/file identifiers present.
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

    # If both bounds are present but reversed, swap them.
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
        print(f"  WARNING: swapped lower/upper bounds for {int(swap_mask.sum())} row(s) in {pair_csv.name}")

    return df.reset_index(drop=True)


# -----------------------------------------------------------------------------
# DSS helpers
# -----------------------------------------------------------------------------

def read_calsim_monthly_pairs(
    dssfile: str | Path,
    specs: list[tuple[str, str]],
    dss_read_start: str = DSS_READ_START,
    dss_read_end: str = DSS_READ_END,
) -> dict[tuple[str, str], pd.Series]:
    """
    Read multiple CalSim monthly DSS series keyed by (B-part, C-part).

    Matching is case-insensitive on pathname B and C parts. All monthly paths
    matching a requested (B, C) pair are stitched together by updating a common
    monthly index.
    """
    requested = {
        (norm_token(b), norm_token(c))
        for b, c in specs
        if clean_text(b) and clean_text(c)
    }
    if not requested:
        return {}

    full_idx = _date_range_me(dss_read_start, dss_read_end)
    out: dict[tuple[str, str], pd.Series] = {}

    with HecDss.Open(str(dssfile), version=6, catalog_flag=True) as dss:
        paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        bucket: dict[tuple[str, str], list[str]] = {}

        for path in paths:
            parts = path.strip("/").split("/")
            if len(parts) != 6:
                continue
            b_part = parts[1].strip().upper()
            c_part = parts[2].strip().upper()
            key = (b_part, c_part)
            if key in requested:
                bucket.setdefault(key, []).append(path)

        for key in sorted(requested):
            if key not in bucket:
                continue

            master = pd.Series(index=full_idx, dtype=float)

            # Sort primarily by D-part, then full path for stability.
            for path in sorted(bucket[key], key=lambda x: (x.strip("/").split("/")[3], x)):
                ts = dss.read_ts(path, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals = np.where(vals <= -900, np.nan, vals)

                # DSS stores period-end timestamps (e.g. Feb for Jan data).
                # Shift back by one month so the index reflects the actual data month.
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                master.update(pd.Series(vals, index=idx))

            if master.notna().any():
                out[key] = master

    return out


# -----------------------------------------------------------------------------
# Product-B basis helpers
# -----------------------------------------------------------------------------

def detect_product_b_value_col(df: pd.DataFrame) -> str:
    """Return the original column name that normalizes to 'qmappostadj'."""
    normalized = {norm_colname(c): c for c in df.columns}
    value_col = normalized.get(norm_colname(SIM_VALUE_COLUMN))
    if value_col is None:
        raise KeyError(
            f"Cannot find a '{SIM_VALUE_COLUMN}' column in Product-B CSV. "
            f"Available columns: {list(df.columns)}"
        )
    return value_col


def load_product_b_basis_series(
    basis_partb: str,
    sim_dir: str | Path,
    timeseries: str,
    product_b_start: str | pd.Timestamp = PRODUCT_B_START,
    product_b_end: str | pd.Timestamp = PRODUCT_B_END,
) -> pd.Series | None:
    """
    Load one Product-B realization for a matched basis term.

    Expected filename pattern:
        <Matched_Inflow_PartB>_qmo_<timeseries>.csv
    """
    sim_dir = Path(sim_dir)
    fname = f"{basis_partb}_qmo_{timeseries}.csv"
    fpath = sim_dir / fname
    if not fpath.exists():
        return None

    df = pd.read_csv(fpath)
    value_col = detect_product_b_value_col(df)
    vals = pd.to_numeric(df[value_col], errors="coerce").to_numpy(float)

    canonical_idx = _date_range_me(pd.Timestamp(product_b_start), pd.Timestamp(product_b_end))
    expected_months = len(canonical_idx)
    if len(vals) != expected_months:
        raise ValueError(
            f"{fname}: expected {expected_months} rows ({canonical_idx[0].date()} to {canonical_idx[-1].date()}) "
            f"but got {len(vals)}."
        )

    return pd.Series(vals, index=canonical_idx, name=basis_partb)


def load_product_b_all_timeseries(
    basis_partb: str,
    sim_dir: str | Path,
    timeseries_list: list[str],
    product_b_start: str | pd.Timestamp = PRODUCT_B_START,
    product_b_end: str | pd.Timestamp = PRODUCT_B_END,
) -> pd.DataFrame:
    """
    Load and concatenate all Product-B realizations for one basis term.

    Returns columns:
      timeseries, year, month, basis_sim
    """
    blocks = []
    for ts in timeseries_list:
        sim_ser = load_product_b_basis_series(
            basis_partb=basis_partb,
            sim_dir=sim_dir,
            timeseries=ts,
            product_b_start=product_b_start,
            product_b_end=product_b_end,
        )
        if sim_ser is None:
            continue

        block = ser_to_df(sim_ser).rename(columns={"value": "basis_sim"})
        block["timeseries"] = ts
        blocks.append(block)

    if not blocks:
        return pd.DataFrame(columns=["timeseries", "year", "month", "basis_sim"])

    out = pd.concat(blocks, ignore_index=True)
    out["timeseries"] = pd.Categorical(out["timeseries"], categories=timeseries_list, ordered=True)
    out = out.sort_values(["timeseries", "year", "month"]).reset_index(drop=True)
    return out


# -----------------------------------------------------------------------------
# Training-pair preparation
# -----------------------------------------------------------------------------

def build_training_pairs(
    df_pairs: pd.DataFrame,
    dss_data: dict[tuple[str, str], pd.Series],
    train_start: str = TRAIN_START,
    train_end: str = TRAIN_END,
) -> tuple[dict[tuple[str, str], dict[str, object]], list[tuple[str, str, str]]]:
    """
    Build training vectors for each target/predictor pair in qmap_pairs.csv.

    Returns
    -------
    training : dict
        Keyed by (target_part_b, predictor_part_b), with values containing
        predictor training DF, target training DF, bounds, and target C-part.
    skipped_rows : list[tuple[str, str, str]]
        (target_part_b, predictor_part_b, reason)
    """
    training: dict[tuple[str, str], dict[str, object]] = {}
    skipped_rows: list[tuple[str, str, str]] = []

    for _, row in df_pairs.iterrows():
        target_b = row["target_part_b"]
        target_c = row["target_part_c"]
        basis_b = row["predictor_part_b"]
        basis_c = row["predictor_part_c"]
        lower_bound = row["lower_bound"]
        upper_bound = row["upper_bound"]

        basis_key = (norm_token(basis_b), norm_token(basis_c))
        target_key = (norm_token(target_b), norm_token(target_c))

        if basis_key not in dss_data:
            skipped_rows.append((target_b, basis_b, f"missing DSS basis {basis_key}"))
            continue
        if target_key not in dss_data:
            skipped_rows.append((target_b, basis_b, f"missing DSS target {target_key}"))
            continue

        joined = pd.concat([dss_data[basis_key], dss_data[target_key]], axis=1, join="inner").dropna()
        if joined.empty:
            skipped_rows.append((target_b, basis_b, "no overlapping non-NaN DSS training data"))
            continue

        joined.columns = ["basis", "target"]
        train = joined.loc[train_start:train_end]
        if train.empty:
            skipped_rows.append((target_b, basis_b, f"no DSS training rows in {train_start} to {train_end}"))
            continue

        b_train = train["basis"]
        t_train = train["target"]
        if b_train.empty or t_train.empty:
            skipped_rows.append((target_b, basis_b, "empty basis/target training vectors"))
            continue

        training[(target_b, basis_b)] = {
            "b_train": ser_to_df(b_train),
            "t_train": ser_to_df(t_train),
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "target_c": target_c,
            "basis_c": basis_c,
        }

    return training, skipped_rows


# -----------------------------------------------------------------------------
# Main reusable runner
# -----------------------------------------------------------------------------

def run_product_b_qmap_from_pairs(
    *,
    pair_csv: str | Path,
    dss_file: str | Path,
    sim_in_dir: str | Path,
    out_dir: str | Path,
    train_start: str = TRAIN_START,
    train_end: str = TRAIN_END,
    product_b_start: str | pd.Timestamp = PRODUCT_B_START,
    product_b_end: str | pd.Timestamp = PRODUCT_B_END,
    output_tag: str = OUTPUT_TAG,
    dss_read_start: str = DSS_READ_START,
    dss_read_end: str = DSS_READ_END,
) -> dict[str, int]:
    """
    Run Product-B quantile mapping for all rows in a qmap_pairs.csv file.

    Parameters
    ----------
    pair_csv
        Path to qmap_pairs.csv. This can be anywhere in the repository.
    dss_file
        Path to CalSim DSS file containing training basis and target series.
    sim_in_dir
        Directory containing Product-B basis CSVs.
    out_dir
        Directory where mapped target CSVs will be written.
    train_start, train_end
        Training window used to build the basis and target distributions.
    product_b_start, product_b_end
        Canonical monthly time axis for Product-B basis files.
    output_tag
        Middle token in output filename, default ``qmap``.
    dss_read_start, dss_read_end
        Monthly DSS read window used when stitching DSS records.

    Returns
    -------
    dict[str, int]
        Summary counts for requested pairs, valid pairs, mapped pairs, and files written.
    """
    t_start = time.perf_counter()

    pair_csv = Path(pair_csv)
    sim_in_dir = Path(sim_in_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading qmap_pairs and DSS training data ...")
    print(f"  pair_csv  : {pair_csv}")
    print(f"  dss_file  : {dss_file}")
    print(f"  sim_in_dir: {sim_in_dir}")
    print(f"  out_dir   : {out_dir}")

    df_pairs = read_qmap_pairs(pair_csv)

    dss_specs: list[tuple[str, str]] = []
    for _, row in df_pairs.iterrows():
        dss_specs.append((row["predictor_part_b"], row["predictor_part_c"]))
        dss_specs.append((row["target_part_b"], row["target_part_c"]))

    dss_data = read_calsim_monthly_pairs(
        dssfile=dss_file,
        specs=dss_specs,
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )
    print(f"  {len(df_pairs)} pair(s) requested, {len(dss_data)} monthly DSS series found")

    timeseries_list = find_timeseries_in_dir(sim_in_dir)
    if not timeseries_list:
        raise RuntimeError(f"No Product B basis files found in: {sim_in_dir}")

    print(f"  Detected {len(timeseries_list)} Product B realizations: {', '.join(timeseries_list)}")

    training, skipped_rows = build_training_pairs(
        df_pairs=df_pairs,
        dss_data=dss_data,
        train_start=train_start,
        train_end=train_end,
    )

    if skipped_rows:
        print("  Skipped pair(s):")
        for target_b, basis_b, reason in skipped_rows:
            print(f"    {target_b:<30s} <- {basis_b:<20s} {reason}")

    if not training:
        raise RuntimeError("No valid DSS training pairs available.")

    print(f"  {len(training)} valid pair(s) ready for quantile mapping")
    print(f"  Setup complete ({time.perf_counter() - t_start:.1f}s)")

    # ------------------------------------------------------------------
    # Quantile map each pair
    # ------------------------------------------------------------------
    n_pairs = len(training)
    print(f"\nQuantile-mapping {n_pairs} pair(s) ...")

    qmap_cache: dict[tuple[str, str, str], pd.DataFrame] = {}
    basis_cache: dict[str, pd.DataFrame] = {}
    t_qmap = time.perf_counter()
    width = len(str(n_pairs))

    for i, ((target_b, basis_b), info) in enumerate(training.items(), 1):
        try:
            if basis_b not in basis_cache:
                basis_cache[basis_b] = load_product_b_all_timeseries(
                    basis_partb=basis_b,
                    sim_dir=sim_in_dir,
                    timeseries_list=timeseries_list,
                    product_b_start=product_b_start,
                    product_b_end=product_b_end,
                )

            sim_all = basis_cache[basis_b]
            if sim_all.empty:
                elapsed = time.perf_counter() - t_qmap
                print(f"  [{i:>{width}}/{n_pairs}] {target_b:<30s} <- {basis_b:<20s} skip ({elapsed:.1f}s)")
                continue

            simulation_df = sim_all[["year", "month", "basis_sim"]].rename(columns={"basis_sim": "value"})
            qmap = qmap_single(simulation_df, info["b_train"], info["t_train"]).copy()

            if "quantile_mapped_value" not in qmap.columns:
                raise KeyError(
                    f"qmap_single output missing 'quantile_mapped_value' for "
                    f"({target_b} <- {basis_b}). Columns: {list(qmap.columns)}"
                )
            if len(qmap) != len(sim_all):
                raise ValueError(
                    f"qmap_single returned {len(qmap)} rows but expected {len(sim_all)} "
                    f"for ({target_b} <- {basis_b})."
                )

            mapped = sim_all.copy()
            mapped["qmap_target"] = pd.to_numeric(
                qmap["quantile_mapped_value"],
                errors="coerce",
            ).to_numpy(float)

            lower_bound = info["lower_bound"]
            upper_bound = info["upper_bound"]
            if pd.notna(lower_bound):
                mapped["qmap_target"] = mapped["qmap_target"].clip(lower=float(lower_bound))
            if pd.notna(upper_bound):
                mapped["qmap_target"] = mapped["qmap_target"].clip(upper=float(upper_bound))

            qmap_cache[(target_b, basis_b, str(info["target_c"]))] = mapped
            tag = "ok"
        except Exception as exc:
            elapsed = time.perf_counter() - t_qmap
            print(f"  [{i:>{width}}/{n_pairs}] {target_b:<30s} <- {basis_b:<20s} ERROR ({elapsed:.1f}s)")
            print(f"      {type(exc).__name__}: {exc}")
            continue

        elapsed = time.perf_counter() - t_qmap
        print(f"  [{i:>{width}}/{n_pairs}] {target_b:<30s} <- {basis_b:<20s} {tag} ({elapsed:.1f}s)")

    print(f"  Mapped {len(qmap_cache)}/{n_pairs} pair(s) ({time.perf_counter() - t_qmap:.1f}s)")

    if not qmap_cache:
        raise RuntimeError("No Product B realizations were available for quantile mapping.")

    # ------------------------------------------------------------------
    # Split mapped results back to each realization and write outputs
    # ------------------------------------------------------------------
    print("\nWriting output CSVs ...")
    total_files = 0

    for ts in timeseries_list:
        chunk_files = 0

        for (target_b, basis_b, target_c), mapped in qmap_cache.items():
            block = mapped[mapped["timeseries"] == ts].copy()
            if block.empty:
                continue

            out_df = pd.DataFrame(
                {
                    "target_part_b": target_b,
                    "target_part_c": target_c,
                    "predictor_part_b": basis_b,
                    "Year": block["year"].astype(int).to_numpy(),
                    "Month": block["month"].astype(int).to_numpy(),
                    "basis_sim": block["basis_sim"].astype(float).to_numpy(),
                    "qmap_target": block["qmap_target"].astype(float).to_numpy(),
                }
            )

            out_fname = build_output_filename(target_b, ts, output_tag=output_tag)
            out_path = out_dir / out_fname
            out_df.to_csv(out_path, index=False)
            chunk_files += 1

        total_files += chunk_files
        print(f"  {ts}: {chunk_files} file(s)")

    elapsed_total = time.perf_counter() - t_start
    print(f"\nComplete: {total_files} file(s) written in {elapsed_total:.1f}s")

    return {
        "pairs_requested": int(len(df_pairs)),
        "pairs_valid": int(len(training)),
        "pairs_mapped": int(len(qmap_cache)),
        "files_written": int(total_files),
    }
