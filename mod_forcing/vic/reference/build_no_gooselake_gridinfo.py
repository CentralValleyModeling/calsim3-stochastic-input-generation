"""
Build no-Goose-Lake GridInfo variants
=====================================
Derives ``*_no_gooselake_GridInfo.txt`` variants by eliminating grid cells that
fall outside the authoritative drainage in the CalSim3 watershed layer. Two
targets:

- ``I_SHSTA``  CS3_I_SHSTA_GridInfo.txt  -> CS3_I_SHSTA_no_gooselake_GridInfo.txt
              mask = the "Inflow to Shasta Lake" polygon (Connect_No SHSTA).
- ``SRBB``     CS3_8RI_SRBB_GridInfo.txt -> CS3_8RI_SRBB_no_gooselake_GridInfo.txt
              mask = SHSTA inflow + all CT_BENDBRIDGE pieces (rim tribs + valley).

Why
---
The Shasta-inflow delineation (CS3_I_SHSTA) was rasterized to extend ~1000 sq mi
into the endorheic Goose Lake basin on the California/Oregon border. The CalSim3
layer's authoritative SHSTA polygon (6588 sq mi) excludes Goose Lake, which
spills to the Pit River only in rare wet sequences and is not part of the routed
Shasta / Bend Bridge inflow. So both CS3_I_SHSTA and the CS3_8RI_SRBB composite
(which contains the Shasta cells) carry 94 Goose Lake cells (~1000 sq mi) that
drain nowhere relevant.

What it does
------------
For each target, drop every cell whose 1/16-degree footprint does not touch the
authoritative mask -- i.e. cells lying entirely outside the reference (the Goose
Lake block). Cells that straddle the divide keep their f1/f2 unchanged; only
cells fully outside are eliminated, matching "eliminate grids outside the
reference". Kept cells retain their exact id/lat/lon/f1/f2 from the source, so
the non-Goose portion is byte-identical to the parent.

Outputs go to GridInfo/, so _2_compile_rim_inflows.py routes them like any other
watershed (CS3_I_SHSTA_no_gooselake_qmo.csv, CS3_8RI_SRBB_no_gooselake_qmo.csv).

Run the SRBB target after build_8RI_SRBB_gridinfo.py (it reads that output). Like
the valley generator, this needs geopandas and runs under a GIS env, not
csstochastic.

Usage
-----
    # gpkg defaults to <data_dir>/BASE/CalSim3/calsim3.gpkg (resolved from config.json)
    python mod_forcing/vic/reference/build_no_gooselake_gridinfo.py            # both targets
    python mod_forcing/vic/reference/build_no_gooselake_gridinfo.py --target I_SHSTA
    python mod_forcing/vic/reference/build_no_gooselake_gridinfo.py --gpkg /path/to/calsim3.gpkg
"""

import argparse
import json
import os

import geopandas as gpd
from shapely.geometry import box

HERE = os.path.dirname(os.path.abspath(__file__))
GI = os.path.join(HERE, "GridInfo")
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
GPKG_LAYER = "CalSim3_And_GooseLake"

RES = 0.0625
KM2_PER_SQMI = 2.589988

# Each target: source GridInfo, output GridInfo, and the gpkg rows whose union is
# the authoritative drainage (cells outside it are eliminated).
TARGETS = {
    "I_SHSTA": {
        "source": "CS3_I_SHSTA_GridInfo.txt",
        "output": "CS3_I_SHSTA_no_gooselake_GridInfo.txt",
        "mask": lambda g: g[g["Connect_No"] == "SHSTA"],
        "label": "Shasta inflow component",
    },
    "SRBB": {
        "source": "CS3_8RI_SRBB_GridInfo.txt",
        "output": "CS3_8RI_SRBB_no_gooselake_GridInfo.txt",
        "mask": lambda g: g[(g["Connect_No"] == "SHSTA") | (g["CT_Name"] == "CT_BENDBRIDGE")],
        "label": "Bend Bridge composite",
    },
}


def default_gpkg():
    """Resolve ``<data_dir>/BASE/CalSim3/calsim3.gpkg`` from config.json (falling
    back to config_default.json), mirroring ``utils.paths`` without importing it
    (that module requires the csstochastic env; this runs under a GIS env)."""
    cfg = os.path.join(REPO_ROOT, "config.json")
    if not os.path.exists(cfg):
        cfg = os.path.join(REPO_ROOT, "config_default.json")
    with open(cfg) as fh:
        data_dir = json.load(fh)["data_dir"]
    if not os.path.isabs(data_dir):
        data_dir = os.path.normpath(os.path.join(REPO_ROOT, data_dir))
    return os.path.join(data_dir, "BASE", "CalSim3", "calsim3.gpkg")


def build_target(name, layer):
    spec = TARGETS[name]
    source_path = os.path.join(GI, spec["source"])
    output_path = os.path.join(GI, spec["output"])
    if not os.path.exists(source_path):
        raise FileNotFoundError(
            f"Missing source GridInfo: {source_path}\n"
            f"Build it first (e.g. python build_8RI_SRBB_gridinfo.py for the SRBB target).")

    mask_sel = spec["mask"](layer)
    if mask_sel.empty:
        raise ValueError(f"No mask polygons found for target {name} in the gpkg.")
    mask = mask_sel.union_all()  # EPSG:4326, same CRS as the cell footprints below

    kept, dropped_area, n_src = [], 0.0, 0
    with open(source_path) as fh:
        for line in fh:
            if not line.strip():
                continue
            n_src += 1
            _cid, lat, lon, _f1, f2 = line.rstrip("\n").split("\t")
            la, lo = float(lat), float(lon)
            footprint = box(lo - RES / 2, la - RES / 2, lo + RES / 2, la + RES / 2)
            if mask.intersects(footprint):
                kept.append(line if line.endswith("\n") else line + "\n")
            else:
                dropped_area += float(f2)

    with open(output_path, "w", newline="") as fh:
        fh.writelines(kept)

    print(f"[{name}] wrote {os.path.basename(output_path)} ({spec['label']})")
    print(f"  kept {len(kept)} of {n_src} cells; "
          f"eliminated {n_src - len(kept)} Goose Lake cells "
          f"({dropped_area / KM2_PER_SQMI:.1f} sq mi)")


def main():
    ap = argparse.ArgumentParser(description="Build no-Goose-Lake GridInfo variants.")
    ap.add_argument("--target", choices=list(TARGETS) + ["all"], default="all",
                    help="Which variant(s) to build (default: all).")
    ap.add_argument("--gpkg", default=default_gpkg(),
                    help="Path to calsim3.gpkg (default: <data_dir>/BASE/CalSim3/calsim3.gpkg).")
    args = ap.parse_args()

    layer = gpd.read_file(args.gpkg, layer=GPKG_LAYER)
    names = list(TARGETS) if args.target == "all" else [args.target]
    for name in names:
        build_target(name, layer)


if __name__ == "__main__":
    main()
