"""
_2_pge_wy_allocation.py
========================
Reconstructs PGE_WY_ALLOCATION_SV using threshold logic on annual unimpaired
Folsom flow, replicating the Excel spreadsheet methodology.

Methodology (from PGE_WY_ALLOCATION_SV-Reconstruction.xlsx):
  1. Sum monthly unimpaired Folsom inflow by water year (Oct-Sep).
  2. Apply threshold table to annual sum => discrete allocation ratio.
  3. Spread ratio to months: the allocation determined for a given water year
     applies from May of that CY through April of the next CY.

Thresholds (annual unimpaired Folsom flow, TAF):
  <= 488.24  -> 0.4
  <= 800.72  -> 0.6
  <= 957.08  -> 0.8
  <= 1146.02 -> 0.9
  >  1146.02 -> 1.0

Products:
  - Product A (historical-length, WY 1972-2018): Uses FOLSM_INFLOW from the
    Product A QMap validation output (calsim_qmap_validation_TS.csv).
  - Product B (1000-yr stochastic, 10 chunks): Uses synthetic FOLSM_INFLOW
    from _10_RimInflow QMap output with the same thresholds applied directly.

Input files (in ./input/):
  - PGE_WY_ALLOCATION_config.json            : Thresholds & configuration

External dependencies:
  - _10_RimInflow/output/_2_qmap_historical_validation/Product_A/
       calsim_qmap_validation_TS.csv  (Product A FOLSM_INFLOW)
  - _10_RimInflow/output/_3_qmap_product_b/
       FOLSM_INFLOW_8RI_FOL_I_qmo_n01.csv ... n10.csv  (Product B inflows)

Output:
  - output/_2_pge_wy_allocation/Product_A/
       _pge_wy_allocation_productA_1972_2018.csv
  - output/_2_pge_wy_allocation/Product_B/
       _pge_wy_allocation_productB_n01.csv  ...  _pge_wy_allocation_productB_n10.csv
"""

from __future__ import annotations

import sys
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
RUN_DIR = Path(__file__).resolve().parent

# Target product: "A", "B", or "BOTH"
TARGET_PRODUCT = "BOTH"

# CalSim study period for Product A (water years)
PRODUCT_A_START_WY = 1972
PRODUCT_A_END_WY = 2018

# Product B: number of chunks
PRODUCT_B_NCHUNKS = 10

# Input paths (relative to this script)
INPUT_DIR = RUN_DIR / "input"
CONFIG_JSON = INPUT_DIR / "PGE_WY_ALLOCATION_config.json"

# RimInflow directories
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
RIM_INFLOW_PRODUCT_A_CSV = (
    _rim_gen / "_2_qmap_historical_validation" / "Product_A" / "calsim_qmap_validation_TS.csv"
)
RIM_INFLOW_PRODUCT_B_DIR = _rim_gen / "_3_qmap_product_b"

# Output directories
_GEN_DIR = get_module_generated_dir("mod_other/upper_watershed")
OUTPUT_ROOT = _GEN_DIR / "output" / "_4_pge_wy_allocation"
OUTPUT_A_DIR = OUTPUT_ROOT / "Product_A"
OUTPUT_B_DIR = OUTPUT_ROOT / "Product_B"


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────
def load_config(config_path: Path) -> dict:
    """Load thresholds and regression parameters from JSON config."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_water_year(year: int, month: int) -> int:
    """Return the water year for a given calendar year/month.
    WY runs Oct (month 10) through Sep (month 9).
    """
    return year + 1 if month >= 10 else year


def apply_thresholds(annual_flow: float, thresholds: list[dict], default: float) -> float:
    """Apply threshold logic to annual flow.

    Parameters
    ----------
    annual_flow : float
        Annual unimpaired Folsom flow (TAF).
    thresholds : list of dict
        Each dict has 'annual_flow_taf_le' and 'ratio'.
        Must be sorted ascending by threshold.
    default : float
        Ratio to return if flow exceeds all thresholds.

    Returns
    -------
    float
        Allocation ratio.
    """
    for t in thresholds:
        if annual_flow <= t["annual_flow_taf_le"]:
            return t["ratio"]
    return default


def annual_flow_to_wy_ratio(
    df_monthly: pd.DataFrame,
    flow_col: str,
    thresholds: list[dict],
    default_ratio: float,
) -> pd.DataFrame:
    """Compute WY annual sums and apply thresholds.

    Parameters
    ----------
    df_monthly : DataFrame
        Must have columns: Year, Month, and `flow_col`.
    flow_col : str
        Column name with monthly flow values (TAF).
    thresholds : list of dict
        Threshold config (ascending).
    default_ratio : float
        Default ratio if flow exceeds all thresholds.

    Returns
    -------
    DataFrame
        Columns: WY, Annual_Flow_TAF, Ratio.
    """
    df = df_monthly.copy()
    df["WY"] = df.apply(lambda r: compute_water_year(int(r["Year"]), int(r["Month"])), axis=1)
    annual = df.groupby("WY")[flow_col].sum().reset_index()
    annual.columns = ["WY", "Annual_Flow_TAF"]
    annual["Ratio"] = annual["Annual_Flow_TAF"].apply(
        lambda x: apply_thresholds(x, thresholds, default_ratio)
    )
    return annual


def spread_ratio_to_monthly(
    wy_ratios: pd.DataFrame,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
    alloc_start_month: int = 5,
    default_ratio: float = 1.0,
) -> pd.DataFrame:
    """Spread WY-level ratios to monthly time series.

    The allocation for water year WY (calendar year CY) applies from May of CY
    through April of CY+1.  For a given month:
      - month >= alloc_start_month  -> use ratio for CY
      - month < alloc_start_month   -> use ratio for CY - 1

    Parameters
    ----------
    wy_ratios : DataFrame
        Columns: WY, Ratio.
    start_year, start_month : int
        First calendar month of output.
    end_year, end_month : int
        Last calendar month of output.
    alloc_start_month : int
        Month when new allocation kicks in (default 5 = May).
    default_ratio : float
        Ratio for WYs not present in wy_ratios.

    Returns
    -------
    DataFrame
        Columns: Part B, Part C, Year, Month, Value.
    """
    ratio_lookup = dict(zip(wy_ratios["WY"].astype(int), wy_ratios["Ratio"]))

    records = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        # Determine which WY's allocation applies to this month
        alloc_wy = y if m >= alloc_start_month else y - 1
        ratio = ratio_lookup.get(alloc_wy, default_ratio)
        records.append(
            {
                "Part B": "PGE_WY_ALLOCATION_SV",
                "Part C": "RATIO",
                "Year": y,
                "Month": m,
                "Value": ratio,
            }
        )
        # Advance to next month
        m += 1
        if m > 12:
            m = 1
            y += 1

    return pd.DataFrame(records)


# ──────────────────────────────────────────────────────────────────────────────
# Product A
# ──────────────────────────────────────────────────────────────────────────────
def run_product_a(config: dict) -> Path:
    """Generate PGE_WY_ALLOCATION_SV for Product A using FOLSM_INFLOW from QMap."""
    print("\n" + "=" * 60)
    print("Product A: PGE_WY_ALLOCATION_SV")
    print("=" * 60)

    # Load FOLSM_INFLOW from Product A QMap validation output
    df_all = pd.read_csv(RIM_INFLOW_PRODUCT_A_CSV)
    df_fols = (
        df_all[df_all["CalSim"] == "FOLSM_INFLOW"][["Year", "Month", "qmap_postAdj"]]
        .rename(columns={"qmap_postAdj": "FOLSM_INFLOW_TAF"})
        .copy()
    )
    print(f"  Loaded FOLSM_INFLOW (Product A): {len(df_fols)} monthly records")

    # Compute WY annual sums and apply thresholds
    thresholds = config["thresholds"]
    default_ratio = config["default_ratio"]
    wy_ratios = annual_flow_to_wy_ratio(df_fols, "FOLSM_INFLOW_TAF", thresholds, default_ratio)

    # Filter to study period
    wy_ratios_study = wy_ratios[
        (wy_ratios["WY"] >= PRODUCT_A_START_WY) & (wy_ratios["WY"] <= PRODUCT_A_END_WY)
    ].copy()

    # Also need the WY before the start for Oct-Apr of start year
    wy_before = wy_ratios[wy_ratios["WY"] == PRODUCT_A_START_WY - 1]
    wy_ratios_full = pd.concat([wy_before, wy_ratios_study], ignore_index=True)

    n_dry = len(wy_ratios_study[wy_ratios_study["Ratio"] < 1.0])
    print(f"  WYs with allocation < 1.0: {n_dry}/{len(wy_ratios_study)}")

    # Spread to monthly (Oct of start WY through Sep of end WY)
    start_year = PRODUCT_A_START_WY - 1  # Oct of previous CY = start of first WY
    start_month = 10
    end_year = PRODUCT_A_END_WY
    end_month = 9

    df_out = spread_ratio_to_monthly(
        wy_ratios_full,
        start_year, start_month,
        end_year, end_month,
        alloc_start_month=config["allocation_start_month"],
        default_ratio=default_ratio,
    )

    # Write output
    OUTPUT_A_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_A_DIR / f"_pge_wy_allocation_productA_{PRODUCT_A_START_WY}_{PRODUCT_A_END_WY}.csv"
    df_out.to_csv(out_path, index=False)
    print(f"  Wrote: {out_path.name} ({len(df_out)} rows)")

    return out_path


# ──────────────────────────────────────────────────────────────────────────────
# Product B
# ──────────────────────────────────────────────────────────────────────────────
def read_folsm_product_b(chunk: int) -> pd.DataFrame:
    """Read FOLSM_INFLOW for a Product B chunk from _10_RimInflow output.

    Parameters
    ----------
    chunk : int
        Chunk number (1-10).

    Returns
    -------
    DataFrame
        Columns: Year, Month, FOLSM_INFLOW_TAF.
    """
    fname = f"FOLSM_INFLOW_8RI_FOL_I_qmo_n{chunk:02d}.csv"
    fpath = RIM_INFLOW_PRODUCT_B_DIR / fname
    if not fpath.exists():
        raise FileNotFoundError(f"Product B FOLSM_INFLOW not found: {fpath}")

    df = pd.read_csv(fpath)
    return df[["Year", "Month", "qmap_postAdj"]].rename(
        columns={"qmap_postAdj": "FOLSM_INFLOW_TAF"}
    )


def run_product_b(config: dict) -> list[Path]:
    """Generate PGE_WY_ALLOCATION_SV for Product B using synthetic FOLSM_INFLOW.

    Uses the same thresholds as Product A applied directly to annual
    FOLSM_INFLOW sums (unimpaired Folsom inflow from QMap).
    """
    print("\n" + "=" * 60)
    print("Product B: PGE_WY_ALLOCATION_SV")
    print("=" * 60)

    thresholds = config["thresholds"]
    default_ratio = config["default_ratio"]
    alloc_month = config["allocation_start_month"]

    OUTPUT_B_DIR.mkdir(parents=True, exist_ok=True)
    output_paths = []

    for chunk in range(1, PRODUCT_B_NCHUNKS + 1):
        tag = f"n{chunk:02d}"
        print(f"\n  --- Chunk {tag} ---")

        # Read synthetic FOLSM_INFLOW
        df_folsm = read_folsm_product_b(chunk)
        print(f"  Loaded FOLSM_INFLOW: {len(df_folsm)} rows, "
              f"Year {df_folsm['Year'].min()}-{df_folsm['Year'].max()}")

        # Compute WY annual sums and apply thresholds directly
        wy_ratios = annual_flow_to_wy_ratio(
            df_folsm, "FOLSM_INFLOW_TAF", thresholds, default_ratio
        )

        n_dry = len(wy_ratios[wy_ratios["Ratio"] < 1.0])
        n_total = len(wy_ratios)
        print(f"  WYs: {n_total}, dry (ratio < 1.0): {n_dry}")

        # Determine output period: first full Oct through last Sep
        first_year = int(df_folsm["Year"].min())
        last_year = int(df_folsm["Year"].max())
        out_start_year = first_year
        out_start_month = 10  # Oct
        out_end_year = last_year
        out_end_month = 9     # Sep

        df_out = spread_ratio_to_monthly(
            wy_ratios,
            out_start_year, out_start_month,
            out_end_year, out_end_month,
            alloc_start_month=alloc_month,
            default_ratio=default_ratio,
        )

        out_path = OUTPUT_B_DIR / f"_pge_wy_allocation_productB_{tag}.csv"
        df_out.to_csv(out_path, index=False)
        output_paths.append(out_path)
        print(f"  Wrote: {out_path.name} ({len(df_out)} rows)")

    return output_paths


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    print("PGE_WY_ALLOCATION_SV Reconstruction")
    print("=" * 60)

    # Load config
    config = load_config(CONFIG_JSON)
    print(f"Config loaded: {CONFIG_JSON.name}")
    thresholds = config["thresholds"]
    print(f"  Thresholds: {[(t['annual_flow_taf_le'], t['ratio']) for t in thresholds]}")
    print(f"  Default ratio: {config['default_ratio']}")
    print(f"  Allocation start month: {config['allocation_start_month']}")

    target = TARGET_PRODUCT.upper().strip()

    if target in ("A", "BOTH"):
        run_product_a(config)

    if target in ("B", "BOTH"):
        run_product_b(config)

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
