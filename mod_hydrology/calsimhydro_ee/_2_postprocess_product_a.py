"""
Postprocess CalSimHydroEE Run Outputs
=====================================
Extracts monthly time series from CalSimHydroEE output DSS files across multiple
scenarios, merges them into a single long-format CSV, computes summary statistics
(monthly/quarterly/annual mean and median by PartC), and generates per-PartC boxplots.

Scenarios compared
------------------
- Historical            (CalSimHydroEE_Historical_1972-2018)
- VIC_Precip            (CalSimHydroEE_VICPrecip_1972-2018)
- QM_ET                 (CalSimHydroEE_QMET_1972-2018)
- Product_A             (CalSimHydroEE_Product_A)

Inputs
------
- CalSimHydroEE_Runs/<scenario>/CalSimHydroEE_DP_EA.dss
- _MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx

Outputs
-------
- output/_2_postprocess_product_a/calsimHydroEE_1972-2018_DSS.csv
- output/_2_postprocess_product_a/calsimHydroEE_summary_statistics_by_PartC.csv
- output/_2_postprocess_product_a/Boxplot_<PartC>_with_mean.png
- output/_2_postprocess_product_a/_product_a_validation/_cshydroEE_productA_1972_2018.csv

Usage
-----
    cd mod_hydrology/calsimhydro_ee && python _2_postprocess_product_a.py
"""

import os
import sys
from functools import reduce
from pathlib import Path

import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import csv_io, dss_io
from utils.paths import get_module_generated_dir, get_inventory_dir


# RESULTS ROOT
_GEN_DIR = get_module_generated_dir("mod_hydrology/calsimhydro_ee")
OUTPUT_DIR = str(_GEN_DIR / "output" / "_2_postprocess_product_a")
os.makedirs(OUTPUT_DIR, exist_ok=True)

VALIDATION_DIR = str(_GEN_DIR / "output" / "_2_postprocess_product_a" / "_product_a_validation")
os.makedirs(VALIDATION_DIR, exist_ok=True)

# Validation window (water years)
START_WY = 1972
END_WY   = 2018

# Load Excel Master File
excel_path = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
sheet_name = "MASTER"
df_master = pd.read_excel(excel_path, sheet_name=sheet_name)

# Filter CalSimHydroEE rows
CalSimHydroEE_rows = df_master[(df_master.iloc[:, 8] == 'CalSimHydroEE') & (df_master.iloc[:, 9] == 'IDCOutputEE.dss')]
CalSimHydroEE_SVnames = [str(name).strip().upper() for name in CalSimHydroEE_rows.iloc[:, 7].tolist()]

# Create mapping: formatted PartB/PartC -> original SV name
excel_to_part_BC = lambda n: n.upper().replace(" ", "_")
excel_partcs = {excel_to_part_BC(n): n for n in CalSimHydroEE_SVnames}

# Get desired sort order based on master file (column 7)
desired_order = [excel_to_part_BC(name) for name in CalSimHydroEE_rows.iloc[:, 7].tolist()]

# DSS File Paths
_ee_runs = _GEN_DIR / "CalSimHydroEE_Runs"
dss_paths = [
    str(_ee_runs / "CalSimHydroEE_Historical_1972-2018" / "CalSimHydroEE_DP_EA.dss"),
    str(_ee_runs / "CalSimHydroEE_VICPrecip_1972-2018" / "CalSimHydroEE_DP_EA.dss"),
    str(_ee_runs / "CalSimHydroEE_QMET_1972-2018" / "CalSimHydroEE_DP_EA.dss"),
    str(_ee_runs / "CalSimHydroEE_Product_A" / "CalSimHydroEE_DP_EA.dss"),
]


# Function to Extract DSS Time Series
def extract_dss_data(dss_path):
    # Open via utils.dss_io (auto directory-junction for long paths,
    # catalog_flag=True -- identical _DSS_LINK path / _PATH_LIMIT=200 as the
    # removed local helper). The bespoke read loop below is preserved verbatim
    # (no-trailing-slash pattern, sort by Part C index 2) because it differs
    # from dss_io.read_monthly_frame -- only the open is consolidated.
    dss_path = Path(dss_path).resolve()
    data_dict = {}
    with dss_io.open_dss(dss_path, version=6, catalog_flag=True) as dss:
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


def main():
    # Read All DSS Files
    dss_data_by_file = [extract_dss_data(path) for path in dss_paths]

    # Convert to Long Format

    # Define meaningful scenario names matching DSS file order
    scenario_labels = ['Historical', 'VIC_Precip', 'QM_ET', 'Product_A']

    long_dfs = []
    for df, label in zip(dss_data_by_file, scenario_labels):
        long_df = df.stack().reset_index()
        long_df.columns = ['Date', 'SV_Name_PartBC', label]
        long_df[['PartB', 'PartC']] = long_df['SV_Name_PartBC'].str.split('/', expand=True)
        long_df = long_df.drop(columns='SV_Name_PartBC')
        long_df = long_df[['Date', 'PartB', 'PartC', label]]
        long_dfs.append(long_df)

    # Merge All DataFrames on Date + PartB + PartC
    merged_df = reduce(
        lambda left, right: pd.merge(left, right, on=['Date', 'PartB', 'PartC'], how='outer'),
        long_dfs
    )

    # Sort by SV Order from Master Excel
    # Create a sort key: PartB/PartC as one string
    merged_df['PartBC'] = merged_df['PartB'].str.upper() + '/' + merged_df['PartC']
    sort_order_map = {val: idx for idx, val in enumerate(desired_order)}
    merged_df['SortOrder'] = merged_df['PartBC'].map(sort_order_map)
    merged_df = merged_df.sort_values(by=['SortOrder', 'Date'])
    merged_df = merged_df.drop(columns=['PartBC', 'SortOrder'])

    # Save Final Merged Time Series
    merged_csv_path = os.path.join(OUTPUT_DIR, "calsimHydroEE_1972-2018_DSS.csv")
    merged_df.to_csv(merged_csv_path, index=False)
    print(f"Final CSV saved to: {merged_csv_path}")

    # Summary Statistics by PartC

    # Ensure Date column is datetime
    merged_df['Date'] = pd.to_datetime(merged_df['Date'])

    # Add time units for grouping
    merged_df['Year'] = merged_df['Date'].dt.year
    merged_df['Month'] = merged_df['Date'].dt.month
    merged_df['Quarter'] = merged_df['Date'].dt.to_period("Q")

    value_cols = ['Historical', 'VIC_Precip', 'QM_ET', 'Product_A']

    def compute_summary(df, time_unit, agg_func, label):
        grouped = df.groupby(['PartC', time_unit])[value_cols].agg(agg_func).reset_index()
        grouped['Summary_Type'] = f'{label}_{agg_func.__name__}'
        return grouped

    # Compute all summaries
    monthly_avg    = compute_summary(merged_df, 'Month', np.mean, 'Monthly')
    monthly_median = compute_summary(merged_df, 'Month', np.median, 'Monthly')
    quarterly_avg  = compute_summary(merged_df, 'Quarter', np.mean, 'Quarterly')
    quarterly_med  = compute_summary(merged_df, 'Quarter', np.median, 'Quarterly')
    annual_avg     = compute_summary(merged_df, 'Year', np.mean, 'Annual')
    annual_med     = compute_summary(merged_df, 'Year', np.median, 'Annual')

    # Combine all summaries
    summary_df = pd.concat([
        monthly_avg,
        monthly_median,
        quarterly_avg,
        quarterly_med,
        annual_avg,
        annual_med
    ], ignore_index=True)

    # Save summary statistics to CSV
    summary_output_path = os.path.join(OUTPUT_DIR, "calsimHydroEE_summary_statistics_by_PartC.csv")
    summary_df.to_csv(summary_output_path, index=False)
    print(f"Summary statistics saved to: {summary_output_path}")

    # BOX PLOT

    # --- Prepare Data ---
    plot_df = merged_df[['PartC'] + value_cols].copy()
    plot_df_melted = plot_df.melt(id_vars='PartC',
                                  value_vars=value_cols,
                                  var_name='Scenario', value_name='Value')
    plot_df_melted = plot_df_melted.dropna()

    # Get unique PartC values
    unique_partcs = plot_df_melted['PartC'].unique()

    # --- Plot Loop ---
    for partc in unique_partcs:
        partc_df = plot_df_melted[plot_df_melted['PartC'] == partc]

        plt.figure(figsize=(6, 6))
        sns.boxplot(
            x='Scenario',
            y='Value',
            data=partc_df,
            width=0.6,
            showfliers=False,  # Hide outliers
            boxprops=dict(facecolor='skyblue', edgecolor='black'),
            medianprops=dict(color='red'),
            whiskerprops=dict(color='black'),
            capprops=dict(color='black')
        )

        # --- Add Mean as Black Dot ---
        for i, scenario in enumerate(partc_df['Scenario'].unique()):
            scenario_values = partc_df[partc_df['Scenario'] == scenario]['Value']
            mean_val = scenario_values.mean()
            plt.scatter(i, mean_val, color='black', s=50, zorder=5, label='Mean' if i == 0 else "")

        # --- Final Touches ---
        plt.title(f"Boxplot for PartC: {partc}", fontsize=14)
        plt.xlabel("Scenario")
        plt.ylabel("Value")
        if len(partc_df['Scenario'].unique()) > 1:
            plt.legend(loc='upper right')
        plt.tight_layout()

        # Optional save
        plt.savefig(os.path.join(OUTPUT_DIR, f"Boxplot_{partc}_with_mean.png"), dpi=300)

    # CalSim Historical Validation Extraction
    print("\n" + "=" * 80)
    print("CalSimHydroEE -- CalSim Historical Validation Extraction")
    print(f"Period: WY {START_WY}-{END_WY}")
    print("=" * 80)

    # Reuse the already-extracted Product_A data (index 3 in dss_data_by_file)
    product_a_df = dss_data_by_file[3]
    val_df = csv_io.to_validation_df(product_a_df, START_WY, END_WY)

    if val_df.empty:
        print("  No data in validation period.")
    else:
        val_out_file = os.path.join(VALIDATION_DIR, f"_cshydroEE_productA_{START_WY}_{END_WY}.csv")
        val_df.to_csv(val_out_file, index=False)
        n_vars = val_df.groupby(['Part B', 'Part C']).ngroups
        print(f"  Written : {val_out_file}")
        print(f"  Variables: {n_vars}  |  Rows: {len(val_df):,}")

    print("=" * 80)
    print("Validation extraction complete.")
    print("=" * 80)


if __name__ == "__main__":
    main()


################################################################################################################
######################## The following lines show box plot with outlier data #######################

# # --- Prepare Data ---
# # Melt the data to long format
# plot_df = merged_df[['PartC', 'Historical', 'VIC_Precip', 'QM_ET']].copy()
# plot_df_melted = plot_df.melt(id_vars='PartC',
#                               value_vars=['Historical', 'VIC_Precip', 'QM_ET'],
#                               var_name='Scenario', value_name='Value')
# # Drop NaNs
# plot_df_melted = plot_df_melted.dropna()

# # Get unique PartC values
# unique_partcs = plot_df_melted['PartC'].unique()

# # --- Plot Loop ---
# for partc in unique_partcs:
#     partc_df = plot_df_melted[plot_df_melted['PartC'] == partc]

#     plt.figure(figsize=(6, 6))
#     sns.boxplot(x='Scenario', y='Value', data=partc_df,
#                 width=0.6, showfliers=True,  # showfliers = True to show outliers
#                 boxprops=dict(facecolor='skyblue', edgecolor='black'),
#                 medianprops=dict(color='red'),
#                 whiskerprops=dict(color='black'),
#                 capprops=dict(color='black'))

#     plt.title(f"Boxplot for PartC: {partc}", fontsize=14)
#     plt.xlabel("Scenario")
#     plt.ylabel("Value")
#     plt.tight_layout()

#     # Optional: Save each plot
#     plt.savefig(os.path.join(OUTPUT_DIR, f"Boxplot_{partc}.png"), dpi=300)

#     plt.show()  # Opens each plot in a new window
