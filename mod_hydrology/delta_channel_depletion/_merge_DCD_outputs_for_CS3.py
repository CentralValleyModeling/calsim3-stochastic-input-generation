# -*- coding: utf-8 -*-
"""
Merge DCD Outputs for CalSim 3
==============================
Copies every time-series record of two DSS files of one DCD run into CS3sv_DCD_PRISM_Dtrnd.dss,
keeping pathnames, units and type. Where both files hold a pathname, the second file's record
is taken; a record that fails to read from one file is read from the other.

Inputs
------
- <run_dir>/DCD_island_month_C3.dss (written by _aggregate_dpflow_gwflow_for_DCD.py)
- <run_dir>/DCD_Sep2018_Lch5_mon_C3.dss
(run_dir: the positional argument, a DCD run folder)

Outputs
-------
- <run_dir>/CS3sv_DCD_PRISM_Dtrnd.dss (_2_postprocess_single.py reads it from
  <run>/DCD/Output/CALSIM3/)

Dependencies
------------
utils.dss_io; pydsstools. Does not import utils.paths.

Usage
-----
    python mod_hydrology/delta_channel_depletion/_merge_DCD_outputs_for_CS3.py <run_dir>

Author: mbastani, 10/2/2025
"""


#%%# ====================== 1) Imports & Config ======================
import argparse
import sys
import numpy as np
from pathlib import Path
from pydsstools.core import TimeSeriesContainer as TSC

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io

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

#%%# ========================= 3) Merge Execution =========================
# version=None: a new DST is created as DSS 7, the version of the DCD outputs CalSim reads
with (dss_io.open_dss(SRC[0], version=None) as f0, dss_io.open_dss(SRC[1], version=None) as f1,
      dss_io.open_dss(DST, version=None) as fout):
    chosen = {p:0 for p in all_paths(f0)}       # take all from first
    for p in all_paths(f1): chosen[p] = 1       # overwrite with second when duplicated

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

print("Merged into", DST)
if failed_paths:
    print(f"Skipped {len(failed_paths)} path(s) due to read/write errors")

