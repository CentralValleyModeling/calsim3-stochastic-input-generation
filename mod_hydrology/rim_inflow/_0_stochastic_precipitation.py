# %% imports
import os, sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir, REPO_ROOT

# %% style
sns.set_style("ticks")
plt.rcParams.update({
    'font.size':        8,
    'axes.titlesize':   8,
    'axes.labelsize':   8,
    'xtick.labelsize':  8,
    'ytick.labelsize':  8,
    'legend.fontsize':  8,
    'figure.titlesize': 8,
    'figure.dpi':       300,
})
GRID_KW       = dict(alpha=0.3,  color='k', linestyle='--', linewidth=0.5)
MINOR_GRID_KW = dict(alpha=0.08, color='k', linestyle='-',  linewidth=0.3)
COLORS  = dict(cs3='steelblue', hist='indianred', synth='#d4aaaa')

_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_VIC_GRID_DIR = REPO_ROOT / "mod_forcing" / "vic" / "reference" / "GridInfo"

# %% settings
LOCATION   = 'CS3_8RI_OROVI'   # CS3_8RI_OROVI | CS3_I_SHSTA
GRID_INFO  = str(_VIC_GRID_DIR / f'{LOCATION}_GridInfo.txt')
METEO_COLS = ['Year', 'Month', 'Day', 'PRECIP', 'TMAX', 'TMIN']
_FIG_DIR = str(_gen / "_0_stochastic_precipitation")
os.makedirs(_FIG_DIR, exist_ok=True)

# ============================================================
# %% helpers
# ============================================================

def _rolling(series, window):
    return series.rolling(window=window, min_periods=window).mean()


def _legend_handles(cs3=False):
    handles = []
    if cs3:
        handles.append(Line2D([0], [0], color=COLORS['cs3'], label='CS3 (Historical)'))
    handles += [
        Line2D([0], [0], color=COLORS['hist'], label='Product A (Historical)'),
        Rectangle((0, 0), 1, 1, facecolor=COLORS['synth'], edgecolor='none', alpha=0.7, label='Product B (Stoch)'),
    ]
    return handles


def gather_precip(meteo_dir, grid_info, start_date):
    """Area-weighted precipitation from WGEN meteo files. Returns (daily, monthly, annual)."""
    precip = pd.Series(dtype=float)
    area_sum = 0.0
    for _, row in grid_info.iterrows():
        path = os.path.join(meteo_dir, f"meteo_{row.Lat}_{row.Lon}")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Meteo file not found: {path}")
        df = pd.read_csv(path, sep='  ', header=None, engine='python', names=METEO_COLS)
        precip = precip.add(df['PRECIP'], fill_value=0)
        area_sum += row['f2'] / row['f1']
    precip = (precip / area_sum) * 0.0393701  # mm → in
    precip.index = pd.date_range(start=start_date, periods=len(precip), freq='D')
    return precip, precip.resample('M').sum(), precip.resample('A').sum()


def _grid(ax, axis='both'):
    ax.minorticks_on()
    ax.grid(which='major', axis=axis, **GRID_KW)
    ax.grid(which='minor', axis=axis, **MINOR_GRID_KW)


def _ecdf(series):
    vals = np.sort(series.astype(float).values)
    return vals, np.arange(1, vals.size + 1) / vals.size


# ============================================================
# %% load precipitation
# ============================================================

grid_info = pd.read_csv(GRID_INFO, sep=r'\s+', header=None, names=['id', 'Lat', 'Lon', 'f1', 'f2'])

hist_precip,  hist_precip_monthly,  hist_precip_annual  = gather_precip(str(get_base_dir() / 'WGEN' / 'Product_A' / '1'), grid_info, '1915-01-01')
stoch_precip, stoch_precip_monthly, stoch_precip_annual = gather_precip(str(get_base_dir() / 'WGEN' / 'Product_B' / '1'), grid_info, '2025-01-01')

# Split stochastic annual into 100-yr traces
TRACE_LEN = 100
n_traces = min(10, len(stoch_precip_annual) // TRACE_LEN)
if n_traces < 10:
    print(f'Warning: only {n_traces} full 100-yr traces available.')
stoch_traces = [
    stoch_precip_annual.iloc[i*TRACE_LEN:(i+1)*TRACE_LEN].rename(f'Synthetic {i+1:02d}')
    for i in range(n_traces)
]

# ============================================================
# %% plot 1 — rolling precip means (2, 5, 20 yr, shared x-axis)
# ============================================================

fig, axes = plt.subplots(3, 1, figsize=(6.5, 6), sharex=True)
for i, w in enumerate([2, 5, 20]):
    ax = axes[i]
    for tr in stoch_traces:
        ax.plot(_rolling(tr, w), color=COLORS['synth'], alpha=0.7, linewidth=0.9, zorder=0)
    ax.plot(_rolling(hist_precip_annual, w),
            color=COLORS['hist'], linewidth=1.4, label='Product A (Historical)')
    ax.set(ylabel=f'{w}-Yr Rolling\nMean Precip (in)',
           title=f'{LOCATION} — {w}-Year Rolling Mean Precipitation')
    _grid(ax)

axes[0].legend(handles=_legend_handles(), bbox_to_anchor=(1.01, 1), loc='upper left')
axes[-1].set_xlabel('Year')
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_precip_rolling_means.svg')
plt.show()

# ============================================================
# %% plot 2 — rolling precip KDEs (1, 2, 5, 10 yr)
# ============================================================

fig, axes = plt.subplots(4, 1, figsize=(6.5, 5), sharex=True)
for i, w in enumerate([1, 2, 5, 10]):
    ax = axes[i]
    hist_roll  = _rolling(hist_precip_annual, w).dropna()
    synth_roll = pd.concat([_rolling(tr, w).dropna() for tr in stoch_traces], ignore_index=True)

    if not synth_roll.empty:
        sns.kdeplot(x=synth_roll, ax=ax, color=COLORS['synth'], linewidth=2, fill=True, alpha=0.3,
                    label='Product B (all traces)', clip=(synth_roll.min(), synth_roll.max()))
    sns.kdeplot(x=hist_roll, ax=ax, color=COLORS['hist'], linewidth=1.5, fill=False,
                label='Product A (Historical)', clip=(hist_roll.min(), hist_roll.max()))
    if not hist_roll.empty:
        ax.axvline(hist_roll.mean(), color=COLORS['hist'], linestyle='--', linewidth=1, alpha=0.9,
                   label='Product A mean' if i == 0 else None)
    if not synth_roll.empty:
        ax.axvline(synth_roll.mean(), color=COLORS['synth'], linestyle='--', linewidth=1.2, alpha=0.9,
                   label='Product B mean' if i == 0 else None)
    ax.text(0.01, 0.96, f'{w}-yr window', transform=ax.transAxes,
            ha='left', va='top', fontweight='bold')
    ax.set_ylabel('Density')
    if i == 0:
        ax.legend(loc='upper right')

axes[-1].set_xlabel('Rolling annual precipitation (in)')
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_precip_rolling_kdes.svg')

# ============================================================
# %% plot 3 — January daily precip ECDF
# ============================================================

THRESHOLD = 0.1
hist_jan  = hist_precip[hist_precip.index.month == 1]
hist_jan  = hist_jan[hist_jan > THRESHOLD].dropna()
stoch_jan = stoch_precip[stoch_precip.index.month == 1]
stoch_jan = stoch_jan[stoch_jan > THRESHOLD].dropna()

hx, hp = _ecdf(hist_jan)
sx, sp = _ecdf(stoch_jan)

fig, ax = plt.subplots(figsize=(6.5, 4))
if hx.size:
    ax.step(hx, hp, where='post', color=COLORS['hist'], linewidth=2,
            label=f'Product A (Historical) (n={hx.size})')
if sx.size:
    ax.step(sx, sp, where='post', color=COLORS['synth'], linewidth=2, alpha=0.8,
            label=f'Product B (Stoch) (n={sx.size})')
ax.set(xlabel='January daily precipitation (in)', ylabel='Empirical CDF',
       title=f'{LOCATION} — January Daily Precipitation ECDF (>{THRESHOLD} in)')
_grid(ax)
ax.legend(loc='lower right')
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_jan_daily_precip_ecdf.svg')
plt.show()

# ============================================================
# %% save precipitation outputs
# ============================================================

_out = _FIG_DIR
for data, name in [
    (hist_precip,          'hist_daily'),
    (hist_precip_monthly,  'hist_monthly'),
    (hist_precip_annual,   'hist_annual'),
    (stoch_precip,         'stoch_daily'),
    (stoch_precip_monthly, 'stoch_monthly'),
    (stoch_precip_annual,  'stoch_annual'),
]:
    data.to_csv(f'{_out}/{LOCATION}_precip_{name}.csv', header=False)
