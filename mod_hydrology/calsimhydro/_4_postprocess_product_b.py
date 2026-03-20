#%% Postprocessing for CalSimHydro Product B (1000-year stochastic) DSS outputs.
#
# Extracts monthly time series from the 10 chunked Product B DSS files
# (CS3L2015V0Hydro_SV, RiceOutput, HydroRebalanceSJRdemands) and produces:
#   1. Per-chunk CSVs in Part B / Part C / Year / Month / Value format
#   2. Per-chunk summary CSVs with descriptive statistics by SV
#   3. (--compare-a) Comparison CSV: Product A vs Product B at the PartC level
#
# Each chunk covers 100 water years (1,200 months) using canonical dates
# Oct 1921 - Sep 2021 (WY 1922-2021).
#
# Usage:
#     python _4_postprocess_product_b.py                     # all sources, all chunks
#     python _4_postprocess_product_b.py --sources cshydro   # single source
#     python _4_postprocess_product_b.py --chunks 1 2 3      # specific chunks only
#     python _4_postprocess_product_b.py --compare-a         # compare B vs A only
#%%

import os
import sys
import argparse
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_inventory_dir


# -- CONSTANTS -----------------------------------------------------------------
_GEN_DIR = get_module_generated_dir("mod_hydrology/calsimhydro")
OUTPUT_DIR = _GEN_DIR / "output" / "_4_postprocess_product_b"

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

N_CHUNKS = 10          # 10 chunks of 100 water years each
MONTHS_PER_CHUNK = 1200  # 100 WY x 12 months
START_WY = 1922
END_WY = 2021

# DSS source definitions
_cshydro_runs = _GEN_DIR / "CalSimHydro_Runs"
_rebalance_runs = _GEN_DIR / "CalSimHydro_Rebalance_Runs"
_PRODUCT_A_DIR = _GEN_DIR / "output" / "_3_postprocess_product_a"

SOURCES = {
    "cshydro": {
        "label": "CS3L2015V0Hydro_SV",
        "inv_filter": "CS3L2015V0Hydro_SV.dss",
        "dss_dir": _cshydro_runs / "CalSimHydro_Product_B",
        "dss_template": "CS3L2015V0Hydro_SV_n{chunk:02d}.DSS",
        "csv_template": "_cshydro_sv_productB_n{chunk:02d}.csv",
        "summary_template": "_cshydro_sv_productB_n{chunk:02d}_summary.csv",
        "prodA_merged": _PRODUCT_A_DIR / "cshydro" / "calsimHydro_1972-2018_SV_DSS.csv",
        "compare_a_csv": "_cshydro_sv_productB_vs_productA.csv",
    },
    "rebalance": {
        "label": "HydroRebalanceSJRdemands",
        "inv_filter": "RebalancedSJR_AW_TW_DP.dss",
        "dss_dir": _rebalance_runs / "Rebalance_Product_B",
        "dss_template": "HydroRebalanceSJRdemands_n{chunk:02d}.DSS",
        "csv_template": "_cshydro_rebalance_productB_n{chunk:02d}.csv",
        "summary_template": "_cshydro_rebalance_productB_n{chunk:02d}_summary.csv",
        "prodA_merged": _PRODUCT_A_DIR / "rebalance" / "HydroRebalanceSJRdemands_1972-2018_DSS.csv",
        "compare_a_csv": "_cshydro_rebalance_productB_vs_productA.csv",
    },
    "rice": {
        "label": "RiceOutput",
        "inv_filter": "RiceOutput.dss",
        "dss_dir": _cshydro_runs / "CalSimHydro_Product_B",
        "dss_template": "RiceOutput_n{chunk:02d}.DSS",
        "csv_template": "_cshydro_rice_productB_n{chunk:02d}.csv",
        "summary_template": "_cshydro_rice_productB_n{chunk:02d}_summary.csv",
        "prodA_merged": _PRODUCT_A_DIR / "rice" / "RiceOutput_DSS.csv",
        "compare_a_csv": "_cshydro_rice_productB_vs_productA.csv",
    },
}


# -- HELPER FUNCTIONS ----------------------------------------------------------

_df_master_cache = None

def _get_master():
    """Read and cache the master inventory DataFrame."""
    global _df_master_cache
    if _df_master_cache is None:
        _df_master_cache = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    return _df_master_cache


def load_inventory(inv_filter):
    """Load master inventory rows for a given DSS filename.

    Returns (excel_partcs dict, desired_order list).
    """
    df_master = _get_master()
    rows = df_master[
        (df_master.iloc[:, 8] == 'CalSimHydro') &
        (df_master.iloc[:, 9] == inv_filter)
    ]
    sv_names = [str(n).strip().upper() for n in rows.iloc[:, 7].tolist()]

    fmt = lambda n: n.upper().replace(" ", "_")
    excel_partcs = {fmt(n): n for n in sv_names}
    desired_order = [fmt(n) for n in sv_names]
    return excel_partcs, desired_order


# -- Junction helper for long DSS paths ---------------------------------------
# The Fortran HEC-DSS library inside pydsstools limits path names to 256 chars.
# The data directory lives on OneDrive with a very long path, so we create a
# temporary Windows directory junction under the repo root to shorten it.

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DSS_LINK = _REPO_ROOT / "_dss_link"
_PATH_LIMIT = 200  # conservative limit vs Fortran's 256-char CNAME


def _needs_junction(dss_path):
    return len(str(dss_path)) > _PATH_LIMIT


def _create_junction(target_dir):
    """Create (or re-create) a directory junction at _DSS_LINK -> target_dir."""
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(_DSS_LINK), str(target_dir)],
        check=True, capture_output=True,
    )


def _remove_junction():
    """Remove the _DSS_LINK junction (does not affect target directory)."""
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)


# -- DSS extraction via pydsstools ---------------------------------------------

def extract_dss_data(dss_path, excel_partcs):
    """Extract monthly time series from a DSS file, filtered to inventory parts.

    Creates a directory junction for paths exceeding the Fortran 256-char
    limit, then reads all monthly pathnames and assembles a DataFrame.
    """
    dss_path = Path(dss_path).resolve()
    print(f"    Reading DSS: {dss_path.name}")

    use_junction = _needs_junction(dss_path)
    if use_junction:
        _create_junction(dss_path.parent)
        work_path = str(_DSS_LINK / dss_path.name)
        print(f"    Using junction: {work_path} ({len(work_path)} chars)")
    else:
        work_path = str(dss_path)

    try:
        return _read_dss(work_path, excel_partcs)
    finally:
        if use_junction:
            _remove_junction()


def _read_dss(dss_path, excel_partcs):
    """Read monthly time series from a DSS file using pydsstools.

    Groups pathnames by Part B/C, reads each path, concatenates date ranges,
    filters -901 sentinel values, and returns a wide DataFrame.
    """
    data_dict = {}
    with HecDss.Open(dss_path, version=6) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*/")
        print(f"    Catalog: {len(all_paths)} monthly paths found")

        # Group pathnames by Part B / Part C
        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            key = parts[1].upper() + "/" + parts[2]
            buckets.setdefault(key, []).append(p)

        # Filter to inventory SVs; fall back to all if none match
        wanted = {k: v for k, v in buckets.items() if k in excel_partcs}
        if not wanted:
            print("    No inventory match -- reading all paths")
            wanted = buckets
        else:
            print(f"    Matched {len(wanted)} of {len(excel_partcs)} inventory SVs")

        for part_BC, plist in wanted.items():
            master = {}
            for p in sorted(plist, key=lambda x: x.strip("/").split("/")[3]):
                ts = dss.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan
                # pydsstools dates are start-of-period; shift to end-of-month
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                s = pd.Series(vals, index=idx)
                master.update(s.to_dict())
            if master:
                series = pd.Series(master).sort_index()
                series.name = excel_partcs.get(part_BC, part_BC)
                data_dict[series.name] = series

    df = pd.DataFrame(data_dict).sort_index()
    print(f"    Result: {df.shape[1]} variables, {len(df)} timesteps")
    return df


# -- OUTPUT FORMATTING ---------------------------------------------------------

def to_long_csv(df):
    """Convert wide DataFrame to long format: Part B, Part C, Year, Month, Value."""
    long = df.stack().reset_index()
    long.columns = ['Date', 'PartBC', 'Value']
    long['Date'] = pd.to_datetime(long['Date'])

    long[['Part B', 'Part C']] = long['PartBC'].str.split('/', expand=True, n=1)
    long['Year'] = long['Date'].dt.year
    long['Month'] = long['Date'].dt.month

    long = long.dropna(subset=['Value'])
    long = long[['Part B', 'Part C', 'Year', 'Month', 'Value']]
    return long.sort_values(['Part B', 'Part C', 'Year', 'Month']).reset_index(drop=True)


def compute_summary(df_long):
    """Compute summary statistics from long-format DataFrame.

    Returns a DataFrame with overall and monthly stats per SV (Part B / Part C).
    """
    group_cols = ['Part B', 'Part C']

    # Overall statistics by SV
    overall = df_long.groupby(group_cols)['Value'].agg(
        ['count', 'mean', 'std', 'min', 'median', 'max']
    ).reset_index()
    overall.columns = group_cols + ['count', 'mean', 'std', 'min', 'median', 'max']
    overall['stat_type'] = 'overall'
    overall['Month'] = np.nan

    # Monthly statistics by SV
    monthly = df_long.groupby(group_cols + ['Month'])['Value'].agg(
        ['count', 'mean', 'std', 'min', 'median', 'max']
    ).reset_index()
    monthly.columns = group_cols + ['Month', 'count', 'mean', 'std', 'min', 'median', 'max']
    monthly['stat_type'] = 'monthly'

    out_cols = group_cols + ['stat_type', 'Month', 'count', 'mean', 'std', 'min', 'median', 'max']
    summary = pd.concat([overall[out_cols], monthly[out_cols]], ignore_index=True)
    return summary.sort_values(group_cols + ['stat_type', 'Month']).reset_index(drop=True)


# -- CHUNK PROCESSING ----------------------------------------------------------

def process_chunk(source_key, src, chunk_num, excel_partcs):
    """Process a single Product B chunk: extract DSS, write CSV and summary."""
    chunk_tag = f"n{chunk_num:02d}"
    dss_name = src["dss_template"].format(chunk=chunk_num)
    dss_path = src["dss_dir"] / dss_name

    print(f"\n  Chunk {chunk_tag}: {dss_name}")

    if not dss_path.exists():
        print(f"    WARNING: DSS not found, skipping: {dss_path}")
        return False

    # Extract DSS data
    df = extract_dss_data(str(dss_path), excel_partcs)
    if df.empty:
        print(f"    WARNING: No data extracted for chunk {chunk_tag}")
        return False

    print(f"    Extracted: {df.shape[1]} variables, {len(df)} timesteps")
    if len(df) > 0:
        print(f"    Date range: {df.index.min().strftime('%Y-%m')} - "
              f"{df.index.max().strftime('%Y-%m')}")

    # Convert to long format
    df_long = to_long_csv(df)
    if df_long.empty:
        print(f"    WARNING: No valid values in chunk {chunk_tag}")
        return False

    # Write chunk CSV
    out_dir = OUTPUT_DIR / "_product_b_final"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_name = src["csv_template"].format(chunk=chunk_num)
    csv_path = out_dir / csv_name
    df_long.to_csv(csv_path, index=False)

    n_vars = df_long.groupby(['Part B', 'Part C']).ngroups
    print(f"    CSV: {csv_name}  ({n_vars} SVs, {len(df_long):,} rows)")

    # Compute and write summary
    summary = compute_summary(df_long)
    summary_name = src["summary_template"].format(chunk=chunk_num)
    summary_path = out_dir / summary_name
    summary.to_csv(summary_path, index=False)

    n_overall = len(summary[summary['stat_type'] == 'overall'])
    print(f"    Summary: {summary_name}  ({n_overall} SVs)")

    return True


# -- COMPARE PRODUCT B vs PRODUCT A -------------------------------------------

STAT_NAMES = ['mean', 'median', 'std', 'min', 'max']
STAT_FUNCS = [np.mean, np.median, np.std, np.min, np.max]


def _partc_monthly_stats(df, value_col, tag):
    """Compute monthly stats at the PartC level, returning one row per (PartC, stat, Month)."""
    frames = []
    for name, func in zip(STAT_NAMES, STAT_FUNCS):
        g = df.groupby(['Part C', 'Month'])[value_col].agg(func).reset_index()
        g = g.rename(columns={value_col: tag})
        g['stat'] = name
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def run_compare_a(source_key, src):
    """Compare Product B chunk monthly statistics against Product A at the PartC level.

    Produces a CSV with columns: Part C, stat, Month, Product_A, n01, ..., n10.
    Reads the per-chunk data CSVs to compute PartC-level stats, and reads the
    Product A merged CSV to compute matching stats from the Product_A column.
    """
    print(f"\n{'=' * 60}")
    print(f"  Compare B vs A: {src['label']}")
    print(f"{'=' * 60}")

    # -- Check that all 10 Product B chunk CSVs exist --------------------------
    out_dir = OUTPUT_DIR / "_product_b_final"
    missing = []
    for i in range(1, N_CHUNKS + 1):
        csv_path = out_dir / src["csv_template"].format(chunk=i)
        if not csv_path.exists():
            missing.append(f"n{i:02d}")
    if missing:
        print(f"\nERROR: Product B chunk CSVs not found for {src['label']}: "
              f"{', '.join(missing)}")
        print("Run Product B postprocessing first:")
        print(f"  python _4_postprocess_product_b.py --sources {source_key}")
        sys.exit(1)

    # -- Check that Product A merged CSV exists --------------------------------
    prodA_path = src["prodA_merged"]
    if not prodA_path.exists():
        print(f"\nERROR: Product A merged CSV not found: {prodA_path}")
        print("Run Product A comparison postprocessing first:")
        print(f"  python _3_postprocess_product_a.py --sources {source_key}")
        sys.exit(1)

    # -- Compute Product A stats from merged CSV -------------------------------
    prodA_df = pd.read_csv(prodA_path)
    prodA_df['Date'] = pd.to_datetime(prodA_df['Date'])
    prodA_df['Month'] = prodA_df['Date'].dt.month
    # Rename PartC -> Part C for consistency with Product B CSVs
    if 'PartC' in prodA_df.columns:
        prodA_df = prodA_df.rename(columns={'PartC': 'Part C'})

    result = _partc_monthly_stats(prodA_df, 'Product_A', 'Product_A')
    print(f"  Product A: {result['Part C'].nunique()} PartC groups")

    # -- Read each Product B chunk and compute PartC-level stats ---------------
    for i in range(1, N_CHUNKS + 1):
        chunk_tag = f"n{i:02d}"
        csv_path = out_dir / src["csv_template"].format(chunk=i)
        chunk_df = pd.read_csv(csv_path)
        print(f"  Reading chunk {chunk_tag}: {len(chunk_df):,} rows")

        chunk_stats = _partc_monthly_stats(chunk_df, 'Value', chunk_tag)
        result = result.merge(
            chunk_stats, on=['Part C', 'stat', 'Month'], how='outer',
        )

    # -- Reorder columns: Part C, stat, Month, Product_A, n01..n10 -------------
    chunk_cols = [f"n{i:02d}" for i in range(1, N_CHUNKS + 1)]
    col_order = ['Part C', 'stat', 'Month', 'Product_A'] + chunk_cols
    result = result[[c for c in col_order if c in result.columns]]

    result = result.sort_values(
        ['Part C', 'stat', 'Month']
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    compare_path = OUTPUT_DIR / src["compare_a_csv"]
    result.to_csv(compare_path, index=False)

    n_partc = result['Part C'].nunique()
    print(f"  Written: {compare_path.name}")
    print(f"  PartC groups: {n_partc}  |  Rows: {len(result):,}")


# -- MAIN PROCESSING -----------------------------------------------------------

def run_source(source_key, src, chunks):
    """Process all requested chunks for a single DSS source."""
    print(f"\n{'=' * 60}")
    print(f"  Source: {src['label']}")
    print(f"  DSS dir: {src['dss_dir']}")
    print(f"  Chunks: {', '.join(f'n{c:02d}' for c in chunks)}")
    print(f"{'=' * 60}")

    if not src["dss_dir"].exists():
        print(f"  WARNING: DSS directory not found: {src['dss_dir']}")
        return

    excel_partcs, _ = load_inventory(src["inv_filter"])
    print(f"  Inventory: {len(excel_partcs)} SVs from master spreadsheet")

    success_count = 0
    for chunk_num in chunks:
        ok = process_chunk(source_key, src, chunk_num, excel_partcs)
        if ok:
            success_count += 1

    print(f"\n  Completed: {success_count}/{len(chunks)} chunks for {src['label']}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Postprocess CalSimHydro Product B (1000-year stochastic) DSS outputs.",
    )
    parser.add_argument(
        "--sources", nargs="+",
        choices=list(SOURCES.keys()), default=list(SOURCES.keys()),
        help="DSS sources to process (default: all)",
    )
    parser.add_argument(
        "--chunks", nargs="+", type=int,
        default=list(range(1, N_CHUNKS + 1)),
        help="Chunk numbers to process, 1-10 (default: all)",
    )
    parser.add_argument(
        "--compare-a", action="store_true", default=False,
        help="Compare Product B chunk stats against Product A at PartC level",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Validate chunk numbers
    for c in args.chunks:
        if c < 1 or c > N_CHUNKS:
            print(f"ERROR: Chunk number {c} out of range (1-{N_CHUNKS})")
            sys.exit(1)

    print("=" * 80)
    print("CalSimHydro -- Product B Postprocessing")
    print(f"Sources: {', '.join(args.sources)}")
    if not args.compare_a:
        print(f"Chunks: {', '.join(f'n{c:02d}' for c in args.chunks)}")
        print(f"Canonical period: WY {START_WY}-{END_WY} (100 WY per chunk)")
    if args.compare_a:
        print("Mode: Compare Product B vs Product A")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 80)

    for key in args.sources:
        src = SOURCES[key]
        if not args.compare_a:
            run_source(key, src, args.chunks)
        if args.compare_a:
            run_compare_a(key, src)

    print(f"\n{'=' * 80}")
    print("Product B postprocessing complete.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
