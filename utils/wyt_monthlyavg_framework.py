"""wyt_monthlyavg_framework.py

WYT × monthly-average reconstruction framework.

This module defines a function compute_wyt_monthlyavg() that implements the core computations.

Returned outputs (what the runner writes)
----------------------------------------
pattern_df  -> <prefix>_pattern_by_WYT_month.csv
    WIDE format: columns are terms, rows are (WYT, month)
    Month is a string abbreviation (Jan, Feb, Mar, ...).

hist_cmp_df -> <prefix>_actual_vs_synthetic.csv
    WIDE format: actual & synthetic values are side-by-side
    Columns: date, WY, month, WYT, <term>, <term>_synthetic, ...
    Month is a string abbreviation (Jan, Feb, Mar, ...).

targets dict -> each target output CSV (Product A or Product B)
    LONG format:
        date, WY, month, WYT, term, value
  

"""

from __future__ import annotations

import calendar
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


# -----------------------
# Small helpers
# -----------------------

def water_year(ts: pd.Timestamp) -> int:
    """CA convention: WY N is Oct(N-1)–Sep(N)."""
    return int(ts.year + (1 if ts.month >= 10 else 0))


def basin_tag(basin: str) -> str:
    """Map user string -> filename tag used by WYT CSVs."""
    b = basin.strip().lower()
    if b.startswith("sj"):
        return "SJ"
    if b.startswith("sac"):
        return "Sac"
    raise ValueError("basin must start with 'sj' or 'sac' (e.g. 'SJ' or 'Sac').")


def month_abbr(m: int) -> str:
    """Return Jan..Dec."""
    return calendar.month_abbr[int(m)]


def _infer_monthly_freq(dates: pd.Series) -> str:
    """Infer whether dates are aligned to month-end or month-start."""
    d = pd.to_datetime(dates)
    # Default to month-end if unclear (common in DSS exports)
    end_score = float(d.dt.is_month_end.mean())
    start_score = float(d.dt.is_month_start.mean())
    return "ME" if end_score >= start_score else "MS"


def _make_monthly_index(wy_min: int, wy_max: int, freq: str) -> pd.DataFrame:
    """Monthly dates spanning WY_min..WY_max inclusive, aligned to freq ('ME' or 'MS')."""
    if freq == "ME":
        start = pd.Timestamp(wy_min - 1, 10, 1) + pd.offsets.MonthEnd(0)
        end = pd.Timestamp(wy_max, 9, 1) + pd.offsets.MonthEnd(0)
        dates = pd.date_range(start=start, end=end, freq="ME")
    elif freq == "MS":
        start = pd.Timestamp(wy_min - 1, 10, 1)
        end = pd.Timestamp(wy_max, 9, 1)
        dates = pd.date_range(start=start, end=end, freq="MS")
    else:
        raise ValueError("freq must be 'ME' or 'MS'.")

    out = pd.DataFrame({"date": dates})
    out["WY"] = out["date"].apply(water_year).astype(int)
    out["month"] = out["date"].dt.month.astype(int)
    return out


# -----------------------
# Readers and path handling
# -----------------------

def read_wyt_fixed(path: Path) -> pd.DataFrame:
    """Read one WYT CSV and return columns WY (int), WYT (str).

    Expected columns include:
      - water_year
      - wyt_label

    (Extra columns like index, wyt code are ignored.)
    """
    df = pd.read_csv(path)

    missing = [c for c in ("water_year", "wyt_label") if c not in df.columns]
    if missing:
        raise KeyError(
            f"{path} is missing required columns {missing}. Found columns: {list(df.columns)}"
        )

    out = df[["water_year", "wyt_label"]].copy()
    out.columns = ["WY", "WYT"]

    out["WY"] = pd.to_numeric(out["WY"], errors="coerce").astype("Int64")
    out["WYT"] = out["WYT"].astype(str).str.strip()

    out = out.dropna(subset=["WY"]).copy()
    out = out[out["WYT"].str.lower().ne("nan")].copy()
    out["WY"] = out["WY"].astype(int)

    return out


def read_terms_csv(path: Path) -> Tuple[pd.DataFrame, List[str], str]:
    """Read the historical terms CSV.

    Input format assumptions (your fixed format):
      - first column is date (often 'date' or DSS 'Unnamed: 0')
      - from second column onward: 1+ term columns (names in header row)

    Returns:
      df: includes date (datetime), WY (int), month (int), term columns (float)
      terms: list of term column names
      inferred_freq: 'ME' or 'MS'
    """
    df = pd.read_csv(path)

    # DSS exports sometimes label the date column 'Unnamed: 0'
    if "date" not in df.columns:
        # If date column isn't literally named 'date', treat first column as date
        df = df.rename(columns={df.columns[0]: "date"})

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    inferred_freq = _infer_monthly_freq(df["date"])

    df["WY"] = df["date"].apply(water_year).astype(int)
    df["month"] = df["date"].dt.month.astype(int)

    meta = {"date", "WY", "month"}
    terms = [c for c in df.columns if c not in meta]

    # Coerce all term columns to numeric
    for c in terms:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Keep only columns with at least one value
    terms = [c for c in terms if df[c].notna().any()]
    if not terms:
        raise ValueError("No numeric term columns found in the terms CSV (after coercion).")

    return df, terms, inferred_freq


# -----------------------
# Core computations
# -----------------------

def _pattern_wide(df_terms_wyt: pd.DataFrame, terms: List[str]) -> pd.DataFrame:
    """Mean by (WYT, month), WIDE columns = term names."""
    return (
        df_terms_wyt.dropna(subset=["WYT"])
        .groupby(["WYT", "month"], as_index=False)[terms]
        .mean()
    )


def _pattern_wide_for_output(pattern_wide: pd.DataFrame, terms: List[str]) -> pd.DataFrame:
    """Convert month numbers to abbreviations and sort in WY order (Oct..Sep)."""

    out = pattern_wide.copy()

    # Sort in water-year month order: Oct, Nov, Dec, Jan, ..., Sep
    # month_sort: Oct->0, Nov->1, ..., Sep->11
    out["_month_sort"] = (out["month"] - 10) % 12
    out = out.sort_values(["WYT", "_month_sort"]).drop(columns=["_month_sort"]).reset_index(drop=True)

    out["month"] = out["month"].map(month_abbr)

    # Ensure column order
    return out[["WYT", "month"] + terms]


def _hist_actual_vs_synth_wide(
    df_hist: pd.DataFrame,
    pattern_wide: pd.DataFrame,
    terms: List[str],
) -> pd.DataFrame:
    """Wide historical table with actual and synthetic columns side-by-side."""

    syn = pattern_wide.rename(columns={c: f"{c}_synthetic" for c in terms})
    df2 = df_hist.merge(syn, on=["WYT", "month"], how="left")

    wide_cols: List[str] = []
    for c in terms:
        wide_cols.extend([c, f"{c}_synthetic"])

    out = df2[["date", "WY", "month", "WYT"] + wide_cols].copy()
    out = out.sort_values("date").reset_index(drop=True)

    # Month labels for output
    out["month"] = out["month"].map(month_abbr)

    return out


def compute_target_from_wyt(
    wyt_tbl: pd.DataFrame,
    pattern_wide: pd.DataFrame,
    terms: List[str],
    freq: str,
) -> pd.DataFrame:
    """Reconstruct target monthly series (LONG format)."""

    base = _make_monthly_index(int(wyt_tbl["WY"].min()), int(wyt_tbl["WY"].max()), freq=freq)
    base = base.merge(wyt_tbl, on="WY", how="left")  # adds WYT

    wide = base.merge(pattern_wide, on=["WYT", "month"], how="left")

    long = wide.melt(
        id_vars=["date", "WY", "month", "WYT"],
        value_vars=terms,
        var_name="term",
        value_name="value",
    )
    return long[["date", "WY", "month", "WYT", "term", "value"]]


def compute_wyt_monthlyavg(
    *,
    terms_csv: Path,
    basin: str,
    target_product: str,
    wyt_input_dir: Path,
    wyt_target_dir: Path,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Main entry point.

    Steps:
      1) Compute historical pattern by WYT × month
      2) Reconstruct historical series using pattern (actual vs synthetic)
      3) Reconstruct target(s) using Product A OR Product B WYTs

    Returns:
      pattern_df:  [WYT, month, <term columns...>]  (month is Jan..Dec)
      hist_cmp_df: [date, WY, month, WYT, <term>, <term>_synthetic, ...] (month is Jan..Dec)
      targets:     dict { name: df_long }, where df_long = [date, WY, month, WYT, term, value]
    """

    tag = basin_tag(basin)
    prod = target_product.strip().upper()
    if prod not in {"A", "B"}:
        raise ValueError("target_product must be 'A' or 'B'.")

    # --- Read terms + historical WYT
    df_terms, terms, freq = read_terms_csv(Path(terms_csv))
    hist_wyt = read_wyt_fixed(Path(wyt_input_dir) / f"_Historical_{tag}WYT.csv")
    df_hist = df_terms.merge(hist_wyt, on="WY", how="left")

    # --- Pattern
    pat_wide = _pattern_wide(df_hist, terms)
    pattern_df = _pattern_wide_for_output(pat_wide, terms)

    # --- Historical compare (wide)
    hist_cmp_df = _hist_actual_vs_synth_wide(df_hist, pat_wide, terms)

    # --- Targets
    targets: Dict[str, pd.DataFrame] = {}

    if prod == "A":
        wytA_path = Path(wyt_target_dir) / f"_ProductA_{tag}WYT.csv"
        wytA = read_wyt_fixed(wytA_path)
        name = f"ProductA_{tag}WYT"
        targets[name] = compute_target_from_wyt(wytA, pat_wide, terms, freq=freq)

    else:  # prod == 'B' (ALWAYS 10)
        expected_files = [
            Path(wyt_target_dir) / f"_ProductB_{tag}WYT_n{str(i).zfill(2)}.csv"
            for i in range(1, 11)
        ]
        missing = [p.name for p in expected_files if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Product B requires ALL 10 ensemble WYT files, but these are missing:\n  - "
                + "\n  - ".join(missing)
            )

        for p in expected_files:
            wytB = read_wyt_fixed(p)
            name = p.stem.lstrip("_")  # e.g. 'ProductB_SJWYT_n01'
            targets[name] = compute_target_from_wyt(wytB, pat_wide, terms, freq=freq)

    return pattern_df, hist_cmp_df, targets
