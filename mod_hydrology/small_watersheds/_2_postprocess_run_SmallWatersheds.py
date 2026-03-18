"""
Postprocess Small Watersheds DSS runs.

Extracts time series from historical and VIC-precip Small Watersheds DSS outputs,
merges scenarios into a single CSV, computes summary statistics, and generates
boxplots comparing scenario distributions.

Usage
-----
    python _2_postprocess_run_SmallWatersheds.py
"""
#%%

import os
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss
from functools import reduce

import seaborn as sns
import matplotlib.pyplot as plt

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_inventory_dir

_GEN_DIR = get_module_generated_dir("mod_hydrology/small_watersheds")


# %% ── CONSTANTS ────────────────────────────────────────────────────────
OUTPUT_DIR = str(_GEN_DIR / "output" / "_2_postprocess_run")

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

_sws_runs = _GEN_DIR / "SmallWatersheds_Runs"
DSS_PATHS = [
    str(_sws_runs / "SmallWatershed_Historical_1921-2018" / "CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss"),      # Value 1
    str(_sws_runs / "SmallWatershed_VICPrecip_1921-2018" / "CVSWShed_FlowContribution3pcntWBA24_2013Init_2021.dss"),       # Value 2
]

SCENARIO_LABELS = ['Historical_1921', 'VIC_Precip']


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


def extract_dss_data(dss_path, excel_partcs):
    """Extract time series from a DSS file for SmallWatersheds variables."""
    data_dict = {}
    with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:
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
    print(f"✅ Final CSV saved to: {merged_csv_path}")

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
    print(f"📊 Summary statistics saved to: {summary_output_path}")

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
        ax = sns.boxplot(
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

    print("✅ Postprocessing complete.")


# %% ── CLI ENTRY POINT ─────────────────────────────────────────────────

if __name__ == "__main__":
    run_postprocess()


