"""
Build the CS3_8RI_SRBB Composite GridInfo (rim + valley floor)
==============================================================
One-off generator for ``GridInfo/CS3_8RI_SRBB_GridInfo.txt``, the grid-weight
file that lets ``_2_compile_rim_inflows.py`` route the Sacramento River at Bend
Bridge (CalSim node SAC257, anchor for UNIMP_SRBB) directly -- the same way any
other rim point is routed -- instead of summing pre-routed component series
afterward.

The Shasta-only routing (CS3_I_SHSTA) stops at the dam and under-represents Bend
Bridge by roughly 30 percent. Bend Bridge drains Shasta inflow plus everything
the CalSim 3 domain GIS tags as draining to it (CT_Name == "CT_BENDBRIDGE"):
the seven rim tributaries (Type == "Rim") AND the valley floor between them and
the gauge (Type == "Valley", the WBA 02 and WBA 03 watersheds, ~682 sq mi).

This single script does both halves of the build:

1. Merge the eight rim component GridInfo files: each unique grid cell appears
   once, with f2 (area-within-basin) summed across the sub-basins that share it
   and f1 (full cell area) kept at full precision.
2. Rasterize the CT_BENDBRIDGE valley-floor polygons from the CalSim3 watershed
   gpkg onto the 1/16-degree VIC grid and merge them in: existing rim cells keep
   their rim f1 and gain the valley area (capped at f1 on write), and valley-only
   cells are added with their own f1/id.

The valley rasterization (formerly the separate build_valley_bendbridge_gridinfo.py)
is now inlined here so there is a single 8RI_SRBB build. Because of step 2 this
script now needs geopandas/pyproj and must run under a GIS env (e.g. sacsma), not
the csstochastic pipeline env.

Valley rasterization detail
---------------------------
Per cell, in California Albers (EPSG:3310, equal-area), compute f1 = full cell
area and f2 = area of the cell within the dissolved valley, both in km^2 -- the
same units as every committed GridInfo file (a 1/16-degree cell at 42.4N is
35.69 km^2). The dissolved valley reproduces the gpkg WBA 02+03 total (681.8 vs
682.0 sq mi), and the rim component files already reproduce their gpkg per-basin
SQ_MI to within 0.1 sq mi, so both halves are rasterized consistently.

The GridInfo ``id`` is a legacy GIS raster index the runtime is indifferent to --
``_2_compile_rim_inflows.py`` matches cells to VIC flux files by lat/lon, never by
id. Valley cells that already appear in a committed GridInfo keep their canonical
id and f1; valley-only cells (outside every existing rim delineation) get a
computed f1 and a synthetic id in a reserved block (>= VALLEY_ID_BASE),
collision-free and informational only.

Routing the merged GridInfo reproduces the old sum-of-series aggregate to within
~0.04 percent of annual volume; the small residual is the global (vs per-basin)
area normalization in compile_rim_inflows.compute_runoff, and is the physically
consistent result since every cell is now weighted once against the whole basin.

This is a build-time artifact generator, not part of the runtime pipeline. Run
it only if the component delineations change; the committed
CS3_8RI_SRBB_GridInfo.txt is what the pipeline actually consumes.

Usage
-----
    # gpkg defaults to <data_dir>/BASE/CalSim3/calsim3.gpkg (resolved from config.json)
    python mod_forcing/vic/reference/build_8RI_SRBB_gridinfo.py
    python mod_forcing/vic/reference/build_8RI_SRBB_gridinfo.py --gpkg /path/to/calsim3.gpkg
"""

import argparse
import glob
import json
import math
import os
from collections import Counter, OrderedDict

import geopandas as gpd
from shapely.geometry import box

HERE = os.path.dirname(os.path.abspath(__file__))
GI = os.path.join(HERE, "GridInfo")
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir, os.pardir, os.pardir))
GPKG_LAYER = "CalSim3_And_GooseLake"
OUTPUT_NAME = "CS3_8RI_SRBB_GridInfo.txt"

# Bend Bridge (SAC257) rim components: Shasta inflow + above-SAC257 tributaries.
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

RES = 0.0625                 # VIC grid resolution (degrees)
AREA_EPSG = 3310             # California Albers (meters); equal-area, km^2 via /1e6
KM2_PER_SQMI = 2.589988
VALLEY_ID_BASE = 900001      # reserved synthetic-id block for valley-only cells
MIN_CELL_KM2 = 1e-6          # ignore slivers


def default_gpkg():
    """Resolve ``<data_dir>/BASE/CalSim3/calsim3.gpkg`` from config.json (falling
    back to config_default.json), mirroring ``utils.paths`` without importing it:
    that module calls ``require_env()`` for the csstochastic pipeline env, but
    this generator runs under a GIS env (geopandas), so we read the config here."""
    cfg = os.path.join(REPO_ROOT, "config.json")
    if not os.path.exists(cfg):
        cfg = os.path.join(REPO_ROOT, "config_default.json")
    with open(cfg) as fh:
        data_dir = json.load(fh)["data_dir"]
    if not os.path.isabs(data_dir):
        data_dir = os.path.normpath(os.path.join(REPO_ROOT, data_dir))
    return os.path.join(data_dir, "BASE", "CalSim3", "calsim3.gpkg")


def _load_known():
    """Canonical (lat, lon) -> id and -> most-precise f1 string, gathered from
    every committed component GridInfo (the composite CS3_8RI_SRBB file is skipped
    so stale output never feeds back in). Lets valley cells that coincide with an
    existing rim cell reuse its canonical id/f1."""
    known_id, known_f1 = {}, {}
    for path in glob.glob(os.path.join(GI, "CS3_*_GridInfo.txt")):
        if os.path.basename(path) == OUTPUT_NAME:
            continue
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                cid, lat, lon, f1, _f2 = line.rstrip("\n").split("\t")
                key = (round(float(lat), 5), round(float(lon), 5))
                known_id[key] = int(cid)
                if key not in known_f1 or len(f1) > len(known_f1[key]):
                    known_f1[key] = f1
    return known_id, known_f1


def _grid_centers(lo, hi):
    """1/16-degree cell-center coordinates (aligned to the VIC grid, fractional
    part .03125) spanning [lo, hi]."""
    start = math.floor((lo - 0.03125) / RES) * RES + 0.03125
    out, x = [], start
    while x < hi + RES:
        out.append(round(x, 5))
        x += RES
    return out


def compute_valley_cells(gpkg_path):
    """Rasterize the CT_BENDBRIDGE Type=Valley polygons (WBA 02/03) onto the
    1/16-degree grid, returning [{id, lat, lon, f1, f2, canonical}, ...] sorted by
    (-lat, lon). f1/f2 are km^2; valley-only cells get computed f1 and synthetic
    ids (>= VALLEY_ID_BASE). (Formerly build_valley_bendbridge_gridinfo.py.)"""
    known_id, known_f1 = _load_known()

    valley = gpd.read_file(gpkg_path, layer=GPKG_LAYER)
    sel = valley[(valley["CT_Name"] == "CT_BENDBRIDGE") & (valley["Type"] == "Valley")]
    if sel.empty:
        raise ValueError("No CT_BENDBRIDGE Type=Valley polygons found in " + gpkg_path)
    diss_geo = sel.union_all()                      # EPSG:4326, for the overlap test
    diss_area = sel.to_crs(AREA_EPSG).union_all()   # EPSG:3310, for areas
    minx, miny, maxx, maxy = diss_geo.bounds

    # Candidate cells: every 1/16-deg cell whose footprint touches the valley.
    cand = [(la, lo)
            for la in _grid_centers(miny, maxy)
            for lo in _grid_centers(minx, maxx)
            if box(lo - RES / 2, la - RES / 2, lo + RES / 2, la + RES / 2).intersects(diss_geo)]

    # Reproject all candidate cell boxes to the equal-area CRS at once.
    boxes = gpd.GeoSeries(
        [box(lo - RES / 2, la - RES / 2, lo + RES / 2, la + RES / 2) for la, lo in cand],
        crs=4326,
    ).to_crs(AREA_EPSG)

    rows, derived = [], 0
    for (la, lo), cell in zip(cand, boxes):
        inter_km2 = cell.intersection(diss_area).area / 1e6
        if inter_km2 <= MIN_CELL_KM2:
            continue
        key = (la, lo)
        f1_str = known_f1[key] if key in known_f1 else f"{cell.area / 1e6:.2f}"
        f2 = min(inter_km2, float(f1_str))
        if key in known_id:
            cid = known_id[key]
        else:
            cid = VALLEY_ID_BASE + derived
            derived += 1
        rows.append({"id": cid, "lat": la, "lon": lo, "f1": f1_str, "f2": f2,
                     "canonical": key in known_id})

    # Sanity: ids unique (canonical by construction; synthetic ones occupy a
    # reserved block that cannot collide with legacy ids).
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        raise AssertionError(f"Duplicate valley cell ids produced: {dupes}")

    rows.sort(key=lambda r: (-r["lat"], r["lon"]))
    return rows


def build(gpkg_path=None):
    gpkg_path = gpkg_path or default_gpkg()

    # --- 1. Merge the eight rim component GridInfo files. ---
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

    # --- 2. Rasterize the valley floor and merge it. A valley cell only ever
    # contributes f2: cells shared with a rim component keep that component's f1
    # and just accumulate the valley area; valley-only cells are added with their
    # own f1/id. The f2 cap at write time keeps boundary cells <= full cell area.
    valley_rows = compute_valley_cells(gpkg_path)
    n_valley, n_valley_new = len(valley_rows), 0
    for r in valley_rows:
        key = (f"{r['lat']:.5f}", f"{r['lon']:.5f}")
        if key in cells:
            cells[key]["f2"] += float(r["f2"])
        else:
            cells[key] = {"id": str(r["id"]), "lat": key[0], "lon": key[1],
                          "f1": r["f1"], "f2": float(r["f2"])}
            n_valley_new += 1

    # --- 3. Write the composite. ---
    out = os.path.join(GI, OUTPUT_NAME)
    with open(out, "w", newline="") as fh:
        for rec in cells.values():
            # guard against GIS rounding pushing summed area past the full cell
            f2 = min(rec["f2"], float(rec["f1"]))
            fh.write(f"{rec['id']}\t{rec['lat']}\t{rec['lon']}\t{rec['f1']}\t{f2!r}\n")

    valley_total = sum(r["f2"] for r in valley_rows)
    print(f"Wrote {out} ({len(cells)} unique cells from {len(COMPONENTS)} rim "
          f"components + valley floor [{n_valley} cells, {n_valley_new} valley-only, "
          f"{valley_total / KM2_PER_SQMI:.1f} sq mi])")


def main():
    ap = argparse.ArgumentParser(description="Build the CS3_8RI_SRBB composite GridInfo (rim + valley floor).")
    ap.add_argument("--gpkg", default=default_gpkg(),
                    help="Path to calsim3.gpkg (default: <data_dir>/BASE/CalSim3/calsim3.gpkg).")
    args = ap.parse_args()
    build(args.gpkg)


if __name__ == "__main__":
    main()
