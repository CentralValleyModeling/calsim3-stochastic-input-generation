"""
Extract CalSimHydroEE Outputs for CalSim Historical Validation
==============================================================
Reads the Product_A CalSimHydroEE DSS run and writes a standard validation CSV
(Part B, Part C, Year, Month, Value) filtered to the WY 1972–2018 validation window.
Output is consumed by _99_SV_Compile to build the master historical validation DSS.

Inputs
------
- CalSimHydroEE_Runs/CalSimHydroEE_Product_A/CalSimHydroEE_DP_EA.dss
- _MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx

Outputs
-------
- output/product_a_historical_validation/_cshydroEE_productA_1972_2018.csv

Usage
-----
    cd mod_hydrology/calsimhydro_ee && python _3_postprocess_for_calsim_validation.py
"""

import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_inventory_dir


# %% ── CONSTANTS ────────────────────────────────────────────────────────
_GEN_DIR = get_module_generated_dir("mod_hydrology/calsimhydro_ee")
OUTPUT_DIR = str(_GEN_DIR / "output" / "product_a_historical_validation")

EXCEL_PATH = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
SHEET_NAME = "MASTER"

# Validation window (water years)
START_WY = 1972
END_WY   = 2018

# DSS sources: (label, master-inventory col-9 filter, path to Combined DSS file)
_ee_runs = _GEN_DIR / "CalSimHydroEE_Runs"
DSS_SOURCES = [
    {
        "label":       "CalSimHydroEE_DP_EA",
        "inv_filter":  "IDCOutputEE.dss",
        "dss_path":    str(_ee_runs / "CalSimHydroEE_Product_A" / "CalSimHydroEE_DP_EA.dss"),
        "output_name": "_cshydroEE_productA",
    },
]


# %% ── HELPER FUNCTIONS ────────────────────────────────────────────────

def load_inventory_for_dss(inv_filter):
    """Load and filter master inventory rows for a given DSS filename."""
    df_master = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
    rows = df_master[
        (df_master.iloc[:, 8] == 'CalSimHydroEE') &
        (df_master.iloc[:, 9] == inv_filter)
    ]
    sv_names = [str(n).strip().upper() for n in rows.iloc[:, 7].tolist()]

    excel_to_part_BC = lambda n: n.upper().replace(" ", "_")
    excel_partcs = {excel_to_part_BC(n): n for n in sv_names}
    return excel_partcs


def extract_dss_data(dss_path, excel_partcs):
    """Extract monthly time series from a DSS file, filtered to inventory parts."""
    data_dict = {}
    with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            part_BC = parts[1].upper() + '/' + parts[2]
            buckets.setdefault(part_BC, []).append(p)

        wanted = {b: buckets[b] for b in buckets if b in excel_partcs} or buckets

        for part_BC, plist in wanted.items():
            master = {}
            for p in sorted(plist, key=lambda x: x.strip("/").split("/")[2]):
                ts = dss.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                s = pd.Series(vals, index=idx)
                master.update(s.to_dict())
            if master:
                series = pd.Series(master).sort_index()
                series.name = excel_partcs.get(part_BC, part_BC)
                data_dict[series.name] = series

    return pd.DataFrame(data_dict).sort_index()


def to_validation_csv(df, start_wy, end_wy):
    """Convert wide DataFrame (Date index, PartB/PartC columns) to validation format.

    Returns DataFrame with columns: Part B, Part C, Year, Month, Value
    filtered to the specified water year range.
    """
    # WY N runs Oct (N-1) through Sep (N)
    start_date = pd.Timestamp(start_wy - 1, 10, 1)
    end_date   = pd.Timestamp(end_wy, 9, 30)

    # Stack to long format
    long = df.stack().reset_index()
    long.columns = ['Date', 'PartBC', 'Value']
    long['Date'] = pd.to_datetime(long['Date'])

    # Filter to validation window
    mask = (long['Date'] >= start_date) & (long['Date'] <= end_date)
    long = long.loc[mask].copy()

    if long.empty:
        return pd.DataFrame(columns=['Part B', 'Part C', 'Year', 'Month', 'Value'])

    # Split PartB/PartC
    long[['Part B', 'Part C']] = long['PartBC'].str.split('/', expand=True)
    long['Year']  = long['Date'].dt.year
    long['Month'] = long['Date'].dt.month

    # Drop NaN values and order
    long = long.dropna(subset=['Value'])
    long = long[['Part B', 'Part C', 'Year', 'Month', 'Value']]
    long = long.sort_values(['Part B', 'Part C', 'Year', 'Month']).reset_index(drop=True)

    return long


# %% ── MAIN ─────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 80)
    print("CalSimHydroEE — CalSim Historical Validation Extraction")
    print(f"Period: WY {START_WY}–{END_WY}")
    print("=" * 80)

    for src in DSS_SOURCES:
        print(f"\n--- {src['label']} ---")

        # Check DSS file existence
        if not os.path.exists(src["dss_path"]):
            print(f"  ⚠  DSS not found, skipping: {src['dss_path']}")
            continue

        # Load inventory filter
        excel_partcs = load_inventory_for_dss(src["inv_filter"])
        print(f"  Inventory SVs: {len(excel_partcs)}")

        # Extract DSS data
        print(f"  Reading: {src['dss_path']}")
        df = extract_dss_data(src["dss_path"], excel_partcs)
        print(f"  Extracted: {df.shape[1]} variables, "
              f"{df.index.min().strftime('%Y-%m')} – {df.index.max().strftime('%Y-%m')}")

        # Convert to validation CSV
        val_df = to_validation_csv(df, START_WY, END_WY)

        if val_df.empty:
            print("  No data in validation period.")
            continue

        # Save
        out_file = os.path.join(
            OUTPUT_DIR,
            f"{src['output_name']}_{START_WY}_{END_WY}.csv"
        )
        val_df.to_csv(out_file, index=False)

        n_vars = val_df.groupby(['Part B', 'Part C']).ngroups
        print(f"  Written : {out_file}")
        print(f"  Variables: {n_vars}  |  Rows: {len(val_df):,}")

    print(f"\n{'=' * 80}")
    print("Validation extraction complete.")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
