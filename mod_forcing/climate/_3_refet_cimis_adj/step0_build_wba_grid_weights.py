# -*- coding: utf-8 -*-
"""
Step 0: Build WBA Grid-Cell Weight Files from Product A Grid
=============================================================
Project  : Reference ETo for CalSim3 using Product A weather data
Author   : DWR — adapted from Mohammad Hasan's PRISM-based workflow
Date     : 2026

PURPOSE
-------
This script computes, for each of the 42 CalSim3 Water Budget Areas (WBAs),
the fractional area contribution (percent[k]) of each Product A weather grid
cell to that WBA. These weight files are the direct replacement for the
WTable*.csv files that were originally generated with ArcPy.

The output files are consumed by step8_wba_spatial_average.py to produce
spatially-averaged monthly ETo per WBA.

BACKGROUND
----------
Product A weather data (Historical_Unsplit) uses a 1/16-degree (~6 km) regular
grid. Each file is named data_{lat}_{lon} and covers 1915-01-01 to 2018-12-31.
The grid cell represented by each file is a 0.0625° × 0.0625° square centered
on that lat/lon.

For each WBA polygon:
    percent[k] = (area of cell_k ∩ WBA) / (total WBA area) × 100

The percentages across all cells in one WBA sum to approximately 100%.

SPATIAL REFERENCE
-----------------
All area calculations are performed in California Albers Equal Area
(EPSG:3310) to ensure correct area weighting independent of latitude.
Input GeoJSON and lat/lon grid files are in WGS84 (EPSG:4326).

INPUTS
------
1. Boundary GeoJSON files (in mod_forcing/climate/reference/):
    CS3_WBAs.geojson          (42 WBA polygons, field: WBA_ID)
    C2vsim_subregions.geojson (21 SR polygons, field: Subregion_)
    SmallWatersheds.geojson   (SW polygons, field: SW_ID)

2. Product A grid cell directory (filenames encode lat/lon):
    BASE/WGEN/Historical_Unsplit/
    Example filename: data_38.03125_-121.46875

OUTPUTS
-------
CSV files per WBA / SR / SW in OUTPUT_DIR (GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step0):
    WTable_02.csv, WTable_03.csv, ..., WTable_DETAW.csv
    WTable_SR_*.csv
    WTable_SW_*.csv

Each file format (matches H-S_RefETo_PRISM_CIMIS_WBAs_SR_SW_SpatialAvg_Monthly.py):
    line 1: # comment
    line 2: # comment
    line 3: long[k],lati[k],percent[k]    ← column header (skiprows=2, header=0)
    line 4+: data rows

ENVIRONMENT SETUP (one-time)
-----------------------------
Using conda (recommended — handles GDAL/GEOS dependencies automatically):

    conda env create -f environment.yml
    conda activate eto_env

Or using pip (requires pre-installed system GDAL):

    pip install geopandas pandas numpy pyproj shapely fiona tqdm

To run:
    python step1_build_wba_grid_weights.py

VALIDATION
----------
After running, check that:
  - 42 WTable_*.csv files are created (one per WBA)
  - Each file's percent[k] column sums to ~100 (printed in console output)
  - Cell counts per WBA are reasonable (large WBAs like 25 → hundreds of cells)
"""

import os
import re
import sys
import pathlib
import warnings

# Configure PROJ database directory for pyproj/geopandas in Conda on Windows
_proj_dir = pathlib.Path(sys.prefix) / "Library" / "share" / "proj"
if _proj_dir.exists():
    os.environ["PROJ_DATA"] = str(_proj_dir)
    os.environ["PROJ_LIB"] = str(_proj_dir)
    try:
        import pyproj.datadir
        pyproj.datadir.set_data_dir(str(_proj_dir))
    except Exception:
        pass
warnings.filterwarnings("ignore", message="pyproj unable to set PROJ database path")

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

try:
    from tqdm import tqdm as _tqdm
    def progress(iterable, **kwargs):
        return _tqdm(list(iterable), **kwargs)
except ImportError:
    def progress(iterable, **kwargs):
        return list(iterable)


# =============================================================================
# CONFIGURATION — update paths here if data locations change
# =============================================================================

script_dir = pathlib.Path(__file__).parent.resolve()
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")

REFERENCE_DIR = script_dir.parent / "reference"
WBA_GEOJSON = REFERENCE_DIR / "CS3_WBAs.geojson"
SR_GEOJSON = REFERENCE_DIR / "C2vsim_subregions.geojson"
SW_GEOJSON = REFERENCE_DIR / "SmallWatersheds.geojson"

GRID_DATA_DIR = base_dir / "WGEN" / "Historical_Unsplit"

OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step0"

CRS_GEO  = "EPSG:4326"   # WGS84 geographic (input)
CRS_AREA = "EPSG:3310"   # California Albers Equal Area (area calculations)

HALF_CELL   = 0.03125    # half the 1/16-degree cell width
WBA_ID_FIELD = "WBA_ID"
SR_ID_FIELD  = "Subregion_"         # integer 1-21
SW_ID_FIELD  = "SW_ID"              # integer; null rows are skipped
MIN_PERCENT  = 0.01      # drop cells contributing less than 0.01% to a polygon

# =============================================================================


def parse_grid_cells(data_dir: pathlib.Path) -> gpd.GeoDataFrame:
    """Scan data_dir for data_{lat}_{lon} files and build a GeoDataFrame of cell squares."""
    pattern = re.compile(r"^data_([-\d.]+)_([-\d.]+)$")
    records = []
    for fname in os.listdir(data_dir):
        m = pattern.match(fname)
        if m:
            lat = float(m.group(1))
            lon = float(m.group(2))
            records.append({
                "lat": lat,
                "lon": lon,
                "geometry": box(lon - HALF_CELL, lat - HALF_CELL,
                                lon + HALF_CELL, lat + HALF_CELL),
            })
    if not records:
        raise FileNotFoundError(
            f"No data_{{lat}}_{{lon}} files found in:\n  {data_dir}"
        )
    gdf = gpd.GeoDataFrame(records, crs=CRS_GEO)
    print(f"  Found {len(gdf):,} grid cells")
    return gdf


def compute_weights(
    poly_gdf: gpd.GeoDataFrame,
    grid_gdf: gpd.GeoDataFrame,
    id_field: str,
    label: str = "polygon",
) -> dict:
    """
    For every polygon compute percent[k] for each overlapping grid cell.
    Returns dict: poly_id → DataFrame with columns [long[k], lati[k], percent[k]].
    """
    poly_proj = poly_gdf.to_crs(CRS_AREA)
    grid_proj = grid_gdf.to_crs(CRS_AREA)

    # Spatial index speeds up candidate lookup per polygon
    grid_sindex = grid_proj.sindex

    results = {}
    for _, poly_row in progress(poly_proj.iterrows(), desc=label, unit=label):
        poly_id   = str(poly_row[id_field])
        poly_geom = poly_row.geometry
        poly_area = poly_geom.area

        if poly_area == 0:
            print(f"  [WARN] {label} {poly_id} has zero area — skipped")
            continue

        # Candidate cells via spatial index (bounding-box pre-filter)
        candidate_idx = list(grid_sindex.intersection(poly_geom.bounds))
        candidates    = grid_proj.iloc[candidate_idx]

        rows = []
        for _, cell in candidates.iterrows():
            intersection = cell.geometry.intersection(poly_geom)
            if intersection.is_empty:
                continue
            pct = (intersection.area / poly_area) * 100.0
            if pct < MIN_PERCENT:
                continue
            rows.append({
                "long[k]":    round(cell["lon"], 7),
                "lati[k]":    round(cell["lat"], 7),
                "percent[k]": round(pct, 6),
            })

        if not rows:
            print(f"  [WARN] No grid cells intersect {label} {poly_id}")
            continue

        df        = pd.DataFrame(rows)
        total_pct = df["percent[k]"].sum()
        results[poly_id] = df
        print(f"  {label} {poly_id:>20s}: {len(df):4d} cells, coverage sum = {total_pct:.2f}%")

    return results


def write_wtable(poly_id: str, df: pd.DataFrame, output_dir: pathlib.Path, prefix: str = "") -> None:
    """Write WTable_{prefix}{poly_id}.csv in the two-comment-line format the reader expects."""
    out_path = output_dir / f"WTable_{prefix}{poly_id}.csv"
    with open(out_path, "w", newline="") as fh:
        fh.write(f"# {prefix}{poly_id} - Product A grid-cell fractional coverage weights\n")
        fh.write(f"# percent[k] = intersection_area / polygon_area * 100  (column sum ~ 100)\n")
        df.to_csv(fh, index=False)


def main():
    print("=" * 60)
    print("Step 0: Build WBA / SR / SW grid-cell weight files")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/4] Scanning grid cells in:\n  {GRID_DATA_DIR}")
    grid_gdf = parse_grid_cells(GRID_DATA_DIR)

    # --- WBAs (42) -------------------------------------------------------
    print(f"\n[2/4] WBAs -- loading from:\n  {WBA_GEOJSON}")
    wba_gdf = gpd.read_file(WBA_GEOJSON)[[WBA_ID_FIELD, "geometry"]]
    print(f"  Loaded {len(wba_gdf)} WBAs")
    wba_weights = compute_weights(wba_gdf, grid_gdf, id_field=WBA_ID_FIELD, label="WBA")
    for poly_id, df in sorted(wba_weights.items()):
        write_wtable(poly_id, df, OUTPUT_DIR, prefix="")
    print(f"  Written: {len(wba_weights)} WTable_*.csv")

    # --- Subregions / SR (21) --------------------------------------------
    print(f"\n[3/4] Subregions (SR) -- loading from:\n  {SR_GEOJSON}")
    sr_gdf = gpd.read_file(SR_GEOJSON)[[SR_ID_FIELD, "geometry"]]
    # Cast ID to string for consistent naming
    sr_gdf[SR_ID_FIELD] = sr_gdf[SR_ID_FIELD].astype(int).astype(str)
    print(f"  Loaded {len(sr_gdf)} subregions")
    sr_weights = compute_weights(sr_gdf, grid_gdf, id_field=SR_ID_FIELD, label="SR")
    for poly_id, df in sorted(sr_weights.items()):
        write_wtable(poly_id, df, OUTPUT_DIR, prefix="SR_")
    print(f"  Written: {len(sr_weights)} WTable_SR_*.csv")

    # --- Small Watersheds / SW --------------------------------------------
    print(f"\n[4/4] Small Watersheds (SW) -- loading from:\n  {SW_GEOJSON}")
    sw_gdf_all = gpd.read_file(SW_GEOJSON)[[SW_ID_FIELD, "geometry"]]
    # Keep only features with a non-blank SW_ID
    sw_gdf = sw_gdf_all[
        sw_gdf_all[SW_ID_FIELD].notna()
        & sw_gdf_all[SW_ID_FIELD].astype(str).str.strip().ne("")
    ].copy()
    sw_gdf[SW_ID_FIELD] = sw_gdf[SW_ID_FIELD].astype(str).str.strip()
    print(f"  Loaded {len(sw_gdf)} valid features ({len(sw_gdf_all)} total)")
    sw_weights = compute_weights(sw_gdf, grid_gdf, id_field=SW_ID_FIELD, label="SW")
    for poly_id, df in sorted(sw_weights.items()):
        write_wtable(poly_id, df, OUTPUT_DIR, prefix="SW_")
    print(f"  Written: {len(sw_weights)} WTable_SW_*.csv")

    # --- Summary ---------------------------------------------------------
    total = len(wba_weights) + len(sr_weights) + len(sw_weights)
    print(f"\n{'='*60}")
    print(f"Done. {total} WTable files written to:\n  {OUTPUT_DIR}")
    print(f"  WBAs : {len(wba_weights):3d}  (WTable_*.csv)")
    print(f"  SR   : {len(sr_weights):3d}  (WTable_SR_*.csv)")
    print(f"  SW   : {len(sw_weights):3d}  (WTable_SW_*.csv)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
