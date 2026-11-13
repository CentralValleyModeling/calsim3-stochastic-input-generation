"""
Calendar of the Weather Sets
============================
The time axis of every series in the pipeline. Historical_Unsplit, Product A and LTO run on real
dates. Product B's weather (BASE/WGEN/Product_B/<scenario>/meteo_<lat>_<lon>) is one daily
sequence over the stamp years 1-1008, with a leap day in every 4th stamp year from year 1 (1, 5,
9, ...). Its leap years are not Gregorian ones, so no module dates the rows itself: the stamp
year and month in each row are the calendar.

The pipeline cuts 10 chunks of 100 water years from that sequence. It skips Jan-Sep of stamp
year 1, so chunk k runs from October of stamp year 100(k-1)+1 to September of stamp year
100k+1, and the outputs (``*_n01.csv`` ... ``*_n10.csv``) label every chunk WY1922-2021 (Oct
1921 to Sep 2021, ``LABEL_MONTHS``).

A labelled table carries ``chunk`` (0 for a single series: Historical_Unsplit, Product A, LTO;
1-10 for Product B), ``Year`` and ``Month`` (the label month) and ``WY`` (``water_year``).
``monthly`` builds one from the daily rows of ``utils.wgen.read_met``. A module that works on
the file's own months first (a quantile map fit over stamp months) takes ``month_totals`` and
then ``label``. ``write_chunk_csvs`` writes Product B's chunk files, and
``require_label_months`` checks a chunk file read back, and ``in_label_months`` cuts an
external model's run of a chunk to its label months. ``wy_months`` lists the months of a span
of water years (``LABEL_MONTHS`` is WY1922-2021's). The daily consumers take ``chunk_days`` or
``daily_chunk_1920_2021`` and date their rows with ``LABEL_DAYS`` or ``DAYS_1920_2021``;
CalSimHydro's monthly inputs take ``monthly_chunk_1920_2021``.

Usage
-----
    from utils.wgen import met_path, read_met
    from utils.wgen_calendar import monthly
    rows = read_met("B", met_path("B", lat, lon), usecols=["precip"])
    m = monthly("B", rows, "sum")      # chunk, Year, Month, WY, precip: 10 x 1,200 label months
"""

import functools
from pathlib import Path

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


@functools.cache
def stamp_days() -> np.ndarray:
    """Per row of a Product B file (stamp day), its stamp year, month and day: shape
    (``STAMP_DAYS``, 3). Read-only."""
    month = stamp_month_of_day()
    lengths = np.bincount(month)
    first = np.repeat(np.cumsum(lengths) - lengths, lengths)
    out = np.stack([month // 12 + 1, month % 12 + 1, np.arange(len(month)) - first + 1], axis=1)
    out.setflags(write=False)
    return out


@functools.cache
def stamp_day_of_year() -> np.ndarray:
    """Per row of a Product B file (stamp day), its day of the stamp year: 1 on 1 January, 366
    on 31 December of a leap stamp year. Read-only."""
    lengths = np.bincount(stamp_days()[:, 0])[1:]
    first = np.repeat(np.cumsum(lengths) - lengths, lengths)
    out = np.arange(STAMP_DAYS) - first + 1
    out.setflags(write=False)
    return out


def require_stamp_calendar(ymd: np.ndarray, what) -> None:
    """Stop unless the (year, month, day) rows of a Product B file are the stamp days in order
    from 1 January of stamp year 1: the daily consumers cut the chunks by row position."""
    require_stamp_days(len(ymd), what)
    off = np.flatnonzero((np.asarray(ymd) != stamp_days()).any(axis=1))
    if len(off):
        i = int(off[0])
        raise ValueError(f"{what}: row {i} is ({', '.join(map(str, ymd[i]))}), but stamp day {i} "
                         f"is ({', '.join(map(str, stamp_days()[i]))}) (year, month, day)")


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


def water_year(year, month) -> np.ndarray:
    """The water year of a calendar or label month: October to December count toward the next
    year."""
    return np.asarray(year, dtype=np.int64) + (np.asarray(month) >= 10)


def wy_months(first_wy: int, last_wy: int) -> pd.DataFrame:
    """Year and Month of every month of water years ``first_wy``..``last_wy``, October of
    ``first_wy - 1`` to September of ``last_wy``, in order."""
    t = (first_wy - 1) * 12 + 9 + np.arange(12 * (last_wy - first_wy + 1))
    return pd.DataFrame({"Year": t // 12, "Month": t % 12 + 1})


#: The 1,200 label months every Product B chunk carries: Year and Month, Oct 1921 to Sep 2021.
LABEL_MONTHS = wy_months(*LABEL_WY)

#: The days a daily Product B output labels a chunk's 36,525 days with (``chunk_days``), in
#: order: 1 October 1921 to 30 September 2021.
LABEL_DAYS = pd.date_range(f"{LABEL_WY[0] - 1}-10-01", f"{LABEL_WY[1]}-09-30", freq="D")

#: The days of the daily series CalSimHydro and CalSimHydroEE read, 1 January 1920 to
#: 31 December 2021 (``daily_chunk_1920_2021``).
DAYS_1920_2021 = pd.date_range("1920-01-01", "2021-12-31", freq="D")


def require_label_months(year, month, what) -> None:
    """Stop unless ``year`` and ``month`` are a chunk's 1,200 ``LABEL_MONTHS`` in order."""
    ym = np.column_stack([np.asarray(year), np.asarray(month)])
    if ym.shape != LABEL_MONTHS.shape or not (ym == LABEL_MONTHS.to_numpy()).all():
        raise ValueError(f"{what}: {len(ym)} rows, not the {CHUNK_MONTHS} label months "
                         "Oct 1921 - Sep 2021 in order")


def in_label_months(df: pd.DataFrame, what: str) -> pd.DataFrame:
    """The rows of a chunk table (Part B, Part C, Year, Month, ...) in the 1,200
    ``LABEL_MONTHS``: an external model's run of a chunk also holds the months before them
    (its spin-up). Stops unless every series holds every label month, in order."""
    ym = df["Year"].to_numpy(dtype=np.int64) * 12 + df["Month"].to_numpy(dtype=np.int64) - 1
    out = df[(ym >= _LABEL_START) & (ym < _LABEL_START + CHUNK_MONTHS)].reset_index(drop=True)
    for key, g in out.groupby(["Part B", "Part C"], sort=False):
        require_label_months(g["Year"], g["Month"], f"{what} {key}")
    return out


def label_months(product: str, year, month) -> pd.DataFrame:
    """``chunk``, ``Year``, ``Month`` and ``WY`` of monthly rows of ``product`` given by their
    file year and month: Product B's stamp months take their chunk labels (chunk 0 outside every
    chunk), the other sets keep their dates with chunk 0. The index follows ``year`` when it is
    a Series."""
    if product == "B":
        out = chunk_months(year, month)
    else:
        out = pd.DataFrame({"chunk": 0, "Year": np.asarray(year, dtype=np.int64),
                            "Month": np.asarray(month, dtype=np.int64)},
                           index=year.index if isinstance(year, pd.Series) else None)
    out["WY"] = water_year(out["Year"], out["Month"])
    return out


def month_totals(rows: pd.DataFrame, how) -> pd.DataFrame:
    """Daily ``rows`` (Year, Month, Day and value columns, as ``utils.wgen.read_met`` returns
    them) aggregated by the months of the file with ``how`` ("sum", "mean" or a column ->
    function dict), in file order: Year, Month (stamp months for Product B) and the values."""
    values = [c for c in rows.columns if c not in ("Year", "Month", "Day")]
    return rows.groupby(["Year", "Month"], sort=False)[values].agg(how).reset_index()


def label(product: str, m: pd.DataFrame) -> pd.DataFrame:
    """Monthly rows of ``product`` by file month (Year, Month and value columns) as a labelled
    table: chunk, Year, Month, WY and the value columns. Product B keeps only the months
    inside its chunks, in chunk order."""
    values = [c for c in m.columns if c not in ("Year", "Month")]
    out = pd.concat([label_months(product, m["Year"], m["Month"]), m[values]], axis=1)
    if product == "B":
        out = out[out["chunk"] > 0].reset_index(drop=True)
    return out


def monthly(product: str, rows: pd.DataFrame, how) -> pd.DataFrame:
    """``label(product, month_totals(rows, how))``: the daily rows of ``product`` aggregated by
    month as a labelled table."""
    return label(product, month_totals(rows, how))


def write_chunk_csvs(df: pd.DataFrame, folder, stem: str, columns=None) -> list[Path]:
    """Write Product B's chunk files ``<folder>/<stem>_n01.csv`` ... ``_n10.csv`` from a labelled
    table (``chunk`` plus ``columns``, by default Part B, Part C, Year, Month, Value). Rows of
    chunk 0 (outside every chunk) are left out, and any other value outside 1..N_CHUNKS is an
    error. Each chunk must hold every series of the table over the 1,200 ``LABEL_MONTHS`` in
    order, which the compiler assumes. Returns the paths written."""
    stray = set(pd.unique(df["chunk"])) - set(range(N_CHUNKS + 1))
    if stray:
        raise ValueError(f"{stem}: chunk values {sorted(map(str, stray))} outside 0..{N_CHUNKS}")
    columns = columns or ["Part B", "Part C", "Year", "Month", "Value"]
    keys = [c for c in columns if c not in ("Year", "Month", "Value")]
    series = set(df.groupby(keys, sort=False).groups) if keys else None
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for k in range(1, N_CHUNKS + 1):
        part = df[df["chunk"] == k]
        if part.empty:
            raise ValueError(f"{stem} n{k:02d}: no rows")
        groups = part.groupby(keys, sort=False) if keys else [((), part)]
        if keys and set(groups.groups) != series:
            raise ValueError(f"{stem} n{k:02d}: holds {len(groups.groups)} of the table's {len(series)} series")
        for key, g in groups:
            require_label_months(g["Year"], g["Month"], f"{stem} n{k:02d} {key}")
        path = folder / f"{stem}_n{k:02d}.csv"
        part[columns].to_csv(path, index=False)
        out.append(path)
    return out


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


def monthly_chunk_1920_2021(values, chunk: int) -> np.ndarray:
    """A monthly series of chunk ``chunk`` laid out January 1920 to December 2021, the span of
    CalSimHydro's monthly inputs (1,224 months), from ``values`` by stamp month (index 0 is
    January of stamp year 1). The chunk's months are WY1922-2021, Jan-Sep 1921 holds the 9
    months before them, Oct-Dec 2021 the 3 after them, and 1920 is a copy of 1921."""
    (year, month), _ = chunk_span(chunk)
    first = int(stamp_month_index(year, month))
    from_1921 = np.asarray(values)[first - 9:first + CHUNK_MONTHS + 3]
    if len(from_1921) != CHUNK_MONTHS + 12:
        raise ValueError(f"chunk {chunk}: {len(values)} stamp months do not reach its Oct-Dec 2021")
    return np.concatenate([from_1921[:12], from_1921])
