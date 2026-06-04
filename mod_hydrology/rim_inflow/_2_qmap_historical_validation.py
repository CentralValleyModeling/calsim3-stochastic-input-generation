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
    - Monthly_Avg_Err_VIC.png                  (VIC avg monthly error; fixed major-reservoir set)
    - Monthly_Avg_Err_VIC-QM.png               (VIC-QM avg monthly error; fixed major-reservoir set)
    - Monthly_Avg_Err_Annual.png               (clustered annual avg error: VIC vs VIC-QM)
    - Monthly_Avg_<loc>.png                    (CS3 vs VIC vs Q-MAP monthly means; only when --locations is passed)
    - Monthly_Avg_PctErr_<loc>.png             (monthly median % error + annual WY % error box; only when --locations is passed)
- _2_qmap_historical_validation/_product_a_validation/
  - _riminflow_productA_1972_2018.csv  (CalSim format for SV compiler)

Usage
-----
    # Full validation run (default behavior / outputs):
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py

    # Also write per-location monthly-average comparison figures:
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py --locations UNIMP_OROV
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py --locations UNIMP_OROV FOLSM_INFLOW
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py --locations UNIMP_OROV,I_MLRTN_IMP,I_SHSTA
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py --locations ALL

    # Major reservoir unimpaired inflows:
    python mod_hydrology/rim_inflow/_2_qmap_historical_validation.py --locations \
        I_SHSTA UNIMP_OROV UNIMP_FOLS UNIMP_YUBA UNIMP_TU \
        UNIMP_SJ UNIMP_TRIN UNIMP_ST UNIMP_ME UNIMP_SRBB
"""

import os, sys, re, argparse, calendar, numpy as np, pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
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
    # TotalInflow_Bar normalization: 1/(2 - NSE). Negative NSE stays
    # valid (maps to a low positive value); no min-max scaling, no clipping.
    # Non-finite results (incl. denominator non-finite/zero) -> NaN.
    values = np.asarray(values, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 1.0 / (2.0 - values)
    out[~np.isfinite(out)] = np.nan
    return out


def make_total_inflow_bar_figure(detail_df: pd.DataFrame, output_dir: str) -> None:
    """`TotalInflow_Bar` figure: independently sorted,
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

    # ---- Figure (TotalInflow_Bar chart) ----
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x_vic,  vic_norm,  color="#C00000", linewidth=1.5, label="VIC Product A")
    ax.plot(x_qmap, qmap_norm, color="#2E75B6", linewidth=1.5, label="VIC-QMAP Product A")
    ax.set_xlabel("CS3 Rim Inflows (idx)", fontsize=11)
    ax.set_ylabel("Normalize NSE (1/(2-NSE))", fontsize=11)
    ax.set_xlim(0, n + 1)
    ax.set_ylim(0, 1)
    ax.set_yticks(np.arange(0.0, 1.0 + 1e-9, 0.1))   # gridlines every 0.1
    ax.tick_params(labelsize=10)
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


# Water-year month order (Oct -> Sep) for monthly-average plots.
_WY_MONTH_ORDER = [10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9]

# Monthly_Avg series colors.
_MONTHLY_AVG_SERIES = [
    ("CS3 Historical",  "cs3_val", "black"),       # CS3
    ("VIC Product A",   "vic_val", "#C00000"),     # VIC (red)
    ("VIC-QMAP Product A", None,   "#2E75B6"),     # VIC-QMAP (blue; col filled in per call)
]

# Fixed location set always shown in the Monthly_Avg_Err validation figures
# (independent of --locations). Missing entries are warned and skipped.
_MONTHLY_AVG_ERR_LOCATIONS = [
    "I_SHSTA", "UNIMP_OROV", "UNIMP_FOLS", "UNIMP_YUBA", "UNIMP_TU",
    "UNIMP_SJ", "UNIMP_TRIN", "UNIMP_ST", "UNIMP_ME",
]


def sanitize_filename(name: str) -> str:
    """Make a string safe for use as a filename: replace spaces and unsafe
    characters (/ \\ : * ? " < > | and similar) with underscores."""
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', "_", str(name)).strip("_")
    return cleaned or "unnamed"


def complete_water_year_filter(df: pd.DataFrame, wy_start: int = 1972,
                               wy_end: int = vic_end_year) -> pd.DataFrame:
    """Return rows within complete water years only.

    Adds a `WY` column (WY = Year+1 for Oct-Dec, else Year), keeps
    wy_start <= WY <= wy_end, then drops any WY that is missing months
    (keeps only WYs where all 12 calendar months are present).
    """
    out = df.copy()
    out["Year"]  = out["Year"].astype(int)
    out["Month"] = out["Month"].astype(int)
    out["WY"]    = np.where(out["Month"] >= 10, out["Year"] + 1, out["Year"]).astype(int)
    out = out[(out["WY"] >= wy_start) & (out["WY"] <= wy_end)]
    if out.empty:
        return out
    month_counts = out.groupby("WY")["Month"].nunique()
    complete_wys = month_counts[month_counts == 12].index
    return out[out["WY"].isin(complete_wys)]


def make_monthly_avg_location_figure(detail_df: pd.DataFrame, location: str, output_dir: str,
                                     qmap_col: str = "qmap_postAdj",
                                     include_annual_box: bool = True) -> dict:
    """`Monthly_Avg` figure for one inflow: 12-point average monthly
    hydrograph (CS3 Historical vs VIC Product A vs Q-MAP Product A) in water-year
    month order (Oct -> Sep), optionally with an annual WY-total box inset.

    Returns a dict: {location, status, n_complete_wy, figure_path}. status is one
    of "ok", "missing" (location absent), or "no_complete_wy".
    """
    names = detail_df["CalSim"].astype(str)
    mask  = names.str.lower() == str(location).strip().lower()
    if not mask.any():
        print(f"[WARN] --locations: '{location}' not found in results; skipping.")
        return {"location": location, "status": "missing", "n_complete_wy": 0, "figure_path": None}
    canonical = names[mask].iloc[0]

    loc_df = complete_water_year_filter(detail_df[mask].copy())
    if loc_df.empty:
        print(f"[WARN] --locations: '{canonical}' has no complete water years "
              f"(WY1972-{vic_end_year}); skipping.")
        return {"location": canonical, "status": "no_complete_wy", "n_complete_wy": 0, "figure_path": None}
    n_wy = int(loc_df["WY"].nunique())

    series = [(lbl, (qmap_col if col is None else col), color)
              for lbl, col, color in _MONTHLY_AVG_SERIES]
    value_cols = [col for _, col, _ in series]
    for c in value_cols:
        loc_df[c] = pd.to_numeric(loc_df[c], errors="coerce")

    monthly = (loc_df.groupby("Month")[value_cols].mean().reindex(_WY_MONTH_ORDER))
    annual  = (loc_df.groupby("WY")[value_cols].sum(min_count=12))

    os.makedirs(output_dir, exist_ok=True)

    # ---- Figure: monthly hydrograph (left) + optional annual box panel (right) ----
    if include_annual_box:
        fig, (ax, ax_box) = plt.subplots(
            1, 2, figsize=(9, 4.5),
            gridspec_kw={"width_ratios": [3.5, 1], "wspace": 0.22})
    else:
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax_box = None

    x = np.arange(len(_WY_MONTH_ORDER))
    for label, col, color in series:
        ax.plot(x, monthly[col].to_numpy(float), marker="o", markersize=5,
                linewidth=1.5, color=color, label=label)
    ax.set_xticks(x)
    ax.set_xticklabels([calendar.month_abbr[m] for m in _WY_MONTH_ORDER])
    ax.set_xlabel("Month", fontsize=11)
    ax.set_ylabel("Flow (TAF)", fontsize=11)
    ax.set_ylim(bottom=0)                              # use the vertical space (flows >= 0)
    ax.tick_params(labelsize=9)
    ax.grid(True, which="major", color="0.85", linewidth=0.6)
    ax.yaxis.set_minor_locator(AutoMinorLocator(4))   # small dividers between major y ticks
    ax.tick_params(axis="y", which="minor", length=3)
    ax.set_axisbelow(True)

    # Compact header: title, sim-period subtitle, and shared legend stacked
    # above the plots (the series colors apply to BOTH panels).
    fig.subplots_adjust(top=0.76)
    _handles, _labels = ax.get_legend_handles_labels()
    fig.legend(_handles, _labels, loc="upper center", ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 0.84))
    wy_lo, wy_hi = int(loc_df["WY"].min()), int(loc_df["WY"].max())
    fig.suptitle(str(canonical), fontsize=13, fontweight="bold", y=1.0)
    fig.text(0.5, 0.91, f"(Sim Period {wy_lo}-{wy_hi})",
             ha="center", va="center", fontsize=9, fontweight="bold")

    # ---- Annual WY-total box panel (side-by-side): CS3 / VIC / QMAP ----
    if ax_box is not None:
        box_data = [annual[col].dropna().to_numpy(float) for _, col, _ in series]
        bp = ax_box.boxplot(box_data, showfliers=False, patch_artist=True, widths=0.6,
                            showmeans=True,
                            meanprops=dict(marker="x", markeredgecolor="black",
                                           markerfacecolor="black", markersize=7))
        for patch, (_, _, color) in zip(bp["boxes"], series):
            patch.set_facecolor(color); patch.set_alpha(0.75)
        for med in bp["medians"]:
            med.set_color("black")
        ax_box.set_xticks([])
        ax_box.set_xlabel("Annual (WY)", fontsize=10)
        ax_box.set_ylabel("Annual total (TAF)", fontsize=9)
        ax_box.set_ylim(bottom=0)
        ax_box.tick_params(axis="y", labelsize=8)
        ax_box.grid(True, axis="y", color="0.9", linewidth=0.6)
        ax_box.yaxis.set_minor_locator(AutoMinorLocator(4))   # small dividers between major y ticks
        ax_box.tick_params(axis="y", which="minor", length=3)
        ax_box.set_axisbelow(True)

    fig_path = os.path.join(output_dir, f"Monthly_Avg_{sanitize_filename(canonical)}.png")
    fig.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Monthly-avg figure: {fig_path}  (complete WYs: {n_wy})")
    return {"location": canonical, "status": "ok", "n_complete_wy": n_wy, "figure_path": fig_path}


def get_qmap_pct_error_series(df: pd.DataFrame, qmap_col: str) -> pd.Series:
    """Per-row QMAP percent error for the chosen variant: reuse the precomputed
    error_pct_* column when present, else recompute robustly via pct_error()."""
    if qmap_col == "qmap_postAdj" and "error_pct_postAdj" in df.columns:
        return pd.to_numeric(df["error_pct_postAdj"], errors="coerce")
    if qmap_col == "qmap_preAdj" and "error_pct_preAdj" in df.columns:
        return pd.to_numeric(df["error_pct_preAdj"], errors="coerce")
    qmap_vals = pd.to_numeric(df[qmap_col], errors="coerce")
    cs3_vals  = pd.to_numeric(df["cs3_val"], errors="coerce")
    return pd.Series(
        pct_error((qmap_vals - cs3_vals).to_numpy(float), cs3_vals.to_numpy(float)),
        index=df.index,
    )


def make_monthly_avg_pcterr_location_figure(detail_df: pd.DataFrame, location: str, output_dir: str,
                                            qmap_col: str = "qmap_postAdj") -> dict:
    """`Monthly_Avg_PctErr` figure for one inflow: 12-point monthly MEDIAN
    percent-error line chart (VIC vs VIC-QMAP) in water-year month order, with a
    side annual water-year percent-error box-and-whisker panel.

    Percent error = 100 * (product - CS3) / CS3. VIC uses 100*(vic_val-cs3_val)/cs3_val;
    QMAP uses error_pct_postAdj/error_pct_preAdj per qmap_col (recomputed if absent).
    Uses complete water years only. Returns {location, status, n_complete_wy, figure_path}.
    """
    names = detail_df["CalSim"].astype(str)
    mask  = names.str.lower() == str(location).strip().lower()
    if not mask.any():
        print(f"[WARN] --locations: '{location}' not found in results; skipping.")
        return {"location": location, "status": "missing", "n_complete_wy": 0, "figure_path": None}
    canonical = names[mask].iloc[0]

    loc_df = complete_water_year_filter(detail_df[mask].copy())
    if loc_df.empty:
        print(f"[WARN] --locations: '{canonical}' has no complete water years "
              f"(WY1972-{vic_end_year}); skipping.")
        return {"location": canonical, "status": "no_complete_wy", "n_complete_wy": 0, "figure_path": None}
    n_wy = int(loc_df["WY"].nunique())
    wy_lo, wy_hi = int(loc_df["WY"].min()), int(loc_df["WY"].max())

    cs3 = pd.to_numeric(loc_df["cs3_val"], errors="coerce")
    vic = pd.to_numeric(loc_df["vic_val"], errors="coerce")
    loc_df["VIC_PctErr"]  = pct_error((vic - cs3).to_numpy(float), cs3.to_numpy(float))
    loc_df["QMAP_PctErr"] = get_qmap_pct_error_series(loc_df, qmap_col).to_numpy(float)

    series = [("VIC Product A",      "VIC_PctErr",  "#C00000"),
              ("VIC-QMAP Product A", "QMAP_PctErr", "#2E75B6")]

    # Monthly MEDIAN percent error, WY order.
    monthly = (loc_df.groupby("Month")[["VIC_PctErr", "QMAP_PctErr"]]
                     .median().reindex(_WY_MONTH_ORDER))

    # Annual WY percent error (one value per complete WY) for the box panel.
    ann = loc_df.groupby("WY").agg(cs3=("cs3_val", "sum"),
                                   vic=("vic_val", "sum"),
                                   qm=(qmap_col, "sum"))
    vic_ann = pct_error((ann["vic"] - ann["cs3"]).to_numpy(float), ann["cs3"].to_numpy(float))
    qm_ann  = pct_error((ann["qm"]  - ann["cs3"]).to_numpy(float), ann["cs3"].to_numpy(float))
    box_data = [vic_ann[np.isfinite(vic_ann)], qm_ann[np.isfinite(qm_ann)]]

    os.makedirs(output_dir, exist_ok=True)
    fig, (ax, ax_box) = plt.subplots(
        1, 2, figsize=(9, 4.5),
        gridspec_kw={"width_ratios": [3.5, 1], "wspace": 0.22})

    # ---- Main: monthly median percent-error lines ----
    x = np.arange(len(_WY_MONTH_ORDER))
    for label, col, color in series:
        ax.plot(x, monthly[col].to_numpy(float), marker="o", markersize=5,
                linewidth=1.5, color=color, label=label)
    ax.axhline(0, color="0.5", linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels([calendar.month_abbr[m] for m in _WY_MONTH_ORDER])
    ax.set_xlabel("Month", fontsize=11)
    ax.set_ylabel(f"Median Percent Error with CS3 ({wy_lo}-{wy_hi})", fontsize=11)
    ax.tick_params(labelsize=9)
    ax.grid(True, which="major", color="0.85", linewidth=0.6)
    ax.yaxis.set_minor_locator(AutoMinorLocator(4))
    ax.tick_params(axis="y", which="minor", length=3)
    ax.set_axisbelow(True)

    # Compact header: title, sim-period subtitle, shared legend.
    fig.subplots_adjust(top=0.76)
    _h, _l = ax.get_legend_handles_labels()
    fig.legend(_h, _l, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.84))
    fig.suptitle(str(canonical), fontsize=13, fontweight="bold", y=1.0)
    fig.text(0.5, 0.91, f"(Sim Period {wy_lo}-{wy_hi})",
             ha="center", va="center", fontsize=9, fontweight="bold")

    # ---- Side: annual WY percent-error box-and-whisker (VIC vs VIC-QMAP) ----
    bp = ax_box.boxplot(box_data, showfliers=False, patch_artist=True, widths=0.6,
                        showmeans=True,
                        meanprops=dict(marker="x", markeredgecolor="black",
                                       markerfacecolor="black", markersize=7))
    for patch, (_, _, color) in zip(bp["boxes"], series):
        patch.set_facecolor(color); patch.set_alpha(0.75)
    for med in bp["medians"]:
        med.set_color("black")
    ax_box.axhline(0, color="0.5", linewidth=0.8)
    ax_box.set_xticks([])
    ax_box.set_xlabel("Annual (WY)", fontsize=10)
    ax_box.set_ylabel("Annual Percent Error (%)", fontsize=9)
    ax_box.tick_params(axis="y", labelsize=8)
    ax_box.grid(True, axis="y", color="0.9", linewidth=0.6)
    ax_box.yaxis.set_minor_locator(AutoMinorLocator(4))
    ax_box.tick_params(axis="y", which="minor", length=3)
    ax_box.set_axisbelow(True)

    fig_path = os.path.join(output_dir, f"Monthly_Avg_PctErr_{sanitize_filename(canonical)}.png")
    fig.savefig(fig_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Monthly_Avg_PctErr figure: {fig_path}  (complete WYs: {n_wy})")
    return {"location": canonical, "status": "ok", "n_complete_wy": n_wy, "figure_path": fig_path}


def make_monthly_avg_err_figure(detail_df: pd.DataFrame, requested_locations, output_dir: str,
                                qmap_col: str = "qmap_postAdj") -> dict:
    """`Monthly_Avg_Err` figures for the selected inflows, written as THREE
    separate images:

      - Monthly_Avg_Err_VIC.png      VIC average monthly error (TAF/month)
      - Monthly_Avg_Err_VIC-QM.png   VIC-QM average monthly error (TAF/month)
      - Monthly_Avg_Err_Annual.png   clustered annual average error (TAF/yr), VIC vs VIC-QM

    Error sign convention is product - CS3 (positive = product higher than CS3):
    VIC error = vic_val - cs3_val; QMAP error = <qmap_col> - cs3_val. Uses complete
    water years only, filtered per location; requested order is preserved. Returns
    a status dict {status, locations, figure_paths}.
    """
    if not requested_locations:
        return {"status": "no_locations", "locations": [], "figure_paths": {}}

    # Resolve requested names case-insensitively to canonical CalSim names.
    names = detail_df["CalSim"].astype(str)
    lower_map = {}
    for nm in names.unique():
        lower_map.setdefault(nm.lower(), nm)

    vic_monthly, qm_monthly, vic_annual, qm_annual, used = {}, {}, {}, {}, []
    for req in requested_locations:
        canon = lower_map.get(str(req).strip().lower())
        if canon is None:
            print(f"[WARN] Monthly_Avg_Err: '{req}' not found in results; skipping.")
            continue
        if canon in used:
            continue
        d = complete_water_year_filter(detail_df[names == canon].copy())
        if d.empty:
            print(f"[WARN] Monthly_Avg_Err: '{canon}' has no complete water years "
                  f"(WY1972-{vic_end_year}); skipping.")
            continue
        cs3 = pd.to_numeric(d["cs3_val"], errors="coerce")
        d["VIC_Error"]  = pd.to_numeric(d["vic_val"], errors="coerce") - cs3
        d["QMAP_Error"] = pd.to_numeric(d[qmap_col],  errors="coerce") - cs3
        vic_monthly[canon] = d.groupby("Month")["VIC_Error"].mean().reindex(_WY_MONTH_ORDER).to_numpy(float)
        qm_monthly[canon]  = d.groupby("Month")["QMAP_Error"].mean().reindex(_WY_MONTH_ORDER).to_numpy(float)
        vic_annual[canon]  = float(d.groupby("WY")["VIC_Error"].sum().mean())   # TAF/yr
        qm_annual[canon]   = float(d.groupby("WY")["QMAP_Error"].sum().mean())
        used.append(canon)

    if not used:
        print("[WARN] Monthly_Avg_Err: no valid locations; figures not produced.")
        return {"status": "no_locations", "locations": [], "figure_paths": {}}

    os.makedirs(output_dir, exist_ok=True)
    month_labels = [calendar.month_abbr[m] for m in _WY_MONTH_ORDER]
    x = np.arange(len(_WY_MONTH_ORDER))
    cmap = plt.get_cmap("tab10")
    loc_colors = {loc: cmap(i % 10) for i, loc in enumerate(used)}

    # ---- Monthly average-error line charts (one image each) ----
    def _monthly_chart(series_by_loc, title, fname):
        fig, ax = plt.subplots(figsize=(7, 4.5))
        for loc in used:
            ax.plot(x, series_by_loc[loc], marker="o", markersize=4, linewidth=1.3,
                    color=loc_colors[loc], label=loc)
        ax.axhline(0, color="0.5", linewidth=0.8)
        ax.set_xticks(x); ax.set_xticklabels(month_labels)
        ax.set_xlabel("Month", fontsize=11)
        ax.set_ylabel("Average Monthly Error (TAF/month)", fontsize=11)
        ax.set_title(title, fontsize=12, fontweight="bold")
        ax.tick_params(labelsize=9)
        ax.grid(True, color="0.88", linewidth=0.6); ax.set_axisbelow(True)
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False, fontsize=8)
        path = os.path.join(output_dir, fname)
        fig.savefig(path, dpi=300, bbox_inches="tight"); plt.close(fig)
        return path

    p_vic = _monthly_chart(vic_monthly, "VIC Product A", "Monthly_Avg_Err_VIC.png")
    p_qm  = _monthly_chart(qm_monthly, "VIC-QMAP Product A", "Monthly_Avg_Err_VIC-QM.png")

    # ---- Clustered annual average-error bar chart (one image) ----
    fig, ax = plt.subplots(figsize=(max(7.0, 0.85 * len(used) + 3.0), 4.5))
    xb = np.arange(len(used)); w = 0.4
    ax.bar(xb - w / 2, [vic_annual[loc] for loc in used], w, label="VIC Product A", color="#C00000")
    ax.bar(xb + w / 2, [qm_annual[loc] for loc in used], w, label="VIC-QMAP Product A", color="#2E75B6")
    ax.axhline(0, color="0.4", linewidth=0.8)
    ax.set_xticks(xb)
    ax.set_xticklabels(used, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("Average Annual Error (TAF/yr)", fontsize=11)
    ax.set_title(f"Annual Error with CS3 Inflow (1972-{vic_end_year})",
                 fontsize=12, fontweight="bold")
    ax.legend(frameon=False, ncol=2, fontsize=9)
    ax.grid(True, axis="y", color="0.88", linewidth=0.6); ax.set_axisbelow(True)
    ax.tick_params(axis="y", labelsize=9)
    p_ann = os.path.join(output_dir, "Monthly_Avg_Err_Annual.png")
    fig.savefig(p_ann, dpi=300, bbox_inches="tight"); plt.close(fig)

    paths = {"vic": p_vic, "vic_qm": p_qm, "annual": p_ann}
    print(f"Monthly_Avg_Err figures ({len(used)} location(s)): "
          f"{p_vic}, {p_qm}, {p_ann}")
    return {"status": "ok", "locations": used, "figure_paths": paths}


def parse_locations(loc_args, available, master_order=None):
    """Resolve the raw --locations tokens into an ordered list of CalSim names.

    Accepts space- and/or comma-separated tokens. 'ALL' or '*' expands to every
    available location (ordered by master_order when given). Other tokens are
    matched case-insensitively to canonical names; unmatched tokens are passed
    through unchanged so the figure builder can warn about them. Returns [] when
    no tokens are supplied.
    """
    if not loc_args:
        return []
    tokens = []
    for t in loc_args:
        tokens.extend(s for s in re.split(r"[,\s]+", str(t)) if s)
    if not tokens:
        return []

    avail_list = [str(a) for a in available]
    if any(t.upper() in ("ALL", "*") for t in tokens):
        avail_set = set(avail_list)
        if master_order:
            ordered = [str(n) for n in master_order if str(n) in avail_set]
            extra   = [a for a in avail_list if a not in set(ordered)]
            return ordered + extra
        return avail_list

    lower_map = {a.lower(): a for a in avail_list}
    seen, out = set(), []
    for t in tokens:
        canon = lower_map.get(t.lower(), t)   # unknown -> keep token (figure warns)
        if canon not in seen:
            seen.add(canon); out.append(canon)
    return out


def main(locations=None, qmap_col="qmap_postAdj"):
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

    # Monthly_Avg_Err figures (VIC, VIC-QM, annual): always over the fixed
    # major-reservoir set, regardless of --locations.
    make_monthly_avg_err_figure(detail_df, _MONTHLY_AVG_ERR_LOCATIONS, FIGURES_DIR,
                                qmap_col=qmap_col)

    # Optional per-location monthly-average comparison figures (--locations).
    # Additive only: does not alter any existing output above.
    if locations is not None:
        available = list(pd.unique(detail_df["CalSim"].dropna().astype(str)))
        requested = parse_locations(locations, available, master_order)
        monthly_dir = FIGURES_DIR
        if not requested:
            print("[WARN] --locations supplied but no locations resolved; "
                  "no monthly-average figures produced.")
        else:
            results = [make_monthly_avg_location_figure(detail_df, loc, monthly_dir,
                                                        qmap_col=qmap_col)
                       for loc in requested]
            for loc in requested:
                make_monthly_avg_pcterr_location_figure(detail_df, loc, monthly_dir,
                                                        qmap_col=qmap_col)
            n_ok = sum(1 for r in results if r["status"] == "ok")
            print(f"\nMonthly-avg: produced {n_ok}/{len(requested)} requested location "
                  f"figure(s) in {monthly_dir}")

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


def parse_args():
    p = argparse.ArgumentParser(
        description="Quantile-mapping historical validation (Product A). Without "
                    "--locations, runs the full validation and writes the usual "
                    "outputs. With --locations, additionally writes per-location "
                    "Monthly_Avg comparison figures.",
        epilog="examples:\n"
               "  --locations UNIMP_OROV\n"
               "  --locations UNIMP_OROV,FOLSM_INFLOW\n"
               "  --locations ALL          (or: --locations *)\n"
               "  --locations I_SHSTA UNIMP_OROV UNIMP_FOLS UNIMP_YUBA UNIMP_TU "
               "UNIMP_SJ UNIMP_TRIN UNIMP_ST UNIMP_ME   (major reservoir unimpaired inflows)",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--locations", nargs="*", default=None, metavar="LOC",
                   help="One or more CalSim inflow names (space and/or comma "
                        "separated), or ALL / * for every processed inflow. "
                        "Matched case-insensitively. "
                        "Example: --locations UNIMP_OROV,FOLSM_INFLOW")
    p.add_argument("--qmap-col", choices=["qmap_preAdj", "qmap_postAdj"],
                   default="qmap_postAdj",
                   help="Which QMAP column to plot as 'Q-MAP Product A' "
                        "(default: qmap_postAdj).")
    return p.parse_args()


if __name__ == "__main__":
    _args = parse_args()
    main(locations=_args.locations, qmap_col=_args.qmap_col)
