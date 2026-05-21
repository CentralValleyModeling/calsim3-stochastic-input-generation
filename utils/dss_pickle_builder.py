"""
dss_pickle_builder.py

Shared CalView-style "cache" builder for DSS time series used by both
Product A and Product B post-processing.

Artifacts created in an output directory:
- values.pkl : pandas DataFrame with stacked monthly data for all scenarios
- diffs.pkl  : pandas DataFrame of (scenario - baseline) for each metric column
- units.pkl  : dict mapping metric_key -> units string (builder can force everything to "TAF")
- fields.pkl : dict mapping metric_key -> human-friendly label
- meta.json  : provenance (scenario paths, metric definitions, DSS pathnames selected, etc.)

Key features:
- Reads DSS using pydsstools (HEC-DSS).
- Supports "Construction" formulas such as:
      A + B - C
  using a safe AST evaluator.
- Forces all metrics to monthly TAF by default:
    * CFS -> TAF/month using days_in_month
    * AF  -> TAF
    * TAF/KAF -> TAF
- Loads metric definitions from a shared metrics.csv.

Compared with the earlier single-purpose version, this shared builder:
- lives in utils/dss_pickle_builder.py
- computes diffs by aligning on the monthly time columns instead of row order
- is intended to be imported by both product_a and product_b run scripts
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import ast
import json
import pickle
import re
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from utils.dss_io import open_dss


# -----------------------------
# Data classes
# -----------------------------

@dataclass(frozen=True)
class Scenario:
    """One scenario/run = one DSS file."""

    name: str
    dss_path: str


@dataclass(frozen=True)
class MetricSpec:
    """One metric definition row loaded from metrics.csv."""

    group: str
    metric: str
    construction: str
    key: str


# -----------------------------
# Helpers
# -----------------------------

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\uFEFF]")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_OPERATOR_REMAP = {
    "\u2212": "-",  # minus sign
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\uFE63": "-",  # small hyphen-minus
    "\uFF0D": "-",  # fullwidth hyphen-minus
    "\uFF0B": "+",  # fullwidth plus
}


def clean_text(value: str) -> str:
    text = "" if value is None else str(value)
    text = _ZERO_WIDTH_RE.sub("", text)
    return text.strip()


def normalize_construction(expr: str) -> str:
    expr = clean_text(expr)
    if expr.startswith("="):
        expr = expr[1:].strip()
    for old, new in _OPERATOR_REMAP.items():
        expr = expr.replace(old, new)
    return expr


def make_safe_key(label: str) -> str:
    label = clean_text(label)
    label = label.replace("&", "and")
    label = re.sub(r"[^\w]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label or "metric"


def extract_symbols(expr: str) -> List[str]:
    expr = normalize_construction(expr)
    symbols = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)
    return sorted(set(symbols))


class _SafeEval(ast.NodeVisitor):
    """Safe evaluator for expressions like A + B - C."""

    def __init__(self, series_lookup: Dict[str, pd.Series]):
        self.series_lookup = series_lookup

    def visit_Expression(self, node: ast.Expression):
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name):
        if node.id not in self.series_lookup:
            raise KeyError(f"Unknown symbol in construction: {node.id}")
        return self.series_lookup[node.id]

    def visit_BinOp(self, node: ast.BinOp):
        left = self.visit(node.left)
        right = self.visit(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        raise ValueError("Only + and - are supported in constructions.")

    def visit_UnaryOp(self, node: ast.UnaryOp):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError("Only unary + and - are supported.")

    def generic_visit(self, node):
        raise ValueError(f"Unsupported syntax in construction: {type(node).__name__}")


def evaluate_construction(expr: str, series_lookup: Dict[str, pd.Series]) -> pd.Series:
    expr = normalize_construction(expr)
    tree = ast.parse(expr, mode="eval")
    evaluator = _SafeEval(series_lookup)
    out = evaluator.visit(tree)
    if not isinstance(out, pd.Series):
        raise TypeError("Construction did not evaluate to a pandas Series.")
    return out


def to_monthly_taf(series: pd.Series, units: str) -> pd.Series:
    """Convert a monthly series to TAF if possible."""

    u = clean_text(units).upper()
    s = series.copy()
    s.index = pd.to_datetime(s.index)

    if u in ("TAF", "KAF"):
        return s

    if u in ("AF", "AC-FT", "ACFT", "ACRE-FEET", "ACRE_FEET"):
        return s / 1000.0

    if u in ("CFS", "FT3/S", "FT^3/S"):
        days = pd.Index(s.index).days_in_month
        return s * days * 1.983471074 / 1000.0

    raise ValueError(f"Unsupported units for TAF conversion: '{units}'")


def _find_col(df: pd.DataFrame, want: str) -> str:
    want_norm = want.strip().lower()
    for col in df.columns:
        if str(col).strip().lower() == want_norm:
            return str(col)
    raise KeyError(want)


def load_metric_specs_from_csv(metrics_csv_path: str) -> List[MetricSpec]:
    """Load MetricSpec rows from a shared metrics.csv."""

    df = pd.read_csv(metrics_csv_path)

    col_group = _find_col(df, "Group")
    col_metric = _find_col(df, "Metric")
    col_key = _find_col(df, "Key")
    col_con = _find_col(df, "Calsim Part B Construction")

    used: set[str] = set()
    specs: List[MetricSpec] = []

    for _, row in df.iterrows():
        group = clean_text(row[col_group])
        metric = clean_text(row[col_metric])
        key_raw = clean_text(row[col_key])
        construction = normalize_construction(row[col_con])

        if not key_raw:
            raise ValueError(
                f"Missing Key for metric '{metric}'. "
                "Every row in metrics.csv must include a populated Key."
            )

        key = key_raw.upper()
        if not _SYMBOL_RE.fullmatch(key):
            key = make_safe_key(key).upper()

        base_key = key
        i = 2
        while key in used:
            key = f"{base_key}_{i}"
            i += 1
        used.add(key)

        specs.append(
            MetricSpec(
                group=group,
                metric=metric,
                construction=construction,
                key=key,
            )
        )

    return specs


def single_scenario_pull(
    dss_path: str,
    bparts: Sequence[str],
    shift_index_days: int = -1,
) -> Tuple[pd.DataFrame, Dict[str, str], Dict[str, str]]:
    """Open one DSS file once and pull all requested B-parts.

    Long Windows file paths (> 200 chars) are transparently shortened via a
    Windows directory junction by ``utils.dss_io.open_dss``, so the underlying
    Fortran HEC-DSS library always sees a path well under its 256-char CNAME
    limit. The per-record (DSS pathname) 256-char limit is still enforced
    below by filtering ``getPathnameList`` results.
    """
    with open_dss(dss_path, version=6, catalog_flag=False) as fid:
        try:
            pathnames_raw = fid.getPathnameList("/*/*/*/*/*/*/", sort=1)
        except Exception:
            pathnames_dict = fid.getPathnameDict()
            pathnames_raw = list(pathnames_dict.values())[0]

        # Keep only valid string pathnames within 256-char Fortran CNAME limit
        pathnames = [
            p for p in pathnames_raw
            if isinstance(p, str) and p.startswith("/") and len(p) <= 256
        ]
        n_skipped = len(pathnames_raw) - len(pathnames)
        if n_skipped:
            print(f"  Warning: skipped {n_skipped} DSS pathname(s) (non-string or exceeding 256-char limit)")

        if not pathnames:
            raise RuntimeError(
                f"No valid pathnames found in DSS file (0 records).\n"
                f"  Path: {dss_path}"
            )

        df_paths = pd.DataFrame(pathnames, columns=["AllPaths"])
        df_paths[["blank1", "A", "B", "C", "D", "E", "F", "blank2"]] = (
            df_paths["AllPaths"].str.split("/", expand=True)
        )
        df_paths = df_paths.drop(columns=["AllPaths", "blank1", "blank2"])
        df_paths = df_paths.sort_values(by=["B", "D"])
        df_paths = df_paths.drop_duplicates(subset=["B", "C"]).reset_index(drop=True)

        df_ts = pd.DataFrame()
        base_units: Dict[str, str] = {}
        base_paths: Dict[str, str] = {}

        for bpart in bparts:
            bpart_up = clean_text(bpart).upper()
            try:
                match = df_paths[df_paths["B"] == bpart_up]
                if match.empty:
                    raise KeyError(f"B-part '{bpart_up}' not found.")

                chosen_row = match.iloc[0]
                pathname = (
                    f"/{chosen_row['A']}/{bpart_up}/{chosen_row['C']}//"
                    f"{chosen_row['E']}/{chosen_row['F']}/"
                )

                working_ts = fid.read_ts(pathname, trim_missing=True)
                units = getattr(working_ts, "units", "") or ""

                base_units[bpart_up] = str(units)
                base_paths[bpart_up] = pathname

                df_working = pd.DataFrame(
                    working_ts.values.astype("float64"),
                    index=working_ts.pytimes,
                    columns=[bpart_up],
                )
                df_ts = df_ts.merge(
                    right=df_working,
                    how="outer",
                    left_index=True,
                    right_index=True,
                )
            except Exception as exc:
                print(f"  Warning: could not read B-part '{bpart_up}' -- {exc}")

    if not df_ts.empty:
        df_ts.index = pd.to_datetime(df_ts.index)
        if shift_index_days != 0:
            df_ts.index = df_ts.index + timedelta(days=shift_index_days)

    return df_ts, base_units, base_paths


def _compute_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.insert(0, "JanDecYear", df.index.year)
    df.insert(0, "Month", df.index.month)
    df.insert(0, "Year", df.index.year)
    df.insert(0, "MarFebYear", np.where(df["Month"] >= 3, df["Year"], df["Year"] - 1))
    df.insert(0, "OctSeptYear", np.where(df["Month"] <= 9, df["Year"], df["Year"] + 1))
    return df


def _compute_diffs(
    df_values: pd.DataFrame,
    metric_cols: Sequence[str],
    baseline_name: str,
) -> pd.DataFrame:
    """Compute scenario - baseline diffs aligned on the monthly time columns."""

    fixed_cols = ["Date", "Scenario", "OctSeptYear", "MarFebYear", "Year", "Month", "JanDecYear"]
    join_cols = [c for c in fixed_cols if c != "Scenario"]

    baseline = df_values[df_values["Scenario"] == baseline_name].copy()
    baseline = baseline[join_cols + list(metric_cols)].copy()
    baseline = baseline.rename(columns={col: f"{col}__baseline" for col in metric_cols})

    diff_frames: List[pd.DataFrame] = []

    for scen in df_values["Scenario"].drop_duplicates():
        block = df_values[df_values["Scenario"] == scen].copy()
        merged = block.merge(baseline, on=join_cols, how="left", validate="one_to_one")

        missing_rows = merged[[f"{col}__baseline" for col in metric_cols]].isna().all(axis=1).sum()
        if missing_rows:
            raise ValueError(
                f"Could not align {missing_rows} rows of scenario '{scen}' with baseline "
                f"'{baseline_name}' when computing diffs."
            )

        diff = merged[fixed_cols].copy()
        for col in metric_cols:
            diff[col] = merged[col] - merged[f"{col}__baseline"]

        diff_frames.append(diff)

    return pd.concat(diff_frames, ignore_index=True)


def build_pickles(
    scenarios: Sequence[Scenario],
    metric_specs: Sequence[MetricSpec],
    baseline_name: str,
    out_dir: str,
    force_taf: bool = True,
    shift_index_days: int = -1,
) -> Dict[str, str]:
    """Build CalView-like pickle files for a set of DSS scenarios."""

    if not scenarios:
        raise ValueError("No scenarios provided.")

    scenario_names = [scenario.name for scenario in scenarios]
    if baseline_name not in scenario_names:
        raise ValueError(f"baseline_name='{baseline_name}' not found in scenarios: {scenario_names}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    base_symbols: List[str] = []
    for metric_spec in metric_specs:
        base_symbols.extend(extract_symbols(metric_spec.construction))
    base_symbols = sorted({symbol.upper() for symbol in base_symbols})

    all_frames: List[pd.DataFrame] = []
    base_units: Dict[str, str] = {}
    base_paths: Dict[str, str] = {}

    for scenario in scenarios:
        print(f"Working on {scenario.name}")

        df_ts, scen_units, scen_paths = single_scenario_pull(
            dss_path=scenario.dss_path,
            bparts=base_symbols,
            shift_index_days=shift_index_days,
        )

        for symbol in base_symbols:
            base_units.setdefault(symbol, scen_units.get(symbol, ""))
            base_paths.setdefault(symbol, scen_paths.get(symbol, ""))

        df_ts.dropna(how="any", inplace=True)

        if force_taf:
            for symbol in list(df_ts.columns):
                df_ts[symbol] = to_monthly_taf(df_ts[symbol], scen_units.get(symbol, ""))

        series_by_symbol: Dict[str, pd.Series] = {col: df_ts[col] for col in df_ts.columns}

        metric_series: Dict[str, pd.Series] = {}
        for metric_spec in metric_specs:
            expr_norm = normalize_construction(metric_spec.construction)
            expr_upper = re.sub(
                r"[A-Za-z_][A-Za-z0-9_]*",
                lambda match: match.group(0).upper(),
                expr_norm,
            )
            out_series = evaluate_construction(expr_upper, series_by_symbol)
            out_series.name = metric_spec.key
            metric_series[metric_spec.key] = out_series

        df = pd.DataFrame(metric_series).sort_index()
        df = _compute_time_columns(df)
        df.insert(0, "Scenario", scenario.name)

        df["Date"] = df.index
        date_col = df.pop("Date")
        df.insert(0, "Date", date_col)

        df = df.reset_index(drop=True)
        all_frames.append(df)

    df_values = pd.concat(all_frames, ignore_index=True)

    metric_cols = [metric_spec.key for metric_spec in metric_specs]
    df_diffs = _compute_diffs(df_values=df_values, metric_cols=metric_cols, baseline_name=baseline_name)

    units_dict = {metric_spec.key: ("TAF" if force_taf else "") for metric_spec in metric_specs}
    fields_dict = {
        metric_spec.key: (
            f"{metric_spec.group}: {metric_spec.metric}"
            if metric_spec.group else metric_spec.metric
        )
        for metric_spec in metric_specs
    }

    values_pkl = out_path / "values.pkl"
    diffs_pkl = out_path / "diffs.pkl"
    units_pkl = out_path / "units.pkl"
    fields_pkl = out_path / "fields.pkl"

    with open(values_pkl, "wb") as f:
        pickle.dump(df_values, f)

    with open(diffs_pkl, "wb") as f:
        pickle.dump(df_diffs, f)

    with open(units_pkl, "wb") as f:
        pickle.dump(units_dict, f)

    with open(fields_pkl, "wb") as f:
        pickle.dump(fields_dict, f)

    meta = {
        "baseline": baseline_name,
        "scenarios": [{"name": scenario.name, "dss_path": scenario.dss_path} for scenario in scenarios],
        "metric_specs": [
            {
                "group": metric_spec.group,
                "metric": metric_spec.metric,
                "key": metric_spec.key,
                "construction": metric_spec.construction,
            }
            for metric_spec in metric_specs
        ],
        "base_units": base_units,
        "base_pathnames_example": base_paths,
        "force_taf": force_taf,
        "shift_index_days": shift_index_days,
    }
    (out_path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "values.pkl": str(values_pkl),
        "diffs.pkl": str(diffs_pkl),
        "units.pkl": str(units_pkl),
        "fields.pkl": str(fields_pkl),
        "meta.json": str(out_path / "meta.json"),
    }


def build_pickles_from_metrics_csv(
    scenarios: Sequence[Scenario],
    baseline_name: str,
    out_dir: str,
    metrics_csv_path: str,
    force_taf: bool = True,
    shift_index_days: int = -1,
) -> Dict[str, str]:
    metric_specs = load_metric_specs_from_csv(metrics_csv_path)
    return build_pickles(
        scenarios=scenarios,
        metric_specs=metric_specs,
        baseline_name=baseline_name,
        out_dir=out_dir,
        force_taf=force_taf,
        shift_index_days=shift_index_days,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Build CalView-style pickles from DSS scenarios using a shared metrics.csv."
        )
    )
    parser.add_argument("--metrics-csv", required=True, help="Path to shared metrics.csv")
    parser.add_argument("--baseline", required=True, help="Baseline scenario name")
    parser.add_argument("--out-dir", required=True, help="Output directory for pickles")
    parser.add_argument(
        "--scenario",
        action="append",
        nargs=2,
        metavar=("NAME", "DSS_PATH"),
        help='Add a scenario as: --scenario "Benchmark" C:\\path\\run.dss',
        required=True,
    )

    args = parser.parse_args()
    scenarios = [Scenario(name=name, dss_path=path) for name, path in args.scenario]

    paths = build_pickles_from_metrics_csv(
        scenarios=scenarios,
        baseline_name=args.baseline,
        out_dir=args.out_dir,
        metrics_csv_path=args.metrics_csv,
    )

    print("Created:")
    for key, value in paths.items():
        print(f"  {key}: {value}")
