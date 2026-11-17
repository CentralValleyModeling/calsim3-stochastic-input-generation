"""
Build the CS3_8RI_SRBB Composite GridInfo (rim + valley floor)
==============================================================
Grid weights of the Sacramento River at Bend Bridge (CalSim node SAC257, anchor of UNIMP_SRBB):
the eight rim component GridInfo files merged with the CT_BENDBRIDGE valley floor (WBA 02 and
03) rasterized onto the 1/16-degree grid, and the valley floor alone.

Method
------
1. Merge the rim components (I_SHSTA, I_COW014, I_BTL006, I_BCN010, I_CLR011, I_WKYTN,
   I_CWD018, I_SCW008): each cell once, f2 (area inside the basin) summed over the components
   that share it, f1 (full cell area) at its most precise.
2. Rasterize the gpkg polygons with CT_Name == "CT_BENDBRIDGE" and Type == "Valley" in
   California Albers (EPSG:3310): f1 and f2 in km^2 per cell. Rim cells keep their f1 and gain
   the valley f2 (capped at f1). Valley cells found in another committed GridInfo keep its id
   and f1; valley-only cells get a computed f1 and a synthetic id from 900001
   (``VALLEY_ID_BASE``). Routing matches cells by lat/lon, so the id is informational.

Build-time only; run when the component delineations change.

Inputs
------
- reference/GridInfo/CS3_<component>_GridInfo.txt of the eight components, and every other
  CS3_*_GridInfo.txt there for canonical ids and f1
- calsim3.gpkg, layer CalSim3_And_GooseLake (--gpkg; default <data_dir>/BASE/CalSim3/calsim3.gpkg,
  data_dir read from config.json or config_default.json)

Outputs
-------
Tab-separated id, lat, lon, f1, f2:
- reference/GridInfo/CS3_8RI_SRBB_GridInfo.txt: rim plus valley floor
- reference/GridInfo/CS3_I_SRBB_VAL_GridInfo.txt: valley floor alone, the valley node
  I_SRBB_VAL of adapters/vic.py (UNIMP_SRBB is the 8 rim arcs plus this node)

Dependencies
------------
geopandas, shapely; a GIS environment (e.g. sacsma), not csstochastic. Does not import
utils.paths.

Usage
-----
    python mod_forcing/climate/reference/build_8RI_SRBB_gridinfo.py
    python mod_forcing/climate/reference/build_8RI_SRBB_gridinfo.py --gpkg /path/to/calsim3.gpkg
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
VALLEY_NAME = "CS3_I_SRBB_VAL_GridInfo.txt"

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
    every committed component GridInfo (this script's two outputs are skipped so
    stale output never feeds back in). Lets valley cells that coincide with an
    existing rim cell reuse its canonical id/f1."""
    known_id, known_f1 = {}, {}
    for path in glob.glob(os.path.join(GI, "CS3_*_GridInfo.txt")):
        if os.path.basename(path) in (OUTPUT_NAME, VALLEY_NAME):
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

    # --- 4. Write the valley floor alone (the valley node I_SRBB_VAL). ---
    out = os.path.join(GI, VALLEY_NAME)
    with open(out, "w", newline="") as fh:
        for r in valley_rows:
            fh.write(f"{r['id']}\t{r['lat']:.5f}\t{r['lon']:.5f}\t{r['f1']}\t{r['f2']!r}\n")
    print(f"Wrote {out} ({n_valley} cells, {valley_total / KM2_PER_SQMI:.1f} sq mi)")


def main():
    ap = argparse.ArgumentParser(description="Build the CS3_8RI_SRBB composite GridInfo (rim + valley floor).")
    ap.add_argument("--gpkg", default=default_gpkg(),
                    help="Path to calsim3.gpkg (default: <data_dir>/BASE/CalSim3/calsim3.gpkg).")
    args = ap.parse_args()
    build(args.gpkg)


if __name__ == "__main__":
    main()
