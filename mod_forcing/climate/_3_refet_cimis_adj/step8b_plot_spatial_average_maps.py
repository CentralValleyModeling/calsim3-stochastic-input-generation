# -*- coding: utf-8 -*-
"""Map Step 8 monthly ETo averages for WBAs, subregions, and watersheds."""

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

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import geopandas as gpd
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_base_dir, get_module_generated_dir

script_dir = pathlib.Path(__file__).parent.resolve()
base_dir = get_base_dir()
gen_dir = get_module_generated_dir("mod_forcing/climate")
REFERENCE_DIR = script_dir.parent / "reference"
STEP8_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step8"
PLOT_OUTPUT_DIR = STEP8_DIR / "plots"


def _find_network_dir():
    network_dir = REFERENCE_DIR
    if not (network_dir / "CS3_WBAs.geojson").is_file():
        raise FileNotFoundError(f"Climate reference boundary inputs not found in: {network_dir}")
    return network_dir


def _find_california_boundary():
    boundary_file = REFERENCE_DIR / "CA_StateBoundary.shp"
    return boundary_file if boundary_file.is_file() else None


def load_wba_boundary():
    return gpd.read_file(_find_network_dir() / "CS3_WBAs.geojson").to_crs("EPSG:4326")


def load_california_boundary(wba_boundary=None):
    boundary_path = _find_california_boundary()
    if boundary_path is not None:
        try:
            boundary = gpd.read_file(boundary_path)
            if boundary.crs is None:
                return boundary.set_crs("EPSG:4326")
            return boundary.to_crs("EPSG:4326")
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


BOUNDARY_DIR = _find_network_dir()

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PERIOD_LABEL = "2004-2018"

GROUPS = {
    "WBA": {
        "csv": STEP8_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_WBA.csv",
        "geojson": BOUNDARY_DIR / "CS3_WBAs.geojson",
        "join_column": "WBA_ID",
        "output_dir": PLOT_OUTPUT_DIR / "maps_FixedScaleBar" / "WBA",
        "monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_VariableScaleBar" / "WBA",
        "california_output_dir": PLOT_OUTPUT_DIR / "maps_Statewide_FixedScaleBar" / "WBA",
        "california_monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_Statewide_VariableScaleBar" / "WBA",
        "title": "Water Budget Area",
        "id_transform": lambda value: str(value),
        "focus": True,
    },
    "SR": {
        "csv": STEP8_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SR.csv",
        "geojson": BOUNDARY_DIR / "C2vsim_subregions.geojson",
        "join_column": "Subregion_",
        "output_dir": PLOT_OUTPUT_DIR / "maps_FixedScaleBar" / "SR",
        "monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_VariableScaleBar" / "SR",
        "california_output_dir": PLOT_OUTPUT_DIR / "maps_Statewide_FixedScaleBar" / "SR",
        "california_monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_Statewide_VariableScaleBar" / "SR",
        "title": "Subregion",
        "id_transform": lambda value: int(float(str(value).replace("SR_", ""))),
        "focus": False,
    },
    "SW": {
        "csv": STEP8_DIR / "Historical_Unsplit (Product_A)_Spatial_Average_ETo_F1corrected_monthly_averaged_per_SW.csv",
        "geojson": BOUNDARY_DIR / "SmallWatersheds.geojson",
        "join_column": "SW_ID",
        "output_dir": PLOT_OUTPUT_DIR / "maps_FixedScaleBar" / "SW",
        "monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_VariableScaleBar" / "SW",
        "california_output_dir": PLOT_OUTPUT_DIR / "maps_Statewide_FixedScaleBar" / "SW",
        "california_monthly_scale_dir": PLOT_OUTPUT_DIR / "maps_Statewide_VariableScaleBar" / "SW",
        "title": "Small Watershed",
        "id_transform": lambda value: str(value).replace("SW_", "", 1),
        "focus": False,
    },
}


def plot_group(name, config):
    values = pd.read_csv(config["csv"])
    boundaries = gpd.read_file(config["geojson"])
    wba_boundary = load_wba_boundary()
    california = load_california_boundary(wba_boundary)
    boundaries["_join_id"] = boundaries[config["join_column"]].map(
        lambda value: config["id_transform"](value)
    )
    values["_join_id"] = values[values.columns[0]].map(config["id_transform"])
    joined = boundaries.merge(values, on="_join_id", how="left")
    joined["geometry"] = joined.geometry.intersection(
        california.geometry.unary_union
    )
    mapped = joined.dropna(subset=MONTHS).copy()

    missing = joined[MONTHS].isna().all(axis=1).sum()
    if missing:
        print(f"{name}: {missing} polygons had no matching Step 8 values")

    output_dir = config["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    vmin = float(mapped[MONTHS].min().min())
    vmax = float(mapped[MONTHS].max().max())

    def draw_one(ax, month, month_vmin=vmin, month_vmax=vmax):
        draw_study_background(ax, california)
        mapped.plot(
            ax=ax, column=month, cmap="YlOrRd", vmin=month_vmin, vmax=month_vmax,
            edgecolor="#334155", linewidth=0.28,
        )
        boundaries.boundary.plot(ax=ax, color="#334155", linewidth=0.28, zorder=5)
        if name in ("SR", "SW"):
            minx, miny, maxx, maxy = mapped.total_bounds
            dx, dy = (maxx - minx) * 0.04, (maxy - miny) * 0.04
            ax.set_xlim(minx - dx, maxx + dx)
            ax.set_ylim(miny - dy, maxy + dy)
        elif config["focus"]:
            minx, miny, maxx, maxy = wba_boundary.total_bounds
            dx, dy = (maxx - minx) * 0.04, (maxy - miny) * 0.04
            ax.set_xlim(minx - dx, maxx + dx)
            ax.set_ylim(miny - dy, maxy + dy)
        else:
            ax.set_xlim(*california.total_bounds[[0, 2]])
            ax.set_ylim(*california.total_bounds[[1, 3]])
        apply_map_frame(ax)
        ax.set_title(month, fontsize=9, fontweight="bold", pad=3)
        ax.tick_params(labelbottom=True, labelleft=True, labelsize=8, length=2)
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude", fontsize=9)

    for month in MONTHS:
        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor="#F8FAFC")
        draw_one(ax, month)
        ax.set_title(f"{month} {config['title']} ETo\nHistorical_Unsplit (Product_A) F1-corrected | {PERIOD_LABEL} | inches/month",
                     fontsize=11, fontweight="bold", pad=8)
        sm = plt.cm.ScalarMappable(cmap="YlOrRd", norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        colorbar = fig.colorbar(sm, ax=ax, orientation="vertical", pad=0.02, shrink=0.65)
        colorbar.set_label("inches/month", fontsize=9)
        output_file = output_dir / f"{name}_{month}.png"
        with open(str(output_file), "wb") as f_out:
            fig.savefig(f_out, dpi=180, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)

    monthly_dir = config["monthly_scale_dir"]
    monthly_dir.mkdir(parents=True, exist_ok=True)
    for month in MONTHS:
        month_vmin = float(mapped[month].min())
        month_vmax = float(mapped[month].max())
        if month_vmin == month_vmax:
            month_vmax = month_vmin + 1e-9
        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor="#F8FAFC")
        draw_one(ax, month, month_vmin, month_vmax)
        ax.set_title(f"{month} {config['title']} ETo\nHistorical_Unsplit (Product_A) F1-corrected | {PERIOD_LABEL} | inches/month",
                     fontsize=11, fontweight="bold", pad=8)
        sm = plt.cm.ScalarMappable(
            cmap="YlOrRd", norm=plt.Normalize(vmin=month_vmin, vmax=month_vmax)
        )
        sm.set_array([])
        colorbar = fig.colorbar(sm, ax=ax, orientation="vertical", pad=0.02, shrink=0.65)
        colorbar.set_label(f"inches/month ({month} scale)", fontsize=9)
        output_file = monthly_dir / f"{name}_{month}.png"
        with open(str(output_file), "wb") as f_out:
            fig.savefig(f_out, dpi=180, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)
    print(f"Maps saved under: {PLOT_OUTPUT_DIR}")

    print(f"{name}: monthly-scale maps saved to {monthly_dir}")

    print(f"{name}: {len(values)} values mapped to {len(joined)} polygons")


def main():
    for name, config in GROUPS.items():
        plot_group(name, config)
        california_config = config.copy()
        california_config["output_dir"] = config["california_output_dir"]
        california_config["monthly_scale_dir"] = config["california_monthly_scale_dir"]
        california_config["focus"] = False
        plot_group(f"{name}_California", california_config)
    print(f"Maps saved under: {PLOT_OUTPUT_DIR}")


if __name__ == "__main__":
    main()