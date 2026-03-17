#%% This script extracts, processes, and visualizes time series data from CalSimHydro output DSS files.
# It generates merged CSVs, summary statistics, and boxplots comparing different scenario outputs.
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


# %% ── RESULTS ROOT ─────────────────────────────────────────────────────
_GEN_DIR = get_module_generated_dir("mod_hydrology/calsimhydro")
OUTPUT_DIR = str(_GEN_DIR / "output" / "_3_postprocess_run_RiceOutput")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# %% ── Load Excel Master File ───────────────────────────────────────────
excel_path = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
sheet_name = "MASTER"
df_master = pd.read_excel(excel_path, sheet_name=sheet_name)

# Filter CalSimHydro rows
CalSimHydro_rows = df_master[(df_master.iloc[:, 8] == 'CalSimHydro') & (df_master.iloc[:, 9] == 'RiceOutput.dss')]
CalSimHydro_SVnames = [str(name).strip().upper() for name in CalSimHydro_rows.iloc[:, 7].tolist()]

# Create mapping: formatted PartB/PartC → original SV name
excel_to_part_BC = lambda n: n.upper().replace(" ", "_")
excel_partcs = {excel_to_part_BC(n): n for n in CalSimHydro_SVnames}

# Get desired sort order based on master file (column 7)
desired_order = [excel_to_part_BC(name) for name in CalSimHydro_rows.iloc[:, 7].tolist()]

# %% ── DSS File Paths ───────────────────────────────────────────────────
_cshydro_runs = _GEN_DIR / "CalSimHydro_Runs"
dss_paths = [
    str(_cshydro_runs / "CalSimHydro_Historical_1972-2018" / "RiceOutput.dss"),
    str(_cshydro_runs / "CalSimHydro_VICPrecip_1972-2018" / "RiceOutput.dss"),
    str(_cshydro_runs / "CalSimHydro_QMET_1972-2018" / "RiceOutput.dss"),
    str(_cshydro_runs / "CalSimHydro_Product_A" / "RiceOutput.dss"),
]

# %% ── Function to Extract DSS Time Series ──────────────────────────────
def extract_dss_data(dss_path):
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

# %% ── Read All DSS Files ───────────────────────────────────────────────
dss_data_by_file = [extract_dss_data(path) for path in dss_paths]

# %% ── Convert to Long Format ───────────────────────────────────────────

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

# %% ── Merge All DataFrames on Date + PartB + PartC ─────────────────────
merged_df = reduce(
    lambda left, right: pd.merge(left, right, on=['Date', 'PartB', 'PartC'], how='outer'),
    long_dfs
)

# %% ── Sort by SV Order from Master Excel ───────────────────────────────
# Create a sort key: PartB/PartC as one string
merged_df['PartBC'] = merged_df['PartB'].str.upper() + '/' + merged_df['PartC']
sort_order_map = {val: idx for idx, val in enumerate(desired_order)}
merged_df['SortOrder'] = merged_df['PartBC'].map(sort_order_map)
merged_df = merged_df.sort_values(by=['SortOrder', 'Date'])
merged_df = merged_df.drop(columns=['PartBC', 'SortOrder'])

# %% ── Save Final Merged Time Series ─────────────────────────────────────
merged_csv_path = os.path.join(OUTPUT_DIR, "RiceOutput_DSS.csv")
merged_df.to_csv(merged_csv_path, index=False)
print(f"✅ Final CSV saved to: {merged_csv_path}")

# %% ── Summary Statistics by PartC ───────────────────────────────────────

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
summary_output_path = os.path.join(OUTPUT_DIR, "RiceOutput_summary_statistics_by_PartC.csv")
summary_df.to_csv(summary_output_path, index=False)
print(f"📊 Summary statistics saved to: {summary_output_path}")


#%% BOX PLOT


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
    ax = sns.boxplot(
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
    



################################################################################################################
######################## The following lines show box plot with outlier data #######################

# # --- Prepare Data ---
# # Melt the data to long format
# plot_df = merged_df[['PartC', 'Historical_1921', 'Historical', 'VIC_Precip', 'QM_ET']].copy()
# plot_df_melted = plot_df.melt(id_vars='PartC',
#                               value_vars=['Historical_1921', 'Historical', 'VIC_Precip', 'QM_ET'],
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
    

############################################################################################################
###############################################################################################################


