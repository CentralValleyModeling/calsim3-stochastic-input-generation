"""
WGEN Closure Terms: Weighted vs 4-Year-Block Stitched, with Correlations

What this does
--------------
1) Reads ALL monthly closure terms from a CalSim DSS file Part C ='CLOSURE-TERM'.
2) Reads WGEN resampled dates CSV (daily mapping of WGEN -> historical date).
3) For each WGEN month:
   - Weighted-average closure terms using sampled-day shares across (hist_year, hist_month).
   - Build a "block-stitched" closure term series by, for each WGEN 4-year block,
     detecting the dominant historic 4-year window and stitching those monthly closure values from history.
4) Computes R-squared between the two series (overall and per 4-year block) for each closure term.

Key outputs (in --outdir)
-------------------------
- closure_weighted_timeseries.csv
- closure_blockstitched_timeseries.csv
- closure_correlation_overall.csv
- closure_correlation_by_block.csv
- wgen_block_hist_window.csv
- closure_terms_historical_timeseries.csv
- closure_term_correlation_boxplot.png
- coverage_share_boxplot.png
- corr_vs_coverage_scatter.png
- r_squared_vs_coverage_points.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import (
    read_calsim_monthly_pairs,
    norm_token,
    DEFAULT_DSS_READ_START,
    DEFAULT_DSS_READ_END,
)

# plotting (headless-safe)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------
# Default paths (via utils.paths)
# ---------------------------------------------------------------------
_base = get_base_dir()
_gen  = get_module_generated_dir("mod_other/closure_terms")

DEFAULT_DSS        = _base / "CalSim3" / "__calsim_sv_default__.dss"
DEFAULT_RESAMPLED  = _base / "WGEN" / "resampled.dates_Product_B_1000yr.csv"
DEFAULT_OUTDIR     = _gen / "output" /"_1_ct_calculation" /"wgen_analysis_outputs"

# -----------------------------
# Shared selection used by both box plot and filtered scatters
# -----------------------------
PART_B = [
    "CT_BENDBRIDGE_SV", "CT_BUTTECITY_SV", "CT_FAIROAKS_SV", "CT_FREEPORT_SV",
    "CT_NICOLAUS_SV", "CT_OROVILLE_SV", "CT_SMARTVILLE_SV", "CT_VERONA_SV",
    "CT_WHEATLAND_SV", "CT_WILKINSSL_SV", "CT_PEDRO_SV", "CT_PARDE_SV", "CT_MELON_SV"
]

# -----------------------------
# DSS reader: read closure terms via read_calsim_monthly_pairs
# -----------------------------
CLOSURE_C_PART = "CLOSURE-TERM"


def read_all_closure_terms_monthly(
    dssfile: str | Path,
    term_filter: list[str] | None = None,
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> pd.DataFrame:
    """Read selected CLOSURE-TERM series from DSS using (B-part, C-part) pairs."""
    dssfile = Path(dssfile)
    if not dssfile.is_file():
        raise FileNotFoundError(f"DSS file not found: {dssfile}")

    if term_filter is None:
        raise ValueError("term_filter (list of Part B names) is required.")

    specs = [(b, CLOSURE_C_PART) for b in term_filter]
    series_by_key = read_calsim_monthly_pairs(
        dssfile=dssfile,
        specs=specs,
        dss_read_start=dss_read_start,
        dss_read_end=dss_read_end,
    )

    full_idx = pd.date_range(dss_read_start, dss_read_end, freq="ME")
    df = pd.DataFrame(index=full_idx)
    df.index.name = "date"

    missing: list[str] = []
    for b in term_filter:
        key = (norm_token(b), norm_token(CLOSURE_C_PART))
        if key not in series_by_key:
            missing.append(b)
            continue
        df[b] = pd.to_numeric(
            series_by_key[key].reindex(full_idx), errors="coerce"
        ).to_numpy()

    if missing:
        print(f"[warn] Not found in DSS: {', '.join(missing)}")

    return df


# -----------------------------
# WGEN helpers
# -----------------------------
def _add_months(year: int, month: int, delta_months: int) -> tuple[int, int]:
    """Add months to (year, month), return (Y, M) with 1..12."""
    total = year * 12 + (month - 1) + int(delta_months)
    return total // 12, (total % 12) + 1


def parse_wgen_date_to_ym(s: str) -> str | None:
    """
    Parse 'M/D/YYYY' (or 'M-D-YYYY') into 'YYYY-MM' without using pandas datetime,
    so we avoid datetime64 overflow for years > 2262.
    """
    s = str(s).strip()
    if not s:
        return None
    for sep in ("/", "-"):
        if sep in s:
            parts = s.split(sep)
            if len(parts) == 3:
                m, d, y = parts
                try:
                    return f"{int(y):04d}-{int(m):02d}"
                except Exception:
                    return None
    return None


def wgen_calendar(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Build a calendar map per (stamp_year, stamp_month) using the MODE of `wgen_date` calendar month
    (parsed to 'YYYY-MM' as text). This avoids datetime overflows and ensures a single label
    even if a group contains an adjacent-month spill day.
    """
    # Ensure a robust monthly key from wgen_date
    if "wgen_ym" not in df_daily.columns:
        df_daily = df_daily.copy()
        df_daily["wgen_ym"] = df_daily["wgen_date"].map(parse_wgen_date_to_ym)

    # Mode YYYY-MM per (stamp_year, stamp_month)
    mode_map = (
        df_daily.groupby(["stamp_year","stamp_month"])["wgen_ym"]
                .agg(lambda s: s.value_counts().idxmax() if s.notna().any() else None)
                .reset_index(name="Wgen_year_month")
    )

    # Split back to ints
    mode_map["wgen_cal_year"]  = mode_map["Wgen_year_month"].str.split("-", expand=True)[0].astype("Int64")
    mode_map["wgen_cal_month"] = mode_map["Wgen_year_month"].str.split("-", expand=True)[1].astype("Int64")
    return mode_map[["stamp_year","stamp_month","wgen_cal_year","wgen_cal_month","Wgen_year_month"]]


def detect_dominant_4yr_windows(df_daily: pd.DataFrame) -> pd.DataFrame:
    """
    For each 4-year WGEN block:
      1) Compute the majority (unique mode) historical year for the first three WGEN years in the block.
      2) Select the 4-year historical window [Y, Y+3] that maximizes coverage (total days from those years).
      3) If the selected window's first year != majority of the first WGEN year:
           If (Y+1 == maj_first) and (Y+2 == maj_second) and (Y+3 == maj_third) and the shifted window exists,
           then shift the window to start at Y+1, recalc coverage, window_alignment='shifted',
           and write the shifted window to the output so stitching can proceed.
      4) If the selected window's first year == maj_first, accept (window_alignment='direct').

    Output columns (one row per block_id):
      - block_id
      - hist_start_year, hist_end_year
      - coverage_share
      - dom_first_hist_year, dom_second_hist_year, dom_third_hist_year  (diagnostics)
      - window_alignment: 'direct' | 'shifted' | 'unresolved'
    """
    df = df_daily.copy()
    if "block_id" not in df.columns:
        df["block_id"] = (df["stamp_year"] - 1)//4 + 1

    def _majority_hist_year(sub: pd.DataFrame, sy: int) -> int | None:
        """Unique mode hist_year for a given stamp_year; None if tie or empty."""
        vc = sub.loc[sub["stamp_year"] == sy, "hist_year"].value_counts()
        if len(vc):
            top2 = vc.nlargest(2).values
            return int(vc.idxmax()) if (len(top2) == 1 or top2[0] > top2[1]) else None
        return None

    rows = []
    for b, g in df.groupby("block_id"):
        # Identify first three WGEN years of the block
        first_sy = int(g["stamp_year"].min())
        second_sy = first_sy + 1
        third_sy  = first_sy + 2

        maj1 = _majority_hist_year(g, first_sy)
        maj2 = _majority_hist_year(g, second_sy)
        maj3 = _majority_hist_year(g, third_sy)

        # 4-year window sums over hist_year counts
        counts = g["hist_year"].value_counts().sort_index()
        yrs = counts.index.to_numpy()
        win: dict[int, int] = {}
        if yrs.size >= 4:
            y_min, y_max = int(yrs.min()), int(yrs.max())
            for y in range(y_min, y_max - 3 + 2):
                total = int(counts.loc[(counts.index >= y) & (counts.index <= y + 3)].sum())
                win[y] = total

        # No usable window → flag
        if not win:
            rows.append({
                "block_id": int(b),
                "hist_start_year": np.nan,
                "hist_end_year": np.nan,
                "coverage_share": np.nan,
                "dom_first_hist_year": (np.nan if maj1 is None else int(maj1)),
                "dom_second_hist_year": (np.nan if maj2 is None else int(maj2)),
                "dom_third_hist_year": (np.nan if maj3 is None else int(maj3)),
                "window_alignment": "unresolved",
            })
            continue

        # Select the best-coverage window 
        best = max(win.values())
        cand = [y for y, s in win.items() if s == best]
        start0 = min(cand)
        cov_best = (best / len(g)) if len(g) else np.nan

        accepted_start = None
        coverage_share = cov_best
        alignment = "unresolved"

        # Accept if aligned with majority of the FIRST WGEN year
        if maj1 is not None and start0 == maj1:
            accepted_start = start0
            coverage_share = (win[start0] / len(g)) if len(g) else np.nan
            alignment = "direct"
        else:
            # If misaligned, apply your 1-year shift rule:
            # second window year == maj1, third == maj2, fourth == maj3
            if (maj1 is not None and maj2 is not None and maj3 is not None and
                (start0 + 1) == maj1 and (start0 + 2) == maj2 and (start0 + 3) == maj3 and
                (start0 + 1) in win):
                accepted_start = start0 + 1
                coverage_share = (win[accepted_start] / len(g)) if len(g) else np.nan
                alignment = "shifted"

        if accepted_start is not None:
            rows.append({
                "block_id": int(b),
                "hist_start_year": int(accepted_start),
                "hist_end_year": int(accepted_start + 3),
                "coverage_share": coverage_share,
                "dom_first_hist_year": (np.nan if maj1 is None else int(maj1)),
                "dom_second_hist_year": (np.nan if maj2 is None else int(maj2)),
                "dom_third_hist_year": (np.nan if maj3 is None else int(maj3)),
                "window_alignment": alignment,
            })
        else:
            # Keep best coverage for visibility; no window assigned
            rows.append({
                "block_id": int(b),
                "hist_start_year": np.nan,
                "hist_end_year": np.nan,
                "coverage_share": cov_best,
                "dom_first_hist_year": (np.nan if maj1 is None else int(maj1)),
                "dom_second_hist_year": (np.nan if maj2 is None else int(maj2)),
                "dom_third_hist_year": (np.nan if maj3 is None else int(maj3)),
                "window_alignment": "unresolved",
            })

    return pd.DataFrame(rows)

# -----------------------------
# Closure transforms
# -----------------------------
def make_month_table(df_wide: pd.DataFrame) -> pd.DataFrame:
    """Return monthly closure table keyed by (hist_year, hist_month)."""
    out = df_wide.copy()
    out["hist_year"]  = out.index.year
    out["hist_month"] = out.index.month
    return out.set_index(["hist_year","hist_month"]).sort_index()


# -----------------------------
# Weighted and block-stitched engines
# -----------------------------
def compute_weighted_closure(counts: pd.DataFrame,
                             cal_map: pd.DataFrame,
                             ct_month_table: pd.DataFrame,
                             term_cols: list[str]) -> pd.DataFrame:
    """
    For each WGEN month, weighted-average closure terms across all contributing
    (hist_year, hist_month) using 'share' as weights.
    """
    joined = counts.merge(ct_month_table.reset_index(), on=["hist_year","hist_month"], how="left")
    for c in term_cols:
        joined[c] = joined[c] * joined["share"]
    wgt = joined.groupby(["stamp_year","stamp_month"], as_index=False)[term_cols].sum()
    wgt = wgt.merge(cal_map[["stamp_year","stamp_month","Wgen_year_month"]], on=["stamp_year","stamp_month"], how="left")
    return wgt.sort_values(["stamp_year","stamp_month"]).reset_index(drop=True)


def build_blockstitched_closure(months_layout: pd.DataFrame,
                                block_map: pd.DataFrame,
                                ct_month_table: pd.DataFrame,
                                term_cols: list[str],
                                align: str = "calendar") -> pd.DataFrame:
    """
    For each WGEN 4-yr block, stitch closure terms from the chosen historic 4-yr window.
    align='calendar' -> start at Jan; align='water' -> start at Oct.

    Adds:
      - block_id
      - historical_4yrs_block ('YYYY-YYYY'; empty if no mapping)
    """
    align_month0 = 1 if align == "calendar" else 10  # 1=Jan, 10=Oct
    stitched_rows = []

    for b, grp in months_layout.groupby("block_id"):
        grp = grp.sort_values(["stamp_year","stamp_month"])
        m = block_map.loc[block_map["block_id"] == b]

        # If no mapping for this block: emit rows with NaN term values
        if m.empty or pd.isna(m.iloc[0]["hist_start_year"]):
            for _, r in grp.iterrows():
                row = {
                    "block_id": int(b),
                    "stamp_year": int(r["stamp_year"]),
                    "stamp_month": int(r["stamp_month"]),
                    "Wgen_year_month": r["Wgen_year_month"],
                    "historical_4yrs_block": ""
                }
                for c in term_cols:
                    row[c] = np.nan
                stitched_rows.append(row)
            continue

        # Valid historic window
        start_y = int(m.iloc[0]["hist_start_year"])
        end_y   = start_y + 3
        hist_label = f"{start_y}-{end_y}"

        for idx, (_, r) in enumerate(grp.iterrows()):
            yy, mm = _add_months(start_y, align_month0, idx)  # 48 months across the block
            row = {
                "block_id": int(b),
                "stamp_year": int(r["stamp_year"]),
                "stamp_month": int(r["stamp_month"]),
                "Wgen_year_month": r["Wgen_year_month"],
                "historical_4yrs_block": hist_label
            }
            if (yy, mm) in ct_month_table.index:
                vals = ct_month_table.loc[(yy, mm), term_cols].to_dict()
                row.update(vals)
            else:
                for c in term_cols:
                    row[c] = np.nan
            stitched_rows.append(row)

    stitched = pd.DataFrame(stitched_rows).sort_values(["stamp_year","stamp_month"]).reset_index(drop=True)
    return stitched


# -----------------------------
# Correlations 
# -----------------------------
def overall_and_perblock_correlations(stitched: pd.DataFrame,
                                      weighted: pd.DataFrame,
                                      term_cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = stitched.merge(
        weighted,
        on=["stamp_year","stamp_month","Wgen_year_month"],
        suffixes=("_block","_weighted")
    )
    merged["block_id"] = (merged["stamp_year"] - 1)//4 + 1

    have_block    = {col[:-6] for col in merged.columns if col.endswith("_block")}
    have_weighted = {col[:-9] for col in merged.columns if col.endswith("_weighted")}
    usable_terms  = sorted(set(term_cols) & have_block & have_weighted)

    overall_rows = []
    for c in usable_terms:
        a = merged[f"{c}_block"]
        b = merged[f"{c}_weighted"]
        valid = a.notna() & b.notna()
        r = np.corrcoef(a[valid], b[valid])[0, 1] if valid.sum() >= 3 else np.nan
        overall_rows.append({"closure_term": c, "overall_r_squared": r ** 2, "n_points": int(valid.sum())})
    overall_df = pd.DataFrame(overall_rows)

    per_block_rows = []
    for b_id, sub in merged.groupby("block_id"):
        for c in usable_terms:
            a = sub[f"{c}_block"]; d = sub[f"{c}_weighted"]
            valid = a.notna() & d.notna()
            r = np.corrcoef(a[valid], d[valid])[0, 1] if valid.sum() >= 3 else np.nan
            per_block_rows.append({"block_id": int(b_id), "closure_term": c, "r_squared": r ** 2, "n_points": int(valid.sum())})
    perblock_df = pd.DataFrame(per_block_rows)

    return overall_df, perblock_df


# -----------------------------
# Build "all sources" text column (ALL contributors)
# -----------------------------
def build_all_sources_column(counts: pd.DataFrame) -> pd.DataFrame:
    """
    From counts at (stamp_year, stamp_month, hist_year, hist_month) with n_days & share,
    build a text column that lists ALL contributing (hist_year, hist_month) with days and weights.
    """
    def _fmt_group(g: pd.DataFrame) -> pd.Series:
        g = g.sort_values("n_days_from_hist_pair", ascending=False)
        total = int(g["n_days_from_hist_pair"].sum())
        parts = []
        for _, r in g.iterrows():
            share = (r["n_days_from_hist_pair"] / total) if total else float("nan")
            parts.append(f"{int(r['hist_year'])}-{int(r['hist_month']):02d}: {int(r['n_days_from_hist_pair'])}d ({share:.1%})")
        return pd.Series({"hist_sources_all": "; ".join(parts)})
    return (counts.groupby(["stamp_year","stamp_month"], as_index=False)
                 .apply(_fmt_group)
                 .reset_index(drop=True))


# -----------------------------
# box plots of per-block R-squared (one box per closure term)
# -----------------------------
def _short_label(term: str) -> str:
    """CT_BENDBRIDGE_SV -> Bend Bridge, CT_FAIROAKS_SV -> Fair Oaks, etc."""
    name = term
    if name.startswith("CT_"):
        name = name[3:]
    if name.endswith("_SV"):
        name = name[:-3]
    # Insert space before each uppercase letter that follows a lowercase letter
    cleaned = name.replace("_", " ").title()
    return cleaned


def plot_corr_boxplots_13_terms(perblock_df: pd.DataFrame, out_path: Path) -> None:
    terms_to_plot = PART_B

    data, labels, missing = [], [], []
    for t in terms_to_plot:
        vals = perblock_df.loc[perblock_df["closure_term"] == t, "r_squared"].dropna().to_numpy()
        if vals.size == 0:
            missing.append(t); data.append(np.array([])); labels.append(_short_label(t) + " *")
        else:
            data.append(vals); labels.append(_short_label(t))

    fig, ax = plt.subplots(figsize=(8, 6))
    bp = ax.boxplot(
        data, vert=False, patch_artist=True, showmeans=True,
        boxprops=dict(facecolor="#A8C4E0", edgecolor="black", linewidth=0.8),
        medianprops=dict(color="#E67E22", linewidth=1.5),
        meanprops=dict(marker="D", markerfacecolor="#2980B9", markeredgecolor="#2980B9", markersize=4),
        whiskerprops=dict(color="black", linewidth=0.8),
        capprops=dict(color="black", linewidth=0.8),
        flierprops=dict(marker="o", markerfacecolor="none", markeredgecolor="black", markersize=4, linestyle="none"),
    )

    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0.0, 1.05)
    ax.set_xlabel("$R^2$", fontsize=10)
    ax.set_title("Per-Block $R^2$: Weighted vs. Block-Stitched Closure Terms", fontsize=11, pad=10)
    ax.axvline(1.0, color="#888", linewidth=0.5, linestyle=":")
    ax.axvline(0.0, color="black", linewidth=0.6)
    ax.grid(True, axis="x", linestyle="--", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    if missing:
        print("[warn] No per-block R-squared data for:", ", ".join(missing))


# -----------------------------
# HORIZONTAL box plot of coverage_share across blocks
# -----------------------------
def plot_coverage_share_boxplot(block_map: pd.DataFrame, out_path: Path) -> None:
    """
    One horizontal box plot of coverage_share across all blocks,
    with jittered points showing each block's value.
    """
    vals = block_map["coverage_share"].dropna().to_numpy()
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    ax.boxplot([vals], vert=False, showmeans=True, whis=[5, 95],
               medianprops=dict(color='blue', linewidth=1.5))
    # jittered points along the single y-category
    yj = np.random.normal(loc=1.0, scale=0.03, size=len(vals))
    ax.scatter(vals, yj, s=18, alpha=0.7, color="orange")
    ax.set_yticks([1])
    ax.set_yticklabels(["All blocks"])
    ax.set_xlim(0.5, 1.0)
    ax.set_xlabel("Coverage ratio of dominant 4-year window")
    ax.set_title("Coverage ratio across blocks")
    ax.grid(True, axis="x", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_corr_vs_coverage_scatter(perblock_df: pd.DataFrame,
                                  block_map: pd.DataFrame,
                                  out_path: Path,
                                  save_csv_path: Path | None = None,
                                  terms_filter: list[str] | None = None,
                                  title: str | None = None) -> None:
    """
    Scatter: per-block R-squared (weighted vs block-stitched) vs coverage_share.

    If `terms_filter` is provided, only those closure terms are plotted.
    A least-squares trend is added when >= 2 finite points are available.

    Saves a PNG (out_path), and optionally a CSV of the plotted points (save_csv_path).

    Columns used:
      - perblock_df: [block_id, closure_term, r_squared, n_points]
      - block_map:   [block_id, coverage_share]
    """
    # Merge correlation-per-block with the coverage share for that block
    merged = perblock_df.merge(
        block_map[["block_id", "coverage_share"]],
        on="block_id", how="left"
    )

    if terms_filter is not None:
        merged = merged[merged["closure_term"].isin(terms_filter)]

    # Keep rows that have both r_squared and coverage_share
    pts = merged.dropna(subset=["r_squared", "coverage_share"]).copy()

    # Optional: export the plotted points
    if save_csv_path is not None:
        cols = ["block_id", "closure_term", "coverage_share", "r_squared", "n_points"]
        pts[cols].to_csv(save_csv_path, index=False)

    # Build scatter
    fig, ax = plt.subplots(figsize=(7.0, 5.2))
    if not pts.empty:
        ax.scatter(pts["coverage_share"], pts["r_squared"], s=12, alpha=0.35, edgecolors="none")

        # Simple least-squares trend line
        x = pts["coverage_share"].to_numpy()
        y = pts["r_squared"].to_numpy()
        good = np.isfinite(x) & np.isfinite(y)
        if good.sum() >= 2:
            slope, intercept = np.polyfit(x[good], y[good], 1)
            xx = np.linspace(x[good].min(), x[good].max(), 100)
            yy = slope * xx + intercept
            ax.plot(xx, yy, linewidth=1.6)

    # Axes, bounds, grid
    ax.set_xlim(0.5, 1.0)      # typical coverage range here
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("Coverage share (dominant 4-year window)")
    ax.set_ylabel("$R^2$: weighted vs block-stitched")

    if title:
        ax.set_title(title)
    else:
        if terms_filter is None:
            ax.set_title("Per-block $R^2$ vs coverage share (all closure terms)")
        elif len(terms_filter) == 1:
            ax.set_title(f"Per-block $R^2$ vs coverage share ({terms_filter[0]})")
        else:
            ax.set_title("Per-block $R^2$ vs coverage share (selected terms)")

    ax.axhline(0.0, linewidth=0.8, color="black")
    ax.grid(True, linestyle="--", alpha=0.35)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_cdf_num_distinct_pairs_excl_ones(counts_by_label: pd.DataFrame,
                                          out_path: Path,
                                          min_pairs: int = 2,
                                          title: str | None = None) -> pd.DataFrame:
    """
    CDF of the NUMBER of distinct (hist_year, hist_month) contributors per WGEN month,
    excluding 1-to-1 months (i.e., keep months with >= min_pairs distinct contributors).

    Parameters
    ----------
    counts_by_label : DataFrame
        Must include columns: ['wgen_ym','hist_year','hist_month'].
        (This is the table you already build via groupby over 'wgen_ym' × (hist_year, hist_month).)
    out_path : Path
        Where to save the PNG figure.
    min_pairs : int, default 2
        Minimum number of distinct (year, month) contributors to keep (2 per meeting notes).
    title : str | None
        Optional plot title override.

    Returns
    -------
    pd.DataFrame
        Table with columns ['n_pairs','count','cdf'] used to draw the CDF.
        (Returned for QA or if you want to export later.)
    """
    from matplotlib.ticker import PercentFormatter

    # --- Count distinct (hist_year, hist_month) per WGEN calendar month label ---
    pairs = counts_by_label[["wgen_ym", "hist_year", "hist_month"]].drop_duplicates()
    distinct_counts = (pairs.groupby("wgen_ym")
                             .size()
                             .rename("n_distinct_pairs")
                             .reset_index())

    # --- Keep only "mixed months" (>= min_pairs) ---
    mixed = distinct_counts.loc[distinct_counts["n_distinct_pairs"] >= int(min_pairs), "n_distinct_pairs"]

    # --- Build discrete CDF over integer n_pairs values ---
    freq = (mixed.value_counts()
                  .sort_index()
                  .rename_axis("n_pairs")
                  .reset_index(name="count"))
    freq["cdf"] = freq["count"].cumsum() / freq["count"].sum()

    # --- Plot (step CDF with integer x) ---
    fig, ax = plt.subplots(figsize=(6.8, 4.2))
    ax.step(freq["n_pairs"], freq["cdf"], where="post", linewidth=1.8)

    ax.set_xlim(freq["n_pairs"].min(), freq["n_pairs"].max())
    ax.set_ylim(0.0, 1.0)
    ax.set_xlabel("Number of distinct (hist year, month) contributing to a WGEN month")
    ax.set_ylabel("CDF")
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    if title is None:
        title = "CDF of mixed months only (≥2 distinct pairs)"
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.35)

    # Make x-ticks integers (avoid clutter if the max is large)
    max_x = int(freq["n_pairs"].max())
    min_x = int(freq["n_pairs"].min())
    if max_x - min_x <= 20:
        ax.set_xticks(range(min_x, max_x + 1))

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

    return freq[["n_pairs", "count", "cdf"]]

# -----------------------------
# Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser(description="Closure terms (DSS): weighted vs 4-yr-block stitched, with correlations + plots")
    ap.add_argument("--resampled", default=DEFAULT_RESAMPLED, type=Path,
                    help="WGEN resampled dates CSV (daily)")
    ap.add_argument("--dss", default=DEFAULT_DSS, type=Path,
                    help="CalSim DSS file with monthly closure terms")
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, type=Path,
                    help="Output folder")
    ap.add_argument("--block-align", choices=["calendar","water"], default="calendar",
                    help="Month alignment for stitching (Jan vs Oct)")
    args = ap.parse_args()

    outdir = args.outdir; outdir.mkdir(parents=True, exist_ok=True)

    # --- Read selected closure terms from DSS (monthly, wide)
    df_ct = read_all_closure_terms_monthly(args.dss, term_filter=PART_B)
    if df_ct.empty or df_ct.dropna(how="all", axis=1).empty:
        raise RuntimeError("No closure term series found in DSS with Part C = 'CLOSURE-TERM'.")
    df_ct.index = pd.to_datetime(df_ct.index)
    term_cols = list(df_ct.columns)

    # Save closure terms with their real historical dates to CSV
    ct_with_dates = df_ct.copy()
    ct_with_dates.index.name = 'date'
    ct_with_dates.to_csv(outdir / "closure_terms_historical_timeseries.csv", index=True)

    # Make (hist_year, hist_month)-indexed table for lookups
    ct_month_table = make_month_table(df_ct)

    # --- Read WGEN resampled dates (daily)
    dfd = pd.read_csv(args.resampled)

    # Historical (source) year-month from resampled date
    dfd["hist_date"]  = pd.to_datetime(dfd["resmplDatesLoc"], errors="coerce")
    dfd["hist_year"]  = dfd["hist_date"].dt.year
    dfd["hist_month"] = dfd["hist_date"].dt.month

    # WGEN identifiers
    dfd["stamp_year"]  = dfd["stamp_year"].astype(int)
    dfd["stamp_month"] = dfd["stamp_month"].astype(int)

    # Robust calendar month from wgen_date as TEXT -> 'YYYY-MM'
    dfd["wgen_ym"] = dfd["wgen_date"].map(parse_wgen_date_to_ym)

    # Build WGEN calendar map (mode of wgen_ym per (stamp_year, stamp_month))
    cal_map = wgen_calendar(dfd)

    # -----------------------------------------------------------------
    # Counts & shares by calendar month of wgen_date (not stamp)
    # -----------------------------------------------------------------
    dfd_valid = dfd.dropna(subset=["hist_year","hist_month","wgen_ym"]).copy()

    # Count days per (calendar WGEN month from wgen_date) × (hist_year, hist_month)
    counts_by_label = (
        dfd_valid.groupby(["wgen_ym","hist_year","hist_month"], dropna=False)
                 .size().reset_index(name="n_days_from_hist_pair")
    )
    totals_by_label = (
        counts_by_label.groupby(["wgen_ym"], as_index=False)["n_days_from_hist_pair"]
                       .sum().rename(columns={"n_days_from_hist_pair": "n_days_in_wgen_month"})
    )
    counts_by_label = counts_by_label.merge(totals_by_label, on="wgen_ym", how="left")
    counts_by_label["share"] = counts_by_label["n_days_from_hist_pair"] / counts_by_label["n_days_in_wgen_month"]

    # Map those calendar-month counts back to each (stamp_year, stamp_month) via the WGEN calendar label
    counts = counts_by_label.merge(
        cal_map[["stamp_year","stamp_month","Wgen_year_month"]],
        left_on="wgen_ym", right_on="Wgen_year_month", how="left"
    )

    # Build "all sources" text
    all_sources = build_all_sources_column(counts)

    # --- Weighted-average closure (uses shares computed by calendar month of wgen_date)
    weighted = compute_weighted_closure(counts, cal_map, ct_month_table, term_cols)
    weighted = weighted.merge(all_sources, on=["stamp_year","stamp_month"], how="left")
    # Add block_id as first column in the weighted CSV
    weighted["block_id"] = (weighted["stamp_year"] - 1)//4 + 1
    ordered_cols = ["block_id", "stamp_year", "stamp_month", "Wgen_year_month", "hist_sources_all"] + term_cols
    weighted[ordered_cols].to_csv(outdir / "closure_weighted_timeseries.csv", index=False)

    # --- Dominant 4-yr windows per WGEN block
    dfd_for_blocks = dfd.copy()
    dfd_for_blocks["hist_year"] = dfd_for_blocks["hist_year"]  # already set
    block_map = detect_dominant_4yr_windows(dfd_for_blocks)
    block_map.to_csv(outdir / "wgen_block_hist_window.csv", index=False)

    # NEW: Horizontal box plot of coverage_share across blocks
    plot_coverage_share_boxplot(block_map, outdir / "coverage_share_boxplot.png")

    # Build WGEN month layout with block ids for stitching
    months_layout = cal_map.copy()
    months_layout["block_id"] = (months_layout["stamp_year"] - 1)//4 + 1
    months_layout = months_layout.sort_values(["stamp_year","stamp_month"])

    # --- Block-stitched closure
    stitched = build_blockstitched_closure(
        months_layout, block_map, ct_month_table, term_cols, align=args.block_align
    )
    cols_order = ["block_id", "stamp_year", "stamp_month", "Wgen_year_month", "historical_4yrs_block"] + term_cols
    stitched[cols_order].to_csv(outdir / "closure_blockstitched_timeseries.csv", index=False)

    # --- Correlations
    overall_df, perblock_df = overall_and_perblock_correlations(stitched, weighted, term_cols)
    overall_df.to_csv(outdir / "closure_correlation_overall.csv", index=False)
    perblock_wide = perblock_df.pivot(index="block_id", columns="closure_term", values="r_squared")
    perblock_wide.columns.name = None
    perblock_wide.to_csv(outdir / "closure_correlation_by_block.csv")

    # --- Single figure with box plots (one per requested closure term)
    out_fig = outdir / "closure_term_correlation_boxplot.png"
    plot_corr_boxplots_13_terms(perblock_df, out_fig)

    # --- Scatter plot: R-squared vs coverage share
    scatter_fig = outdir / "r_squared_vs_coverage_scatter.png"
    plot_corr_vs_coverage_scatter(
        perblock_df, block_map, scatter_fig,
        save_csv_path=outdir / "r_squared_vs_coverage_points.csv",
        terms_filter=None,
        title="Per-block $R^2$ vs coverage share (all closure terms)"
    )

    print("Wrote:", (outdir / "coverage_share_boxplot.png").resolve())
    print("Wrote:", out_fig.resolve())
    print("Wrote:", scatter_fig.resolve())
    print("Done. Outputs written to:", outdir.resolve())

    plot_cdf_num_distinct_pairs_excl_ones(
        counts_by_label,
        outdir / "wgen_num_distinct_pairs_cdf.png"
    )


if __name__ == "__main__":
    main()
