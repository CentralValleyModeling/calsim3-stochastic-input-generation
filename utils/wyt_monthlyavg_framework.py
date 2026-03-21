"""wyt_monthlyavg_framework.py

WYT × monthly-average reconstruction framework.

Historical series are loaded via DSS + term spec mode:
  - a CSV containing term_part_b / term_part_c pairs
  - a historical DSS file from which the monthly series are extracted

Returned outputs (what the runner writes)
----------------------------------------
pattern_df  -> <prefix>_pattern_by_WYT_month.csv
    WIDE format: columns are terms, rows are (WYT, month)
    Month is a string abbreviation (Jan, Feb, Mar, ...).

hist_cmp_df -> <prefix>_actual_vs_synthetic.csv
    WIDE format: actual & synthetic values are side-by-side
    Columns: year, month, WYT, <term>_actual, <term>_synthetic, ...
   

targets dict -> each target output CSV (Product A or Product B)
    LONG format:
        year, month, WYT, part_b, part_c, wyt_monthly_avg
"""

from __future__ import annotations

import calendar
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


DEFAULT_DSS_READ_START = "1921-10-31"
DEFAULT_DSS_READ_END = "2021-09-30"


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



def clean_text(value: object) -> str:
    """Return a stripped string, or empty string for null-ish values."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text



def norm_token(value: object) -> str:
    """Case-insensitive token normalization used for DSS pathname matching."""
    return clean_text(value).upper()



def _norm_header(value: object) -> str:
    """Normalize a CSV header for forgiving column matching."""
    return re.sub(r"[^A-Z0-9]+", "_", norm_token(value)).strip("_")



def _make_monthly_index(wy_min: int, wy_max: int) -> pd.DataFrame:
    """Monthly dates spanning WY_min..WY_max inclusive, aligned to month-end."""
    start = pd.Timestamp(wy_min - 1, 10, 1) + pd.offsets.MonthEnd(0)
    end = pd.Timestamp(wy_max, 9, 1) + pd.offsets.MonthEnd(0)
    dates = pd.date_range(start=start, end=end, freq="ME")

    out = pd.DataFrame({"date": dates})
    out["WY"] = out["date"].apply(water_year).astype(int)
    out["month"] = out["date"].dt.month.astype(int)
    return out


@dataclass(frozen=True) 
class TermSpec:
    term_name: str
    b_part: str
    c_part: str



def _load_hecdss():
    """Load HecDss from pydsstools."""
    from pydsstools.heclib.dss import HecDss
    return HecDss


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



def read_term_specs_csv(path: Path) -> List[TermSpec]:
    """Read a DSS term spec CSV with B-part / C-part columns.

    Required columns:
      - term_part_b
      - term_part_c

    The output term label defaults to the B-part when it is unique across rows,
    otherwise to '<B>__<C>' so output column names stay unique.
    """
    df = pd.read_csv(path)
    col_lookup = {_norm_header(c): c for c in df.columns}

    try:
        b_col = col_lookup["TERM_PART_B"]
        c_col = col_lookup["TERM_PART_C"]
    except KeyError as exc:
        raise KeyError(
            f"{path} must contain columns 'term_part_b' and 'term_part_c'. "
            f"Found columns: {list(df.columns)}"
        ) from exc

    raw_rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        b_part = clean_text(row[b_col])
        c_part = clean_text(row[c_col])
        if not b_part and not c_part:
            continue
        if not b_part or not c_part:
            raise ValueError(
                f"{path} contains a row with a missing B-part or C-part: {row.to_dict()}"
            )
        raw_rows.append({"b_part": b_part, "c_part": c_part})

    if not raw_rows:
        raise ValueError(f"No valid B-part / C-part rows found in {path}.")

    b_counts = Counter(norm_token(r["b_part"]) for r in raw_rows)
    out: list[TermSpec] = []
    seen_names: set[str] = set()

    for row in raw_rows:
        if b_counts[norm_token(row["b_part"])] == 1:
            term_name = row["b_part"]
        else:
            term_name = f"{row['b_part']}__{row['c_part']}"

        term_key = norm_token(term_name)
        if term_key in seen_names:
            raise ValueError(
                f"Duplicate output term name '{term_name}' generated from {path}."
            )
        seen_names.add(term_key)
        out.append(TermSpec(term_name=term_name, b_part=row["b_part"], c_part=row["c_part"]))

    return out



def read_calsim_monthly_pairs(
    dssfile: str | Path,
    specs: list[tuple[str, str]],
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> dict[tuple[str, str], pd.Series]:
    """Read multiple CalSim monthly DSS series keyed by (B-part, C-part).

    Matching is case-insensitive on pathname B and C parts. All monthly paths
    matching a requested (B, C) pair are stitched together by updating a common
    monthly index.

    DSS monthly period data are labeled at the end of the period. For example,
    a January monthly value may be returned as 01FEB 00:00 (equivalent to
    31JAN 24:00 in DSS). Shift the timestamp back one month so the pandas index
    reflects the actual data month represented by the value.
    """
    requested = {
        (norm_token(b), norm_token(c))
        for b, c in specs
        if clean_text(b) and clean_text(c)
    }
    if not requested:
        return {}

    full_idx = pd.date_range(dss_read_start, dss_read_end, freq="ME")
    out: dict[tuple[str, str], pd.Series] = {}
    HecDss = _load_hecdss()

    with HecDss.Open(str(dssfile), version=6, catalog_flag=True) as dss:  # pragma: no cover
        paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        bucket: dict[tuple[str, str], list[str]] = {}

        for path in paths:
            parts = path.strip("/").split("/")
            if len(parts) != 6:
                continue
            b_part = norm_token(parts[1])
            c_part = norm_token(parts[2])
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

                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                master.update(pd.Series(vals, index=idx))

            if master.notna().any():
                out[key] = master

    return out



def read_terms_from_dss(
    term_specs_csv: Path,
    dssfile: Path,
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> Tuple[pd.DataFrame, List[str], List[TermSpec]]:
    """Build the historical term dataframe by reading B/C-part specs from DSS."""
    term_specs = read_term_specs_csv(term_specs_csv)
    requested_pairs = [(spec.b_part, spec.c_part) for spec in term_specs]
    series_by_key = read_calsim_monthly_pairs(
        dssfile=dssfile,
        specs=requested_pairs,
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )

    full_idx = pd.date_range(dss_read_start, dss_read_end, freq="ME")
    out = pd.DataFrame({"date": full_idx})

    missing: list[str] = []
    terms: list[str] = []
    for spec in term_specs:
        key = (norm_token(spec.b_part), norm_token(spec.c_part))
        if key not in series_by_key:
            missing.append(f"{spec.term_name} ({spec.b_part}, {spec.c_part})")
            continue

        out[spec.term_name] = pd.to_numeric(
            series_by_key[key].reindex(full_idx), errors="coerce"
        ).to_numpy()
        terms.append(spec.term_name)

    if missing:
        raise KeyError(
            "The following B/C-part term specs were not found in the historical DSS file:\n  - "
            + "\n  - ".join(missing)
        )

    if not terms:
        raise ValueError("No DSS term series were loaded from the requested term specs.")

    out["WY"] = out["date"].apply(water_year).astype(int)
    out["month"] = out["date"].dt.month.astype(int)

    return out, terms, term_specs



def _load_historical_terms(
    *,
    term_specs_csv: Path,
    historical_dssfile: Path,
    dss_read_start: str,
    dss_read_end: str,
) -> Tuple[pd.DataFrame, List[str], List[TermSpec]]:
    """Load historical terms from DSS using a term spec CSV."""
    return read_terms_from_dss(
        term_specs_csv=term_specs_csv,
        dssfile=historical_dssfile,
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )


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
    return out[["WYT", "month"] + terms]



def _hist_actual_vs_synth_wide(
    df_hist: pd.DataFrame,
    pattern_wide: pd.DataFrame,
    terms: List[str],
) -> pd.DataFrame:
    """Wide historical table with actual and synthetic columns side-by-side."""
    syn = pattern_wide.rename(columns={c: f"{c}_synthetic" for c in terms})
    df2 = df_hist.rename(columns={c: f"{c}_actual" for c in terms})
    df2 = df2.merge(syn, on=["WYT", "month"], how="left")

    wide_cols: List[str] = []
    for c in terms:
        wide_cols.extend([f"{c}_actual", f"{c}_synthetic"])

    out = df2[["date", "WY", "month", "WYT"] + wide_cols].copy()
    out = out.sort_values("date").reset_index(drop=True)
    out["year"] = out["date"].dt.year
    out = out[["year", "month", "WYT"] + wide_cols]
    return out



def compute_target_from_wyt(
    wyt_tbl: pd.DataFrame,
    pattern_wide: pd.DataFrame,
    term_specs: List[TermSpec],
) -> pd.DataFrame:
    """Reconstruct target monthly series (LONG format)."""
    terms = [s.term_name for s in term_specs]
    base = _make_monthly_index(int(wyt_tbl["WY"].min()), int(wyt_tbl["WY"].max()))
    base = base.merge(wyt_tbl, on="WY", how="left")  # adds WYT

    wide = base.merge(pattern_wide, on=["WYT", "month"], how="left")

    long = wide.melt(
        id_vars=["date", "WY", "month", "WYT"],
        value_vars=terms,
        var_name="term",
        value_name="wyt_monthly_avg",
    )
    spec_map = {s.term_name: (s.b_part, s.c_part) for s in term_specs}
    long["part_b"] = long["term"].map(lambda t: spec_map[t][0])
    long["part_c"] = long["term"].map(lambda t: spec_map[t][1])
    long["year"] = long["date"].dt.year
    return long[["year", "month", "WYT", "part_b", "part_c", "wyt_monthly_avg"]]


# ── Public helpers (split DSS read from target computation) ─────────────

def compute_wyt_pattern(
    *,
    basin: str,
    wyt_input_dir: Path,
    term_specs_csv: Path,
    historical_dssfile: Path,
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, "List[TermSpec]", str]:
    """Compute the historical pattern and comparison (reads DSS once).

    Returns:
      pattern_df, hist_cmp_df, pat_wide, term_specs, tag
    """
    tag = basin_tag(basin)
    df_terms, terms, term_specs = _load_historical_terms(
        term_specs_csv=Path(term_specs_csv),
        historical_dssfile=Path(historical_dssfile),
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )
    hist_wyt = read_wyt_fixed(Path(wyt_input_dir) / f"_Historical_{tag}WYT.csv")
    df_hist = df_terms.merge(hist_wyt, on="WY", how="left")

    pat_wide = _pattern_wide(df_hist, terms)
    pattern_df = _pattern_wide_for_output(pat_wide, terms)
    hist_cmp_df = _hist_actual_vs_synth_wide(df_hist, pat_wide, terms)

    return pattern_df, hist_cmp_df, pat_wide, term_specs, tag


def compute_product_targets(
    *,
    product: str,
    wyt_target_dir: Path,
    pat_wide: pd.DataFrame,
    term_specs: "List[TermSpec]",
    tag: str,
) -> Dict[str, pd.DataFrame]:
    """Compute targets for a single product using a precomputed pattern.

    Returns:
      dict { name: df_long }
    """
    prod = product.strip().upper()
    if prod not in {"A", "B"}:
        raise ValueError("product must be 'A' or 'B'.")

    targets: Dict[str, pd.DataFrame] = {}

    if prod == "A":
        wytA_path = Path(wyt_target_dir) / f"_{tag}WYT.csv"
        wytA = read_wyt_fixed(wytA_path)
        name = f"product_a_{tag}WYT"
        targets[name] = compute_target_from_wyt(wytA, pat_wide, term_specs)
    else:
        expected_files = [
            Path(wyt_target_dir) / f"_{tag}WYT_n{str(i).zfill(2)}.csv"
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
            name = "product_b_" + p.stem.lstrip("_")
            targets[name] = compute_target_from_wyt(wytB, pat_wide, term_specs)

    return targets
