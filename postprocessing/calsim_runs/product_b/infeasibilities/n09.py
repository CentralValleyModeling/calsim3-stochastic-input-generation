"""Diagnose n09 SJR cycle 14 infeasibility at April 1962.

Error summary (from WRIMS log screenshots)
-------------------------------------------
n09 -- 1962_04_c14 Solve_c__ infeasible (Linear relaxation not feasible)
       1962_04_c15 also infeasible (sjrbase_gw1)

After applying Fix 4 (relaxed meetSJRR under low storage), April 1962 was
resolved but a new failure appeared at June 1933, Cycle 14 (sjrbase).
Analysis with HiGHS solver showed this was LP UNBOUNDEDNESS (not infeasibility)
caused by D_SJR205_SJR201 having cost=-500K and no effective upper bound when
Fix 4's lowStorage case (lhs>rhs penalty 0) fires. See Fix 5 in
wresl_modifications/SJR_Rest_Req_Cycle1.wresl and the analysis log at
docs/source/calsim-run/n09_jun1933_unboundedness_analysis.md.

Infeasibility analysis identified constraints:
  1. meetsjrr (SJR_Rest_Req_Cycle1.wresl:50):
     D_SJR205_SJR201 = REST_RCH_NP  (SJR Restoration requirement)
  2. continuity16/17/MLRTN (Connectivity-table.wresl:1-3):
     Millerton Lake mass balance
  3. evap_mlrtn (constraints-Reservoirs.wresl:41):
     E_MLRTN evaporation constraint; log shows e_mlrtn ~ -0.189 (negative!)
  4. setpossgXX_sjrYYY_7 (constraints-Seepage_SJREast.wresl:561-573):
     SG54-SG63 seepage >= 0 constraints all violated (< 0)
  5. continuitysjrXXX (constraints-Connectivity.wresl:240-252):
     SJR reach mass balance at nodes 205-265
  6. setpostivect_gravellyford (arcs-Inflows.wresl:196):
     CT_GRAVELLYFORD = 38.65 (closure term at Gravelly Ford)
  7. set_sr_64_sjr214/227 (constraints-Runoff.wresl:128-129):
     WBA64 surface runoff allocation
  8. setr_64_pa1/sjr235 (constraints-Returns.wresl:344-345):
     WBA64 return flows

Hypothesis: SJR restoration flow requirement (REST_RCH_NP) forces a minimum
release from Millerton that is incompatible with the SJR East seepage/connectivity
system under n09's stochastic hydrology at April 1962.
"""
# %% Imports and paths
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from utils.paths import get_base_dir, get_generated_dir

COMPILED = (get_generated_dir() / "postprocessing" / "sv_compile"
            / "product_b_compilation" / "_product_b_compiled_sv")
RIM_DIR = (get_generated_dir() / "postprocessing" / "sv_compile"
           / "product_b_compilation" / "compiled_input_files" / "rim_inflow")
DSS_PATH = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
OUT_DIR = Path(__file__).resolve().parent
DV_DIR = get_generated_dir() / "postprocessing" / "calsim_runs" / "product_b"
CRASH_DSS = DV_DIR / "DCR2023_DV_9.3.1_Danube_Hist_v1.7_ProductB_n09_crash.dss"
DV_N09 = DV_DIR / "dv_out" / "DCR2023_DV_9.3.1_Danube_Hist_v1.7_ProductB_n09.dss"
HIST_DV = (get_base_dir() / "CalSim3" / "Studies" / "9.3.1_danube_hist"
           / "DSS" / "output" / "DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss")

FAIL_CHUNK = 9
FAIL_YEAR = 1962
FAIL_MONTH = 4

MO_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Key SJR/Friant inflow variables
SJR_INFLOW_VARS = [
    'I_MLRTN', 'I_MCLRE', 'I_NHGAN', 'I_PEDRO', 'I_MOK079', 'I_PARDE',
    'I_BCK040', 'I_DED044', 'I_SJR258', 'I_SJR265', 'I_BUR005',
]

# Variables referenced in infeasibility constraints
CONSTRAINT_VARS = [
    'REST_REQ_NP', 'REST_REQ_P', 'REST_RCH_NP',
    'CT_GRAVELLYFORD_SV',
    'ER_MLRTN',
    'UNIMP_SJ',
    'SEEP_SJR_EAST', 'SEEP_SJR_WEST',
    'DRN_SJR_EAST', 'DRN_SJR_WEST',
    'IRR_SJR_EAST', 'IRR_SJR_WEST',
    'SR_64',
]

# Broader SJR system variables
SJR_SYSTEM_VARS = SJR_INFLOW_VARS + CONSTRAINT_VARS + [
    'S_MLRTN_SV', 'E_MLRTN_SV', 'CT_MERCED_SV', 'CT_PEDRO_SV',
    'S_PEDRO_SV', 'S_PEDROLEVEL4', 'E_PEDRO_SV',
    'S_MCLRE_SV', 'E_MCLRE_SV',
    'S_NHGAN_SV', 'E_NHGAN_SV',
    'MINFLOWFEATHER',
]

ALL_CHECK_VARS = sorted(set(SJR_SYSTEM_VARS))


def load_calsim_hist(wanted_vars):
    """Read from CalSim default DSS."""
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


def load_chunk_csv(chunk_id, part_b_filter=None):
    """Load compiled SV CSV for a single chunk."""
    path = COMPILED / f"ProductB_SV_n{chunk_id:02d}.csv"
    df = pd.read_csv(path)
    if part_b_filter:
        df = df[df['Part B'].isin(part_b_filter)]
    return df


# ============================================================================
# Section 1: n09 Millerton/SJR inflows at failure WY (Oct 1961 - Sep 1962)
# ============================================================================
print("=" * 80)
print(f"SECTION 1: n09 SJR RIM INFLOWS -- WY{FAIL_YEAR}")
print(f"  Failure: {MO_NAMES[FAIL_MONTH-1]} {FAIL_YEAR}, Cycle 14 (sjrbase)")
print("=" * 80)

for var in SJR_INFLOW_VARS:
    try:
        df = pd.read_csv(RIM_DIR / f"{var}_qmo_n{FAIL_CHUNK:02d}.csv")
        mask = ((df['Year'] == FAIL_YEAR - 1) & (df['Month'] >= 10)) | \
               ((df['Year'] == FAIL_YEAR) & (df['Month'] <= 9))
        sub = df[mask]
        print(f"\n{var}:")
        for _, r in sub.iterrows():
            marker = " <-- FAIL" if (int(r['Year']) == FAIL_YEAR and
                                     int(r['Month']) == FAIL_MONTH) else ""
            print(f"  {int(r['Year'])}-{int(r['Month']):02d}:"
                  f" {r['qmap_postAdj']:10.3f}{marker}")
    except FileNotFoundError:
        print(f"\n{var}: (no per-chunk rim inflow file)")


# ============================================================================
# Section 2: Cross-chunk comparison at April 1962
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 2: APR {FAIL_YEAR} -- ALL 10 CHUNKS + HISTORICAL")
print("=" * 80)

# Load historical
hist = load_calsim_hist([v for v in SJR_INFLOW_VARS if v != 'I_BUR005'])
hist['date'] = pd.to_datetime(hist['date'])
hist['Year'] = hist['date'].dt.year
hist['Month'] = hist['date'].dt.month

# Load all chunks for the SJR variables
print("\nLoading chunk data (SJR variables only)...")
chunk_data = {}
for i in range(1, 11):
    chunk_data[i] = load_chunk_csv(i)

# Cross-chunk table: rim inflows
header = f"{'Variable':<20}"
for i in range(1, 11):
    tag = "**" if i == FAIL_CHUNK else "  "
    header += f"{tag + 'n' + str(i).zfill(2):>10}"
header += f"{'Historical':>12}"
print(header)
print("-" * len(header))

for var in SJR_INFLOW_VARS:
    row = f"{var:<20}"
    for i in range(1, 11):
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_n{i:02d}.csv")
            val = df[(df['Year'] == FAIL_YEAR) &
                     (df['Month'] == FAIL_MONTH)]['qmap_postAdj']
            row += f"{val.iloc[0]:10.2f}" if not val.empty else f"{'N/A':>10}"
        except FileNotFoundError:
            # Fall back to compiled SV
            cd = chunk_data[i]
            val = cd[(cd['Part B'] == var) & (cd['Year'] == FAIL_YEAR) &
                     (cd['Month'] == FAIL_MONTH)]['Value']
            row += f"{val.iloc[0]:10.2f}" if not val.empty else f"{'N/A':>10}"
    hval = hist[(hist['Year'] == FAIL_YEAR) &
                (hist['Month'] == FAIL_MONTH)].get(var)
    if hval is not None and not hval.empty:
        row += f"{hval.iloc[0]:12.2f}"
    else:
        row += f"{'N/A':>12}"
    print(row)


# ============================================================================
# Section 3: Constraint-referenced SVs at April 1962
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 3: CONSTRAINT-REFERENCED SVs AT APR {FAIL_YEAR}")
print("=" * 80)

# These are the SVs that directly feed the infeasible constraints
constraint_check = [
    'REST_REQ_NP', 'REST_REQ_P', 'REST_RCH_NP',
    'CT_GRAVELLYFORD_SV',
    'ER_MLRTN',
    'UNIMP_SJ',
    'SEEP_SJR_EAST', 'SEEP_SJR_WEST',
    'DRN_SJR_EAST', 'DRN_SJR_WEST',
    'IRR_SJR_EAST', 'IRR_SJR_WEST',
    'SR_64',
]

header = f"{'Variable':<30}"
for i in range(1, 11):
    tag = "**" if i == FAIL_CHUNK else "  "
    header += f"{tag + 'n' + str(i).zfill(2):>12}"
print(header)
print("-" * len(header))

for var in constraint_check:
    row = f"{var:<30}"
    for i in range(1, 11):
        cd = chunk_data[i]
        val = cd[(cd['Part B'] == var) & (cd['Year'] == FAIL_YEAR) &
                 (cd['Month'] == FAIL_MONTH)]['Value']
        row += f"{val.iloc[0]:12.4f}" if not val.empty else f"{'N/A':>12}"
    print(row)


# ============================================================================
# Section 4: n09 vs n02 detailed comparison at failure month
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 4: n09 vs n02 DETAILED COMPARISON AT APR {FAIL_YEAR}")
print("=" * 80)

# Get all SJR-related variables
sjr_patterns = ['SJR', 'MLRTN', 'MERC', 'MCLRE', 'PEDRO', 'NHGAN', 'STAN',
                'TUOL', 'MOK', 'FRIANT', 'REST', 'GRAVELLY', 'BCK', 'DED',
                'SEEP', 'DRN', 'IRR', 'SR_6', 'UNIMP', 'MDOTA']
pat = '|'.join(sjr_patterns)

n09 = chunk_data[FAIL_CHUNK]
n02 = chunk_data[2]

n09_apr = n09[(n09['Year'] == FAIL_YEAR) & (n09['Month'] == FAIL_MONTH)]
n02_apr = n02[(n02['Year'] == FAIL_YEAR) & (n02['Month'] == FAIL_MONTH)]

n09_sjr = n09_apr[n09_apr['Part B'].str.upper().str.contains(pat, na=False)]
n02_sjr = n02_apr[n02_apr['Part B'].str.upper().str.contains(pat, na=False)]

all_vars = sorted(set(n09_sjr['Part B'].tolist() + n02_sjr['Part B'].tolist()))

print(f"{'Variable':<35s}  {'n09':>12s}  {'n02':>12s}  {'Diff':>12s}  {'Diff%':>8s}")
print("-" * 90)

for var in all_vars:
    v9 = n09_sjr.loc[n09_sjr['Part B'] == var, 'Value']
    v2 = n02_sjr.loc[n02_sjr['Part B'] == var, 'Value']
    vf = v9.iloc[0] if not v9.empty else float('nan')
    vr = v2.iloc[0] if not v2.empty else float('nan')
    diff = vf - vr
    denom = max(abs(vf), abs(vr), 1e-6)
    dpct = diff / denom * 100
    print(f"{var:<35s}  {vf:12.4f}  {vr:12.4f}  {diff:12.4f}  {dpct:7.1f}%")


# ============================================================================
# Section 5: n09 WY1962 time series for key constraint variables
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 5: n09 KEY VARIABLE TIME SERIES -- WY{FAIL_YEAR}")
print("=" * 80)

wy_months = [(FAIL_YEAR - 1, m) for m in range(10, 13)] + \
            [(FAIL_YEAR, m) for m in range(1, 10)]

key_ts_vars = ['I_MLRTN', 'REST_REQ_NP', 'REST_REQ_P', 'REST_RCH_NP',
               'UNIMP_SJ', 'CT_GRAVELLYFORD_SV', 'ER_MLRTN',
               'SEEP_SJR_EAST', 'I_MCLRE', 'I_PEDRO', 'I_NHGAN']

n09_full = chunk_data[FAIL_CHUNK]

for var in key_ts_vars:
    sub = n09_full[n09_full['Part B'] == var]
    if sub.empty:
        print(f"\n{var}: NOT IN SV")
        continue
    print(f"\n{var}:")
    for y, m in wy_months:
        val = sub.loc[(sub['Year'] == y) & (sub['Month'] == m), 'Value']
        if not val.empty:
            marker = " <-- FAIL" if (y == FAIL_YEAR and m == FAIL_MONTH) else ""
            print(f"  {y}-{m:02d}: {val.values[0]:12.4f}{marker}")


# ============================================================================
# Section 6: Percentile rank of n09 Apr 1962 in all-chunk April distribution
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 6: n09 APR {FAIL_YEAR} PERCENTILE RANK")
print("  (rank among all 10 chunks x all Aprils)")
print("=" * 80)

rank_vars = ['I_MLRTN', 'REST_REQ_NP', 'REST_RCH_NP', 'UNIMP_SJ',
             'CT_GRAVELLYFORD_SV', 'ER_MLRTN', 'SEEP_SJR_EAST',
             'I_MCLRE', 'I_PEDRO', 'I_NHGAN', 'I_MOK079']

# Pool all April values across all chunks
all_apr = pd.concat([
    chunk_data[i][(chunk_data[i]['Month'] == FAIL_MONTH)]
    for i in range(1, 11)
], ignore_index=True)

print(f"{'Variable':<30s}  {'n09 value':>12s}  {'Pctile':>8s}  {'All-Apr min':>12s}  {'All-Apr max':>12s}  {'All-Apr mean':>12s}")
print("-" * 95)

for var in rank_vars:
    pool = all_apr[all_apr['Part B'] == var]['Value'].dropna()
    n09_val = n09_apr.loc[n09_apr['Part B'] == var, 'Value']
    if pool.empty or n09_val.empty:
        print(f"{var:<30s}  {'N/A':>12s}")
        continue
    v = n09_val.iloc[0]
    pctile = (pool < v).sum() / len(pool) * 100
    print(f"{var:<30s}  {v:12.4f}  {pctile:7.1f}%  {pool.min():12.4f}  {pool.max():12.4f}  {pool.mean():12.4f}")


# ============================================================================
# Section 7: Historical April 1962 comparison
# ============================================================================
print("\n" + "=" * 80)
print(f"SECTION 7: HISTORICAL APR {FAIL_YEAR} vs n09 APR {FAIL_YEAR}")
print("=" * 80)

hist_apr = hist[(hist['Year'] == FAIL_YEAR) & (hist['Month'] == FAIL_MONTH)]
print(f"{'Variable':<25s}  {'n09':>12s}  {'Historical':>12s}  {'Ratio n09/hist':>15s}")
print("-" * 70)

for var in SJR_INFLOW_VARS:
    if var == 'I_BUR005':
        continue
    n09_val = n09_apr.loc[n09_apr['Part B'] == var, 'Value']
    h_val = hist_apr.get(var)
    vn = n09_val.iloc[0] if not n09_val.empty else float('nan')
    vh = h_val.iloc[0] if h_val is not None and not h_val.empty else float('nan')
    ratio = vn / vh if vh != 0 and not np.isnan(vh) else float('nan')
    print(f"{var:<25s}  {vn:12.4f}  {vh:12.4f}  {ratio:14.2f}x")

print("\n--- End SV analysis ---")


# ============================================================================
# Section 8: Cross-run minimum-April Millerton storage comparison
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 8: CROSS-RUN MINIMUM-APRIL MILLERTON STORAGE")
print("=" * 80)

N_BEFORE = 12  # months before the minimum-April
N_AFTER = 6    # months after


def read_dv_ts(dss_path, part_b, start_year=1921, end_year=2022):
    """Read a monthly time series from a DSS file."""
    with HecDss.Open(str(dss_path), version=6) as fid:
        cat = fid.getPathnameList(f"/*/{part_b}/*/*/*/*/", sort=1)
        if not cat:
            return None, None
        all_dates, all_vals = [], []
        for p in sorted(cat, key=lambda x: x.strip("/").split("/")[3]):
            try:
                ts = fid.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan
                all_dates.extend(ts.pytimes)
                all_vals.extend(vals)
            except Exception:
                pass
        if not all_dates:
            return None, None
        # Correct pydsstools 1-month-ahead date offset (same as load_calsim_hist)
        raw = pd.to_datetime(all_dates)
        dates = (raw.to_period("M") - 1).to_timestamp("M")
        values = np.array(all_vals)
        mask = (dates.year >= start_year) & (dates.year <= end_year)
        return dates[mask], values[mask]


def find_min_april(dates, vals):
    """Return (year, value) of the April with minimum value."""
    df = pd.DataFrame({'date': dates, 'val': vals}).dropna()
    apr = df[df['date'].dt.month == 4]
    if apr.empty:
        return None, None
    idx = apr['val'].idxmin()
    return int(apr.loc[idx, 'date'].year), float(apr.loc[idx, 'val'])


def rel_window(years, months, values, cy, cm=4):
    """Compute relative-month window around (cy, cm)."""
    rel = (years - cy) * 12 + (months - cm)
    mask = (rel >= -N_BEFORE) & (rel <= N_AFTER)
    order = np.argsort(rel[mask])
    return rel[mask][order].astype(int), values[mask][order]


def window_sv(chunk_id, part_b, center_year):
    """Extract relative-month window from SV CSV (chunk_data)."""
    df = chunk_data[chunk_id]
    sub = df[df['Part B'] == part_b][['Year', 'Month', 'Value']].copy()
    if sub.empty:
        return None, None
    return rel_window(sub['Year'].values, sub['Month'].values,
                      sub['Value'].values, center_year)


def window_dv(dates, vals, center_year):
    """Extract relative-month window from DV time series."""
    if dates is None:
        return None, None
    yrs = np.array([d.year for d in dates])
    mos = np.array([d.month for d in dates])
    return rel_window(yrs, mos, vals, center_year)


def window_hist_sv(part_b, center_year):
    """Extract from the already-loaded hist DataFrame (Section 2)."""
    if part_b not in hist.columns:
        return None, None
    sub = hist[['Year', 'Month', part_b]].dropna(subset=[part_b])
    return rel_window(sub['Year'].values, sub['Month'].values,
                      sub[part_b].values, center_year)


# ---- Step 1: Read S_MLRTN from each DV, find min-April year ----
print("\nFinding minimum-April S_MLRTN from DV files...")

run_data = {}  # key -> dict with cached data

# n01-n08
for n in range(1, 9):
    tag = f'n{n:02d}'
    dv = DV_DIR / "dv_out" / (
        f"DCR2023_DV_9.3.1_Danube_Hist_v1.7_ProductB_{tag}.dss")
    if not dv.exists():
        print(f"  {tag}: DV not found, skipping")
        continue
    try:
        d, v = read_dv_ts(dv, 'S_MLRTN')
    except Exception as exc:
        print(f"  {tag}: error reading DV -- {exc}")
        continue
    if d is None:
        print(f"  {tag}: S_MLRTN not in DV, skipping")
        continue
    yr, val = find_min_april(d, v)
    if yr is None:
        continue
    run_data[tag] = {
        'min_year': yr, 'min_val': val,
        's_dates': d, 's_vals': v,
        'chunk_id': n,
    }
    print(f"  {tag}: Apr {yr}, S_MLRTN = {val:.1f} TAF")

# n09 (crash file)
_dv09 = CRASH_DSS if CRASH_DSS.exists() else DV_N09
if _dv09.exists():
    try:
        d, v = read_dv_ts(_dv09, 'S_MLRTN')
        if d is not None:
            yr, val = find_min_april(d, v)
            if yr is not None:
                run_data['n09'] = {
                    'min_year': yr, 'min_val': val,
                    's_dates': d, 's_vals': v,
                    'chunk_id': FAIL_CHUNK,
                }
                print(f"  n09: Apr {yr}, S_MLRTN = {val:.1f} TAF (crash)")
    except Exception as exc:
        print(f"  n09: error reading crash DV -- {exc}")
else:
    print("  n09: crash DV not found")

# Historical
if HIST_DV.exists():
    try:
        d, v = read_dv_ts(HIST_DV, 'S_MLRTN')
        if d is not None:
            yr, val = find_min_april(d, v)
            if yr is not None:
                run_data['hist'] = {
                    'min_year': yr, 'min_val': val,
                    's_dates': d, 's_vals': v,
                }
                print(f"  hist: Apr {yr}, S_MLRTN = {val:.1f} TAF")
        else:
            print("  hist: S_MLRTN not in historical DV")
    except Exception as exc:
        print(f"  hist: error reading DV -- {exc}")
else:
    print(f"  hist: DV not found at {HIST_DV}")


# ---- Step 2: Build windowed traces for each run ----
print("\nExtracting windowed traces...")

traces = {}
for key, info in run_data.items():
    cy = info['min_year']

    # Storage from DV (already loaded)
    s_rel, s_val = window_dv(info['s_dates'], info['s_vals'], cy)

    if key.startswith('n'):
        # Stochastic: I_MLRTN and REST_REQ_NP from SV CSV
        cid = info['chunk_id']
        i_rel, i_val = window_sv(cid, 'I_MLRTN', cy)
        r_rel, r_val = window_sv(cid, 'REST_REQ_NP', cy)
    else:
        # Historical: I_MLRTN from hist DataFrame, REST_REQ_NP from DV
        i_rel, i_val = window_hist_sv('I_MLRTN', cy)
        # Try REST_REQ_NP from historical DV
        try:
            d_r, v_r = read_dv_ts(HIST_DV, 'REST_REQ_NP')
        except Exception:
            d_r, v_r = None, None
        if d_r is not None:
            r_rel, r_val = window_dv(d_r, v_r, cy)
        else:
            # Fallback: try CalSim default SV DSS
            hist_rest = load_calsim_hist(['REST_REQ_NP'])
            if 'REST_REQ_NP' in hist_rest.columns:
                hist_rest['date'] = pd.to_datetime(hist_rest['date'])
                hist_rest['Year'] = hist_rest['date'].dt.year
                hist_rest['Month'] = hist_rest['date'].dt.month
                sub_r = hist_rest[['Year', 'Month', 'REST_REQ_NP']].dropna(
                    subset=['REST_REQ_NP'])
                r_rel, r_val = rel_window(
                    sub_r['Year'].values, sub_r['Month'].values,
                    sub_r['REST_REQ_NP'].values, cy)
            else:
                r_rel, r_val = None, None
                print("  hist: REST_REQ_NP not found in DV or default SV")

    traces[key] = {
        'inflow': (i_rel, i_val),
        'rest': (r_rel, r_val),
        'storage': (s_rel, s_val),
        'min_year': cy,
        'min_val': info['min_val'],
    }
    print(f"  {key}: center = Apr {cy}, S_MLRTN = {info['min_val']:.1f} TAF")


# ---- Step 2b: April mass balance table ----
def _val_at(rel_vals_pair, target_rel):
    """Return value at a specific relative month, or NaN."""
    rel, vals = rel_vals_pair
    if rel is None or len(rel) == 0:
        return np.nan
    idx = np.where(rel == target_rel)[0]
    return float(vals[idx[0]]) if len(idx) > 0 else np.nan

print("\n" + "=" * 100)
print("MILLERTON MASS BALANCE: MARCH -> APRIL -> MAY")
print("  S(t) ~ S(t-1) + I(t) - REST(t) - Other(t)")
print("  Other = evaporation + non-restoration deliveries")
print("  Deficit = S(prev) + I - REST  (negative => infeasible before other losses)")
print("=" * 100)

display_order = (sorted(k for k in traces if k.startswith('n') and k != 'n09')
                 + (['hist'] if 'hist' in traces else [])
                 + (['n09'] if 'n09' in traces else []))

header = (f"{'Run':<6s} {'Year':>4s} | "
          f"{'S(Mar)':>8s} {'I(Apr)':>8s} {'REST':>8s} {'Deficit':>8s} "
          f"{'Other':>8s} {'S(Apr)':>8s} | "
          f"{'I(May)':>8s} {'REST':>8s} {'Deficit':>8s} "
          f"{'Other':>8s} {'S(May)':>8s}")
print(header)
print("-" * len(header))

for key in display_order:
    t = traces[key]
    yr = t['min_year']
    s_mar = _val_at(t['storage'], -1)
    s_apr = _val_at(t['storage'], 0)
    s_may = _val_at(t['storage'], 1)
    i_apr = _val_at(t['inflow'], 0)
    i_may = _val_at(t['inflow'], 1)
    r_apr = _val_at(t['rest'], 0)
    r_may = _val_at(t['rest'], 1)

    def_apr = s_mar + i_apr - r_apr
    oth_apr = s_mar + i_apr - r_apr - s_apr
    def_may = s_apr + i_may - r_may
    oth_may = s_apr + i_may - r_may - s_may

    flag = ""
    if def_apr < 0:
        flag = " <-- APR INFEASIBLE"
    elif def_may < 0:
        flag = " <-- MAY INFEASIBLE"

    print(f"{key:<6s} {yr:>4d} | "
          f"{s_mar:>8.1f} {i_apr:>8.1f} {r_apr:>8.1f} {def_apr:>8.1f} "
          f"{oth_apr:>8.1f} {s_apr:>8.1f} | "
          f"{i_may:>8.1f} {r_may:>8.1f} {def_may:>8.1f} "
          f"{oth_may:>8.1f} {s_may:>8.1f}{flag}")

print()


# ---- Step 2c: Focused Millerton mass balance from DV ----
# Continuity: S(end t) = S(end t-1) + I(t) - E(t) - C(t) - D_FRK(t) - D_MDC(t)
BALANCE_DVS = ['S_MLRTN', 'E_MLRTN', 'C_MLRTN', 'C_MLRTNM', 'C_MLRTNA',
               'C_MLRTNF', 'C_MLRTN_FLOOD', 'D_MLRTN_FRK000',
               'D_MLRTN_MDC006']


def read_dv_months(dss_path, part_bs, target_year, target_months):
    """Read specific DVs for given months from a DV file (one open)."""
    results = {}  # {(part_b, month): value}
    with HecDss.Open(str(dss_path), version=6) as fid:
        for pb in part_bs:
            cat = fid.getPathnameList(f"/*/{pb}/*/*/*/*/", sort=1)
            if not cat:
                continue
            for p in sorted(cat, key=lambda x: x.strip("/").split("/")[3]):
                try:
                    ts = fid.read_ts(p, trim_missing=True)
                    vals = np.asarray(ts.values, dtype=float)
                    raw = pd.to_datetime(ts.pytimes)
                    corrected = (raw.to_period("M") - 1).to_timestamp("M")
                    for d, v in zip(corrected, vals):
                        if (d.year == target_year
                                and d.month in target_months
                                and v > -900
                                and (pb, d.month) not in results):
                            results[(pb, d.month)] = v
                except Exception:
                    pass
    return results


detail_runs = []
if 'n09' in run_data:
    detail_runs.append(('n09', _dv09))
for comp in ['n07', 'n02']:
    if comp in run_data:
        dv = DV_DIR / "dv_out" / (
            f"DCR2023_DV_9.3.1_Danube_Hist_v1.7_ProductB_{comp}.dss")
        detail_runs.append((comp, dv))
if 'hist' in run_data:
    detail_runs.append(('hist', HIST_DV))

print("=" * 80)
print("MILLERTON LAKE APRIL MASS BALANCE (from DV)")
print("  S(end Apr) = S(end Mar) + I(Apr) - E(Apr) - C(Apr)")
print("              - D_FRK(Apr) - D_MDC(Apr) - Spill(Apr)")
print("=" * 80)

for tag, dv_path in detail_runs:
    yr = traces[tag]['min_year']
    if not Path(dv_path).exists():
        print(f"\n--- {tag}: DV not found ---")
        continue
    dvs = read_dv_months(dv_path, BALANCE_DVS, yr, [3, 4])
    # DV terms
    s_mar = dvs.get(('S_MLRTN', 3), float('nan'))
    s_apr = dvs.get(('S_MLRTN', 4), float('nan'))
    e_apr = dvs.get(('E_MLRTN', 4), float('nan'))
    c_apr = dvs.get(('C_MLRTN', 4), float('nan'))
    c_main = dvs.get(('C_MLRTNM', 4), float('nan'))
    c_snow = dvs.get(('C_MLRTNA', 4), float('nan'))
    c_flood = dvs.get(('C_MLRTNF', 4), float('nan'))
    spill = dvs.get(('C_MLRTN_FLOOD', 4), float('nan'))
    d_frk = dvs.get(('D_MLRTN_FRK000', 4), float('nan'))
    d_mdc = dvs.get(('D_MLRTN_MDC006', 4), float('nan'))
    # SV terms (from traces)
    i_apr = _val_at(traces[tag]['inflow'], 0)
    r_apr = _val_at(traces[tag]['rest'], 0)

    # Computed check
    computed = s_mar + i_apr - e_apr - c_apr - d_frk - d_mdc - spill
    residual = s_apr - computed

    print(f"\n--- {tag}: April {yr} ---")
    print(f"  S(end Mar):      {s_mar:8.1f} TAF  (starting storage)")
    print(f"  + I(Apr):       +{i_apr:8.1f} TAF  (inflow, from SV)")
    print(f"  - E(Apr):       -{e_apr:8.1f} TAF  (evaporation)")
    print(f"  - C(Apr):       -{c_apr:8.1f} TAF  (total channel release)")
    print(f"      C_main:      {c_main:8.1f}      (main release)")
    print(f"      C_snowmelt:  {c_snow:8.1f}      (snowmelt release)")
    print(f"      C_flood:     {c_flood:8.1f}      (flood release)")
    print(f"      REST_REQ_NP: {r_apr:8.1f}      (restoration req., included in C)")
    print(f"  - D_FRK(Apr):   -{d_frk:8.1f} TAF  (Friant-Kern diversion)")
    print(f"  - D_MDC(Apr):   -{d_mdc:8.1f} TAF  (Madera Canal diversion)")
    print(f"  - Spill(Apr):   -{spill:8.1f} TAF  (uncontrolled spill)")
    print(f"  = S(end Apr):    {s_apr:8.1f} TAF  (ending storage)")
    if abs(residual) > 0.5:
        print(f"    (residual: {residual:+.1f}, likely rounding or minor terms)")

# Side-by-side summary
if len(detail_runs) > 1:
    tags = [t for t, _ in detail_runs]
    print(f"\n{'Term':<22s}", end="")
    for t in tags:
        print(f"  {t:>10s}", end="")
    print()
    print("-" * (22 + 12 * len(tags)))
    rows = [
        ('S(end Mar)', lambda t: _val_at(traces[t]['storage'], -1)),
        ('+ I(Apr)', lambda t: _val_at(traces[t]['inflow'], 0)),
        ('- REST_REQ_NP(Apr)', lambda t: _val_at(traces[t]['rest'], 0)),
        ('= Avail for storage', lambda t: (
            _val_at(traces[t]['storage'], -1)
            + _val_at(traces[t]['inflow'], 0)
            - _val_at(traces[t]['rest'], 0))),
        ('- E + other losses', lambda t: (
            _val_at(traces[t]['storage'], -1)
            + _val_at(traces[t]['inflow'], 0)
            - _val_at(traces[t]['rest'], 0)
            - _val_at(traces[t]['storage'], 0))),
        ('= S(end Apr)', lambda t: _val_at(traces[t]['storage'], 0)),
    ]
    for label, fn in rows:
        print(f"{label:<22s}", end="")
        for t in tags:
            try:
                v = fn(t)
                print(f"  {v:>10.1f}", end="")
            except Exception:
                print(f"  {'--':>10s}", end="")
        print()

print()


# ---- Step 3: Three-panel figure ----
print("\nGenerating comparison figure...")

fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
fig.suptitle(
    'Minimum-April Millerton Storage: Cross-Run Comparison',
    fontsize=13, fontweight='bold')

panels = [
    ('inflow', 'I_MLRTN (Millerton Inflow)', 'TAF/month'),
    ('rest', 'REST_REQ_NP (SJR Restoration Req.)', 'TAF/month'),
    ('storage', 'S_MLRTN (Millerton Storage)', 'TAF'),
]

grey_keys = sorted(k for k in traces if k.startswith('n') and k != 'n09')
first_grey = grey_keys[0] if grey_keys else None

for ax, (vk, title, ylabel) in zip(axes, panels):
    # n01-n08 in grey
    for key in grey_keys:
        rel, val = traces[key][vk]
        if rel is not None and len(rel) > 0:
            ax.plot(rel, val, color='lightgrey', linewidth=0.8, alpha=0.7,
                    label=('n01-n08' if key == first_grey else None))

    # Historical in blue
    if 'hist' in traces:
        rel, val = traces['hist'][vk]
        if rel is not None and len(rel) > 0:
            ax.plot(rel, val, color='steelblue', linewidth=1.8,
                    label='Historical')

    # n09 in red
    if 'n09' in traces:
        rel, val = traces['n09'][vk]
        if rel is not None and len(rel) > 0:
            ax.plot(rel, val, color='red', linewidth=2,
                    marker='o', markersize=3, label='n09')

    # Mark the minimum-April reference point
    ax.axvline(0, color='black', linestyle=':', linewidth=1, alpha=0.5)

    if vk == 'storage':
        ax.axhline(y=130, color='darkred', linestyle='--', linewidth=1.5,
                   label='Min operational pool (~130 TAF)')

    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.legend(loc='upper right' if vk == 'storage' else 'upper left',
              fontsize=8)

axes[-1].set_xlabel('Months relative to minimum-April storage')
axes[-1].set_xticks(range(-N_BEFORE, N_AFTER + 1, 3))

plt.tight_layout()
fig_path = OUT_DIR / "fig3_n09_mlrtn_min_april_comparison.png"
fig.savefig(fig_path, dpi=150, bbox_inches='tight')
print(f"\nSaved: {fig_path}")
plt.close()


# ---- Summary table ----
print(f"\n{'Run':<8s}  {'Min-Apr Year':>12s}  {'S_MLRTN (TAF)':>14s}")
print("-" * 38)
for key in sorted(traces):
    t = traces[key]
    print(f"{key:<8s}  {t['min_year']:>12d}  {t['min_val']:>14.1f}")

print("\n--- Done ---")
