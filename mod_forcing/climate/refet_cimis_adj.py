"""
Reference ET library (CIMIS adjusted Hargreaves-Samani)
=======================================================
Shared code of the two command line programs in this folder:

- ``_3_refet_f1_factors.py``  steps 0, 5, 6, 7 and 8 of the manual on the
  Historical_Unsplit weather: grid weights, H-S ETo, CIMIS monthly means, the F1
  correction factors and the Historical_Unsplit polygon averages.
- ``_4_refet_product_et.py``  steps 10 to 14 for one product: H-S ETo on the
  product weather, F1, polygon averages, the daily spline, daily precipitation
  and the CUP+ crop ET run that produces the CalSimHydro ET DSS files.

Manual: ``User_Manual_CS3_Domain_v2.pdf`` (Mohammad Monirul Hasan, DWR MSO),
"Calculating Reference Evapotranspiration for California and CalSim 3 Domain
Using PRISM Data and the Hargreaves-Samani Equation". Each section below names
the manual section it implements and states where the code departs from it.
The one factor memo (Hassan and others, 2025) gives the method: ETo_HS from
Hargreaves-Samani, F1(month) = mean CIMIS ETo / mean H-S ETo per grid cell over
the calibration years, ETo = F1 * ETo_HS, then area weighted averages per
polygon.

Sections
--------
 1. Products, folders and file names
 2. Calendars: Gregorian, WGEN stamp years, Product B chunk windows
 3. Weather grid cells and polygon weights (manual sections 3 and 8; step 0)
 4. Hargreaves-Samani ETo (manual section 5; steps 5 and 10)
 5. Monthly mean Spatial CIMIS ETo at the grid cells (manual section 6; step 6)
 6. F1 adjustment factors (manual section 7; steps 7 and 10)
 7. Area weighted polygon averages (manual section 8; steps 8 and 11)
 8. Daily ETo by cubic spline (manual section 9; step 12)
 9. Daily WBA precipitation for CUP+ (step 13)
10. DSS writers and checks (steps 11 and 14)
11. The CUP+ run (step 14)
12. Pipeline steps and the Product B pass
13. Diagnostic maps (--plots)
"""
from __future__ import annotations

import calendar
import gzip
import os
import re
import shutil
import sys
import tempfile
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from multiprocessing import Pool, cpu_count
from pathlib import Path

import numpy as np
import pandas as pd

# The repository root for utils, whichever folder this file is run or imported from.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from utils import wgen, wgen_calendar  # noqa: E402
from utils.paths import (REPO_ROOT, WEATHER_SETS, get_base_dir,  # noqa: E402
                         get_module_generated_dir, get_wgen_dir)

# pydsstools (through utils.dss_io) and pycup are imported inside the functions that use
# them, so the worker processes of the cell pass never load them.


# =============================================================================================
# 1. Products, folders and file names
# =============================================================================================
# Every path is built here, so the weather set is an argument and never a constant in a step.
#
#     GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/
#         step0/ step5/ step6/ step7/ step8/     set independent (Historical_Unsplit)
#         <set>/step10/ ... <set>/step14/        one tree per set
#     GENERATED/mod_hydrology/calsimhydro/output/_2_compile_et/<set>/
#         CS3_RefETo.dss, CS3_ET.dss              Product B: one pair per chunk, suffix _n01 to _n10

STEP_FOLDER = "_3_refet_cimis_adj"
#: The --product keys, those of utils.paths.WEATHER_SETS: historical (Historical_Unsplit), A and B.
PRODUCT_KEYS = tuple(WEATHER_SETS)
FACTOR_STEPS = (0, 5, 6, 7, 8)
PRODUCT_STEPS = (10, 11, 12, 13, 14)

HISTORICAL_START_YEAR = 1920
HISTORICAL_END_YEAR = 2018


@dataclass(frozen=True)
class Product:
    """One weather set of the pipeline: a key of ``utils.paths.WEATHER_SETS``, whose table
    gives the weather folder (``utils.paths.get_wgen_dir``), the file prefix (``data`` for
    the historical record, ``meteo`` for the WGEN products) and the output folder name."""

    key: str               # "historical", "A" or "B"
    start_year: int        # first label year of the outputs
    end_year: int          # last label year of the outputs

    @property
    def name(self) -> str:
        """The output folder name: Historical_Unsplit, Product_A or Product_B."""
        return WEATHER_SETS[self.key]["name"]

    @property
    def weather_dir(self) -> Path:
        return get_wgen_dir(self.key)

    @property
    def calendar(self) -> str:
        """``gregorian`` (dated rows) or ``wgen`` (Product B's stamp years)."""
        return "wgen" if self.key == "B" else "gregorian"

    @property
    def is_chunked(self) -> bool:
        return self.calendar == "wgen"

    @property
    def n_years(self) -> int:
        return self.end_year - self.start_year + 1


def get_product(key: str) -> Product:
    if key not in PRODUCT_KEYS:
        raise ValueError(f"unknown product {key!r}; choose one of {PRODUCT_KEYS}")
    if key == "B":
        # Each chunk is laid out January 1920 to December 2021, the span CalSimHydro reads.
        return Product(key, 1920, 2021)
    return Product(key, HISTORICAL_START_YEAR, HISTORICAL_END_YEAR)


# -- folders -------------------------------------------------------------------

def refet_output_dir() -> Path:
    return get_module_generated_dir("mod_forcing/climate") / "output" / STEP_FOLDER


def factor_step_dir(step: int) -> Path:
    """Folder of a product independent step (0, 5, 6, 7, 8)."""
    if step not in FACTOR_STEPS:
        raise ValueError(f"step {step} is not a correction factor step {FACTOR_STEPS}")
    return refet_output_dir() / f"step{step}"


def product_step_dir(product: Product, step: int) -> Path:
    """Folder of a product step (10 to 14) for one product."""
    if step not in PRODUCT_STEPS:
        raise ValueError(f"step {step} is not a product step {PRODUCT_STEPS}")
    return refet_output_dir() / product.name / f"step{step}"


def calsimhydro_et_dir(product: Product) -> Path:
    """Where CalSimHydro picks up CS3_RefETo.dss and CS3_ET.dss for this product."""
    return (get_module_generated_dir("mod_hydrology/calsimhydro")
            / "output" / "_2_compile_et" / product.name)


def calsimhydro_precip_dir(product: Product) -> Path:
    """The daily WBA precipitation csv files of mod_hydrology/calsimhydro/_1_compile_precip.py."""
    return (get_module_generated_dir("mod_hydrology/calsimhydro")
            / "output" / "_1_compile_precip" / product.name / "pcp")


def cimis_monthly_dir() -> Path:
    return factor_step_dir(6) / "CIMIS_MonthlyAvg_ETo"


def reference_dir() -> Path:
    """mod_forcing/climate/reference: boundary files and the CalSim reference tables."""
    return REPO_ROOT / "mod_forcing" / "climate" / "reference"


def cimis_raster_dir() -> Path:
    return get_base_dir() / "CIMIS" / "cimis_eto_rasters"


def pycup_dir() -> Path:
    return get_base_dir() / "PyCUP"


def reference_cropet_dss() -> Path:
    """Historical CalSimHydro ET input that holds the legacy CropET terms."""
    return get_base_dir() / "CalSim3" / "CSHydro_Existing" / "inputDSS" / "CS3_ET.dss"


# -- file names ------------------------------------------------------------------

def chunk_suffix(chunk: int | None) -> str:
    return "" if chunk is None else f"_n{chunk:02d}"


# step 5 / step 10: Hargreaves-Samani per grid cell
ETO_MONTHLY_CSV = "ETo_monthly_inpermonth.csv"
MONTHLY_RA_CSV = "monthly_Ra.csv"
DAILY_RA_CSV = "daily_Ra_reference_year.csv"
# step 7 / step 10: F1
ETO_CORRECTED_CSV = "ETo_F1corrected_monthly_inpermonth.csv"
F1_TABLE_CSV = "F1_table.csv"
HS_AVG_CSV = "HS_monthly_avg_mmperday.csv"
HS_AVG_F1_PERIOD_CSV = "HS_monthly_avg_mmperday_{start}_{end}.csv"
F1_SOURCE_TXT = "F1_source.txt"
# step 6: the monthly CIMIS means, one file per year and one over all years
CIMIS_ANNUAL_CSV = "CIMIS_MonthlyAvg_ETo_mmperday_grid_{year}.csv"
CIMIS_OVERALL_CSV = "CIMIS_MonthlyAvg_ETo_mmperday_grid_{start}_{end}.csv"
# step 8 / step 11: polygon averages and series
AVERAGED_CSV = "Spatial_Average_ETo_F1corrected_monthly_averaged_per_{group}{chunk}.csv"
TIMESERIES_CSV = "Spatial_Average_ETo_F1corrected_monthly_timeseries_per_{group}{chunk}.csv"
# step 12
ETOCUM_CSV = "EToCum{chunk}.csv"
ETO_DAILY_CSV = "EToDaily{chunk}.csv"
# step 13
PRECIP_DAILY_CSV = "precip_daily{chunk}.csv"
# step 14
CUP_MONTHLY_ETC_CSV = "MonthlyETc{chunk}.csv"
STEP14_REPORT = "DSS_validation{chunk}.txt"
# CalSimHydro inputs
REFETO_DSS = "CS3_RefETo{chunk}.dss"
ET_DSS = "CS3_ET{chunk}.dss"


def named(template: str, chunk: int | None = None, **fields) -> str:
    return template.format(chunk=chunk_suffix(chunk), **fields)


# =============================================================================================
# 2. Calendars
# =============================================================================================
# Historical_Unsplit and Product A are dated rows on the Gregorian calendar. Product B is WGEN's
# own sequence of 1008 stamp years (utils/wgen_calendar.py), cut into ten chunks of 100 water
# years, each labelled January 1920 to December 2021 for CalSimHydro: the 9 stamp months before
# the chunk become January to September 1921, the chunk October 1921 to September 2021, the 3
# months after it October to December 2021, and 1920 is a copy of 1921. Daily values follow
# utils.wgen_calendar.daily_chunk_1920_2021, the convention of the CalSimHydro precipitation.

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_LENGTHS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

CHUNK_START_YEAR = 1920
CHUNK_END_YEAR = 2021
N_CHUNKS = wgen_calendar.N_CHUNKS


def month_columns(start_year: int, end_year: int) -> list[str]:
    """Column names ``Jan-1920`` ... ``Dec-2018`` of the per cell monthly tables."""
    return [f"{month}-{year}" for year in range(start_year, end_year + 1)
            for month in MONTH_NAMES]


def parse_month_column(column: str) -> tuple[str, int]:
    name, year = column.split("-")
    return name, int(year)


def gregorian_month_lengths(year: int) -> np.ndarray:
    return np.array([calendar.monthrange(year, month)[1] for month in range(1, 13)], dtype=float)


def stamp_month_lengths(year: int) -> np.ndarray:
    lengths = np.array(MONTH_LENGTHS, dtype=float)
    if wgen_calendar.is_stamp_leap(year):
        lengths[1] = 29
    return lengths


def stamp_day_of_year(year, month, day) -> np.ndarray:
    """Day of the stamp year (1 on 1 January) for arrays of stamp year, month and day."""
    year = np.asarray(year, dtype=np.int64)
    month = np.asarray(month, dtype=np.int64)
    day = np.asarray(day, dtype=np.int64)
    before = np.concatenate([[0], np.cumsum(MONTH_LENGTHS)[:-1]])
    doy = before[month - 1] + day
    leap_after_feb = wgen_calendar.is_stamp_leap(year) & (month > 2)
    return doy + leap_after_feb.astype(np.int64)


def chunk_monthly_window(values: np.ndarray, chunk: int) -> np.ndarray:
    """1224 monthly values labelled January 1920 to December 2021 for one chunk, taken
    from a series indexed by stamp month (0 = January of stamp year 1): the layout of
    CalSimHydro's other Product B inputs (``utils.wgen_calendar.monthly_chunk_1920_2021``)."""
    return wgen_calendar.monthly_chunk_1920_2021(values, chunk)


def chunk_daily_window(values: np.ndarray, chunk: int) -> np.ndarray:
    """37,256 daily values labelled 1 January 1920 to 31 December 2021 for one chunk."""
    return wgen_calendar.daily_chunk_1920_2021(values, chunk)


def chunk_month_index() -> pd.DatetimeIndex:
    """Month ends of the chunk window."""
    return pd.date_range(f"{CHUNK_START_YEAR}-01-01", periods=12 * (CHUNK_END_YEAR - CHUNK_START_YEAR + 1),
                         freq="ME")


def chunk_day_index() -> pd.DatetimeIndex:
    return pd.date_range(f"{CHUNK_START_YEAR}-01-01", f"{CHUNK_END_YEAR}-12-31", freq="D")


def stamp_month_count() -> int:
    return 12 * wgen_calendar.STAMP_YEARS


# =============================================================================================
# 3. Weather grid cells and polygon weights (manual sections 3 and 8; step 0)
# =============================================================================================
# Manual sections 3 and 4 select PRISM 4 km cells; section 8 weights them into polygons with
# ArcPy WTable files. Here the grid is WGEN's 1/16 degree daily grid (one text file per cell:
# year month day precip tmax tmin) and step 0 builds the WTable files itself by intersecting
# the cell squares with the WBA, subregion and small watershed polygons (EPSG:3310).
# WBA 91 has no polygon; its table copies WBA 90's.

CELL_PATTERN = re.compile(r"^(?:data|meteo)_([-\d.]+)_([-\d.]+)$")
CLOUD_ONLY_ATTRIBUTE = 0x400000      # FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS: a OneDrive placeholder
MM_PER_INCH = 25.4

WBA_91_ID = "91"
WBA_91_SOURCE = "90"
HALF_CELL = 0.03125          # half the 1/16 degree cell width
MIN_PERCENT = 0.01           # drop cells contributing less than 0.01 percent to a polygon
CRS_GEO = "EPSG:4326"
CRS_AREA = "EPSG:3310"
WBA_GEOJSON = "CS3_WBAs.geojson"
SR_GEOJSON = "C2vsim_subregions.geojson"
SW_GEOJSON = "SmallWatersheds.geojson"
WBA_ID_FIELD = "WBA_ID"
SR_ID_FIELD = "Subregion_"
SW_ID_FIELD = "SW_ID"
GROUPS = ("WBA", "SR", "SW")


# -- grid cells ------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    lat: float
    lon: float
    path: Path

    @property
    def key(self) -> tuple[float, float]:
        """The (lat, lon) key the weight tables and file names agree on."""
        return (round(self.lat, 5), round(self.lon, 5))


def scan_cells(weather_dir: Path) -> list[Cell]:
    """Every weather file of a product, in file name order."""
    cells = []
    for name in sorted(os.listdir(weather_dir)):
        match = CELL_PATTERN.match(name)
        if match:
            cells.append(Cell(float(match.group(1)), float(match.group(2)), Path(weather_dir) / name))
    if not cells:
        raise FileNotFoundError(f"no data_<lat>_<lon> or meteo_<lat>_<lon> files in {weather_dir}")
    return cells


def require_hydrated(cells: list[Cell]) -> None:
    """Stop on OneDrive cloud only placeholders before a worker pool reads them one by one
    (reading a placeholder downloads it on demand, slowly or not at all). A placeholder
    reports its full size, so the test is the Windows file attribute, and zero size."""
    def is_placeholder(path: Path) -> bool:
        info = os.stat(path)
        return info.st_size == 0 or bool(getattr(info, "st_file_attributes", 0) & CLOUD_ONLY_ATTRIBUTE)

    placeholders = [cell for cell in cells if is_placeholder(cell.path)]
    if placeholders:
        raise OSError(
            f"{len(placeholders):,} of {len(cells):,} weather files are OneDrive cloud only "
            f"placeholders, for example {placeholders[0].path.name}. Right click the "
            "folder in File Explorer, choose 'Always keep on this device', wait for the sync, "
            "and rerun."
        )


# -- polygon weight tables (step 0 output) ------------------------------------------

def polygon_group(poly_id: str) -> str:
    if poly_id.startswith("SR_"):
        return "SR"
    if poly_id.startswith("SW_"):
        return "SW"
    return "WBA"


def polygon_sort_key(poly_id: str):
    """WBAs first in name order, then subregions and small watersheds in numeric order."""
    for group, prefix in enumerate(("SR_", "SW_"), start=1):
        if poly_id.startswith(prefix):
            return (group, int(poly_id[len(prefix):]), poly_id)
    return (0, 0, poly_id)


def read_weight_table(path: Path) -> pd.DataFrame:
    """One ``WTable_<id>.csv``: two comment lines, then long[k], lati[k], percent[k]."""
    table = pd.read_csv(path, skiprows=2)
    table.columns = ["Lon", "Lat", "pct_k"]
    table = table.apply(pd.to_numeric, errors="coerce")
    return table.dropna().reset_index(drop=True)


def load_weight_tables(step0_dir: Path) -> dict[str, pd.DataFrame]:
    """All weight tables keyed by polygon id (``02``, ``SR_3``, ``SW_10``), sorted."""
    tables = {}
    for path in Path(step0_dir).glob("WTable_*.csv"):
        tables[path.stem[len("WTable_"):]] = read_weight_table(path)
    if not tables:
        raise FileNotFoundError(f"no WTable_*.csv in {step0_dir}; run step 0 first")
    return {poly_id: tables[poly_id] for poly_id in sorted(tables, key=polygon_sort_key)}


def group_ids(weights: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    groups = {group: [] for group in GROUPS}
    for poly_id in weights:
        groups[polygon_group(poly_id)].append(poly_id)
    return groups


def weight_sums(weights: dict[str, pd.DataFrame]) -> np.ndarray:
    return np.array([table["pct_k"].sum() for table in weights.values()], dtype=float)


def cell_memberships(weights: dict[str, pd.DataFrame]) -> dict[tuple[float, float], list[tuple[int, float]]]:
    """For every weighted cell, the (polygon index, percent) pairs it contributes to.
    Polygon indexes follow the order of ``weights``."""
    members: dict[tuple[float, float], list[tuple[int, float]]] = {}
    for index, table in enumerate(weights.values()):
        for lon, lat, pct in table.itertuples(index=False):
            members.setdefault((round(lat, 5), round(lon, 5)), []).append((index, float(pct)))
    return members


def member_cells(cells: list[Cell], memberships) -> list[Cell]:
    """The cells that carry weight in at least one polygon, in file order."""
    present = {cell.key for cell in cells}
    missing = sorted(set(memberships) - present)
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} cells weighted in step 0 have no weather file; first "
            f"lat={missing[0][0]} lon={missing[0][1]}")
    return [cell for cell in cells if cell.key in memberships]


# -- step 0: build the weight tables (manual section 3, the ArcPy WTable files) --------

def write_weight_table(poly_id: str, table: pd.DataFrame, output_dir: Path, prefix: str = "") -> Path:
    """Write ``WTable_<prefix><id>.csv`` in the two comment line format every reader expects."""
    path = Path(output_dir) / f"WTable_{prefix}{poly_id}.csv"
    with open(path, "w", newline="") as handle:
        handle.write(f"# {prefix}{poly_id} - grid cell fractional coverage weights\n")
        handle.write("# percent[k] = intersection_area / polygon_area * 100  (column sum ~ 100)\n")
        table.to_csv(handle, index=False)
    return path


def build_weight_tables(reference_dir: Path, weather_dir: Path, output_dir: Path) -> dict[str, int]:
    """Step 0: percent of each polygon's area covered by every grid cell square.

    Returns the number of tables written per group. Needs geopandas and shapely
    (both in environment.yml); the step runs once and its outputs are kept.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import box
    except ImportError as exc:
        raise ImportError("step 0 needs geopandas and shapely; run it in an environment "
                          "that has them (the other steps do not need them)") from exc

    cells = scan_cells(weather_dir)
    grid = gpd.GeoDataFrame(
        {"lat": [cell.lat for cell in cells], "lon": [cell.lon for cell in cells]},
        geometry=[box(cell.lon - HALF_CELL, cell.lat - HALF_CELL,
                      cell.lon + HALF_CELL, cell.lat + HALF_CELL) for cell in cells],
        crs=CRS_GEO,
    ).to_crs(CRS_AREA)
    grid_index = grid.sindex
    print(f"  grid cells: {len(grid):,}")

    def weights_for(polygons, id_field: str, label: str) -> dict[str, pd.DataFrame]:
        polygons = polygons.to_crs(CRS_AREA)
        result = {}
        for _, polygon in polygons.iterrows():
            poly_id = str(polygon[id_field])
            geometry = polygon.geometry
            area = geometry.area
            if area == 0:
                print(f"  [WARN] {label} {poly_id} has zero area; skipped")
                continue
            candidates = grid.iloc[list(grid_index.intersection(geometry.bounds))]
            rows = []
            for _, cell in candidates.iterrows():
                intersection = cell.geometry.intersection(geometry)
                if intersection.is_empty:
                    continue
                pct = intersection.area / area * 100.0
                if pct < MIN_PERCENT:
                    continue
                rows.append({"long[k]": round(cell["lon"], 7), "lati[k]": round(cell["lat"], 7),
                             "percent[k]": round(pct, 6)})
            if not rows:
                print(f"  [WARN] no grid cells intersect {label} {poly_id}")
                continue
            table = pd.DataFrame(rows)
            result[poly_id] = table
            print(f"  {label} {poly_id:>8s}: {len(table):4d} cells, coverage sum {table['percent[k]'].sum():.2f}%")
        return result

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reference_dir = Path(reference_dir)
    counts = {}

    wba = gpd.read_file(reference_dir / WBA_GEOJSON)[[WBA_ID_FIELD, "geometry"]]
    wba_weights = weights_for(wba, WBA_ID_FIELD, "WBA")
    if WBA_91_SOURCE not in wba_weights:
        raise KeyError(f"WBA {WBA_91_SOURCE} weights not found; cannot build WBA {WBA_91_ID}")
    wba_weights[WBA_91_ID] = wba_weights[WBA_91_SOURCE].copy()
    for poly_id, table in sorted(wba_weights.items()):
        write_weight_table(poly_id, table, output_dir)
    counts["WBA"] = len(wba_weights)

    sr = gpd.read_file(reference_dir / SR_GEOJSON)[[SR_ID_FIELD, "geometry"]]
    sr[SR_ID_FIELD] = sr[SR_ID_FIELD].astype(int).astype(str)
    sr_weights = weights_for(sr, SR_ID_FIELD, "SR")
    for poly_id, table in sorted(sr_weights.items()):
        write_weight_table(poly_id, table, output_dir, prefix="SR_")
    counts["SR"] = len(sr_weights)

    sw_all = gpd.read_file(reference_dir / SW_GEOJSON)[[SW_ID_FIELD, "geometry"]]
    sw = sw_all[sw_all[SW_ID_FIELD].notna()
                & sw_all[SW_ID_FIELD].astype(str).str.strip().ne("")].copy()
    sw[SW_ID_FIELD] = sw[SW_ID_FIELD].astype(str).str.strip()
    sw_weights = weights_for(sw, SW_ID_FIELD, "SW")
    for poly_id, table in sorted(sw_weights.items()):
        write_weight_table(poly_id, table, output_dir, prefix="SW_")
    counts["SW"] = len(sw_weights)
    return counts


# =============================================================================================
# 4. Hargreaves-Samani reference ETo (manual section 5; steps 5 and 10)
# =============================================================================================
# Manual: ETo = 0.0023 Ra (Tmax - Tmin)^0.5 (Tmean + 17.8), Ra from latitude and day of year,
# on monthly PRISM temperatures with the monthly mean Ra of a reference year, in inches/month.
# Departures from the manual: the weather is daily, so ETo is computed per day with that day's
# Ra and summed to months (not identical to the monthly formula because of the square root);
# Ra uses a 365.25 day period and the diagnostic Ra tables use 1920, a leap year; monthly ETo
# is rounded to 4 decimals. The same kernel serves every set, Product B on stamp days.

REFERENCE_YEAR = 1920
REFERENCE_DAYS = [datetime(REFERENCE_YEAR, 1, 1) + timedelta(days=i) for i in range(366)]
ETO_DECIMALS = 4


def ra_daily(lat_deg: float, day_of_year) -> np.ndarray:
    """Extraterrestrial radiation Ra (MJ/m2/day) divided by 2.45, per day of year."""
    phi = np.radians(lat_deg)
    j = np.asarray(day_of_year, dtype=float)
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365.25)
    delta = 0.409 * np.sin(2 * np.pi * j / 365.25 - 1.39)
    omega_s = np.arccos(-np.tan(phi) * np.tan(delta))
    ra_mj = (24 * 60 / np.pi) * 0.0820 * dr * (
        omega_s * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(omega_s)
    )
    return ra_mj / 2.45


def hs_eto_mm(ra: np.ndarray, tmax: np.ndarray, tmin: np.ndarray) -> np.ndarray:
    """Daily Hargreaves-Samani ETo in mm; zero when Tmax does not exceed Tmin."""
    delta_t = np.maximum(tmax - tmin, 0.0)
    tmean = (tmax + tmin) / 2.0
    return np.where(delta_t > 0, 0.0023 * ra * (tmean + 17.8) * np.sqrt(delta_t), 0.0)


def reference_ra(lat: float, lon: float) -> tuple[dict, list]:
    """Monthly mean Ra of the reference year and its daily values (diagnostic tables)."""
    ra = ra_daily(lat, [day.timetuple().tm_yday for day in REFERENCE_DAYS])
    months = np.array([day.month for day in REFERENCE_DAYS])
    monthly = {name: round(float(np.mean(ra[months == i + 1])), 4)
               for i, name in enumerate(MONTH_NAMES)}
    daily = [[lon, lat, REFERENCE_DAYS[i].strftime("%Y-%m-%d"), round(float(ra[i]), 4)]
             for i in range(len(REFERENCE_DAYS))]
    return monthly, daily


@dataclass(frozen=True)
class CellTask:
    """What to compute for one cell; picklable for the worker pool."""
    lat: float
    lon: float
    path: str
    product: str               # a key of utils.paths.WEATHER_SETS; B follows the stamp calendar
    start_year: int            # ignored for Product B
    end_year: int
    want_ra: bool = False


@dataclass
class CellResult:
    lat: float
    lon: float
    monthly_eto: np.ndarray | None = None      # inches per month, rounded, one value per month
    monthly_ra: dict | None = None
    daily_ra: list | None = None
    error: str | None = None

    @property
    def key(self) -> tuple[float, float]:
        return (round(self.lat, 5), round(self.lon, 5))


def process_cell(task: CellTask) -> CellResult:
    """Read the temperatures of one weather file through ``utils.wgen.read_met``, the reader
    every module uses (it checks Product B's stamp calendar), and compute the monthly H-S ETo
    and, if the task asks, the Ra tables."""
    result = CellResult(task.lat, task.lon)
    try:
        weather = wgen.read_met(task.product, task.path, usecols=["tmax", "tmin"])

        if task.product != "B":
            dates = wgen.dates(weather)
            keep = (dates >= f"{task.start_year}-01-01") & (dates <= f"{task.end_year}-12-31")
            weather = weather[keep].reset_index(drop=True)
            dates = dates[keep]
            if weather.empty:
                raise ValueError(f"no rows between {task.start_year} and {task.end_year}")
            n_months = 12 * (task.end_year - task.start_year + 1)
            month_index = ((weather["Year"].to_numpy() - task.start_year) * 12
                           + weather["Month"].to_numpy() - 1)
            expected_days = (pd.Timestamp(f"{task.end_year}-12-31")
                             - pd.Timestamp(f"{task.start_year}-01-01")).days + 1
            if len(weather) != expected_days or not dates.is_monotonic_increasing:
                raise ValueError(f"{len(weather)} rows between {task.start_year} and "
                                 f"{task.end_year}; expected {expected_days} in order")
            day_of_year = dates.dayofyear.to_numpy()
        else:
            # read_met has checked that the rows are the stamp days in order.
            n_months = stamp_month_count()
            month_index = wgen_calendar.stamp_month_index(weather["Year"], weather["Month"])
            day_of_year = stamp_day_of_year(weather["Year"], weather["Month"], weather["Day"])

        ra = ra_daily(task.lat, day_of_year)
        eto_mm = hs_eto_mm(ra, weather["tmax"].to_numpy(), weather["tmin"].to_numpy())
        totals = np.bincount(month_index, weights=eto_mm, minlength=n_months)
        counts = np.bincount(month_index, minlength=n_months)
        if (counts == 0).any():
            raise ValueError("a month has no rows")
        result.monthly_eto = np.round(totals / MM_PER_INCH, ETO_DECIMALS)
        if task.want_ra:
            result.monthly_ra, result.daily_ra = reference_ra(task.lat, task.lon)
    except Exception as exc:          # reported by the caller, which stops the run
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def make_tasks(cells: list[Cell], product_key: str, start_year: int, end_year: int, *,
               want_ra: bool = False) -> list[CellTask]:
    return [CellTask(cell.lat, cell.lon, str(cell.path), product_key, start_year, end_year, want_ra)
            for cell in cells]


def run_cells(tasks: list[CellTask], workers: int | None = None, progress_every: int = 500):
    """Yield a CellResult per task, in task order. ``workers`` 0 or 1 runs in this process."""
    if workers is None:
        workers = cpu_count()
    if workers <= 1:
        iterator = map(process_cell, tasks)
        pool = None
    else:
        pool = Pool(workers)
        iterator = pool.imap(process_cell, tasks, chunksize=4)
    try:
        for n, result in enumerate(iterator, start=1):
            if result.error:
                raise RuntimeError(f"cell lat={result.lat} lon={result.lon}: {result.error}")
            if progress_every and n % progress_every == 0:
                print(f"    cells done: {n:,}/{len(tasks):,}", flush=True)
            yield result
    finally:
        if pool is not None:
            pool.close()
            pool.join()


def monthly_table(results: list[CellResult], start_year: int, end_year: int) -> pd.DataFrame:
    """Per cell monthly ETo table: Lon, Lat, Jan-<start> ... Dec-<end> (the step 5 and 10 layout)."""
    columns = month_columns(start_year, end_year)
    values = np.vstack([result.monthly_eto for result in results])
    table = pd.DataFrame(values, columns=columns)
    table.insert(0, "Lat", [result.lat for result in results])
    table.insert(0, "Lon", [result.lon for result in results])
    return table


def ra_tables(results: list[CellResult]) -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = pd.DataFrame([{"Lon": r.lon, "Lat": r.lat, **r.monthly_ra} for r in results])
    daily = pd.DataFrame([row for r in results for row in r.daily_ra],
                         columns=["Lon", "Lat", "Date", "Daily_Ra"])
    return monthly, daily


# =============================================================================================
# 5. Monthly mean Spatial CIMIS ETo at the grid cells (manual section 6; step 6)
# =============================================================================================
# Manual: daily Spatial CIMIS ETo rasters (2 km, Penman-Monteith), 2004 to 2021, missing days
# filled, long term monthly mean rasters, then the mean of the pixels inside each PRISM cell.
# Departures from the manual: each raster is sampled at the centre of every grid cell; the
# means are written per year, 2004 to 2023, and step 7 averages 2004 to 2018, the years that
# overlap the weather; missing days are not filled (the download is a separate manual step);
# cells outside the CIMIS domain carry NaN, which step 7 turns into F1 = 1.
# The rasters are gzip ESRI ASCII grids ETo_YYYYMMDD.asc.gz in BASE/CIMIS/cimis_eto_rasters,
# read as California Albers NAD83 (EPSG:3310).

FILENAME_PATTERN = re.compile(r"ETo_(\d{4})(\d{2})(\d{2})\.asc\.gz$")
RASTER_CRS = "EPSG:3310"
CIMIS_START_YEAR = 2004
CIMIS_END_YEAR = 2023
GZIP_MAGIC = b"\x1f\x8b"


def index_rasters(raster_dir: Path, start_year: int, end_year: int) -> dict[date, Path]:
    """Raster path per day, for the days in the years."""
    index = {}
    for path in Path(raster_dir).iterdir():
        match = FILENAME_PATTERN.search(path.name)
        if not match:
            continue
        try:
            day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if start_year <= day.year <= end_year:
            index[day] = path
    if not index:
        raise FileNotFoundError(f"no ETo_YYYYMMDD.asc.gz rasters for {start_year}-{end_year} in {raster_dir}")
    return index


def project_cells(cells: list[Cell], crs: str = RASTER_CRS) -> tuple[np.ndarray, np.ndarray]:
    """Cell centres in the raster coordinate system."""
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = transformer.transform([cell.lon for cell in cells], [cell.lat for cell in cells])
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def sample_raster(path: Path, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """The raster value under each point; NaN outside the raster or where it has no data."""
    with open(path, "rb") as raw:
        is_gzip = raw.read(2) == GZIP_MAGIC
    opener = gzip.open if is_gzip else open
    with opener(path, "rt") as handle:
        header = {}
        for _ in range(6):
            key, value = handle.readline().split(maxsplit=1)
            header[key.lower()] = float(value)
        data = np.fromstring(handle.read(), sep=" ")
    ncols, nrows = int(header["ncols"]), int(header["nrows"])
    data = data.reshape((nrows, ncols))
    cellsize = header["cellsize"]
    cols = np.floor((xs - header["xllcorner"]) / cellsize).astype(int)
    top = header["yllcorner"] + nrows * cellsize
    rows = np.floor((top - ys) / cellsize).astype(int)
    inside = (rows >= 0) & (rows < nrows) & (cols >= 0) & (cols < ncols)
    values = np.full(len(xs), np.nan)
    if inside.any():
        picked = data[rows[inside], cols[inside]]
        picked[picked == header.get("nodata_value", np.nan)] = np.nan
        values[inside] = picked
    return values


def monthly_means(cells: list[Cell], raster_index: dict[date, Path], output_dir: Path,
                  start_year: int = CIMIS_START_YEAR, end_year: int = CIMIS_END_YEAR) -> list[Path]:
    """Per year, the mean daily CIMIS ETo of each month at every cell (mm/day), plus one
    file averaged over all the years. Returns the paths written."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    xs, ys = project_cells(cells)
    n_cells = len(cells)
    by_year: dict[int, list] = {year: [] for year in range(start_year, end_year + 1)}
    for day, path in raster_index.items():
        by_year[day.year].append((day, path))
    missing_years = [year for year, days in by_year.items() if not days]
    if missing_years:
        raise FileNotFoundError("no CIMIS rasters for the years " + ", ".join(map(str, missing_years)))

    overall_sums = np.zeros((n_cells, 12))
    overall_counts = np.zeros((n_cells, 12))
    written = []
    for year in range(start_year, end_year + 1):
        sums = np.zeros((n_cells, 12))
        counts = np.zeros((n_cells, 12))
        for day, path in sorted(by_year[year]):
            values = sample_raster(path, xs, ys)
            valid = ~np.isnan(values)
            m = day.month - 1
            sums[valid, m] += values[valid]
            counts[valid, m] += 1
        overall_sums += sums
        overall_counts += counts
        written.append(_write_cimis_means(cells, sums, counts, output_dir / named(CIMIS_ANNUAL_CSV, year=year)))
        print(f"  {year}: {len(by_year[year])} rasters")
    written.append(_write_cimis_means(cells, overall_sums, overall_counts,
                                      output_dir / named(CIMIS_OVERALL_CSV, start=start_year, end=end_year)))
    return written


def _write_cimis_means(cells: list[Cell], sums: np.ndarray, counts: np.ndarray, path: Path) -> Path:
    with np.errstate(divide="ignore", invalid="ignore"):
        means = np.where(counts > 0, np.round(sums / counts, 4), np.nan)
    table = pd.DataFrame(means, columns=MONTH_NAMES)
    table.insert(0, "lat", [cell.lat for cell in cells])
    table.insert(0, "lon", [cell.lon for cell in cells])
    table.to_csv(path, index=False, na_rep="NaN")
    return path


# =============================================================================================
# 6. F1 adjustment factors (manual section 7; steps 7 and 10)
# =============================================================================================
# Manual (section 7.3): average the H-S monthly series per calendar month over the calibration
# years, F1 = CIMIS average / H-S average per cell and month, multiply the H-S series by F1.
# Departures from the manual: the calibration years are 2004 to 2018 (the weather ends in
# 2018); F1 = 1 where CIMIS has no value or the H-S average is zero; the corrected series and
# F1 are rounded to 6 decimals, the averages to 4.
# F1 is fit once, in step 7, on Historical_Unsplit, and step 10 applies that table to every
# set: the factor corrects what Hargreaves-Samani leaves out (radiation, humidity, wind), so it
# must come from the years Spatial CIMIS measured, with no temperature detrending. A fit on
# Product A's detrended temperatures would mix the method difference with that adjustment;
# Product B has no 2004 to 2018 at all. (_4 --f1-table applies another table instead.)

F1_START_YEAR = 2004
F1_END_YEAR = 2018
ID_COLUMNS = ["Lon", "Lat"]


def month_data_columns(table: pd.DataFrame) -> list[str]:
    return [column for column in table.columns if column not in ID_COLUMNS]


def hs_monthly_average(table: pd.DataFrame, start_year: int, end_year: int) -> tuple[np.ndarray, pd.DataFrame]:
    """Manual step ii: mean H-S ETo per calendar month over the years, in mm/day.
    Returns the (cells, 12) array and the diagnostic table rounded to 4 decimals."""
    sums = np.zeros((len(table), 12))
    counts = np.zeros(12, dtype=int)
    for column in month_data_columns(table):
        name, year = parse_month_column(column)
        if name not in MONTH_NAMES or not start_year <= year <= end_year:
            continue
        m = MONTH_NAMES.index(name)
        days = calendar.monthrange(year, m + 1)[1]
        sums[:, m] += table[column].to_numpy(dtype=float) * 25.4 / days
        counts[m] += 1
    expected = end_year - start_year + 1
    if not np.all(counts == expected):
        raise ValueError(f"the H-S table must hold every month from {start_year} through "
                         f"{end_year}; found monthly counts {counts.tolist()}")
    average = sums / counts
    diagnostic = table[ID_COLUMNS].copy()
    for m, name in enumerate(MONTH_NAMES):
        diagnostic[name] = np.round(average[:, m], 4)
    return average, diagnostic


def load_cimis_monthly_average(cimis_dir: Path, cells: pd.DataFrame,
                               start_year: int = F1_START_YEAR, end_year: int = F1_END_YEAR) -> np.ndarray:
    """Manual step iii: the step 6 annual CIMIS monthly means averaged over the years, at
    the given cells (Lon, Lat), in mm/day; NaN where a cell has no CIMIS coverage."""
    paths = {year: Path(cimis_dir) / named(CIMIS_ANNUAL_CSV, year=year)
             for year in range(start_year, end_year + 1)}
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        listing = "\n  ".join(str(path) for path in missing)
        raise FileNotFoundError(f"missing step 6 annual CIMIS files for {start_year}-{end_year}:\n  {listing}")
    required = ID_COLUMNS + MONTH_NAMES
    annual = []
    for year, path in paths.items():
        cimis = pd.read_csv(path).rename(columns={"lon": "Lon", "lat": "Lat"})
        absent = [column for column in required if column not in cimis.columns]
        if absent:
            raise ValueError(f"missing columns {absent} in {path}")
        merged = cells[ID_COLUMNS].merge(cimis[required], on=ID_COLUMNS, how="left", validate="one_to_one")
        annual.append(merged[MONTH_NAMES].to_numpy(dtype=float))
    values = np.stack(annual, axis=0)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).sum(axis=0)
    counts = valid.sum(axis=0)
    average = np.full(totals.shape, np.nan)
    np.divide(totals, counts, out=average, where=counts > 0)
    return average


def compute_f1(hs_average: np.ndarray, cimis_average: np.ndarray, cells: pd.DataFrame) -> tuple[np.ndarray, pd.DataFrame]:
    """Manual step iv: F1 = CIMIS average / H-S average per cell and month. A cell with any
    missing CIMIS month lies outside the CIMIS domain and keeps F1 = 1.0 for every month,
    as does any month whose H-S average is zero."""
    outside = ~np.isfinite(cimis_average).all(axis=1)
    valid = np.isfinite(cimis_average) & ~outside[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where((hs_average > 0) & valid, cimis_average / hs_average, 1.0)
    table = cells[ID_COLUMNS].copy()
    for m, name in enumerate(MONTH_NAMES):
        table[name] = np.round(f1[:, m], 6)
    return f1, table


def apply_f1(table: pd.DataFrame, f1: np.ndarray) -> pd.DataFrame:
    """Manual step v: multiply every month of the series by its cell's F1 for that month."""
    columns = month_data_columns(table)
    months = []
    for column in columns:
        name, _ = parse_month_column(column)
        if name not in MONTH_NAMES:
            raise ValueError(f"{column} is not a monthly column")
        months.append(MONTH_NAMES.index(name))
    corrected = np.round(table[columns].to_numpy(dtype=float) * f1[:, months], 6)
    return pd.concat([table[ID_COLUMNS].reset_index(drop=True),
                      pd.DataFrame(corrected, columns=columns)], axis=1)


def read_f1_table(path: Path) -> pd.DataFrame:
    table = pd.read_csv(path)
    absent = [column for column in ID_COLUMNS + MONTH_NAMES if column not in table.columns]
    if absent:
        raise ValueError(f"F1 table {path} lacks columns {absent}")
    return table


def align_f1(f1_table: pd.DataFrame, cells: pd.DataFrame) -> np.ndarray:
    """The (cells, 12) F1 array of a table, in the order of ``cells`` (Lon, Lat)."""
    key = lambda frame: pd.MultiIndex.from_arrays([frame["Lon"].round(6), frame["Lat"].round(6)])
    positions = key(f1_table).get_indexer(key(cells))
    if (positions < 0).any():
        first = cells.iloc[int(np.flatnonzero(positions < 0)[0])]
        raise KeyError(f"F1 table has no row for Lon={first['Lon']} Lat={first['Lat']}")
    return f1_table.iloc[positions][MONTH_NAMES].to_numpy(dtype=float)


# =============================================================================================
# 7. Area weighted polygon averages (manual section 8; steps 8 and 11)
# =============================================================================================
# Manual: for every WBA, subregion and small watershed, the weighted average of the corrected
# grid ETo with the WTable area percentages as weights, matching cells by their longitude and
# latitude. The outputs are the long term monthly averages per polygon and, beyond the manual,
# the full monthly time series per polygon, which the spline and the RefETo DSS need.



ID_COLUMN = {"WBA": "WBA_ID", "SR": "SR_ID", "SW": "SW_ID"}
AVERAGE_DECIMALS = 4
TIMESERIES_DECIMALS = 6


def _cell_index(table: pd.DataFrame) -> pd.MultiIndex:
    return pd.MultiIndex.from_arrays([table["Lon"].round(6), table["Lat"].round(6)])


def longterm_monthly_average(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Per cell mean of each calendar month over the given monthly columns, rounded."""
    average = table[["Lon", "Lat"]].copy()
    for name in MONTH_NAMES:
        columns_of_month = [column for column in columns if column.split("-")[0] == name]
        average[name] = table[columns_of_month].mean(axis=1).round(AVERAGE_DECIMALS)
    return average


def _positions(table_index: pd.MultiIndex, weights: pd.DataFrame, poly_id: str) -> np.ndarray:
    positions = table_index.get_indexer(_cell_index(weights))
    if (positions < 0).any():
        row = weights.iloc[int(np.flatnonzero(positions < 0)[0])]
        raise ValueError(f"{poly_id}: weighted cell Lon={row['Lon']} Lat={row['Lat']} is not "
                         "in the cell table; rerun the H-S step with the full grid")
    return positions


def polygon_averages(cell_average: pd.DataFrame, weights: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Long term monthly averages per polygon, one table per group (WBA, SR, SW).
    Sums cell by cell in weight table order, which fixes the last digits of the sums."""
    index = _cell_index(cell_average)
    values = cell_average[MONTH_NAMES].to_numpy(dtype=float)
    records = {group: [] for group in GROUPS}
    for poly_id, table in weights.items():
        positions = _positions(index, table, poly_id)
        total = np.zeros(12)
        total_weight = 0.0
        for position, pct in zip(positions, table["pct_k"].to_numpy(dtype=float)):
            total += values[position] * pct
            total_weight += pct
        average = np.round(total / total_weight, AVERAGE_DECIMALS) if total_weight > 0 else total
        group = polygon_group(poly_id)
        records[group].append({ID_COLUMN[group]: poly_id, **dict(zip(MONTH_NAMES, average))})
    return {group: pd.DataFrame(rows, columns=[ID_COLUMN[group]] + MONTH_NAMES)
            for group, rows in records.items() if rows}


def polygon_timeseries(table: pd.DataFrame, columns: list[str],
                       weights: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Every dated value per polygon, one table per group, unrounded."""
    index = _cell_index(table)
    values = table[columns].to_numpy(dtype=float)
    records = {group: [] for group in GROUPS}
    for poly_id, weight_table in weights.items():
        positions = _positions(index, weight_table, poly_id)
        cell_values = values[positions]
        pct = weight_table["pct_k"].to_numpy(dtype=float)
        valid = np.isfinite(cell_values)
        totals = np.where(valid, cell_values, 0.0).T @ pct
        valid_weights = valid.T @ pct
        series = np.divide(totals, valid_weights, out=np.full(len(columns), np.nan), where=valid_weights > 0)
        if not np.isfinite(series).all():
            raise ValueError(f"{poly_id}: missing weighted values")
        group = polygon_group(poly_id)
        records[group].append({ID_COLUMN[group]: poly_id, **dict(zip(columns, series))})
    return {group: pd.DataFrame(rows, columns=[ID_COLUMN[group]] + columns)
            for group, rows in records.items() if rows}


class PolygonAccumulator:
    """Weighted sums per polygon built one cell at a time.

    ``add`` takes a cell key (lat, lon rounded to 5 decimals) and its values (any length,
    the same for every cell). ``finish`` divides by each polygon's full weight sum and
    checks that every weighted cell was seen.
    """

    def __init__(self, weights: dict[str, pd.DataFrame], n_values: int, dtype=float):
        self.poly_ids = list(weights)
        self.memberships = cell_memberships(weights)
        self.weight_sums = weight_sums(weights)
        self.totals = np.zeros((len(self.poly_ids), n_values), dtype=dtype)
        self.seen: set = set()

    def add(self, key: tuple[float, float], values: np.ndarray) -> None:
        members = self.memberships.get(key)
        if not members:
            return
        for index, pct in members:
            self.totals[index] += pct * values
        self.seen.add(key)

    def finish(self) -> np.ndarray:
        missing = set(self.memberships) - self.seen
        if missing:
            lat, lon = sorted(missing)[0]
            raise ValueError(f"{len(missing)} weighted cells were never added; first lat={lat} lon={lon}")
        return self.totals / self.weight_sums[:, None]

    def tables(self, columns: list[str], values: np.ndarray | None = None) -> dict[str, pd.DataFrame]:
        """The finished values as one table per group with the polygon id first."""
        if values is None:
            values = self.finish()
        groups = group_ids({poly_id: None for poly_id in self.poly_ids})
        position = {poly_id: i for i, poly_id in enumerate(self.poly_ids)}
        out = {}
        for group, ids in groups.items():
            if not ids:
                continue
            frame = pd.DataFrame(values[[position[poly_id] for poly_id in ids]], columns=columns)
            frame.insert(0, ID_COLUMN[group], ids)
            out[group] = frame
        return out


def round_timeseries(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """The precision the step 11 csv files carry, applied in memory so the spline sees the
    same numbers whether it reads the csv or not."""
    out = {}
    for group, table in tables.items():
        rounded = table.copy()
        value_columns = [column for column in table.columns if column != ID_COLUMN[group]]
        rounded[value_columns] = table[value_columns].astype(float).round(TIMESERIES_DECIMALS)
        out[group] = rounded
    return out


# =============================================================================================
# 8. Daily ETo by cubic spline (manual section 9; step 12)
# =============================================================================================
# Manual: paste the monthly polygon ETo into the EToCum sheet of the workbook
# CS3_Table_9-xx_ETo_Spline2025.xlsm and run its createdaily macro. This section is a Python
# replica of that macro, per series and calendar year: the 12 monthly means (total / days in
# the month) sit at mid month positions X = 61, 92, ... 397, padded with the same year's
# November and December at X = 1, 32 and January and February at X = 426, 457; the cubic spline
# of Numerical Recipes "spline" (end derivatives 0) is evaluated at X = 47 to 411; January 1
# and December 31 get the mean of the two spline end values, January 2 to 5 and December 26 to
# 30 are linear ramps to it; a leap year repeats the last value, so February 29 gets the value
# of day 60 and December 31 a copy of December 30.
# The spline does not preserve the monthly totals (the daily values sum to more than the total
# in the winter trough and less in the summer peak: 1.85 percent mean absolute difference,
# annual sums within 0.3 percent). The workbook behaved the same way.
# Only the 172 CUP+ areas are carried (43 WBA, 12 subregions, 117 small watersheds): CUP+ has
# crop tables only for these.

# The CUP+ areas, named as CUP+ names them (WBA_02, WBA_SR_15, WBA_SW_3).
WBA_IDS = ["02", "03", "04", "05", "06", "07N", "07S", "08N", "08S", "09", "10",
           "11", "12", "13", "14", "15N", "15S", "16", "17N", "17S", "18", "19",
           "20", "21", "22", "23", "24", "25", "26N", "26S", "50", "60N", "60S",
           "61", "62", "63", "64", "71", "72", "73", "90", "91", "DETAW"]
SR_IDS = [1, 2, 6, 8, 10, 15, 16, 17, 18, 19, 20, 21]
SW_IDS = [3, 5, *range(6, 16), 20, 21, 25, 26, 28, 29, *range(30, 125), *range(126, 130)]

# Spline sheet, column E (X(I%)): Nov, Dec, Jan..Dec, Jan, Feb knot positions
KNOT_X = np.array([1, 32, 61, 92, 122, 153, 183, 214, 244, 275, 305, 336,
                   366, 397, 426, 457], dtype=float)
YP1 = 0.0                     # Spline!I1
YPN = 0.0                     # Spline!I2
END_COEFFICIENT = -0.25       # Spline!J4 and Spline!J19
FIRST_DAY_X = 47              # Splint row 50, January 1
LAST_DAY_X = 411              # Splint row 414, December 31
RAMP_DAYS = 5                 # Splint!R50 and Splint!R414 divide by 5


def series_sources() -> list[tuple[str, str, str]]:
    """(CUP+ series name, polygon group, polygon id) for every carried series."""
    return ([(f"WBA_{wba}", "WBA", wba) for wba in WBA_IDS]
            + [(f"WBA_SR_{n}", "SR", f"SR_{n}") for n in SR_IDS]
            + [(f"WBA_SW_{n}", "SW", f"SW_{n}") for n in SW_IDS])


def cup_series_table(timeseries: dict[str, pd.DataFrame], index: pd.DatetimeIndex) -> pd.DataFrame:
    """Monthly totals (inches) of the 172 CUP+ series, month end index: the EToCum table.
    ``timeseries`` holds one table per group with the polygon id in its first column."""
    columns = {}
    for name, group, region in series_sources():
        table = timeseries.get(group)
        if table is None:
            raise KeyError(f"{name}: no {group} table")
        frame = table.set_index(table.columns[0])
        if region not in frame.index:
            raise KeyError(f"{name}: region {region} not found in the {group} table; "
                           "rerun step 0 and the polygon averaging step")
        values = frame.loc[region].to_numpy(dtype=float)
        if len(values) != len(index):
            raise ValueError(f"{name}: {len(values)} monthly values for {len(index)} months")
        columns[name] = values
    return pd.DataFrame(columns, index=index)


def second_derivatives(y: np.ndarray) -> np.ndarray:
    """Spline!K4:K19 for knot values y of shape (16, n_series)."""
    x = KNOT_X
    n_knots = len(x)
    u = np.zeros_like(y)
    y2 = np.zeros_like(y)
    u[0] = (3 / (x[1] - x[0])) * ((y[1] - y[0]) / (x[1] - x[0]) - YP1)
    y2[0] = END_COEFFICIENT
    for i in range(1, n_knots - 1):
        sig = (x[i] - x[i - 1]) / (x[i + 1] - x[i - 1])
        p = sig * y2[i - 1] + 2
        u[i] = (6 * (((y[i + 1] - y[i]) / (x[i + 1] - x[i]))
                     - ((y[i] - y[i - 1]) / (x[i] - x[i - 1])))
                / (x[i + 1] - x[i - 1]) - sig * u[i - 1]) / p
        y2[i] = (sig - 1) / p
    u[-1] = (3 / (x[-1] - x[-2])) * (YPN - (y[-1] - y[-2])) / (x[-1] - x[-2])
    k = np.zeros_like(y)
    k[-1] = u[-1]                 # Spline!K19 = J19 * K20 + I19 with K20 blank
    for i in range(n_knots - 2, -1, -1):
        k[i] = y2[i] * k[i + 1] + u[i]
    return k


def spline_daily(monthly_means: np.ndarray) -> np.ndarray:
    """Splint!T50:T414 for monthly means of shape (12, n_series) -> (365, n_series)."""
    y = np.vstack([monthly_means[10:12], monthly_means, monthly_means[0:2]])
    k = second_derivatives(y)

    day_x = np.arange(FIRST_DAY_X, LAST_DAY_X + 1, dtype=float)
    khi = np.searchsorted(KNOT_X, day_x, side="left")     # first knot >= X
    klo = khi - 1
    h = KNOT_X[khi] - KNOT_X[klo]
    a = (KNOT_X[khi] - day_x) / h
    b = (day_x - KNOT_X[klo]) / h
    linear = a[:, None] * y[klo] + b[:, None] * y[khi]
    cubic = linear + (((a ** 3 - a)[:, None] * k[klo]
                       + (b ** 3 - b)[:, None] * k[khi])) * (h ** 2)[:, None] / 6

    daily = cubic.copy()
    first, last = 0, LAST_DAY_X - FIRST_DAY_X
    daily[first] = (cubic[first] + cubic[last]) / 2
    daily[last] = (cubic[first] + cubic[last]) / 2
    ramp_start = (cubic[first + RAMP_DAYS] - daily[first]) / RAMP_DAYS
    for i in range(first + 1, first + RAMP_DAYS):
        daily[i] = daily[i - 1] + ramp_start
    ramp_end = (daily[last] - cubic[last - RAMP_DAYS - 1]) / RAMP_DAYS
    for i in range(last - RAMP_DAYS, last):
        daily[i] = daily[i - 1] + ramp_end
    return daily


def spline_year(totals: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Daily ETo of one year from its 12 monthly totals (rows) and month lengths: 365 rows, or
    366 when February has 29 days."""
    daily = spline_daily(totals / lengths[:, None])
    if lengths[1] == 29:
        daily = np.vstack([daily, daily[-1:]])     # Splint!T415 = N414
    return daily


def disaggregate(monthly: pd.DataFrame, chunk: int | None = None) -> pd.DataFrame:
    """Daily ETo (inches/day) for every calendar year of a month end indexed table of monthly
    totals. A single series follows the Gregorian calendar of its years. A Product B chunk's
    table runs January 1920 to December 2021 (chunk_monthly_window), so each year from 1921 is
    one of the chunk's stamp years: its totals are divided by the stamp month lengths, its
    spline runs over the stamp year's days, and those days are laid out on 1920-2021 like the
    chunk's precipitation (chunk_daily_window)."""
    years = range(monthly.index[0].year, monthly.index[-1].year + 1)

    def totals(year: int) -> np.ndarray:
        table = monthly.loc[str(year)]
        if len(table) != 12:
            raise ValueError(f"{year}: {len(table)} months in the monthly table, expected 12")
        return table.to_numpy(dtype=float)

    if chunk is None:
        return pd.concat([pd.DataFrame(spline_year(totals(year), gregorian_month_lengths(year)),
                                       index=pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D"),
                                       columns=monthly.columns)
                          for year in years])
    if (years[0], years[-1]) != (CHUNK_START_YEAR, CHUNK_END_YEAR):
        raise ValueError(f"chunk {chunk}: the monthly table runs {years[0]}-{years[-1]}, not "
                         f"{CHUNK_START_YEAR}-{CHUNK_END_YEAR}")
    first_stamp_year = wgen_calendar.chunk_span(chunk)[0][0]      # labelled 1921
    stamp_days = np.vstack([spline_year(totals(year), stamp_month_lengths(first_stamp_year + year - 1921))
                            for year in range(CHUNK_START_YEAR + 1, CHUNK_END_YEAR + 1)])
    return pd.DataFrame(wgen_calendar.days_1920_2021(stamp_days), index=chunk_day_index(),
                        columns=monthly.columns)


def write_etocum_table(monthly: pd.DataFrame, path: Path) -> None:
    """The EToCum table as csv: Date (month end, m/d/yyyy) and one column per CUP+ series,
    inches per month with 6 decimals, the spline's input kept beside its output."""
    output = monthly.reset_index(names="Date")
    output["Date"] = [f"{d.month}/{d.day}/{d.year}" for d in output["Date"]]
    output.to_csv(path, index=False, float_format="%.6f")


def eto_date_labels(index: pd.DatetimeIndex) -> list[str]:
    """m/d/yyyy, the date format CUP+ reads for ETo."""
    return [f"{d.month}/{d.day}/{d.year}" for d in index]


def write_daily_csv(daily: pd.DataFrame, path: Path) -> None:
    output = daily.copy()
    output.insert(0, "Date", eto_date_labels(output.index))
    output.to_csv(path, index=False)


def read_daily_csv(path: Path) -> pd.DataFrame:
    """A daily ETo csv back into a date indexed table."""
    table = pd.read_csv(path)
    if table.columns.size == 0 or table.columns[0] != "Date":
        raise ValueError(f"{path} must start with a Date column")
    index = pd.DatetimeIndex(pd.to_datetime(table["Date"], format="%m/%d/%Y"))
    return table.drop(columns="Date").set_index(index)


# =============================================================================================
# 9. Daily WBA precipitation for CUP+ (step 13)
# =============================================================================================
# Not in the manual. CUP+ needs daily precipitation for every WBA it runs. Each WBA takes the
# series CalSimHydro reads, written by mod_hydrology/calsimhydro/_1_compile_precip.py for the
# same set (WBA_91 gets WBA 90's there), so CUP+ and CalSimHydro see the same rain. WBA_DETAW,
# which CalSimHydro has no WBA for, is the step 0 weighted mean of its cells,
# P(d) = sum_k(w_k P_k(d)) / sum_k(w_k), read through utils.wgen. Product B takes the chunk
# files of _1, laid out like chunk_daily_window. Output: a csv with a Date column (01JAN1920,
# the format CUP+ reads) and one column per WBA named like the ETo series (WBA_02 ... WBA_91,
# WBA_DETAW), inches per day with 6 decimals.

PRECIP_DECIMALS = 6
DETAW_ID = "DETAW"


def product_days(product: Product) -> pd.DatetimeIndex:
    """The days of a set's daily tables: its years, or the chunk window for Product B."""
    if product.is_chunked:
        return chunk_day_index()
    return pd.date_range(f"{product.start_year}-01-01", f"{product.end_year}-12-31", freq="D")


def calsimhydro_wba_precip(product: Product, wba_id: str, dates: pd.DatetimeIndex,
                           chunk: int | None = None) -> np.ndarray:
    """Daily precipitation (in) of one WBA on ``dates``, from the csv of CalSimHydro _1:
    date and value rows, or year, month, day and value rows for a Product B chunk."""
    path = require(calsimhydro_precip_dir(product) / f"WBA_{wba_id}_pcp{chunk_suffix(chunk)}.csv",
                   f"run mod_hydrology/calsimhydro/_1_compile_precip.py --product {product.key} first")
    if chunk is None:
        table = pd.read_csv(path, header=None, names=["date", "pcp"])
        index = pd.to_datetime(table["date"])
    else:
        table = pd.read_csv(path, header=None, names=["year", "month", "day", "pcp"])
        index = pd.to_datetime(table[["year", "month", "day"]])
    series = pd.Series(table["pcp"].to_numpy(dtype=float), index=pd.DatetimeIndex(index)).reindex(dates)
    if series.isna().any():
        raise ValueError(f"{path.name} does not cover {dates[0].date()} through {dates[-1].date()}")
    return series.to_numpy()


def detaw_precip(product: Product) -> pd.Series:
    """Daily precipitation (in) of WBA_DETAW, the step 0 weighted mean of its cells, on
    every row of the weather files: indexed by date, or by stamp day for Product B."""
    weights = read_weight_table(require(factor_step_dir(0) / f"WTable_{DETAW_ID}.csv",
                                        "run _3_refet_f1_factors.py --step 0 first"))
    cells = [(wgen.met_path(product.key, f"{lat:.5f}", f"{lon:.5f}"), pct)
             for lon, lat, pct in weights.itertuples(index=False)]
    daily = wgen.weighted_daily(product.key, cells, ["precip"])
    index = pd.RangeIndex(len(daily)) if product.is_chunked else wgen.dates(daily)
    return pd.Series(daily["precip"].to_numpy(dtype=float) / MM_PER_INCH, index=index)


def precip_table(product: Product, detaw: pd.Series, chunk: int | None = None) -> pd.DataFrame:
    """The step 13 table of a set, or of one Product B chunk: Date, then one column per WBA
    in the order of ``WBA_IDS``."""
    dates = product_days(product)
    columns = {}
    for wba_id in WBA_IDS:
        if wba_id != DETAW_ID:
            columns[f"WBA_{wba_id}"] = calsimhydro_wba_precip(product, wba_id, dates, chunk)
        elif product.is_chunked:
            columns[f"WBA_{wba_id}"] = chunk_daily_window(detaw.to_numpy(), chunk)
        else:
            values = detaw.reindex(dates)
            if values.isna().any():
                raise ValueError(f"the WBA_DETAW cells do not cover {dates[0].date()} through "
                                 f"{dates[-1].date()}")
            columns[f"WBA_{wba_id}"] = values.to_numpy()
    table = pd.DataFrame(columns)
    table.insert(0, "Date", precip_date_labels(dates))
    return table


def precip_date_labels(dates: pd.DatetimeIndex) -> list[str]:
    """ddMONyyyy in upper case, the date format CUP+ reads for precipitation."""
    return list(dates.strftime("%d%b%Y").str.upper())


def write_precip_csv(table: pd.DataFrame, path: Path) -> None:
    table.to_csv(path, index=False, float_format=f"%.{PRECIP_DECIMALS}f")


def read_precip_csv(path: Path) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    table = pd.read_csv(path)
    if "Date" not in table.columns:
        raise ValueError(f"{path} has no Date column")
    dates = pd.DatetimeIndex(pd.to_datetime(table["Date"], format="%d%b%Y"))
    return table, dates


def wba_columns(columns) -> list[str]:
    """The WBA series among precipitation or ETo headers (not subregions or watersheds)."""
    return [column for column in columns
            if column.startswith("WBA_") and not column.startswith(("WBA_SR_", "WBA_SW_"))]


# =============================================================================================
# 10. DSS writers and checks (steps 11 and 14)
# =============================================================================================
# - CS3_RefETo.dss: monthly reference ETo per WBA, /CALSIM/WBA 02/REF-ET//1MON/REFETO/,
#   IN/MONTH, PER-CUM (step 11);
# - CS3_ET.dss: monthly crop ET per WBA and land use type,
#   /IWFM/WBA02_AL_ET/RATE_INCH//1MON/EVAPOTRANSPIRATION/, IN, PER-CUM, plus the 106 crop ET
#   records that do not depend on climate, copied from the existing input: the bare soil (SL)
#   and urban (UR) climatologies of the 42 WBAs (part D 01JAN4000, urban zero in Dec-Feb) and
#   2 RI terms in 11 decade blocks (step 14). CUP+ writes no SL or UR record.
# Every DSS goes through utils.dss_io.open_dss (pydsstools, long path junction).

STATIC_CROP_ET_WBAS = {
    "WBA02", "WBA03", "WBA04", "WBA05", "WBA06", "WBA07N", "WBA07S",
    "WBA08N", "WBA08S", "WBA09", "WBA10", "WBA11", "WBA12", "WBA13",
    "WBA14", "WBA15N", "WBA15S", "WBA16", "WBA17N", "WBA17S", "WBA18",
    "WBA19", "WBA20", "WBA21", "WBA22", "WBA23", "WBA24", "WBA25",
    "WBA26N", "WBA26S", "WBA50", "WBA60N", "WBA60S", "WBA61", "WBA62",
    "WBA63", "WBA64", "WBA71", "WBA72", "WBA73", "WBA90", "WBA91",
}
CLIMATOLOGY_LAND_USES = ("SL", "UR")
CLIMATOLOGY_PART_B = {f"{wba}_{land_use}_ET" for wba in STATIC_CROP_ET_WBAS
                      for land_use in CLIMATOLOGY_LAND_USES}
STATIC_RI_CROP_ET_PART_B = {"WBA02_RI_ET", "WBA03_RI_ET"}
STATIC_RI_CROP_ET_D_PARTS = {f"01JAN{year}" for year in range(1920, 2030, 10)}
LEGACY_RECORD_COUNT = len(CLIMATOLOGY_PART_B) + len(STATIC_RI_CROP_ET_PART_B) * len(STATIC_RI_CROP_ET_D_PARTS)


def remove_dss_files(path: Path) -> None:
    """Delete a DSS file and its catalog sidecars."""
    for suffix in (".dss", ".dsc", ".dsd", ".dsk"):
        stale = Path(path).with_suffix(suffix)
        if stale.exists():
            stale.unlink()


# -- step 11: reference ETo --------------------------------------------------------

def refeto_part_b(wba_id: str) -> str:
    """``02`` -> ``WBA 02``, ``07N`` -> ``WBA 07N``, ``DETAW`` -> ``WBA DETAW``."""
    return f"WBA_{wba_id}".replace("_", " ")


def write_refeto_dss(wba_table: pd.DataFrame, start_year: int, path: Path) -> int:
    """Monthly WBA reference ETo. ``wba_table`` has the WBA id first, then one column per
    month from January of ``start_year``. Written to a temporary file and moved into place
    after its catalog has been checked."""
    from pydsstools.core import TimeSeriesContainer
    from utils import dss_io

    path = Path(path)
    n_months = wba_table.shape[1] - 1
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".CS3_RefETo_", suffix=".dss", dir=path.parent)
    os.close(handle)
    temp_path = Path(temp_name)
    temp_path.unlink()
    expected = set()
    try:
        with dss_io.open_dss(temp_path, version=6, catalog_flag=False) as dss:
            for row in wba_table.itertuples(index=False, name=None):
                wba_id, *values = row
                if len(values) != n_months:
                    raise ValueError(f"{wba_id}: {len(values)} monthly values, expected {n_months}")
                tsc = TimeSeriesContainer()
                tsc.pathname = f"/CALSIM/{refeto_part_b(str(wba_id))}/REF-ET//1MON/REFETO/"
                tsc.startDateTime = f"31JAN{start_year} 24:00:00"
                tsc.numberValues = len(values)
                tsc.units = "IN/MONTH"
                tsc.type = "PER-CUM"
                tsc.interval = 1
                tsc.values = np.asarray(values, dtype=float)
                dss.put_ts(tsc)
                expected.add(refeto_part_b(str(wba_id)))
        with dss_io.open_dss(temp_path, version=6, catalog_flag=False) as dss:
            paths = dss.getPathnameList("/CALSIM/*/REF-ET/*/1MON/REFETO/") or []
        actual = {pathname.strip("/").split("/")[1] for pathname in paths}
        if actual != expected:
            raise ValueError(f"RefETo DSS check failed; missing={sorted(expected - actual)}, "
                             f"unexpected={sorted(actual - expected)}")
        remove_dss_files(path)
        os.replace(temp_path, path)
    finally:
        remove_dss_files(temp_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"RefETo DSS was not created: {path}")
    return len(expected)


# -- step 14: CalSimHydro ET DSS ---------------------------------------------------------

ET_PART_A, ET_PART_C, ET_PART_E, ET_PART_F = "IWFM", "RATE_INCH", "1MON", "EVAPOTRANSPIRATION"
ET_UNITS, ET_TYPE = "IN", "PER-CUM"


def calsimhydro_part_b(part_b: str) -> str:
    """CalSimHydro names WBA records WBA02_AL_ET; CUP+ names the areas WBA_02."""
    return part_b.replace("WBA_", "WBA", 1) if part_b.startswith("WBA_") else part_b


def et_pathname(part_b: str) -> str:
    return f"/{ET_PART_A}/{part_b}/{ET_PART_C}//{ET_PART_E}/{ET_PART_F}/"


def write_land_use_et(path: Path, series: dict[str, pd.Series], start_year: int, n_months: int) -> int:
    """Monthly crop ET per WBA and land use type from January of ``start_year`` into a new
    DSS, replacing an existing file."""
    from pydsstools.core import TimeSeriesContainer
    from utils import dss_io

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    remove_dss_files(path)
    with dss_io.open_dss(path, version=6, catalog_flag=False) as dss:
        for part_b, values in series.items():
            if len(values) != n_months:
                raise ValueError(f"{part_b}: {len(values)} months, expected {n_months}")
            tsc = TimeSeriesContainer()
            tsc.pathname = et_pathname(part_b)
            tsc.startDateTime = f"31JAN{start_year} 24:00:00"
            tsc.numberValues = n_months
            tsc.units = ET_UNITS
            tsc.type = ET_TYPE
            tsc.interval = 1
            tsc.values = np.asarray(values, dtype=float)
            dss.put_ts(tsc)
    return len(series)


def validate_land_use_et(path: Path, part_bs: list[str], start_year: int, end_year: int) -> int:
    """Every land use record reads back with finite values over January of ``start_year``
    to December of ``end_year``."""
    from utils import dss_io

    expected = pd.period_range(f"{start_year}-01", f"{end_year}-12", freq="M")  # period-resample
    with dss_io.open_dss(path, version=6, catalog_flag=False) as dss:
        for part_b in part_bs:
            ts = dss.read_ts(et_pathname(part_b), trim_missing=True)
            periods = pd.DatetimeIndex(ts.pytimes).shift(-1, freq="D").to_period("M")
            values = np.asarray(ts.values, dtype=float)
            if not periods.equals(expected) or not np.isfinite(values).all():
                raise ValueError(f"DSS record {part_b} does not cover {expected[0]} through "
                                 f"{expected[-1]} with finite values ({periods.min()} through "
                                 f"{periods.max()})")
    return len(part_bs)


def copy_legacy_crop_et_records(target_dss: Path, reference_dss: Path) -> int:
    """Copy the 84 SL and UR climatologies and the 22 RI decade block records from the
    historical CalSimHydro ET input into the target, and verify they are all there. Stops if
    the target already holds an SL or UR record: CalSimHydro reads these pathnames with a blank
    part D, so a CUP+ series beside the climatology would be ambiguous."""
    from utils import dss_io

    reference_dss = Path(reference_dss)
    target_dss = Path(target_dss)
    if not reference_dss.is_file():
        raise FileNotFoundError(f"reference CropET DSS not found: {reference_dss}")
    if not target_dss.is_file():
        raise FileNotFoundError(f"target CalSimHydro DSS not found: {target_dss}")

    with dss_io.open_dss(reference_dss, version=6, catalog_flag=False) as source:
        with dss_io.open_dss(target_dss, version=6, catalog_flag=False) as target:
            source_paths = source.getPathnameList("/*/*/*/*/*/*/") or []
            target_paths = target.getPathnameList("/*/*/*/*/*/*/") or []
            existing = {pathname.upper() for pathname in target_paths}
            clashes = sorted({pathname.strip("/").split("/")[1].upper() for pathname in target_paths}
                             & CLIMATOLOGY_PART_B)
            if clashes:
                raise ValueError(f"{target_dss} already holds {len(clashes)} SL/UR records, first "
                                 f"{clashes[0]}; they come only from the climatologies")
            required = []
            found_climatology = set()
            found_ri = {part_b: set() for part_b in STATIC_RI_CROP_ET_PART_B}
            for pathname in source_paths:
                parts = pathname.strip("/").split("/")
                if len(parts) != 6:
                    continue
                _, part_b, part_c, part_d, _, part_f = parts
                part_b = part_b.upper()
                if part_c.upper() != "RATE_INCH" or part_f.upper() != "EVAPOTRANSPIRATION":
                    continue
                if part_b in CLIMATOLOGY_PART_B and part_d.upper() == "01JAN4000":
                    found_climatology.add(part_b)
                    required.append(pathname)
                elif part_b in STATIC_RI_CROP_ET_PART_B:
                    found_ri[part_b].add(part_d.upper())
                    if part_d.upper() in STATIC_RI_CROP_ET_D_PARTS:
                        required.append(pathname)
            missing_climatology = CLIMATOLOGY_PART_B - found_climatology
            missing_ri = {part_b: sorted(STATIC_RI_CROP_ET_D_PARTS - parts_d)
                          for part_b, parts_d in found_ri.items() if STATIC_RI_CROP_ET_D_PARTS - parts_d}
            if missing_climatology or missing_ri:
                raise ValueError(f"reference DSS lacks legacy CropET records: "
                                 f"SL/UR={sorted(missing_climatology)}, RI blocks={missing_ri}")
            if len(required) != LEGACY_RECORD_COUNT:
                raise ValueError(f"reference DSS has duplicate legacy CropET pathnames; found "
                                 f"{len(required)}, expected {LEGACY_RECORD_COUNT}")
            to_copy = [pathname for pathname in required if pathname.upper() not in existing]
            for pathname in to_copy:
                target.copyRecordsFrom(source, pathname, pathname)
            final = {pathname.upper() for pathname in target.getPathnameList("/*/*/*/*/*/*/") or []}
            still_missing = [pathname for pathname in required if pathname.upper() not in final]
            if still_missing:
                raise ValueError(f"target DSS lacks legacy CropET records after copying: {still_missing}")
    return len(to_copy)


# =============================================================================================
# 11. The CUP+ run (step 14)
# =============================================================================================
# Not in the manual. PyCUP is DWR's CUP+ (Consumptive Use Program Plus) in Python, kept at
# BASE/PyCUP outside this repository; its package pycup is imported from there and runs in this
# process. For every WBA, pycup.getET turns daily ETo and precipitation (mm) into the daily ETc
# of each crop in the WBA's crop tables, one crop per worker; precipitation enters only through
# its wetting test (rain above twice the 5 day mean ETo). The daily ETc is summed to months
# (inches), and pycup.getCropWeights weights the crops of each CalSimHydro land use type, with
# the WBA's Sacramento or San Joaquin weights and its cover crop ratio, into one monthly series
# per WBA and land use. pycup's calcMETo and daily2month fail under pandas 3, so this section
# computes the 5 day mean ETo and the monthly sums itself; PyCUP's driver
# (08_AbvCUPmodel_parrallel.py) is not used.

TABLE_FILES = ("ccTable.csv", "WBATable.csv")
CROP_DATE_COLUMNS = ["PlantingMonth", "PlantingDay", "HarvestMonth", "HarvestDay"]


def load_pycup():
    """The pycup package of BASE/PyCUP. Import it before the worker pool starts, so the
    workers inherit its folder on sys.path."""
    folder = str(pycup_dir())
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import pycup
    return pycup


def cup_tables_dir() -> Path:
    return pycup_dir() / "tables"


def validate_crop_inputs(headers: list[str]) -> None:
    tables = cup_tables_dir()
    required = [tables / name for name in TABLE_FILES]
    for header in headers:
        required.append(tables / "CropRef" / f"CropRef_{header}.csv")
        required.append(tables / "csh_CropTable" / f"csh_CropTable_{header}.csv")
    unavailable = [path for path in required if not path.is_file()]
    if unavailable:
        listing = "\n  ".join(str(path) for path in unavailable[:10])
        more = f"\n  ... and {len(unavailable) - 10} more" if len(unavailable) > 10 else ""
        raise FileNotFoundError(f"CUP+ crop tables are missing ({len(unavailable)}):\n  {listing}{more}")


def cup_inputs(daily_eto: pd.DataFrame, precipitation: pd.DataFrame,
               precip_dates: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """The WBA columns of the daily ETo and the matching precipitation columns, both date
    indexed, in inches per day."""
    headers = wba_columns(daily_eto.columns)
    if not headers:
        raise ValueError("the daily ETo has no WBA series")
    if not daily_eto.index.equals(precip_dates):
        raise ValueError("ETo and precipitation days differ")
    missing = sorted(set(headers) - set(precipitation.columns))
    if missing:
        raise ValueError(f"precipitation table lacks ETo headers: {missing}")
    eto = daily_eto[headers].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(eto.to_numpy(dtype=float)).all():
        raise ValueError("daily ETo contains missing or nonnumeric values")
    precip = precipitation[headers].astype(float).set_axis(daily_eto.index)
    if precip.isna().any().any():
        raise ValueError("precipitation table contains missing values")
    return eto, precip, headers


def crop_table(wba: str) -> pd.DataFrame:
    """The CalSimHydro crop table of a WBA: land use, crop weights, cover crops."""
    return pd.read_csv(cup_tables_dir() / "csh_CropTable" / f"csh_CropTable_{wba}.csv").dropna(how="all")


def five_day_mean_eto(eto: pd.Series) -> pd.Series:
    """Centered 5 day mean ETo; the first and last two days filled as CUP+ fills them."""
    meto = eto.rolling(5, center=True).mean()
    meto.iloc[0] = eto.iloc[1]
    meto.iloc[1] = meto.iloc[2]
    meto.iloc[-1] = eto.iloc[-3:].mean()
    meto.iloc[-2] = eto.iloc[-4:].mean()
    return meto


def daily_crop_etc(pycup, wba: str, eto_in: pd.Series, precip_in: pd.Series, pool) -> dict[str, pd.Series]:
    """Daily ETc (mm) of every crop of a WBA, keyed <WBA>_<CropNumber_CSH>."""
    crops = crop_table(wba).merge(
        pd.read_csv(cup_tables_dir() / "CropRef" / f"CropRef_{wba}.csv").dropna(how="all"),
        how="left", left_on="CropNumber", right_on="Crop Number",
    )
    crops[CROP_DATE_COLUMNS] = crops[CROP_DATE_COLUMNS].astype(int)
    if crops["CropNumber_CSH"].duplicated().any():
        raise ValueError(f"{wba}: duplicate CropNumber_CSH in its crop table")
    weather = pd.DataFrame({"eto": eto_in * MM_PER_INCH, "precip": precip_in * MM_PER_INCH})
    weather["METo"] = five_day_mean_eto(weather["eto"])
    results = pool.map(pycup.getET, [(weather, row) for _, row in crops.iterrows()])
    return {f"{wba}_{crop}": etc for crop, etc in zip(crops["CropNumber_CSH"], results)}


def land_use_et(pycup, monthly: pd.DataFrame, wbas: list[str]) -> dict[str, pd.Series]:
    """Monthly ET (in) of each CalSimHydro land use type, the weighted sum of its crops' ETc,
    keyed by CalSimHydro part B (WBA_02 and AL give WBA02_AL_ET). The SL and UR land uses are
    left out: CalSimHydro takes them from the climatologies (copy_legacy_crop_et_records)."""
    wba_table = pd.read_csv(cup_tables_dir() / "WBATable.csv")
    cc_table = pd.read_csv(cup_tables_dir() / "ccTable.csv")
    out = {}
    for wba in sorted(wbas):
        table = crop_table(wba)
        sacramento = wba_table.loc[wba_table.WBA == wba, "SacRSJR"].iloc[0] == 1
        cc_ratio = cc_table.loc[cc_table.WBA == wba, "ccRatio"].iloc[0]
        for land_use in table["CSH_CrpAbv"].unique():
            if land_use in CLIMATOLOGY_LAND_USES:
                continue
            crops = table[table["CSH_CrpAbv"] == land_use].copy()
            crops["RegionWeight"] = crops["SacWeighting"] if sacramento else crops["SJWeighting"]
            weights = pycup.getCropWeights(crops, cc_ratio)
            et = sum(monthly[f"{wba}_{crop}"] * weight
                     for crop, weight in zip(crops["CropNumber_CSH"], weights))
            out[calsimhydro_part_b(f"{wba}_{land_use}_ET")] = et
    return out


# =============================================================================================
# 12. Pipeline steps and the Product B pass
# =============================================================================================
# One function per step of the two programs. Each reads the files of the previous step and
# writes its own, so any step can be run alone; when an input file is missing the program
# stops and says which step to run first. Historical_Unsplit and Product A go through the
# steps one at a time, with the per cell tables written in the step folders. Product B, whose
# per cell tables would be gigabytes, goes through steps 10 and 11 in one pass over the
# weather that keeps only the polygon series (see product_b_pass).

def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def require(path: Path, hint: str) -> Path:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; {hint}")
    return path


def cells_frame(cells: list[Cell]) -> pd.DataFrame:
    return pd.DataFrame({"Lon": [cell.lon for cell in cells], "Lat": [cell.lat for cell in cells]})


# -- Hargreaves-Samani table (manual section 5; steps 5 and 10) ----------------------------

def hs_table_step(product: Product, out_dir: Path, workers: int | None) -> pd.DataFrame:
    """H-S ETo per cell and month for every weather file of the product, with the Ra
    diagnostic tables. Returns the monthly table (Lon, Lat, Jan-<start> ...)."""
    cells = scan_cells(product.weather_dir)
    require_hydrated(cells)
    log(f"step H-S: {len(cells):,} cells in {product.weather_dir}")
    tasks = make_tasks(cells, product.key, product.start_year, product.end_year, want_ra=True)
    results = list(run_cells(tasks, workers))
    table = monthly_table(results, product.start_year, product.end_year)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_dir / ETO_MONTHLY_CSV, index=False)
    monthly_ra, daily_ra = ra_tables(results)
    monthly_ra.to_csv(out_dir / MONTHLY_RA_CSV, index=False)
    daily_ra.to_csv(out_dir / DAILY_RA_CSV, index=False)
    log(f"  wrote {ETO_MONTHLY_CSV} ({len(table):,} cells, {table.shape[1] - 2} months)")
    return table


def read_hs_table(path: Path, product: Product) -> pd.DataFrame:
    table = pd.read_csv(path)
    expected = month_columns(product.start_year, product.end_year)
    if list(table.columns) != ["Lon", "Lat"] + expected:
        raise ValueError(f"{path} must hold Lon, Lat and Jan-{product.start_year} through "
                         f"Dec-{product.end_year}")
    return table


# -- F1 (manual section 7; fit in step 7, applied in step 10) -------------------------------

def f1_fit(table: pd.DataFrame, out_dir: Path) -> np.ndarray:
    """F1 fit on the table's own H-S ETo over the calibration years (manual steps ii to iv):
    step 7, on the Historical_Unsplit weather. Writes the F1 table and the H-S monthly average of
    those years, F1's denominator; returns the factors before their rounding to 6 decimals,
    which step 7 applies to the historical series."""
    hs_average, hs_diagnostic = hs_monthly_average(table, F1_START_YEAR, F1_END_YEAR)
    cimis_dir = require(cimis_monthly_dir(), "run _3_refet_f1_factors.py --step 6 first")
    cimis_average = load_cimis_monthly_average(cimis_dir, table)
    values, f1_table = compute_f1(hs_average, cimis_average, table)
    out_dir = Path(out_dir)
    f1_table.to_csv(out_dir / F1_TABLE_CSV, index=False)
    hs_diagnostic.to_csv(out_dir / named(HS_AVG_F1_PERIOD_CSV, start=F1_START_YEAR, end=F1_END_YEAR),
                         index=False)
    outside = int((~np.isfinite(cimis_average).all(axis=1)).sum())
    log(f"  F1 fit: {len(table) - outside:,} cells corrected, {outside:,} outside CIMIS")
    return values


def f1_from_table(path: Path, cells: pd.DataFrame, out_dir: Path) -> np.ndarray:
    """The F1 table of step 7, or any other table, aligned to these cells and copied into
    ``out_dir``: the factors step 10 applies to every set."""
    path = require(path, "run _3_refet_f1_factors.py --step 7 first or pass --f1-table")
    values = align_f1(read_f1_table(path), cells)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, out_dir / F1_TABLE_CSV)
    return values


def apply_f1_step(table: pd.DataFrame, values: np.ndarray, out_dir: Path) -> pd.DataFrame:
    """Manual step v; writes the corrected per cell table."""
    corrected = apply_f1(table, values)
    corrected.to_csv(Path(out_dir) / ETO_CORRECTED_CSV, index=False)
    log(f"  wrote {ETO_CORRECTED_CSV}")
    return corrected


# -- polygon averages (manual section 8; steps 8 and 11) ------------------------------------

def load_weights() -> dict[str, pd.DataFrame]:
    step0 = require(factor_step_dir(0), "run _3_refet_f1_factors.py --step 0 first")
    return load_weight_tables(step0)


def polygon_step(corrected: pd.DataFrame, columns: list[str], weights: dict[str, pd.DataFrame],
                 out_dir: Path) -> dict[str, pd.DataFrame]:
    """Long term monthly averages and full monthly series per polygon, written per group.
    Returns the unrounded series tables."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    averages = polygon_averages(longterm_monthly_average(corrected, columns), weights)
    series = polygon_timeseries(corrected, columns, weights)
    write_polygon_tables(out_dir, averages, series)
    return series


def write_polygon_tables(out_dir: Path, averages: dict[str, pd.DataFrame] | None,
                         series: dict[str, pd.DataFrame] | None, chunk: int | None = None) -> None:
    if averages:
        for group, table in averages.items():
            table.to_csv(Path(out_dir) / named(AVERAGED_CSV, group=group), index=False)
    if series:
        for group, table in series.items():
            table.to_csv(Path(out_dir) / named(TIMESERIES_CSV, chunk, group=group), index=False,
                         float_format="%.6f")
    counts = ", ".join(f"{len(table)} {group}" for group, table in (series or averages).items())
    log(f"  wrote polygon tables{chunk_suffix(chunk)}: {counts}")


def read_polygon_series(step_dir: Path, start_year: int, end_year: int,
                        chunk: int | None = None) -> dict[str, pd.DataFrame]:
    columns = month_columns(start_year, end_year)
    tables = {}
    for group in GROUPS:
        path = require(Path(step_dir) / named(TIMESERIES_CSV, chunk, group=group),
                       "run the polygon averaging step first")
        table = pd.read_csv(path, dtype={ID_COLUMN[group]: str})
        if list(table.columns) != [ID_COLUMN[group]] + columns:
            raise ValueError(f"{path} must hold {ID_COLUMN[group]} and Jan-{start_year} through Dec-{end_year}")
        tables[group] = table
    return tables


def refeto_step(wba_series: pd.DataFrame, product: Product, chunk: int | None = None) -> Path:
    path = calsimhydro_et_dir(product) / named(REFETO_DSS, chunk)
    count = write_refeto_dss(wba_series, product.start_year, path)
    log(f"  wrote {path.name} ({count} WBA series)")
    return path


# -- spline (manual section 9; step 12) -------------------------------------------------------

def spline_step(product: Product, step11_dir: Path, out_dir: Path, chunk: int | None = None) -> Path:
    index = pd.date_range(f"{product.start_year}-01-01", periods=12 * product.n_years, freq="ME")
    series = read_polygon_series(step11_dir, product.start_year, product.end_year, chunk)
    monthly = cup_series_table(series, index)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_etocum_table(monthly, out_dir / named(ETOCUM_CSV, chunk))
    daily = disaggregate(monthly, chunk)
    path = out_dir / named(ETO_DAILY_CSV, chunk)
    write_daily_csv(daily, path)
    log(f"  wrote {path.name} ({len(daily):,} days, {daily.shape[1]} series)")
    return path


# -- daily precipitation (step 13) ---------------------------------------------------------------

def precip_step(product: Product, chunks: list) -> None:
    """Daily WBA precipitation of a set, or of each Product B chunk in ``chunks``."""
    log(f"step 13: CalSimHydro WBA precipitation of {product.name} and the WBA_DETAW cells")
    detaw = detaw_precip(product)
    out_dir = product_step_dir(product, 13)
    out_dir.mkdir(parents=True, exist_ok=True)
    for chunk in chunks:
        table = precip_table(product, detaw, chunk)
        path = out_dir / named(PRECIP_DAILY_CSV, chunk)
        write_precip_csv(table, path)
        log(f"  wrote {path.name} ({len(table):,} days, {table.shape[1] - 1} WBA series)")


# -- CUP+ (step 14) -----------------------------------------------------------------------------

def crop_et_step(product: Product, chunks: list, workers: int | None) -> None:
    """Step 14 for a set, or for each Product B chunk in ``chunks``, on one worker pool."""
    pycup = load_pycup()
    with Pool(workers or cpu_count()) as pool:
        for chunk in chunks:
            crop_et_chunk(product, chunk, pycup, pool)


def crop_et_chunk(product: Product, chunk: int | None, pycup, pool) -> Path:
    """CUP+ on the step 12 ETo and step 13 precipitation of the WBAs, the monthly ETc csv,
    and CS3_ET.dss with the legacy records."""
    daily_eto = read_daily_csv(require(product_step_dir(product, 12) / named(ETO_DAILY_CSV, chunk),
                                       "run step 12 first"))
    expected = product_days(product)
    if not daily_eto.index.equals(expected):
        raise ValueError(f"daily ETo must cover {expected[0].date()} through {expected[-1].date()} once each")
    precipitation, precip_dates = read_precip_csv(
        require(product_step_dir(product, 13) / named(PRECIP_DAILY_CSV, chunk), "run step 13 first"))
    eto, precip, headers = cup_inputs(daily_eto, precipitation, precip_dates)
    validate_crop_inputs(headers)

    log(f"step 14{chunk_suffix(chunk)}: CUP+ on {len(headers)} WBA series, {len(eto):,} days")
    started = time.time()
    daily = {}
    for wba in headers:
        daily.update(daily_crop_etc(pycup, wba, eto[wba], precip[wba], pool))
    monthly = pd.DataFrame(daily).resample("ME").sum() / MM_PER_INCH
    out_dir = product_step_dir(product, 14)
    out_dir.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(out_dir / named(CUP_MONTHLY_ETC_CSV, chunk))
    log(f"  CUP+ finished in {(time.time() - started) / 60:.1f} min")

    series = land_use_et(pycup, monthly, headers)
    path = calsimhydro_et_dir(product) / named(ET_DSS, chunk)
    write_land_use_et(path, series, product.start_year, len(monthly))
    checked = validate_land_use_et(path, list(series), product.start_year, product.end_year)
    copied = copy_legacy_crop_et_records(path, reference_cropet_dss())
    (out_dir / named(STEP14_REPORT, chunk)).write_text(
        f"CalSimHydro ET DSS: {path}\n"
        f"ETo and precipitation days: {eto.index[0].date()} through {eto.index[-1].date()}\n"
        f"CUP+ land use records verified for {product.start_year}-01 through {product.end_year}-12: "
        f"{checked}\n"
        f"Legacy CropET records copied: {copied} of {LEGACY_RECORD_COUNT} (42 SL and 42 UR "
        "climatologies, 2 RI terms with 11 decade blocks)\n"
        "WBA_91 takes WBA 90's grid cells for ETo and WBA 90's CalSimHydro precipitation.\n",
        encoding="ascii")
    log(f"  wrote {path.name}: {checked} CUP+ records and {copied} legacy records")
    return path


# -- Product B: steps 10 and 11 in one pass ------------------------------------------------------------

def product_b_pass(product: Product, f1_values_for, weights: dict[str, pd.DataFrame], chunks: list[int],
                   workers: int | None) -> None:
    """One pass over the weighted cells of Product B: H-S ETo per stamp month corrected with
    F1, summed straight into the polygons. Then every chunk's window is written: the step 11
    polygon series and RefETo DSS. ``f1_values_for(cells_frame, out_dir)`` returns the F1
    array for the given cells and records its source in the step 10 folder."""
    memberships = cell_memberships(weights)
    cells = member_cells(scan_cells(product.weather_dir), memberships)
    require_hydrated(cells)
    out10 = product_step_dir(product, 10)
    out10.mkdir(parents=True, exist_ok=True)
    f1_values = f1_values_for(cells_frame(cells), out10)
    n_months = stamp_month_count()
    log(f"Product B pass: {len(cells):,} weighted cells, {n_months:,} stamp months")

    eto_acc = PolygonAccumulator(weights, n_months)
    mean_acc = PolygonAccumulator(weights, 12)
    f1_by_month = np.tile(f1_values, (1, n_months // 12))        # (cells, months)
    tasks = make_tasks(cells, product.key, product.start_year, product.end_year)
    for i, result in enumerate(run_cells(tasks, workers)):
        corrected = np.round(result.monthly_eto * f1_by_month[i], 6)
        eto_acc.add(result.key, corrected)
        mean_acc.add(result.key, np.round(corrected.reshape(-1, 12).mean(axis=0), 4))
    eto_series = eto_acc.finish()
    averages = mean_acc.tables(MONTH_NAMES, np.round(mean_acc.finish(), 4))

    out11 = product_step_dir(product, 11)
    out11.mkdir(parents=True, exist_ok=True)
    write_polygon_tables(out11, averages, None)
    columns = month_columns(CHUNK_START_YEAR, CHUNK_END_YEAR)
    for chunk in chunks:
        monthly = np.vstack([chunk_monthly_window(row, chunk) for row in eto_series])
        series = eto_acc.tables(columns, monthly)
        write_polygon_tables(out11, None, series, chunk)
        refeto_step(series["WBA"], product, chunk)


# =============================================================================================
# 13. Diagnostic maps (--plots)
# =============================================================================================
# Maps drawn on request (--plots) from a step's outputs into a plots/ folder under that step:
# factor_maps for steps 6 (CIMIS means), 7 (F1 and the H-S averages of the calibration years)
# and 8 (polygon averages); product_maps for steps 10 (F1 and H-S averages) and 11 (polygon
# averages). Each set comes in four variants: WBA and statewide extent, each with one colour
# scale over the twelve months (FixedScaleBar) and a scale per month (VariableScaleBar).
# geopandas and matplotlib (both in environment.yml) are imported only when a map is drawn.

MONTHS = MONTH_NAMES
FIGURE_FACE = "#F8FAFC"
LAND_FACE = "#D1D5DB"
WBA_LINE = "#475569"
POLYGON_LINE = "#334155"
CALIFORNIA_SHAPEFILE = "CA_StateBoundary.shp"
EXTENT_MARGIN = 0.04

# Polygon groups: boundary file, its id field, the map title and how both sides' ids are
# brought to the same form before joining.
POLYGON_GROUPS = {
    "WBA": (WBA_GEOJSON, WBA_ID_FIELD, "Water Budget Area", lambda value: str(value)),
    "SR": (SR_GEOJSON, SR_ID_FIELD, "Subregion", lambda value: int(float(str(value).replace("SR_", "")))),
    "SW": (SW_GEOJSON, SW_ID_FIELD, "Small Watershed", lambda value: str(value).replace("SW_", "", 1)),
}


# -- shared helpers ----------------------------------------------------------------------------

def _geo():
    """geopandas and pyplot, imported on first use."""
    try:
        import geopandas as gpd
    except ImportError as exc:
        raise ImportError("the maps need geopandas (and shapely), part of environment.yml; "
                          "run --plots in an environment that has them") from exc
    _fix_proj_data()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return gpd, plt


def _fix_proj_data() -> None:
    """Point pyproj at the PROJ database of a conda environment on Windows."""
    proj_dir = Path(sys.prefix) / "Library" / "share" / "proj"
    if proj_dir.exists():
        os.environ["PROJ_DATA"] = str(proj_dir)
        os.environ["PROJ_LIB"] = str(proj_dir)
        try:
            import pyproj.datadir
            pyproj.datadir.set_data_dir(str(proj_dir))
        except Exception:
            pass
    warnings.filterwarnings("ignore", message="pyproj unable to set PROJ database path")


def _union(geometry):
    return geometry.union_all() if hasattr(geometry, "union_all") else geometry.unary_union


def _require_output(path: Path, step: int) -> Path:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found; run step {step} first")
    return path


def load_boundaries(gpd):
    """The WBA polygons and the California outline (or the dissolved WBA footprint when the
    state shapefile is missing), both in EPSG:4326."""
    reference = reference_dir()
    wba = gpd.read_file(reference / WBA_GEOJSON).to_crs("EPSG:4326")
    shapefile = reference / CALIFORNIA_SHAPEFILE
    if shapefile.is_file():
        try:
            california = gpd.read_file(shapefile)
            california = california.set_crs("EPSG:4326") if california.crs is None else california.to_crs("EPSG:4326")
            return wba, california
        except Exception as exc:
            print(f"  [WARN] could not read the California boundary shapefile: {exc}")
    print("  [INFO] California boundary not found; using the dissolved WBA footprint")
    return wba, gpd.GeoDataFrame(geometry=[_union(wba.geometry)], crs=wba.crs)


def _background(ax, california) -> None:
    ax.set_facecolor(LAND_FACE)
    california.plot(ax=ax, facecolor=FIGURE_FACE, edgecolor="none", zorder=0)


def _frame(ax) -> None:
    ax.set_axis_on()
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("black")
        spine.set_linewidth(1.2)


def _extent(ax, boundary, margin: float = EXTENT_MARGIN) -> None:
    minx, miny, maxx, maxy = boundary.total_bounds
    dx, dy = (maxx - minx) * margin, (maxy - miny) * margin
    ax.set_xlim(minx - dx, maxx + dx)
    ax.set_ylim(miny - dy, maxy + dy)


def _points_inside(gpd, points: pd.DataFrame, boundary) -> pd.DataFrame:
    geometry = gpd.points_from_xy(points["Lon"], points["Lat"], crs="EPSG:4326")
    return points[geometry.within(_union(boundary.geometry))].copy()


def _save(plt, fig, path: Path, dpi: int = 180) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "wb") as handle:
        fig.savefig(handle, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor(), format="png")
    plt.close(fig)


def _scale(values: pd.DataFrame | pd.Series) -> tuple[float, float]:
    vmin, vmax = float(np.nanmin(values.to_numpy(dtype=float))), float(np.nanmax(values.to_numpy(dtype=float)))
    if vmin == vmax:
        vmax = vmin + 1e-9
    return vmin, vmax


# -- point maps of per cell tables (steps 6, 7 and 10) ---------------------------------------------

def _point_maps(gpd, plt, points: pd.DataFrame, boundaries, focus, out_dir: Path, file_name, title,
                colorbar_label, cmap: str, variable_scale: bool, grid_lines: bool) -> None:
    """Twelve maps of a Lon, Lat, Jan..Dec table within ``focus``: one colour scale over all
    months, or one per month when ``variable_scale``."""
    wba, california = boundaries
    points = _points_inside(gpd, points, focus)
    fixed = _scale(points[MONTHS])
    for month in MONTHS:
        month_points = points.dropna(subset=[month])
        vmin, vmax = _scale(month_points[month]) if variable_scale else fixed
        fig, ax = plt.subplots(figsize=(6, 7.5), facecolor=FIGURE_FACE)
        _background(ax, california)
        wba.boundary.plot(ax=ax, color=WBA_LINE, linewidth=0.55, zorder=3)
        scatter = ax.scatter(month_points["Lon"], month_points["Lat"], c=month_points[month], cmap=cmap,
                             vmin=vmin, vmax=vmax, s=3, alpha=0.9, linewidths=0, zorder=4)
        _extent(ax, focus)
        _frame(ax)
        if grid_lines and not variable_scale:
            ax.grid(True, color="white", linewidth=0.4, alpha=0.5, zorder=2)
        ax.set_title(title(month, variable_scale), fontsize=11, fontweight="bold", pad=8)
        if not variable_scale:
            ax.tick_params(labelbottom=True, labelleft=True, labelsize=8)
            ax.set_xlabel("Longitude", fontsize=9)
            ax.set_ylabel("Latitude", fontsize=9)
        colorbar = fig.colorbar(scatter, ax=ax, orientation="vertical", pad=0.02, shrink=0.65)
        colorbar.set_label(colorbar_label(month, variable_scale), fontsize=9)
        if not variable_scale:
            plt.tight_layout()
        _save(plt, fig, out_dir / file_name(month))
    print(f"  {len(MONTHS)} maps in {out_dir}")


def _four_variants(gpd, plt, points, boundaries, out_root: Path, folder: str, wba_file, state_file,
                   title, colorbar_label, cmap: str, grid_lines: bool) -> None:
    """The WBA and statewide extents, each with a fixed and a monthly colour scale. ``folder``
    is the set's name with ``{extent}`` and ``{scale}`` placeholders."""
    wba, california = boundaries
    for extent, focus, file_name in (("WBA", wba, wba_file), ("Statewide", california, state_file)):
        for scale, variable in (("FixedScaleBar", False), ("VariableScaleBar", True)):
            out_dir = out_root / folder.format(extent=extent, scale=scale)
            _point_maps(gpd, plt, points, boundaries, focus, out_dir, file_name, title, colorbar_label,
                        cmap, variable, grid_lines)


def cimis_maps(gpd, plt, boundaries, cimis_dir: Path, out_root: Path, grid_label: str) -> None:
    """Step 6: the mean CIMIS ETo of each month over the extraction years, averaged from the
    annual files, at every grid cell (mm/day). Replaces step6b."""
    start, end = CIMIS_START_YEAR, CIMIS_END_YEAR
    tables = [pd.read_csv(_require_output(Path(cimis_dir) / named(CIMIS_ANNUAL_CSV, year=year), 6))
              for year in range(start, end + 1)]
    coordinates = tables[0][["lon", "lat"]].reset_index(drop=True)
    for table in tables[1:]:
        if not table[["lon", "lat"]].reset_index(drop=True).equals(coordinates):
            raise ValueError("the step 6 annual CIMIS files do not share one grid")
    values = np.stack([table[MONTHS].to_numpy(dtype=float) for table in tables], axis=0)
    valid = np.isfinite(values)
    totals = np.where(valid, values, 0.0).sum(axis=0)
    counts = valid.sum(axis=0)
    averages = np.full(totals.shape, np.nan)
    np.divide(totals, counts, out=averages, where=counts > 0)
    points = coordinates.rename(columns={"lon": "Lon", "lat": "Lat"}).copy()
    for m, month in enumerate(MONTHS):
        points[month] = averages[:, m]
    period = f"{start}-{end}"

    def title(month, variable):
        return (f"{month} Average CIMIS ETo (mm/day)\n{grid_label} | {period}"
                + (" | monthly scale" if variable else ""))

    def colorbar_label(month, variable):
        return f"ETo (mm/day, {month} scale)" if variable else "ETo (mm/day)"

    def file_name(month):
        return f"{month}_ETo_map.png"

    _four_variants(gpd, plt, points, boundaries, out_root, "ETo_maps_{extent}_{scale}", file_name, file_name,
                   title, colorbar_label, "YlOrRd", grid_lines=False)


def f1_hs_maps(gpd, plt, boundaries, step_dir: Path, out_root: Path, step: int, grid_label: str,
               f1_period: str, hs_file: str | None, hs_period: str) -> None:
    """The F1 factors (viridis) and, when ``hs_file`` is given, the H-S monthly average ETo
    (YlOrRd) of a per cell table folder. Replaces step7b and step10c."""
    sets = [(F1_TABLE_CSV, "F1", "F1_CA", "F1 adjustment factor", "unitless", "viridis", f1_period)]
    if hs_file:
        sets.append((hs_file, "HS_avg", "HS_CA", "H-S monthly average ETo", "mm/day", "YlOrRd", hs_period))
    for file, prefix, state_prefix, value_name, unit, cmap, period in sets:
        points = pd.read_csv(_require_output(Path(step_dir) / file, step))

        def title(month, variable, value_name=value_name, period=period):
            return (f"{month} {value_name}\n{grid_label} | {period}"
                    + (" | monthly scale" if variable else ""))

        def colorbar_label(month, variable, unit=unit):
            return f"{unit} ({month} scale)" if variable else unit

        folder = prefix.split("_")[0] + "_maps_{extent}_{scale}"
        _four_variants(gpd, plt, points, boundaries, out_root, folder,
                       lambda month, prefix=prefix: f"{prefix}_{month}.png",
                       lambda month, prefix=state_prefix: f"{prefix}_{month}.png",
                       title, colorbar_label, cmap, grid_lines=True)


# -- polygon maps of the averaged tables (steps 8 and 11) ------------------------------------------

def polygon_maps(gpd, plt, boundaries, step_dir: Path, out_root: Path, step: int, product_label: str,
                 period_label: str) -> None:
    """The long term monthly average ETo per polygon (inches/month) for the WBAs, subregions and
    small watersheds, clipped to California. Replaces step8b and step11b."""
    wba, california = boundaries
    state = _union(california.geometry)
    for group, (geojson, id_field, title, transform) in POLYGON_GROUPS.items():
        values = pd.read_csv(_require_output(Path(step_dir) / named(AVERAGED_CSV, group=group), step))
        polygons = gpd.read_file(reference_dir() / geojson)
        polygons["_join_id"] = polygons[id_field].map(transform)
        values["_join_id"] = values[values.columns[0]].map(transform)
        joined = polygons.merge(values, on="_join_id", how="left")
        joined["geometry"] = joined.geometry.intersection(state)
        mapped = joined.dropna(subset=MONTHS).copy()
        missing = int(joined[MONTHS].isna().all(axis=1).sum())
        if missing:
            print(f"  {group}: {missing} polygons have no step {step} values")
        fixed = _scale(mapped[MONTHS])

        for name, statewide in ((group, False), (f"{group}_California", True)):
            for scale, variable in (("FixedScaleBar", False), ("VariableScaleBar", True)):
                out_dir = out_root / f"maps_{'Statewide_' if statewide else ''}{scale}" / group
                out_dir.mkdir(parents=True, exist_ok=True)
                for month in MONTHS:
                    vmin, vmax = _scale(mapped[month]) if variable else fixed
                    fig, ax = plt.subplots(figsize=(6, 7.5), facecolor=FIGURE_FACE)
                    _background(ax, california)
                    mapped.plot(ax=ax, column=month, cmap="YlOrRd", vmin=vmin, vmax=vmax,
                                edgecolor=POLYGON_LINE, linewidth=0.28)
                    polygons.boundary.plot(ax=ax, color=POLYGON_LINE, linewidth=0.28, zorder=5)
                    if statewide:
                        ax.set_xlim(*california.total_bounds[[0, 2]])
                        ax.set_ylim(*california.total_bounds[[1, 3]])
                    elif group == "WBA":
                        _extent(ax, wba)
                    else:
                        _extent(ax, mapped)
                    _frame(ax)
                    ax.tick_params(labelbottom=True, labelleft=True, labelsize=8, length=2)
                    ax.set_xlabel("Longitude", fontsize=9)
                    ax.set_ylabel("Latitude", fontsize=9)
                    ax.set_title(f"{month} {title} ETo\n{product_label} F1-corrected | {period_label} | inches/month",
                                 fontsize=11, fontweight="bold", pad=8)
                    mappable = plt.cm.ScalarMappable(cmap="YlOrRd", norm=plt.Normalize(vmin=vmin, vmax=vmax))
                    mappable.set_array([])
                    colorbar = fig.colorbar(mappable, ax=ax, orientation="vertical", pad=0.02, shrink=0.65)
                    colorbar.set_label(f"inches/month ({month} scale)" if variable else "inches/month", fontsize=9)
                    _save(plt, fig, out_dir / f"{name}_{month}.png")
                print(f"  {len(MONTHS)} maps in {out_dir}")
        print(f"  {group}: {len(values)} values mapped to {len(joined)} polygons")


# -- entry points --------------------------------------------------------------------------------

def factor_maps(steps: list[int]) -> None:
    """Maps of the correction factor steps: 6 (CIMIS monthly means), 7 (F1 and the H-S
    averages of the calibration years), 8 (polygon averages over the calibration years).
    Other steps are ignored."""
    gpd, plt = _geo()
    boundaries = load_boundaries(gpd)
    f1_period = "2004-2018"
    if 6 in steps:
        print("step 6 maps")
        cimis_maps(gpd, plt, boundaries, cimis_monthly_dir(), factor_step_dir(6) / "plots",
                   "Historical_Unsplit grid")
    if 7 in steps:
        print("step 7 maps")
        f1_hs_maps(gpd, plt, boundaries, factor_step_dir(7), factor_step_dir(7) / "plots", 7,
                   "Historical_Unsplit grid", f1_period,
                   named(HS_AVG_F1_PERIOD_CSV, start=2004, end=2018), "2004-2018")
    if 8 in steps:
        print("step 8 maps")
        polygon_maps(gpd, plt, boundaries, factor_step_dir(8), factor_step_dir(8) / "plots", 8,
                     "Historical_Unsplit", "2004-2018")


def product_maps(product: Product, steps: list[int], chunks: list | None = None) -> None:
    """Maps of a product: step 10 (the F1 table it applied and, for dated products, its H-S
    monthly averages over the whole period), step 11 (its polygon monthly averages). Other steps are
    ignored; chunks are not needed because the averaged tables carry no chunk suffix."""
    gpd, plt = _geo()
    boundaries = load_boundaries(gpd)
    if product.is_chunked:
        years = "1008 stamp years"
        hs_file = None
    else:
        years = f"{product.start_year}-{product.end_year}"
        hs_file = HS_AVG_CSV
    if 10 in steps:
        print(f"step 10 maps ({product.name})")
        if hs_file is None:
            print("  Product B keeps no per cell H-S table; only the F1 maps are drawn")
        f1_hs_maps(gpd, plt, boundaries, product_step_dir(product, 10),
                   product_step_dir(product, 10) / "plots", 10, f"{product.name} grid",
                   f"Applied to ETo {years}", hs_file, f"Averaged over {years}")
    if 11 in steps:
        print(f"step 11 maps ({product.name})")
        polygon_maps(gpd, plt, boundaries, product_step_dir(product, 11),
                     product_step_dir(product, 11) / "plots", 11, product.name, f"{years} average")
