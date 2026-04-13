# %% Fix ProductB_SV_n10.dss -- restore baseline values through Oct 1921
"""Diagnose/fix n10 initial-timestep infeasibility at October 1921.

Infeasibility summary
---------------------
n10 -- 1921_10 (first simulation timestep) infeasible.
The specific SV value(s) causing the failure have not been identified.
One or more stochastic SV values at October 1921 differ from the baseline
in a way that makes the LP infeasible at initialization. Unlike the other
failure modes (low-flow, high-flow, low-storage), no single constraint or
variable has been pinpointed as the root cause.

Fix
---
Replace all SV values at and before October 1921 with historical baseline
values from __calsim_sv_default__.dss. This restores the initialization
state to the known-good baseline while preserving the stochastic sequence
for November 1921 through September 2021. The fix produces a new file
(ProductB_SV_n10_fixed.dss) without modifying the original.

Approach:
  1. Copy existing n10 DSS -> n10_fixed DSS
  2. For each monthly SV path in the 01JAN1920 decade block:
     a. Read that block from both baseline and the n10 copy
     b. Replace values for months <= Oct 1921 with baseline values
     c. Write the merged block back to the n10 copy
"""

import sys
import shutil
import subprocess
import atexit
import time
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

from pydsstools.heclib.dss import HecDss
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

# -- Junction helper (long OneDrive paths) ---------------------------------
_REPO_ROOT  = Path(__file__).resolve().parents[2]
_DSS_LINK   = _REPO_ROOT / "_dss_link"
_PATH_LIMIT = 200


def _create_junction(target_dir):
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(_DSS_LINK), str(target_dir)],
        check=True, capture_output=True,
    )


def _remove_junction():
    if _DSS_LINK.exists():
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)


def _get_dss_str(path, use_junction):
    if use_junction:
        return str(_DSS_LINK / path.name)
    return str(path)


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

    # Set up junction if paths are too long
    use_junction = len(str(N10_FIXED)) > _PATH_LIMIT
    if use_junction:
        _create_junction(COMPILED_DIR)
        atexit.register(_remove_junction)

    baseline_str = str(BASELINE_DSS)
    if len(baseline_str) > _PATH_LIMIT:
        # Use a junction for the baseline directory too
        _base_link = _REPO_ROOT / "_dss_link_base"
        if _base_link.exists():
            subprocess.run(["cmd", "/c", "rmdir", str(_base_link)], capture_output=True)
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(_base_link), str(BASELINE_DSS.parent)],
            check=True, capture_output=True,
        )
        baseline_str = str(_base_link / BASELINE_DSS.name)

        def _remove_base_junction():
            if _base_link.exists():
                subprocess.run(["cmd", "/c", "rmdir", str(_base_link)], capture_output=True)
        atexit.register(_remove_base_junction)

    fixed_str = _get_dss_str(N10_FIXED, use_junction)

    # Step 2: Find all 01JAN1920 decade paths in baseline (these contain Oct 1921)
    print("Step 2: Scanning baseline for 1920-decade paths ...")
    paths_1920 = []
    with HecDss.Open(baseline_str, version=6) as dss_base:
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

    with HecDss.Open(baseline_str, version=6) as dss_base, \
         HecDss.Open(fixed_str, version=6) as dss_out:

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

    if use_junction:
        _remove_junction()

    print()
    print("=" * 60)
    print(f"  Records modified:    {n_restored:,}")
    print(f"  Values restored:     {n_values_restored:,}")
    print(f"  Output file:         {N10_FIXED}")
    print(f"  Elapsed:             {time.time()-t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
