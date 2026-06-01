"""
Product A Validation Run Postprocessing
=======================================
Consumes the shared CalView-style pickle cache (values.pkl / diffs.pkl /
units.pkl / fields.pkl) built by ``_productA_pickle_builder.py`` and
produces annual WY summary tables + per-metric two-panel figures
(monthly time series + non-exceedance CDF, with R2 / NSE / PBIAS
annotations vs the baseline). Default periods: full validation
WY 1972-2018 and drought WY 1987-1992. Also reused by
``_historical_modified_postproc.py`` via ``run_post_processing_package``.

Inputs
------
- Pickle cache: ``GENERATED/postprocessing/calsim_runs/product_a/
  pickle_files/`` (values.pkl, diffs.pkl, units.pkl, fields.pkl)

Outputs
-------
- ``GENERATED/postprocessing/calsim_runs/product_a/output/``
  - ``annual_WY_summary.xlsx`` (one sheet per period)
  - ``figures/<period>/<metric>.png`` (2-panel: monthly TS + non-exceedance CDF)

Dependencies
------------
- utils.paths
- utils.validation_plots
- pandas, numpy, openpyxl

Usage
-----
    python postprocessing/calsim_runs/_productA_postproc.py
    python postprocessing/calsim_runs/_productA_postproc.py --baseline-name Historical
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle
import sys as _sys
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# =============================
# Repository-aware default paths
# =============================
RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]

_sys.path.insert(0, str(REPO_ROOT))
from utils.paths import get_generated_dir
from utils.validation_plots import Series, plot_ts_cdf

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
    name="Full_Validation_WY1972_2018",
    start=pd.Timestamp("1971-10-01"),
    end=pd.Timestamp("2018-09-30"),
    wy_start=1972,
    wy_end=2018,
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
    """Two-panel monthly time series + non-exceedance CDF for baseline vs
    one-or-more scenarios. Thin wrapper over
    :func:`utils.validation_plots.plot_ts_cdf` that builds the per-scenario
    :class:`Series` list and lets the helper auto-compute R2 / NSE / PBIAS
    against the baseline (``compute_metrics_from=0``).
    """
    dfp = df_values[
        (df_values["Date"] >= period.start) & (df_values["Date"] <= period.end)
    ].copy()

    all_scenarios = [baseline_name] + list(compare_scenarios)
    series_list = []
    for i, scen in enumerate(all_scenarios):
        sub = dfp[dfp["Scenario"] == scen].sort_values("Date")
        series_list.append(Series(
            label=scen,
            dates=sub["Date"].to_numpy(),
            values=sub[metric_key].to_numpy(dtype=float),
            linewidth=0.8 if i == 0 else 0.9,
        ))

    subtitle = None
    if "Full_Validation" not in period.name:
        subtitle = f"(WY {period.wy_start}-{period.wy_end})"

    plot_ts_cdf(
        series=series_list,
        title=f"{metric_label} ({unit})",
        unit=unit,
        compute_metrics_from=0,
        subtitle=subtitle,
        out_path=out_png,
    )


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