"""
Build the CS3_8RI_SRBB Composite GridInfo
=========================================
One-off generator for ``GridInfo/CS3_8RI_SRBB_GridInfo.txt``, the grid-weight
file that lets ``_2_compile_rim_inflows.py`` route the Sacramento River at Bend
Bridge (CalSim node SAC257, anchor for UNIMP_SRBB) directly -- the same way any
other rim point is routed -- instead of summing pre-routed component series
afterward.

The Shasta-only routing (CS3_I_SHSTA) stops at the dam and under-represents Bend
Bridge by roughly 30 percent. Bend Bridge drains Shasta inflow plus the seven
tributaries the CalSim 3 domain GIS tags as draining above SAC257
(Incr_Drain == "Above SAC257"). This script merges those eight component
GridInfo files into one: each unique grid cell appears once, with f2
(area-within-basin) summed across the sub-basins that share it and f1
(full cell area) kept at full precision.

Routing the merged GridInfo reproduces the old sum-of-series aggregate to within
~0.04 percent of annual volume; the small residual is the global (vs per-basin)
area normalization in compile_rim_inflows.compute_runoff, and is the physically
consistent result since every cell is now weighted once against the whole basin.

This is a build-time artifact generator, not part of the runtime pipeline. Run
it only if the component delineations change; the committed
CS3_8RI_SRBB_GridInfo.txt is what the pipeline actually consumes.

Usage
-----
    python mod_forcing/vic/reference/build_8RI_SRBB_gridinfo.py
"""

import os
from collections import OrderedDict

GI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "GridInfo")

# Bend Bridge (SAC257) components: Shasta inflow + above-SAC257 tributaries.
COMPONENTS = [
    "I_SHSTA",   # Sacramento River inflow to Shasta Lake
    "I_COW014",  # Cow Creek
    "I_BTL006",  # Battle Creek
    "I_BCN010",  # Bear Creek
    "I_CLR011",  # Clear Creek below Whiskeytown
    "I_WKYTN",   # Clear Creek inflow to Whiskeytown
    "I_CWD018",  # Cottonwood Creek near Olinda
    "I_SCW008",  # South Fork Cottonwood Creek
]

OUTPUT_NAME = "CS3_8RI_SRBB_GridInfo.txt"


def build():
    cells = OrderedDict()  # (lat, lon) -> {id, lat, lon, f1, f2}
    for comp in COMPONENTS:
        path = os.path.join(GI, f"CS3_{comp}_GridInfo.txt")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing component GridInfo: {path}")
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                cid, lat, lon, f1, f2 = line.rstrip("\n").split("\t")
                key = (lat, lon)
                if key not in cells:
                    cells[key] = {"id": cid, "lat": lat, "lon": lon,
                                  "f1": f1, "f2": float(f2)}
                else:
                    rec = cells[key]
                    rec["f2"] += float(f2)
                    # keep the most precise full-cell area (longest decimal string)
                    if len(f1) > len(rec["f1"]):
                        rec["f1"] = f1

    out = os.path.join(GI, OUTPUT_NAME)
    with open(out, "w", newline="") as fh:
        for rec in cells.values():
            # guard against GIS rounding pushing summed area past the full cell
            f2 = min(rec["f2"], float(rec["f1"]))
            fh.write(f"{rec['id']}\t{rec['lat']}\t{rec['lon']}\t{rec['f1']}\t{f2!r}\n")

    print(f"Wrote {out} ({len(cells)} unique cells from {len(COMPONENTS)} components)")


if __name__ == "__main__":
    build()
