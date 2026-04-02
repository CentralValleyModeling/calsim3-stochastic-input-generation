# %% -- Compile Product B (1000-year stochastic) SV CSVs --------------------
"""
Consolidated Product B stochastic compilation script.

Workflow
--------
1. Scan each module's ``_product_b_final/`` directory for data CSVs
   (all CSVs are read; filenames not pattern-matched).
   The rim_inflow module uses a non-standard format and is normalised
   in-place (CalSim -> Part B, qmap_postAdj -> Value, inventory Part C).
2. Assign each CSV to a chunk tag (n01-n10) from the filename.
3. Cross-reference against the master inventory (same flags as Product A):
   - Missing = T  ->  skip entirely
   - Used in DCR = F  ->  skip entirely
   - Constant/Rept = T  ->  auto-fill from baseline 12-month pattern
4. For each chunk, concatenate all module CSVs + Constant/Rept rows into a
   single compiled CSV: ``ProductB_SV_n{01..10}.csv``
5. Compare Product B chunk statistics against compiled Product A DSS
   (monthly means per Part B/C) and write diagnostic comparison CSV.
6. Write inventory cross-reference diagnostics and compilation summary.

Diagnostic outputs  (all written to ``product_b_compilation/``)
------------------------------------------------------------------------
- ``compiled_input_files/<module>/*.csv``  -- local copies of source CSVs
- ``_product_b_compiled_sv/ProductB_SV_n01.dss`` .. ``n10.dss``
- ``inventory_expected_modified.csv``
- ``inventory_expected_missing.csv``
- ``inventory_constant_rept.csv``
- ``inventory_skipped_missing.csv``
- ``inventory_skipped_not_in_dcr.csv``
- ``inventory_unexpected.csv``
- ``sv_coverage_by_chunk.csv``
- ``product_b_vs_a_comparison.csv``
- ``compilation_summary.txt``
- ``figures/monthly_climatology_by_category.png``
- ``figures/chunk_spread_by_category.png``

CLI flags
---------
- ``--skip-comparison``  Skip the Product A vs B comparison step.
- ``--skip-dss``         Skip DSS file generation.
- ``--chunks 1 2 3``     Process only specific chunks (default: all 10).
- ``--n-workers 10``     Number of parallel threads for DSS writing (default: 10).
"""

import os
import sys
import time
import shutil
import argparse
import subprocess
import atexit
import warnings
import functools
import numpy as np
import pandas as pd
from pathlib import Path
from collections import OrderedDict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_generated_dir, get_module_generated_dir, get_inventory_dir

warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="All-NaN slice encountered")


# ======================================================================
# Configuration
# ======================================================================
_base = get_base_dir()
_gen  = get_module_generated_dir("postprocessing/sv_compile")

BASELINE_DSS   = _base / "CalSim3" / "__calsim_sv_default__.dss"
OUTPUT_DIR     = _gen / "product_b_compilation"
COMPILED_DIR   = OUTPUT_DIR / "_product_b_compiled_sv"
COMPILED_CSV   = OUTPUT_DIR / "compiled_input_files"

# Product A compiled DSS (for comparison)
PRODUCT_A_DSS  = _gen / "product_a_validation" / "ProductA_Historical_Validation_SV.dss"

INVENTORY_XLSX = get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx"

DSS_PATTERN = "/*/*/*/*/1MON/*"

# Product B canonical period: 100 WY per chunk  (Oct 1921 - Sep 2021)
N_CHUNKS     = 10
CHUNK_TAGS   = [f"n{i:02d}" for i in range(1, N_CHUNKS + 1)]
PB_START_YM  = (1921, 10)   # first data month
PB_END_YM    = (2021,  9)   # last data month

# Product A overwrite window (for comparison statistics)
PA_START = pd.Timestamp(1971, 10, 31)
PA_END   = pd.Timestamp(2018,  9, 30)


# -- Junction helper for long DSS paths -----------------------------------
_REPO_ROOT  = Path(__file__).resolve().parents[2]
_DSS_LINK   = _REPO_ROOT / "_dss_link"
_PATH_LIMIT = 200


def _create_junction(target_dir):
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(_DSS_LINK), str(target_dir)],
        check=True, capture_output=True,
    )


def _remove_junction():
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)


def _dss_str(path):
    s = str(path)
    if len(s) <= _PATH_LIMIT:
        return s
    try:
        rel = Path(path).relative_to(Path(path).parent)
        return str(_DSS_LINK / rel)
    except ValueError:
        return s


# -- CLI arguments ---------------------------------------------------------
_parser = argparse.ArgumentParser(
    description="Product B (1000-year stochastic) -- CSV Compilation",
)
_parser.add_argument(
    "--skip-comparison", action="store_true", default=False,
    help="Skip the Product A vs B comparison step.",
)
_parser.add_argument(
    "--skip-dss", action="store_true", default=False,
    help="Skip DSS file generation (CSV only).",
)
_parser.add_argument(
    "--chunks", nargs="+", type=int,
    default=list(range(1, N_CHUNKS + 1)),
    help="Chunk numbers to compile, 1-10 (default: all).",
)
_parser.add_argument(
    "--n-workers", type=int, default=10,
    help="Number of parallel threads for DSS writing (default: 10).",
)
_parser.add_argument(
    "--summary-figures", action="store_true", default=False,
    help="Regenerate only the summary figures from a previous comparison CSV. "
         "Skips Steps 1-6, 8, and monthly climatology plots.",
)
CLI_ARGS = _parser.parse_args()

# Validate chunk numbers
for _c in CLI_ARGS.chunks:
    if _c < 1 or _c > N_CHUNKS:
        sys.exit(f"ERROR: Chunk number {_c} out of range (1-{N_CHUNKS})")

ACTIVE_CHUNKS = sorted(CLI_ARGS.chunks)
ACTIVE_TAGS   = [f"n{c:02d}" for c in ACTIVE_CHUNKS]


# ======================================================================
# Module definitions
# ======================================================================
_gen_dir = get_generated_dir()

# label -> (path to _product_b_final dir, inventory Input_Category, reader_type)
# reader_type: "standard" = Part B, Part C, Year, Month, Value
#              "rim_inflow" = CalSim, Matched_inflow, Year, Month, ..., qmap_postAdj
MODULE_CONFIG_B = OrderedDict([
    ("calsimhydro", (
        _gen_dir / "mod_hydrology/calsimhydro/output/_4_postprocess_product_b/_product_b_final",
        "CalSimHydro", "standard")),
    ("calsimhydro_ee", (
        _gen_dir / "mod_hydrology/calsimhydro_ee/output/_3_postprocess_product_b/_product_b_final",
        "CalSimHydroEE", "standard")),
    ("evaporation", (
        _gen_dir / "mod_reservoir/evaporation/output/_2_run_reservoir_evap/_product_b_final",
        "Reservoir Evaporation", "standard")),
    ("rim_inflow", (
        _gen_dir / "mod_hydrology/rim_inflow/output/_3_qmap_product_b",
        "Rim Inflow", "rim_inflow")),
    ("delta_channel_depletion", (
        _gen_dir / "mod_hydrology/delta_channel_depletion/output/_3_postprocess_product_b/_product_b_final",
        "Delta Channel Depletion", "standard")),
    ("small_watersheds", (
        _gen_dir / "mod_hydrology/small_watersheds/output/_3_postprocess_product_b/_product_b_final",
        "Small Watersheds", "standard")),
    ("storage_curves", (
        _gen_dir / "mod_reservoir/storage_curves/output/_product_b_final",
        "Reservoir Storage Curves", "standard")),
    ("instream_flows", (
        _gen_dir / "mod_other/instream_flows/output/_product_b_final",
        "Instream Flows", "standard")),
    ("tulare_gw_terms", (
        _gen_dir / "mod_hydrology/tulare_gw_terms/output/_1_wyt_monthlyavg/_product_b_final",
        "Tulare Groundwater Terms", "standard")),
    ("climate", (
        _gen_dir / "mod_forcing/climate/output/_product_b_final",
        "Climate", "standard")),
    ("miscellaneous", (
        _gen_dir / "mod_other/miscellaneous/output/_product_b_final",
        "Other", "standard")),
    ("upper_watershed", (
        _gen_dir / "mod_other/upper_watershed/output/_product_b_final",
        "Upper Watershed Modules", "standard")),
    ("closure_terms", (
        _gen_dir / "mod_other/closure_terms/output/_product_b_final",
        "Closure Terms", "standard")),
    ("day_volume_fractions", (
        _gen_dir / "mod_other/day_volume_fractions/output/_product_b_final",
        "Day-Volume Fraction", "standard")),
])

# Inventory categories that do NOT have Product B modules
CATEGORIES_WITHOUT_PRODUCT_B = {"Salinity"}


# ======================================================================
# Helpers
# ======================================================================
def excel_to_part(name: str) -> str:
    return str(name).upper().replace(" ", "_")


def safe_write_ts(dss_out, pathname: str, ts_obj):
    """Write a TimeSeriesContainer, tolerating API differences."""
    ts_obj.pathname = pathname
    if hasattr(dss_out, "put_ts"):
        dss_out.put_ts(ts_obj)
    elif hasattr(dss_out, "write_ts"):
        dss_out.write_ts(ts_obj)


def ym_to_eom(year: int, month: int) -> pd.Timestamp:
    return pd.Timestamp(year=int(year), month=int(month), day=1).to_period("M").to_timestamp("M")


def dss_eom(ts_pytimes) -> pd.DatetimeIndex:
    return (pd.to_datetime(ts_pytimes).to_period("M") - 1).to_timestamp("M")


def path_key(pathname: str) -> tuple:
    parts = pathname.strip("/").split("/")
    return (parts[1].upper(), parts[2].upper())


@functools.lru_cache(maxsize=1)
def read_master_inventory() -> pd.DataFrame:
    """Read the MASTER sheet from the inventory workbook."""
    import openpyxl
    try:
        wb = openpyxl.load_workbook(str(INVENTORY_XLSX), read_only=True, data_only=True)
    except PermissionError:
        sys.exit(
            f"ERROR: Cannot read the master inventory -- the file may be open in Excel.\n"
            f"  Close the file and re-run the script:\n"
            f"  {INVENTORY_XLSX}"
        )
    ws = wb["MASTER"]
    rows = list(ws.iter_rows(min_row=3, max_row=ws.max_row, values_only=True))
    wb.close()
    records = []
    for r in rows:
        b, c, cat = r[2], r[3], r[8]
        if b and c and cat:
            records.append({
                "Part_B":          str(b).upper().replace(" ", "_"),
                "Part_C":          str(c).upper().replace(" ", "_"),
                "Input_Category":  str(cat).strip(),
                "Missing":         str(r[10]).strip().upper() == "T",
                "Constant_Rept":   str(r[11]).strip().upper() == "T",
                "Used_in_DCR":     str(r[12]).strip().upper() != "F",
            })
    return pd.DataFrame(records)


@functools.lru_cache(maxsize=1)
def _inventory_partc_map() -> dict:
    """Build Part_B -> Part_C lookup from the inventory (for rim_inflow normalization)."""
    inv = read_master_inventory()
    m = {}
    for _, r in inv.iterrows():
        m[r["Part_B"]] = r["Part_C"]
    return m


# ======================================================================
# Step 0: Detect chunk tag from filename
# ======================================================================
def detect_chunk_tag(filename: str) -> str:
    """Extract chunk tag (n01-n10) from a CSV filename.

    Tries several patterns used across modules.
    Returns empty string if no chunk tag found.
    """
    import re
    name = filename.lower()
    # Match _n01, _n02 .. _n10
    m = re.search(r'_n(\d{2})(?:\.|_|$)', name)
    if m:
        num = int(m.group(1))
        if 1 <= num <= N_CHUNKS:
            return f"n{num:02d}"
    return ""


# ======================================================================
# Step 1: Read & normalize module CSVs
# ======================================================================
def read_standard_csv(csv_path: Path) -> pd.DataFrame:
    """Read a standard SV CSV (Part B, Part C, Year, Month, Value)."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    required = {"Part B", "Part C", "Year", "Month", "Value"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        print(f"    WARNING: {csv_path.name} missing columns {sorted(missing)} -- skipping")
        return pd.DataFrame(columns=["Part B", "Part C", "Year", "Month", "Value"])
    df["Part B"] = df["Part B"].apply(excel_to_part)
    df["Part C"] = df["Part C"].apply(excel_to_part)
    df["Year"]   = df["Year"].astype(int)
    df["Month"]  = df["Month"].astype(int)
    df["Value"]  = pd.to_numeric(df["Value"], errors="coerce")
    return df[["Part B", "Part C", "Year", "Month", "Value"]].dropna(subset=["Value"])


def read_rim_inflow_csv(csv_path: Path) -> pd.DataFrame:
    """Read a rim_inflow non-standard CSV and normalise to standard format.

    Input columns:  CalSim, Matched_inflow, Year, Month, vic_val, qmap_preAdj, qmap_postAdj
    Output columns: Part B, Part C, Year, Month, Value
    """
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    if "CalSim" not in df.columns or "qmap_postAdj" not in df.columns:
        # Try case-insensitive lookup
        col_map = {c.lower(): c for c in df.columns}
        if "calsim" not in col_map or "qmap_postadj" not in col_map:
            print(f"    WARNING: {csv_path.name} missing CalSim/qmap_postAdj columns -- skipping")
            return pd.DataFrame(columns=["Part B", "Part C", "Year", "Month", "Value"])
        calsim_col = col_map["calsim"]
        value_col  = col_map["qmap_postadj"]
    else:
        calsim_col = "CalSim"
        value_col  = "qmap_postAdj"

    partc_map = _inventory_partc_map()

    out = pd.DataFrame()
    out["Part B"] = df[calsim_col].apply(excel_to_part)
    out["Part C"] = out["Part B"].map(partc_map).fillna("FLOW-INFLOW")
    out["Year"]   = df["Year"].astype(int)
    out["Month"]  = df["Month"].astype(int)
    out["Value"]  = pd.to_numeric(df[value_col], errors="coerce")
    return out[["Part B", "Part C", "Year", "Month", "Value"]].dropna(subset=["Value"])


def scan_module_csvs(label, src_dir, reader_type):
    """Scan a module directory for CSVs, group by chunk tag.

    Returns:
        chunk_data: dict  chunk_tag -> list[pd.DataFrame]
        n_files: int
        n_svs: set of (Part B, Part C)
        source_paths: list[Path]  -- original CSV file paths (for copying)
    """
    chunk_data = {tag: [] for tag in CHUNK_TAGS}
    n_files = 0
    all_svs = set()
    source_paths = []

    if not src_dir.is_dir():
        return chunk_data, 0, set(), []

    csv_files = sorted(src_dir.glob("*.csv"))
    reader_fn = read_rim_inflow_csv if reader_type == "rim_inflow" else read_standard_csv

    for csv_path in csv_files:
        tag = detect_chunk_tag(csv_path.name)
        if not tag:
            continue  # not a chunk CSV (could be a summary or report file)
        if tag not in chunk_data:
            continue

        df = reader_fn(csv_path)
        if df.empty:
            continue

        chunk_data[tag].append(df)
        n_files += 1
        source_paths.append(csv_path)
        for b, c in zip(df["Part B"], df["Part C"]):
            all_svs.add((b, c))

    return chunk_data, n_files, all_svs, source_paths


# ======================================================================
# Step 2: Constant/Rept auto-fill from baseline
# ======================================================================
def _extract_wy_pattern(ser_clean):
    """Extract a 12-month repeating pattern from non-missing baseline data."""
    WY_MONTHS = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    wy = ser_clean.index.year + (ser_clean.index.month >= 10).astype(int)
    for water_year in sorted(wy.unique(), reverse=True):
        wy_slice = ser_clean[wy == water_year]
        months_present = set(wy_slice.index.month)
        if months_present == set(WY_MONTHS):
            pattern = {}
            for dt, val in zip(wy_slice.index, wy_slice.values):
                pattern[dt.month] = val
            return pattern, True
    pattern = {}
    for m in WY_MONTHS:
        month_vals = ser_clean[ser_clean.index.month == m]
        if not month_vals.empty:
            pattern[m] = month_vals.iloc[-1]
    return pattern, len(pattern) == 12


def build_constant_rept_rows(dss_in, baseline_bucket, part_key):
    """Build 100 WY of constant/rept values from the baseline pattern.

    Returns a DataFrame with Part B, Part C, Year, Month, Value
    covering Oct 1921 - Sep 2021 (1200 months).
    """
    if part_key not in baseline_bucket:
        return pd.DataFrame()

    from pydsstools.heclib.dss import HecDss

    # Merge all D-part blocks into one unified series
    merged = {}
    for pathname in baseline_bucket[part_key]:
        ts = dss_in.read_ts(pathname, trim_missing=False)
        eom = dss_eom(ts.pytimes)
        eom_pd = pd.DatetimeIndex(eom)
        ts_vals = np.array(ts.values, dtype=float)
        for i, dt in enumerate(eom_pd):
            if ts_vals[i] > -900:
                merged[dt] = ts_vals[i]

    if not merged:
        return pd.DataFrame()

    merged_dates = sorted(merged.keys())
    merged_ser = pd.Series(
        [merged[d] for d in merged_dates],
        index=pd.DatetimeIndex(merged_dates),
    )
    pattern, complete = _extract_wy_pattern(merged_ser)

    if not complete:
        missing_months = sorted(set(range(1, 13)) - set(pattern.keys()))
        month_names = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",
                       7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
        missing_str = ", ".join(month_names[m] for m in missing_months)
        print(f"  WARNING: Constant/Rept pattern for {part_key} is missing "
              f"months: {missing_str}")

    # Tile pattern across the Product B window
    rows = []
    partb, partc = part_key
    start = pd.Timestamp(PB_START_YM[0], PB_START_YM[1], 1)
    end = pd.Timestamp(PB_END_YM[0], PB_END_YM[1], 1)
    months = pd.date_range(start, end, freq="MS")
    for dt in months:
        m = dt.month
        if m in pattern:
            rows.append({
                "Part B": partb,
                "Part C": partc,
                "Year": dt.year,
                "Month": m,
                "Value": pattern[m],
            })

    return pd.DataFrame(rows)


# ======================================================================
# Step 3: Read Product A DSS for comparison
# ======================================================================
def read_product_a_monthly_means(product_a_dss: Path, baseline_bucket: dict,
                                 keys_to_read: set) -> dict:
    """Read Product A compiled DSS and compute monthly means per (Part B, Part C).

    Returns dict: (Part_B, Part_C) -> {month: mean_value}
    """
    from pydsstools.heclib.dss import HecDss

    use_junction = len(str(product_a_dss)) > _PATH_LIMIT
    if use_junction:
        _create_junction(product_a_dss.parent)
        atexit.register(_remove_junction)
        dss_path = str(_DSS_LINK / product_a_dss.name)
    else:
        dss_path = str(product_a_dss)

    result = {}
    with HecDss.Open(dss_path, version=6, catalog_flag=True) as dss:
        pa_paths = dss.getPathnameList(DSS_PATTERN)
        pa_bucket = {}
        for p in pa_paths:
            k = path_key(p)
            pa_bucket.setdefault(k, []).append(p)

        for pk in sorted(keys_to_read):
            if pk not in pa_bucket:
                continue

            merged = {}
            for pathname in pa_bucket[pk]:
                try:
                    ts = dss.read_ts(pathname, trim_missing=False)
                except Exception:
                    continue
                eom = dss_eom(ts.pytimes)
                vals = np.array(ts.values, dtype=float)
                for i, dt in enumerate(eom):
                    if vals[i] > -900 and PA_START <= dt <= PA_END:
                        merged[dt] = vals[i]

            if not merged:
                continue

            ser = pd.Series(merged)
            monthly_means = {}
            for m in range(1, 13):
                mm = ser[ser.index.month == m]
                if not mm.empty:
                    monthly_means[m] = mm.mean()
            result[pk] = monthly_means

    if use_junction:
        _remove_junction()

    return result


# ======================================================================
# MAIN EXECUTION
# ======================================================================
print("=" * 72)
print("  Product B (1000-year stochastic) -- CSV Compilation")
print("=" * 72)

if not BASELINE_DSS.exists():
    sys.exit(f"ERROR: Baseline DSS not found:\n  {BASELINE_DSS}")
if not INVENTORY_XLSX.exists():
    sys.exit(f"ERROR: Master inventory not found:\n  {INVENTORY_XLSX}")

# Prompt to close Excel if locked
while True:
    try:
        with open(INVENTORY_XLSX, "r+b"):
            pass
        break
    except PermissionError:
        print(
            f"\nWARNING: The master inventory appears to be open in Excel.\n"
            f"  {INVENTORY_XLSX}\n"
            f"  Close the file, then press Enter to continue (or Ctrl+C to abort)..."
        )
        try:
            input()
        except KeyboardInterrupt:
            sys.exit("\nAborted.")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if not CLI_ARGS.skip_dss:
    COMPILED_DIR.mkdir(parents=True, exist_ok=True)

print(f"  Active chunks: {', '.join(ACTIVE_TAGS)}")
print(f"  Output: {OUTPUT_DIR}")
print()

# ==================================================================
# FAST PATH: --summary-figures (regenerate figures from previous run)
# ==================================================================
if CLI_ARGS.summary_figures:
    print("--- Running in --summary-figures mode (figures only) ---")
    print()

    _cmp_csv = OUTPUT_DIR / "product_b_vs_a_comparison.csv"
    if not _cmp_csv.exists():
        sys.exit(f"ERROR: Comparison CSV not found from a previous run:\n  {_cmp_csv}")

    cmp_df = pd.read_csv(_cmp_csv)
    print(f"  Loaded {_cmp_csv.name} ({len(cmp_df):,} rows)")

    all_compiled_svs = set(
        zip(cmp_df["Part_B"], cmp_df["Part_C"])
    )

    # Catalog baseline DSS for unit extraction
    from pydsstools.heclib.dss import HecDss
    with HecDss.Open(str(BASELINE_DSS), version=6, catalog_flag=True) as _dss_b:
        _bp = _dss_b.getPathnameList(DSS_PATTERN)
    baseline_bucket = {}
    for p in _bp:
        k = path_key(p)
        baseline_bucket.setdefault(k, []).append(p)

    # No baseline_ts_cache in this mode
    baseline_ts_cache = {}

    # Jump into the figure generation code (same as Step 7 figures)
    print("  Generating summary figures ...")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _FS = 7
        plt.rcParams.update({
            "font.size": _FS, "axes.titlesize": _FS,
            "axes.labelsize": _FS, "xtick.labelsize": _FS,
            "ytick.labelsize": _FS, "legend.fontsize": _FS,
            "figure.dpi": 300, "savefig.dpi": 300,
            "figure.facecolor": "white",
        })

        fig_dir = OUTPUT_DIR / "figures"
        fig_dir.mkdir(exist_ok=True)

        # -- Extract SV units from baseline DSS --
        units_map = {}
        _missing_unit_keys = all_compiled_svs
        with HecDss.Open(str(BASELINE_DSS), version=6) as _dss_u:
            for _pk in sorted(_missing_unit_keys):
                if _pk not in baseline_bucket:
                    continue
                try:
                    _ts_u = _dss_u.read_ts(
                        baseline_bucket[_pk][0], trim_missing=False
                    )
                    units_map[_pk] = _ts_u.units
                except Exception:
                    units_map[_pk] = "UNKNOWN"
        print(f"  Extracted units for {len(units_map):,} SVs")

        # -- Aggregate comparison to mean-annual values --
        _SUM_UNITS = {"TAF", "IN", "INCHES"}
        cats_present = sorted(cmp_df["Input_Category"].dropna().unique())

        annual_rows = []
        for (b, c), grp in cmp_df.groupby(["Part_B", "Part_C"]):
            unit = units_map.get((b, c), "UNKNOWN")
            cat = grp["Input_Category"].iloc[0]
            use_sum = unit.upper() in _SUM_UNITS
            pa_vals = grp["Product_A_mean"].values
            pa_ann = float(np.nansum(pa_vals) if use_sum
                           else np.nanmean(pa_vals))

            row = {"Part_B": b, "Part_C": c, "Units": unit,
                   "Input_Category": cat, "PA_annual": pa_ann}

            for tag in ACTIVE_TAGS:
                col = f"{tag}_mean"
                if col not in grp.columns:
                    continue
                ch_vals = grp[col].values
                ch_ann = float(np.nansum(ch_vals) if use_sum
                               else np.nanmean(ch_vals))
                row[f"{tag}_annual"] = ch_ann
                if (np.isfinite(pa_ann) and abs(pa_ann) > 1e-6
                        and np.isfinite(ch_ann)):
                    row[f"{tag}_pct_diff"] = (
                        (ch_ann - pa_ann) / abs(pa_ann) * 100.0
                    )
                    row[f"{tag}_abs_diff"] = ch_ann - pa_ann
                else:
                    row[f"{tag}_pct_diff"] = np.nan
                    row[f"{tag}_abs_diff"] = np.nan

            annual_rows.append(row)

        annual_df = pd.DataFrame(annual_rows)

        # -- Per-category chunk spread (one figure per category) --
        spread_dir = fig_dir / "chunk_spread_by_category"
        spread_dir.mkdir(exist_ok=True)

        for cat in cats_present:
            cat_df = annual_df[annual_df["Input_Category"] == cat]
            if cat_df.empty:
                continue

            unique_units = sorted(cat_df["Units"].dropna().unique())
            if not unique_units:
                unique_units = ["UNKNOWN"]
            n_unit_panels = len(unique_units)
            n_sv = len(cat_df)

            from matplotlib.gridspec import GridSpec
            n_cols_bot = max(1, n_unit_panels)
            gs = GridSpec(2, n_cols_bot, height_ratios=[1, 1])
            fig = plt.figure(figsize=(6.5, 5.0))

            # -- Top row: % diff (spans all columns) --
            ax_top = fig.add_subplot(gs[0, :])
            pct_data = []
            for tag in ACTIVE_TAGS:
                col = f"{tag}_pct_diff"
                if col in cat_df.columns:
                    pct_data.append(cat_df[col].dropna().values)
                else:
                    pct_data.append(np.array([]))

            if any(len(d) > 0 for d in pct_data):
                bp = ax_top.boxplot(
                    pct_data, vert=True, patch_artist=True, widths=0.6,
                    labels=list(ACTIVE_TAGS),
                )
                for patch in bp["boxes"]:
                    patch.set_facecolor("#5B9BD5")
                    patch.set_alpha(0.7)
                for cap in bp["caps"]:
                    cap.set_visible(False)
                for flier in bp["fliers"]:
                    flier.set(marker="o", markersize=1,
                              markerfacecolor="k", markeredgecolor="none")
            ax_top.axhline(0.0, color="red", ls="--", lw=0.6, alpha=0.5)
            ax_top.set_ylabel("Mean Annual % Diff")
            ax_top.set_title(f"{cat}  (n={n_sv} SVs)")
            ax_top.tick_params(axis="x", rotation=45)

            # -- Bottom row: abs diff (one column per unit) --
            for u_idx, unit in enumerate(unique_units):
                ax = fig.add_subplot(gs[1, u_idx])
                unit_df = cat_df[cat_df["Units"] == unit]
                n_unit_sv = len(unit_df)

                abs_data = []
                for tag in ACTIVE_TAGS:
                    col = f"{tag}_abs_diff"
                    if col in unit_df.columns:
                        abs_data.append(unit_df[col].dropna().values)
                    else:
                        abs_data.append(np.array([]))

                if any(len(d) > 0 for d in abs_data):
                    bp = ax.boxplot(
                        abs_data, vert=True, patch_artist=True, widths=0.6,
                        labels=list(ACTIVE_TAGS),
                    )
                    for patch in bp["boxes"]:
                        patch.set_facecolor("#E8A54B")
                        patch.set_alpha(0.7)
                    for cap in bp["caps"]:
                        cap.set_visible(False)
                    for flier in bp["fliers"]:
                        flier.set(marker="o", markersize=1,
                                  markerfacecolor="k", markeredgecolor="none")
                ax.axhline(0.0, color="red", ls="--", lw=0.6, alpha=0.5)
                ax.set_ylabel(f"Mean Annual Abs Diff ({unit})")
                if n_unit_panels > 1:
                    ax.set_title(f"{unit}  (n={n_unit_sv})")
                ax.tick_params(axis="x", rotation=45)

            fig.tight_layout()
            cat_safe = cat.replace(" ", "_").replace("/", "_")
            fig.savefig(
                spread_dir / f"{cat_safe}.png", bbox_inches="tight"
            )
            plt.close(fig)

        print(f"  Figures: figures/chunk_spread_by_category/ "
              f"({len(cats_present)} categories)")

    except ImportError:
        print("  WARNING: matplotlib not available, skipping figures.")

    print(f"\nDone (--summary-figures).  Output in: {OUTPUT_DIR}")
    sys.exit(0)


# ==================================================================
# STEP 1 -- Scan module directories & read CSVs
# ==================================================================
print("Step 1: Scanning module directories for Product B CSVs ...")
print("-" * 72)

t0_scan = time.time()

# chunk_tag -> module_label -> list[DataFrame]
all_chunk_data = {tag: {} for tag in CHUNK_TAGS}
module_svs     = {}          # label -> set of (Part B, Part C)
module_files   = {}          # label -> int (file count)
module_src_paths = {}        # label -> list[Path] (for copying)
missing_modules = []

for label, (src_dir, _inv_cat, reader_type) in MODULE_CONFIG_B.items():
    chunk_data, n_files, svs, src_paths = scan_module_csvs(label, src_dir, reader_type)
    if n_files > 0:
        module_files[label] = n_files
        module_svs[label]   = svs
        module_src_paths[label] = src_paths
        for tag in CHUNK_TAGS:
            if chunk_data[tag]:
                all_chunk_data[tag][label] = chunk_data[tag]
        print(f"  [OK]   {label:40s}  {n_files:>4} files  |  "
              f"{len(svs):>4} unique (B,C)")
    else:
        missing_modules.append(label)
        print(f"  [SKIP] {label:40s}  (no chunk CSVs found in {src_dir})")

print("-" * 72)
print(f"  Modules found: {len(module_files)} / {len(MODULE_CONFIG_B)}")
if missing_modules:
    print(f"  Modules skipped: {', '.join(missing_modules)}")
print(f"  Scan completed in {time.time()-t0_scan:.1f}s")
print()

if not module_files:
    sys.exit("ERROR: No module CSVs found. Nothing to compile.")

# Collect all (Part B, Part C) provided by modules across all chunks
all_module_keys = set()
for svs in module_svs.values():
    all_module_keys |= svs
print(f"  Total unique (Part B, Part C) from modules: {len(all_module_keys):,}")


# -- Copy source CSVs into compiled_input_files/<module>/ --
print()
print("  Copying source CSVs into compiled_input_files/ ...")
COMPILED_CSV.mkdir(parents=True, exist_ok=True)
for label, src_paths in module_src_paths.items():
    dest_dir = COMPILED_CSV / label
    dest_dir.mkdir(parents=True, exist_ok=True)
    for csv_path in src_paths:
        shutil.copy2(csv_path, dest_dir / csv_path.name)
    print(f"    {label:40s}  -> {len(src_paths)} file(s) copied")


# ==================================================================
# STEP 2 -- Inventory cross-reference
# ==================================================================
print()
print("Step 2: Cross-referencing against master inventory ...")

inventory_df = read_master_inventory()
print(f"  Inventory rows loaded: {len(inventory_df):,}")

# Category -> module label mapping
inv_category_map = {}
for label, (_dir, inv_cat, _reader) in MODULE_CONFIG_B.items():
    inv_category_map[inv_cat] = label

# Skipped: Missing=T
inv_skipped_missing = inventory_df[inventory_df["Missing"] == True].copy()
skipped_missing_keys = set(zip(inv_skipped_missing["Part_B"], inv_skipped_missing["Part_C"]))

# Skipped: Used_in_DCR=F (and not already Missing)
inv_skipped_not_dcr = inventory_df[
    (~inventory_df["Missing"]) & (~inventory_df["Used_in_DCR"])
].copy()
skipped_not_dcr_keys = set(zip(inv_skipped_not_dcr["Part_B"], inv_skipped_not_dcr["Part_C"]))

# Constant/Rept SVs
inv_const_rept_all = inventory_df[
    (inventory_df["Constant_Rept"] == True)
    & (~inventory_df["Missing"])
    & (inventory_df["Used_in_DCR"])
].copy()
const_rept_all_keys = set(zip(inv_const_rept_all["Part_B"], inv_const_rept_all["Part_C"]))

# Active SVs: not missing, used in DCR, not constant/rept,
# in a category with a module (or a known no-module category)
expected_svs = inventory_df[
    (~inventory_df["Missing"])
    & (inventory_df["Used_in_DCR"])
    & (~inventory_df["Constant_Rept"])
    & (inventory_df["Input_Category"].isin(inv_category_map.keys()))
].copy()
expected_svs["Module"] = expected_svs["Input_Category"].map(inv_category_map).fillna("(no module)")
expected_keys = set(zip(expected_svs["Part_B"], expected_svs["Part_C"]))

# Which expected SVs are actually provided?
inv_expected_modified = expected_keys & all_module_keys
inv_expected_missing  = expected_keys - all_module_keys
# Which module SVs are unexpected (not in inventory)?
inv_unexpected = all_module_keys - expected_keys - const_rept_all_keys

print(f"  Skipped (Missing=T):           {len(skipped_missing_keys):>6,}")
print(f"  Skipped (Used_in_DCR=F):       {len(skipped_not_dcr_keys):>6,}")
print(f"  Constant/Rept (total):         {len(const_rept_all_keys):>6,}")
print(f"  Expected from modules:         {len(expected_keys):>6,}")
print(f"  Expected & provided:           {len(inv_expected_modified):>6,}")
print(f"  Expected but MISSING:          {len(inv_expected_missing):>6,}")
print(f"  Provided but NOT in inventory: {len(inv_unexpected):>6,}")
print()


# ==================================================================
# STEP 3 -- Auto-fill Constant/Rept SVs from baseline
# ==================================================================
print("Step 3: Auto-filling Constant/Rept SVs from baseline DSS ...")

# Constant/Rept keys that are NOT already provided by module CSVs
const_rept_to_fill = const_rept_all_keys - all_module_keys

# Also include Constant/Rept from categories WITHOUT modules
const_rept_other = inventory_df[
    (inventory_df["Constant_Rept"] == True)
    & (~inventory_df["Missing"])
    & (inventory_df["Used_in_DCR"])
    & (~inventory_df["Input_Category"].isin(inv_category_map.keys()))
].copy()
const_rept_to_fill |= set(zip(const_rept_other["Part_B"], const_rept_other["Part_C"]))
const_rept_to_fill -= all_module_keys

print(f"  Constant/Rept SVs to auto-fill: {len(const_rept_to_fill):,}")

from pydsstools.heclib.dss import HecDss

# Catalog baseline DSS
with HecDss.Open(str(BASELINE_DSS), version=6, catalog_flag=True) as _dss_b:
    _bp = _dss_b.getPathnameList(DSS_PATTERN)
baseline_bucket = {}
for p in _bp:
    k = path_key(p)
    baseline_bucket.setdefault(k, []).append(p)
print(f"  Baseline unique (Part B, Part C): {len(baseline_bucket):,}")

# Build constant/rept DataFrames (one per Part B/C, same for all chunks)
const_rept_frames = {}   # (Part B, Part C) -> DataFrame
const_rept_filled = set()

t0_cr = time.time()
with HecDss.Open(str(BASELINE_DSS), version=6, catalog_flag=True) as dss_in:
    for pk in sorted(const_rept_to_fill):
        df_cr = build_constant_rept_rows(dss_in, baseline_bucket, pk)
        if not df_cr.empty:
            const_rept_frames[pk] = df_cr
            const_rept_filled.add(pk)

print(f"  Successfully auto-filled: {len(const_rept_filled):,} (B,C)  ({time.time()-t0_cr:.1f}s)")
print(f"  Already provided by module CSVs: {len(const_rept_all_keys & all_module_keys):,}")
print()


# ==================================================================
# STEP 4 -- Merge per-chunk data in memory
# ==================================================================
print("Step 4: Merging per-chunk data ...")
print("-" * 72)

t0_compile = time.time()
chunk_stats = {}           # tag -> {n_rows, n_svs, modules}
chunk_sv_sets = {}         # tag -> set of (Part B, Part C)
compiled_chunks = {}       # tag -> DataFrame  (kept in memory for DSS / comparison)

for chunk_idx in ACTIVE_CHUNKS:
    tag = f"n{chunk_idx:02d}"
    t_chunk = time.time()

    frames = []

    # Module CSVs for this chunk
    modules_in_chunk = []
    if tag in all_chunk_data:
        for label, dfs in all_chunk_data[tag].items():
            for df in dfs:
                frames.append(df)
            modules_in_chunk.append(label)

    # Constant/Rept rows (same for every chunk)
    for pk, df_cr in const_rept_frames.items():
        frames.append(df_cr)

    if not frames:
        print(f"  {tag}: WARNING -- no data, skipping")
        continue

    compiled = pd.concat(frames, ignore_index=True)

    # De-duplicate: keep last occurrence for each (Part B, Part C, Year, Month)
    compiled = compiled.drop_duplicates(
        subset=["Part B", "Part C", "Year", "Month"], keep="last"
    )

    # Sort
    compiled = compiled.sort_values(
        ["Part B", "Part C", "Year", "Month"]
    ).reset_index(drop=True)

    compiled_chunks[tag] = compiled

    sv_keys = set(zip(compiled["Part B"], compiled["Part C"]))
    chunk_sv_sets[tag] = sv_keys

    chunk_stats[tag] = {
        "n_rows": len(compiled),
        "n_svs": len(sv_keys),
        "modules": modules_in_chunk,
    }

    print(f"  {tag}:  {len(compiled):>10,} rows  |  {len(sv_keys):>5,} (B,C)  |  "
          f"{len(modules_in_chunk)} modules  ({time.time()-t_chunk:.1f}s)")

print("-" * 72)
print(f"  Merge completed in {time.time()-t0_compile:.1f}s")
print()


# ==================================================================
# STEP 4b -- Write per-chunk DSS files
# ==================================================================
if not CLI_ARGS.skip_dss:
    print("Step 4b: Writing per-chunk DSS files ...")
    print("-" * 72)

    from pydsstools.core import TimeSeriesContainer
    from concurrent.futures import ThreadPoolExecutor, as_completed

    t0_dss = time.time()
    dss_chunk_paths = {}  # tag -> Path

    # -- 4b-i: Pre-build chunk lookups ---------------------------------
    print("  Building per-chunk value lookups ...")
    chunk_lookups = {}   # tag -> {(B,C): {(year,month): value}}
    all_compiled_pks = set()

    for chunk_idx in ACTIVE_CHUNKS:
        tag = f"n{chunk_idx:02d}"
        if tag not in compiled_chunks:
            continue
        df_chunk = compiled_chunks[tag]
        lookup = {}
        for (b, c), grp in df_chunk.groupby(["Part B", "Part C"]):
            ym_dict = dict(zip(zip(grp["Year"].astype(int), grp["Month"].astype(int)),
                               grp["Value"]))
            lookup[(b, c)] = ym_dict
            all_compiled_pks.add((b, c))
        chunk_lookups[tag] = lookup

    # -- 4b-ii: Cache baseline TS data (read each pathname once) -------
    print("  Caching baseline time series data ...")
    t0_cache = time.time()
    baseline_ts_cache = {}  # pathname -> dict

    with HecDss.Open(str(BASELINE_DSS), version=6, catalog_flag=True) as dss_in:
        for pk in sorted(all_compiled_pks):
            if pk not in baseline_bucket:
                continue
            for pathname in baseline_bucket[pk]:
                if pathname in baseline_ts_cache:
                    continue
                try:
                    ts = dss_in.read_ts(pathname, trim_missing=False)
                except Exception:
                    continue
                eom = dss_eom(ts.pytimes)
                eom_pd = pd.DatetimeIndex(eom)
                baseline_ts_cache[pathname] = {
                    'start_dt':   ts.pytimes[0].strftime("%d%b%Y %H:%M"),
                    'values':     np.array(ts.values, dtype=float),
                    'units':      ts.units,
                    'type':       ts.type,
                    'interval':   ts.interval,
                    'eom_years':  eom_pd.year.values.copy(),
                    'eom_months': eom_pd.month.values.copy(),
                }
    print(f"  Cached {len(baseline_ts_cache):,} baseline pathnames ({time.time()-t0_cache:.1f}s)")

    # -- 4b-iii: Prepare output files (copy baseline sequentially) -----
    use_junction = len(str(COMPILED_DIR / "ProductB_SV_n01.dss")) > _PATH_LIMIT
    if use_junction:
        _create_junction(COMPILED_DIR)

    def _get_dss_str(path):
        if use_junction:
            return str(_DSS_LINK / path.name)
        return str(path)

    for tag in sorted(chunk_lookups):
        chunk_dss = COMPILED_DIR / f"ProductB_SV_{tag}.dss"
        for f in [chunk_dss] + [chunk_dss.with_suffix(e) for e in [".dsd", ".dsk", ".dsc"]]:
            if f.exists():
                f.unlink()
        shutil.copy2(BASELINE_DSS, chunk_dss)
        for ext in [".dsd", ".dsk", ".dsc"]:
            src = BASELINE_DSS.with_suffix(ext)
            if src.exists():
                shutil.copy2(src, chunk_dss.with_suffix(ext))

    # -- 4b-iv: Worker function ----------------------------------------
    def _write_chunk(tag):
        """Overlay cached baseline with chunk values and write to DSS."""
        chunk_dss = COMPILED_DIR / f"ProductB_SV_{tag}.dss"
        dss_str = _get_dss_str(chunk_dss)
        lookup = chunk_lookups[tag]

        n_paths_written = 0
        n_svs_written = set()

        with HecDss.Open(dss_str, version=6) as dss_out:
            for pk, ym_vals in lookup.items():
                if pk not in baseline_bucket:
                    continue
                for pathname in baseline_bucket[pk]:
                    if pathname not in baseline_ts_cache:
                        continue
                    cached = baseline_ts_cache[pathname]
                    ts_vals = cached['values'].copy()

                    eom_years  = cached['eom_years']
                    eom_months = cached['eom_months']
                    modified = False
                    for i in range(len(ts_vals)):
                        v = ym_vals.get((eom_years[i], eom_months[i]))
                        if v is not None:
                            ts_vals[i] = v
                            modified = True

                    if modified:
                        tsc = TimeSeriesContainer()
                        tsc.pathname      = pathname
                        tsc.startDateTime = cached['start_dt']
                        tsc.numberValues  = len(ts_vals)
                        tsc.units         = cached['units']
                        tsc.type          = cached['type']
                        tsc.interval      = cached['interval']
                        tsc.values        = ts_vals
                        safe_write_ts(dss_out, pathname, tsc)
                        n_paths_written += 1

                n_svs_written.add(pk)

        return tag, n_paths_written, len(n_svs_written)

    # -- 4b-v: Execute (threaded or sequential) ------------------------
    n_workers = max(1, min(CLI_ARGS.n_workers, len(chunk_lookups)))
    tags_to_write = sorted(chunk_lookups)

    if n_workers > 1:
        print(f"  Writing {len(tags_to_write)} chunks with {n_workers} threads ...")
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = {
                executor.submit(_write_chunk, tag): tag
                for tag in tags_to_write
            }
            for future in as_completed(futures):
                tag, n_paths, n_svs = future.result()
                dss_chunk_paths[tag] = COMPILED_DIR / f"ProductB_SV_{tag}.dss"
                print(f"  {tag}:  {n_paths:>6,} DSS paths written  |  "
                      f"{n_svs:>5,} (B,C)")
    else:
        print(f"  Writing {len(tags_to_write)} chunks (single-threaded) ...")
        for tag in tags_to_write:
            t_one = time.time()
            tag, n_paths, n_svs = _write_chunk(tag)
            dss_chunk_paths[tag] = COMPILED_DIR / f"ProductB_SV_{tag}.dss"
            print(f"  {tag}:  {n_paths:>6,} DSS paths written  |  "
                  f"{n_svs:>5,} (B,C)  ({time.time()-t_one:.1f}s)")

    if use_junction:
        _remove_junction()

    print("-" * 72)
    print(f"  DSS compilation completed in {time.time()-t0_dss:.1f}s")
    print()
else:
    print("Step 4b: Skipped (--skip-dss)")
    print()


# ==================================================================
# STEP 5 -- SV coverage by chunk
# ==================================================================
print("Step 5: Writing SV coverage diagnostics ...")

# Build a DataFrame showing which SVs appear in which chunks
all_compiled_svs = set()
for sv_set in chunk_sv_sets.values():
    all_compiled_svs |= sv_set

coverage_rows = []
for pk in sorted(all_compiled_svs):
    row = {"Part_B": pk[0], "Part_C": pk[1]}
    for tag in ACTIVE_TAGS:
        row[tag] = pk in chunk_sv_sets.get(tag, set())
    # Source module
    source_mod = "constant_rept" if pk in const_rept_filled else "unknown"
    for label, svs in module_svs.items():
        if pk in svs:
            source_mod = label
            break
    row["Source_Module"] = source_mod
    coverage_rows.append(row)

coverage_df = pd.DataFrame(coverage_rows)
# Flag any SVs that are not in ALL active chunks
bool_cols = [c for c in ACTIVE_TAGS if c in coverage_df.columns]
if bool_cols:
    coverage_df["All_Chunks"] = coverage_df[bool_cols].all(axis=1)

fp = OUTPUT_DIR / "sv_coverage_by_chunk.csv"
coverage_df.to_csv(fp, index=False)
incomplete = coverage_df[~coverage_df.get("All_Chunks", True)].shape[0]
print(f"  {fp.name:45s}  {len(coverage_df):>6,} SVs")
if incomplete > 0:
    print(f"  WARNING: {incomplete} SVs are missing from at least one chunk!")
print()


# ==================================================================
# STEP 6 -- Inventory diagnostic CSVs
# ==================================================================
print("Step 6: Writing inventory diagnostics ...")

# inventory_expected_modified.csv
inv_mod_rows = expected_svs[
    expected_svs.apply(lambda r: (r["Part_B"], r["Part_C"]) in inv_expected_modified, axis=1)
].copy()
inv_mod_rows = inv_mod_rows.sort_values(["Module", "Part_B", "Part_C"]).reset_index(drop=True)
fp = OUTPUT_DIR / "inventory_expected_modified.csv"
inv_mod_rows.to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_mod_rows):>6,} records")

# inventory_expected_missing.csv
inv_miss_rows = expected_svs[
    expected_svs.apply(lambda r: (r["Part_B"], r["Part_C"]) in inv_expected_missing, axis=1)
].copy()
inv_miss_rows = inv_miss_rows.sort_values(["Module", "Part_B", "Part_C"]).reset_index(drop=True)
fp = OUTPUT_DIR / "inventory_expected_missing.csv"
inv_miss_rows.to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_miss_rows):>6,} records")

# inventory_constant_rept.csv
inv_cr_rows = inv_const_rept_all.copy()
inv_cr_rows["Auto_Filled"] = inv_cr_rows.apply(
    lambda r: (r["Part_B"], r["Part_C"]) in const_rept_filled, axis=1
)
inv_cr_rows["From_CSV"] = inv_cr_rows.apply(
    lambda r: (r["Part_B"], r["Part_C"]) in all_module_keys, axis=1
)
inv_cr_rows = inv_cr_rows.sort_values(["Input_Category", "Part_B", "Part_C"]).reset_index(drop=True)
fp = OUTPUT_DIR / "inventory_constant_rept.csv"
inv_cr_rows.to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_cr_rows):>6,} records")

# inventory_skipped_missing.csv
fp = OUTPUT_DIR / "inventory_skipped_missing.csv"
inv_skipped_missing.sort_values(["Input_Category", "Part_B", "Part_C"]).reset_index(
    drop=True
).to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_skipped_missing):>6,} records")

# inventory_skipped_not_in_dcr.csv
fp = OUTPUT_DIR / "inventory_skipped_not_in_dcr.csv"
inv_skipped_not_dcr.sort_values(["Input_Category", "Part_B", "Part_C"]).reset_index(
    drop=True
).to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_skipped_not_dcr):>6,} records")

# inventory_unexpected.csv
inv_unexp_rows = []
for mk in sorted(inv_unexpected):
    source = "unknown"
    for label, svs in module_svs.items():
        if mk in svs:
            source = label
            break
    inv_unexp_rows.append({"Part_B": mk[0], "Part_C": mk[1], "Module": source})
inv_unexp_df = pd.DataFrame(inv_unexp_rows)
fp = OUTPUT_DIR / "inventory_unexpected.csv"
inv_unexp_df.to_csv(fp, index=False)
print(f"  {fp.name:45s}  {len(inv_unexp_df):>6,} records")
print()


# ==================================================================
# STEP 7 -- Product A vs Product B comparison
# ==================================================================
if not CLI_ARGS.skip_comparison:
    print("Step 7: Comparing Product B chunks against Product A ...")
    t0_cmp = time.time()

    if not PRODUCT_A_DSS.exists():
        print(f"  WARNING: Product A DSS not found, skipping comparison.")
        print(f"    Expected: {PRODUCT_A_DSS}")
    else:
        # Read Product A monthly means for all compiled SVs
        print(f"  Reading Product A DSS ({PRODUCT_A_DSS.name}) ...")
        pa_means = read_product_a_monthly_means(
            PRODUCT_A_DSS, baseline_bucket, all_compiled_svs
        )
        print(f"  Product A: {len(pa_means):,} (B,C) with data in overwrite window")

        # Compute Product B chunk monthly means
        print("  Computing Product B chunk monthly means ...")

        # Compute monthly means per (Part B, Part C) from in-memory data.
        cmp_rows = []
        pb_chunk_means = {}  # tag -> {(B,C): {month: mean}}

        for tag in ACTIVE_TAGS:
            if tag not in compiled_chunks:
                pb_chunk_means[tag] = {}
                continue

            df_chunk = compiled_chunks[tag]

            tag_means = {}
            for (b, c), grp in df_chunk.groupby(["Part B", "Part C"]):
                mm = {}
                for m_val, mg in grp.groupby("Month"):
                    mm[int(m_val)] = mg["Value"].mean()
                tag_means[(b, c)] = mm

            pb_chunk_means[tag] = tag_means

        # Build comparison rows
        for pk in sorted(all_compiled_svs):
            if pk not in pa_means:
                continue

            pa_mm = pa_means[pk]

            for m in range(1, 13):
                row = {
                    "Part_B": pk[0],
                    "Part_C": pk[1],
                    "Month": m,
                    "Product_A_mean": pa_mm.get(m, np.nan),
                }

                chunk_means_for_month = []
                for tag in ACTIVE_TAGS:
                    val = pb_chunk_means.get(tag, {}).get(pk, {}).get(m, np.nan)
                    row[f"{tag}_mean"] = val
                    if np.isfinite(val):
                        chunk_means_for_month.append(val)

                if chunk_means_for_month:
                    row["chunk_median"] = np.median(chunk_means_for_month)
                    pa_val = pa_mm.get(m, np.nan)
                    if np.isfinite(pa_val) and abs(pa_val) > 1e-6:
                        row["pct_diff"] = (
                            (row["chunk_median"] - pa_val) / abs(pa_val)
                        ) * 100.0
                    else:
                        row["pct_diff"] = np.nan
                else:
                    row["chunk_median"] = np.nan
                    row["pct_diff"] = np.nan

                cmp_rows.append(row)

        cmp_df = pd.DataFrame(cmp_rows)

        # Join with inventory category
        inv = read_master_inventory()
        cat_map = {}
        for _, r in inv.iterrows():
            cat_map[(r["Part_B"], r["Part_C"])] = r["Input_Category"]
        cmp_df["Input_Category"] = cmp_df.apply(
            lambda r: cat_map.get((r["Part_B"], r["Part_C"]), "Unknown"), axis=1
        )

        fp = OUTPUT_DIR / "product_b_vs_a_comparison.csv"
        cmp_df.to_csv(fp, index=False)
        n_svs_compared = cmp_df.groupby(["Part_B", "Part_C"]).ngroups
        print(f"  {fp.name:45s}  {n_svs_compared:>6,} SVs compared")

        # -- Summary figures --
        print("  Generating comparison figures ...")
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            _FS = 7
            plt.rcParams.update({
                "font.size": _FS, "axes.titlesize": _FS,
                "axes.labelsize": _FS, "xtick.labelsize": _FS,
                "ytick.labelsize": _FS, "legend.fontsize": _FS,
                "figure.dpi": 300, "savefig.dpi": 300,
                "figure.facecolor": "white",
            })

            fig_dir = OUTPUT_DIR / "figures"
            fig_dir.mkdir(exist_ok=True)

            _MONTH_LABELS = ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar",
                             "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
            _MONTH_NUMS = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]

            # -- Extract SV units from baseline DSS --
            units_map = {}  # (Part_B, Part_C) -> unit string
            try:
                _bt_cache = baseline_ts_cache
            except NameError:
                _bt_cache = {}
            for _pn, _cached in _bt_cache.items():
                _pk = path_key(_pn)
                if _pk not in units_map:
                    units_map[_pk] = _cached["units"]
            _missing_unit_keys = all_compiled_svs - set(units_map.keys())
            if _missing_unit_keys:
                with HecDss.Open(str(BASELINE_DSS), version=6) as _dss_u:
                    for _pk in sorted(_missing_unit_keys):
                        if _pk not in baseline_bucket:
                            continue
                        try:
                            _ts_u = _dss_u.read_ts(
                                baseline_bucket[_pk][0], trim_missing=False
                            )
                            units_map[_pk] = _ts_u.units
                        except Exception:
                            units_map[_pk] = "UNKNOWN"
            print(f"  Extracted units for {len(units_map):,} SVs")

            # -- Aggregate comparison to mean-annual values --
            # Volume/depth units are summed across 12 months; rates are averaged.
            _SUM_UNITS = {"TAF", "IN", "INCHES"}
            cats_present = sorted(cmp_df["Input_Category"].dropna().unique())

            annual_rows = []
            for (b, c), grp in cmp_df.groupby(["Part_B", "Part_C"]):
                unit = units_map.get((b, c), "UNKNOWN")
                cat = grp["Input_Category"].iloc[0]
                use_sum = unit.upper() in _SUM_UNITS
                pa_vals = grp["Product_A_mean"].values
                pa_ann = float(np.nansum(pa_vals) if use_sum
                               else np.nanmean(pa_vals))

                row = {"Part_B": b, "Part_C": c, "Units": unit,
                       "Input_Category": cat, "PA_annual": pa_ann}

                for tag in ACTIVE_TAGS:
                    col = f"{tag}_mean"
                    if col not in grp.columns:
                        continue
                    ch_vals = grp[col].values
                    ch_ann = float(np.nansum(ch_vals) if use_sum
                                   else np.nanmean(ch_vals))
                    row[f"{tag}_annual"] = ch_ann
                    if (np.isfinite(pa_ann) and abs(pa_ann) > 1e-6
                            and np.isfinite(ch_ann)):
                        row[f"{tag}_pct_diff"] = (
                            (ch_ann - pa_ann) / abs(pa_ann) * 100.0
                        )
                        row[f"{tag}_abs_diff"] = ch_ann - pa_ann
                    else:
                        row[f"{tag}_pct_diff"] = np.nan
                        row[f"{tag}_abs_diff"] = np.nan

                annual_rows.append(row)

            annual_df = pd.DataFrame(annual_rows)

            # -- Fig 1: Per-category chunk spread (one figure per category) --
            spread_dir = fig_dir / "chunk_spread_by_category"
            spread_dir.mkdir(exist_ok=True)

            for cat in cats_present:
                cat_df = annual_df[annual_df["Input_Category"] == cat]
                if cat_df.empty:
                    continue

                unique_units = sorted(cat_df["Units"].dropna().unique())
                if not unique_units:
                    unique_units = ["UNKNOWN"]
                n_unit_panels = len(unique_units)
                n_sv = len(cat_df)

                # Layout: row 0 = % diff (spans all cols), row 1 = abs diff (one col per unit)
                from matplotlib.gridspec import GridSpec
                n_cols_bot = max(1, n_unit_panels)
                gs = GridSpec(2, n_cols_bot, height_ratios=[1, 1])
                fig = plt.figure(figsize=(6.5, 5.0))

                # -- Top row: mean-annual % diff (spans all columns) --
                ax_top = fig.add_subplot(gs[0, :])
                pct_data = []
                for tag in ACTIVE_TAGS:
                    col = f"{tag}_pct_diff"
                    if col in cat_df.columns:
                        pct_data.append(cat_df[col].dropna().values)
                    else:
                        pct_data.append(np.array([]))

                if any(len(d) > 0 for d in pct_data):
                    bp = ax_top.boxplot(
                        pct_data, vert=True, patch_artist=True, widths=0.6,
                        labels=list(ACTIVE_TAGS),
                    )
                    for patch in bp["boxes"]:
                        patch.set_facecolor("#5B9BD5")
                        patch.set_alpha(0.7)
                    for cap in bp["caps"]:
                        cap.set_visible(False)
                    for flier in bp["fliers"]:
                        flier.set(marker="o", markersize=1,
                                  markerfacecolor="k", markeredgecolor="none")
                ax_top.axhline(0.0, color="red", ls="--", lw=0.6, alpha=0.5)
                ax_top.set_ylabel("Mean Annual % Diff")
                ax_top.set_title(f"{cat}  (n={n_sv} SVs)")
                ax_top.tick_params(axis="x", rotation=45)

                # -- Bottom row: mean-annual abs diff (one column per unit) --
                for u_idx, unit in enumerate(unique_units):
                    ax = fig.add_subplot(gs[1, u_idx])
                    unit_df = cat_df[cat_df["Units"] == unit]
                    n_unit_sv = len(unit_df)

                    abs_data = []
                    for tag in ACTIVE_TAGS:
                        col = f"{tag}_abs_diff"
                        if col in unit_df.columns:
                            abs_data.append(unit_df[col].dropna().values)
                        else:
                            abs_data.append(np.array([]))

                    if any(len(d) > 0 for d in abs_data):
                        bp = ax.boxplot(
                            abs_data, vert=True, patch_artist=True, widths=0.6,
                            labels=list(ACTIVE_TAGS),
                        )
                        for patch in bp["boxes"]:
                            patch.set_facecolor("#E8A54B")
                            patch.set_alpha(0.7)
                        for cap in bp["caps"]:
                            cap.set_visible(False)
                        for flier in bp["fliers"]:
                            flier.set(marker="o", markersize=1,
                                      markerfacecolor="k", markeredgecolor="none")
                    ax.axhline(0.0, color="red", ls="--", lw=0.6, alpha=0.5)
                    ax.set_ylabel(f"Mean Annual Abs Diff ({unit})")
                    if n_unit_panels > 1:
                        ax.set_title(f"{unit}  (n={n_unit_sv})")
                    ax.tick_params(axis="x", rotation=45)

                fig.tight_layout()
                cat_safe = cat.replace(" ", "_").replace("/", "_")
                fig.savefig(
                    spread_dir / f"{cat_safe}.png", bbox_inches="tight"
                )
                plt.close(fig)

            print(f"  Figures: figures/chunk_spread_by_category/ "
                  f"({len(cats_present)} categories)")

            # -- Fig 2: Monthly climatology example (per-category) --
            #    For each category, pick the SV with median chunk_median,
            #    plot Product A monthly means vs Product B chunk envelope.
            if not CLI_ARGS.summary_figures:
              scatter_dir = fig_dir / "monthly_climatology"
              scatter_dir.mkdir(exist_ok=True)

              for cat in cats_present:
                scatter_dir = fig_dir / "monthly_climatology"
                scatter_dir.mkdir(exist_ok=True)

                for cat in cats_present:
                    cat_cmp = cmp_df[cmp_df["Input_Category"] == cat]
                    # Get unique SVs
                    sv_list = cat_cmp.groupby(["Part_B", "Part_C"]).ngroups
                    if sv_list == 0:
                        continue

                    # One plot per SV
                    n_plotted = 0
                    for (partb, partc), sv_cmp in cat_cmp.groupby(["Part_B", "Part_C"]):
                        sv_cmp = sv_cmp.sort_values("Month")
                        months_data = sv_cmp["Month"].values

                        fig, ax = plt.subplots(figsize=(5.0, 2.5))

                        # Product B chunks (orange envelope)
                        chunk_cols = [f"{t}_mean" for t in ACTIVE_TAGS if f"{t}_mean" in sv_cmp.columns]
                        for i, col in enumerate(chunk_cols):
                            vals = sv_cmp[col].values
                            ax.plot(months_data, vals, color="tab:orange", alpha=0.3,
                                    lw=0.8, label="Product B" if i == 0 else None)

                        # Product A (blue)
                        pa_vals = sv_cmp["Product_A_mean"].values
                        ax.plot(months_data, pa_vals, color="tab:blue", lw=1.2,
                                label="Product A")

                        ax.set_xticks(range(1, 13))
                        ax.set_xticklabels(_MONTH_LABELS)
                        ax.set_xlabel("Month")
                        ax.set_ylabel("Monthly Mean")
                        ax.set_title(f"{partb}/{partc}")
                        ax.legend(loc="best", framealpha=0.7)
                        fig.tight_layout()

                        cat_safe = cat.replace(" ", "_").replace("/", "_")
                        cat_plot_dir = scatter_dir / cat_safe
                        cat_plot_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"{partb}__{partc}.png".replace("/", "_")
                        fig.savefig(cat_plot_dir / fname, bbox_inches="tight")
                        plt.close(fig)
                        n_plotted += 1

                    print(f"    {cat}: {n_plotted} climatology plots")

        except ImportError:
            print("  WARNING: matplotlib not available, skipping figures.")

        print(f"  Comparison completed in {time.time()-t0_cmp:.1f}s")
        print()
else:
    print("Step 7: Skipped (--skip-comparison)")
    print()


# ==================================================================
# STEP 8 -- Compilation summary
# ==================================================================
print("Step 8: Writing compilation summary ...")

n_total_compiled = sum(cs["n_rows"] for cs in chunk_stats.values())
n_total_svs = len(all_compiled_svs)

lines = [
    "=" * 65,
    "  Product B (1000-year) -- Compilation Summary",
    "=" * 65,
    "",
    f"  Baseline DSS:  {BASELINE_DSS.name}",
    f"  Inventory:     {INVENTORY_XLSX.name}",
    f"  Source CSVs:   {COMPILED_CSV}",
    f"  DSS output:    {COMPILED_DIR}",
    "",
    f"  Chunks compiled: {len(chunk_stats)} / {N_CHUNKS}",
    f"  Total unique (Part B, Part C): {n_total_svs:>6,}",
    "",
    "--- Module Contributions ---",
    "",
]

for label in MODULE_CONFIG_B:
    if label in module_svs:
        n = len(module_svs[label])
        nf = module_files.get(label, 0)
        lines.append(f"    {label:40s}  {n:>5} (B,C)  |  {nf:>4} files")
    else:
        lines.append(f"    {label:40s}  (not found)")

lines += [
    "",
    "--- Constant/Rept ---",
    "",
    f"    Total Constant/Rept in inventory:    {len(const_rept_all_keys):>6,}",
    f"    Auto-filled by script:               {len(const_rept_filled):>6,}",
    f"    Already in module CSVs:              {len(const_rept_all_keys & all_module_keys):>6,}",
    "",
    "--- Per-Chunk Statistics ---",
    "",
]

for tag in ACTIVE_TAGS:
    if tag in chunk_stats:
        cs = chunk_stats[tag]
        lines.append(f"    {tag}:  {cs['n_rows']:>10,} rows  |  "
                      f"{cs['n_svs']:>5,} (B,C)  |  "
                      f"modules: {', '.join(cs['modules'][:5])}"
                      f"{'...' if len(cs['modules']) > 5 else ''}")
    else:
        lines.append(f"    {tag}:  (not compiled)")

lines += [
    "",
    "--- Inventory Flags ---",
    "",
    f"    Total inventory SVs:                 {len(inventory_df):>6,}",
    f"    Skipped -- Missing=T:                {len(skipped_missing_keys):>6,}",
    f"    Skipped -- Used_in_DCR=F:            {len(skipped_not_dcr_keys):>6,}",
    "",
    "--- Inventory Cross-Reference ---",
    "",
    f"    Expected from modules:               {len(expected_keys):>6,}",
    f"    Expected & provided:                 {len(inv_expected_modified):>6,}",
    f"    Expected but MISSING:                {len(inv_expected_missing):>6,}",
    f"    Provided but NOT in inventory:       {len(inv_unexpected):>6,}",
    "",
    "--- Categories Without Product B Modules ---",
    "",
]

for cat in sorted(CATEGORIES_WITHOUT_PRODUCT_B):
    cnt_active = len(inventory_df[
        (inventory_df["Input_Category"] == cat)
        & (~inventory_df["Missing"])
        & (inventory_df["Used_in_DCR"])
        & (~inventory_df["Constant_Rept"])
    ])
    cnt_cr = len(inventory_df[
        (inventory_df["Input_Category"] == cat)
        & (inventory_df["Constant_Rept"] == True)
        & (~inventory_df["Missing"])
        & (inventory_df["Used_in_DCR"])
    ])
    cnt_total = len(inventory_df[inventory_df["Input_Category"] == cat])
    lines.append(f"    {cat:40s}  {cnt_total:>5} total  "
                 f"({cnt_cr} const/rept, {cnt_active} other)")

lines += [
    "",
    "--- Modules Skipped (no data) ---",
    "",
]
if missing_modules:
    for m in missing_modules:
        lines.append(f"    {m}")
else:
    lines.append("    (none)")

lines += [
    "",
    "--- Source CSV Modification Dates ---",
    "",
]
import datetime as _dt
for label in MODULE_CONFIG_B:
    if label not in module_src_paths:
        continue
    lines.append(f"    {label}")
    for csv_path in sorted(module_src_paths[label], key=lambda p: p.name):
        mtime = csv_path.stat().st_mtime
        mtime_str = _dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        lines.append(f"      {csv_path.name:60s}  {mtime_str}")
    lines.append("")

lines += ["=" * 65]

summary_path = OUTPUT_DIR / "compilation_summary.txt"
summary_path.write_text("\n".join(lines), encoding="utf-8")

print(f"\n  {summary_path.name}")
print()
for line in lines:
    print(line)

print(f"\nDone.  Output in: {OUTPUT_DIR}")
