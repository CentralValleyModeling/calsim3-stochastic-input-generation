"""Diagnose n03/n07 SJR cycle 14 infeasibility: extreme low-flow failure at Jul 1922.


Error summary (from error_screenshots/)
----------------------------------------
n03 -- 1922_07_c14 Solve_c__ infeasible (Linear relaxation not feasible)
  Two constraint groups:
  1. Mokelumne allocation (mok ws.wresl):
     - :232  setannalloc60n_na5adjusteddv = -4.8116
     - :235  set_d_mok050_60n_na5 < -8.6777  (negative delivery upper bound)
     - :236  set_d_mok039_60n_na5 < -0.6675
     - :237  set_d_mok033_60n_na5 < -4.0051
  2. Bear Creek / Deadman Creek seepage (constraints-seepage sjreast init.wresl):
     - :128-131  setnegsg105_bck040_15 .. setnegsg108_bck024_15  (surplus_set*)
     - :166-171  setnegsg93_ded044_13 .. setnegsg98_ded019_13   (surplus_set*)
     Also: merced ops.wresl:611  setd_bck006_esc004_wr_2
       d_bck006_esc004_wr - sg105..sg111_bck*_15 < 0

n07 -- 1922_07_c14 Solve_c__ infeasible (Linear relaxation not feasible)
  Mokelumne allocation only (mok ws.wresl):
     - :232  setannalloc60n_na5adjusteddv = -4.9599
     - :235  set_d_mok050_60n_na5 < -8.8135
     - :236  set_d_mok039_60n_na5 < -0.6780
     - :237  set_d_mok033_60n_na5 < -4.0678
  (No seepage group -- only the Mokelumne constraints fire for n07.)
"""
# %% Imports and paths
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from utils.paths import get_base_dir, get_generated_dir
COMPILED = (get_generated_dir() / "postprocessing" / "sv_compile"
            / "product_b_compilation" / "_product_b_compiled_sv")
RIM_DIR = (get_generated_dir() / "postprocessing" / "sv_compile"
           / "product_b_compilation" / "compiled_input_files" / "rim_inflow")
DSS_PATH = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
OUT_DIR = Path(__file__).resolve().parent


def load_calsim_hist(wanted_vars):
    """Read monthly inflows from CalSim default DSS (WY1922-WY2021)."""
    full_idx = pd.date_range("1921-01-31", "2021-12-31", freq="ME")
    with HecDss.Open(str(DSS_PATH), version=6, catalog_flag=True) as fid:
        paths = fid.getPathnameList("/*/*/*/*/1MON/*")
        buckets = {}
        for p in paths:
            part_b = p.strip("/").split("/")[1].upper()
            buckets.setdefault(part_b, []).append(p)
        data = {}
        for var in wanted_vars:
            if var not in buckets:
                continue
            master = pd.Series(index=full_idx, dtype="float64")
            for p in sorted(buckets[var],
                            key=lambda x: x.strip("/").split("/")[3]):
                ts = fid.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan
                idx = (pd.to_datetime(ts.pytimes)
                       .to_period("M") - 1).to_timestamp("M")
                master.update(pd.Series(vals, index=idx))
            if master.notna().any():
                data[var] = master
    df = pd.DataFrame(data, index=full_idx)
    df.index.name = "date"
    return df.reset_index()

FAILING = {1, 3, 4, 5, 6, 7}
PASSING = {2, 8, 9, 10}

FAIL_YEAR, FAIL_MONTH = 1922, 7

SJR_INFLOW_VARS = ['I_MLRTN', 'I_MCLRE', 'I_NHGAN', 'I_PEDRO', 'I_MOK079', 'I_PARDE']
SJR_KEY_VARS = SJR_INFLOW_VARS + [
    'UNIMP_SJ', 'I_BCK040', 'I_DED044', 'I_SJR258', 'I_SJR265',
    'CT_PEDRO_SV', 'CT_MERCED_SV', 'REST_REQ_P', 'REST_REQ_NP',
    'S_PEDROLEVEL4', 'S_PEDRO_SV', 'E_PEDRO_SV',
]


# %% Section 1: Fail/pass SJR variable comparison across all chunks
# Loads all 10 compiled SV files -- ~19M rows total.
print("=" * 80)
print("SECTION 1: FAIL vs PASS SJR VARIABLE COMPARISON")
print("=" * 80)

sjr_patterns = ['SJR', 'STAN', 'TUOL', 'MERC', 'MOK', 'UNIMP_SJ', 'BCK', 'ESC',
                'PEDRO', 'MCLRE', 'NHGAN', 'EXCHEQ', 'MLRTN', 'REST_REQ', 'MINFLOW']
pat = '|'.join(sjr_patterns)

frames = []
for i in range(1, 11):
    print(f"  Loading n{i:02d}...")
    df = pd.read_csv(COMPILED / f"ProductB_SV_n{i:02d}.csv")
    df['chunk'] = i
    df['status'] = 'FAIL' if i in FAILING else 'PASS'
    frames.append(df)

big = pd.concat(frames, ignore_index=True)
del frames
print(f"Loaded all 10 chunks: {len(big):,} rows")

sjr_mask = big['Part B'].str.upper().str.contains(pat, na=False)
sjr_df = big[sjr_mask]
sjr_vars = sorted(sjr_df['Part B'].unique())
print(f"SJR-related variables: {len(sjr_vars)} of {big['Part B'].nunique()} total")


def compare_fail_pass(subset):
    """Per-variable fail vs pass mean/min/max with relative diff."""
    grp = subset.groupby(['Part B', 'status'])['Value'].agg(['mean', 'min', 'max']).reset_index()
    fail = grp[grp['status'] == 'FAIL'].set_index('Part B')
    pas = grp[grp['status'] == 'PASS'].set_index('Part B')
    common = fail.index.intersection(pas.index)
    if common.empty:
        return pd.DataFrame()
    r = pd.DataFrame({
        'var': common,
        'fail_mean': fail.loc[common, 'mean'].values,
        'pass_mean': pas.loc[common, 'mean'].values,
        'fail_min': fail.loc[common, 'min'].values,
        'pass_min': pas.loc[common, 'min'].values,
        'fail_max': fail.loc[common, 'max'].values,
        'pass_max': pas.loc[common, 'max'].values,
    })
    denom = np.maximum(np.abs(r['fail_mean']), np.abs(r['pass_mean']))
    denom = np.maximum(denom, 1e-6)
    r['diff_pct'] = ((r['fail_mean'] - r['pass_mean']) / denom * 100).round(1)
    return r.sort_values('diff_pct', ascending=False, key=abs)


rdf = compare_fail_pass(sjr_df)
if not rdf.empty:
    print(rdf.to_string(index=False))

# Error-referenced variables (BCK/DED/MOK seepage)
err_patterns = ['SG\\d', 'BCK', 'DED', 'MOK', 'ANNALLOC', 'D_MOK']
err_mask = big['Part B'].str.upper().str.contains('|'.join(err_patterns), na=False, regex=True)
err_cmp = compare_fail_pass(big[err_mask])
if not err_cmp.empty:
    print("\nError-referenced variables (BCK/DED/MOK):")
    print(err_cmp.to_string(index=False))

# Per-chunk annual inflow stats
print("\nPer-chunk SJR inflow annual stats:")
inflow_df = big[big['Part B'].isin(SJR_INFLOW_VARS)].copy()
inflow_df['WY'] = inflow_df['Year'] + (inflow_df['Month'] >= 10).astype(int)
wy_sums = inflow_df.groupby(['Part B', 'chunk', 'status', 'WY'])['Value'].sum().reset_index()
chunk_stats = wy_sums.groupby(['Part B', 'chunk', 'status'])['Value'].agg(
    ann_min='min', ann_max='max', ann_mean='mean'
).reset_index()
mon_stats = inflow_df.groupby(['Part B', 'chunk', 'status'])['Value'].agg(
    mon_min='min', mon_max='max'
).reset_index()
merged = chunk_stats.merge(mon_stats, on=['Part B', 'chunk', 'status'])

for var in SJR_INFLOW_VARS:
    print(f"\n--- {var} ---")
    print(f"  {'chunk':>5s}  {'status':>5s}  {'ann_min':>10s}  {'ann_max':>10s}  {'ann_mean':>10s}  {'mon_min':>10s}  {'mon_max':>10s}")
    sub = merged[merged['Part B'] == var].sort_values('chunk')
    for _, row in sub.iterrows():
        print(f"  n{int(row['chunk']):02d}    {row['status']}   {row['ann_min']:10.1f}  {row['ann_max']:10.1f}  {row['ann_mean']:10.1f}  {row['mon_min']:10.1f}  {row['mon_max']:10.1f}")


# %% Section 2: BCK/DED/MOK/PARDE values at Jul 1922 (n03, n07 vs passing)
print("\n" + "=" * 80)
print("SECTION 2: BCK/DED/MOK/PARDE AT JUL 1922 (n03/n07 vs PASSING)")
print("=" * 80)

for chunk_id in [3, 7, 2, 8]:
    df_c = big[big['chunk'] == chunk_id]
    row = df_c[(df_c['Year'] == FAIL_YEAR) & (df_c['Month'] == FAIL_MONTH)]
    tag = "FAIL" if chunk_id in FAILING else "PASS"
    print(f"\n=== n{chunk_id:02d} ({tag}) at {FAIL_YEAR}-{FAIL_MONTH:02d} ===")

    for search_pat in ['BCK', 'BUR', 'DED', 'MOK', 'PARDE']:
        matches = row[row['Part B'].str.upper().str.contains(search_pat, na=False)]
        for _, r in matches.iterrows():
            print(f"  {r['Part B']:35s} = {r['Value']:12.4f}")

    for v in ['I_MLRTN', 'I_MCLRE', 'I_PEDRO', 'I_NHGAN', 'UNIMP_SJ', 'REST_REQ_NP']:
        val = row.loc[row['Part B'] == v, 'Value']
        if not val.empty:
            print(f"  {v:35s} = {val.values[0]:12.4f}")


# %% Section 3: Mokelumne context -- WY1922 time series (n03 vs n02)
print("\n" + "=" * 80)
print("SECTION 3: MOKELUMNE CONTEXT -- WY1922 TIME SERIES")
print("=" * 80)

wy_months_1922 = [(1921, 10), (1921, 11), (1921, 12),
                  (1922, 1), (1922, 2), (1922, 3),
                  (1922, 4), (1922, 5), (1922, 6), (1922, 7)]

for chunk_id in [3, 7, 2]:
    df_c = big[big['chunk'] == chunk_id]
    tag = "FAIL" if chunk_id in FAILING else "PASS"
    print(f"\n--- n{chunk_id:02d} ({tag}) ---")
    for var in ['I_MOK079', 'I_PARDE', 'DRN_MOK', 'IRR_MOK', 'SEEP_MOK']:
        sub = df_c[df_c['Part B'] == var]
        if sub.empty:
            continue
        print(f"  {var}:")
        for y, m in wy_months_1922:
            val = sub.loc[(sub['Year'] == y) & (sub['Month'] == m), 'Value']
            if not val.empty:
                print(f"    {y}-{m:02d}: {val.values[0]:10.3f}")


# %% Section 4: Cross-chunk snapshot at Jul 1922
print("\n" + "=" * 80)
print("SECTION 4: ALL 10 CHUNKS AT JUL 1922")
print("=" * 80)

header = f"{'Variable':<20s}"
for i in range(1, 11):
    tag = "F" if i in FAILING else "P"
    header += f"  {'n' + str(i).zfill(2) + '(' + tag + ')':>12s}"
print(header)
print("-" * (20 + 14 * 10))

for var in SJR_KEY_VARS:
    line = f"{var:<20s}"
    for i in range(1, 11):
        df_c = big[(big['chunk'] == i) & (big['Year'] == FAIL_YEAR) &
                    (big['Month'] == FAIL_MONTH) & (big['Part B'] == var)]
        v = df_c['Value'].iloc[0] if not df_c.empty else float('nan')
        line += f"  {v:12.3f}"
    print(line)

# Snapshot comparison: n03 vs n02 (detailed)
print("\n--- n03 vs n02 at Jul 1922 ---")
print(f"{'Variable':<30s}  {'n03 (FAIL)':>14s}  {'n02 (PASS)':>14s}  {'Difference':>12s}  {'Diff%':>8s}")
print("-" * 90)
for var in sjr_vars:
    v3 = big[(big['chunk'] == 3) & (big['Year'] == FAIL_YEAR) &
             (big['Month'] == FAIL_MONTH) & (big['Part B'] == var)]
    v2 = big[(big['chunk'] == 2) & (big['Year'] == FAIL_YEAR) &
             (big['Month'] == FAIL_MONTH) & (big['Part B'] == var)]
    if v3.empty and v2.empty:
        continue
    vf = v3['Value'].iloc[0] if not v3.empty else float('nan')
    vr = v2['Value'].iloc[0] if not v2.empty else float('nan')
    diff = vf - vr
    denom = max(abs(vf), abs(vr), 1e-6)
    dpct = diff / denom * 100
    print(f"{var:<30s}  {vf:14.3f}  {vr:14.3f}  {diff:12.3f}  {dpct:7.1f}%")


# %% Section 5: WY1922 totals and percentile ranks
print("\n" + "=" * 80)
print("SECTION 5: WY1922 TOTALS AND PERCENTILE RANKS")
print("=" * 80)

for chunk_id in [3, 7]:
    df_c = big[big['chunk'] == chunk_id].copy()
    df_c['WY'] = df_c['Year'] + (df_c['Month'] >= 10).astype(int)
    wy_data = df_c[df_c['WY'] == FAIL_YEAR]

    print(f"\n--- n{chunk_id:02d}: WY {FAIL_YEAR} ---")
    print(f"{'Variable':<25s}  {'WY Total':>12s}  {'All-WY Med':>12s}  {'All-WY P95':>12s}  {'Pctile':>8s}")
    print("-" * 75)

    for var in SJR_KEY_VARS:
        wy_val = wy_data.loc[wy_data['Part B'] == var, 'Value']
        if wy_val.empty:
            continue
        wy_sum = wy_val.sum()
        all_wy = df_c[df_c['Part B'] == var].groupby('WY')['Value'].sum()
        med = all_wy.median()
        p95 = all_wy.quantile(0.95)
        pctile = (all_wy < wy_sum).sum() / len(all_wy) * 100
        print(f"{var:<25s}  {wy_sum:12.1f}  {med:12.1f}  {p95:12.1f}  {pctile:7.1f}%")


# %% Section 6: May-Jul average drought severity comparison
print("\n" + "=" * 80)
print("SECTION 6: MAY-JUL AVERAGE DROUGHT SEVERITY")
print("=" * 80)

# Load CalSim historical baseline (default DSS, 1921-2021)
hist = load_calsim_hist(SJR_INFLOW_VARS + ['I_BCK040', 'I_DED044'])
hist['date'] = pd.to_datetime(hist['date'])
hist['Year'] = hist['date'].dt.year
hist['Month'] = hist['date'].dt.month
hist['WY'] = hist['Year'] + (hist['Month'] >= 10).astype(int)
hist = hist.dropna(subset=['I_MLRTN'])

# Historical May-Jul averages by WY
hist_mjj = hist[hist['Month'].isin([5, 6, 7])]
hist_wy_avg = hist_mjj.groupby('WY')[SJR_INFLOW_VARS].mean()
hist_wy_avg['Total'] = hist_wy_avg.sum(axis=1)

print("\nLowest 5 historical May-Jul totals (TAF/month):")
lowest5 = hist_wy_avg.nsmallest(5, 'Total')
print(lowest5[['Total']].to_string())

print(f"\nHistorical minimum per tributary (May-Jul avg):")
for var in SJR_INFLOW_VARS:
    idx = hist_wy_avg[var].idxmin()
    print(f"  {var:<15s}  min={hist_wy_avg[var].min():.3f}  (WY {idx})")

# n03 and n07 May-Jul WY1922
for chunk_id in [3, 7]:
    df_c = big[big['chunk'] == chunk_id].copy()
    df_c['WY'] = df_c['Year'] + (df_c['Month'] >= 10).astype(int)
    mjj = df_c[(df_c['WY'] == FAIL_YEAR) & (df_c['Month'].isin([5, 6, 7]))]
    print(f"\nn{chunk_id:02d} May-Jul WY{FAIL_YEAR}:")
    total = 0.0
    for var in SJR_INFLOW_VARS:
        vals = mjj.loc[mjj['Part B'] == var, 'Value']
        avg = vals.mean() if not vals.empty else float('nan')
        total += avg if not np.isnan(avg) else 0
        print(f"  {var:<15s}  {avg:.3f}")
    print(f"  {'Total':<15s}  {total:.1f}")

# Overlapping historical period (same calendar WY)
hist_1922 = hist_wy_avg.loc[FAIL_YEAR] if FAIL_YEAR in hist_wy_avg.index else None
if hist_1922 is not None:
    print(f"\nHistorical WY{FAIL_YEAR} May-Jul avg:")
    for var in SJR_INFLOW_VARS:
        print(f"  {var:<15s}  {hist_1922[var]:.3f}")
    print(f"  {'Total':<15s}  {hist_1922['Total']:.1f}")

del big  # free memory before plotting


# %% Section 6b: Report table percentile calculations
# Reproduces the values in the report's Table 1 (Jul 1922 snapshot) and
# Table 2 (May-Jul averages) -- historical comparison + dual percentiles.
print("\n" + "=" * 80)
print("SECTION 6b: REPORT TABLE -- PERCENTILE CALCULATIONS")
print("=" * 80)

TABLE1_VARS = ['I_MOK079', 'I_PARDE', 'I_PEDRO', 'I_NHGAN',
               'I_MCLRE', 'I_MLRTN', 'I_BCK040', 'I_DED044']

# n03 Jul 1922 values (from cross-chunk snapshot)
n03_jul = {
    'I_MOK079': 0, 'I_PARDE': 0, 'I_PEDRO': 0, 'I_NHGAN': 0,
    'I_MCLRE': 2.590, 'I_MLRTN': 15.229, 'I_BCK040': 0, 'I_DED044': 0,
}

# --- Table 1: Jul 1922 snapshot vs historical ---

# Historical Jul 1922 values
hist_jul1922 = hist[(hist['Year'] == 1922) & (hist['Month'] == 7)]
print("\nHistorical Jul 1922:")
for v in TABLE1_VARS:
    if v in hist_jul1922.columns:
        print(f"  {v}: {hist_jul1922[v].iloc[0]:.3f}")

# Historical July minimums
hist_jul = hist[hist['Month'] == 7]
print("\nHistorical July minimum:")
for v in TABLE1_VARS:
    if v in hist_jul.columns:
        idx = hist_jul[v].idxmin()
        wy = hist.loc[idx, 'WY']
        print(f"  {v}: {hist_jul[v].min():.3f} (WY {int(wy)})")

# Stochastic July percentiles (all-chunk July distribution)
print("\nStochastic July percentiles (n03 values vs all-chunk Julys):")
for v in TABLE1_VARS:
    try:
        all_jul = []
        for i in range(1, 11):
            df = pd.read_csv(RIM_DIR / f"{v}_qmo_n{i:02d}.csv")
            all_jul.extend(df[df['Month'] == 7]['qmap_postAdj'].tolist())
        all_jul = np.array(all_jul)
        pct = (all_jul < n03_jul[v]).sum() / len(all_jul) * 100
        print(f"  {v}: {pct:.1f}%  (n={len(all_jul)})")
    except FileNotFoundError:
        print(f"  {v}: no rim file")

# Historical July percentiles (n03 values vs historical July distribution)
print("\nHistorical July percentiles (n03 values vs historical Julys):")
for v in TABLE1_VARS:
    if v in hist_jul.columns:
        h_vals = hist_jul[v].values
        pct = (h_vals < n03_jul[v]).sum() / len(h_vals) * 100
        print(f"  {v}: {pct:.1f}%  (n={len(h_vals)})")

# --- Table 2: May-Jul averages with percentiles ---

n03_mjj = {'I_MOK079': 0.000, 'I_PARDE': 0.000, 'I_PEDRO': 3.836,
           'I_NHGAN': 0.042, 'I_MCLRE': 16.580, 'I_MLRTN': 25.900}
n07_mjj = {'I_MOK079': 0.000, 'I_PARDE': 0.000, 'I_PEDRO': 3.582,
           'I_NHGAN': 0.079, 'I_MCLRE': 15.195, 'I_MLRTN': 22.364}

# Stochastic May-Jul percentiles (per-WY avg across all 10 chunks)
print("\nMay-Jul stochastic percentiles (per-WY avg, all 10 chunks):")
for v in SJR_INFLOW_VARS:
    try:
        all_wy_avgs = []
        for i in range(1, 11):
            df = pd.read_csv(RIM_DIR / f"{v}_qmo_n{i:02d}.csv")
            df['WY'] = df['Year'] + (df['Month'] >= 10).astype(int)
            mjj = df[df['Month'].isin([5, 6, 7])]
            wy_avg = mjj.groupby('WY')['qmap_postAdj'].mean()
            all_wy_avgs.extend(wy_avg.tolist())
        all_wy_avgs = np.array(all_wy_avgs)
        s_pct_n03 = (all_wy_avgs < n03_mjj[v]).sum() / len(all_wy_avgs) * 100
        s_pct_n07 = (all_wy_avgs < n07_mjj[v]).sum() / len(all_wy_avgs) * 100
        print(f"  {v}: n03={s_pct_n03:.1f}%, n07={s_pct_n07:.1f}%  (n={len(all_wy_avgs)})")
    except FileNotFoundError:
        print(f"  {v}: no rim file")

# Historical May-Jul percentiles (per-WY avg, 1921-2021)
print("\nMay-Jul historical percentiles (per-WY avg, 1921-2021):")
for v in SJR_INFLOW_VARS:
    h_vals = hist_wy_avg[v].values
    h_pct_n03 = (h_vals < n03_mjj[v]).sum() / len(h_vals) * 100
    h_pct_n07 = (h_vals < n07_mjj[v]).sum() / len(h_vals) * 100
    print(f"  {v}: n03={h_pct_n03:.1f}%, n07={h_pct_n07:.1f}%")

h_pct_n03_tot = (hist_wy_avg['Total'] < sum(n03_mjj.values())).sum() / len(hist_wy_avg) * 100
h_pct_n07_tot = (hist_wy_avg['Total'] < sum(n07_mjj.values())).sum() / len(hist_wy_avg) * 100
print(f"  Total: n03={h_pct_n03_tot:.1f}%, n07={h_pct_n07_tot:.1f}%")


# %% Section 7: Fig1 -- MOK/PARDE traces around WY1922
print("\n" + "=" * 80)
print("SECTION 7: GENERATING FIG1 (MOK/PARDE TRACES WY1922)")
print("=" * 80)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams.update({'font.size': 8})

# Load per-chunk rim inflow files
mok_chunks = {}
parde_chunks = {}
for i in range(1, 11):
    mok_df = pd.read_csv(RIM_DIR / f"I_MOK079_qmo_n{i:02d}.csv")
    mok_df['Value'] = mok_df['qmap_postAdj']
    parde_df = pd.read_csv(RIM_DIR / f"I_PARDE_qmo_n{i:02d}.csv")
    parde_df['Value'] = parde_df['qmap_postAdj']
    mok_chunks[i] = mok_df
    parde_chunks[i] = parde_df

hist_raw = load_calsim_hist(['I_MOK079', 'I_PARDE'])
hist_raw['date'] = pd.to_datetime(hist_raw['date'])
hist_raw['Year'] = hist_raw['date'].dt.year
hist_raw['Month'] = hist_raw['date'].dt.month
hist_raw = hist_raw.dropna(subset=['I_MOK079'])

fig, axes = plt.subplots(2, 1, figsize=(6.5, 4.5), sharex=True)

# Oct 1921 - Sep 1923
wy_months = []
for y in [1921, 1922, 1923]:
    for m in range(1, 13):
        if (y == 1921 and m < 10) or (y == 1923 and m > 9):
            continue
        wy_months.append((y, m))
date_labels = [f"{y}-{m:02d}" for y, m in wy_months]

for ax_idx, (var_col, chunk_dict, title) in enumerate([
    ('I_MOK079', mok_chunks, 'Mokelumne Inflow (I_MOK079)'),
    ('I_PARDE', parde_chunks, 'Pardee Inflow (I_PARDE)'),
]):
    ax = axes[ax_idx]

    for i in range(1, 11):
        df = chunk_dict[i]
        vals = []
        for y, m in wy_months:
            row = df[(df['Year'] == y) & (df['Month'] == m)]
            vals.append(row['Value'].iloc[0] if not row.empty else np.nan)

        if i in [3, 7]:
            ax.plot(range(len(vals)), vals, color='#d62728', alpha=0.9, lw=1.2,
                    label=f'n{i:02d}', zorder=5)
        else:
            ax.plot(range(len(vals)), vals, color='#999999', alpha=0.3, lw=0.6,
                    label='Other chunks' if i == 1 else None, zorder=2)

    hist_vals = []
    for y, m in wy_months:
        row = hist_raw[(hist_raw['Year'] == y) & (hist_raw['Month'] == m)]
        hist_vals.append(row[var_col].iloc[0] if not row.empty else np.nan)
    ax.plot(range(len(hist_vals)), hist_vals, color='#1f77b4', lw=1.2,
            ls='-', label='CalSim Historical', zorder=6, alpha=0.9)

    fail_idx = wy_months.index((FAIL_YEAR, FAIL_MONTH))
    ax.axvline(fail_idx, color='black', ls=':', lw=0.7, alpha=0.5)
    ax.set_ylabel('TAF/month')
    ax.set_title(title, fontweight='bold')
    ax.legend(loc='upper right', ncol=2,
              handlelength=1.5, handletextpad=0.4, columnspacing=0.8)
    ax.set_xlim(0, len(wy_months) - 1)

axes[1].set_xticks(range(0, len(date_labels), 2))
axes[1].set_xticklabels([date_labels[i] for i in range(0, len(date_labels), 2)],
                         rotation=45, ha='right')
axes[1].set_xlabel('Month')

fig.suptitle('Product B SJR Inflows: WY 1922-1923 (n03/n07 Failure at Jul 1922)',
             fontweight='bold', y=0.99)
plt.tight_layout(rect=[0, 0, 1, 0.96])
fig_path = OUT_DIR / 'fig1_mok_parde_traces_wy1922.png'
fig.savefig(fig_path, dpi=300, bbox_inches='tight')
print(f"Saved {fig_path}")
plt.close()

print("\nDone.")
