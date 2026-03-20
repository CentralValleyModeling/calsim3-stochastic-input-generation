# -*- coding: utf-8 -*-
"""
Created on 10/2/2025
@author: mbastani

This script merges two DSS files called "DCD_island_month_C3" and "DCD_Sep2018_Lch5_mon_C3" into a
single DSS v6 file called "CS3sv_DCD_PRISM_Dtrnd.dss". It copies all time-series
records (preserving units/type and A-F parts), preferring records from the 2nd file on conflicts.

Usage
-----
    python _3_merge_DCD_outputs_for_CS3.py <run_dir>

Example
-------
    python _3_merge_DCD_outputs_for_CS3.py "C:\path\to\data\GENERATED\mod_hydrology\delta_channel_depletion\DeltaChannelDepletion_Runs\DCD_Calsim3_PlanningStudy_1921-2018"

Arguments
---------
run_dir : Path
    Path to the DCD model run directory containing the source DSS files.

Inputs
------
- <run_dir>/DCD_island_month_C3.dss
- <run_dir>/DCD_Sep2018_Lch5_mon_C3.dss

Outputs
-------
- <run_dir>/CS3sv_DCD_PRISM_Dtrnd.dss
"""


#%%# ====================== 1) Imports & Config ======================
import os
import argparse
import numpy as np
from pathlib import Path
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer as TSC

parser = argparse.ArgumentParser(
    description="Merge DCD_island_month_C3 and DCD_Sep2018_Lch5_mon_C3 into CS3sv_DCD_PRISM_Dtrnd.dss."
)
parser.add_argument(
    "run_dir",
    type=Path,
    help="Path to the DCD model run directory containing the source DSS files",
)
args = parser.parse_args()

RUN_DIR = args.run_dir.resolve()
SRC = [
    str(RUN_DIR / "DCD_island_month_C3.dss"),
    str(RUN_DIR / "DCD_Sep2018_Lch5_mon_C3.dss"),
]  # second wins
DST = str(RUN_DIR / "CS3sv_DCD_PRISM_Dtrnd.dss")

#%%# ========================= 2) Small Helpers =========================
def all_paths(fid): 
    return fid.getPathnameList("/*/*/*/*/*/*/")

def read_ts_obj(fid, p):
    if hasattr(fid, "read_ts"):
        return fid.read_ts(p, trim_missing=False)
    return fid.get_ts(p, trim_missing=False)

def write_ts(fout, p, ts):
    tsc = TSC()
    tsc.pathname = p
    if hasattr(ts, "startDateTime") and ts.startDateTime:
        tsc.startDateTime = ts.startDateTime
    else:
        t0 = ts.pytimes[0] if hasattr(ts, "pytimes") else ts.times[0]
        tsc.startDateTime = t0.strftime("%d%b%Y %H%M").upper()
    tsc.values = np.asarray(ts.values, dtype=float)
    tsc.numberValues = len(tsc.values)
    tsc.interval = getattr(ts, "interval", 1)
    tsc.units = getattr(ts, "units", "")
    tsc.type = getattr(ts, "type", "")
    fout.put_ts(tsc)

def open_v6(path):
    if os.path.exists(path): os.remove(path)  # ensure fresh create as v6
    try:    return HecDss.Open(path, version=6)
    except TypeError:
        try:    return HecDss.Open(path, v6=True)
        except TypeError:
            os.environ["HEC_DSS_VERSION"] = "6"
            return HecDss.Open(path)

#%%# ========================= 3) Merge Execution =========================
f0, f1 = HecDss.Open(SRC[0]), HecDss.Open(SRC[1])
chosen = {p:0 for p in all_paths(f0)}       # take all from first
for p in all_paths(f1): chosen[p] = 1       # overwrite with second when duplicated

fout = HecDss.Open(DST)
failed_paths = []
for p, idx in chosen.items():
    src_primary = (f0, f1)[idx]
    src_secondary = (f1, f0)[idx]
    try:
        ts = read_ts_obj(src_primary, p)
        write_ts(fout, p, ts)
    except Exception:
        try:
            ts = read_ts_obj(src_secondary, p)
            write_ts(fout, p, ts)
        except Exception:
            failed_paths.append(p)

f0.close(); f1.close(); fout.close()
print("Merged into", DST)
if failed_paths:
    print(f"Skipped {len(failed_paths)} path(s) due to read/write errors")

