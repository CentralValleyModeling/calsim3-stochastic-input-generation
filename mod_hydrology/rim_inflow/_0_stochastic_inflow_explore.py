# %% imports
import os
import sys
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir, REPO_ROOT

# %% style
sns.set_style("ticks")
plt.rcParams.update({
    'font.size':        9,
    'axes.titlesize':   9,
    'axes.labelsize':   9,
    'xtick.labelsize':  9,
    'ytick.labelsize':  9,
    'legend.fontsize':  9,
    'figure.titlesize': 9,
    'figure.dpi':       300,
})
GRID_KW       = dict(alpha=0.3,  color='k', linestyle='--', linewidth=0.5)
MINOR_GRID_KW = dict(alpha=0.08, color='k', linestyle='-',  linewidth=0.3)
COLORS  = dict(cs3='steelblue', hist='indianred', synth='#d4aaaa')

_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_VIC_GRID_DIR = REPO_ROOT / "mod_forcing" / "vic" / "reference" / "GridInfo"

# %% settings
LOCATION    = 'CS3_8RI_OROVI'   # CS3_8RI_OROVI | CS3_I_SHSTA
CS3_PATH    = 'UNIMP_OROV/FLOW-UNIMPAIRED'
CS3_DSS     = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
MATCHED_KEY = LOCATION.replace('CS3_', '')          # e.g., '8RI_OROVI'
CALSIM_KEY  = CS3_PATH.split('/')[0]                # e.g., 'UNIMP_OROV'
HIST_CSV    = str(_gen / "_2_qmap_historical_validation" / "Product_A" / "calsim_qmap_validation_TS.csv")
STOCH_DIR   = str(_gen / "_3_qmap_product_b")
GRID_INFO   = str(_VIC_GRID_DIR / f'{LOCATION}_GridInfo.txt')
METEO_COLS = ['Year', 'Month', 'Day', 'PRECIP', 'TMAX', 'TMIN']
_FIG_DIR = str(_gen / "_0_stochastic_inflow_explore")
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
# %% load flows
# ============================================================

# CS3 baseline (L2020A)
fid = HecDss.Open(CS3_DSS)
_ts = fid.read_ts(f"/CALSIM/{CS3_PATH}//1MON/L2020A/")
cs3 = pd.DataFrame(
    {LOCATION: _ts.values},
    index=pd.date_range(start='1920-10-31', periods=len(_ts.values), freq='M')
)
cs3 = cs3.loc[cs3.index <= '2021-09-30']
cs3_annual = cs3.resample('AS-OCT').sum()

# WGEN historical (qmap-adjusted)
_hist_all = pd.read_csv(HIST_CSV)
_hist = _hist_all.loc[
    (_hist_all['CalSim'] == CALSIM_KEY) & (_hist_all['Matched_inflow'] == MATCHED_KEY),
    ['Year', 'Month', 'qmap_postAdj']
].copy()
_hist.index = pd.to_datetime(_hist['Year'].astype(str) + '-' + _hist['Month'].astype(str) + '-01')
wgen_hist = _hist[['qmap_postAdj']].rename(columns={'qmap_postAdj': LOCATION})
wgen_hist_annual = wgen_hist.resample('AS-OCT').sum()
wgen_hist_annual = wgen_hist_annual.loc[(wgen_hist_annual.index.year >= 1915) & (wgen_hist_annual.index.year <= 2017)]

# WGEN stochastic (qmap-adjusted)
_files = sorted(glob.glob(os.path.join(STOCH_DIR, f'{CALSIM_KEY}_{MATCHED_KEY}_qmo_n*.csv')))
_chunks = []
for i, f in enumerate(_files):
    df = pd.read_csv(f)[['Year', 'Month', 'qmap_postAdj']].copy()
    _chunks.append(df.rename(columns={'qmap_postAdj': f'{LOCATION}_{i+1:02d}'}).set_index(['Year', 'Month']))
wgen = pd.concat(_chunks, axis=1).reset_index().rename(columns={'Year': 'year', 'Month': 'month'})
wgen['year'] = np.where(wgen['month'] >= 10, wgen['year'] + 1, wgen['year']).astype(int)
wgen = wgen.loc[(wgen['year'] >= 1921) & (wgen['year'] <= 2021)]
wgen_annual = wgen.groupby('year').sum().drop(columns='month')
syn_cols = sorted([c for c in wgen_annual.columns if c.startswith(f'{LOCATION}_')])

# ============================================================
# %% plot 1 — single 30-year rolling mean panel
# ============================================================

fig, ax = plt.subplots(figsize=(6.5, 4))
ax.plot(_rolling(cs3_annual[LOCATION], 30),
        color=COLORS['cs3'], linewidth=2, label='CS3 (Historical)')
ax.plot(_rolling(wgen_hist_annual[LOCATION], 30),
        color=COLORS['hist'], linewidth=2, linestyle='-', label='Product A (Historical)')
for col in syn_cols:
    ax.plot(pd.date_range('1916-10-01', periods=len(wgen_annual), freq='A'),
            _rolling(wgen_annual[col], 30),
            color=COLORS['synth'], alpha=0.6, linewidth=1, zorder=0)
ax.set(xlabel='Year', ylabel='30-Year Rolling Mean Flow',
       title=f'{LOCATION} — 30-Year Rolling Mean')
ax.legend(handles=_legend_handles(cs3=True), bbox_to_anchor=(1.05, 1), loc='upper left')
_grid(ax)
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_rolling30yr.svg')
plt.show()

# ============================================================
# %% plot 2 — 4-row rolling means (flows, shared x-axis)
# ============================================================

cs3_dates = pd.date_range('1920-10-01', periods=len(cs3_annual), freq='A')
syn_dates = pd.date_range('1916-10-01', periods=len(wgen_annual), freq='A')

import matplotlib.dates as mdates

fig, axes = plt.subplots(3, 1, figsize=(6.5, 6), sharex=True)
for i, w in enumerate([2, 5, 20]):
    ax = axes[i]
    for col in syn_cols:
        ax.plot(syn_dates, _rolling(wgen_annual[col], w), color=COLORS['synth'], linewidth=0.9, zorder=0)
    ax.plot(wgen_hist_annual.index, _rolling(wgen_hist_annual[LOCATION], w), color=COLORS['hist'], linewidth=1.4)
    ax.plot(cs3_dates,              _rolling(cs3_annual[LOCATION], w),       color=COLORS['cs3'],  linewidth=1.4)
    ax.set(ylabel=f'{w}-Yr Rolling\nMean Flow (TAF)', title=f'{LOCATION} — {w}-Year Rolling Mean')
    _grid(ax)

axes[0].legend(handles=_legend_handles(cs3=True), bbox_to_anchor=(1.01, 1), loc='upper left')
axes[-1].set_xlabel('Year')
axes[-1].xaxis.set_major_locator(mdates.YearLocator(10))
axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_rolling_means.svg')
plt.show()

# ============================================================
# %% plot 2b — mean-annual flow bar chart
# ============================================================

_syn_means  = [wgen_annual[c].mean() for c in syn_cols]
_syn_center = np.mean(_syn_means)
_syn_min    = np.min(_syn_means)
_syn_max    = np.max(_syn_means)
_cs3_mean   = cs3_annual[LOCATION].mean()
_hist_mean  = wgen_hist_annual[LOCATION].mean()

_labels = ['CS3\n(Historical)', 'Product A\n(Historical)', 'Product B\n(Stoch)']
_vals   = [_cs3_mean, _hist_mean, _syn_center]
_colors = [COLORS['cs3'], COLORS['hist'], COLORS['synth']]
_yerr_lo = [0, 0, _syn_center - _syn_min]
_yerr_hi = [0, 0, _syn_max    - _syn_center]

fig, ax = plt.subplots(figsize=(3, 3))
bars = ax.bar(_labels, _vals, color=_colors, edgecolor='k', linewidth=0.6, width=0.75, zorder=2)
ax.errorbar(
    [2], [_syn_center],
    yerr=[[_syn_center - _syn_min], [_syn_max - _syn_center]],
    fmt='none', color='k', capsize=4, linewidth=1, zorder=3
)
ax.set(ylabel='Mean Annual Flow (TAF)', title=f'{LOCATION}')
ax.set_ylim(bottom=0)
_grid(ax, axis='y')
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_mean_annual_bar.svg')

# ============================================================
# %% plot 3 — drought severity scatter (duration vs % of average)
# ============================================================

MAX_DUR     = 15
YEAR_ONE    = 1921   # water year where trace index = 1
SHARED_MEAN = True  # True  → use CS3 mean for all series
             #         False → CS3 uses its own mean; Product A/B use Product B grand mean


def _find_droughts(series, mean):
    """Find all complete, non-overlapping consecutive below-mean runs.

    A drought of duration w is counted exactly once at that length —
    a 2-year below-average run that is part of a 3-year below-average run
    is only recorded as duration 3. Single-year dips are ignored.

    Returns list of (duration, pct_of_mean, start_idx, end_idx).
    """
    arr   = series.values
    idxs  = series.index.tolist()
    out   = []
    i     = 0
    while i < len(arr):
        if arr[i] < mean:
            j = i + 1
            while j < len(arr) and arr[j] < mean:
                j += 1
            dur = j - i
            if dur >= 2:
                pct = arr[i:j].mean() / mean * 100
                out.append((dur, pct, idxs[i], idxs[j - 1]))
            i = j
        else:
            i += 1
    return out  # [(duration, pct_of_mean, start_idx, end_idx), ...]


# ------- reference means -------
_cs3_int       = cs3_annual[LOCATION].copy()
_cs3_int.index = _cs3_int.index.year + 1   # AS-OCT: 1920-10-01 = WY1921
cs3_mean       = _cs3_int.mean()

syn_mean = wgen_annual[syn_cols].values.mean()   # Product B grand mean

if SHARED_MEAN:
    hist_mean = cs3_mean
    prod_b_mean = cs3_mean
else:
    hist_mean = syn_mean
    prod_b_mean = syn_mean

# ------- detect droughts -------
cs3_droughts  = _find_droughts(_cs3_int, cs3_mean)

_hist       = wgen_hist_annual[LOCATION].copy()
_hist.index = _hist.index.year + 1   # AS-OCT: same WY offset
hist_droughts = _find_droughts(_hist, hist_mean)

syn_droughts = []   # (duration, pct, label)
for ci, col in enumerate(syn_cols):
    tn = ci + 1
    for dur, pct, s_yr, e_yr in _find_droughts(wgen_annual[col], prod_b_mean):
        yr_s = s_yr - YEAR_ONE + 1
        yr_e = e_yr - YEAR_ONE + 1
        syn_droughts.append((dur, pct, f"n{tn:02d} ({yr_s}–{yr_e})"))

# ------- dynamic x-axis limit -------
all_durs = (
    [d for d, *_ in cs3_droughts]
    + [d for d, *_ in hist_droughts]
    + [d for d, *_ in syn_droughts]
)
x_max = max(all_durs) + 1 if all_durs else MAX_DUR + 1

# ------- plot -------
fig, ax = plt.subplots(figsize=(6.5, 4.5))

if cs3_droughts:
    ax.scatter([d for d, *_ in cs3_droughts], [p for _, p, *_ in cs3_droughts],
               color=COLORS['cs3'], s=35, zorder=3, label='CS3 (Historical)')

if hist_droughts:
    ax.scatter([d for d, *_ in hist_droughts], [p for _, p, *_ in hist_droughts],
               color=COLORS['hist'], s=35, zorder=3, label='Product A (Historical)')

if syn_droughts:
    sd, sp, sl = zip(*syn_droughts)
    ax.scatter(sd, sp, color=COLORS['synth'], s=20, alpha=0.7, zorder=1, label='Product B (Stoch)')



_ARROW = dict(arrowstyle='-', color='0.4', lw=0.6,
              shrinkA=0, shrinkB=3)

# Annotate worst (lowest %) Product B point per duration
_worst: dict = {}
for dur, pct, lbl in syn_droughts:
    if dur not in _worst or pct < _worst[dur][0]:
        _worst[dur] = (pct, lbl)
for dur, (pct, lbl) in _worst.items():
    ax.annotate(lbl, xy=(dur, pct), xytext=(6, -14),
                textcoords='offset points', fontsize=7, color='k',
                arrowprops=_ARROW)

# Annotate worst (lowest %) CS3 point per duration
_cs3_worst: dict = {}
for dur, pct, s_yr, e_yr in cs3_droughts:
    if dur not in _cs3_worst or pct < _cs3_worst[dur][0]:
        _cs3_worst[dur] = (pct, f"{s_yr}–{e_yr}")
for dur, (pct, lbl) in _cs3_worst.items():
    ax.annotate(lbl, xy=(dur, pct), xytext=(-6, 10),
                textcoords='offset points', fontsize=7, ha='left', va='bottom',
                color=COLORS['cs3'], arrowprops={**_ARROW, 'color': COLORS['cs3']})

if SHARED_MEAN:
    ax.set(xlabel='Duration (years)', ylabel='Percent of average (%)',
        title=f'{LOCATION} — Drought Severity by Duration\n (Shared mean: {cs3_mean:.1f} TAF)')
else:
    ax.set(xlabel='Duration (years)', ylabel='Percent of average (%)',
        title=f'{LOCATION} — Drought Severity by Duration\n (CS3 mean: {cs3_mean:.1f} TAF; Product A/B mean: {prod_b_mean:.1f} TAF)')
ax.set_xlim(1, x_max)
ax.spines[['top', 'right']].set_visible(False)
ax.legend(loc='upper right')
plt.tight_layout()
plt.savefig(f'{_FIG_DIR}/{LOCATION}_drought_scatter_{"shared" if SHARED_MEAN else "separate"}.svg')
plt.show()


# %%
