"""
Shared standard-value (SV) CSV helpers
======================================
Centralizes the CSV read/normalize idioms repeated across the pipeline for the
standard SV format ``Part B, Part C, Year, Month, Value``.

Behavior-preservation note
--------------------------
``load_sv_series`` and ``to_validation_df`` are *faithful copies* of two
pre-existing functions and must keep their exact behavior (no tests exist):

- ``load_sv_series`` reproduces
  ``utils/qmap_product_a_from_pairs.load_product_a_rim_series``.  It uses a
  plain ``pd.read_csv`` (NOT the normalized :func:`read_sv_csv`) on purpose --
  routing it through the normalized reader would change its behavior.
- ``to_validation_df`` reproduces
  ``mod_hydrology/calsimhydro/_3_postprocess_product_a.to_validation_csv``
  (water-year window filter, column order, sort, empty-frame shape).

``read_sv_csv`` captures the ``pd.read_csv(skipinitialspace=True)`` +
strip-column-names idiom used by ``read_qmap_pairs`` and many numbered
scripts.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# Canonical column order for the standard SV / validation CSV format.
SV_COLUMNS = ["Part B", "Part C", "Year", "Month", "Value"]


# -- Normalized reader --------------------------------------------------------

def read_sv_csv(path) -> pd.DataFrame:
    """Read a CSV with the common normalization idiom.

    Equivalent to ``pd.read_csv(path, skipinitialspace=True)`` followed by
    stripping whitespace from the column names -- the pattern repeated in
    ``read_qmap_pairs`` and numerous numbered scripts.
    """
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# -- Series loader (faithful copy of load_product_a_rim_series) ---------------

def load_sv_series(csv_path, part_b, part_c) -> pd.Series:
    """Load one Part B + Part C series from a standard SV CSV.

    Returns a monthly ``pd.Series`` with a month-end ``DatetimeIndex`` (empty
    float Series if the pair is absent).  Faithful copy of
    ``qmap_product_a_from_pairs.load_product_a_rim_series`` -- uses a plain
    ``pd.read_csv`` to preserve that function's exact behavior.
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


# -- Wide -> validation format (faithful copy of to_validation_csv) -----------

def to_validation_df(df, start_wy, end_wy) -> pd.DataFrame:
    """Convert a wide (Date index x ``"B/C"`` columns) DataFrame to the
    validation format ``Part B, Part C, Year, Month, Value``.

    Filters to the water-year window [Oct 1 of ``start_wy``-1,
    Sep 30 of ``end_wy``], splits the ``"B/C"`` column label, sorts, and
    returns an empty 5-column frame when nothing falls in the window.
    Faithful copy of ``_3_postprocess_product_a.to_validation_csv``.
    """
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date = pd.Timestamp(end_wy, 9, 30)

    long = df.stack().reset_index()
    long.columns = ["Date", "PartBC", "Value"]
    long["Date"] = pd.to_datetime(long["Date"])

    mask = (long["Date"] >= start_date) & (long["Date"] <= end_date)
    long = long.loc[mask].copy()

    if long.empty:
        return pd.DataFrame(columns=SV_COLUMNS)

    long[["Part B", "Part C"]] = long["PartBC"].str.split("/", expand=True, n=1)
    long["Year"] = long["Date"].dt.year
    long["Month"] = long["Date"].dt.month

    long = long.dropna(subset=["Value"])
    long = long[SV_COLUMNS]
    return long.sort_values(
        ["Part B", "Part C", "Year", "Month"]
    ).reset_index(drop=True)
