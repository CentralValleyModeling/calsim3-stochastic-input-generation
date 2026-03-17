# -*- coding: utf-8 -*-
"""
Created on 10/02/2025
@author: mbastani

This script uses Sum-Product calculation to aggregates 168 island monthly flow time series (in cfs) 
into Delta & WBA50 weighted totals for DP-FLOW and GW-FLOW, and write four 
new records into "DCD_island_month_C3.dss".

Note: If you want the weighted average instead of sum, just divide 
each result by w["Delta"].sum() or w["WBA50"].sum() before writing.

Python configurations:
It works with both "read_ts" or "get_ts", parses island IDs from Part B, and 
writes via "TimeSeriesContainer" (most compatible). Handles "pytimes" vs "times".

Inputs
------
- DCD_island_month.dss
- WeightedRatiosForDCD.csv  (columns: Island, Delta, WBA50; tab or comma separated)

Outputs
-------
- DCD_island_month_C3.dss with:
  /<A>/DP_DELTA_DCD/DP-FLOW/<D>/<E>/<F>/
  /<A>/DP_WBA50_DCD/DP-FLOW/<D>/<E>/<F>/
  /<A>/GW_DELTA_DCD/GW-FLOW/<D>/<E>/<F>/
  /<A>/GW_WBA50_DCD/GW-FLOW/<D>/<E>/<F>/
"""

#%%# ========================= 1) Imports & File Paths =========================
import os
import sys
import re
import pandas as pd
from pathlib import Path
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer as TSC

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_GEN_DIR = get_module_generated_dir("mod_hydrology/delta_channel_depletion")
_SCRIPT_DIR = Path(__file__).resolve().parent

DSS_IN  = str(_GEN_DIR / "DeltaChannelDepletion_Runs" / "DCD_island_month.dss")
DSS_OUT = str(_GEN_DIR / "DeltaChannelDepletion_Runs" / "DCD_island_month_C3.dss")
CSV     = str(_SCRIPT_DIR / "reference" / "WeightedRatiosForDCD.csv")  # columns: Island, Delta, WBA50

# Override A- and F-parts for outputs:
A_OUT = "CALSIM"
F_OUT = "L2015A"

#%%# ===================== 2) DSS Utilities (paths & series) ====================
def get_paths(fid, cpart):
    return sorted(fid.getPathnameList(f"/*/*/{cpart}/*/*/*/"))

def ts_series(fid, path):
    ts = fid.read_ts(path, trim_missing=True) if hasattr(fid, "read_ts") else fid.get_ts(path, trim_missing=True)
    t  = pd.to_datetime(ts.pytimes if hasattr(ts, "pytimes") else ts.times)
    return pd.Series(ts.values, index=t).sort_index()

def island_id(path):
    b = path.strip("/").split("/")[1]
    m = re.findall(r"\d+", b)
    return int(m[-1]) if m else None

#%%# ======================= 3) Weighted Sum-Product Logic =======================

# Sum_i (w_i * series_i) across provided paths.
# Weights are looked up by the island id parsed from B-part.
# Missing ids default to weight 0.

def sum_weighted(fid, paths, weights, col):
    out = None
    for p in paths:
        iid = island_id(p)
        w = float(weights.at[iid, col]) if (iid in weights.index) else 0.0
        s = ts_series(fid, p) * w
        out = s if out is None else out.add(s, fill_value=0.0)
    return out

#%%# ========================== 4) Writing Results to DSS =========================

# Write a monthly series via TimeSeriesContainer, preserving A/C/D/E/F from template.

def write_series(fid_out, template_path, new_b, series, units="CFS", vtype="PER-AVER"):
    A,B,C,D,E,F = template_path.strip("/").split("/")
    A, F = A_OUT, F_OUT     # override Parts A and F
    new_path = f"/{A}/{new_b}/{C}/{D}/{E}/{F}/"
    tsc = TSC()
    tsc.pathname = new_path
    tsc.startDateTime = series.index[0].strftime("%d%b%Y %H%M").upper()
    tsc.values = series.values.astype(float)
    tsc.numberValues = len(tsc.values)
    tsc.interval = 1        # monthly step
    tsc.units = units       # "CFS"
    tsc.type  = vtype       # "PER-AVER"
    fid_out.put_ts(tsc)
    return new_path

#%%# =============================== 5) Main Flow ===============================
if __name__ == "__main__":
    # Load weights (tab or comma CSV). Expect columns: Island, Delta, WBA50
    w = pd.read_csv(CSV, sep=None, engine="python")
    w = w[["Island","Delta","WBA50"]].copy()
    w["Island"] = pd.to_numeric(w["Island"], errors="coerce").round().astype(int)
    w["Delta"]  = pd.to_numeric(w["Delta"],  errors="coerce").fillna(0.0)
    w["WBA50"]  = pd.to_numeric(w["WBA50"],  errors="coerce").fillna(0.0)
    w = w.set_index("Island")

    # Read DSS inputs
    fin  = HecDss.Open(DSS_IN)
    dp   = get_paths(fin, "DP-FLOW")
    gw   = get_paths(fin, "GW-FLOW")

    # Aggregate (sum-product in CFS)
    dp_delta  = sum_weighted(fin, dp, w, "Delta")
    dp_wba50  = sum_weighted(fin, dp, w, "WBA50")
    gw_delta  = sum_weighted(fin, gw, w, "Delta")
    gw_wba50  = sum_weighted(fin, gw, w, "WBA50")

    # Write outputs
    fout = HecDss.Open(DSS_OUT)
    write_series(fout, dp[0], "DP_DELTA_DCD",  dp_delta)
    write_series(fout, dp[0], "DP_WBA50_DCD",  dp_wba50)
    write_series(fout, gw[0], "GW_DELTA_DCD",  gw_delta)
    write_series(fout, gw[0], "GW_WBA50_DCD",  gw_wba50)
    fin.close(); fout.close()
    print(f"Wrote 4 records to {DSS_OUT}")
