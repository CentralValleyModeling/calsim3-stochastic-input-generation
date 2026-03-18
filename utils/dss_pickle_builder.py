"""dss_pickle_builder.py

CalView-style "cache" builder for DSS time series.


Artifacts created in an output directory:
- values.pkl : pandas DataFrame with stacked monthly data for all scenarios
- diffs.pkl  : pandas DataFrame of (scenario - baseline) for each metric column
- units.pkl  : dict mapping metric_key -> units string (builder can force everything to "TAF")
- fields.pkl : dict mapping metric_key -> human-friendly label (CalView-style)
- meta.json  : provenance (scenario paths, constructions, DSS pathnames selected, etc.)

Key features:
- Reads DSS using pydsstools (HEC-DSS).
- Supports "Construction" formulas like:
      A + B - C
  using a safe AST evaluator (no arbitrary code execution).
- Forces all metrics to monthly TAF by default:
    * CFS -> TAF/month using days_in_month
    * AF  -> TAF
    * TAF/KAF -> TAF

Metrics CSV requirements:
- metrics.csv has these columns (case-insensitive):
    Group, Metric, Key, Calsim Part B Construction
- For a direct DSS B-part: Construction is just the B-part and Key is the same B-part.
- For a formula: Construction is an expression using + and - between B-part symbols,
  and Key is the desired output field-code.

Example row:
    Group: Deliveries
    Metric: CVP Total
    Key: DEL_CVP_TOTAL
    Calsim Part B Construction: DEL_CVP_TOTAL_N + DEL_CVP_TOTAL_S

Typical usage from a run script:

    from pathlib import Path
    import sys

    RUN_DIR = Path(__file__).resolve().parent
    UTILS_DIR = (RUN_DIR / ".." / "_utils_").resolve()
    sys.path.append(str(UTILS_DIR))

    from dss_pickle_builder import Scenario, build_pickles_from_metrics_csv

    scenarios = [
        Scenario("Historical", r"C:\\path\\hist.dss"),
        Scenario("AltA",       r"C:\\path\\alta.dss"),
    ]

    build_pickles_from_metrics_csv(
        scenarios=scenarios,
        baseline_name="Historical",
        out_dir=r"C:\\path\\cache\\Hist_vs_AltA",
        metrics_csv_path=str(RUN_DIR / "metrics.csv"),
    )

Command line usage:

    python dss_pickle_builder.py --baseline "Historical" --out-dir C:\cache \
        --scenario "Historical" C:\hist.dss --scenario "AltA" C:\altA.dss

"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import timedelta
import ast
import json
import re
import pickle
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


# -----------------------------
# Data classes
# -----------------------------

@dataclass(frozen=True)
class Scenario:
    """One scenario/run = one DSS file (same assumption as CalView)."""

    name: str
    dss_path: str


@dataclass(frozen=True)
class MetricSpec:
    """One metric definition row (from metrics.csv)."""

    group: str
    metric: str
    construction: str
    key: str  # column key in output DataFrame


# -----------------------------
# Helpers
# -----------------------------

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\uFEFF]")  # common invisible characters
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Normalize common unicode operator variants that appear when copying from Excel/Word/PDF
_OPERATOR_REMAP = {
    "\u2212": "-",  # minus sign (U+2212)
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\uFE63": "-",  # small hyphen-minus
    "\uFF0D": "-",  # fullwidth hyphen-minus
    "\uFF0B": "+",  # fullwidth plus
}


def clean_text(s: str) -> str:
    s = "" if s is None else str(s)
    s = _ZERO_WIDTH_RE.sub("", s)
    return s.strip()


def normalize_construction(expr: str) -> str:
    """Normalize a Construction string (metric definition)."""

    expr = clean_text(expr)
    if expr.startswith("="):
        expr = expr[1:].strip()
    for k, v in _OPERATOR_REMAP.items():
        expr = expr.replace(k, v)
    return expr


def make_safe_key(label: str) -> str:
    """Convert a label into a safe, reproducible column key."""

    label = clean_text(label)
    label = label.replace("&", "and")
    label = re.sub(r"[^\w]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label or "metric"


def parse_dss_pathname(pathname: str) -> Tuple[str, str, str, str, str, str]:
    """Split a DSS pathname /A/B/C/D/E/F/ into parts."""

    parts = pathname.strip("/").split("/")
    if len(parts) != 6:
        raise ValueError(f"Unexpected DSS pathname format: {pathname}")
    return tuple(parts)  # type: ignore


def extract_symbols(expr: str) -> List[str]:
    """Extract variable symbols from a Construction string."""

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


def _require_pydsstools():
    try:
        from pydsstools.heclib.dss import HecDss  # noqa: F401
    except Exception as e:
        raise ImportError(
            "pydsstools is required to read DSS. Install with:\n"
            "  conda install -c conda-forge pydsstools\n"
            "or\n"
            "  pip install pydsstools\n"
        ) from e


def read_dss_bpart_series(
    dss_path: str,
    bpart: str,
    shift_index_days: int = -1,
) -> Tuple[pd.Series, str, str]:
    """Read a time series from a DSS file by matching B-part.

    Mirrors csdss_readlib_fullfile.single_file_pull(): opens the file with
    HecDss.Open(), builds a pathname DataFrame from getPathnameDict(),
    sorts by ['B', 'D'] and drops duplicates on ['B', 'C'] so that
    iloc[0] gives a single deterministic match — no E-part preference
    logic needed.
    """

    _require_pydsstools()
    from pydsstools.heclib.dss import HecDss

    bpart = clean_text(bpart).upper()
    dss_path = str(dss_path)

    fid = HecDss.Open(dss_path)

    # Build a DataFrame of all pathnames (csdss approach)
    pathNamesDict = fid.getPathnameDict()
    pathNames = np.array(list(pathNamesDict.values())[0])

    dfPaths = pd.DataFrame(pathNames, columns=["AllPaths"])
    dfPaths[["blank1", "A", "B", "C", "D", "E", "F", "blank2"]] = \
        dfPaths["AllPaths"].str.split("/", expand=True)
    dfPaths = dfPaths.drop(columns=["AllPaths", "blank1", "blank2"])
    # Sort by B then D, deduplicate on (B, C) — identical to csdss
    dfPaths = dfPaths.sort_values(by=["B", "D"])
    dfPaths = dfPaths.drop_duplicates(subset=["B", "C"])
    dfPaths = dfPaths.reset_index(drop=True)

    match = dfPaths[dfPaths["B"] == bpart]
    if match.empty:
        fid.close()
        raise KeyError(f"B-part '{bpart}' not found in DSS: {dss_path}")

    chosen_row = match.iloc[0]
    target_pathname = f"/{chosen_row['A']}/{bpart}/{chosen_row['C']}//{chosen_row['E']}/{chosen_row['F']}/"

    working_ts = fid.read_ts(target_pathname, trim_missing=True)
    units = getattr(working_ts, "units", "") or ""

    s = pd.Series(working_ts.values.astype("float64"), index=working_ts.pytimes, name=bpart)
    fid.close()

    s.index = pd.to_datetime(s.index)
    if shift_index_days != 0:
        s.index = s.index + timedelta(days=shift_index_days)

    return s, str(units), target_pathname


def to_monthly_taf(series: pd.Series, units: str) -> pd.Series:
    """Convert a monthly series to TAF if possible."""

    u = clean_text(units).upper()
    s = series.copy()
    s.index = pd.to_datetime(s.index)

    if u in ("TAF"):
        return s

    if u in ("AF", "AC-FT", "ACFT", "ACRE-FEET", "ACRE_FEET"):
        return s / 1000.0

    if u in ("CFS", "FT3/S", "FT^3/S"):
        # 1 cfs-day = 1.983471074 acre-feet
        days = pd.Index(s.index).days_in_month
        return s * days * 1.983471074 / 1000.0

    raise ValueError(f"Unsupported units for TAF conversion: '{units}'")


def compute_time_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add water-year columns to a DataFrame that has Date as a column.

    Matches csdss_readlib_fullfile convention:
    - OctSeptYear: Oct water year (month <= 9 → same year, month >= 10 → year+1)
    - MarFebYear:  Mar water year (month >= 3 → same year, month < 3 → year-1)
    - JanDecYear:  calendar year
    """
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    df["OctSeptYear"] = np.where(df["Month"] <= 9, df["Year"], df["Year"] + 1)
    df["MarFebYear"] = np.where(df["Month"] >= 3, df["Year"], df["Year"] - 1)
    df["JanDecYear"] = df["Year"]
    return df


# -----------------------------
# Metrics spec loading (CSV with Key)
# -----------------------------


def _find_col(df: pd.DataFrame, want: str) -> str:
    want_norm = want.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == want_norm:
            return str(c)
    raise KeyError(want)


def load_metric_specs_from_csv(metrics_csv_path: str = "metrics.csv") -> List[MetricSpec]:
    """Load MetricSpec list from a Key-based metrics.csv."""

    df = pd.read_csv(metrics_csv_path)

    # Case-insensitive column match
    col_group = _find_col(df, "Group")
    col_metric = _find_col(df, "Metric")
    col_key = _find_col(df, "Key")
    col_con = _find_col(df, "Calsim Part B Construction")

    used = set()
    specs: List[MetricSpec] = []

    for _, row in df.iterrows():
        group = clean_text(row[col_group])
        metric = clean_text(row[col_metric])
        key_raw = clean_text(row[col_key])
        construction = normalize_construction(row[col_con])

        if not key_raw:
            raise ValueError(
                f"Missing Key for metric '{metric}'. "
                "Your metrics.csv must always have a Key column populated for every row."
            )

        # Enforce CalView-style "field code" naming: uppercase, safe identifier
        key = key_raw.upper()
        if not _SYMBOL_RE.fullmatch(key):
            key = make_safe_key(key).upper()

        # Ensure uniqueness (avoid collisions if user repeats keys)
        base_key = key
        i = 2
        while key in used:
            key = f"{base_key}_{i}"
            i += 1
        used.add(key)

        specs.append(MetricSpec(group=group, metric=metric, construction=construction, key=key))

    return specs


def single_scenario_pull(
    dss_path: str,
    bparts: Sequence[str],
    shift_index_days: int = -1,
) -> Tuple["pd.DataFrame", Dict[str, str], Dict[str, str]]:
    """Open a DSS file ONCE and pull all required B-parts into a merged DataFrame.

    Mirrors csdss_readlib_fullfile.single_file_pull(): builds a pathname
    DataFrame with getPathnameDict(), sorts by ['B', 'D'], drops duplicates
    on ['B', 'C'], then uses iloc[0] for each B-part — no E-part preference
    logic needed. Reads with trim_missing=True and merges with an outer join.

    Returns
    -------
    df_ts : DataFrame indexed by datetime, one column per B-part successfully read
    base_units : dict mapping bpart -> units string
    base_paths : dict mapping bpart -> full DSS pathname used
    """
    _require_pydsstools()
    from pydsstools.heclib.dss import HecDss

    fid = HecDss.Open(str(dss_path))

    # Build pathname lookup DataFrame once for the whole file (csdss approach)
    pathNamesDict = fid.getPathnameDict()
    pathNames = np.array(list(pathNamesDict.values())[0])

    dfPaths = pd.DataFrame(pathNames, columns=["AllPaths"])
    dfPaths[["blank1", "A", "B", "C", "D", "E", "F", "blank2"]] = \
        dfPaths["AllPaths"].str.split("/", expand=True)
    dfPaths = dfPaths.drop(columns=["AllPaths", "blank1", "blank2"])
    # Sort by B then D, deduplicate on (B, C) — identical to csdss
    dfPaths = dfPaths.sort_values(by=["B", "D"])
    dfPaths = dfPaths.drop_duplicates(subset=["B", "C"])
    dfPaths = dfPaths.reset_index(drop=True)

    df_ts: pd.DataFrame = pd.DataFrame()
    base_units: Dict[str, str] = {}
    base_paths: Dict[str, str] = {}

    for bpart in bparts:
        bpart_up = clean_text(bpart).upper()
        try:
            match = dfPaths[dfPaths["B"] == bpart_up]
            if match.empty:
                raise KeyError(f"B-part '{bpart_up}' not found.")

            chosen_row = match.iloc[0]
            target_pathname = f"/{chosen_row['A']}/{bpart_up}/{chosen_row['C']}//{chosen_row['E']}/{chosen_row['F']}/"

            working_ts = fid.read_ts(target_pathname, trim_missing=True)
            units = getattr(working_ts, "units", "") or ""

            base_units[bpart_up] = str(units)
            base_paths[bpart_up] = target_pathname

            # Merge into combined DataFrame (csdss outer-join approach)
            df_working = pd.DataFrame(
                working_ts.values.astype("float64"),
                index=working_ts.pytimes,
                columns=[bpart_up],
            )
            df_ts = df_ts.merge(right=df_working, how="outer", left_index=True, right_index=True)

        except Exception as exc:
            print(f"  Warning: could not read B-part '{bpart_up}' — {exc}")

    fid.close()

    if not df_ts.empty:
        df_ts.index = pd.to_datetime(df_ts.index)
        if shift_index_days != 0:
            df_ts.index = df_ts.index + timedelta(days=shift_index_days)

    return df_ts, base_units, base_paths


# -----------------------------
# Main build function
# -----------------------------


def build_pickles(
    scenarios: Sequence[Scenario],
    metric_specs: Sequence[MetricSpec],
    baseline_name: str,
    out_dir: str,
    force_taf: bool = True,
    shift_index_days: int = -1,
) -> Dict[str, str]:
    """Build CalView-like pickle files for a set of scenarios and metric constructions."""

    if not scenarios:
        raise ValueError("No scenarios provided.")

    scenario_names = [s.name for s in scenarios]
    if baseline_name not in scenario_names:
        raise ValueError(f"baseline_name='{baseline_name}' not found in scenarios: {scenario_names}")

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Collect base B-parts required by all constructions
    base_symbols: List[str] = []
    for ms in metric_specs:
        base_symbols.extend(extract_symbols(ms.construction))
    base_symbols = sorted(set([s.upper() for s in base_symbols]))

    all_frames: List[pd.DataFrame] = []
    base_units: Dict[str, str] = {}
    base_paths: Dict[str, str] = {}

    for scen in scenarios:
        print(f"Working on {scen.name}")

        # Open DSS once per scenario and read all base symbols (csdss approach)
        df_ts, scen_units, scen_paths = single_scenario_pull(
            dss_path=scen.dss_path,
            bparts=base_symbols,
            shift_index_days=shift_index_days,
        )

        for sym in base_symbols:
            base_units.setdefault(sym, scen_units.get(sym, ""))
            base_paths.setdefault(sym, scen_paths.get(sym, ""))

        # Drop rows with any NaN across all base B-parts (mirror csdss dropna)
        df_ts.dropna(how="any", inplace=True)

        # Convert to TAF in-place on the merged DataFrame
        if force_taf:
            for sym in list(df_ts.columns):
                units = scen_units.get(sym, "")
                df_ts[sym] = to_monthly_taf(df_ts[sym], units)

        # series_by_symbol keyed by uppercase B-part name
        series_by_symbol: Dict[str, pd.Series] = {col: df_ts[col] for col in df_ts.columns}

        # Evaluate construction formulas
        metric_series: Dict[str, pd.Series] = {}
        for ms in metric_specs:
            expr_norm = normalize_construction(ms.construction)
            expr_upper = re.sub(
                r"[A-Za-z_][A-Za-z0-9_]*",
                lambda m: m.group(0).upper(),
                expr_norm,
            )
            out_s = evaluate_construction(expr_upper, series_by_symbol)
            out_s.name = ms.key
            metric_series[ms.key] = out_s

        # Build metric DataFrame with datetime index
        df = pd.DataFrame(metric_series)

        # Add time columns using insert + np.where (csdss approach)
        df.insert(0, "JanDecYear", df.index.year)
        df.insert(0, "Month", df.index.month)
        df.insert(0, "Year", df.index.year)
        df.insert(0, "MarFebYear", np.where(df["Month"] >= 3, df["Year"], df["Year"] - 1))
        df.insert(0, "OctSeptYear", np.where(df["Month"] <= 9, df["Year"], df["Year"] + 1))
        df.insert(0, "Scenario", scen.name)

        # Make Date a column (csdss approach: pop from index, insert at front)
        df["Date"] = df.index
        date_temp = df.pop("Date")
        df.insert(0, "Date", date_temp)

        df = df.reset_index(drop=True)
        all_frames.append(df)

    df_values = pd.concat(all_frames, ignore_index=True)

    # Units and fields dicts for metrics
    units_dict = {ms.key: ("TAF" if force_taf else "") for ms in metric_specs}

    # CalView-style label: "Group: Metric" (includes group prefix so
    # downstream code can parse the group from the label via ":".)
    fields_dict = {
        ms.key: (f"{ms.group}: {ms.metric}" if ms.group else ms.metric)
        for ms in metric_specs
    }

    # Compute diffs vs baseline using num_fixed approach (csdss-style)
    # num_fixed = number of non-metric header columns (Date, Scenario, OctSeptYear,
    #             MarFebYear, Year, Month, JanDecYear)
    num_fixed = 7
    metric_cols = [ms.key for ms in metric_specs]

    baseline_df = df_values[df_values["Scenario"] == baseline_name].reset_index(drop=True)

    diffs_frames = []
    for scen in scenario_names:
        block = df_values[df_values["Scenario"] == scen].reset_index(drop=True)

        df_fixed = block.iloc[:, :num_fixed]
        df_numeric = block.iloc[:, num_fixed:]
        df_base_numeric = baseline_df.iloc[:, num_fixed:]

        df_diff_numeric = df_numeric.subtract(df_base_numeric)
        df_diff = pd.concat([df_fixed, df_diff_numeric], axis=1)
        diffs_frames.append(df_diff)

    df_diffs = pd.concat(diffs_frames, ignore_index=True)

    # Write pickles
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
        "scenarios": [{"name": s.name, "dss_path": s.dss_path} for s in scenarios],
        "metric_specs": [
            {"group": ms.group, "metric": ms.metric, "key": ms.key, "construction": ms.construction}
            for ms in metric_specs
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
    metrics_csv_path: str = "metrics.csv",
    force_taf: bool = True,
    shift_index_days: int = -1,
) -> Dict[str, str]:
    """Convenience wrapper: load metric specs from metrics.csv (with Key) and build pickles."""

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
        description="Build CalView-like pickles from DSS scenarios using metrics.csv (must include Key column)."
    )

    # As requested: assume metrics.csv exists; allow override for convenience
    parser.add_argument(
        "--metrics-csv",
        default="metrics.csv",
        help="Path to metrics.csv (default: metrics.csv in current working directory)",
    )
    parser.add_argument("--baseline", required=True, help="Baseline scenario name (e.g., Historical)")
    parser.add_argument("--out-dir", required=True, help="Output directory for pickles")
    parser.add_argument(
        "--scenario",
        action="append",
        nargs=2,
        metavar=("NAME", "DSS_PATH"),
        help='Add a scenario as: --scenario "Historical" C:\\path\\hist.dss  (repeatable)',
        required=True,
    )

    args = parser.parse_args()

    scens = [Scenario(name=n, dss_path=p) for n, p in args.scenario]

    paths = build_pickles_from_metrics_csv(
        scenarios=scens,
        baseline_name=args.baseline,
        out_dir=args.out_dir,
        metrics_csv_path=args.metrics_csv,
    )

    print("Created:")
    for k, v in paths.items():
        print(f"  {k}: {v}")
