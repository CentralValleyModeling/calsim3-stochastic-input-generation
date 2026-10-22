# -*- coding: utf-8 -*-
"""Generate the Step 10 F1 and H-S monthly maps."""

import sys
import pathlib
import warnings

# Configure PROJ database directory for pyproj/geopandas in Conda on Windows
_proj_dir = pathlib.Path(sys.prefix) / "Library" / "share" / "proj"
if _proj_dir.exists():
    try:
        import pyproj.datadir
        pyproj.datadir.set_data_dir(str(_proj_dir))
    except Exception:
        pass
warnings.filterwarnings("ignore", message="pyproj unable to set PROJ database path")

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import geopandas as gpd

# Add repo root to path for utils imports
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir

script_dir = pathlib.Path(__file__).parent.resolve()
gen_dir = get_module_generated_dir("mod_forcing/climate")
REFERENCE_DIR = script_dir.parent / "reference"
STEP10_DIR = gen_dir / "output" / "_3_refet_cimis_adj" / "step10"
PLOT_OUTPUT_DIR = STEP10_DIR / "plots"


def _find_network_dir():
    if not (REFERENCE_DIR / "CS3_WBAs.geojson").is_file():
        raise FileNotFoundError(f"Step 0 WBA boundary not found: {REFERENCE_DIR / 'CS3_WBAs.geojson'}")
    return REFERENCE_DIR


def _find_california_boundary():
    boundary_file = REFERENCE_DIR / "CA_StateBoundary.shp"
    return boundary_file if boundary_file.is_file() else None


def load_wba_boundary():
    return gpd.read_file(_find_network_dir() / "CS3_WBAs.geojson").to_crs("EPSG:4326")


def load_california_boundary(wba_boundary=None):
    boundary_path = _find_california_boundary()
    if boundary_path is not None:
        boundary = gpd.read_file(boundary_path)
        if boundary.crs is None:
            return boundary.set_crs("EPSG:4326")
        return boundary.to_crs("EPSG:4326")
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


F1_CSV = STEP10_DIR / "Historical_Unsplit (Product_A)_F1_table.csv"
HS_CSV = STEP10_DIR / "Historical_Unsplit (Product_A)_HS_monthly_avg_mmperday.csv"
CORRECTED_CSV = STEP10_DIR / "Historical_Unsplit (Product_A)_ETo_F1corrected_monthly_inpermonth.csv"
F1_DIR = PLOT_OUTPUT_DIR / "F1_maps_WBA_FixedScaleBar"
F1_CA_DIR = PLOT_OUTPUT_DIR / "F1_maps_Statewide_FixedScaleBar"
F1_MONTHLY_DIR = PLOT_OUTPUT_DIR / "F1_maps_WBA_VariableScaleBar"
F1_CA_MONTHLY_DIR = PLOT_OUTPUT_DIR / "F1_maps_Statewide_VariableScaleBar"
HS_DIR = PLOT_OUTPUT_DIR / "HS_maps_WBA_FixedScaleBar"
HS_MONTHLY_DIR = PLOT_OUTPUT_DIR / "HS_maps_WBA_VariableScaleBar"
HS_CA_DIR = PLOT_OUTPUT_DIR / "HS_maps_Statewide_FixedScaleBar"
HS_CA_MONTHLY_DIR = PLOT_OUTPUT_DIR / "HS_maps_Statewide_VariableScaleBar"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PERIOD_LABELS = {
    "F1 adjustment factor": "Applied to ETo 1921-2018",
    "H-S monthly average ETo": "Averaged over 1921-2018",
}


def validate_full_period(corrected_csv):
    columns = pd.read_csv(corrected_csv, nrows=0).columns.tolist()
    data_columns = columns[2:]
    expected = [
        f"{month}-{year}"
        for year in range(1921, 2019)
        for month in MONTHS
    ]
    if data_columns != expected:
        first = data_columns[0] if data_columns else "<none>"
        last = data_columns[-1] if data_columns else "<none>"
        raise ValueError(
            "Step 10b corrected input must cover exactly Jan-1921 through "
            f"Dec-2018; found {first} through {last}"
        )


def draw_map_set(df, value_name, unit, output_dir, filename_prefix,
                 color_map, limits, focus_boundary=None,
                 save_monthly_grid=True):
    output_dir.mkdir(parents=True, exist_ok=True)
    boundaries = load_wba_boundary()
    california = load_california_boundary(boundaries)
    vmin, vmax = limits
    if focus_boundary is None:
        focus_boundary = boundaries
    df = points_inside(df, focus_boundary)
    period_label = PERIOD_LABELS[value_name]
    vmin = float(df[MONTHS].min().min())
    vmax = float(df[MONTHS].max().max())
    if vmin == vmax:
        vmax = vmin + 1e-9

    def draw_one(ax, month):
        points = df.dropna(subset=[month])
        draw_study_background(ax, california)
        boundaries.boundary.plot(ax=ax, color="#475569", linewidth=0.55, zorder=3)
        scatter = ax.scatter(
            points["Lon"], points["Lat"], c=points[month],
            cmap=color_map, vmin=vmin, vmax=vmax,
            s=3, alpha=0.9, linewidths=0, zorder=4,
        )
        if focus_boundary is None:
            ax.set_xlim(*california.total_bounds[[0, 2]])
            ax.set_ylim(*california.total_bounds[[1, 3]])
        else:
            minx, miny, maxx, maxy = focus_boundary.total_bounds
            dx, dy = (maxx - minx) * 0.04, (maxy - miny) * 0.04
            ax.set_xlim(minx - dx, maxx + dx)
            ax.set_ylim(miny - dy, maxy + dy)
        apply_map_frame(ax)
        ax.set_title(month, fontsize=9, fontweight="bold", pad=3)
        ax.tick_params(labelbottom=False, labelleft=False, length=2)
        ax.grid(True, color="white", linewidth=0.4, alpha=0.5, zorder=2)
        return scatter

    for month in MONTHS:
        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor="#F8FAFC")
        scatter = draw_one(ax, month)
        ax.set_title(
            f"{month} {value_name}\nHistorical_Unsplit (Product_A) grid | {period_label}",
            fontsize=11, fontweight="bold", pad=8,
        )
        ax.tick_params(labelbottom=True, labelleft=True, labelsize=8)
        ax.set_xlabel("Longitude", fontsize=9)
        ax.set_ylabel("Latitude", fontsize=9)
        colorbar = plt.colorbar(scatter, ax=ax, orientation="vertical", pad=0.02,
                                shrink=0.65)
        colorbar.set_label(unit, fontsize=9)
        plt.tight_layout()
        output_file = output_dir / f"{filename_prefix}_{month}.png"
        with open(str(output_file), "wb") as f_out:
            fig.savefig(f_out, dpi=180, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)

    if save_monthly_grid:
        fig, axes = plt.subplots(3, 4, figsize=(22, 17), facecolor="#F8FAFC")
        fig.suptitle(
            f"{value_name} ({unit}) | Historical_Unsplit (Product_A) grid | {period_label}",
            fontsize=14, fontweight="bold", y=0.995,
        )
        scatter = None
        for ax, month in zip(axes.flat, MONTHS):
            scatter = draw_one(ax, month)
        colorbar = fig.colorbar(scatter, ax=axes, orientation="horizontal",
                                fraction=0.025, pad=0.03, aspect=50)
        colorbar.set_label(unit, fontsize=11)
        plt.subplots_adjust(wspace=0.04, hspace=0.15)
        output_file = output_dir / f"{filename_prefix}_monthly_grid.png"
        with open(str(output_file), "wb") as f_out:
            fig.savefig(f_out, dpi=160, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)


def draw_monthly_scale_map_set(df, value_name, unit, output_dir, filename_prefix,
                               color_map, focus_boundary=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    boundaries = load_wba_boundary()
    california = load_california_boundary(boundaries)
    if focus_boundary is None:
        focus_boundary = boundaries
    df = points_inside(df, focus_boundary)
    period_label = PERIOD_LABELS[value_name]
    def draw_one(ax, month):
        points = df.dropna(subset=[month])
        month_min = float(points[month].min())
        month_max = float(points[month].max())
        if month_min == month_max:
            month_max = month_min + 1e-9
        draw_study_background(ax, california)
        boundaries.boundary.plot(ax=ax, color="#475569", linewidth=0.55, zorder=3)
        scatter = ax.scatter(
            points["Lon"], points["Lat"], c=points[month], cmap=color_map,
            vmin=month_min, vmax=month_max, s=3, alpha=0.9,
            linewidths=0, zorder=4,
        )
        if focus_boundary is None:
            ax.set_xlim(*california.total_bounds[[0, 2]])
            ax.set_ylim(*california.total_bounds[[1, 3]])
        else:
            minx, miny, maxx, maxy = focus_boundary.total_bounds
            dx, dy = (maxx - minx) * 0.04, (maxy - miny) * 0.04
            ax.set_xlim(minx - dx, maxx + dx)
            ax.set_ylim(miny - dy, maxy + dy)
        apply_map_frame(ax)
        return scatter, month_min, month_max

    for month in MONTHS:
        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor="#F8FAFC")
        scatter, month_min, month_max = draw_one(ax, month)
        ax.set_title(f"{month} {value_name}\nHistorical_Unsplit (Product_A) grid | {period_label} | monthly scale",
                     fontsize=11, fontweight="bold", pad=8)
        colorbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.02,
                                shrink=0.65)
        colorbar.set_label(f"{unit} ({month} scale)", fontsize=9)
        output_file = output_dir / f"{filename_prefix}_{month}.png"
        with open(str(output_file), "wb") as f_out:
            fig.savefig(f_out, dpi=180, bbox_inches="tight",
                        facecolor=fig.get_facecolor(), format="png")
        plt.close(fig)


def main():
    validate_full_period(CORRECTED_CSV)
    f1 = pd.read_csv(F1_CSV)
    hs = pd.read_csv(HS_CSV)
    f1 = f1.rename(columns={"Lon": "Lon", "Lat": "Lat"})
    hs = hs.rename(columns={"Lon": "Lon", "Lat": "Lat"})

    draw_map_set(
        f1, "F1 adjustment factor", "unitless", F1_DIR, "F1",
        "viridis", (0.0, 3.0), save_monthly_grid=False,
    )
    california = load_california_boundary(load_wba_boundary())
    draw_map_set(
        f1, "F1 adjustment factor", "unitless", F1_CA_DIR, "F1_CA",
        "viridis", (0.0, 3.0), focus_boundary=california,
        save_monthly_grid=False,
    )
    draw_monthly_scale_map_set(
        f1, "F1 adjustment factor", "unitless", F1_MONTHLY_DIR, "F1",
        "viridis",
    )
    draw_monthly_scale_map_set(
        f1, "F1 adjustment factor", "unitless", F1_CA_MONTHLY_DIR, "F1_CA",
        "viridis", focus_boundary=california,
    )
    draw_map_set(
        hs, "H-S monthly average ETo", "mm/day", HS_DIR, "HS_avg",
        "YlOrRd", (0.0, 8.0), save_monthly_grid=False,
    )
    draw_monthly_scale_map_set(
        hs, "H-S monthly average ETo", "mm/day", HS_MONTHLY_DIR, "HS_avg",
        "YlOrRd",
    )
    draw_map_set(
        hs, "H-S monthly average ETo", "mm/day", HS_CA_DIR, "HS_CA",
        "YlOrRd", (0.0, 8.0), focus_boundary=california,
        save_monthly_grid=False,
    )
    draw_monthly_scale_map_set(
        hs, "H-S monthly average ETo", "mm/day", HS_CA_MONTHLY_DIR, "HS_CA",
        "YlOrRd", focus_boundary=california,
    )
    print(f"F1 maps saved to: {F1_DIR}")
    print(f"H-S maps saved to: {HS_DIR}")


if __name__ == "__main__":
    main()