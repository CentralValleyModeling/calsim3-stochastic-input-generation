"""
Build no-Goose-Lake GridInfo Variants
=====================================
GridInfo variants of the Shasta inflow and the Bend Bridge composite without the cells outside
the drainage of the CalSim3 watershed layer: CS3_I_SHSTA reaches into the endorheic Goose Lake
basin, which is not part of the routed Shasta or Bend Bridge inflow.

Targets
-------
- I_SHSTA : CS3_I_SHSTA_GridInfo.txt to CS3_I_SHSTA_no_gooselake_GridInfo.txt; mask the
            Connect_No SHSTA polygon
- SRBB    : CS3_8RI_SRBB_GridInfo.txt to CS3_8RI_SRBB_no_gooselake_GridInfo.txt; mask SHSTA
            plus every CT_BENDBRIDGE polygon (rim tributaries and valley)

Per target, drops every cell whose 1/16-degree footprint does not touch the mask and clips the
f2 (basin area) of an edge cell to its area inside the mask (EPSG:3310); other lines are copied
unchanged. Build-time only.

Inputs
------
- reference/GridInfo/<source> above; build_8RI_SRBB_gridinfo.py writes the SRBB source
- calsim3.gpkg, layer CalSim3_And_GooseLake (--gpkg; default <data_dir>/BASE/CalSim3/calsim3.gpkg,
  data_dir read from config.json or config_default.json)

Outputs
-------
- reference/GridInfo/<output> above (tab-separated id, lat, lon, f1, f2); adapters/vic.py
  routes I_SHSTA through CS3_I_SHSTA_no_gooselake

Dependencies
------------
geopandas, shapely; a GIS environment (e.g. sacsma), not csstochastic. Does not import
utils.paths.

Usage
-----
    python mod_forcing/climate/reference/build_no_gooselake_gridinfo.py               # both targets
    python mod_forcing/climate/reference/build_no_gooselake_gridinfo.py --target I_SHSTA
    python mod_forcing/climate/reference/build_no_gooselake_gridinfo.py --target SRBB
    python mod_forcing/climate/reference/build_no_gooselake_gridinfo.py --gpkg /path/to/calsim3.gpkg
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
AREA_EPSG = 3310             # California Albers (meters); equal-area, km^2 via /1e6

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
    mask_area = mask_sel.to_crs(AREA_EPSG).union_all()

    with open(source_path) as fh:
        rows = [line.rstrip("\n").split("\t") for line in fh if line.strip()]
    footprints = [box(float(lo) - RES / 2, float(la) - RES / 2, float(lo) + RES / 2,
                      float(la) + RES / 2) for _cid, la, lo, _f1, _f2 in rows]
    inside_km2 = gpd.GeoSeries(footprints, crs=4326).to_crs(AREA_EPSG).intersection(mask_area).area / 1e6

    kept, dropped_area, clipped_area, n_clipped = [], 0.0, 0.0, 0
    for (cid, lat, lon, f1, f2), footprint, inside in zip(rows, footprints, inside_km2):
        if not mask.intersects(footprint):
            dropped_area += float(f2)
            continue
        if float(f2) > inside:
            clipped_area += float(f2) - inside
            n_clipped += 1
            f2 = repr(float(inside))
        kept.append(f"{cid}\t{lat}\t{lon}\t{f1}\t{f2}\n")

    with open(output_path, "w", newline="") as fh:
        fh.writelines(kept)

    print(f"[{name}] wrote {os.path.basename(output_path)} ({spec['label']})")
    print(f"  kept {len(kept)} of {len(rows)} cells; "
          f"eliminated {len(rows) - len(kept)} Goose Lake cells "
          f"({dropped_area / KM2_PER_SQMI:.1f} sq mi); clipped {n_clipped} edge cells to the "
          f"drainage ({clipped_area / KM2_PER_SQMI:.1f} sq mi)")


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
