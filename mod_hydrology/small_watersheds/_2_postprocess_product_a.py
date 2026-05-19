"""
Postprocess Small Watersheds DSS Runs
=====================================
Extracts time series from historical and VIC-precip Small Watersheds DSS
outputs, merges scenarios into a single CSV, computes summary statistics,
generates scenario-comparison boxplots, and creates a CalSim validation CSV
from the VIC_Precip (Product A) scenario.

Inputs
------
- Small Watersheds DSS outputs (historical, VIC-precip scenarios)
- Master inventory xlsx

Outputs
-------
- <generated>/output/_2_postprocess_product_a/  (merged + summary CSVs, boxplots)
- <generated>/output/_2_postprocess_product_a/_product_a_validation/  (CalSim-format CSV)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
Default (runs postprocess + validation for WY 1972-2018):
    python _2_postprocess_product_a.py

Custom validation period (SWS product A output is 1921-2018):
    python _2_postprocess_product_a.py 1922 2018
"""

import os
import sys
import subprocess
from functools import reduce
from pathlib import Path

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_inventory_dir

_GEN_DIR = get_module_generated_dir("mod_hydrology/small_watersheds")


# %% ── CONSTANTS ────────────────────────────────────────────────────────
OUTPUT_DIR = str(_GEN_DIR / "output" / "_2_postprocess_product_a")
VALIDATION_DIR = str(_GEN_DIR / "output" / "_2_postprocess_product_a" / "_product_a_validation")

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

_sws_runs = _GEN_DIR / "SmallWatersheds_Runs"
DSS_PATHS = [
    str(_sws_runs / "SmallWatershed_Historical_1921-2018" / "CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss"),      # Value 1
    str(_sws_runs / "SmallWatershed_Product_A" / "CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss"),                  # Value 2
]

SCENARIO_LABELS = ['Historical_1921', 'ProductA']


# %% ── HELPER FUNCTIONS ────────────────────────────────────────────────

def load_master_inventory():
    """Load and filter SmallWatersheds entries from the master inventory."""
    df_master = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)

    SmallWatersheds_rows = df_master[
        (df_master.iloc[:, 8] == 'Small Watersheds') &
        (df_master.iloc[:, 9] == 'CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss')
    ]
    SmallWatersheds_SVnames = [str(name).strip().upper() for name in SmallWatersheds_rows.iloc[:, 7].tolist()]

    excel_to_part_BC = lambda n: n.upper().replace(" ", "_")
    excel_partcs = {excel_to_part_BC(n): n for n in SmallWatersheds_SVnames}
    desired_order = [excel_to_part_BC(name) for name in SmallWatersheds_rows.iloc[:, 7].tolist()]

    return excel_partcs, desired_order


# -- Junction helper for long DSS paths ---------------------------------------
# The Fortran HEC-DSS library inside pydsstools limits path names to 256 chars.
# The data directory may live on OneDrive with a very long path, so we create a
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


def extract_dss_data(dss_path, excel_partcs):
    """Extract time series from a DSS file for SmallWatersheds variables."""
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
    """Read monthly time series from a DSS file using pydsstools."""
    data_dict = {}
    with HecDss.Open(dss_path, version=6, catalog_flag=True) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            part_BC = parts[1].upper() + '/' + parts[2]
            buckets.setdefault(part_BC, []).append(p)

        wanted = {b: buckets[b] for b in buckets if b in excel_partcs} or buckets

        for part_BC, plist in wanted.items():
            master = {}
            for p in sorted(plist, key=lambda x: x.strip("/").split("/")[2]):
                ts = dss.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                s = pd.Series(vals, index=idx)
                master.update(s.to_dict())
            if master:
                series = pd.Series(master).sort_index()
                series.name = excel_partcs.get(part_BC, part_BC)
                data_dict[series.name] = series

    return pd.DataFrame(data_dict).sort_index()


def compute_summary(df, time_unit, agg_func, label, value_cols):
    """Compute grouped summary statistics."""
    grouped = df.groupby(['PartC', time_unit])[value_cols].agg(agg_func).reset_index()
    grouped['Summary_Type'] = f'{label}_{agg_func.__name__}'
    return grouped


# %% ── POSTPROCESS ──────────────────────────────────────────────────────

def run_postprocess():
    """Extract DSS data, merge scenarios, generate summary statistics and boxplots."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load master inventory
    excel_partcs, desired_order = load_master_inventory()

    # Read all DSS files
    print("Reading DSS files...")
    dss_data_by_file = [extract_dss_data(path, excel_partcs) for path in DSS_PATHS]

    # Convert to long format
    long_dfs = []
    for df, label in zip(dss_data_by_file, SCENARIO_LABELS):
        long_df = df.stack().reset_index()
        long_df.columns = ['Date', 'SV_Name_PartBC', label]
        long_df[['PartB', 'PartC']] = long_df['SV_Name_PartBC'].str.split('/', expand=True)
        long_df = long_df.drop(columns='SV_Name_PartBC')
        long_df = long_df[['Date', 'PartB', 'PartC', label]]
        long_dfs.append(long_df)

    # Merge all DataFrames on Date + PartB + PartC
    merged_df = reduce(
        lambda left, right: pd.merge(left, right, on=['Date', 'PartB', 'PartC'], how='outer'),
        long_dfs
    )

    # Sort by SV order from master Excel
    merged_df['PartBC'] = merged_df['PartB'].str.upper() + '/' + merged_df['PartC']
    sort_order_map = {val: idx for idx, val in enumerate(desired_order)}
    merged_df['SortOrder'] = merged_df['PartBC'].map(sort_order_map)
    merged_df = merged_df.sort_values(by=['SortOrder', 'Date'])
    merged_df = merged_df.drop(columns=['PartBC', 'SortOrder'])

    # Save final merged time series
    merged_csv_path = os.path.join(OUTPUT_DIR, "SmallWatersheds_2DSS.csv")
    merged_df.to_csv(merged_csv_path, index=False)
    print(f"Final CSV saved to: {merged_csv_path}")

    # ── Summary Statistics by PartC ──────────────────────────────────────
    merged_df['Date'] = pd.to_datetime(merged_df['Date'])
    merged_df['Year'] = merged_df['Date'].dt.year
    merged_df['Month'] = merged_df['Date'].dt.month
    merged_df['Quarter'] = merged_df['Date'].dt.to_period("Q")

    value_cols = SCENARIO_LABELS

    summary_df = pd.concat([
        compute_summary(merged_df, 'Month',   np.mean,   'Monthly',    value_cols),
        compute_summary(merged_df, 'Month',   np.median, 'Monthly',    value_cols),
        compute_summary(merged_df, 'Quarter', np.mean,   'Quarterly',  value_cols),
        compute_summary(merged_df, 'Quarter', np.median, 'Quarterly',  value_cols),
        compute_summary(merged_df, 'Year',    np.mean,   'Annual',     value_cols),
        compute_summary(merged_df, 'Year',    np.median, 'Annual',     value_cols),
    ], ignore_index=True)

    summary_output_path = os.path.join(OUTPUT_DIR, "SmallWatersheds_summary_statistics_by_PartC.csv")
    summary_df.to_csv(summary_output_path, index=False)
    print(f"Summary statistics saved to: {summary_output_path}")

    # ── Boxplots ─────────────────────────────────────────────────────────
    plot_df = merged_df[['PartC'] + value_cols].copy()
    plot_df_melted = plot_df.melt(
        id_vars='PartC', value_vars=value_cols,
        var_name='Scenario', value_name='Value'
    )
    plot_df_melted = plot_df_melted.dropna()

    for partc in plot_df_melted['PartC'].unique():
        partc_df = plot_df_melted[plot_df_melted['PartC'] == partc]

        plt.figure(figsize=(6, 6))
        sns.boxplot(
            x='Scenario', y='Value', data=partc_df,
            width=0.6, showfliers=False,
            boxprops=dict(facecolor='skyblue', edgecolor='black'),
            medianprops=dict(color='red'),
            whiskerprops=dict(color='black'),
            capprops=dict(color='black')
        )

        for i, scenario in enumerate(partc_df['Scenario'].unique()):
            scenario_values = partc_df[partc_df['Scenario'] == scenario]['Value']
            mean_val = scenario_values.mean()
            plt.scatter(i, mean_val, color='black', s=50, zorder=5,
                        label='Mean' if i == 0 else "")

        plt.title(f"Boxplot for PartC: {partc}", fontsize=14)
        plt.xlabel("Scenario")
        plt.ylabel("Value")
        if len(partc_df['Scenario'].unique()) > 1:
            plt.legend(loc='upper right')
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_DIR, f"Boxplot_{partc}_with_mean.png"), dpi=300)
        plt.show()

    print("Postprocessing complete.")

    return merged_df


# %% ── VALIDATION CSV ───────────────────────────────────────────────────

def create_validation_csv(merged_df=None, output_dir=None, start_wy=1972, end_wy=2018):
    """
    Create validation CSV from SmallWatersheds postprocess output.

    Filters the VIC_Precip (Product A) scenario to the CalSim validation period
    and converts AF to TAF.  Outputs in standard CalSim validation format:
    Part B, Part C, Year, Month, Value.

    Parameters
    ----------
    merged_df : pd.DataFrame, optional
        Merged postprocess DataFrame (from run_postprocess).  If None, reads
        from SmallWatersheds_2DSS.csv on disk.
    output_dir : str, optional
        Output directory for validation CSV.  Defaults to VALIDATION_DIR.
    start_wy : int
        Start water year (default: 1972)
    end_wy : int
        End water year (default: 2018)
    """
    if output_dir is None:
        output_dir = VALIDATION_DIR
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 80)
    print("Creating Validation CSV -- Small Watersheds")
    print("=" * 80)

    # Load from CSV if no DataFrame provided
    if merged_df is None:
        source_csv = os.path.join(OUTPUT_DIR, "SmallWatersheds_2DSS.csv")
        if not os.path.exists(source_csv):
            print(f"Error: {source_csv} not found. Run postprocessing first.")
            return
        merged_df = pd.read_csv(source_csv)

    df = merged_df.copy()
    df['Date'] = pd.to_datetime(df['Date'])

    # WY N starts Oct of year N-1 and ends Sep of year N
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date   = pd.Timestamp(end_wy, 9, 30)

    print(f"Period : WY {start_wy}-{end_wy}  "
          f"({start_date.strftime('%b %Y')} - {end_date.strftime('%b %Y')})")

    # Filter to validation period
    mask = (df['Date'] >= start_date) & (df['Date'] <= end_date)
    df_filtered = df.loc[mask].copy()

    if df_filtered.empty:
        print("No data found in the validation period.")
        return

    # Build validation DataFrame using ProductA values
    # SmallWatersheds DSS outputs in AF; CalSim baseline expects TAF
    val_df = pd.DataFrame({
        'Part B': df_filtered['PartB'].values,
        'Part C': df_filtered['PartC'].values,
        'Year':   df_filtered['Date'].dt.year.values,
        'Month':  df_filtered['Date'].dt.month.values,
        'Value':  df_filtered['ProductA'].values / 1000.0   # AF -> TAF
    })

    val_df = val_df.dropna(subset=['Value'])
    val_df = val_df.sort_values(
        by=['Part B', 'Part C', 'Year', 'Month']
    ).reset_index(drop=True)

    output_file = os.path.join(
        output_dir, f"_smallwatersheds_productA_{start_wy}_{end_wy}.csv"
    )
    val_df.to_csv(output_file, index=False)

    n_variables = val_df.groupby(['Part B', 'Part C']).ngroups
    print(f"\n  Written   : {output_file}")
    print(f"  Variables : {n_variables}")
    print(f"  Rows      : {len(val_df)}")
    print(f"  Date range: "
          f"{df_filtered['Date'].min().strftime('%Y-%m')} - "
          f"{df_filtered['Date'].max().strftime('%Y-%m')}")
    print("=" * 80)


# %% ── CLI ENTRY POINT ─────────────────────────────────────────────────

def main():
    """Main entry point."""
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    start_wy = int(args[0]) if len(args) >= 2 else 1972
    end_wy   = int(args[1]) if len(args) >= 2 else 2018

    if len(args) >= 2:
        print(f"\nCustom validation period: WY {start_wy}-{end_wy}\n")

    merged_df = run_postprocess()
    create_validation_csv(merged_df=merged_df, start_wy=start_wy, end_wy=end_wy)


if __name__ == "__main__":
    main()


