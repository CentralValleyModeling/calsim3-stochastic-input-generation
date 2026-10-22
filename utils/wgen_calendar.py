"""
WGEN Product B Calendar
=======================
Product B's weather (BASE/WGEN/Product_B/<scenario>/meteo_<lat>_<lon>, year month day prcp tmax
tmin) is one daily sequence over the stamp years 1-1008, with a leap day in every 4th stamp year
from year 1 (1, 5, 9, ...). Its leap years are not Gregorian ones, so no module should date the
rows itself: the stamp year and month in each row are the calendar.

The pipeline cuts 10 chunks of 100 water years from the sequence. It skips Jan-Sep of stamp year
1, so chunk k runs from October of stamp year 100(k-1)+1 to September of stamp year 100k+1, and
the outputs (``*_n01.csv`` ... ``*_n10.csv``) label every chunk WY1922-2021 (Oct 1921 to Sep
2021). closure_terms has always cut it this way.

Usage
-----
    from utils.wgen_calendar import chunk_months
    w = pd.read_csv(path, sep=r"\\s+", header=None, names=["y", "m", "d", "prcp", "tmax", "tmin"])
    monthly = w.groupby(["y", "m"], as_index=False)["prcp"].sum()
    monthly = monthly.join(chunk_months(monthly["y"], monthly["m"]))
    monthly = monthly[monthly["chunk"] > 0]      # chunk, Year, Month: the label of each month
"""

import functools

import numpy as np
import pandas as pd

N_CHUNKS = 10
CHUNK_MONTHS = 1200
SKIP_MONTHS = 9
LABEL_WY = (1922, 2021)
_LABEL_START = (LABEL_WY[0] - 1) * 12 + 9          # October of the first label water year


def is_stamp_leap(year) -> np.ndarray:
    """Whether a stamp year has a 29 February (every 4th year from year 1)."""
    return np.asarray(year) % 4 == 1


def stamp_month_index(year, month) -> np.ndarray:
    """Months since January of stamp year 1 (0 for that month)."""
    return (np.asarray(year, dtype=np.int64) - 1) * 12 + np.asarray(month, dtype=np.int64) - 1


def chunk_months(year, month) -> pd.DataFrame:
    """Per stamp month: ``chunk`` (1-10; 0 for a month outside every chunk) and the ``Year`` and
    ``Month`` the chunk labels it with (0 outside every chunk). The index follows ``year`` when
    it is a Series."""
    i = stamp_month_index(year, month) - SKIP_MONTHS
    inside = (i >= 0) & (i < N_CHUNKS * CHUNK_MONTHS)
    t = _LABEL_START + i % CHUNK_MONTHS
    out = pd.DataFrame({"chunk": np.where(inside, i // CHUNK_MONTHS + 1, 0),
                        "Year": np.where(inside, t // 12, 0),
                        "Month": np.where(inside, t % 12 + 1, 0)},
                       index=year.index if isinstance(year, pd.Series) else None)
    return out


def stamp_day_index(year: int, month: int, day: int) -> int:
    """Days since 1 January of stamp year 1 (0 for that day), on the stamp calendar."""
    y = year - 1
    days = 365 * y + (y + 3) // 4                     # leap years 1, 5, ... below ``year``
    feb = 29 if is_stamp_leap(year) else 28
    return days + sum((31, feb, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[:month - 1]) + day - 1


STAMP_YEARS = 1008
STAMP_DAYS = stamp_day_index(STAMP_YEARS + 1, 1, 1)    # 368,172 rows in a Product B file


def require_stamp_days(n_rows: int, what) -> None:
    """Stop unless a Product B file has one row per stamp day; a truncated file would otherwise
    pass and bias every sum over its missing tail."""
    if n_rows != STAMP_DAYS:
        raise ValueError(f"{what}: {n_rows} rows; a Product B file has {STAMP_DAYS}, one per stamp day")


@functools.cache
def stamp_month_of_day() -> np.ndarray:
    """Per row of a Product B file (stamp day), the stamp month it falls in
    (:func:`stamp_month_index`), for grouping daily rows into months without dates. Read-only."""
    lengths = [n for y in range(1, STAMP_YEARS + 1)
               for n in (31, 29 if is_stamp_leap(y) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)]
    out = np.repeat(np.arange(len(lengths)), lengths)
    out.setflags(write=False)
    return out


def chunk_span(chunk: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """The first and last stamp (year, month) of a chunk: ((100(k-1)+1, 10), (100k+1, 9))."""
    if not 1 <= chunk <= N_CHUNKS:
        raise ValueError(f"chunk {chunk}: Product B has chunks 1-{N_CHUNKS}")
    first = SKIP_MONTHS + (chunk - 1) * CHUNK_MONTHS
    last = first + CHUNK_MONTHS - 1
    return (first // 12 + 1, first % 12 + 1), (last // 12 + 1, last % 12 + 1)


def chunk_days(chunk: int) -> tuple[int, int]:
    """First row (0 = 1 January of stamp year 1) and length of chunk ``chunk``: 274 + 36,525 (k - 1)
    and 36,525, the days of WY1922-2021. A daily output that labels them in order runs one day
    behind the stamp calendar from each label 29 February (1924, 1928, ...) to the stamp 29
    February a year later, so in those months each label month ends with the first day of the
    next stamp month."""
    (y0, m0), (y1, _) = chunk_span(chunk)
    first = stamp_day_index(y0, m0, 1)
    return first, stamp_day_index(y1, 10, 1) - first


def daily_chunk_1920_2021(values, chunk: int) -> np.ndarray:
    """A daily series of chunk ``chunk`` laid out 1 January 1920 to 31 December 2021, the span
    CalSimHydro and CalSimHydroEE read (37,256 days). The chunk's days are WY1922-2021. Jan-Sep
    1921 holds the 274 days before them less the stamp 29 February (the chunk's first stamp year
    is a leap year), Oct-Dec 2021 the 92 days after them, and 1920 is a copy of 1921 with 28
    February repeated as 29 February."""
    first, n = chunk_days(chunk)
    values = np.asarray(values)
    jan_sep = np.delete(values[first - 274:first], 31 + 28)
    from_1921 = np.concatenate([jan_sep, values[first:first + n + 92]])
    y1921 = from_1921[:365]
    return np.concatenate([y1921[:59], y1921[58:59], y1921[59:], from_1921])
