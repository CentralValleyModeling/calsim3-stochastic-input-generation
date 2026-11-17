# %% Fix ProductB_SV_n10.dss -- restore baseline values through Oct 1921
"""
Chunk n10 First-Month Fix, October 1921
=======================================
Writes a copy of the Product B chunk n10 SV DSS whose values through October 1921
are the CalSim 3 baseline's, so the run starts from the baseline state; November
1921 to September 2021 keep n10's values. The original file is left unchanged.

n10 fails at its first timestep, October 1921 (wr_ranchomurieta.wresl, cycle 14
sjrbase), reported as ``maxdiversionrate_total in svar definition: Initial data of
rnchowr_rem_totaldv in dss file doesn't exist``. ``rnchowr_rem_totaldv`` is a
decision variable, absent from any SV DSS, so the message follows from the failed
first-month LP rather than a missing record. The compiled n10 DSS holds all 19,063
paths at October 1921 with valid values. The trigger is n10's October 1921 draw:
I_CSM035 (Cosumnes inflow, which drives the Rancho Murieta water right) is 19.5 TAF
against the baseline's 0.33, with Sacramento unimpaired flows 10-17 times the
baseline's, in the first month of the run. The binding LP constraint is not
isolated. The other chunks fail later in their runs (WRESL fixes).

Steps: copy ProductB_SV_n10.dss (and its .dsd, .dsk, .dsc) to ProductB_SV_n10_fixed.dss;
for every monthly path of the baseline whose D part holds 1920, write the n10 block
back with the baseline's values for the months through October 1921.

Inputs
------
- <base>/CalSim3/__calsim_sv_default__.dss
- <generated>/postprocessing/sv_compile/product_b_compilation/_product_b_compiled_sv/ProductB_SV_n10.dss

Outputs
-------
- <generated>/postprocessing/sv_compile/product_b_compilation/_product_b_compiled_sv/ProductB_SV_n10_fixed.dss

Dependencies
------------
utils.dss_io, utils.paths; numpy, pandas, pydsstools

Usage
-----
    python postprocessing/calsim_runs/infeasibilities/n10.py
"""

import sys
import shutil
import time
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils import dss_io
from utils.paths import get_base_dir, get_module_generated_dir

from pydsstools.core import TimeSeriesContainer

# -- Paths -----------------------------------------------------------------
_base = get_base_dir()
_gen = get_module_generated_dir("postprocessing/sv_compile")

BASELINE_DSS = _base / "CalSim3" / "__calsim_sv_default__.dss"
COMPILED_DIR = _gen / "product_b_compilation" / "_product_b_compiled_sv"
N10_DSS      = COMPILED_DIR / "ProductB_SV_n10.dss"
N10_FIXED    = COMPILED_DIR / "ProductB_SV_n10_fixed.dss"

DSS_PATTERN = "/*/*/*/*/1MON/*"

# Cutoff: restore baseline values for months <= October 1921
CUTOFF = pd.Timestamp(1921, 10, 31)

def dss_eom(ts_pytimes):
    """Convert pydsstools start-of-period dates to end-of-month timestamps."""
    return (pd.to_datetime(ts_pytimes).to_period("M") - 1).to_timestamp("M")


def safe_write_ts(dss_out, pathname, ts_obj):
    ts_obj.pathname = pathname
    if hasattr(dss_out, "put_ts"):
        dss_out.put_ts(ts_obj)
    elif hasattr(dss_out, "write_ts"):
        dss_out.write_ts(ts_obj)


# -- Main ------------------------------------------------------------------
def main():
    t0 = time.time()

    # Validate inputs
    if not BASELINE_DSS.exists():
        sys.exit(f"ERROR: Baseline DSS not found: {BASELINE_DSS}")
    if not N10_DSS.exists():
        sys.exit(f"ERROR: n10 DSS not found: {N10_DSS}")

    # Step 1: Copy n10 -> n10_fixed
    print(f"Source n10:  {N10_DSS}")
    print(f"Output:      {N10_FIXED}")
    print(f"Baseline:    {BASELINE_DSS}")
    print(f"Cutoff:      values <= {CUTOFF.strftime('%b %Y')} restored from baseline")
    print()

    print("Step 1: Copying n10 DSS to new fixed file ...")
    for f in [N10_FIXED] + [N10_FIXED.with_suffix(e) for e in [".dsd", ".dsk", ".dsc"]]:
        if f.exists():
            f.unlink()
    shutil.copy2(N10_DSS, N10_FIXED)
    for ext in [".dsd", ".dsk", ".dsc"]:
        src = N10_DSS.with_suffix(ext)
        if src.exists():
            shutil.copy2(src, N10_FIXED.with_suffix(ext))
    print("  Done.")
    print()

    # Step 2: Find all 01JAN1920 decade paths in baseline (these contain Oct 1921)
    print("Step 2: Scanning baseline for 1920-decade paths ...")
    paths_1920 = []
    with dss_io.open_dss(BASELINE_DSS) as dss_base:
        all_paths = dss_base.getPathnameList(DSS_PATTERN)
        for p in all_paths:
            parts = p.strip("/").split("/")
            # Part D (date) is parts[3], e.g. "01JAN1920"
            if "1920" in parts[3]:
                paths_1920.append(p)
    print(f"  Found {len(paths_1920)} paths in the 1920 decade block.")
    print()

    # Step 3: For each 1920-decade path, merge baseline+n10 values
    print("Step 3: Restoring baseline values through Oct 1921 ...")
    n_restored = 0
    n_values_restored = 0

    with dss_io.open_dss(BASELINE_DSS) as dss_base, \
         dss_io.open_dss(N10_FIXED) as dss_out:

        for i, pathname in enumerate(sorted(paths_1920)):
            # Read baseline decade block
            try:
                ts_base = dss_base.read_ts(pathname, trim_missing=False)
            except Exception as e:
                print(f"  WARNING: Could not read baseline {pathname}: {e}")
                continue

            # Read the same block from the n10 copy
            try:
                ts_n10 = dss_out.read_ts(pathname, trim_missing=False)
            except Exception as e:
                print(f"  WARNING: Could not read n10 {pathname}: {e}")
                continue

            base_vals = np.array(ts_base.values, dtype=float)
            n10_vals  = np.array(ts_n10.values, dtype=float)
            eom_dates = dss_eom(ts_n10.pytimes)

            # Build merged array: baseline for <= cutoff, n10 for > cutoff
            merged = n10_vals.copy()
            n_replaced = 0
            for j in range(len(merged)):
                if eom_dates[j] <= CUTOFF:
                    merged[j] = base_vals[j]
                    n_replaced += 1

            if n_replaced > 0:
                tsc = TimeSeriesContainer()
                tsc.pathname      = pathname
                tsc.startDateTime = ts_n10.pytimes[0].strftime("%d%b%Y %H:%M")
                tsc.numberValues  = len(merged)
                tsc.units         = ts_n10.units
                tsc.type          = ts_n10.type
                tsc.interval      = ts_n10.interval
                tsc.values        = merged
                safe_write_ts(dss_out, pathname, tsc)
                n_restored += 1
                n_values_restored += n_replaced

            if (i + 1) % 100 == 0:
                print(f"  Processed {i+1}/{len(paths_1920)} paths ...")

    print()
    print("=" * 60)
    print(f"  Records modified:    {n_restored:,}")
    print(f"  Values restored:     {n_values_restored:,}")
    print(f"  Output file:         {N10_FIXED}")
    print(f"  Elapsed:             {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
