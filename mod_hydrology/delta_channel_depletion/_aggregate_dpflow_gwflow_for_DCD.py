# -*- coding: utf-8 -*-
"""
Aggregate DCD Island DP and GW Flows to Delta and WBA 50
========================================================
Weighted sums (CFS, PER-AVER) of the monthly DP-FLOW and GW-FLOW of every DCD island into Delta
and WBA 50 totals, written as four records of one DCD run. Each island's weight comes from its
id in Part B; an island missing from the weight table counts 0.

Inputs
------
- <run_dir>/DCD_island_month.dss (run_dir: the positional argument, a DCD run folder)
- reference/WeightedRatiosForDCD.csv: Island, Delta, WBA50 (tab or comma separated)

Outputs
-------
- <run_dir>/DCD_island_month_C3.dss, Parts D and E from the first input record:
  /CALSIM/DP_DELTA_DCD/DP-FLOW/<D>/<E>/L2015A/, /CALSIM/DP_WBA50_DCD/DP-FLOW/<D>/<E>/L2015A/,
  /CALSIM/GW_DELTA_DCD/GW-FLOW/<D>/<E>/L2015A/, /CALSIM/GW_WBA50_DCD/GW-FLOW/<D>/<E>/L2015A/

Dependencies
------------
utils.dss_io; pydsstools. Does not import utils.paths.

Usage
-----
    python mod_hydrology/delta_channel_depletion/_aggregate_dpflow_gwflow_for_DCD.py <run_dir>

Author: mbastani, 10/02/2025
"""

#%%# ========================= 1) Imports & File Paths =========================
import re
import argparse
import sys
import pandas as pd
from pathlib import Path
from pydsstools.core import TimeSeriesContainer as TSC

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io

_SCRIPT_DIR = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(
    description="Aggregate 168 island monthly flows into Delta & WBA50 weighted totals."
)
parser.add_argument(
    "run_dir",
    type=Path,
    help="Path to the DCD model run directory containing DCD_island_month.dss",
)
args = parser.parse_args()

RUN_DIR = args.run_dir.resolve()
DSS_IN  = str(RUN_DIR / "DCD_island_month.dss")
DSS_OUT = str(RUN_DIR / "DCD_island_month_C3.dss")
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
    with dss_io.open_dss(DSS_IN, version=None) as fin:
        dp   = get_paths(fin, "DP-FLOW")
        gw   = get_paths(fin, "GW-FLOW")

        # Aggregate (sum-product in CFS)
        dp_delta  = sum_weighted(fin, dp, w, "Delta")
        dp_wba50  = sum_weighted(fin, dp, w, "WBA50")
        gw_delta  = sum_weighted(fin, gw, w, "Delta")
        gw_wba50  = sum_weighted(fin, gw, w, "WBA50")

    # Write outputs; version=None creates a new DSS_OUT as DSS 7, like the DCD outputs CalSim reads
    with dss_io.open_dss(DSS_OUT, version=None) as fout:
        write_series(fout, dp[0], "DP_DELTA_DCD",  dp_delta)
        write_series(fout, dp[0], "DP_WBA50_DCD",  dp_wba50)
        write_series(fout, gw[0], "GW_DELTA_DCD",  gw_delta)
        write_series(fout, gw[0], "GW_WBA50_DCD",  gw_wba50)
    print(f"Wrote 4 records to {DSS_OUT}")
