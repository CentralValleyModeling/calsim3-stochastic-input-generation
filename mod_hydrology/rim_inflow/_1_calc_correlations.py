"""
CalSim vs VIC Inflow Correlations
=================================
Calculate R-squared between each CalSim DSS inflow (1920-2021) and all
VIC SAC-SMA routed inflows (1915-2018) over their overlapping period.

For CalSim inflows with an exact VIC name match, the direct correlation
is used. For unmatched names, the best-correlated VIC inflow is selected.

Inputs
------
- CalSim baseline DSS:  CalSim3/__calsim_sv_default__.dss
- Master inventory:     _MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx
- VIC historical routed: mod_forcing/vic/output/routed/Historical/

Outputs
-------
- _1_calc_correlations/r2_calsim_vs_vic.csv
  Columns: DSS Inflow, VIC Inflow (matched or best), R-squared

Usage
-----
    cd mod_hydrology/rim_inflow && python _1_calc_correlations.py
"""

# %% This script calculates the Correlation (R^2) between
# CALSIM inflows (1920-2021) and SAC-SMA inflows (1915-2018) over their
# overlapping period (1920-2018).
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_inventory_dir, get_module_generated_dir

_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_vic_gen = get_module_generated_dir("mod_forcing/vic")

# %% ---  Extract inflow names from Excel MASTER file ---
excel_path = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
sheet_name = "MASTER"
df_master = pd.read_excel(excel_path, sheet_name=sheet_name)
inflow_rows = df_master[df_master.iloc[:, 8] == 'Rim Inflow']
inflow_names = [str(name).strip().upper() for name in inflow_rows.iloc[:, 2].tolist()]
vic_path = str(_vic_gen / "output" / "routed" / "Historical")


# %% --- read DSS monthly INFLOW slices, overwrite missing codes with NaN
excel_to_part_b = lambda n: n.upper().replace(" ", "_")
excel_partbs     = {excel_to_part_b(n): n for n in inflow_names}

dss_path = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"

dss_monthly = {}
with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:

    all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
    buckets   = {}
    for p in all_paths:
        part_b = p.strip("/").split("/")[1].upper()
        buckets.setdefault(part_b, []).append(p)

    wanted = {b: buckets[b] for b in buckets if b in excel_partbs} or buckets
    full_index = pd.date_range("1915-01-31", "2021-12-31", freq="ME")

    for part_b, plist in wanted.items():
        master = pd.Series(index=full_index, dtype="float64")
        for p in sorted(plist, key=lambda x: x.strip("/").split("/")[3]):
            ts = dss.read_ts(p, trim_missing=True)
            vals = np.asarray(ts.values, dtype=float)
            vals[vals <= -900] = np.nan                         # -901 → NaN

            idx = (
                pd.to_datetime(ts.pytimes)
                  .to_period("M")  - 1     # back one monthly period for correction
            ).to_timestamp("M")            # month‑end (.to_period("M") to have values for end of each months)

            master.update(pd.Series(vals, index=idx))

        if master.notna().any():
            inflow_ = excel_partbs.get(part_b, part_b)
            master.name = inflow_
            dss_monthly[inflow_] = master

dss_monthly_df = pd.DataFrame(dss_monthly).sort_index()

print(dss_monthly_df.head())

vic_series = {}
vic_file_info = []
for file in os.listdir(vic_path):
    VICinflow = file[len("CS3_") : -len("_qmo.csv")] 
    fpath = os.path.join(vic_path, file)
    df_v = pd.read_csv(fpath, header=None)
    df_v.iloc[:, 0] = pd.to_datetime(df_v.iloc[:, 0], errors="coerce")
    ser = pd.Series(df_v.iloc[:, 1].values, index=df_v.iloc[:, 0].values, name=VICinflow)


    vic_series[VICinflow] = ser.sort_index()
    vic_file_info.append((file, VICinflow))

vic_monthly_df = pd.DataFrame(vic_series).sort_index()


# 3) Name matching: try exact (normalized) match first, else fall back to best-correlation VIC
dss_names_ordered = [n for n in inflow_names if n in dss_monthly_df.columns]
vic_names = list(vic_monthly_df.columns)


results_rows = []
unmatched_dss = []

for dss in dss_names_ordered:

    # Try exact name match on normalized labels
    if dss in vic_names:
        matched_vic = dss
        series1 = dss_monthly_df[dss]
        series2 = vic_monthly_df[matched_vic]
        r = series1.corr(series2)
        r2 = float(r**2) if pd.notnull(r) else np.nan
        results_rows.append([dss, matched_vic, r2])
    else:
        # No direct match: find max-correlated VIC across all
        unmatched_dss.append(dss)
        series1 = dss_monthly_df[dss]
        
        best_matched = None
        best_r2 = -np.inf
        for vic in vic_names:
            series2 = vic_monthly_df[vic]
            r = series1.corr(series2)
            r2 = float(r**2) if pd.notnull(r) else np.nan
            if pd.notnull(r2) and r2 > best_r2:
                best_r2 = r2
                best_matched = vic

        results_rows.append([dss, best_matched, (best_r2 if best_matched is not None else np.nan)])

# 4) Build final output: keep EXACT Excel order; one VIC name + one R² per DSS inflow
final_df = pd.DataFrame(results_rows, columns=["DSS Inflow", "VIC Inflow (matched or best)", "R²"]).set_index("DSS Inflow")
final_df = final_df.reindex(dss_names_ordered).reset_index()
_out_dir = _gen / "output" / "_1_calc_correlations"
_out_dir.mkdir(parents=True, exist_ok=True)
final_df.to_csv(str(_out_dir / "r2_calsim_vs_vic.csv"), index=False)





































