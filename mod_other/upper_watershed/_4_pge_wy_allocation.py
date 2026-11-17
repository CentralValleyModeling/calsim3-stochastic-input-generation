"""
PGE Water-Year Allocation Ratio (PGE_WY_ALLOCATION_SV)
======================================================
PGE_WY_ALLOCATION_SV/RATIO from the water-year total of the rim-inflow SV FOLSM_INFLOW (TAF), by
the threshold table of PGE_WY_ALLOCATION_SV-Reconstruction.xlsx. The ratio of water year WY
applies from May of calendar year WY through April of WY+1.

Thresholds (reference/PGE_WY_ALLOCATION_config.json):

    annual flow (TAF)   ratio
    <= 488.24           0.4
    <= 800.72           0.6
    <= 957.08           0.8
    <= 1146.02          0.9
    > 1146.02           1.0

Oct 1921 - Apr 1922 take the WY1921 ratio: from the model run for Historical_Unsplit and
Product A, the chunk's WY1922 ratio for each Product B chunk.

Inputs
------
- reference/PGE_WY_ALLOCATION_config.json: thresholds, default ratio, allocation start month
- Historical_Unsplit, Product A: FOLSM_INFLOW rows of the set's calsim_qmap_validation_TS.csv
  (utils.paths.get_rim_inflow_outputs)
- Product B: FOLSM_INFLOW_qmo_n01.csv ... _n10.csv (qmap_postAdj;
  utils.paths.get_rim_inflow_outputs)

Outputs
-------
Under <generated>/mod_other/upper_watershed/output/:
- _historical_unsplit_validation/_pge_wy_allocation_historicalUnsplit_1922_2018.csv
- _product_a_validation/_pge_wy_allocation_productA_1922_2018.csv
- _product_b_final/_pge_wy_allocation_productB_n01.csv ... _n10.csv

Delivery and chunk CSVs: Part B, Part C, Year, Month, Value.

Dependencies
------------
utils.paths, utils.csv_io, utils.wgen_calendar

Usage
-----
    python mod_other/upper_watershed/_4_pge_wy_allocation.py --product historical
    python mod_other/upper_watershed/_4_pge_wy_allocation.py --product A
    python mod_other/upper_watershed/_4_pge_wy_allocation.py --product B
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.csv_io import write_delivery_csv
from utils.wgen_calendar import LABEL_MONTHS, N_CHUNKS, water_year, write_chunk_csvs, wy_months
from utils.paths import DELIVERY_WY, WEATHER_SETS, delivery_dir, get_module_generated_dir, get_rim_inflow_outputs

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------
RUN_DIR = Path(__file__).resolve().parent

# Delivered water years of the single series
START_WY, END_WY = DELIVERY_WY

# Input paths (relative to this script)
REFERENCE_DIR = RUN_DIR / "reference"
CONFIG_JSON = REFERENCE_DIR / "PGE_WY_ALLOCATION_config.json"

# RimInflow files
RIM_INFLOW_PRODUCT_B_DIR = get_rim_inflow_outputs("B")["dir"]

# Output directories
_GEN_DIR = get_module_generated_dir("mod_other/upper_watershed")
OUTPUT_ROOT = _GEN_DIR / "output" / "_4_pge_wy_allocation"
OUTPUT_B_DIR = _GEN_DIR / "output" / "_product_b_final"


# ------------------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------------------
def load_config(config_path: Path) -> dict:
    """Load thresholds and regression parameters from JSON config."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


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
    df["WY"] = water_year(df["Year"], df["Month"])
    annual = df.groupby("WY")[flow_col].sum().reset_index()
    annual.columns = ["WY", "Annual_Flow_TAF"]
    annual["Ratio"] = annual["Annual_Flow_TAF"].apply(
        lambda x: apply_thresholds(x, thresholds, default_ratio)
    )
    return annual


def spread_ratio_to_monthly(
    wy_ratios: pd.DataFrame,
    months: pd.DataFrame,
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
    months : DataFrame
        Year and Month of the output months, in order (utils.wgen_calendar.wy_months or
        LABEL_MONTHS).
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
    year = months["Year"].astype(int).to_numpy()
    month = months["Month"].astype(int).to_numpy()
    # The allocation of the water year in whose calendar year the month falls from May on
    alloc_wy = [y if m >= alloc_start_month else y - 1 for y, m in zip(year, month)]
    return pd.DataFrame({
        "Part B": "PGE_WY_ALLOCATION_SV",
        "Part C": "RATIO",
        "Year": year,
        "Month": month,
        "Value": [ratio_lookup.get(w, default_ratio) for w in alloc_wy],
    })


# ------------------------------------------------------------------------------
# Historical_Unsplit and Product A
# ------------------------------------------------------------------------------
def run_single(config: dict, product: str) -> Path:
    """Generate PGE_WY_ALLOCATION_SV for Historical_Unsplit or Product A using the set's
    FOLSM_INFLOW from QMap."""
    name = WEATHER_SETS[product]["name"]
    print("\n" + "=" * 60)
    print(f"{name}: PGE_WY_ALLOCATION_SV")
    print("=" * 60)

    # Load FOLSM_INFLOW from the set's QMap validation output
    df_all = pd.read_csv(get_rim_inflow_outputs(product)["ts"])
    df_fols = (
        df_all[df_all["CalSim"] == "FOLSM_INFLOW"][["Year", "Month", "qmap_postAdj"]]
        .rename(columns={"qmap_postAdj": "FOLSM_INFLOW_TAF"})
        .copy()
    )
    print(f"  Loaded FOLSM_INFLOW ({name}): {len(df_fols)} monthly records")

    # Compute WY annual sums and apply thresholds
    thresholds = config["thresholds"]
    default_ratio = config["default_ratio"]
    wy_ratios = annual_flow_to_wy_ratio(df_fols, "FOLSM_INFLOW_TAF", thresholds, default_ratio)

    # Filter to study period
    wy_ratios_study = wy_ratios[
        (wy_ratios["WY"] >= START_WY) & (wy_ratios["WY"] <= END_WY)
    ].copy()

    # Also need the WY before the start for Oct-Apr of start year
    wy_before = wy_ratios[wy_ratios["WY"] == START_WY - 1]
    wy_ratios_full = pd.concat([wy_before, wy_ratios_study], ignore_index=True)

    n_dry = len(wy_ratios_study[wy_ratios_study["Ratio"] < 1.0])
    print(f"  WYs with allocation < 1.0: {n_dry}/{len(wy_ratios_study)}")

    # Spread to monthly (Oct of start WY through Sep of end WY)
    df_out = spread_ratio_to_monthly(
        wy_ratios_full,
        wy_months(START_WY, END_WY),
        alloc_start_month=config["allocation_start_month"],
        default_ratio=default_ratio,
    )

    # Write output
    out_path = write_delivery_csv(df_out, delivery_dir(_GEN_DIR / "output", product),
                                  "_pge_wy_allocation", product)
    print(f"  Wrote: {out_path.name} ({len(df_out)} rows)")

    return out_path


# ------------------------------------------------------------------------------
# Product B
# ------------------------------------------------------------------------------
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
    fname = f"FOLSM_INFLOW_qmo_n{chunk:02d}.csv"
    fpath = RIM_INFLOW_PRODUCT_B_DIR / fname
    if not fpath.exists():
        raise FileNotFoundError(f"Product B FOLSM_INFLOW not found: {fpath}")

    df = pd.read_csv(fpath)
    return df[["Year", "Month", "qmap_postAdj"]].rename(
        columns={"qmap_postAdj": "FOLSM_INFLOW_TAF"}
    )


def run_product_b(config: dict) -> list[Path]:
    """Generate PGE_WY_ALLOCATION_SV for Product B using synthetic FOLSM_INFLOW.

    Uses the same thresholds as the single series applied directly to annual
    FOLSM_INFLOW sums (unimpaired Folsom inflow from QMap).
    """
    print("\n" + "=" * 60)
    print("Product B: PGE_WY_ALLOCATION_SV")
    print("=" * 60)

    thresholds = config["thresholds"]
    default_ratio = config["default_ratio"]
    alloc_month = config["allocation_start_month"]

    chunks = []
    for chunk in range(1, N_CHUNKS + 1):
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

        # The chunk starts at Oct 1921, so spread_ratio_to_monthly needs a WY
        # 1921 entry to assign allocations for Oct 1921 - Apr 1922.  WY 1921
        # cannot be computed (only 3 months of data available), so use WY 1922
        # as the nearest proxy.
        first_wy = int(wy_ratios["WY"].min())
        wy_before = wy_ratios[wy_ratios["WY"] == first_wy].copy()
        wy_before["WY"] = first_wy - 1
        wy_ratios = pd.concat([wy_before, wy_ratios], ignore_index=True)

        n_dry = len(wy_ratios[wy_ratios["Ratio"] < 1.0])
        n_total = len(wy_ratios)
        print(f"  WYs: {n_total}, dry (ratio < 1.0): {n_dry}")

        # Output period: the chunk's label months, Oct 1921 - Sep 2021
        df_out = spread_ratio_to_monthly(
            wy_ratios,
            LABEL_MONTHS,
            alloc_start_month=alloc_month,
            default_ratio=default_ratio,
        )
        chunks.append(df_out.assign(chunk=chunk))

    output_paths = write_chunk_csvs(pd.concat(chunks, ignore_index=True), OUTPUT_B_DIR,
                                    "_pge_wy_allocation_productB")
    print(f"  Wrote: {len(output_paths)} chunk files to {OUTPUT_B_DIR}")
    return output_paths


# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(
        description="PGE_WY_ALLOCATION_SV reconstruction from FOLSM_INFLOW thresholds.")
    ap.add_argument("--product", choices=list(WEATHER_SETS), required=True,
                    help='Weather set: historical (Historical_Unsplit) or A (WY1922-2018), '
                         'or B (stochastic 1000-yr chunks).')
    args = ap.parse_args()

    print("PGE_WY_ALLOCATION_SV Reconstruction")
    print("=" * 60)

    # Load config
    config = load_config(CONFIG_JSON)
    print(f"Config loaded: {CONFIG_JSON.name}")
    thresholds = config["thresholds"]
    print(f"  Thresholds: {[(t['annual_flow_taf_le'], t['ratio']) for t in thresholds]}")
    print(f"  Default ratio: {config['default_ratio']}")
    print(f"  Allocation start month: {config['allocation_start_month']}")

    if args.product == "B":
        run_product_b(config)
    else:
        run_single(config, args.product)

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
