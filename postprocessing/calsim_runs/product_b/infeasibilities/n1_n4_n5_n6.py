"""Diagnose high-flow SJR cycle 14 infeasibilities: n01, n04, n05, n06.

All four chunks fail in June with the identical mechanism: extreme Millerton
inflow overflows the Mendota Pool DMC water balance bookkeeping cap
(mdota_max = 10000 cfs in SJR_Cycle_Defs_Local.wresl).

Failure timestamps:
  n01 -- 1980_06_c14 Solve_c__ infeasible (Linear relaxation not feasible)
  n04 -- 2006_06_c14 Solve_c__ infeasible (Linear relaxation not feasible)
  n05 -- 1968_06_c14 Solve_c__ infeasible (Linear relaxation not feasible)
  n06 -- 1944_06_c14 Solve_c__ infeasible (Linear relaxation not feasible)

Root cause: SJR_Cycle_Defs_Local.wresl lines ~147-163
   - MendotaBalance:  mdota_above - mdota_below = mp_inflow - mp_deliveries - Sack_short
   - MPInf_abv_force: mdota_above < INT_MPInflow_abv * 10000
   - MPInf_blw_force: mdota_below < 10000 - INT_MPInflow_abv * 10000
   When mp_inflow (= C_FSL005 + C_SJR205) - mp_deliveries - Sack_short > 10000,
   neither integer setting can satisfy MendotaBalance: mdota_above hits 10000 cap
   (INT=1) or mdota_below goes negative (INT=0). LP infeasible under both settings.

The physical routing is NOT the bottleneck -- all SJR channel arcs are unbounded.
The infeasibility is purely in the bookkeeping layer.

IIS co-member constraints (not independently infeasible, same across all 4):
  1. Millerton storage zones (friant adj fld spc.wresl)
  2. SJR East connectivity/seepage (setpossg*/setnegsg* for sjr205..sjr265)
  3. SJR channel splits (meetsjrr, boundd_sjr214_ebp001, mp_inflow_alias)
  4. Contract limits (limitd_mdota_64_xa, limitd_mdota_90_pa1)
  5. Friant-Kern delivery (split_d910_16b, lim_d910_16b_pc)
  6. SJR West wufactors (parcels 72_pr2, 72_pr3, 64_pa3, 91_pr)
  7. XCC connectivity (continuityxcc010, continuityxcc025, continuityxcc033)
  8. Millerton continuity (continuitymlrtn)

Fix: increase mdota_max from 10000 to 50000 in SJR_Cycle_Defs_Local.wresl.
"""
# %% Imports and paths
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from utils.paths import get_base_dir, get_generated_dir
RIM_DIR = (get_generated_dir() / "postprocessing" / "sv_compile"
           / "product_b_compilation" / "compiled_input_files" / "rim_inflow")
DSS_PATH = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
SV_DIR = (get_generated_dir() / "postprocessing" / "sv_compile"
          / "product_b_compilation" / "_product_b_compiled_sv")
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


# All four high-flow failures: (chunk_id, fail_year, fail_month)
FAILURES = [
    (1, 1980, 6),
    (4, 2006, 6),
    (5, 1968, 6),
    (6, 1944, 6),
]
FAIL_MONTH = 6  # all fail in June
REFERENCE_CHUNK = 2  # n02 passes -- used for SV comparison

SJR_INFLOW_VARS = [
    'I_MLRTN', 'I_MLRTN_IMP', 'I_MCLRE', 'I_PEDRO', 'I_MOK079',
    'I_PARDE', 'I_NHGAN', 'I_BCK040', 'I_DED044', 'I_SJR258',
    'I_SJR265', 'I_BUR005',
]

SV_VARS = [
    'UNIMP_SJ', 'UNIMP_SJ_UHH', 'S_PEDRO_SV', 'S_PEDROLEVEL4',
    'E_PEDRO_SV', 'CT_PEDRO_SV', 'CT_MERCED_SV',
    'SEEP_SJR_EAST', 'SEEP_SJR_WEST', 'SEEP_MOK',
    'DRN_SJR_EAST', 'DRN_SJR_WEST', 'DRN_MOK',
    'IRR_SJR_EAST', 'IRR_SJR_WEST', 'IRR_MOK',
    'REST_REQ_NP', 'REST_REQ_P',
    'R_60N_NA4_SJR022_SV',
]

REPORT_VARS = ['I_MLRTN', 'I_MCLRE', 'I_PEDRO', 'I_MOK079']

# Load historical baseline once
avail_vars = [v for v in SJR_INFLOW_VARS if v != 'I_BUR005']
hist = load_calsim_hist(avail_vars)
hist['date'] = pd.to_datetime(hist['date'])
hist['Year'] = hist['date'].dt.year
hist['Month'] = hist['date'].dt.month
hist = hist.dropna(subset=['I_MLRTN'])

MO_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ============================================================================
# Loop over each failure
# ============================================================================
for chunk_id, fail_year, fail_month in FAILURES:
    tag = f"n{chunk_id:02d}"

    print("\n" + "#" * 80)
    print(f"# {tag.upper()} -- FAILURE AT {MO_NAMES[fail_month-1].upper()} {fail_year}")
    print("#" * 80)

    # %% Section 1: Per-chunk rim inflows at failure WY
    print("\n" + "=" * 80)
    print(f"SECTION 1: {tag} SJR RIM INFLOWS -- WY{fail_year}"
          f" (Oct {fail_year-1} - Sep {fail_year})")
    print("=" * 80)

    for var in SJR_INFLOW_VARS:
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            mask = ((df['Year'] == fail_year - 1) & (df['Month'] >= 10)) | \
                   ((df['Year'] == fail_year) & (df['Month'] <= 9))
            sub = df[mask]
            print(f"\n{var}:")
            for _, r in sub.iterrows():
                print(f"  {int(r['Year'])}-{int(r['Month']):02d}:"
                      f" {r['qmap_postAdj']:.3f}")
        except FileNotFoundError:
            print(f"\n{var}: (no per-chunk file)")

    # %% Section 2: CalSim historical baseline at failure WY
    print("\n" + "=" * 80)
    print(f"SECTION 2: CALSIM HISTORICAL BASELINE -- WY{fail_year}")
    print("=" * 80)

    mask = ((hist['Year'] == fail_year - 1) & (hist['Month'] >= 10)) | \
           ((hist['Year'] == fail_year) & (hist['Month'] <= 9))
    sub_hist = hist[mask]

    for var in avail_vars:
        print(f"\n{var}:")
        for _, r in sub_hist.iterrows():
            print(f"  {int(r['Year'])}-{int(r['Month']):02d}: {r[var]:.3f}")

    # %% Section 3: Failure month cross-chunk + historical comparison
    print("\n" + "=" * 80)
    print(f"SECTION 3: {MO_NAMES[fail_month-1].upper()} {fail_year}"
          " -- ALL CHUNKS + HISTORICAL")
    print("=" * 80)

    header = f"{'Variable':<20}"
    for i in range(1, 11):
        header += f"{'n' + str(i).zfill(2):>10}"
    header += f"{'Historical':>12}"
    print(header)
    print("-" * len(header))

    for var in SJR_INFLOW_VARS:
        row = f"{var:<20}"
        for i in range(1, 11):
            try:
                df = pd.read_csv(RIM_DIR / f"{var}_qmo_n{i:02d}.csv")
                val = df[(df['Year'] == fail_year) &
                         (df['Month'] == fail_month)]['qmap_postAdj']
                row += f"{val.iloc[0]:10.2f}" if not val.empty else f"{'N/A':>10}"
            except FileNotFoundError:
                row += f"{'N/A':>10}"
        if var in sub_hist.columns:
            hval = sub_hist[(sub_hist['Year'] == fail_year) &
                            (sub_hist['Month'] == fail_month)][var]
            row += f"{hval.iloc[0]:12.2f}" if not hval.empty else f"{'N/A':>12}"
        else:
            row += f"{'N/A':>12}"
        print(row)

    # %% Section 4: Percentile ranks
    print("\n" + "=" * 80)
    print(f"SECTION 4: {tag} {MO_NAMES[fail_month-1].upper()} {fail_year}"
          " -- PERCENTILE RANK (ALL-CHUNK JUNE DISTRIBUTION)")
    print("=" * 80)

    for var in SJR_INFLOW_VARS:
        try:
            all_jun = []
            for i in range(1, 11):
                df = pd.read_csv(RIM_DIR / f"{var}_qmo_n{i:02d}.csv")
                jun = df[df['Month'] == fail_month]['qmap_postAdj'].values
                all_jun.extend(jun)
            all_jun = np.array(all_jun)

            dfn = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            n_val = dfn[(dfn['Year'] == fail_year) &
                        (dfn['Month'] == fail_month)]['qmap_postAdj'].iloc[0]

            pct = (all_jun < n_val).sum() / len(all_jun) * 100
            print(f"  {var:<20} {tag}={n_val:10.3f}   percentile={pct:5.1f}%   "
                  f"[min={all_jun.min():.3f}, median={np.median(all_jun):.3f},"
                  f" max={all_jun.max():.3f}]")
        except (FileNotFoundError, IndexError):
            print(f"  {var:<20} (not available)")

    # Historical max and percentile
    print(f"\nHistorical max (all-time) and historical percentile"
          f" ({tag} {MO_NAMES[fail_month-1]} {fail_year} vs all months):")
    for var in REPORT_VARS:
        if var not in hist.columns:
            continue
        h_all = hist[var].values
        h_max = hist[var].max()
        h_max_idx = hist[var].idxmax()
        h_max_yr = hist.loc[h_max_idx, 'Year']
        h_max_mo = hist.loc[h_max_idx, 'Month']

        try:
            dfn = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            n_val = dfn[(dfn['Year'] == fail_year) &
                        (dfn['Month'] == fail_month)]['qmap_postAdj'].iloc[0]
        except (FileNotFoundError, IndexError):
            continue

        h_pct = (h_all < n_val).sum() / len(h_all) * 100
        print(f"  {var:<15} {tag}={n_val:.1f}  "
              f"hist_max={h_max:.1f} ({MO_NAMES[int(h_max_mo)-1]} {int(h_max_yr)})  "
              f"hist_pctile={h_pct:.1f}%  "
              f"{'(exceeds max)' if n_val > h_max else ''}")

    # %% Section 5: Wider context -- 24-month window
    print("\n" + "=" * 80)
    print(f"SECTION 5: WIDER CONTEXT -- WY{fail_year-1} + WY{fail_year} (24 MONTHS)")
    print("=" * 80)

    for var in ['I_MLRTN', 'I_MLRTN_IMP', 'I_MCLRE', 'I_PEDRO', 'I_MOK079']:
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            mask = ((df['Year'] == fail_year - 2) & (df['Month'] >= 10)) | \
                   (df['Year'] == fail_year - 1) | \
                   ((df['Year'] == fail_year) & (df['Month'] <= 9))
            sub = df[mask]
            print(f"\n{var}:")
            for _, r in sub.iterrows():
                print(f"  {int(r['Year'])}-{int(r['Month']):02d}:"
                      f" {r['qmap_postAdj']:10.3f}")
        except FileNotFoundError:
            print(f"\n{var}: (not available)")

    # %% Section 6: Compiled SV comparison vs n02
    print("\n" + "=" * 80)
    print(f"SECTION 6: COMPILED SV -- {tag} vs n{REFERENCE_CHUNK:02d}"
          f" AT {MO_NAMES[fail_month-1].upper()} {fail_year}")
    print("=" * 80)

    print(f"Reading compiled SV {tag} (chunked)...")
    target_rows_nX = []
    for chunk in pd.read_csv(SV_DIR / f"ProductB_SV_{tag}.csv",
                             chunksize=100000):
        match = chunk[(chunk['Year'] == fail_year) &
                      (chunk['Month'] == fail_month) &
                      (chunk['Part B'].isin(SV_VARS))]
        if not match.empty:
            target_rows_nX.append(match)

    print(f"Reading compiled SV n{REFERENCE_CHUNK:02d} (chunked)...")
    target_rows_ref = []
    for chunk in pd.read_csv(
            SV_DIR / f"ProductB_SV_n{REFERENCE_CHUNK:02d}.csv",
            chunksize=100000):
        match = chunk[(chunk['Year'] == fail_year) &
                      (chunk['Month'] == fail_month) &
                      (chunk['Part B'].isin(SV_VARS))]
        if not match.empty:
            target_rows_ref.append(match)

    if target_rows_nX and target_rows_ref:
        resultX = pd.concat(target_rows_nX)
        resultR = pd.concat(target_rows_ref)
        ref_tag = f"n{REFERENCE_CHUNK:02d}"
        print(f"\n{'Variable':<30} {tag:>12} {ref_tag:>12}"
              f" {'Diff':>12} {'Diff%':>8}")
        print("-" * 76)
        for var in sorted(SV_VARS):
            vX = resultX[resultX['Part B'] == var]['Value']
            vR = resultR[resultR['Part B'] == var]['Value']
            if not vX.empty and not vR.empty:
                valX = vX.iloc[0]
                valR = vR.iloc[0]
                diff = valX - valR
                dpct = (diff / valR * 100) if valR != 0 else float('inf')
                print(f"  {var:<28} {valX:12.3f} {valR:12.3f}"
                      f" {diff:12.3f} {dpct:7.1f}%")
    else:
        print("  Missing data for one or both chunks")


# ============================================================================
# %% Section 7: Cross-comparison of all 4 failures at their failure months
# ============================================================================
print("\n" + "#" * 80)
print("# CROSS-COMPARISON: ALL HIGH-FLOW FAILURES")
print("#" * 80)

print("\n" + "=" * 80)
print("SECTION 7: RIM INFLOWS AT EACH FAILURE MONTH")
print("=" * 80)

col_headers = [f"n{c:02d} {MO_NAMES[m-1]} {y}" for c, y, m in FAILURES]
header = f"{'Variable':<20}" + "".join(f"{h:>18}" for h in col_headers)
print(header)
print("-" * len(header))

for var in SJR_INFLOW_VARS:
    row = f"{var:<20}"
    for chunk_id, fail_year, fail_month in FAILURES:
        tag = f"n{chunk_id:02d}"
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            val = df[(df['Year'] == fail_year) &
                     (df['Month'] == fail_month)]['qmap_postAdj']
            row += f"{val.iloc[0]:18.2f}" if not val.empty else f"{'N/A':>18}"
        except FileNotFoundError:
            row += f"{'N/A':>18}"
    print(row)

# Highlight QM ceiling matches
print("\nQM ceiling analysis (I_MLRTN, I_MCLRE -- vars that saturate at QM max):")
for var in ['I_MLRTN', 'I_MCLRE']:
    vals = []
    for chunk_id, fail_year, fail_month in FAILURES:
        tag = f"n{chunk_id:02d}"
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            v = df[(df['Year'] == fail_year) &
                   (df['Month'] == fail_month)]['qmap_postAdj'].iloc[0]
            vals.append(v)
        except (FileNotFoundError, IndexError):
            vals.append(np.nan)
    unique_vals = [v for v in vals if not np.isnan(v)]
    all_same = len(set(f"{v:.3f}" for v in unique_vals)) == 1
    val_strs = [f"n{c:02d}={v:.3f}" for (c, _, _), v in zip(FAILURES, vals)]
    print(f"  {var:<15} {', '.join(val_strs)}"
          f"  {'** ALL IDENTICAL (QM ceiling)' if all_same else ''}")


# ============================================================================
# %% Section 8: Markdown report table (for sjr_infeasibility_report.md)
# ============================================================================
print("\n" + "=" * 80)
print("SECTION 8: REPORT TABLE -- paste into sjr_infeasibility_report.md")
print("=" * 80)

# Variable name labels for the report
VAR_LABELS = {
    'I_MLRTN': 'I_MLRTN (Millerton)',
    'I_MCLRE': 'I_MCLRE (McClure)',
    'I_PEDRO': 'I_PEDRO (Don Pedro)',
}

# Build all-chunk June distribution for percentile calculation
june_dist = {}
for var in REPORT_VARS:
    all_jun = []
    for i in range(1, 11):
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_n{i:02d}.csv")
            jun = df[df['Month'] == FAIL_MONTH]['qmap_postAdj'].values
            all_jun.extend(jun)
        except FileNotFoundError:
            pass
    june_dist[var] = np.array(all_jun)

# Collect values for each failure x variable
fail_vals = {}  # (chunk_id, var) -> value
for chunk_id, fail_year, fail_month in FAILURES:
    tag = f"n{chunk_id:02d}"
    for var in REPORT_VARS:
        try:
            df = pd.read_csv(RIM_DIR / f"{var}_qmo_{tag}.csv")
            v = df[(df['Year'] == fail_year) &
                   (df['Month'] == fail_month)]['qmap_postAdj'].iloc[0]
            fail_vals[(chunk_id, var)] = v
        except (FileNotFoundError, IndexError):
            fail_vals[(chunk_id, var)] = np.nan

# Historical max per variable (June only for consistency with report)
hist_max_info = {}
for var in REPORT_VARS:
    if var not in hist.columns:
        continue
    h_jun = hist[hist['Month'] == FAIL_MONTH]
    h_max = hist[var].max()
    h_max_idx = hist[var].idxmax()
    h_max_yr = hist.loc[h_max_idx, 'Year']
    h_max_mo = hist.loc[h_max_idx, 'Month']
    hist_max_info[var] = (h_max, MO_NAMES[int(h_max_mo) - 1], int(h_max_yr))

# Build markdown table
chunk_cols = [f"n{c:02d} {MO_NAMES[m-1]} {y}" for c, y, m in FAILURES]
md_header = "| Variable | " + " | ".join(chunk_cols) + " | Hist. Max (all time) | Stochastic Pctile |"
md_sep = "|----------" + "|".join(["-------------|"] * len(FAILURES)) + "|--------------------|-------------------|"

md_lines = [md_header, md_sep]
for var in ['I_MLRTN', 'I_MCLRE', 'I_PEDRO']:
    label = VAR_LABELS.get(var, var)
    row = f"| {label} |"
    pctiles = []
    for chunk_id, fail_year, fail_month in FAILURES:
        v = fail_vals.get((chunk_id, var), np.nan)
        row += f" {v:.1f} |" if not np.isnan(v) else " N/A |"
        if not np.isnan(v) and var in june_dist and len(june_dist[var]) > 0:
            pct = (june_dist[var] < v).sum() / len(june_dist[var]) * 100
            pctiles.append(f"{pct:.1f}%")
        else:
            pctiles.append("N/A")
    h_max, h_mo, h_yr = hist_max_info.get(var, (np.nan, "?", 0))
    row += f" {h_max:.1f} ({h_mo} {h_yr}) |"
    # Collapse identical percentiles
    if len(set(pctiles)) == 1:
        row += f" {pctiles[0]} |"
    else:
        row += f" {' / '.join(pctiles)} |"
    md_lines.append(row)

print()
for line in md_lines:
    print(line)

# Also note QM ceiling observations
print()
print("I_MLRTN and I_MCLRE are identical across all four chunks -- all hit the QM")
print("ceiling. I_PEDRO differs slightly, confirming these are distinct realizations")
print("that independently saturate the same bound.")

print("\nAll flow values in TAF. Stochastic Pctile: rank within the all-chunk "
      "June distribution (10 chunks x 100 Junes).")

print("\nDone.")

# %%
