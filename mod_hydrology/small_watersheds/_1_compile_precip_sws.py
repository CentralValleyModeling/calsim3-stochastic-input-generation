"""
Compile Monthly Area-Weighted Precipitation for Small Watersheds
================================================================
Area-weighted monthly precipitation (inches/month) per small watershed from the daily weather of
one set (``utils.wgen``), written into the CVprecip .dat template.

The template holds WY1921-2021 (``WINDOW``). For Historical_Unsplit and Product A the months of
the window run from October 1920, and a day of the window past the end of the weather files
counts as 0 in its month. Each Product B chunk fills WY1922-2021 with the chunk's label months
(``utils.wgen_calendar``) and keeps the template's WY1921 as initialization.

Inputs
------
- reference/SmallWatersheds_Grid_Info_20200915_RowBased.txt (watershed_id, Lat, Lon, pct_area,
  f1, f2; weight f2 / f1)
- reference/CVprecipWY1921_2021.dat (template)
- The daily weather of the set (``utils.wgen.read_met``)

Outputs
-------
- output/_1_compile_precip_sws/<set>/CVprecipWY1921_2021.dat, <set> being Historical_Unsplit or
  Product_A (the months of --clip_period only, when given)
- output/_1_compile_precip_sws/Product_B/CVprecipWY1921_2021_n01.dat ... n10.dat

Usage
-----
    python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product historical
    python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A
    python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product A --clip_period 1920-10-01 2018-09-30
    python mod_hydrology/small_watersheds/_1_compile_precip_sws.py --product B
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import WEATHER_SETS, get_module_generated_dir
from utils.wgen import dates, met_path, read_met
from utils.wgen_calendar import CHUNK_MONTHS, N_CHUNKS, label, month_totals

MM_TO_IN = 0.0393701
WINDOW = pd.date_range("1920-10-01", "2021-09-30", freq="D")   # the template's WY1921-2021
HEADER_ROWS = 104      # template rows before the first month
INIT_MONTHS = 12       # WY1921, kept from the template in every Product B chunk
FIRST_COLUMN = 1393    # template column of the first watershed


def watershed_daily(product: str, cells: pd.DataFrame) -> pd.DataFrame:
    """Area-weighted daily precipitation (mm) of one watershed: Year, Month, Day, precip on the
    rows of the weather files."""
    total, weight, first = None, 0.0, None
    for row in cells.itertuples(index=False):
        path = met_path(product, row.Lat, row.Lon)
        if not path.exists():
            raise FileNotFoundError(f"Missing weather file: {path}")
        met = read_met(product, path, usecols=["precip"])
        if first is None:
            first = met
        elif not np.array_equal(met[["Year", "Month", "Day"]].to_numpy(),
                                first[["Year", "Month", "Day"]].to_numpy()):
            raise ValueError(f"{path}: its days differ from the other cells of the watershed")
        w = row.f2 / row.f1
        total = met["precip"] * w if total is None else total + met["precip"] * w
        weight += w
    return first[["Year", "Month", "Day"]].assign(precip=total / weight)


def monthly_single(daily: pd.DataFrame) -> pd.Series:
    """Monthly inches over the months of ``WINDOW`` (Historical_Unsplit, Product A)."""
    s = pd.Series(daily["precip"].to_numpy(), index=dates(daily)).reindex(WINDOW)
    return (s * MM_TO_IN).resample("ME").sum()


def monthly_b(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly inches of Product B as a labelled table (chunk, Year, Month, WY, precip)."""
    m = label("B", month_totals(daily, "sum"))
    m["precip"] = m["precip"] * MM_TO_IN
    return m


def write_dat(template: pd.DataFrame, values: np.ndarray, first_row: int, out_file: Path) -> None:
    """The template with ``values`` (months x watersheds) from ``first_row``, its header rows
    with 0 decimals and its month rows with 3."""
    dat = template.copy()
    dat.iloc[first_row:first_row + len(values), FIRST_COLUMN:FIRST_COLUMN + values.shape[1]] = values
    dat.iloc[:HEADER_ROWS].to_csv(out_file, sep="\t", index=False, header=False, float_format="%.0f")
    dat.iloc[HEADER_ROWS:first_row + len(values)].to_csv(out_file, sep="\t", index=False, header=False,
                                                        float_format="%.3f", mode="a")
    print(f"  Written: {out_file}")


def main():
    p = argparse.ArgumentParser(description="Compile the monthly small-watershed precipitation matrix (inches/month).")
    p.add_argument("--product", choices=list(WEATHER_SETS), required=True,
                   help="Weather set: historical (Historical_Unsplit), A or B")
    p.add_argument("--grid_info_file", default=None,
                   help="Grid info file (default: reference/SmallWatersheds_Grid_Info_20200915_RowBased.txt)")
    p.add_argument("--CVprecip_file", default=None,
                   help=".dat template (default: reference/CVprecipWY1921_2021.dat)")
    p.add_argument("--clip_period", nargs=2, default=None,
                   help="First and last day (YYYY-MM-DD) of the months written, Historical_Unsplit "
                        "and Product A only (default: the whole template)")
    p.add_argument("--output_path", default=None,
                   help="Output directory (default: output/_1_compile_precip_sws/<set>)")
    args = p.parse_args()

    script_dir = Path(__file__).resolve().parent
    grid_info_file = args.grid_info_file or script_dir / "reference" / "SmallWatersheds_Grid_Info_20200915_RowBased.txt"
    cvprecip_file = Path(args.CVprecip_file or script_dir / "reference" / "CVprecipWY1921_2021.dat")
    output_path = Path(args.output_path or get_module_generated_dir("mod_hydrology/small_watersheds")
                       / "output" / "_1_compile_precip_sws" / WEATHER_SETS[args.product]["name"])
    output_path.mkdir(parents=True, exist_ok=True)

    grid = pd.read_csv(grid_info_file, sep=r"\s+", header=None,
                       names=["watershed_id", "Lat", "Lon", "pct_area", "f1", "f2"], engine="python")
    ws_ids = sorted(grid.watershed_id.unique())
    print(f"Compiling {len(ws_ids)} watersheds ({WEATHER_SETS[args.product]['name']})...")
    template = pd.read_csv(cvprecip_file, delimiter="\t", header=None)
    print(f"  Template shape: {template.shape}")

    if args.product == "B":
        tables = []
        for i, wsid in enumerate(ws_ids, 1):
            print(f"  [{i}/{len(ws_ids)}] Watershed {wsid}")
            tables.append(monthly_b(watershed_daily("B", grid[grid.watershed_id == wsid])))
        for k in range(1, N_CHUNKS + 1):
            values = np.column_stack([t.loc[t["chunk"] == k, "precip"].to_numpy() for t in tables])
            if len(values) != CHUNK_MONTHS:
                raise ValueError(f"chunk {k}: {len(values)} months, not {CHUNK_MONTHS}")
            write_dat(template, values, HEADER_ROWS + INIT_MONTHS,
                      output_path / f"{cvprecip_file.stem}_n{k:02d}{cvprecip_file.suffix}")
        print(f"Months per chunk: {CHUNK_MONTHS}, watersheds: {len(ws_ids)}")
        return

    monthly = pd.concat({str(wsid): monthly_single(watershed_daily(args.product, grid[grid.watershed_id == wsid]))
                         for wsid in ws_ids}, axis=1)
    if args.clip_period:
        monthly = monthly.loc[args.clip_period[0]:args.clip_period[1]]
    write_dat(template, monthly.to_numpy(), HEADER_ROWS, output_path / cvprecip_file.name)
    print(f"Rows (months): {monthly.shape[0]}, Watersheds: {monthly.shape[1]}")


if __name__ == "__main__":
    main()
