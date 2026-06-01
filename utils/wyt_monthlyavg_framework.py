"""wyt_monthlyavg_framework.py

WYT × monthly-average reconstruction framework.

Historical series are loaded via DSS + term spec mode:
  - a CSV containing term_part_b / term_part_c / basin_wyt rows
  - a historical DSS file from which the monthly series are extracted

Returned outputs (what the runner writes)
----------------------------------------
pattern_df  -> <prefix>_pattern_by_WYT_month.csv
    WIDE format: columns are terms, rows are (WYT, month)
    Month is a string abbreviation (Jan, Feb, Mar, ...).

hist_cmp_df -> <prefix>_actual_vs_reconstructed.csv
    WIDE format: actual & reconstructed values are side-by-side.
    If all terms use the same WYT basin, the historical WYT column is named
    'WYT' for backward compatibility. If multiple basins are used, one WYT
    column is included per basin (for example, SJ_WYT and Sac_WYT).

targets dict -> each target output CSV (Product A or Product B)
    LONG format:
        date, basin_wyt, WYT, part_b, part_c, wyt_monthly_avg
"""

from __future__ import annotations

import calendar
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from utils import dss_io


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



def canonical_basin_wyt(basin: str) -> str:
    """Return a canonical lower-case basin token for CSV/output use."""
    tag = basin_tag(basin)
    return tag.lower()



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
    basin_wyt: str

    @property
    def wyt_tag(self) -> str:
        return basin_tag(self.basin_wyt)




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
    """Read a DSS term spec CSV with B-part / C-part / basin columns.

    Required columns:
      - term_part_b
      - term_part_c
      - basin_wyt

    If the B-part is unique across rows, it is used as the output term label.
    Otherwise the label defaults to '<B>__<C>' so output column names stay unique.
    """
    df = pd.read_csv(path)
    col_lookup = {_norm_header(c): c for c in df.columns}

    try:
        b_col = col_lookup["TERM_PART_B"]
        c_col = col_lookup["TERM_PART_C"]
        basin_col = col_lookup["BASIN_WYT"]
    except KeyError as exc:
        raise KeyError(
            f"{path} must contain columns 'term_part_b', 'term_part_c', and 'basin_wyt'. "
            f"Found columns: {list(df.columns)}"
        ) from exc

    raw_rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        b_part = clean_text(row[b_col])
        c_part = clean_text(row[c_col])
        basin = clean_text(row[basin_col])
        if not b_part and not c_part and not basin:
            continue
        if not b_part or not c_part or not basin:
            raise ValueError(
                f"{path} contains a row with a missing B-part, C-part, or basin_wyt: {row.to_dict()}"
            )

        # Validate and canonicalize the basin token immediately.
        basin = canonical_basin_wyt(basin)

        raw_rows.append(
            {
                "b_part": b_part,
                "c_part": c_part,
                "basin_wyt": basin,
            }
        )

    if not raw_rows:
        raise ValueError(f"No valid B-part / C-part / basin_wyt rows found in {path}.")

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
                f"Duplicate output term name '{term_name}' generated from {path}. "
                "Ensure B-parts are unique or that B+C combinations are unique."
            )
        seen_names.add(term_key)
        out.append(
            TermSpec(
                term_name=term_name,
                b_part=row["b_part"],
                c_part=row["c_part"],
                basin_wyt=row["basin_wyt"],
            )
        )

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

    # Direct open (no junction; catalog_flag=True) + the shared faithful read
    # loop in utils.dss_io. dss_io.read_monthly_series is a byte-equivalent
    # copy of the prior inline loop: same "/*/*/*/*/1MON/*" catalog query,
    # same case-insensitive (B, C) bucketing, same (D-part, path) sort,
    # same -900 sentinel and end-of-month index shift, same master.update
    # stitch onto a fixed month-end index.
    with dss_io.open_dss(str(dssfile), version=6, catalog_flag=True,
                         use_junction=False) as dss:
        return dss_io.read_monthly_series(
            dss, requested, dss_read_start, dss_read_end)



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
            missing.append(
                f"{spec.term_name} ({spec.b_part}, {spec.c_part}, basin_wyt={spec.basin_wyt})"
            )
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





def _load_historical_wyts(
    wyt_input_dir: Path,
    basin_tags: list[str],
) -> dict[str, pd.DataFrame]:
    """Load the required historical WYT tables keyed by basin tag."""
    out: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for tag in sorted(set(basin_tags)):
        path = Path(wyt_input_dir) / f"_Historical_{tag}WYT.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        out[tag] = read_wyt_fixed(path)

    if missing:
        raise FileNotFoundError(
            "Missing historical WYT file(s):\n  - " + "\n  - ".join(missing)
        )

    return out



def _load_product_a_wyts(
    wyt_target_dir: Path,
    basin_tags: list[str],
) -> dict[str, pd.DataFrame]:
    """Load Product A target WYT tables keyed by basin tag."""
    out: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for tag in sorted(set(basin_tags)):
        path = Path(wyt_target_dir) / f"_{tag}WYT.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        out[tag] = read_wyt_fixed(path)

    if missing:
        raise FileNotFoundError(
            "Missing Product A WYT file(s):\n  - " + "\n  - ".join(missing)
        )

    return out



def _load_product_b_wyts(
    wyt_target_dir: Path,
    basin_tags: list[str],
    ensemble: str,
) -> dict[str, pd.DataFrame]:
    """Load Product B target WYT tables keyed by basin tag for one ensemble."""
    out: dict[str, pd.DataFrame] = {}
    missing: list[str] = []

    for tag in sorted(set(basin_tags)):
        path = Path(wyt_target_dir) / f"_{tag}WYT_{ensemble}.csv"
        if not path.exists():
            missing.append(path.name)
            continue
        out[tag] = read_wyt_fixed(path)

    if missing:
        raise FileNotFoundError(
            f"Missing Product B WYT file(s) for {ensemble}:\n  - " + "\n  - ".join(missing)
        )

    return out


# -----------------------
# Core computations
# -----------------------


def _term_pattern(
    df_terms: pd.DataFrame,
    hist_wyt: pd.DataFrame,
    spec: TermSpec,
) -> pd.DataFrame:
    """Mean monthly pattern for one term using that term's assigned WYT basin."""
    cols = ["WY", "month", spec.term_name]
    df = df_terms[cols].merge(hist_wyt, on="WY", how="left")
    return (
        df.dropna(subset=["WYT"])
        .groupby(["WYT", "month"], as_index=False)[spec.term_name]
        .mean()
    )



def _pattern_wide(
    df_terms: pd.DataFrame,
    term_specs: List[TermSpec],
    hist_wyts: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Mean by (WYT, month), WIDE columns = term names.

    Each term is grouped against the historical WYT series for its own basin_wyt.
    """
    out: pd.DataFrame | None = None

    for spec in term_specs:
        pat = _term_pattern(df_terms, hist_wyts[spec.wyt_tag], spec)
        if out is None:
            out = pat
        else:
            out = out.merge(pat, on=["WYT", "month"], how="outer")

    if out is None:
        return pd.DataFrame(columns=["WYT", "month"])

    return out



def _pattern_wide_for_output(pattern_wide: pd.DataFrame, terms: List[str]) -> pd.DataFrame:
    """Convert month numbers to abbreviations and sort in WY order (Oct..Sep)."""
    out = pattern_wide.copy()

    # Sort in water-year month order: Oct, Nov, Dec, Jan, ..., Sep
    # month_sort: Oct->0, Nov->1, ..., Sep->11
    out["_month_sort"] = (out["month"] - 10) % 12
    out = out.sort_values(["WYT", "_month_sort"]).drop(columns=["_month_sort"]).reset_index(drop=True)

    out["month"] = out["month"].map(month_abbr)
    return out[["WYT", "month"] + terms]



def _hist_actual_vs_reconstructed_wide(
    df_terms: pd.DataFrame,
    pattern_wide: pd.DataFrame,
    term_specs: List[TermSpec],
    hist_wyts: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Wide historical table with actual and reconstructed columns side-by-side.

    When multiple WYT basins are used across terms, one historical WYT column is
    included per basin. When only one basin is used, the legacy single 'WYT'
    column is preserved.
    """
    out = df_terms[["date", "WY", "month"]].copy()
    basin_tags = sorted(hist_wyts)

    if len(basin_tags) == 1:
        wyt_col_map = {basin_tags[0]: "WYT"}
    else:
        wyt_col_map = {tag: f"{tag}_WYT" for tag in basin_tags}

    for tag in basin_tags:
        out = out.merge(
            hist_wyts[tag].rename(columns={"WYT": wyt_col_map[tag]}),
            on="WY",
            how="left",
        )

    for spec in term_specs:
        term = spec.term_name
        wyt_col = wyt_col_map[spec.wyt_tag]
        pat = pattern_wide[["WYT", "month", term]].rename(columns={term: "_reconstructed"})
        recon_lookup = out[[wyt_col, "month"]].rename(columns={wyt_col: "WYT"})
        recon_series = recon_lookup.merge(pat, on=["WYT", "month"], how="left")["_reconstructed"]

        out[f"{term}_actual"] = pd.to_numeric(df_terms[term], errors="coerce").to_numpy()
        out[f"{term}_reconstructed"] = pd.to_numeric(recon_series, errors="coerce").to_numpy()

    out = out.sort_values("date").reset_index(drop=True)

    wyt_cols = [wyt_col_map[tag] for tag in basin_tags]
    wide_cols: List[str] = []
    for spec in term_specs:
        wide_cols.extend([f"{spec.term_name}_actual", f"{spec.term_name}_reconstructed"])

    return out[["date"] + wyt_cols + wide_cols]



def compute_target_from_wyt(
    wyt_tbls: dict[str, pd.DataFrame],
    pattern_wide: pd.DataFrame,
    term_specs: List[TermSpec],
) -> pd.DataFrame:
    """Reconstruct target monthly series (LONG format).

    Each term uses the target WYT series associated with its own basin_wyt.
    """
    pieces: list[pd.DataFrame] = []

    for term_order, spec in enumerate(term_specs):
        wyt_tbl = wyt_tbls[spec.wyt_tag]
        base = _make_monthly_index(int(wyt_tbl["WY"].min()), int(wyt_tbl["WY"].max()))
        base = base.merge(wyt_tbl, on="WY", how="left")  # adds WYT

        pat = pattern_wide[["WYT", "month", spec.term_name]].rename(
            columns={spec.term_name: "wyt_monthly_avg"}
        )
        long = base.merge(pat, on=["WYT", "month"], how="left")
        long["part_b"] = spec.b_part
        long["part_c"] = spec.c_part
        long["basin_wyt"] = spec.basin_wyt
        long["_term_order"] = term_order
        pieces.append(long[["date", "month", "basin_wyt", "WYT", "part_b", "part_c", "wyt_monthly_avg", "_term_order"]])

    if not pieces:
        return pd.DataFrame(
            columns=["date", "basin_wyt", "WYT", "part_b", "part_c", "wyt_monthly_avg"]
        )

    out = pd.concat(pieces, ignore_index=True)
    out = out.sort_values(["_term_order", "date"]).drop(columns=["_term_order", "month"]).reset_index(drop=True)
    return out


# ── Public helpers (split DSS read from target computation) ─────────────


def compute_wyt_pattern(
    *,
    wyt_input_dir: Path,
    term_specs_csv: Path,
    historical_dssfile: Path,
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[TermSpec]]:
    """Compute the historical pattern and comparison (reads DSS once)."""
    df_terms, terms, term_specs = read_terms_from_dss(
        term_specs_csv=Path(term_specs_csv),
        dssfile=Path(historical_dssfile),
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )

    basin_tags = sorted({spec.wyt_tag for spec in term_specs})
    hist_wyts = _load_historical_wyts(Path(wyt_input_dir), basin_tags)

    pat_wide = _pattern_wide(df_terms, term_specs, hist_wyts)
    pattern_df = _pattern_wide_for_output(pat_wide, terms)
    hist_cmp_df = _hist_actual_vs_reconstructed_wide(df_terms, pat_wide, term_specs, hist_wyts)

    return pattern_df, hist_cmp_df, pat_wide, term_specs



def plot_wyt_hist_validation(
    hist_cmp_df: pd.DataFrame,
    term_specs: List[TermSpec],
    figures_dir: Path,
    *,
    plot_start: str | pd.Timestamp = "1971-10-01",
    plot_end: str | pd.Timestamp = "2018-09-30",
    unit: str = "",
) -> List[Path]:
    """Write one TS+CDF figure per term comparing actual vs reconstructed.

    Uses the wide ``hist_cmp_df`` produced by :func:`compute_wyt_pattern`
    (columns ``date``, ``<term>_actual``, ``<term>_reconstructed``). The
    plot window is clipped to ``[plot_start, plot_end]``; the underlying
    CSV is left untouched. Returns the list of figure paths written.
    """
    from utils.validation_plots import Series, plot_ts_cdf

    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    start = pd.Timestamp(plot_start)
    end = pd.Timestamp(plot_end)

    dates = pd.to_datetime(hist_cmp_df["date"])
    mask = (dates >= start) & (dates <= end)
    sub_dates = dates[mask].to_numpy()

    written: List[Path] = []
    for spec in term_specs:
        actual_col = f"{spec.term_name}_actual"
        recon_col = f"{spec.term_name}_reconstructed"
        if actual_col not in hist_cmp_df.columns or recon_col not in hist_cmp_df.columns:
            continue
        actual = pd.to_numeric(hist_cmp_df.loc[mask, actual_col], errors="coerce").to_numpy(dtype=float)
        recon = pd.to_numeric(hist_cmp_df.loc[mask, recon_col], errors="coerce").to_numpy(dtype=float)
        out_path = figures_dir / f"{spec.b_part}.png"
        plot_ts_cdf(
            series=[
                Series("Historical", sub_dates, actual),
                Series("Reconstructed", sub_dates, recon),
            ],
            title=spec.b_part,
            unit=unit,
            compute_metrics_from=0,
            out_path=out_path,
        )
        written.append(out_path)
    return written



def compute_product_targets(
    *,
    product: str,
    wyt_target_dir: Path,
    pat_wide: pd.DataFrame,
    term_specs: List[TermSpec],
) -> Dict[str, pd.DataFrame]:
    """Compute targets for a single product using a precomputed pattern.

    Returns:
      dict { name: df_long }
    """
    prod = product.strip().upper()
    if prod not in {"A", "B"}:
        raise ValueError("product must be 'A' or 'B'.")

    basin_tags = sorted({spec.wyt_tag for spec in term_specs})
    targets: Dict[str, pd.DataFrame] = {}

    if prod == "A":
        wyt_tables = _load_product_a_wyts(Path(wyt_target_dir), basin_tags)
        name = "product_a"
        targets[name] = compute_target_from_wyt(wyt_tables, pat_wide, term_specs)
    else:
        for i in range(1, 11):
            ensemble = f"n{str(i).zfill(2)}"
            wyt_tables = _load_product_b_wyts(Path(wyt_target_dir), basin_tags, ensemble)
            name = f"product_b_{ensemble}"
            targets[name] = compute_target_from_wyt(wyt_tables, pat_wide, term_specs)

    return targets
