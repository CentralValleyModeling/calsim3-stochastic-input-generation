"""
Quantile-Mapping Product A Validation -- Mammoth Pool Storage
=============================================================
Train quantile mapping on the first half of the overlap period
(Oct 1921 - Sep 1971) and validate on the second half (Oct 1971 - Sep 2018).

For each (target, predictor) pair in ``reference/qmap_pairs.csv``:

- **Training phase**: Both basis (predictor) and target are read from the
  CalSim3 baseline DSS for 1921-1971.
- **Simulation phase**: The Product A QMAP'd predictor (1972-2018) from
  rim_inflow output is used as the simulation basis and mapped to the
  CalSim3 target domain.

Methodology follows the "Other Terms Reproduction" diagram:
  Basis = CalSim3 Matching Term (1921-1971)  -->  QMAP Product_A of Matching Term (1972-2018)
  Target = CalSim3 Term (1921-1971)          -->  QMAP Product_A CalSim3 Term (1972-2018)

Inputs
------
- CalSim baseline DSS: CalSim3/__calsim_sv_default__.dss
- Product A QMAP'd rim inflows: mod_hydrology/rim_inflow/output/
    _2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv
- Pair definitions: reference/qmap_pairs.csv  (target_part_b, target_part_c,
  predictor_part_b, predictor_part_c, lower_bound, upper_bound)

Outputs
-------
- <generated>/output/_2_qmap/product_a/
    - validation detail CSV per target
    - figures (timeseries+CDF, monthly error, monthly percent error)
- <generated>/output/_product_a_validation/
    - <target>_productA_1972_2018.csv  (Part B, Part C, Year, Month, Value)

Dependencies (must run first)
-----------------------------
- mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
    produces: _riminflow_productA_1972_2018.csv (Product A QMAP'd predictor)

Utilities (repo-level, no setup needed)
----------------------------------------
- utils/paths.py          -- resolves data_dir, BASE, and GENERATED paths
- utils/quantile_mapping.py -- qmap_single(): empirical CDF quantile mapping

Usage
-----
    cd mod_reservoir/storage_curves
    python _2a_qmap_product_a.py

Adding a New Term
-----------------
Edit ``reference/qmap_pairs.csv`` -- one row per term:

    target_part_b, target_part_c      -- DSS B/C parts of the CalSim SV to reproduce
    predictor_part_b, predictor_part_c -- DSS B/C parts of the driving (correlated) term;
                                          must exist in the Product A rim inflow CSV
    lower_bound, upper_bound           -- hard limits applied after mapping; leave blank for none

If the term can physically be negative (e.g. net change-in-storage), set
``ALLOW_NEGATIVE = True`` in the CONFIG section; otherwise the mapper clips
negative outputs to zero.  Note: this flag is global and applies to all pairs
in the CSV -- if mixing negative-allowed and positive-only terms, run them in
separate executions with the flag set appropriately each time.
"""

# %% -- IMPORTS ---------------------------------------------------------------
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import seaborn as sns
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.quantile_mapping import qmap_single

# %% -- PATHS -----------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_reservoir/storage_curves")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

PAIR_CSV = _SCRIPT_DIR / "reference" / "qmap_pairs.csv"
DSS_FILE = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")

# Product A QMAP'd rim inflows from the rim_inflow module
PRODUCT_A_RIM_CSV = (
    _rim_gen / "output" / "_2_qmap_historical_validation"
    / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
)

OUTPUT_DIR = str(_gen / "output" / "_2_qmap" / "product_a")
PLOTS_DIR = os.path.join(OUTPUT_DIR, "_figures")
VALIDATION_DIR = str(_gen / "output" / "_product_a_validation")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PLOTS_DIR, exist_ok=True)
os.makedirs(VALIDATION_DIR, exist_ok=True)

# %% -- CONFIG ----------------------------------------------------------------
TRAIN_START = "1921-10-01"
TRAIN_END = "1971-09-30"
SIM_START = "1971-10-01"
SIM_END = "2018-09-30"
DSS_READ_START = "1915-01-31"
DSS_READ_END = "2018-12-31"
ALLOW_NEGATIVE = False  # Set True for terms where negative values are physically valid

MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# Plot styling (consistent with _3_productA_postproc.py)
sns.set_theme(
    style="whitegrid",
    context="paper",
    font_scale=1.0,
    rc={
        "figure.dpi": 200,
        "savefig.dpi": 300,
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Calibri", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.titleweight": "semibold",
        "axes.labelsize": 8,
        "axes.labelweight": "medium",
        "axes.edgecolor": "0.25",
        "axes.linewidth": 0.6,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "grid.linewidth": 0.35,
        "grid.alpha": 0.40,
        "lines.linewidth": 0.9,
        "legend.fontsize": 7,
        "legend.title_fontsize": 8,
        "legend.framealpha": 0.90,
        "legend.edgecolor": "0.55",
        "figure.titlesize": 8,
        "figure.titleweight": "bold",
        "mathtext.default": "regular",
    },
)
_cb = list(sns.color_palette("colorblind"))
_cb[1] = (0.918, 0.341, 0.220)   # Vermillion+1 ~#EB5738
_PALETTE = _cb

# Box plot palette 
_BLUE        = "#003D6B"
_LIGHT_BLUE  = "#B0C4DE"
_MEDIAN_RED  = "#8B0000"
_GRAY        = "#5A5A5A"

# %% -- HELPERS ---------------------------------------------------------------


def ser_to_df(s: pd.Series) -> pd.DataFrame:
    """Convert a monthly Series with month-end index to (year, month, value)."""
    return pd.DataFrame({
        "year": s.index.year.astype(int),
        "month": s.index.month.astype(int),
        "value": s.values.astype(float),
    })


def nse(sim, obs):
    sim = np.asarray(sim, dtype=float)
    obs = np.asarray(obs, dtype=float)
    m = np.isfinite(sim) & np.isfinite(obs)
    if m.sum() < 2:
        return np.nan
    sim, obs = sim[m], obs[m]
    den = np.sum((obs - np.mean(obs)) ** 2)
    if den == 0:
        return np.nan
    return 1 - np.sum((obs - sim) ** 2) / den


def pearson_r(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2:
        return np.nan
    a, b = a[m], b[m]
    if np.nanstd(a) == 0 or np.nanstd(b) == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def read_calsim_monthly(dssfile: str, part_b: str, part_c: str) -> pd.Series:
    """Read a single CalSim monthly time series from DSS by B-part and C-part."""
    full_idx = pd.date_range(DSS_READ_START, DSS_READ_END, freq="ME")
    master = pd.Series(index=full_idx, dtype=float)

    b_upper = part_b.upper().replace(" ", "_")
    c_upper = part_c.upper().replace(" ", "_")

    with HecDss.Open(dssfile, version=6, catalog_flag=True) as dss:
        paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        matched = []
        for p in paths:
            parts = p.strip("/").split("/")
            if len(parts) != 6:
                continue
            if parts[1].strip().upper() == b_upper and parts[2].strip().upper() == c_upper:
                matched.append(p)

        for p in sorted(matched, key=lambda x: (x.strip("/").split("/")[3], x)):
            ts = dss.read_ts(p, trim_missing=True)
            vals = np.asarray(ts.values, dtype=float)
            vals = np.where(vals <= -900, np.nan, vals)
            idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
            master.update(pd.Series(vals, index=idx))

    return master


def load_product_a_rim_series(csv_path: Path, part_b: str, part_c: str) -> pd.Series:
    """Load a specific Part B + Part C series from the Product A rim inflow CSV."""
    df = pd.read_csv(csv_path)
    mask_b = df["Part B"].str.upper().str.strip() == part_b.upper().strip()
    mask_c = df["Part C"].str.upper().str.strip() == part_c.upper().strip()
    sub = df.loc[mask_b & mask_c].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    dates = pd.to_datetime(
        sub["Year"].astype(str) + "-" + sub["Month"].astype(str) + "-01"
    )
    dates = dates + pd.offsets.MonthEnd(0)
    return pd.Series(sub["Value"].values.astype(float), index=dates).sort_index()


# %% -- READ PAIR DEFINITIONS ------------------------------------------------
df_pairs = pd.read_csv(PAIR_CSV, skipinitialspace=True)
for col in df_pairs.columns:
    df_pairs[col] = df_pairs[col].apply(
        lambda x: str(x).strip() if pd.notna(x) else x
    )
df_pairs["lower_bound"] = pd.to_numeric(df_pairs.get("lower_bound"), errors="coerce")
df_pairs["upper_bound"] = pd.to_numeric(df_pairs.get("upper_bound"), errors="coerce")

print(f"Loaded {len(df_pairs)} pair(s) from {PAIR_CSV.name}")

# %% -- MAIN LOOP ------------------------------------------------------------
for _, row in df_pairs.iterrows():
    target_b = row["target_part_b"]
    target_c = row["target_part_c"]
    pred_b = row["predictor_part_b"]
    pred_c = row["predictor_part_c"]
    lb = row.get("lower_bound", np.nan)
    ub = row.get("upper_bound", np.nan)

    print(f"\n{'='*60}")
    print(f"Target: {target_b} / {target_c}")
    print(f"Predictor: {pred_b} / {pred_c}")
    print(f"Bounds: [{lb}, {ub}]")

    # 1) Read CalSim DSS for both predictor and target (full historical range)
    predictor_full = read_calsim_monthly(DSS_FILE, pred_b, pred_c)
    target_full = read_calsim_monthly(DSS_FILE, target_b, target_c)

    if predictor_full.dropna().empty:
        print(f"  WARNING: No DSS data for predictor {pred_b}/{pred_c}, skipping.")
        continue
    if target_full.dropna().empty:
        print(f"  WARNING: No DSS data for target {target_b}/{target_c}, skipping.")
        continue

    # 2) Slice training period
    pred_train = predictor_full.loc[TRAIN_START:TRAIN_END].dropna()
    tgt_train = target_full.loc[TRAIN_START:TRAIN_END].dropna()

    # Align training to common dates
    common_train = pred_train.index.intersection(tgt_train.index)
    if common_train.empty:
        print(f"  WARNING: Predictor ({pred_b}) and target ({target_b}) have no common months in training period ({TRAIN_START} to {TRAIN_END}), skipping.")
        continue
    pred_train = pred_train.loc[common_train]
    tgt_train = tgt_train.loc[common_train]

    print(f"  Training: {len(pred_train)} months "
          f"({common_train.min().date()} to {common_train.max().date()})")

    # 3) Load Product A QMAP'd predictor for simulation period
    pred_sim = load_product_a_rim_series(PRODUCT_A_RIM_CSV, pred_b, pred_c)
    pred_sim = pred_sim.loc[SIM_START:SIM_END].dropna()

    if pred_sim.empty:
        print(f"  WARNING: No Product A data for predictor {pred_b}/{pred_c}, skipping.")
        continue

    # Also load CalSim target for the simulation period (for validation)
    tgt_actual = target_full.loc[SIM_START:SIM_END].dropna()
    common_sim = pred_sim.index.intersection(tgt_actual.index)
    if common_sim.empty:
        print(f"  WARNING: Product A predictor ({pred_b}) and CalSim target ({target_b}) have no common months in simulation period ({SIM_START} to {SIM_END}), skipping.")
        continue
    pred_sim = pred_sim.loc[common_sim]
    tgt_actual = tgt_actual.loc[common_sim]

    print(f"  Simulation: {len(pred_sim)} months "
          f"({common_sim.min().date()} to {common_sim.max().date()})")

    # 4) Quantile map
    qmap_result = qmap_single(
        ser_to_df(pred_sim),
        ser_to_df(pred_train),
        ser_to_df(tgt_train),
        allow_negative=ALLOW_NEGATIVE,
    )
    qmap_vals = qmap_result["quantile_mapped_value"].values.astype(float)

    # 5) Clamp to bounds
    if np.isfinite(lb):
        qmap_vals = np.maximum(qmap_vals, lb)
    if np.isfinite(ub):
        qmap_vals = np.minimum(qmap_vals, ub)

    # 6) Compute skill metrics
    actual_vals = tgt_actual.values.astype(float)
    r = pearson_r(qmap_vals, actual_vals)
    r2 = r ** 2 if np.isfinite(r) else np.nan
    nse_val = nse(qmap_vals, actual_vals)
    obs_sum = np.nansum(actual_vals)
    pbias = (np.nansum(qmap_vals - actual_vals) / obs_sum * 100) if obs_sum != 0 else np.nan

    print(f"  R2 = {r2:.3f}, NSE = {nse_val:.3f}, PBIAS = {pbias:.1f}%")

    # 7) Build detail dataframe
    detail = pd.DataFrame({
        "target": target_b,
        "predictor": pred_b,
        "Year": common_sim.year.astype(int),
        "Month": common_sim.month.astype(int),
        "predictor_sim": pred_sim.values,
        "actual": actual_vals,
        "qmap": qmap_vals,
    })
    detail["error"] = detail["qmap"] - detail["actual"]
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = (detail["qmap"] - detail["actual"]) / detail["actual"] * 100
    pct[~np.isfinite(pct)] = np.nan
    detail["error_pct"] = pct

    # 8) Write detail CSV
    detail.to_csv(
        os.path.join(OUTPUT_DIR, f"{target_b}_qmap_validation.csv"),
        index=False,
    )

    # 9) Write Product A validation CSV (CalSim format)
    val_df = pd.DataFrame({
        "Part B": target_b,
        "Part C": target_c,
        "Year": common_sim.year.astype(int),
        "Month": common_sim.month.astype(int),
        "Value": qmap_vals,
    })
    val_csv = os.path.join(
        VALIDATION_DIR, f"{target_b}_productA_1972_2018.csv"
    )
    val_df.to_csv(val_csv, index=False)
    print(f"  Wrote: {val_csv}")

    # 10) Plot: time series + non-exceedance CDF (two-panel)
    _r2_str = f"{r2:.2f}" if np.isfinite(r2) else "N/A"
    _nse_str = f"{nse_val:.2f}" if np.isfinite(nse_val) else "N/A"
    _pbias_str = f"{pbias:.1f}%" if np.isfinite(pbias) else "N/A"
    _metric_lbl = (f"Product A:  R\u00b2={_r2_str}   "
                   f"NSE={_nse_str}   PBIAS={_pbias_str}")

    _clr_hist = _PALETTE[0]
    _clr_prod = _PALETTE[1]

    fig, (ax_ts, ax_cdf) = plt.subplots(
        nrows=1, ncols=2, figsize=(6.5, 3.25),
        gridspec_kw={"width_ratios": [1.6, 1]},
    )

    # -- Left: Monthly time series --
    ax_ts.plot(common_sim, actual_vals, color=_clr_hist, linewidth=0.8,
               label="Historical", alpha=0.85)
    ax_ts.plot(common_sim, qmap_vals, color=_clr_prod, linewidth=0.9,
               label="Product A", alpha=0.85)
    ax_ts.set_title("Monthly Time Series")
    ax_ts.set_xlabel("Date")
    ax_ts.set_ylabel("TAF")
    ax_ts.xaxis.set_major_locator(mdates.YearLocator(10))
    ax_ts.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate(rotation=35, ha="right")

    # Metrics annotation
    ax_ts.text(
        0.02, 0.97, _metric_lbl,
        transform=ax_ts.transAxes,
        va="top", ha="left", fontsize=7,
        fontfamily="sans-serif",
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="white", edgecolor="0.7",
            alpha=0.88,
        ),
    )

    # -- Right: Non-exceedance CDF --
    for vals_arr, color, lbl in [
        (actual_vals, _clr_hist, "Historical"),
        (qmap_vals, _clr_prod, "Product A"),
    ]:
        arr = np.sort(np.asarray(vals_arr, dtype=float))
        cdf = np.arange(1, len(arr) + 1) / len(arr) * 100
        ax_cdf.plot(cdf, arr, color=color, linewidth=0.9, alpha=0.9,
                    label=lbl)
    ax_cdf.set_title("Non-Exceedance CDF")
    ax_cdf.set_xlabel("Non-Exceedance Probability (%)")
    ax_cdf.set_ylabel("")
    ax_cdf.set_xlim(0, 100)

    # -- Suptitle & layout --
    fig.suptitle(f"{target_b} (TAF)", y=1.02)
    fig.tight_layout()

    # Shared figure legend — top left
    handles, labels = ax_ts.get_legend_handles_labels()
    fig.legend(
        handles, labels,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
        ncol=2,
        fontsize=7,
        frameon=False,
        handlelength=2.0,
        handletextpad=0.6,
        borderpad=0.7,
    )

    fig.savefig(os.path.join(PLOTS_DIR, f"{target_b}_timeseries.png"),
                dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # 11) Plot: monthly box plot of errors
    months_list = list(range(10, 13)) + list(range(1, 10))
    box_data = [
        detail.loc[detail["Month"] == m, "error"].dropna().values
        for m in months_list
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    positions = list(range(1, len(months_list) + 1))
    ax.boxplot(
        box_data, positions=positions, widths=0.5,
        showfliers=False, patch_artist=True, showmeans=True,
        boxprops=dict(facecolor=_LIGHT_BLUE, edgecolor=_BLUE, linewidth=1.0),
        medianprops=dict(color=_MEDIAN_RED, linewidth=1.8),
        meanprops=dict(marker="D", markerfacecolor=_BLUE,
                       markeredgecolor=_BLUE, markersize=5),
        whiskerprops=dict(color=_BLUE, linewidth=1.0),
        capprops=dict(color=_BLUE, linewidth=1.0),
    )
    ax.axhline(0, color=_GRAY, linestyle="--", linewidth=1.4)
    ax.set_xticks(positions)
    ax.set_xticklabels([MONTH_LABELS[m - 1] for m in months_list],
                       fontsize=11, fontweight="medium")
    ax.set_xlabel("Month", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel("Error (TAF)", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title(f"{target_b}: Monthly Error", fontsize=14, fontweight="bold", pad=12)
    ax.tick_params(axis="both", labelsize=11)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5, color="#CCCCCC")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, f"{target_b}_monthly_error.png"),
                dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # 12) Plot: monthly box plot of percent errors
    box_data_pct = [
        detail.loc[detail["Month"] == m, "error_pct"].dropna().values
        for m in months_list
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.boxplot(
        box_data_pct, positions=positions, widths=0.5,
        showfliers=False, patch_artist=True, showmeans=True,
        boxprops=dict(facecolor=_LIGHT_BLUE, edgecolor=_BLUE, linewidth=1.0),
        medianprops=dict(color=_MEDIAN_RED, linewidth=1.8),
        meanprops=dict(marker="D", markerfacecolor=_BLUE,
                       markeredgecolor=_BLUE, markersize=5),
        whiskerprops=dict(color=_BLUE, linewidth=1.0),
        capprops=dict(color=_BLUE, linewidth=1.0),
    )
    ax.axhline(0, color=_GRAY, linestyle="--", linewidth=1.4)
    ax.set_xticks(positions)
    ax.set_xticklabels([MONTH_LABELS[m - 1] for m in months_list],
                       fontsize=11, fontweight="medium")
    ax.set_xlabel("Month", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_ylabel("Percent Error (%)", fontsize=12, fontweight="bold", labelpad=8)
    ax.set_title(f"{target_b}: Monthly Percent Error",
                 fontsize=14, fontweight="bold", pad=12)
    ax.tick_params(axis="both", labelsize=11)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5, color="#CCCCCC")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(PLOTS_DIR, f"{target_b}_monthly_pct_error.png"),
                dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

# %% -- SUMMARY ---------------------------------------------------------------
print("\nDone.")
