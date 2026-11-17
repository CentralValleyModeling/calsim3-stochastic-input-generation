"""
Shared standard-value (SV) CSV helpers
======================================
Centralizes the CSV read/normalize idioms repeated across the pipeline for the
standard SV format ``Part B, Part C, Year, Month, Value``, and
``write_delivery_csv``, which writes a Historical_Unsplit or Product A series over
``DELIVERY_WY``.

Behavior-preservation note
--------------------------
``to_validation_df`` is a *faithful copy* of a pre-existing function and must
keep its exact behavior (no tests exist): it reproduces
``mod_hydrology/calsimhydro/_3_postprocess_single.to_validation_csv``
(water-year window filter, column order, sort, empty-frame shape).
``load_sv_series`` reads with a plain ``pd.read_csv``, not the normalized
:func:`read_sv_csv`, which would change what it returns.

``read_sv_csv`` captures the ``pd.read_csv(skipinitialspace=True)`` +
strip-column-names idiom used by ``read_qmap_pairs`` and many numbered
scripts.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from utils.paths import DELIVERY, DELIVERY_WY

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


# -- Delivery writer -----------------------------------------------------------

def delivery_name(stem: str, product: str, span=DELIVERY_WY) -> str:
    """The file name of a delivery CSV: ``<stem>_<tag>_<first WY>_<last WY>.csv``, with the
    tag of ``product`` in ``utils.paths.DELIVERY`` (``productA``, ``historicalUnsplit``)."""
    return f"{stem}_{DELIVERY[product]['tag']}_{span[0]}_{span[1]}.csv"


def write_delivery_csv(df: pd.DataFrame, folder, stem: str, product: str) -> Path:
    """Write the rows of ``df`` (with ``Year`` and ``Month``) that fall in
    ``utils.paths.DELIVERY_WY`` as ``<folder>/<stem>_<tag>_<first WY>_<last WY>.csv``
    (:func:`delivery_name`), and remove the folder's other spans of the same stem and tag: the
    compiler reads every CSV in a folder, so two spans of one series would give it two values
    for a month. Returns the path written."""
    wy = df["Year"].astype(int) + (df["Month"].astype(int) >= 10)
    keep = wy.between(*DELIVERY_WY)
    if not keep.any():
        raise ValueError(f"{stem}: no rows in WY{DELIVERY_WY[0]}-{DELIVERY_WY[1]}")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / delivery_name(stem, product, (wy[keep].min(), wy[keep].max()))
    prefix = f"{stem}_{DELIVERY[product]['tag']}"
    span = re.compile(re.escape(prefix) + r"_\d{4}_\d{4}\.csv")
    for old in folder.glob(f"{prefix}_*.csv"):
        if old.name != out.name and span.fullmatch(old.name):
            old.unlink()
    df[keep].to_csv(out, index=False)
    return out


# -- Series loader -------------------------------------------------------------

def load_sv_series(csv_path, part_b, part_c) -> pd.Series:
    """Load one Part B + Part C series from a standard SV CSV.

    Returns a monthly ``pd.Series`` with a month-end ``DatetimeIndex`` (empty
    float Series if the pair is absent).
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
    Faithful copy of ``_3_postprocess_single.to_validation_csv``.
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
