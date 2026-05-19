"""
Product A Validation Post-Processing
====================================
Product A validation post-processing using the shared CalView-style pickle
cache (values.pkl / diffs.pkl / units.pkl / fields.pkl).

Outputs:
1) Annual Water Year summary tables for:
   - Full validation period: WY 1972-2021
   - Drought period: WY 1987-1992
   For each metric: baseline + scenario(s), absolute diff, percent diff.

2) For each metric and each period, a two-panel figure:
   - Left: monthly timeseries in TAF
   - Right: monthly non-exceedance CDF
   - R2, NSE, and PBIAS on the timeseries panel versus the baseline.

Expected repository location:
    calsim3-stochastic-input-generation/postprocessing/calsim_runs/_productA_postproc.py

Default inputs:
    data/GENERATED/postprocessing/calsim_runs/product_a/pickle_files

Default outputs:
    data/GENERATED/postprocessing/calsim_runs/product_a/output

Typical usage:
    python _productA_postproc.py --baseline-name Historical

    python _productA_postproc.py ^
        --pickle-dir "../../data/GENERATED/postprocessing/calsim_runs/product_a/pickle_files" ^
        --out-dir "../../data/GENERATED/postprocessing/calsim_runs/product_a/output"
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle
import re
import sys as _sys
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns


# -- Report-quality Seaborn / Matplotlib theme --
sns.set_theme(
    style="whitegrid",
    context="paper",
    font_scale=1.0,
    rc={
        "figure.dpi": 200,
        "savefig.dpi": 300,
        # Professional font stack (tries each in order)
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
_cb = list(sns.color_palette("colorblind"))
_cb[1] = (0.918, 0.341, 0.220)   # Vermillion+1 ~#EB5738
_PALETTE = _cb


# =============================
# Repository-aware default paths
# =============================
RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]

_sys.path.insert(0, str(REPO_ROOT))
try:
    from utils.paths import get_generated_dir
except Exception:
    # Fallback is only for local testing outside the full repository.
    # In the repository, utils.paths should be used.
    def get_generated_dir() -> Path:
        return REPO_ROOT / "data" / "GENERATED"

PICKLE_DIR = (
    get_generated_dir()
    / "postprocessing"
    / "calsim_runs"
    / "product_a"
    / "pickle_files"
)

BASELINE_NAME = "Historical"

OUT_DIR = (
    get_generated_dir()
    / "postprocessing"
    / "calsim_runs"
    / "product_a"
    / "output"
)


# -----------------------------
# Period definitions
# -----------------------------

@dataclass(frozen=True)
class Period:
    name: str
    start: pd.Timestamp  # inclusive
    end: pd.Timestamp    # inclusive
    wy_start: int        # water-year start (inclusive)
    wy_end: int          # water-year end (inclusive)


FULL_VALIDATION = Period(
    name="Full_Validation_WY1972_2021",
    start=pd.Timestamp("1971-10-01"),
    end=pd.Timestamp("2021-09-30"),
    wy_start=1972,
    wy_end=2021,
)

DROUGHT_878892 = Period(
    name="Drought_WY1987_1992",
    start=pd.Timestamp("1986-10-01"),  # WY1987 begins Oct 1986
    end=pd.Timestamp("1992-09-30"),
    wy_start=1987,
    wy_end=1992,
)


# -----------------------------
# Loading
# -----------------------------

def load_pickles(pickle_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, str], Dict[str, str]]:
    p = Path(pickle_dir)
    with open(p / "values.pkl", "rb") as f:
        df_values = pickle.load(f)
    with open(p / "diffs.pkl", "rb") as f:
        df_diffs = pickle.load(f)
    with open(p / "units.pkl", "rb") as f:
        units = pickle.load(f)
    with open(p / "fields.pkl", "rb") as f:
        fields = pickle.load(f)
    return df_values, df_diffs, units, fields


def metric_groups_from_fields(fields: Dict[str, str]) -> Dict[str, str]:
    """
    The builder writes fields like:
        "Delta: SAC (Freeport) (C_SAC048)"
        "Storage: Shasta (S_SHSTA)"
    We parse the text before ":" as the group.

    If no ":" is present, group becomes "".
    """
    out = {}
    for k, label in fields.items():
        if isinstance(label, str) and ":" in label:
            out[k] = label.split(":", 1)[0].strip()
        else:
            out[k] = ""
    return out


# -----------------------------
# Metrics (R2, NSE, PBIAS)
# -----------------------------

def r2_score(obs: np.ndarray, sim: np.ndarray) -> float:
    if len(obs) < 2:
        return np.nan
    r = np.corrcoef(obs, sim)[0, 1]
    return float(r * r)


def nse_score(obs: np.ndarray, sim: np.ndarray) -> float:
    if len(obs) < 2:
        return np.nan
    denom = np.sum((obs - np.mean(obs)) ** 2)
    if denom == 0:
        return np.nan
    return float(1.0 - (np.sum((sim - obs) ** 2) / denom))


def pbias(obs: np.ndarray, sim: np.ndarray) -> float:
    """
    Percent bias (positive means model underestimation, negative
    overestimation), common hydrology definition:
      PBIAS = 100 * sum(obs - sim) / sum(obs)
    """
    if len(obs) == 0:
        return np.nan
    denom = np.sum(obs)
    if denom == 0:
        return np.nan
    return float(100.0 * np.sum(obs - sim) / denom)


def compute_metrics(obs_series: pd.Series, sim_series: pd.Series) -> Dict[str, float]:
    df = pd.concat([obs_series.rename("obs"), sim_series.rename("sim")], axis=1).dropna()
    obs = df["obs"].to_numpy(dtype=float)
    sim = df["sim"].to_numpy(dtype=float)
    return {
        "R2": r2_score(obs, sim),
        "NSE": nse_score(obs, sim),
        "PBIAS": pbias(obs, sim),
        "n": float(len(obs)),
    }


# -----------------------------
# Annual (WY) aggregation
# -----------------------------

def water_year_aggregate(
    df: pd.DataFrame,
    metric_key: str,
    group: str,
) -> pd.DataFrame:
    """
    Returns a DataFrame with columns:
      Scenario, OctSeptYear, WY_value

    Rule for mixed metric types:
      - Storage group: end-of-September value (end of water year)
      - else: WY sum of monthly values (monthly volumes -> annual volume)

    If you want different behavior, change this one function.
    """
    needed = {"Scenario", "OctSeptYear", metric_key, "Date"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"values.pkl missing columns: {sorted(missing)}")

    if group.strip().lower() == "storage":
        # End-of-September value: filter to September rows only
        tmp = df[["Scenario", "Date", "OctSeptYear", metric_key]].copy()
        tmp = tmp.dropna(subset=[metric_key])
        tmp = tmp[tmp["Date"].dt.month == 9]
        wy = tmp.groupby(["Scenario", "OctSeptYear"], as_index=False)[metric_key].last()
    else:
        tmp = df[["Scenario", "OctSeptYear", metric_key]].copy()
        tmp = tmp.dropna(subset=[metric_key])
        wy = tmp.groupby(["Scenario", "OctSeptYear"], as_index=False)[metric_key].sum()

    wy = wy.rename(columns={metric_key: "WY_value"})
    return wy


def annual_summary_table(
    df_values: pd.DataFrame,
    metric_groups: Dict[str, str],
    baseline_name: str,
    periods: Sequence[Period],
    metric_keys: Sequence[str],
) -> Dict[str, pd.DataFrame]:
    """
    Produces one summary table per period (wide format):
      Group | Metric | Baseline_AvgWY_TAF | <Scenario>_AvgWY_TAF | <Scenario>_Diff_TAF | <Scenario>_Diff_pct | ...

    Values are mean across years of water-year aggregated values.
    """
    if baseline_name not in df_values["Scenario"].unique():
        raise ValueError(f"Baseline '{baseline_name}' not found in values.pkl scenarios.")

    scenario_names = list(df_values["Scenario"].unique())
    tables: Dict[str, pd.DataFrame] = {}

    for per in periods:
        dfp = df_values[(df_values["Date"] >= per.start) & (df_values["Date"] <= per.end)].copy()
        rows = []

        for mk in metric_keys:
            group = metric_groups.get(mk, "")
            wy = water_year_aggregate(dfp, mk, group=group)
            wy = wy[(wy["OctSeptYear"] >= per.wy_start) & (wy["OctSeptYear"] <= per.wy_end)]

            wy_mean = wy.groupby("Scenario", as_index=False)["WY_value"].mean()
            wy_mean = wy_mean.set_index("Scenario")["WY_value"]

            base_val = float(wy_mean.get(baseline_name, np.nan))
            row = {
                "Group": group,
                "Metric": mk,
                "Baseline_AvgWY_TAF": base_val,
            }

            for scen in scenario_names:
                if scen == baseline_name:
                    continue
                scen_val = float(wy_mean.get(scen, np.nan))
                diff = scen_val - base_val
                pct = np.nan
                if np.isfinite(base_val) and base_val != 0.0:
                    pct = diff / base_val * 100.0

                row[f"{scen}_AvgWY_TAF"] = scen_val
                row[f"{scen}_Diff_TAF"] = diff
                row[f"{scen}_Diff_pct"] = pct

            rows.append(row)

        table = pd.DataFrame(rows)
        tables[per.name] = table.sort_values(["Group", "Metric"]).reset_index(drop=True)

    return tables


# -----------------------------
# Plotting (timeseries + CDF)
# -----------------------------

def empirical_cdf(x: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return np.array([]), np.array([])
    xs = np.sort(x)
    p = np.arange(1, xs.size + 1) / xs.size
    return xs, p


def plot_timeseries_and_cdf(
    df_values: pd.DataFrame,
    metric_key: str,
    metric_label: str,
    baseline_name: str,
    compare_scenarios: Sequence[str],
    period: Period,
    out_png: str,
    unit: str = "TAF",
):
    dfp = df_values[
        (df_values["Date"] >= period.start) & (df_values["Date"] <= period.end)
    ].copy()

    all_scenarios = [baseline_name] + list(compare_scenarios)
    colors = {s: _PALETTE[i % len(_PALETTE)] for i, s in enumerate(all_scenarios)}

    fig, (ax_ts, ax_cdf) = plt.subplots(
        nrows=1, ncols=2, figsize=(6.5, 3.25),
        gridspec_kw={"width_ratios": [1.6, 1]},
    )

    # -- Left panel: monthly time-series --
    for scen in all_scenarios:
        sub = dfp[dfp["Scenario"] == scen].sort_values("Date")
        ax_ts.plot(
            sub["Date"], sub[metric_key],
            label=scen, color=colors[scen],
            linewidth=0.8 if scen == baseline_name else 0.9,
            alpha=0.85,
        )

    ax_ts.set_title("Monthly Time Series")
    ax_ts.set_xlabel("Date")
    ax_ts.set_ylabel("TAF")
    span_years = period.wy_end - period.wy_start + 1
    tick_interval = 1 if span_years <= 10 else 5 if span_years <= 30 else 10
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(tick_interval))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate(rotation=35, ha="right")

    # Metrics annotation (vs baseline)
    base = dfp[dfp["Scenario"] == baseline_name].set_index("Date")[metric_key]
    metric_lines = []
    for scen in compare_scenarios:
        sim = dfp[dfp["Scenario"] == scen].set_index("Date")[metric_key]
        m = compute_metrics(base, sim)
        metric_lines.append(
            f"{scen}:  R\u00b2={m['R2']:.3f}   NSE={m['NSE']:.3f}   PBIAS={m['PBIAS']:.1f}%"
        )
    if metric_lines:
        ax_ts.text(
            0.02, 0.97, "\n".join(metric_lines),
            transform=ax_ts.transAxes,
            va="top", ha="left", fontsize=7,
            fontfamily="sans-serif",
            bbox=dict(
                boxstyle="round,pad=0.35",
                facecolor="white", edgecolor="0.7",
                alpha=0.88,
            ),
        )

    # -- Right panel: monthly non-exceedance CDF --
    for scen in all_scenarios:
        vals = dfp[dfp["Scenario"] == scen][metric_key].to_numpy(dtype=float)
        xs, p = empirical_cdf(vals)
        ax_cdf.plot(
            p * 100.0, xs,
            label=scen, color=colors[scen],
            linewidth=0.9, alpha=0.9,
        )

    ax_cdf.set_title("Non-Exceedance CDF")
    ax_cdf.set_xlabel("Non-Exceedance Probability (%)")
    ax_cdf.set_ylabel("")
    ax_cdf.set_xlim(0, 100)

    # -- Suptitle & layout --
    fig.suptitle(f"{metric_label} ({unit})", y=1.02)
    if "Full_Validation" not in period.name:
        period_pretty = re.sub(r'(\d{4})_(\d{4})', r'\1-\2', period.name).replace("_", " ")
        fig.text(
            0.5, 0.97, f"({period_pretty})",
            ha="center", va="top",
            fontsize=8, fontstyle="italic", color="0.35",
            transform=fig.transFigure,
        )
    fig.tight_layout()

    # -- Shared figure legend - top left --
    handles, labels = ax_ts.get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
        ncol=len(all_scenarios),
        fontsize=7,
        frameon=False,
        handlelength=2.0,
        handletextpad=0.6,
        borderpad=0.7,
    )

    out_path = Path(out_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# -----------------------------
# Driver
# -----------------------------

def run_post_processing_package(
    pickle_dir: str,
    baseline_name: str,
    out_dir: str,
    periods: Optional[Sequence[Period]] = None,
):
    periods = list(periods) if periods is not None else [FULL_VALIDATION, DROUGHT_878892]

    df_values, df_diffs, units, fields = load_pickles(pickle_dir)
    df_values["Date"] = pd.to_datetime(df_values["Date"])

    metric_groups = metric_groups_from_fields(fields)

    fixed_cols = {"Date", "Scenario", "OctSeptYear", "MarFebYear", "Year", "Month", "JanDecYear"}
    metric_keys = [c for c in df_values.columns if c not in fixed_cols]

    scenarios = list(df_values["Scenario"].unique())
    if baseline_name not in scenarios:
        raise ValueError(f"Baseline '{baseline_name}' not in scenarios: {scenarios}")

    compare_scenarios = [s for s in scenarios if s != baseline_name]

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1) Annual tables
    tables = annual_summary_table(
        df_values=df_values,
        metric_groups=metric_groups,
        baseline_name=baseline_name,
        periods=periods,
        metric_keys=metric_keys,
    )

    # Add labels from fields.pkl 
    for _k, _t in tables.items():
        if "Metric" in _t.columns and "Metric_Label" not in _t.columns:
            _t.insert(2, "Metric_Label", _t["Metric"].map(lambda x: fields.get(x, x)))

    excel_path = out_path / "annual_WY_summary.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as xw:
        for sheet, table in tables.items():
            table.to_excel(xw, sheet_name=sheet[:31], index=False)

    # 2) Figures
    fig_dir = out_path / "figures"
    for per in periods:
        for mk in metric_keys:
            raw_label = fields.get(mk, mk)
            label = raw_label.split(":", 1)[1].strip() if ":" in raw_label else raw_label
            unit = units.get(mk, "TAF")
            out_png = fig_dir / per.name / f"{mk}.png"
            plot_timeseries_and_cdf(
                df_values=df_values,
                metric_key=mk,
                metric_label=label,
                baseline_name=baseline_name,
                compare_scenarios=compare_scenarios,
                period=per,
                out_png=str(out_png),
                unit=unit,
            )

    return {
        "annual_table_excel": str(excel_path),
        "figures_dir": str(fig_dir),
        "scenarios": scenarios,
        "n_metrics": len(metric_keys),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Product A validation post-processing."
    )
    parser.add_argument(
        "--pickle-dir",
        default=str(PICKLE_DIR),
        help="Directory containing values.pkl, diffs.pkl, units.pkl, and fields.pkl.",
    )
    parser.add_argument(
        "--baseline-name",
        "--benchmark-name",
        dest="baseline_name",
        default=BASELINE_NAME,
        help="Baseline scenario name in values.pkl.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="Output directory for Product A post-processing results.",
    )
    args = parser.parse_args()

    outputs = run_post_processing_package(
        pickle_dir=args.pickle_dir,
        baseline_name=args.baseline_name,
        out_dir=args.out_dir,
    )

    print("Created:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()