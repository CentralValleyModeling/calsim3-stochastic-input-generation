# %% imports
import os
import sys
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path
from pydsstools.heclib.dss import HecDss
from matplotlib.gridspec import GridSpec
from statsmodels.distributions.empirical_distribution import ECDF

# %% add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

# %% quantile mapping
import utils.quantile_mapping as qmap

# %%
# set dpi to 300 for high resolution
plt.rcParams['figure.dpi'] = 300
# set figure size
plt.rcParams['figure.figsize'] = (6.5, 4)
# set plot style
plt.style.use('seaborn-v0_8-ticks')
# set font size
plt.rcParams.update({'font.size': 10})

# %% convert to wy
def year_to_wy(date):
    """Convert a date to water year (Oct-Sep)."""
    return date.year + 1 if date.month >= 10 else date.year

# %% set directory for CalSimHydro data
select_wba = 'WBA 02'
_script_dir = Path(__file__).resolve().parent
cshydro_dir = str(_script_dir / "reference")
cshydro_file = "CS3_RefETo.dss" # "CS3_PanEvapGerber.dss" "CS3_ET.dss" "CS3_RefETo.dss"
gridinfo_dir = str(_script_dir / "reference")
startDate_dss = "31OCT1920 00:00:00"
endDate_dss = "30SEP2021 24:00:00"
vic_output_dir = str(get_module_generated_dir("mod_forcing/vic") / "output" / "fluxes" / "Product_A" / "1")
vic_et_col =  7 #7 # column index for Short Grass ET in VIC output
vic_start_date = "1915-01-01"
vic_end_date = "2018-12-31"
wba_list = [
    'WBA 02', 'WBA 03','WBA 04','WBA 05',
    'WBA 06','WBA 07N','WBA 07S',
    'WBA 08N','WBA 08S','WBA 09',
    'WBA 10','WBA 11','WBA 12',
    'WBA 13','WBA 14','WBA 15N',
    'WBA 15S','WBA 16','WBA 17N',
    'WBA 17S','WBA 18','WBA 19',
    'WBA 20','WBA 21','WBA 22',
    'WBA 23','WBA 24','WBA 25',
    'WBA 26N','WBA 26S','WBA 50',
    'WBA 60N','WBA 60S','WBA 61',
    'WBA 62','WBA 63','WBA 64',
    'WBA 71','WBA 72','WBA 73', 'WBA 90'
]

# %% adjust select_wba for calsimhydro dss
if cshydro_file=='CS3_ET.dss':
    cshydro_wba = 'WBA 02'.replace(' ', '') + '_AL_ET'
elif cshydro_file == 'CS3_RefETo.dss':
    cshydro_wba = select_wba
elif cshydro_file == 'CS3_PanEvapGerber.dss':
    cshydro_wba = 'WBA02'

# %% adjust VIC et column if pan evap (idx minus 1)
if cshydro_file == 'CS3_PanEvapGerber.dss':
    vic_et_col -= 1

# %% plot titles
if cshydro_file =='CS3_ET.dss':
    ref_et_label = 'Crop ET (AL)'
elif cshydro_file == 'CS3_RefETo.dss':
    ref_et_label = 'Reference ET (ETo)'
elif cshydro_file == 'CS3_PanEvapGerber.dss':
    ref_et_label = 'Pan Evaporation (Gerber)'

# %% read in WBA grid information
if cshydro_file == 'CS3_PanEvapGerber.dss':
    wba_grid_file = os.path.join(gridinfo_dir, "VIC_grids_for_CIMIS_Stations.csv")
    wba_grid_info = pd.read_csv(wba_grid_file, sep=',', header=0, names=['CIMIS', 'lat', 'lon', 'pct_area'])
else:
    wba_grid_file = os.path.join(gridinfo_dir, "WBA_Grid_Info_20230112_RowBased_rev02.txt")
    wba_grid_info = pd.read_csv(wba_grid_file, sep='\t', header=None, names=['WBA', 'lat', 'lon', 'pct_area', 'X', 'Y'])

# %% --- read DSS monthly ET
cshydro_refeto_file = os.path.join(cshydro_dir, cshydro_file)
fid = HecDss.Open(cshydro_refeto_file,window=(startDate_dss,endDate_dss))
cshydro_et = pd.DataFrame({'date': pd.date_range(start="1920-10-31", end="2021-09-30", freq='ME')})
if cshydro_file == 'CS3_ET.dss':
    ts = fid.read_ts(f"/IWFM/{cshydro_wba}/RATE_INCH//1MON/EVAPOTRANSPIRATION/",window=(startDate_dss,endDate_dss))
elif cshydro_file == 'CS3_RefETo.dss':
    ts = fid.read_ts(f"/CALSIM/{cshydro_wba}/REF-ET//1MON/REFETO/",window=(startDate_dss,endDate_dss))
elif cshydro_file == 'CS3_PanEvapGerber.dss':
    ts = fid.read_ts(f"/CALSIM/{cshydro_wba}/PAN-EVAP//1MON/PAN-EVAP/",window=(startDate_dss,endDate_dss))
cshydro_et.insert(1, "CS3", value=ts.values)
cshydro_et = cshydro_et.set_index('date')

# %% load vic et et
if not cshydro_file == 'CS3_PanEvapGerber.dss':
    wba_info = wba_grid_info[wba_grid_info['WBA'] == select_wba.replace(' ', '_')]
else:
    wba_info = wba_grid_info[wba_grid_info['CIMIS'] == 'Gerber']
pct_area_total = 0
vic_et = pd.Series(data=0,index=pd.date_range(start=vic_start_date, end=vic_end_date, freq='D'))
for lat, lon, pct_area in wba_info[['lat', 'lon', 'pct_area']].values:
    file_name = f"fluxes_{lat}_{lon}"
    vic_et_file = os.path.join(vic_output_dir, file_name)
    vic_et_data = pd.read_csv(vic_et_file, sep='\t', header=None)
    ref_et = vic_et_data.iloc[:,vic_et_col].values # short grass reference ET
    ref_et = ref_et * pct_area  # scale by area percentage
    vic_et += ref_et
    pct_area_total += pct_area
vic_et = vic_et / pct_area_total
# aggregate to monthly and convert mm to inches
vic_et = vic_et.resample('ME').sum() / 25.4
vic_et.name = "VIC"
vic_et.index.name = 'date'
# remove last three months
vic_et = vic_et.loc[vic_et.index < '2018-10-01']

# %% join cshydro and vic ET
et_comparison = pd.merge(cshydro_et, vic_et, on='date')

# %% annual totals and monthly means
annual_et = et_comparison.resample('YS-OCT').sum().reset_index()
annual_et = annual_et.melt(id_vars='date', var_name='Model', value_name='ET')
monthly_et = et_comparison.copy()
monthly_et['month'] = monthly_et.index.month
avg_monthly_et = monthly_et.groupby('month').mean()


# %% combined two-panel plot: 10-year rolling mean (left), annual violin (right)
fig = plt.figure(figsize=(6.5, 4))
gs = GridSpec(1, 2, width_ratios=[3, 1], figure=fig)
ax0 = fig.add_subplot(gs[0])
ax1 = fig.add_subplot(gs[1])
colors = ['grey','indianred']
ylim = (35, 65) if cshydro_file != 'CS3_PanEvapGerber.dss' else (45, 80)
# Left panel: 10-year rolling mean annual ET by model
window = 5
for i, model in enumerate(['CS3', 'VIC']):
    rolling_mean = annual_et[annual_et['Model'] == model]['ET'].rolling(window, min_periods=1).mean()
    ax0.plot(np.arange(1920,2018), rolling_mean, label=model, color=colors[i])
ax0.set_title(f'{window}-Year Rolling Mean Annual {ref_et_label}', fontsize=10)
ax0.set_xlabel('Year')
# ax0.set_ylim(ylim)
ax0.set_ylabel('ET (in/year)')
ax0.grid(True, axis='y', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
ax0.legend()
# Right panel: annual violin plot of ET by Model
sns.violinplot(data=annual_et, x='Model', y='ET', hue='Model', ax=ax1, palette=['grey','indianred'], linewidth=0.75, legend=False)
ax1.set_title(f'Annual {ref_et_label}', fontsize=10)
ax1.set_xlabel('')
ax1.set_xticks(np.arange(len(annual_et['Model'].unique())))
ax1.set_xticklabels(annual_et['Model'].unique(), rotation=0)
ax1.set_ylabel('ET (in/year)')
# ax1.set_ylim(ylim)
ax1.grid(True, axis='y', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'Rolling_Annual_ET_Comparison_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)

# %% lineplot of average monthly ET by model
fig, ax = plt.subplots(figsize=(6.5, 4))
ax.plot(avg_monthly_et.index, avg_monthly_et['CS3'], label='CS3', color='grey')
ax.plot(avg_monthly_et.index, avg_monthly_et['VIC'], label='VIC', color='indianred')
ax.set_xticks(np.arange(1, 13))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
ax.set_title(f'Average Monthly {ref_et_label} by Model', fontsize=10)
ax.set_xlabel('')
ax.set_ylabel('ET (in/month)')
ax.legend()
ax.grid(True, axis='y', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'Average_Monthly_ET_Comparison_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)

# %% scatter of April values between models with 1:1 line
april_et = et_comparison[et_comparison.index.month == 4]
fig, ax = plt.subplots(figsize=(5, 5))
ax.scatter(april_et['CS3'], april_et['VIC'], color='indianred', edgecolor='k', alpha=0.7)
min_val = min(april_et['CS3'].min(), april_et['VIC'].min())
max_val = max(april_et['CS3'].max(), april_et['VIC'].max())
ax.plot([min_val, max_val], [min_val, max_val], color='grey', linestyle='--', linewidth=1)
ax.set_xlabel('CS3 April ET (in/month)')
ax.set_ylabel('VIC April ET (in/month)')
ax.set_title(f'April {ref_et_label}: CS3 vs VIC')
ax.grid(True, axis='both', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'April_ET_Scatter_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)



###### QUANTILE MAPPING ######
# %% set periods
train_period = [1921, 1971]
test_period = [1972, 2018]

# %% run quantile mapping
et_data = et_comparison.copy()
et_data.insert(1, 'month', et_data.index.month)
et_data.insert(2, 'year', et_data.index.map(year_to_wy))
ETsim = et_data[(et_data['year'] >= test_period[0]) & (et_data['year'] <= test_period[1])][['year','month','VIC']].rename(columns={'VIC': 'value'})
EThist = et_data[(et_data['year'] >= train_period[0]) & (et_data['year'] <= train_period[1])][['year','month','VIC']].rename(columns={'VIC': 'value'})
ETTargetHist = et_data[(et_data['year'] >= train_period[0]) & (et_data['year'] <= train_period[1])][['year','month','CS3']].rename(columns={'CS3': 'value'})

# %% apply quantile mapping
ETTargetQmap = qmap.qmap_single(ETsim, EThist, ETTargetHist)

# %% join quantile-mapped values back to original DataFrame
et_data = et_data.merge(ETTargetQmap[['year', 'month', 'quantile_mapped_value']], on=['year', 'month'], how='left')
et_data.index = et_comparison.index
et_data.drop(columns=['year', 'month'], inplace=True)
et_data_annual = et_data.resample('YS-OCT').sum()
monthly_means = et_data.copy()
monthly_means['month'] = monthly_means.index.month
monthly_means = monthly_means.loc[monthly_means.index.year>=1972]
avg_monthly = monthly_means.groupby('month')[['CS3', 'VIC', 'quantile_mapped_value']].mean()



# %% plot rolling 5 year values of the CS3 VIC and quantile_mapped_value
fig, ax = plt.subplots(figsize=(6.5, 4))
window = 5
for label, color in zip(['CS3', 'VIC', 'quantile_mapped_value'], ['grey', 'indianred', 'blue']):
    if label == 'quantile_mapped_value':
        rolling_mean = et_data_annual[label].rolling(window, min_periods=1).mean()
        rolling_mean = rolling_mean[rolling_mean.index.year >= 1976]  # start from 1973 for quantile mapping
        ax.plot(np.arange(1977,2019), rolling_mean, label='Quantile Mapped', color=color)
    else:
        rolling_mean = et_data_annual[label].rolling(window, min_periods=1).mean()
        ax.plot(np.arange(1921,2019), rolling_mean, label=label, color=color)
ax.set_title(f'{window}-Year Rolling Mean Annual {ref_et_label}: {select_wba}', fontsize=10)
ax.set_xlabel('Year')
ax.set_ylabel('ET (in/year)')
ax.grid(True, axis='y', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'Rolling_Annual_ET_Comparison_QMap_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)

# %% monthly mean lineplot for calendar months comparing CS3 VIC and Quantile Mapped Value
fig, ax = plt.subplots(figsize=(6.5, 4))
ax.plot(avg_monthly.index, avg_monthly['CS3'], label='CS3', color='grey')
ax.plot(avg_monthly.index, avg_monthly['VIC'], label='VIC', color='indianred')
ax.plot(avg_monthly.index, avg_monthly['quantile_mapped_value'], label='Quantile Mapped', color='blue')
ax.set_xticks(np.arange(1, 13))
ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
ax.set_title(f'Average Monthly {ref_et_label}: {select_wba}', fontsize=10)
ax.set_xlabel('')
ax.set_ylabel('ET (in/month)')
ax.legend()
ax.grid(True, axis='y', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'Average_Monthly_ET_Comparison_QMap_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)

# %% ecdf plot of CS3 VIC and Quantile Mapped
fig, ax = plt.subplots(figsize=(6.5, 5))
for label, color in zip(['CS3', 'VIC', 'quantile_mapped_value'], ['grey', 'indianred', 'blue']):
    ecdf = ECDF(et_data.loc[et_data.index.year >= 1972][label])
    ax.plot(ecdf.x, ecdf.y, label=label if label != 'quantile_mapped_value' else 'Quantile Mapped', color=color)
ax.set_xlabel('Monthly ET (in/month)')
ax.set_ylabel('Empirical CDF')
ax.set_title(f'ECDF of Monthly {ref_et_label}: {select_wba}', fontsize=10)
ax.legend()
ax.grid(True, axis='both', color='k', linewidth=0.5, linestyle='--', alpha=0.5)
fig.tight_layout()
fig.savefig(os.path.join('./_figures', f'ECDF_Annual_ET_Comparison_QMap_{cshydro_wba.replace(" ", "_")}.svg'), dpi=300)


# %%
et_data.to_csv(os.path.join(".", f"{cshydro_wba.replace(' ', '_')}_ET_QMap.csv"), index=True)

# %%
