"""
_5_dnp_evaporation.py
======================
Hypsographic curve calibration and evaporation generation for Don Pedro Reservoir.

Two run modes
-------------
  calibrate  Reverse-engineer the storage-area polynomial from historical
             CalSim data (S_PEDRO_SV, ER_PEDRO_SV, E_PEDRO_SV). Writes
             polynomial coefficients + diagnostics.

  A          Generate Product A E_PEDRO_SV using the calibrated polynomial,
             synthetic storage from reference/, and ER from
             mod_reservoir/evaporation output.

  B          Same as A but for Product B.

  both       Run both A and B (calibrate must have been run first).

Reference inputs (./reference/)
--------------------------------
  s_pedro_sv_historical.csv
  er_pedro_sv_historical.csv
  e_pedro_sv_historical.csv
  s_pedro_sv_product_a.csv
  s_pedro_sv_product_b.csv   (when available)

External inputs
---------------
  mod_reservoir/evaporation output:
    _2_run_reservoir_evap/Product_{A|B}/individual_reservoirs/
      San_Joaquin_Valley/PEDRO.csv

Outputs  (data/GENERATED/mod_other/upper_watershed/output/)
-------------------------------------------------------------------------------
  _5_dnp_evaporation/calibrate/
    hypsographic_polynomial_coeffs.csv
    surface_area_historical.csv
    hypsographic_curve.csv
    hypsographic_curve.png
    time_series_storage_area.png
  _5_dnp_evaporation/Product_A/
    product_a_evaporation_timeseries.png
    product_a_monthly_pattern.png
  _5_dnp_evaporation/Product_B/
    ...
  _product_a_validation/
    _e_pedro_sv_evaporation_productA_<start>_<end>.csv
  _product_b_final/
    _e_pedro_sv_evaporation_productB_<start>_<end>.csv

Usage
-----
  python _5_dnp_evaporation.py --run calibrate
  python _5_dnp_evaporation.py --run A
  python _5_dnp_evaporation.py --run B
  python _5_dnp_evaporation.py --run both
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

# ── Repo path setup ───────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_SCRIPT_DIR = Path(__file__).resolve().parent
_GEN_DIR    = get_module_generated_dir("mod_other/upper_watershed")
_EVAP_GEN   = get_module_generated_dir("mod_reservoir/evaporation")

# ── Reference (static) inputs ─────────────────────────────────────────────────
REF_DIR = _SCRIPT_DIR / "reference"

# ── Generated output directories ─────────────────────────────────────────────
OUTPUT_ROOT   = _GEN_DIR / "output" / "_5_dnp_evaporation"
CALIBRATE_DIR = OUTPUT_ROOT / "calibrate"
OUTPUT_A_DIR  = OUTPUT_ROOT / "Product_A"
OUTPUT_B_DIR  = OUTPUT_ROOT / "Product_B"
CSV_A_DIR     = _GEN_DIR / "output" / "_product_a_validation"
CSV_B_DIR     = _GEN_DIR / "output" / "_product_b_final"

# ── External input: reservoir evaporation rates ───────────────────────────────
_EVAP_OUTROOT = _EVAP_GEN / "output" / "_2_run_reservoir_evap"

# ── Unit constants ────────────────────────────────────────────────────────────
FT2_PER_ACRE = 43_560
IN_TO_FT     = 1 / 12


# ═══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_polynomial(coeffs_path: Path) -> np.poly1d:
    """Load degree-2 polynomial from CSV produced by run_calibrate()."""
    return np.poly1d(pd.read_csv(coeffs_path)["value"].values)


def _pedro_evap_rate_path(product: str) -> Path:
    return (
        _EVAP_OUTROOT / f"Product_{product}"
        / "individual_reservoirs" / "San_Joaquin_Valley" / "PEDRO.csv"
    )


def _compute_surface_area(e_cfs: np.ndarray, er_in: np.ndarray,
                           days: np.ndarray) -> np.ndarray:
    """Back-calculate surface area (acres) from total evaporation and ER.

    A = [E (cfs) × seconds_in_month] / [ER (ft) × ft²_per_acre]
    """
    seconds = days * 86_400
    return np.where(
        er_in > 0,
        (e_cfs * seconds) / (er_in * IN_TO_FT * FT2_PER_ACRE),
        np.nan,
    )


def _calc_evap_cfs(storage_taf: np.ndarray, er_in: np.ndarray,
                   days: np.ndarray, poly_func: np.poly1d) -> np.ndarray:
    """Calculate evaporation (CFS) from storage, ER, and hypsographic curve."""
    area_acres = poly_func(storage_taf)
    volume_ft3 = er_in * IN_TO_FT * area_acres * FT2_PER_ACRE
    return volume_ft3 / (days * 86_400)


# ═══════════════════════════════════════════════════════════════════════════════
# Mode 1 – calibrate
# ═══════════════════════════════════════════════════════════════════════════════

def run_calibrate() -> None:
    """Reverse-engineer hypsographic curve from historical CalSim data."""
    print("\n" + "=" * 72)
    print("CALIBRATE: Reverse-Engineer Don Pedro Hypsographic Curve")
    print("=" * 72)

    CALIBRATE_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load historical data ─────────────────────────────────────────────────
    print("Loading historical data from reference/...")
    storage    = pd.read_csv(REF_DIR / "s_pedro_sv_historical.csv")
    evap_rate  = pd.read_csv(REF_DIR / "er_pedro_sv_historical.csv")
    evap_total = pd.read_csv(REF_DIR / "e_pedro_sv_historical.csv")

    for df in (storage, evap_rate, evap_total):
        df["date"] = pd.to_datetime(df["Date"])
    storage    = storage.rename(columns={"value": "storage_taf"})
    evap_rate  = evap_rate.rename(columns={"value": "er_inches"})
    evap_total = evap_total.rename(columns={"value": "e_cfs"})

    df = (storage[["date", "storage_taf"]]
          .merge(evap_rate[["date", "er_inches"]], on="date", how="inner")
          .merge(evap_total[["date", "e_cfs"]], on="date", how="inner"))
    print(f"  {len(df)} months, {df['date'].min().date()} – {df['date'].max().date()}")

    # ── Calculate surface area ───────────────────────────────────────────────
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["days"]  = df["date"].dt.days_in_month

    df["surface_area_acres"] = _compute_surface_area(
        df["e_cfs"].values, df["er_inches"].values, df["days"].values
    )
    na_count = df["surface_area_acres"].isna().sum()
    if na_count:
        print(f"  Interpolating {na_count} months with ER=0...")
        df["surface_area_acres"] = df["surface_area_acres"].interpolate(method="linear")

    print(f"  Surface area: {df['surface_area_acres'].min():.1f}–"
          f"{df['surface_area_acres'].max():.1f} acres "
          f"(mean {df['surface_area_acres'].mean():.1f})")

    # ── Fit degree-2 polynomial ──────────────────────────────────────────────
    hypso       = df[["storage_taf", "surface_area_acres"]].sort_values("storage_taf")
    poly_coeffs = np.polyfit(hypso["storage_taf"], hypso["surface_area_acres"], deg=2)
    poly_func   = np.poly1d(poly_coeffs)
    r2 = pearsonr(hypso["surface_area_acres"], poly_func(hypso["storage_taf"]))[0] ** 2
    print(f"\n  A = {poly_coeffs[0]:.6e}·S² + {poly_coeffs[1]:.6e}·S "
          f"+ {poly_coeffs[2]:.6e}   (R²={r2:.4f})")

    # ── Write outputs ────────────────────────────────────────────────────────
    df[["date", "year", "month", "storage_taf", "er_inches",
        "e_cfs", "surface_area_acres"]].to_csv(
        CALIBRATE_DIR / "surface_area_historical.csv", index=False)

    pd.DataFrame({
        "coefficient": ["a2", "a1", "a0"],
        "value":       poly_coeffs,
        "description": ["S² coefficient", "S¹ coefficient", "constant"],
    }).to_csv(CALIBRATE_DIR / "hypsographic_polynomial_coeffs.csv", index=False)

    bins   = np.arange(hypso["storage_taf"].min(), hypso["storage_taf"].max() + 50, 50)
    hypso  = hypso.copy()
    hypso["storage_bin"] = pd.cut(hypso["storage_taf"], bins=bins, labels=bins[:-1])
    binned = (hypso.groupby("storage_bin", observed=True)
              .agg(storage_taf=("storage_taf", "mean"),
                   surface_area_acres=("surface_area_acres", "mean"))
              .reset_index(drop=True))
    binned["surface_area_poly"] = poly_func(binned["storage_taf"])
    binned.to_csv(CALIBRATE_DIR / "hypsographic_curve.csv", index=False)

    print(f"\n  Outputs written to: {CALIBRATE_DIR}")

    # ── Plots ────────────────────────────────────────────────────────────────
    s_smooth = np.linspace(hypso["storage_taf"].min(), hypso["storage_taf"].max(), 200)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    ax1.scatter(hypso["storage_taf"], hypso["surface_area_acres"],
                alpha=0.3, s=10, label="Observed")
    ax1.plot(s_smooth, poly_func(s_smooth), "r-", lw=2, label="Polynomial (deg=2)")
    ax1.set_xlabel("Storage (TAF)"); ax1.set_ylabel("Surface Area (acres)")
    ax1.set_title(f"Hypsographic Curve (R²={r2:.4f})")
    ax1.legend(); ax1.grid(alpha=0.3)
    ax2.plot(binned["storage_taf"], binned["surface_area_acres"],
             "o-", lw=2, label="Binned Observed")
    ax2.plot(binned["storage_taf"], binned["surface_area_poly"],
             "s-", lw=2, color="red", label="Polynomial")
    ax2.set_xlabel("Storage (TAF)"); ax2.set_ylabel("Surface Area (acres)")
    ax2.set_title("Binned vs Polynomial")
    ax2.legend(); ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(CALIBRATE_DIR / "hypsographic_curve.png", dpi=150, bbox_inches="tight")
    plt.close()

    df_ts = df.set_index("date")
    fig2, (ax3, ax4) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    ax3.plot(df_ts.index, df_ts["storage_taf"], lw=1)
    ax3.set_ylabel("Storage (TAF)"); ax3.set_title("Don Pedro: Historical Storage")
    ax3.grid(alpha=0.3)
    ax4.plot(df_ts.index, df_ts["surface_area_acres"], lw=1, color="green")
    ax4.set_ylabel("Surface Area (acres)")
    ax4.set_title("Don Pedro: Calculated Surface Area")
    ax4.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(CALIBRATE_DIR / "time_series_storage_area.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("  Plots saved.")


# ═══════════════════════════════════════════════════════════════════════════════
# Modes 2 & 3 – generate Product A / B
# ═══════════════════════════════════════════════════════════════════════════════

def _load_storage_ref(product: str) -> pd.DataFrame:
    path = REF_DIR / f"s_pedro_sv_product_{product.lower()}.csv"
    if not path.exists():
        raise FileNotFoundError(f"Storage file not found: {path}")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["Date"])
    df = df.rename(columns={"value": "storage_taf"})
    print(f"  Storage (Product {product}): {len(df)} months, "
          f"{df['date'].min().date()} – {df['date'].max().date()}")
    return df


def _load_er(product: str) -> pd.DataFrame:
    path = _pedro_evap_rate_path(product)
    if not path.exists():
        raise FileNotFoundError(f"Evaporation rate file not found:\n  {path}")
    er = pd.read_csv(path, index_col=0, parse_dates=True).reset_index()
    er.columns = ["date", "er_inches"]
    print(f"  ER (Product {product}): {len(er)} months, "
          f"{er['date'].min().date()} – {er['date'].max().date()}")
    return er


def run_generate(product: str) -> None:
    """Generate E_PEDRO_SV for Product A or B."""
    print("\n" + "=" * 72)
    print(f"GENERATE: Don Pedro Evaporation – Product {product}")
    print("=" * 72)

    out_dir = OUTPUT_A_DIR if product == "A" else OUTPUT_B_DIR
    csv_dir = CSV_A_DIR if product == "A" else CSV_B_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    # ── Load polynomial from calibrate output ────────────────────────────────
    coeffs_path = CALIBRATE_DIR / "hypsographic_polynomial_coeffs.csv"
    if not coeffs_path.exists():
        raise FileNotFoundError(
            f"Polynomial coefficients not found – run `--run calibrate` first.\n  {coeffs_path}"
        )
    poly_func = load_polynomial(coeffs_path)
    c = pd.read_csv(coeffs_path)["value"].values
    print(f"  Polynomial: A = {c[0]:.6e}·S² + {c[1]:.6e}·S + {c[2]:.6e}")

    # ── Load inputs ──────────────────────────────────────────────────────────
    storage = _load_storage_ref(product)
    er_data = _load_er(product)

    # ── Calculate E_PEDRO_SV ─────────────────────────────────────────────────
    storage["surface_area_acres"] = poly_func(storage["storage_taf"])
    storage = storage.merge(er_data[["date", "er_inches"]], on="date", how="left")

    missing_er = storage["er_inches"].isna().sum()
    if missing_er:
        print(f"  WARNING: {missing_er} months missing ER – will output NaN")
    else:
        print(f"  ER matched for all {len(storage)} months")

    storage["days"]  = storage["date"].dt.days_in_month
    storage["e_cfs"] = _calc_evap_cfs(
        storage["storage_taf"].values,
        storage["er_inches"].values,
        storage["days"].values,
        poly_func,
    )
    valid = storage["e_cfs"].dropna()
    print(f"  E_PEDRO_SV: {valid.min():.2f}–{valid.max():.2f} CFS  (mean {valid.mean():.2f})")

    # ── Write CalSim SV CSV ──────────────────────────────────────────────────
    def _wy(d: pd.Timestamp) -> int:
        return d.year + 1 if d.month >= 10 else d.year

    valid_rows  = storage[storage["e_cfs"].notna()]
    start_wy    = _wy(valid_rows["date"].min())
    end_wy      = _wy(valid_rows["date"].max())
    out_csv     = csv_dir / f"_e_pedro_sv_evaporation_product{product}_{start_wy}_{end_wy}.csv"
    pd.DataFrame({
        "Part B":  "E_PEDRO_SV",
        "Part C":  "EVAPORATION",
        "Year":    storage["date"].dt.year,
        "Month":   storage["date"].dt.month,
        "Value":   storage["e_cfs"],
    }).to_csv(out_csv, index=False)
    print(f"  Wrote: {out_csv.name}")

    # ── Plots ────────────────────────────────────────────────────────────────
    e_hist = s_hist = None
    if product == "A":
        if (REF_DIR / "s_pedro_sv_historical.csv").exists():
            s_hist = pd.read_csv(REF_DIR / "s_pedro_sv_historical.csv")
            s_hist["date"] = pd.to_datetime(s_hist["Date"])
            s_hist = s_hist.rename(columns={"value": "storage_taf"})
        if (REF_DIR / "e_pedro_sv_historical.csv").exists():
            e_hist = pd.read_csv(REF_DIR / "e_pedro_sv_historical.csv")
            e_hist["date"] = pd.to_datetime(e_hist["Date"])
            e_hist = e_hist.rename(columns={"value": "e_cfs"})

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    if s_hist is not None:
        ax1.plot(s_hist["date"], s_hist["storage_taf"], lw=1,
                 color="blue", alpha=0.7, label="Historical")
    ax1.plot(storage["date"], storage["storage_taf"], lw=1,
             color="green", label=f"Product {product}")
    ax1.set_ylabel("Storage (TAF)")
    ax1.set_title(f"Don Pedro: Product {product} Storage")
    ax1.legend(); ax1.grid(alpha=0.3)

    if e_hist is not None:
        ax2.plot(e_hist["date"], e_hist["e_cfs"], lw=1,
                 color="blue", alpha=0.7, label="Historical")
    ax2.plot(storage["date"], storage["e_cfs"], lw=1,
             color="green", label=f"Product {product}")
    ax2.set_ylabel("Evaporation (CFS)")
    ax2.set_title(f"Don Pedro: Product {product} Evaporation")
    ax2.legend(); ax2.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"product_{product.lower()}_evaporation_timeseries.png",
                dpi=150, bbox_inches="tight")
    plt.close()

    storage["month_num"] = storage["date"].dt.month
    e_monthly = storage.groupby("month_num")["e_cfs"].mean().reset_index()
    fig2, ax3 = plt.subplots(figsize=(10, 6))
    if e_hist is not None:
        e_hist["month_num"] = e_hist["date"].dt.month
        eh_m = e_hist.groupby("month_num")["e_cfs"].mean().reset_index()
        ax3.plot(eh_m["month_num"], eh_m["e_cfs"], "o-", lw=2,
                 color="blue", alpha=0.7, label="Historical")
    ax3.plot(e_monthly["month_num"], e_monthly["e_cfs"], "s-", lw=2,
             color="green", label=f"Product {product}")
    ax3.set_xticks(range(1, 13))
    ax3.set_xticklabels(list("JFMAMJJASOND"))
    ax3.set_xlabel("Month"); ax3.set_ylabel("Average Evaporation (CFS)")
    ax3.set_title(f"Don Pedro: Product {product} Monthly Average Evaporation")
    ax3.legend(); ax3.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / f"product_{product.lower()}_monthly_pattern.png",
                dpi=150, bbox_inches="tight")
    plt.close()

    # Comparison statistics (Product A only)
    if product == "A" and e_hist is not None:
        comp = (storage[["date", "e_cfs"]]
                .merge(e_hist[["date", "e_cfs"]], on="date",
                       how="inner", suffixes=("_gen", "_hist"))
                .dropna())
        if len(comp):
            diff = comp["e_cfs_gen"] - comp["e_cfs_hist"]
            corr = pearsonr(comp["e_cfs_gen"], comp["e_cfs_hist"])[0]
            print(f"\n  Comparison vs historical ({len(comp)} months):")
            print(f"    Correlation : {corr:.4f}")
            print(f"    Mean diff   : {diff.mean():.2f} CFS")
            print(f"    RMSE        : {np.sqrt((diff**2).mean()):.2f} CFS")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Don Pedro evaporation: calibrate hypsographic curve and/or generate E_PEDRO_SV."
    )
    parser.add_argument(
        "--run",
        choices=["calibrate", "A", "B", "both"],
        required=True,
        help=(
            "calibrate – derive hypsographic polynomial from historical data; "
            "A – generate Product A; "
            "B – generate Product B; "
            "both – generate both A and B (requires calibrate to have been run first)"
        ),
    )
    args = parser.parse_args()

    if args.run == "calibrate":
        run_calibrate()
    elif args.run == "A":
        run_generate("A")
    elif args.run == "B":
        run_generate("B")
    elif args.run == "both":
        run_generate("A")
        run_generate("B")

    print("\n" + "=" * 72)
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()
