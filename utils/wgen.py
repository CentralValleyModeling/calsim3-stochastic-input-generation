"""
WGEN Weather Reader
===================
Every module reads the daily weather files through this module. Its functions take a key of
``utils.paths.WEATHER_SETS``: ``historical`` (Historical_Unsplit), ``A`` or ``B`` (Products A and
B, scenario 1), or ``LTO``. A WGEN file holds one grid cell, ``<prefix>_<lat>_<lon>``, one
whitespace-separated row per day: year, month, day, precipitation (mm), tmax and tmin (C)
(``BASE/WGEN/README.md``). Product B's rows follow the stamp calendar of ``utils.wgen_calendar``.

``LTO`` is Historical_Climate_LTO (``LTO_DIR``), another realization of the historical record and
not WGEN. Its files ``data_<lat>_<lon>`` hold precipitation, tmax, tmin and wind, one row per day
of ``LTO_DAYS``, and no dates; ``read_met`` dates the rows and drops the wind.

Historical_Unsplit carries precipitation values at ten times their size, a misplaced decimal of
the Livneh lineage. ``read_met`` divides them by 10 at the 289 (cell, day) pairs of
``X10_TABLE``, SAC-SMA's frozen table, which the rim-inflow adapters apply too; it covers the
4,410 cells of SAC-SMA's region. Elsewhere no table exists yet, so ``read_met`` corrects nothing
and warns about every June-August day of ``SPIKE_SCREEN_MM`` or more that the table does not
list: each spike found so far is such a day.

Usage
-----
    from utils.wgen import met_path, read_met
    w = read_met("historical", met_path("historical", 38.15625, -120.71875))
    w.columns    # Year, Month, Day, precip, tmax, tmin
    dates(w)     # DatetimeIndex 1915-01-01 ... 2018-12-31
"""
from __future__ import annotations

import functools
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from utils.paths import REPO_ROOT, WEATHER_SETS, get_base_dir, get_wgen_dir
from utils.wgen_calendar import require_stamp_calendar

COLUMNS = ["Year", "Month", "Day", "precip", "tmax", "tmin"]
X10_TABLE = REPO_ROOT / "mod_hydrology" / "rim_inflow" / "reference" / "prcp_x10_artifacts.csv"
SPIKE_SCREEN_MM = 150.0
LTO_DIR = Path("Historical_Climate_LTO") / "1_Historical"
LTO_DAYS = pd.date_range("1915-01-01", "2021-12-31", freq="D")


#: Every set ``read_met`` reads: the keys of ``WEATHER_SETS`` and LTO.
SETS = (*WEATHER_SETS, "LTO")


def set_name(product: str) -> str:
    """The name of a set's output folders and files: its ``WEATHER_SETS`` name, or LTO."""
    return "LTO" if product == "LTO" else WEATHER_SETS[product]["name"]


def _prefix(product: str) -> str:
    return "data" if product == "LTO" else WEATHER_SETS[product]["prefix"]


def met_dir(product: str) -> Path:
    """The folder of ``product``'s files."""
    return get_base_dir() / LTO_DIR if product == "LTO" else get_wgen_dir(product)


def met_path(product: str, lat, lon) -> Path:
    """The file of the cell at ``lat``, ``lon``, formatted as the file names are (e.g.
    ``38.15625``, ``-120.71875``)."""
    return met_dir(product) / f"{_prefix(product)}_{lat}_{lon}"


@functools.cache
def cells(product: str) -> tuple[tuple[float, float, Path], ...]:
    """Every cell of ``product``: (lat, lon, file), in file-name order. Stops on a file whose
    name starts with the prefix but is not ``<prefix>_<lat>_<lon>``."""
    prefix = _prefix(product) + "_"
    out = []
    for p in sorted(met_dir(product).glob(prefix + "*")):
        if p.is_file():
            try:
                lat, lon = (float(x) for x in p.name[len(prefix):].split("_"))
            except ValueError:
                raise ValueError(f"{p}: not a weather file name ({prefix}<lat>_<lon>); move it "
                                 f"out of {p.parent}") from None
            out.append((lat, lon, p))
    if not out:
        raise FileNotFoundError(f"{met_dir(product)}: no {prefix}* files")
    return tuple(out)


@functools.cache
def _cell_coords(product: str) -> tuple[np.ndarray, np.ndarray]:
    c = cells(product)
    return np.array([x[0] for x in c]), np.array([x[1] for x in c])


def nearest_cell(product: str, lat: float, lon: float) -> tuple[float, float, Path, float]:
    """The cell of ``product`` nearest to ``lat``, ``lon`` by Euclidean distance in degrees,
    good enough over a cell's span (on a tie, the first in file-name order): (lat, lon, file,
    distance)."""
    lats, lons = _cell_coords(product)
    d = np.sqrt((lats - lat) ** 2 + (lons - lon) ** 2)
    i = int(np.argmin(d))
    c_lat, c_lon, path = cells(product)[i]
    return c_lat, c_lon, path, float(d[i])


@functools.cache
def _x10_days() -> dict:
    """Cell key -> {yyyymmdd: raw precipitation} of its pairs in ``X10_TABLE``."""
    t = pd.read_csv(X10_TABLE, dtype={"key": str, "date": str})
    ymd = t["date"].str.replace("-", "").astype(np.int64)
    out = {}
    for k, d, v in zip(t["key"], ymd, t["prcp_raw_mm"]):
        out.setdefault(k, {})[int(d)] = float(v)
    return out


def read_met(product: str, path, usecols=None) -> pd.DataFrame:
    """The daily rows of a file of ``product`` with columns ``COLUMNS`` (or Year, Month, Day
    and those named in ``usecols``). For Historical_Unsplit the cell's ``X10_TABLE`` pairs are
    divided by 10, and the read stops if a raw value there is not the one the table records. A
    Product B file must hold the stamp days in order (``require_stamp_calendar``), an LTO file
    one row per day of ``LTO_DAYS``."""
    path = Path(path)
    prefix = _prefix(product) + "_"
    if not path.name.startswith(prefix) or path.parent.name != met_dir(product).name:
        raise ValueError(f"{path}: not a {product} file ({met_dir(product).name}/{prefix}<lat>_<lon>)")
    cols = COLUMNS if usecols is None else COLUMNS[:3] + [c for c in COLUMNS[3:] if c in usecols]
    if product == "LTO":
        w = pd.read_csv(path, sep=r"\s+", header=None, names=["precip", "tmax", "tmin", "wind"])
        if len(w) != len(LTO_DAYS):
            raise ValueError(f"{path}: {len(w)} rows; an LTO file has {len(LTO_DAYS)}, one per day "
                             f"from {LTO_DAYS[0]:%Y-%m-%d} to {LTO_DAYS[-1]:%Y-%m-%d}")
        w["Year"], w["Month"], w["Day"] = LTO_DAYS.year, LTO_DAYS.month, LTO_DAYS.day
        return w[cols]
    w = pd.read_csv(path, sep=r"\s+", header=None, names=COLUMNS, usecols=cols)
    if product == "B":
        require_stamp_calendar(w[["Year", "Month", "Day"]].to_numpy(), path)
    if product == "historical" and "precip" in cols:
        _correct_x10(w, path, path.name[len(prefix):])
    return w


def dates(w: pd.DataFrame) -> pd.DatetimeIndex:
    """The dates of rows that ``read_met`` returned for a set on real dates (any but Product B,
    whose stamp leap years no date type knows)."""
    return pd.DatetimeIndex(pd.to_datetime(w[["Year", "Month", "Day"]].set_axis(
        ["year", "month", "day"], axis=1)))


def _correct_x10(w: pd.DataFrame, path: Path, key: str) -> None:
    """Divide the cell's ``X10_TABLE`` pairs by 10 in place, and warn about the unlisted
    June-August days of ``SPIKE_SCREEN_MM`` or more."""
    ymd = (w["Year"].to_numpy(np.int64) * 10000 + w["Month"].to_numpy(np.int64) * 100
           + w["Day"].to_numpy(np.int64))
    fix = _x10_days().get(key, {})
    rows = np.flatnonzero(np.isin(ymd, list(fix)))
    found = dict(zip(ymd[rows], w["precip"].to_numpy()[rows]))
    bad = [d for d, raw in fix.items() if d not in found or abs(found[d] - raw) > 5e-4]
    if bad:
        raise ValueError(f"{path}: the raw precipitation on {bad} is not the value "
                         f"{X10_TABLE.name} records")
    w.loc[rows, "precip"] = w["precip"].to_numpy()[rows] / 10.0
    summer = w["Month"].between(6, 8).to_numpy()
    suspect = np.flatnonzero(summer & (w["precip"].to_numpy() >= SPIKE_SCREEN_MM))
    if len(suspect):
        days = ", ".join(f"{ymd[i]} ({w['precip'].iat[i]:.1f} mm)" for i in suspect)
        warnings.warn(f"{path.name}: June-August precipitation of {SPIKE_SCREEN_MM:.0f} mm or "
                      f"more not in {X10_TABLE.name}, left as recorded: {days}", stacklevel=3)
