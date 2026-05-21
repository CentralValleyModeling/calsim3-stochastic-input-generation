"""
Postprocess Small Watersheds Product B (1000-year stochastic) DSS Outputs
=========================================================================
Extracts monthly time series from the 10 chunked Product B DSS files
(CVSWShed_FlowContribution3pcntWBA24_2013Init_2021) and produces:
  1. Per-chunk CSVs in Part B / Part C / Year / Month / Value format
  2. Per-chunk summary CSVs with descriptive statistics by SV
  3. (--compare-a) Comparison CSV: Product A vs Product B at the PartC level

Each chunk covers 100 water years (1,200 months) using canonical dates
Oct 1921 - Sep 2021 (WY 1922-2021).

Small Watersheds DSS outputs are in AF; values are converted to TAF for
consistency with CalSim baseline expectations.

Inputs
------
- SmallWatersheds_Runs/SmallWatershed_Product_B/CVSWShed_FlowContribution3pcntWBA24_2013Init_2021_n{01..10}.DSS
- _MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx

Outputs
-------
- output/_3_postprocess_product_b/_product_b_final/_sws_productB_n{01..10}.csv
- output/_3_postprocess_product_b/_sws_productB_n{01..10}_summary.csv
- output/_3_postprocess_product_b/_sws_productB_vs_productA.csv  (--compare-a)

Usage
-----
    python _3_postprocess_product_b.py                    # all chunks
    python _3_postprocess_product_b.py --chunks 1 2 3     # specific chunks only
    python _3_postprocess_product_b.py --compare-a        # compare B vs A only
    python _3_postprocess_product_b.py --plot             # plot B vs A comparison
"""

import sys
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import get_module_generated_dir, get_inventory_dir


# -- CONSTANTS -----------------------------------------------------------------
_GEN_DIR = get_module_generated_dir("mod_hydrology/small_watersheds")
OUTPUT_DIR = _GEN_DIR / "output" / "_3_postprocess_product_b"

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

N_CHUNKS = 10           # 10 chunks of 100 water years each
MONTHS_PER_CHUNK = 1200  # 100 WY x 12 months
START_WY = 1922
END_WY = 2021

# AF to TAF conversion
AF_TO_TAF = 1.0 / 1000.0

# DSS source paths
_SWS_RUNS = _GEN_DIR / "SmallWatersheds_Runs"
_PRODUCT_B_DIR = _SWS_RUNS / "SmallWatershed_Product_B"
_PRODUCT_A_MERGED = (
    _GEN_DIR / "output" / "_2_postprocess_product_a" / "SmallWatersheds_2DSS.csv"
)

_DSS_BASE = "CVSWShed_FlowContribution3pcntWBA24_2013Init_2021"
DSS_TEMPLATE = _DSS_BASE + "_n{chunk:02d}.DSS"
CSV_TEMPLATE = "_sws_productB_n{chunk:02d}.csv"
SUMMARY_TEMPLATE = "_sws_productB_n{chunk:02d}_summary.csv"
COMPARE_A_CSV = "_sws_productB_vs_productA.csv"
COMPARE_A_PARTC_AGG_CSV = "_sws_productB_vs_productA_partC_agg.csv"


# -- INVENTORY -----------------------------------------------------------------

_df_master_cache = None


def _get_master():
    """Read and cache the master inventory DataFrame."""
    global _df_master_cache
    if _df_master_cache is None:
        _df_master_cache = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    return _df_master_cache


def load_inventory():
    """Load master inventory rows for Small Watersheds / CVSWShed DSS.

    Returns (excel_partcs dict, desired_order list).
    """
    df_master = _get_master()
    rows = df_master[
        (df_master.iloc[:, 8] == 'Small Watersheds') &
        (df_master.iloc[:, 9] == 'CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss')
    ]
    sv_names = [str(n).strip().upper() for n in rows.iloc[:, 7].tolist()]

    fmt = lambda n: n.upper().replace(" ", "_")
    excel_partcs = {fmt(n): n for n in sv_names}
    desired_order = [fmt(n) for n in sv_names]
    return excel_partcs, desired_order


# -- DSS extraction via pydsstools ---------------------------------------------

def extract_dss_data(dss_path, excel_partcs):
    """Extract monthly time series from a DSS file, filtered to inventory parts.

    Opens via utils.dss_io (Windows long-path junction lifecycle), then
    delegates to the local _read_dss loop, which is kept bespoke because
    SWS's pattern ``/*/*/*/*/1MON/*`` (no trailing slash) and sort key
    ``parts[2]`` (C-part within group) differ from the calsimhydro variant
    that dss_io.read_monthly_frame faithfully copied.
    """
    dss_path = Path(dss_path).resolve()
    print(f"    Reading DSS: {dss_path.name}")
    with dss_io.open_dss(dss_path, version=6, catalog_flag=True) as dss:
        return _read_dss(dss, excel_partcs)


def _read_dss(dss, excel_partcs):
    """Read monthly time series from an open DSS handle using pydsstools.

    Groups pathnames by Part B/C, reads each path, concatenates date ranges,
    filters -901 sentinel values, and returns a wide DataFrame.
    """
    data_dict = {}
    all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
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
        for p in sorted(plist, key=lambda x: x.strip("/").split("/")[2]):
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
    """Convert wide DataFrame to long format: Part B, Part C, Year, Month, Value.

    Small Watersheds DSS outputs are in AF; converts to TAF.
    """
    long = df.stack().reset_index()
    long.columns = ['Date', 'PartBC', 'Value']
    long['Date'] = pd.to_datetime(long['Date'])

    long[['Part B', 'Part C']] = long['PartBC'].str.split('/', expand=True, n=1)
    long['Year'] = long['Date'].dt.year
    long['Month'] = long['Date'].dt.month

    long = long.dropna(subset=['Value'])

    # AF -> TAF conversion
    long['Value'] = long['Value'] * AF_TO_TAF

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

def process_chunk(chunk_num, excel_partcs):
    """Process a single Product B chunk: extract DSS, write CSV and summary."""
    chunk_tag = f"n{chunk_num:02d}"
    dss_name = DSS_TEMPLATE.format(chunk=chunk_num)
    dss_path = _PRODUCT_B_DIR / dss_name

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

    # Convert to long format (includes AF -> TAF conversion)
    df_long = to_long_csv(df)
    if df_long.empty:
        print(f"    WARNING: No valid values in chunk {chunk_tag}")
        return False

    # Write chunk CSV
    out_dir = OUTPUT_DIR / "_product_b_final"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_name = CSV_TEMPLATE.format(chunk=chunk_num)
    csv_path = out_dir / csv_name
    df_long.to_csv(csv_path, index=False)

    n_vars = df_long.groupby(['Part B', 'Part C']).ngroups
    print(f"    CSV: {csv_name}  ({n_vars} SVs, {len(df_long):,} rows)")

    # Compute and write summary
    summary = compute_summary(df_long)
    summary_name = SUMMARY_TEMPLATE.format(chunk=chunk_num)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUTPUT_DIR / summary_name
    summary.to_csv(summary_path, index=False)

    n_overall = len(summary[summary['stat_type'] == 'overall'])
    print(f"    Summary: {summary_name}  ({n_overall} SVs)")

    return True


# -- COMPARE PRODUCT B vs PRODUCT A -------------------------------------------

STAT_NAMES = ['mean', 'median', 'std', 'min', 'max']
STAT_FUNCS = [np.mean, np.median, np.std, np.min, np.max]

GROUP_COLS = ['Part B', 'Part C']


def _monthly_stats(df, value_col, tag):
    """Compute monthly stats per Part B/Part C, returning one row per (Part B, Part C, stat, Month)."""
    frames = []
    for name, func in zip(STAT_NAMES, STAT_FUNCS):
        g = df.groupby(GROUP_COLS + ['Month'])[value_col].agg(func).reset_index()
        g = g.rename(columns={value_col: tag})
        g['stat'] = name
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def _partc_agg_monthly_stats(df, value_col, tag):
    """Sum across Part B per (Part C, row), then compute monthly stats at Part C level."""
    agg = df.groupby(['Part C', 'Year', 'Month'])[value_col].sum().reset_index()
    frames = []
    for name, func in zip(STAT_NAMES, STAT_FUNCS):
        g = agg.groupby(['Part C', 'Month'])[value_col].agg(func).reset_index()
        g = g.rename(columns={value_col: tag})
        g['stat'] = name
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def run_compare_a():
    """Compare Product B chunk monthly statistics against Product A.

    Produces a CSV with columns: Part B, Part C, stat, Month, Product_A, n01, ..., n10.
    Reads the per-chunk data CSVs to compute stats, and reads the
    Product A merged CSV to compute matching stats from the ProductA column.
    """
    print(f"\n{'=' * 60}")
    print("  Compare B vs A: SmallWatersheds")
    print(f"{'=' * 60}")

    # -- Check that all 10 Product B chunk CSVs exist --------------------------
    out_dir = OUTPUT_DIR / "_product_b_final"
    missing = []
    for i in range(1, N_CHUNKS + 1):
        csv_path = out_dir / CSV_TEMPLATE.format(chunk=i)
        if not csv_path.exists():
            missing.append(f"n{i:02d}")
    if missing:
        print(f"\nERROR: Product B chunk CSVs not found: {', '.join(missing)}")
        print("Run Product B postprocessing first:")
        print("  python _3_postprocess_product_b.py")
        sys.exit(1)

    # -- Check that Product A merged CSV exists --------------------------------
    if not _PRODUCT_A_MERGED.exists():
        print(f"\nERROR: Product A merged CSV not found: {_PRODUCT_A_MERGED}")
        print("Run Product A postprocessing first:")
        print("  python _2_postprocess_product_a.py")
        sys.exit(1)

    # -- Compute Product A stats from merged CSV -------------------------------
    prodA_df = pd.read_csv(_PRODUCT_A_MERGED)
    prodA_df['Date'] = pd.to_datetime(prodA_df['Date'])
    prodA_df['Month'] = prodA_df['Date'].dt.month
    prodA_df['Year'] = prodA_df['Date'].dt.year
    if 'PartB' in prodA_df.columns:
        prodA_df = prodA_df.rename(columns={'PartB': 'Part B'})
    if 'PartC' in prodA_df.columns:
        prodA_df = prodA_df.rename(columns={'PartC': 'Part C'})

    # Product A merged CSV stores raw DSS values in AF; convert to TAF
    # to match Product B chunk CSVs (already converted in to_long_csv)
    prodA_df['ProductA'] = prodA_df['ProductA'] * AF_TO_TAF

    result = _monthly_stats(prodA_df, 'ProductA', 'Product_A')
    n_svs = result.groupby(GROUP_COLS).ngroups
    print(f"  Product A: {n_svs} Part B/C groups")

    # -- Read each Product B chunk and compute stats ---------------------------
    for i in range(1, N_CHUNKS + 1):
        chunk_tag = f"n{i:02d}"
        csv_path = out_dir / CSV_TEMPLATE.format(chunk=i)
        chunk_df = pd.read_csv(csv_path)
        print(f"  Reading chunk {chunk_tag}: {len(chunk_df):,} rows")

        chunk_stats = _monthly_stats(chunk_df, 'Value', chunk_tag)
        result = result.merge(
            chunk_stats, on=GROUP_COLS + ['stat', 'Month'], how='outer',
        )

    # -- Reorder columns -------------------------------------------------------
    chunk_cols = [f"n{i:02d}" for i in range(1, N_CHUNKS + 1)]
    col_order = GROUP_COLS + ['stat', 'Month', 'Product_A'] + chunk_cols
    result = result[[c for c in col_order if c in result.columns]]

    result = result.sort_values(
        GROUP_COLS + ['stat', 'Month']
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    compare_path = OUTPUT_DIR / COMPARE_A_CSV
    result.to_csv(compare_path, index=False)

    n_svs = result.groupby(GROUP_COLS).ngroups
    print(f"  Written: {compare_path.name}")
    print(f"  Part B/C groups: {n_svs}  |  Rows: {len(result):,}")


def run_compare_a_partc_agg():
    """Part C aggregation: sum across Part B, then compare B vs A monthly stats.

    Produces a CSV with columns: Part C, stat, Month, Product_A, n01..n10.
    """
    print(f"\n{'=' * 60}")
    print("  Compare B vs A (Part C agg): SmallWatersheds")
    print(f"{'=' * 60}")

    out_dir = OUTPUT_DIR / "_product_b_final"
    missing = []
    for i in range(1, N_CHUNKS + 1):
        csv_path = out_dir / CSV_TEMPLATE.format(chunk=i)
        if not csv_path.exists():
            missing.append(f"n{i:02d}")
    if missing:
        print(f"\nERROR: Product B chunk CSVs not found: {', '.join(missing)}")
        sys.exit(1)

    if not _PRODUCT_A_MERGED.exists():
        print(f"\nERROR: Product A merged CSV not found: {_PRODUCT_A_MERGED}")
        sys.exit(1)

    # Product A
    prodA_df = pd.read_csv(_PRODUCT_A_MERGED)
    prodA_df['Date'] = pd.to_datetime(prodA_df['Date'])
    prodA_df['Month'] = prodA_df['Date'].dt.month
    prodA_df['Year'] = prodA_df['Date'].dt.year
    if 'PartB' in prodA_df.columns:
        prodA_df = prodA_df.rename(columns={'PartB': 'Part B'})
    if 'PartC' in prodA_df.columns:
        prodA_df = prodA_df.rename(columns={'PartC': 'Part C'})
    prodA_df['ProductA'] = prodA_df['ProductA'] * AF_TO_TAF

    result = _partc_agg_monthly_stats(prodA_df, 'ProductA', 'Product_A')
    print(f"  Product A: {result['Part C'].nunique()} Part C groups")

    # Product B chunks
    for i in range(1, N_CHUNKS + 1):
        chunk_tag = f"n{i:02d}"
        csv_path = out_dir / CSV_TEMPLATE.format(chunk=i)
        chunk_df = pd.read_csv(csv_path)
        print(f"  Reading chunk {chunk_tag}: {len(chunk_df):,} rows")
        chunk_stats = _partc_agg_monthly_stats(chunk_df, 'Value', chunk_tag)
        result = result.merge(
            chunk_stats, on=['Part C', 'stat', 'Month'], how='outer',
        )

    chunk_cols = [f"n{i:02d}" for i in range(1, N_CHUNKS + 1)]
    col_order = ['Part C', 'stat', 'Month', 'Product_A'] + chunk_cols
    result = result[[c for c in col_order if c in result.columns]]
    result = result.sort_values(['Part C', 'stat', 'Month']).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    compare_path = OUTPUT_DIR / COMPARE_A_PARTC_AGG_CSV
    result.to_csv(compare_path, index=False)
    print(f"  Written: {compare_path.name}")
    print(f"  Part C groups: {result['Part C'].nunique()}  |  Rows: {len(result):,}")


# -- PLOT PRODUCT B vs PRODUCT A -----------------------------------------------

CHUNK_COLS = [f"n{i:02d}" for i in range(1, N_CHUNKS + 1)]
MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def run_plot():
    """Generate per-(Part B, Part C, stat) line plots from the comparison CSV.

    Product A in blue, all Product B chunks in semi-transparent orange.
    Saves PNGs to _plots_product_b_vs_a/ alongside the comparison CSV.
    """
    compare_csv = OUTPUT_DIR / COMPARE_A_CSV
    if not compare_csv.exists():
        print(f"\nERROR: Comparison CSV not found: {compare_csv}")
        print("Run --compare-a first:")
        print("  python _3_postprocess_product_b.py --compare-a")
        sys.exit(1)

    matplotlib.rcParams.update({'font.size': 8})

    df = pd.read_csv(compare_csv)
    plot_dir = OUTPUT_DIR / "_plots_product_b_vs_a"
    plot_dir.mkdir(parents=True, exist_ok=True)

    groups = df.groupby(['Part B', 'Part C', 'stat'])
    print(f"  Generating {len(groups)} plots from {compare_csv.name}")

    for (partb, partc, stat), gdf in groups:
        gdf = gdf.sort_values('Month')
        months = gdf['Month'].values

        fig, ax = plt.subplots(figsize=(6.5, 3))

        # Product B chunks (orange, transparent)
        for i, col in enumerate(CHUNK_COLS):
            if col in gdf.columns:
                ax.plot(months, gdf[col].values, color='tab:orange', alpha=0.35,
                        linewidth=0.8, label='Product B' if i == 0 else None)

        # Product A (blue, on top)
        if 'Product_A' in gdf.columns:
            ax.plot(months, gdf['Product_A'].values, color='tab:blue',
                    linewidth=1.2, label='Product A')

        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTH_LABELS)
        ax.set_xlabel('Month')
        ax.set_ylabel(stat.capitalize())
        ax.set_title(f"{partb}/{partc} - {stat}")
        ax.legend(loc='best', framealpha=0.8)
        fig.tight_layout()

        stat_dir = plot_dir / stat
        stat_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{partb}_{partc}.png".replace("/", "_")
        fig.savefig(stat_dir / fname, dpi=300)
        plt.close(fig)

    print(f"  Saved {len(groups)} plots to {plot_dir}")


def run_plot_partc_agg():
    """Plot Part C aggregation comparison (sum across Part B).

    Reads the Part C agg CSV and generates per-(Part C, stat) line plots.
    """
    compare_csv = OUTPUT_DIR / COMPARE_A_PARTC_AGG_CSV
    if not compare_csv.exists():
        print(f"\nERROR: Part C agg CSV not found: {compare_csv}")
        print("Run --compare-a first.")
        sys.exit(1)

    matplotlib.rcParams.update({'font.size': 8})

    df = pd.read_csv(compare_csv)
    plot_dir = OUTPUT_DIR / "_plots_product_b_vs_a_partC_agg"
    plot_dir.mkdir(parents=True, exist_ok=True)

    groups = df.groupby(['Part C', 'stat'])
    print(f"  Generating {len(groups)} Part C agg plots")

    for (partc, stat), gdf in groups:
        gdf = gdf.sort_values('Month')
        months = gdf['Month'].values

        fig, ax = plt.subplots(figsize=(6.5, 3))
        for i, col in enumerate(CHUNK_COLS):
            if col in gdf.columns:
                ax.plot(months, gdf[col].values, color='tab:orange', alpha=0.35,
                        linewidth=0.8, label='Product B' if i == 0 else None)
        if 'Product_A' in gdf.columns:
            ax.plot(months, gdf['Product_A'].values, color='tab:blue',
                    linewidth=1.2, label='Product A')

        ax.set_xticks(range(1, 13))
        ax.set_xticklabels(MONTH_LABELS)
        ax.set_xlabel('Month')
        ax.set_ylabel(stat.capitalize())
        ax.set_title(f"{partc} (sum across Part B) - {stat}")
        ax.legend(loc='best', framealpha=0.8)
        fig.tight_layout()

        stat_dir = plot_dir / stat
        stat_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{partc}.png"
        fig.savefig(stat_dir / fname, dpi=300)
        plt.close(fig)

    print(f"  Saved {len(groups)} plots to {plot_dir}")


# -- MAIN ----------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Postprocess Small Watersheds Product B (1000-year stochastic) DSS outputs.",
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
    parser.add_argument(
        "--plot", action="store_true", default=False,
        help="Plot Product B vs Product A (requires --compare-a output)",
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
    print("SmallWatersheds -- Product B Postprocessing")
    if not args.compare_a and not args.plot:
        print(f"Chunks: {', '.join(f'n{c:02d}' for c in args.chunks)}")
        print(f"Canonical period: WY {START_WY}-{END_WY} (100 WY per chunk)")
    if args.compare_a:
        print("Mode: Compare Product B vs Product A")
    if args.plot:
        print("Mode: Plot Product B vs Product A")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 80)

    if not args.compare_a and not args.plot:
        if not _PRODUCT_B_DIR.exists():
            print(f"  WARNING: DSS directory not found: {_PRODUCT_B_DIR}")
            sys.exit(1)

        excel_partcs, _ = load_inventory()
        print(f"  Inventory: {len(excel_partcs)} SVs from master spreadsheet")

        success_count = 0
        for chunk_num in args.chunks:
            ok = process_chunk(chunk_num, excel_partcs)
            if ok:
                success_count += 1

        print(f"\n  Completed: {success_count}/{len(args.chunks)} chunks")

    if args.compare_a:
        run_compare_a()
        run_compare_a_partc_agg()

    if args.plot:
        run_plot()
        run_plot_partc_agg()

    print(f"\n{'=' * 80}")
    print("SmallWatersheds Product B postprocessing complete.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
