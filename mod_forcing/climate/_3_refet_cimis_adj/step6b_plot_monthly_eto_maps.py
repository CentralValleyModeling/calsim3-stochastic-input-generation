# -*- coding: utf-8 -*-
"""
Visualize monthly average CIMIS ETo on the Historical_Unsplit (Product_A) grid.
Usage:  python plot_monthly_eto_maps.py
Input: annual Step 6 CSVs from the configured OneDrive CIMIS folder.
Output: maps in this step's local output/ folder.
"""
import sys

import matplotlib
matplotlib.use("Agg")

import os
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
import matplotlib.pyplot as plt
import geopandas as gpd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

# Set up paths
script_dir = pathlib.Path(__file__).parent.resolve()
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")


# ── paths ─────────────────────────────────────────────────────────────────────

MONTHS   = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
START_YEAR = 2004
END_YEAR = 2023
PERIOD_LABEL = f"{START_YEAR}-{END_YEAR}"
CIMIS_CSV_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step6" / "CIMIS_MonthlyAvg_ETo" 
#pathlib.Path(r"C:\Users\mbastani\OneDrive - California Department of Water Resources\Arnold, Wyatt@DWR's files - CalSim Synthetic Hydroclimate\calsim3-stochastic-input-generation\data\GENERATED\mod_forcing\climate\output\_3_refet_cimis_adj\CIMIS_MonthlyAvg_ETo")
PLOT_OUTPUT_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step6" / "plots"
OUT_WBA_DIR = PLOT_OUTPUT_DIR / "ETo_maps_WBA_FixedScaleBar"
OUT_WBA_MONTHLY_DIR = PLOT_OUTPUT_DIR / "ETo_maps_WBA_VariableScaleBar"
OUT_STATE_DIR = PLOT_OUTPUT_DIR / "ETo_maps_Statewide_FixedScaleBar"
OUT_STATE_MONTHLY_DIR = PLOT_OUTPUT_DIR / "ETo_maps_Statewide_VariableScaleBar"



#def _find_network_dir():
#    network_dir = pathlib.Path("..") / script_dir / "reference"
#    return network_dir
def _find_network_dir():
    return script_dir.parent / "reference"
    
#def _find_california_boundary():
#   CA_boundary = pathlib.Path("..") / script_dir / "reference"/ "CA_StateBoundary.shp"
#   return CA_boundary
def _find_california_boundary():
    boundary_file = script_dir.parent / "reference" / "CA_StateBoundary.shp"
    return boundary_file if boundary_file.is_file() else None

def load_wba_boundary():
    return gpd.read_file(_find_network_dir() / "CS3_WBAs.geojson").to_crs("EPSG:4326")

def load_california_boundary(wba_boundary=None):
    boundary_path = _find_california_boundary()
    if boundary_path is not None:
        try:
            gdf = gpd.read_file(boundary_path)
            if gdf.crs is None:
                gdf = gdf.set_crs("EPSG:4326")
            else:
                gdf = gdf.to_crs("EPSG:4326")
            return gdf
        except Exception as exc:
            print(f"[WARN] Failed to read California boundary shapefile: {exc}")
    if wba_boundary is None:
        wba_boundary = load_wba_boundary()
    print("[INFO] California boundary not found; using dissolved WBA footprint.")
    geom_union = (
        wba_boundary.geometry.union_all()
        if hasattr(wba_boundary.geometry, "union_all")
        else wba_boundary.geometry.unary_union
    )
    return gpd.GeoDataFrame(geometry=[geom_union], crs=wba_boundary.crs)


def draw_study_background(ax, california):
    ax.set_facecolor("#D1D5DB")
    california.plot(ax=ax, facecolor="#F8FAFC", edgecolor="none", zorder=0)


def apply_map_frame(ax):
    ax.set_axis_on()
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("black")
        spine.set_linewidth(1.2)


def points_inside(points, boundary, lon="Lon", lat="Lat"):
    geometry = gpd.points_from_xy(points[lon], points[lat], crs="EPSG:4326")
    geom_union = (
        boundary.geometry.union_all()
        if hasattr(boundary.geometry, "union_all")
        else boundary.geometry.unary_union
    )
    return points[geometry.within(geom_union)].copy()


def load_annual_cimis_averages():
    required_columns = ["lon", "lat", *MONTHS]
    annual_values = []
    grid_coordinates = None
    missing_paths = []

    for year in range(START_YEAR, END_YEAR + 1):
        csv_path = CIMIS_CSV_DIR / f"CIMIS_MonthlyAvg_ETo_mmperday_ProductA_grid_{year}.csv"
        if not csv_path.is_file():
            missing_paths.append(csv_path)
            continue

        annual_df = pd.read_csv(csv_path)
        missing_columns = [column for column in required_columns if column not in annual_df.columns]
        if missing_columns:
            raise ValueError(f"Missing columns {missing_columns} in Step 6 file:\n  {csv_path}")

        current_coordinates = annual_df[["lon", "lat"]].reset_index(drop=True)
        if grid_coordinates is None:
            grid_coordinates = current_coordinates
        elif not current_coordinates.equals(grid_coordinates):
            raise ValueError(f"Grid coordinates or order differ in Step 6 file:\n  {csv_path}")
        annual_values.append(annual_df[MONTHS].to_numpy(dtype=float))

    if missing_paths:
        missing_list = "\n  ".join(str(path) for path in missing_paths)
        raise FileNotFoundError(
            f"Missing Step 6 annual CIMIS files for {START_YEAR}-{END_YEAR}:\n  {missing_list}\n"
            "Make the OneDrive files available locally or sync them, then rerun this script."
        )

    values = np.stack(annual_values, axis=0)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).sum(axis=0)
    counts = valid.sum(axis=0)
    averages = np.full(totals.shape, np.nan, dtype=float)
    np.divide(totals, counts, out=averages, where=counts > 0)

    df_monthly = grid_coordinates.rename(columns={"lon": "Lon", "lat": "Lat"}).copy()
    for month_index, month in enumerate(MONTHS):
        df_monthly[month] = averages[:, month_index]
    print(f"Loaded {len(annual_values)} annual CIMIS files ({START_YEAR}-{END_YEAR}) from:\n  {CIMIS_CSV_DIR}")
    print(f"Averaged {len(df_monthly):,} grid cells")
    return df_monthly

# ── load data ─────────────────────────────────────────────────────────────────
df = load_annual_cimis_averages()

# ── load boundaries once ──────────────────────────────────────────────────────
wba_boundary = load_wba_boundary()
state_boundary = load_california_boundary(wba_boundary)


def save_map_set(points, focus_boundary, output_dir, variable_scale=False):
    """Save monthly maps using the Step 7 figure style."""
    output_dir.mkdir(parents=True, exist_ok=True)
    points = points_inside(points, focus_boundary)
    fixed_min = float(points[MONTHS].min().min())
    fixed_max = float(points[MONTHS].max().max())
    if fixed_min == fixed_max:
        fixed_max = fixed_min + 1e-9

    for month in MONTHS:
        month_points = points.dropna(subset=[month])
        if variable_scale:
            vmin = float(month_points[month].min())
            vmax = float(month_points[month].max())
            if vmin == vmax:
                vmax = vmin + 1e-9
        else:
            vmin, vmax = fixed_min, fixed_max

        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor="#F8FAFC")
        draw_study_background(ax, state_boundary)
        wba_boundary.boundary.plot(ax=ax, color="#475569", linewidth=0.55, zorder=3)
        scatter = ax.scatter(
            month_points["Lon"], month_points["Lat"], c=month_points[month],
            cmap="YlOrRd", vmin=vmin, vmax=vmax, s=3, alpha=0.9,
            linewidths=0, zorder=4,
        )
        minx, miny, maxx, maxy = focus_boundary.total_bounds
        dx, dy = (maxx - minx) * 0.04, (maxy - miny) * 0.04
        ax.set_xlim(minx - dx, maxx + dx)
        ax.set_ylim(miny - dy, maxy + dy)
        apply_map_frame(ax)

        scale_label = " | monthly scale" if variable_scale else ""
        ax.set_title(
            f"{month} Average CIMIS ETo (mm/day)\n"
            f"Historical_Unsplit (Product_A) grid | {PERIOD_LABEL}{scale_label}",
            fontsize=11, fontweight="bold", pad=8,
        )
        if not variable_scale:
            ax.tick_params(labelbottom=True, labelleft=True, labelsize=8)
            ax.set_xlabel("Longitude", fontsize=9)
            ax.set_ylabel("Latitude", fontsize=9)

        colorbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.02,
                                shrink=0.65)
        colorbar_label = f"ETo (mm/day, {month} scale)" if variable_scale else "ETo (mm/day)"
        colorbar.set_label(colorbar_label, fontsize=9)
        plt.tight_layout()
        output_path = output_dir / f"{month}_ETo_map.png"
        with open(str(output_path), "wb") as f_out:
            fig.savefig(f_out, dpi=180, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)
        print(f"  Saved {output_path}")


save_map_set(df, wba_boundary, OUT_WBA_DIR)
save_map_set(df, wba_boundary, OUT_WBA_MONTHLY_DIR, variable_scale=True)
save_map_set(df, state_boundary, OUT_STATE_DIR)
save_map_set(df, state_boundary, OUT_STATE_MONTHLY_DIR, variable_scale=True)
