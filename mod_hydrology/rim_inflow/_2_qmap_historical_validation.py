"""
Quantile-Mapping Historical Validation (Product A)
===================================================
Train quantile mapping on the first half of the overlap period
(Oct 1921 - Sep 1971) and validate on the second half (Oct 1971 - Dec 2018).

For each CalSim/VIC pair from CalSim3_VIC_name_mapping.csv:
- Compute pre-adjustment QMAP and skill metrics (R-squared, NSE)
- Enforce anchor/tributary mass balance (post-adjustment)
- Compare VIC baseline, QMAP pre-adj, and QMAP post-adj

Inputs
------
- CalSim baseline DSS:    CalSim3/__calsim_sv_default__.dss
- Product A VIC routed:   mod_forcing/vic/output/routed/Product_A/1/
- Name mapping:           reference/CalSim3_VIC_name_mapping.csv
- Anchor map:             reference/RimInflowAnchor.xlsx

Outputs
-------
- _2_qmap_historical_validation/
  - calsim_qmap_validation_TS.csv   (row-level qmap results)
  - calsim_VIC_TS.csv               (VIC baseline diagnostics, full overlap)
  - figures/
    - TotalInflow_Bar_Normalized_NSE.png       (VIC vs QMAP normalized-NSE skill curves)
    - TotalInflow_Bar_Normalized_NSE_data.csv  (plotted data for QA/QC)
- _2_qmap_historical_validation/_product_a_validation/
  - _riminflow_productA_1972_2018.csv  (CalSim format for SV compiler)

Usage
-----
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
"""

import os, sys, numpy as np, pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_inventory_dir, get_module_generated_dir
from utils.quantile_mapping import qmap_single
from utils import dss_io

_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_vic_gen = get_module_generated_dir("mod_forcing/vic")

# RESULTS ROOT
BASE_RESULTS_DIR = str(_gen / "output" / "_2_qmap_historical_validation")
OUTPUT_DIR       = BASE_RESULTS_DIR
FIGURES_DIR      = os.path.join(BASE_RESULTS_DIR, "figures")
VALIDATION_DIR   = str(_gen / "output" / "_2_qmap_historical_validation" / "_product_a_validation")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(VALIDATION_DIR, exist_ok=True)

# CONFIG
master_xlsx  = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
dss_file     = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
vic_dir      = str(_vic_gen / "output" / "routed" / "Product_A" / "1")
ANCHOR_XLSX     = str(_SCRIPT_DIR / "reference" / "RimInflowAnchor.xlsx")
NAME_MAP_CSV    = str(_SCRIPT_DIR / "reference" / "CalSim3_VIC_name_mapping.csv")

vic_end_year = 2018

df_master  = pd.read_excel(master_xlsx, sheet_name="MASTER")
col_C, col_I = df_master.columns[2], df_master.columns[8]

# Filter for "Rim Inflow"
df_inflow    = df_master[df_master[col_I].astype(str).str.strip().str.lower() == 'rim inflow']
calsim_names = df_inflow[col_C].dropna().unique().tolist()

# CalSim <-> VIC matched pairs (from name mapping CSV)
df_pairs = pd.read_csv(NAME_MAP_CSV).rename(columns={'CS3_Inflow': 'CalSim_Inflow'})
df_pairs = df_pairs.dropna(subset=['CalSim_Inflow', 'VIC_Inflow'])
df_pairs = df_pairs[df_pairs['VIC_Inflow'].str.strip() != '']

# Preserve CSV order of CalSim inflows for all outputs
master_order = df_pairs['CalSim_Inflow'].tolist()


# METRICS
def nse(sim, obs):
    sim = np.asarray(sim, dtype=float); obs = np.asarray(obs, dtype=float)
    m = np.isfinite(sim) & np.isfinite(obs)
    if m.sum() < 2: return np.nan
    sim = sim[m]; obs = obs[m]
    den = np.sum((obs - np.mean(obs))**2)
    if den == 0: return np.nan
    return 1 - np.sum((obs - sim)**2) / den

def pearson_r(a, b):
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2: return np.nan
    a = a[m]; b = b[m]
    if np.nanstd(a) == 0 or np.nanstd(b) == 0: return np.nan
    return float(np.corrcoef(a, b)[0, 1])

# Robust percent error: returns NaN if denom ~ 0 or non-finite
def pct_error(num, den, eps=1e-12):
    num = np.asarray(num, dtype=float); den = np.asarray(den, dtype=float)
    out = np.full_like(den, np.nan, dtype=float)
    m = np.isfinite(num) & np.isfinite(den) & (np.abs(den) > eps)
    out[m] = 100.0 * num[m] / den[m]
    return out

# 2. LOAD ALL VIC (CS3_<VIC>_qmo.csv with [date,value])
def load_vic_dir(vic_path:str)->pd.DataFrame:
    data = {}
    for file in os.listdir(vic_path):
        if not (file.startswith("CS3_") and file.endswith("_qmo.csv")):
            continue
        name  = file[len("CS3_"):-len("_qmo.csv")]  # VIC inflow name
        fpath = os.path.join(vic_path, file)
        df    = pd.read_csv(fpath, header=None)
        idx   = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        ser = pd.Series(df.iloc[:, 1].values, index=idx, name=name)
        # normalize to month-end to match CalSim
        ser.index = pd.to_datetime(pd.to_datetime(ser.index).to_period('M').to_timestamp('M'))
        data[name] = ser
    return pd.DataFrame(data)

# 3. READ CALSIM (DSS)
def excel_to_partB(name:str) -> str:
    return name.upper().replace(' ','_')

def read_calsim_monthly_multi(dssfile, strList):
    full_idx = pd.date_range('1915-01-31', f'{vic_end_year}-12-31', freq='ME')
    with dss_io.open_dss(dssfile, version=6, catalog_flag=True) as dss:
        paths   = dss.getPathnameList("/*/*/*/*/1MON/*")
        bucket  = {}
        for p in paths:
            b = p.strip('/').split('/')[1].upper()
            bucket.setdefault(b, []).append(p)

        data = {}
        for inflow in strList:
            b = excel_to_partB(inflow)
            if b not in bucket:
                continue
            master = pd.Series(index=full_idx, dtype=float)
            for p in sorted(bucket[b], key=lambda x: x.split('/')[3]):
                ts   = dss.read_ts(p, trim_missing=True)
                vals = np.where(ts.values <= -900, np.nan, ts.values)
                idx  = (pd.to_datetime(ts.pytimes).to_period('M') - 1).to_timestamp('M')
                master.update(pd.Series(vals, index=idx))
            if master.notna().any():
                data[inflow] = master
    return pd.DataFrame(data)

# 4. VALIDATION LOOP
def ser_to_df(s:pd.Series):
    return pd.DataFrame({'year':s.index.year,'month':s.index.month,'value':s.values})

# Mass-balance enforcement
def enforce_anchor_mass_balance(qdf: pd.DataFrame, mapping_cal: pd.DataFrame):
    if mapping_cal.empty:
        return qdf.assign(Flow_QM_Adj=qdf["Flow_QM"]), pd.DataFrame(columns=["Anchor_CalSim","WY","Month","Sum_Trib_Adj","Anchor_Flow","Diff","AbsDiff"])

    df = qdf.copy()
    anchors = set(mapping_cal["Anchor_CalSim"].unique())

    anc = (df[df["Series"].isin(anchors)]
           [["Series","WY","Month","Flow_QM"]]
           .rename(columns={"Series":"Anchor_CalSim","Flow_QM":"Anchor_QM"}))

    trib = df.merge(mapping_cal, left_on="Series", right_on="Trib_CalSim", how="inner")

    tsum = (trib.groupby(["Anchor_CalSim","WY","Month"], as_index=False)["Flow_QM"]
                 .sum().rename(columns={"Flow_QM":"Sum_Trib_QM"}))

    mb = (trib.merge(tsum, on=["Anchor_CalSim","WY","Month"], how="left")
              .merge(anc,  on=["Anchor_CalSim","WY","Month"], how="left"))

    delta = (mb["Anchor_QM"] - mb["Sum_Trib_QM"]).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = mb["Flow_QM"] / mb["Sum_Trib_QM"]
        mb["Flow_QM_Adj"] = np.where(mb["Sum_Trib_QM"].abs()>0, mb["Flow_QM"] + delta*share, mb["Flow_QM"])

    adj_tbl = mb[["Trib_CalSim","Year","Month","Flow_QM_Adj"]].rename(columns={"Trib_CalSim":"Series"})
    out = df.merge(adj_tbl, on=["Series","Year","Month"], how="left")
    out["Flow_QM_Adj"] = out["Flow_QM_Adj"].fillna(out["Flow_QM"])

    trib_after = (out.merge(mapping_cal, left_on="Series", right_on="Trib_CalSim", how="inner")
                    .groupby(["Anchor_CalSim","WY","Month"], as_index=False)["Flow_QM_Adj"]
                    .sum().rename(columns={"Flow_QM_Adj":"Sum_Trib_Adj"}))
    anc_after  = (out[out["Series"].isin(anchors)]
                    .rename(columns={"Series":"Anchor_CalSim","Flow_QM":"Anchor_Flow"})
                    [["Anchor_CalSim","WY","Month","Anchor_Flow"]])
    check = trib_after.merge(anc_after, on=["Anchor_CalSim","WY","Month"], how="left")
    check["Diff"]    = check["Anchor_Flow"] - check["Sum_Trib_Adj"]
    check["AbsDiff"] = check["Diff"].abs()
    return out, check

def _pearson_safe(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2: return np.nan
    return float(np.corrcoef(a[m], b[m])[0,1])

def _nse_safe(sim, obs):
    sim = np.asarray(sim, float); obs = np.asarray(obs, float)
    m = np.isfinite(sim) & np.isfinite(obs)
    if m.sum() < 2: return np.nan
    sim = sim[m]; obs = obs[m]
    den = np.sum((obs - np.mean(obs))**2)
    if den == 0: return np.nan
    return 1 - np.sum((obs - sim)**2) / den


def normalized_nse(values):
    # Excel `TotalInflow_Bar` normalization: 1/(2 - NSE). Negative NSE stays
    # valid (maps to a low positive value); no min-max scaling, no clipping.
    # Non-finite results (incl. denominator non-finite/zero) -> NaN.
    values = np.asarray(values, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 1.0 / (2.0 - values)
    out[~np.isfinite(out)] = np.nan
    return out


def make_total_inflow_bar_figure(detail_df: pd.DataFrame, output_dir: str) -> None:
    """Reproduce the Excel `TotalInflow_Bar` sheet figure: independently sorted,
    normalized NSE curves comparing VIC vs post-adjusted QMAP skill across CS3
    rim inflows. Smooth XY line chart (no markers), not a bar chart.
    """
    # One row per inflow: skill metrics are repeated monthly, so take the first.
    per_inflow = (detail_df.groupby("CalSim", observed=True)
                           .agg(vic_nse=("vic_NSE_TestPeriod", "first"),
                                qmap_nse=("qmap_NSE_TestPeriod_postAdj", "first")))
    vic_nse  = pd.to_numeric(per_inflow["vic_nse"],  errors="coerce")
    qmap_nse = pd.to_numeric(per_inflow["qmap_nse"], errors="coerce")

    # Sort each series ascending, independently.
    vic_sorted  = np.sort(vic_nse.dropna().to_numpy(float))
    qmap_sorted = np.sort(qmap_nse.dropna().to_numpy(float))

    # Normalize via 1/(2 - NSE); drop only non-finite normalized values.
    vic_norm  = normalized_nse(vic_sorted)
    qmap_norm = normalized_nse(qmap_sorted)
    vm = np.isfinite(vic_norm);  vic_sorted  = vic_sorted[vm];  vic_norm  = vic_norm[vm]
    qm = np.isfinite(qmap_norm); qmap_sorted = qmap_sorted[qm]; qmap_norm = qmap_norm[qm]

    # x-index 1..N for each curve.
    x_vic  = np.arange(1, len(vic_norm) + 1)
    x_qmap = np.arange(1, len(qmap_norm) + 1)
    n = max(len(vic_norm), len(qmap_norm))

    # ---- Figure (styled to match the Excel TotalInflow_Bar chart) ----
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_vic,  vic_norm,  color="#C00000", linewidth=1.5, label="VIC")
    ax.plot(x_qmap, qmap_norm, color="#4F81BD", linewidth=1.5, label="VIC-QMAP")
    ax.set_xlabel("CS3 Rim Inflows (idx)")
    ax.set_ylabel("Normalize NSE (1/(2-NSE))")
    ax.set_xlim(0, n + 1)
    ax.set_ylim(0, 1)
    ax.set_yticks(np.arange(0.0, 1.0 + 1e-9, 0.1))   # gridlines every 0.1
    ax.grid(True, which="major", color="0.85", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.08))

    fig_path = os.path.join(output_dir, "TotalInflow_Bar_Normalized_NSE.png")
    fig.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ---- QA/QC data CSV (pad shorter array with NaN) ----
    rows = max(len(vic_sorted), len(qmap_sorted))
    def _pad(arr):
        out = np.full(rows, np.nan, dtype=float)
        out[:len(arr)] = arr
        return out
    qa = pd.DataFrame({
        "idx":                 np.arange(1, rows + 1),
        "VIC_NSE_sorted":      _pad(vic_sorted),
        "QMAP_NSE_sorted":     _pad(qmap_sorted),
        "VIC_Normalized_NSE":  _pad(vic_norm),
        "QMAP_Normalized_NSE": _pad(qmap_norm),
    })
    qa_path = os.path.join(output_dir, "TotalInflow_Bar_Normalized_NSE_data.csv")
    qa.to_csv(qa_path, index=False)

    print(f"\nTotalInflow_Bar figure: {fig_path}")
    print(f"  plotted {len(vic_norm)} VIC / {len(qmap_norm)} QMAP inflows; data: {qa_path}")


def main():
    df_vic_all    = load_vic_dir(vic_dir)
    df_calsim_all = read_calsim_monthly_multi(dss_file, calsim_names)

    detail_rows=[]  # row-wise test-period details (preAdj values)
    vic_detail_rows=[]  # VIC diagnostics over full overlap

    for _, row in df_pairs.iterrows():
        cal = row['CalSim_Inflow']; vic = row['VIC_Inflow']
        if cal not in df_calsim_all or vic not in df_vic_all:
            continue

        joined = pd.concat([df_vic_all[vic], df_calsim_all[cal]], axis=1, join='inner').dropna()
        if joined.empty:
            continue
        joined.columns=['basis','target']   # basis = VIC, target = CalSim

        # Water-year split: Oct 1921-Sep 1971 (train), Oct 1971-Dec vic_end_year (test)
        b_train = joined.loc['1921-10-01':'1971-09-30','basis']; t_train = joined.loc['1921-10-01':'1971-09-30','target']
        b_test  = joined.loc['1971-10-01':f'{vic_end_year}-12-31','basis']; t_test  = joined.loc['1971-10-01':f'{vic_end_year}-12-31','target']
        if b_train.empty or t_train.empty or b_test.empty or t_test.empty:
            continue

        # VIC baseline diagnostics over full overlap
        calsim_vals = joined['target'].to_numpy(float)
        vic_vals    = joined['basis'].to_numpy(float)
        vic_pct_err = pct_error(vic_vals - calsim_vals, calsim_vals)  # robust
        vic_error   = vic_vals - calsim_vals
        vic_r_full  = pearson_r(vic_vals, calsim_vals)
        vic_r2_full = (vic_r_full**2) if np.isfinite(vic_r_full) else np.nan

        for ts, v_val, a_val, ep, ea in zip(joined.index, vic_vals, calsim_vals, vic_pct_err, vic_error):
            vic_detail_rows.append({
                "CalSim":   cal,
                "VIC_Name": vic,
                "Year":     ts.year,
                "Month":    ts.month,
                "Pearson R-squared (Full Period)": vic_r2_full,
                "VIC_val":  v_val,
                "cs3_val":  a_val,   # standardized name for CalSim actuals
                "VIC_Error_pct": ep,
                "VIC_Error":     ea,
            })

        # VIC baseline skill (test window) for side-by-side reporting
        vic_r_testperiod   = pearson_r(b_test.values, t_test.values)
        vic_r2_testperiod  = (vic_r_testperiod**2) if np.isfinite(vic_r_testperiod) else np.nan
        vic_nse_testperiod = nse(b_test.values, t_test.values)

        # ---- QMAP on TEST window only ---------------------------------------
        qmap = qmap_single(ser_to_df(b_test), ser_to_df(b_train), ser_to_df(t_train))
        qmap['actual'] = t_test.values
        qmap['year']   = qmap['year'].astype(int)

        # Pre-adjustment arrays & skill
        q_a = qmap['actual'].to_numpy(float)                  # CalSim test values
        q_q = qmap['quantile_mapped_value'].to_numpy(float)   # QMAP preAdj test values
        qmap_r_pre   = pearson_r(q_q, q_a)
        qmap_r2_pre  = (qmap_r_pre**2) if np.isfinite(qmap_r_pre) else np.nan
        qmap_nse_pre = nse(q_q, q_a)

        # Row-wise preAdj values + naive % error (we will overwrite with robust later)
        with np.errstate(divide='ignore', invalid='ignore'):
            q_pct = (q_q - q_a) / q_a * 100.0
        q_pct[~np.isfinite(q_pct)] = np.nan
        q_err = q_q - q_a

        for ts, basis_val, qval, act_val, ep, ea in zip(b_test.index, b_test.values, q_q, q_a, q_pct, q_err):
            detail_rows.append({
                "CalSim":         cal,
                "Matched_inflow": vic,
                "Year":           ts.year,
                "Month":          ts.month,

                # VIC skill (test window)
                "vic_rPearson_TestPeriod":  round(vic_r_testperiod, 3)  if np.isfinite(vic_r_testperiod)  else np.nan,
                "vic_r2Pearson_TestPeriod": round(vic_r2_testperiod, 3) if np.isfinite(vic_r2_testperiod) else np.nan,
                "vic_NSE_TestPeriod":       round(vic_nse_testperiod, 3) if np.isfinite(vic_nse_testperiod) else np.nan,

                # QMAP skill (preAdj; test window)
                "qmap_rPearson_TestPeriod_preAdj":  round(qmap_r_pre, 3)   if np.isfinite(qmap_r_pre)   else np.nan,
                "qmap_r2Pearson_TestPeriod_preAdj": round(qmap_r2_pre, 3)  if np.isfinite(qmap_r2_pre)  else np.nan,
                "qmap_NSE_TestPeriod_preAdj":       round(qmap_nse_pre, 3) if np.isfinite(qmap_nse_pre) else np.nan,

                # Values & PRE-adj errors at this moment (temporary; will robustify below)
                "vic_val":        basis_val,
                "cs3_val":        act_val,
                "qmap_preAdj":    qval,
                "error_pct_preAdj": ep,
                "Error_preAdj":     ea,
            })

    # 5. BUILD DATAFRAMES
    # Detail (QMAP test-period rows)
    detail_df = pd.DataFrame(detail_rows)
    detail_df['CalSim'] = pd.Categorical(detail_df['CalSim'], categories=master_order, ordered=True)
    detail_df = detail_df.sort_values(['CalSim', 'Year', 'Month'])

    # VIC detailed diagnostics (full overlap)
    vic_detail_df = pd.DataFrame(vic_detail_rows)
    vic_detail_df['CalSim'] = pd.Categorical(vic_detail_df['CalSim'], categories=master_order, ordered=True)
    vic_detail_df = vic_detail_df.sort_values(['CalSim', 'Year', 'Month'])

    # ---------------------- ANCHOR MASS BALANCE --------------------------
    # Monthly coverage assurance for anchors & tributaries:
    # Ensures that for each Anchor_CalSim and (WY,Month), all expected members
    # (anchor + tributaries) have a QMAP value; logs missing member-months.

    # Input for mass balance: preAdj QMAP
    qmap_cal = (detail_df[["CalSim","Year","Month","qmap_preAdj"]]
                .rename(columns={"CalSim":"Series","qmap_preAdj":"Flow_QM"}).copy())
    qmap_cal["Series"] = qmap_cal["Series"].astype(str).str.strip()
    qmap_cal["Year"]   = qmap_cal["Year"].astype(int)
    qmap_cal["Month"]  = qmap_cal["Month"].astype(int)
    qmap_cal["WY"]     = np.where(qmap_cal["Month"] >= 10, qmap_cal["Year"] + 1, qmap_cal["Year"])

    # Anchor map
    w = pd.read_excel(ANCHOR_XLSX)
    a = w.columns[0]
    anchor_map_cal = (w.melt(id_vars=[a], value_vars=w.columns[1:], var_name="_", value_name="Trib_CalSim")
                        .drop(columns="_")
                        .rename(columns={a:"Anchor_CalSim"})
                        .dropna(subset=["Trib_CalSim"]))
    anchor_map_cal["Anchor_CalSim"] = anchor_map_cal["Anchor_CalSim"].astype(str).str.strip()
    anchor_map_cal["Trib_CalSim"]   = anchor_map_cal["Trib_CalSim"].astype(str).str.strip()
    anchor_map_cal = anchor_map_cal.loc[anchor_map_cal["Trib_CalSim"]!="", ["Anchor_CalSim","Trib_CalSim"]].drop_duplicates()

    # Filter to present CalSim inflows
    present_calsim = set(calsim_names)
    anchor_map_cal = anchor_map_cal[
        anchor_map_cal["Anchor_CalSim"].isin(present_calsim) &
        anchor_map_cal["Trib_CalSim"].isin(present_calsim)
    ].drop_duplicates()

    # Coverage check
    members_anchor = anchor_map_cal[["Anchor_CalSim"]].drop_duplicates().copy()
    members_anchor["Member"] = members_anchor["Anchor_CalSim"]
    members_anchor["MemberRole"] = "Anchor"

    members_trib = anchor_map_cal.rename(columns={"Trib_CalSim":"Member"})[["Anchor_CalSim","Member"]].copy()
    members_trib["MemberRole"] = "Trib"

    members = pd.concat([members_anchor, members_trib], ignore_index=True)

    anc_months = (qmap_cal[qmap_cal["Series"].isin(anchor_map_cal["Anchor_CalSim"])]
                    .rename(columns={"Series":"Anchor_CalSim"})
                    [["Anchor_CalSim","WY","Month"]]
                    .drop_duplicates())

    trib_months = (qmap_cal.merge(anchor_map_cal, left_on="Series", right_on="Trib_CalSim", how="inner")
                     [["Anchor_CalSim","WY","Month"]]
                     .drop_duplicates())

    anchor_union_keys = pd.concat([anc_months, trib_months], ignore_index=True).drop_duplicates()

    expected = anchor_union_keys.merge(members, on="Anchor_CalSim", how="left")

    actual = (qmap_cal.dropna(subset=["Flow_QM"])
                        [["Series","WY","Month"]]
                        .rename(columns={"Series":"Member"})
                        .drop_duplicates())
    expected = expected.merge(actual.assign(has=True), on=["Member","WY","Month"], how="left")

    missing = expected[expected["has"].isna()].copy()
    missing = missing[["Anchor_CalSim","Member","MemberRole","WY","Month"]].sort_values(
                ["Anchor_CalSim","WY","Month","MemberRole","Member"])

    n_missing = len(missing)
    n_anchors_with_gaps = missing["Anchor_CalSim"].nunique()
    print(f"[COVERAGE CHECK] Missing member-months: {n_missing} across {n_anchors_with_gaps} anchors.")
    if n_missing > 0:
        LOG_DIR = os.path.join(OUTPUT_DIR, "_anchor_checks")
        os.makedirs(LOG_DIR, exist_ok=True)
        missing.to_csv(os.path.join(LOG_DIR, "missing_member_months_calsim.csv"), index=False)

    # Apply mass-balance;
    adjusted_cal, check_df = enforce_anchor_mass_balance(qmap_cal, anchor_map_cal)
    print("Mass-balance max AbsDiff:", float(check_df["AbsDiff"].max()) if not check_df.empty else 0.0)

    detail_df = detail_df.merge(
        adjusted_cal[["Series","Year","Month","Flow_QM_Adj"]].rename(columns={"Series":"CalSim"}),
        on=["CalSim","Year","Month"], how="left"
    )

    # Post-adjustment flow (fallback to preAdj if nothing to adjust)
    detail_df["qmap_postAdj"] = np.where(detail_df["Flow_QM_Adj"].notna(),
                                         detail_df["Flow_QM_Adj"],
                                         detail_df["qmap_preAdj"])
    detail_df.drop(columns=["Flow_QM_Adj"], inplace=True)

    # Robust percent errors for BOTH preAdj and postAdj
    num_pre = (detail_df["qmap_preAdj"]  - detail_df["cs3_val"]).to_numpy(float)
    num_pos = (detail_df["qmap_postAdj"] - detail_df["cs3_val"]).to_numpy(float)
    den     =  detail_df["cs3_val"].to_numpy(float)

    detail_df["error_pct_preAdj"]  = pct_error(num_pre, den)
    detail_df["Error_preAdj"]      = num_pre
    detail_df["error_pct_postAdj"] = pct_error(num_pos, den)
    detail_df["Error_postAdj"]     = num_pos

    post_metrics = (
        detail_df.groupby("CalSim", as_index=False, observed=True)
                 .apply(lambda g: pd.Series({
                     "qmap_rPearson_TestPeriod_postAdj":  _pearson_safe(g["qmap_postAdj"].values, g["cs3_val"].values),
                     "qmap_r2Pearson_TestPeriod_postAdj": (lambda r: r*r if np.isfinite(r) else np.nan)(
                         _pearson_safe(g["qmap_postAdj"].values, g["cs3_val"].values)),
                     "qmap_NSE_TestPeriod_postAdj":       _nse_safe(g["qmap_postAdj"].values, g["cs3_val"].values),
                 }), include_groups=False)
                 .reset_index(drop=True)
    )
    detail_df = detail_df.merge(post_metrics, on="CalSim", how="left")

    # TotalInflow_Bar figure: normalized NSE skill curves (VIC vs QMAP postAdj)
    make_total_inflow_bar_figure(detail_df, FIGURES_DIR)

    # 6. WRITE ORGANIZED CSVs
    export_cols = [
        # IDs
        "CalSim", "Matched_inflow", "Year", "Month",
        # Core values (grouped)
        "vic_val", "cs3_val", "qmap_preAdj", "qmap_postAdj",
        # Errors (grouped)
        "error_pct_preAdj", "error_pct_postAdj", "Error_preAdj", "Error_postAdj",
        # VIC baseline skill (test window)
        "vic_rPearson_TestPeriod", "vic_r2Pearson_TestPeriod", "vic_NSE_TestPeriod",
        # QMAP skill (test window; pre/post)
        "qmap_rPearson_TestPeriod_preAdj", "qmap_rPearson_TestPeriod_postAdj",
        "qmap_r2Pearson_TestPeriod_preAdj","qmap_r2Pearson_TestPeriod_postAdj",
        "qmap_NSE_TestPeriod_preAdj",      "qmap_NSE_TestPeriod_postAdj",
    ]
    export_cols = [c for c in export_cols if c in detail_df.columns]
    (detail_df[export_cols]
     .sort_values(["CalSim","Year","Month"])
     .to_csv(os.path.join(OUTPUT_DIR, "calsim_qmap_validation_TS.csv"), index=False))

    # VIC CSV (full overlap; standardized cs3_val)
    vic_detail_df.to_csv(os.path.join(OUTPUT_DIR, "calsim_VIC_TS.csv"), index=False)

    # -- 6. PRODUCT A VALIDATION CSV (for SV compiler) --------------------
    # Write final CalSim-format CSV (Part B, Part C, Year, Month, Value) to
    # _product_a_validation/ for consumption by the SV compiler.

    # Build Part B -> Part C map from the inventory (col index 2 = Part B, 3 = Part C)
    col_partB = df_master.columns[2]
    col_partC = df_master.columns[3]
    _partc_map = {}
    for _, r in df_master[[col_partB, col_partC]].dropna().iterrows():
        b = str(r[col_partB]).upper().replace(' ', '_')
        c = str(r[col_partC]).upper().replace(' ', '_')
        if b and c:
            _partc_map[b] = c

    val_rows = []
    for _, r in detail_df.iterrows():
        b = excel_to_partB(str(r['CalSim']))
        c = _partc_map.get(b, 'FLOW-INFLOW')
        val_rows.append({
            'Part B': b,
            'Part C': c,
            'Year': int(r['Year']),
            'Month': int(r['Month']),
            'Value': r['qmap_postAdj'],
        })

    df_val_csv = pd.DataFrame(val_rows).sort_values(['Part B', 'Year', 'Month']).reset_index(drop=True)
    val_csv_path = os.path.join(VALIDATION_DIR, "_riminflow_productA_1972_2018.csv")
    df_val_csv.to_csv(val_csv_path, index=False)
    print(f"\nProduct A validation CSV: {val_csv_path}")
    print(f"  {len(df_val_csv):,} rows, {df_val_csv['Part B'].nunique()} inflows")


if __name__ == "__main__":
    main()
