"""
Postprocess CalSimHydro Product A DSS Outputs
=============================================
Extracts, merges, and compares scenario time series from CalSimHydro DSS
files (CS3L2015V0Hydro_SV, RiceOutput, HydroRebalanceSJRdemands). Produces
merged-scenario CSVs + summary statistics + boxplots (comparison mode) and
Part B / Part C / Year / Month / Value validation CSVs.

Inputs
------
- [EXTERNAL] CalSimHydro Product A scenario DSS (per the SOURCES dict)
- Master inventory xlsx

Outputs
-------
- output/_3_postprocess_product_a/  (merged + summary CSVs, boxplots)
- output/_3_postprocess_product_a/_product_a_validation/  (CalSim-format CSVs)

Dependencies
------------
- utils/dss_io.py, utils/csv_io.py  (DSS read + validation conversion)
- utils/paths.py                    (data-dir resolution)

Usage
-----
    python _3_postprocess_product_a.py                     # run everything
    python _3_postprocess_product_a.py --sources cshydro   # single source
    python _3_postprocess_product_a.py --skip-compare      # validation only
    python _3_postprocess_product_a.py --skip-validate     # comparison only
"""

import os
import sys
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from functools import reduce

import seaborn as sns
import matplotlib.pyplot as plt

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import csv_io, dss_io
from utils.paths import get_module_generated_dir, get_inventory_dir


# -- CONSTANTS -----------------------------------------------------------------
_GEN_DIR = get_module_generated_dir("mod_hydrology/calsimhydro")
COMPARE_DIR = str(_GEN_DIR / "output" / "_3_postprocess_product_a")
VALIDATE_DIR = str(_GEN_DIR / "output" / "_3_postprocess_product_a" / "_product_a_validation")

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

SCENARIO_LABELS = ['Historical', 'VIC_Precip', 'QM_ET', 'Product_A']
START_WY = 1972
END_WY = 2018

# DSS source definitions
_cshydro_runs = _GEN_DIR / "CalSimHydro_Runs"
_rebalance_runs = _GEN_DIR / "CalSimHydro_Rebalance_Runs"

SOURCES = {
    "cshydro": {
        "label": "CS3L2015V0Hydro_SV",
        "inv_filter": "CS3L2015V0Hydro_SV.dss",
        "compare_dss": [
            _cshydro_runs / "CalSimHydro_Historical_1972-2018" / "CS3L2015V0Hydro_SV.dss",
            _cshydro_runs / "CalSimHydro_VICPrecip_1972-2018" / "CS3L2015V0Hydro_SV.dss",
            _cshydro_runs / "CalSimHydro_QMET_1972-2018" / "CS3L2015V0Hydro_SV.dss",
            _cshydro_runs / "CalSimHydro_Product_A" / "CS3L2015V0Hydro_SV.dss",
        ],
        "validate_dss": _cshydro_runs / "CalSimHydro_Product_A" / "CS3L2015V0Hydro_SV.dss",
        "compare_csv": "calsimHydro_1972-2018_SV_DSS.csv",
        "summary_csv": "calsimHydro_summary_statistics_by_PartC.csv",
        "validate_csv": f"_cshydro_sv_productA_{START_WY}_{END_WY}.csv",
    },
    "rebalance": {
        "label": "HydroRebalanceSJRdemands",
        "inv_filter": "RebalancedSJR_AW_TW_DP.dss",
        "compare_dss": [
            _rebalance_runs / "Rebalance_Historical_1972-2018" / "DSS" / "HydroRebalanceSJRdemands.dss",
            _rebalance_runs / "Rebalance_VICPrecip_1972-2018" / "DSS" / "HydroRebalanceSJRdemands.dss",
            _rebalance_runs / "Rebalance_QMET_1972-2018" / "DSS" / "HydroRebalanceSJRdemands.dss",
            _rebalance_runs / "Rebalance_Product_A" / "DSS" / "HydroRebalanceSJRdemands.dss",
        ],
        "validate_dss": _rebalance_runs / "Rebalance_Product_A" / "DSS" / "HydroRebalanceSJRdemands.dss",
        "compare_csv": "HydroRebalanceSJRdemands_1972-2018_DSS.csv",
        "summary_csv": "HydroRebalanceSJRdemands_summary_statistics_by_PartC.csv",
        "validate_csv": f"_cshydro_rebalance_productA_{START_WY}_{END_WY}.csv",
    },
    "rice": {
        "label": "RiceOutput",
        "inv_filter": "RiceOutput.dss",
        "compare_dss": [
            _cshydro_runs / "CalSimHydro_Historical_1972-2018" / "RiceOutput.dss",
            _cshydro_runs / "CalSimHydro_VICPrecip_1972-2018" / "RiceOutput.dss",
            _cshydro_runs / "CalSimHydro_QMET_1972-2018" / "RiceOutput.dss",
            _cshydro_runs / "CalSimHydro_Product_A" / "RiceOutput.dss",
        ],
        "validate_dss": _cshydro_runs / "CalSimHydro_Product_A" / "RiceOutput.dss",
        "compare_csv": "RiceOutput_DSS.csv",
        "summary_csv": "RiceOutput_summary_statistics_by_PartC.csv",
        "validate_csv": f"_cshydro_rice_productA_{START_WY}_{END_WY}.csv",
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


# -- DSS extraction via pydsstools ---------------------------------------------
# Long-path directory-junction handling, the catalog read loop, and the
# start-of-period -> end-of-month shift now live in utils/dss_io (shared with
# the qmap engine and the sv_compile compiler).

def extract_dss_data(dss_path, excel_partcs):
    """Extract monthly time series from a DSS file, filtered to inventory parts.

    Opens via ``utils.dss_io.open_dss`` (auto directory-junction for paths
    over the Fortran 256-char limit) and reads with ``read_monthly_frame``.
    Opened with ``catalog_flag=False`` to match this script's historical
    ``HecDss.Open(dss_path, version=6)`` call.
    """
    dss_path = Path(dss_path).resolve()
    print(f"    Reading DSS: {dss_path.name}")
    with dss_io.open_dss(dss_path, version=6, catalog_flag=False) as dss:
        return dss_io.read_monthly_frame(dss, excel_partcs)


# -- COMPARISON MODE -----------------------------------------------------------

def run_comparison(source_key, src):
    """Extract all scenarios, merge, compute stats, and generate boxplots."""
    print(f"\n{'-' * 60}")
    print(f"  Comparison: {src['label']}")
    print(f"{'-' * 60}")

    excel_partcs, desired_order = load_inventory(src["inv_filter"])
    print(f"  Inventory: {len(excel_partcs)} SVs from master spreadsheet")

    # Read all 4 scenario DSS files (Historical, VIC_Precip, QM_ET, Product_A)
    dss_data_by_file = []
    for dss_path, label in zip(src["compare_dss"], SCENARIO_LABELS):
        if not dss_path.exists():
            print(f"  WARNING: DSS not found, skipping source: {dss_path}")
            return
        print(f"  Reading scenario: {label}")
        dss_data_by_file.append(extract_dss_data(str(dss_path), excel_partcs))

    # Convert each scenario DataFrame to long format and merge on Date/PartB/PartC
    long_dfs = []
    included_labels = []
    for df, label in zip(dss_data_by_file, SCENARIO_LABELS):
        if df.empty:
            print(f"  WARNING: {label} returned no data, skipping in merge")
            continue
        long_df = df.stack().reset_index()
        long_df.columns = ['Date', 'SV_Name_PartBC', label]
        long_df[['PartB', 'PartC']] = long_df['SV_Name_PartBC'].str.split('/', expand=True, n=1)
        long_df = long_df.drop(columns='SV_Name_PartBC')
        long_df = long_df[['Date', 'PartB', 'PartC', label]]
        long_dfs.append(long_df)
        included_labels.append(label)

    if not long_dfs:
        print(f"  WARNING: No scenario data for {src['label']}, skipping comparison")
        return

    merged_df = reduce(
        lambda left, right: pd.merge(left, right, on=['Date', 'PartB', 'PartC'], how='outer'),
        long_dfs,
    )
    print(f"  Merged: {len(merged_df):,} rows across {merged_df['PartC'].nunique()} PartC groups")

    # Sort by master inventory order (preserves SV grouping from spreadsheet)
    merged_df['PartBC'] = merged_df['PartB'].str.upper() + '/' + merged_df['PartC']
    sort_map = {val: idx for idx, val in enumerate(desired_order)}
    merged_df['SortOrder'] = merged_df['PartBC'].map(sort_map)
    merged_df = merged_df.sort_values(by=['SortOrder', 'Date'])
    merged_df = merged_df.drop(columns=['PartBC', 'SortOrder'])

    # -- Save merged CSV -----------------------------------------------------------
    out_dir = os.path.join(COMPARE_DIR, source_key)
    os.makedirs(out_dir, exist_ok=True)

    merged_csv = os.path.join(out_dir, src["compare_csv"])
    merged_df.to_csv(merged_csv, index=False)
    print(f"  Merged CSV saved: {merged_csv}")

    # -- Summary statistics (monthly/quarterly/annual mean & median) ------------
    merged_df['Date'] = pd.to_datetime(merged_df['Date'])
    merged_df['Year'] = merged_df['Date'].dt.year
    merged_df['Month'] = merged_df['Date'].dt.month
    merged_df['Quarter'] = merged_df['Date'].dt.to_period("Q")

    value_cols = included_labels

    def compute_summary(df, time_unit, agg_func, label):
        grouped = df.groupby(['PartC', time_unit])[value_cols].agg(agg_func).reset_index()
        grouped['Summary_Type'] = f'{label}_{agg_func.__name__}'
        return grouped

    summary_df = pd.concat([
        compute_summary(merged_df, 'Month', np.mean, 'Monthly'),
        compute_summary(merged_df, 'Month', np.median, 'Monthly'),
        compute_summary(merged_df, 'Quarter', np.mean, 'Quarterly'),
        compute_summary(merged_df, 'Quarter', np.median, 'Quarterly'),
        compute_summary(merged_df, 'Year', np.mean, 'Annual'),
        compute_summary(merged_df, 'Year', np.median, 'Annual'),
    ], ignore_index=True)

    summary_csv = os.path.join(out_dir, src["summary_csv"])
    summary_df.to_csv(summary_csv, index=False)
    print(f"  Summary CSV saved: {summary_csv}")

    # -- Boxplots (one per PartC, comparing scenarios) -------------------------
    print("  Generating boxplots...")
    plot_df = merged_df[['PartC'] + value_cols].copy()
    plot_df_melted = plot_df.melt(
        id_vars='PartC', value_vars=value_cols,
        var_name='Scenario', value_name='Value',
    ).dropna()

    for partc in plot_df_melted['PartC'].unique():
        partc_df = plot_df_melted[plot_df_melted['PartC'] == partc]

        plt.figure(figsize=(6, 6))
        sns.boxplot(
            x='Scenario', y='Value', data=partc_df, width=0.6,
            showfliers=False,
            boxprops=dict(facecolor='skyblue', edgecolor='black'),
            medianprops=dict(color='red'),
            whiskerprops=dict(color='black'),
            capprops=dict(color='black'),
        )

        for i, scenario in enumerate(partc_df['Scenario'].unique()):
            mean_val = partc_df[partc_df['Scenario'] == scenario]['Value'].mean()
            plt.scatter(i, mean_val, color='black', s=50, zorder=5,
                        label='Mean' if i == 0 else "")

        plt.title(f"Boxplot for PartC: {partc}", fontsize=14)
        plt.xlabel("Scenario")
        plt.ylabel("Value")
        if len(partc_df['Scenario'].unique()) > 1:
            plt.legend(loc='upper right')
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, f"Boxplot_{partc}_with_mean.png"), dpi=300)
        plt.close()

    n_plots = plot_df_melted['PartC'].nunique()
    print(f"  {n_plots} boxplots saved to: {out_dir}")


# -- VALIDATION MODE -----------------------------------------------------------

def to_validation_csv(df, start_wy, end_wy):
    """Convert wide DataFrame to validation format (Part B, Part C, Year,
    Month, Value).  Delegates to ``utils.csv_io.to_validation_df`` (faithful
    copy; this function was its seed)."""
    return csv_io.to_validation_df(df, start_wy, end_wy)


def run_validation(source_key, src):
    """Extract Product A data and write a standard validation CSV.

    Output format: Part B, Part C, Year, Month, Value
    Filtered to the WY range [START_WY, END_WY].
    """
    print(f"\n{'-' * 60}")
    print(f"  Validation: {src['label']}")
    print(f"{'-' * 60}")

    dss_path = src["validate_dss"]
    if not dss_path.exists():
        print(f"  WARNING: DSS not found, skipping: {dss_path}")
        return

    excel_partcs, _ = load_inventory(src["inv_filter"])
    print(f"  Inventory SVs: {len(excel_partcs)}")

    # Read Product A DSS file
    df = extract_dss_data(str(dss_path), excel_partcs)
    print(f"  Extracted: {df.shape[1]} variables, "
          f"{df.index.min().strftime('%Y-%m')} - {df.index.max().strftime('%Y-%m')}")

    # Convert to long format and filter to water year window
    val_df = to_validation_csv(df, START_WY, END_WY)
    if val_df.empty:
        print("  WARNING: No data found in validation period.")
        return

    os.makedirs(VALIDATE_DIR, exist_ok=True)
    out_file = os.path.join(VALIDATE_DIR, src["validate_csv"])
    val_df.to_csv(out_file, index=False)

    n_vars = val_df.groupby(['Part B', 'Part C']).ngroups
    print(f"  Written: {out_file}")
    print(f"  Variables: {n_vars}  |  Rows: {len(val_df):,}")


# -- MAIN ---------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Postprocess CalSimHydro Product A DSS outputs.",
    )
    parser.add_argument(
        "--sources", nargs="+",
        choices=list(SOURCES.keys()), default=list(SOURCES.keys()),
        help="DSS sources to process (default: all)",
    )
    parser.add_argument(
        "--skip-compare", action="store_true", default=False,
        help="Skip scenario comparison (merged CSV, summary, boxplots)",
    )
    parser.add_argument(
        "--skip-validate", action="store_true", default=False,
        help="Skip validation CSV extraction",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 80)
    print("CalSimHydro -- Product A Postprocessing")
    print(f"Sources: {', '.join(args.sources)}")
    print(f"Compare: {'yes' if not args.skip_compare else 'skip'}")
    print(f"Validate: {'yes' if not args.skip_validate else 'skip'}")
    print(f"Period: WY {START_WY}-{END_WY}")
    print("=" * 80)

    for key in args.sources:
        src = SOURCES[key]
        if not args.skip_compare:
            run_comparison(key, src)
        if not args.skip_validate:
            run_validation(key, src)

    print(f"\n{'=' * 80}")
    print("Postprocessing complete.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
