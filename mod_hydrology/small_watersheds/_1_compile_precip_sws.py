"""
Compile Monthly Area-Weighted Precipitation for Small Watersheds
================================================================
Area-weighted monthly precipitation (inches/month) per small watershed from the daily weather of
the --product set, written into the CVprecip .dat template.

The output holds the template's WY1921-2021 (``WINDOW``). Historical_Unsplit and Product A fill
its months from October 1920 to the last month their weather covers completely (December 2018);
the months after it keep the template's values. Each Product B chunk fills WY1922-2021 with the
chunk's label months (utils.wgen_calendar) and keeps the template's WY1921 as initialization.

Inputs
------
- reference/SmallWatersheds_Grid_Info_20200915_RowBased.txt (or --grid_info_file):
  watershed_id, Lat, Lon, pct_area, f1, f2; weight f2, the area inside the watershed
- reference/CVprecipWY1921_2021.dat (or --CVprecip_file): the template
- daily weather of the set (utils.wgen.weighted_daily)

Outputs
-------
Under <generated>/mod_hydrology/small_watersheds/output/_1_compile_precip_sws/ (or
--output_path):
- <Historical_Unsplit|Product_A>/CVprecipWY1921_2021.dat (only the months of --clip_period,
  when given)
- Product_B/CVprecipWY1921_2021_n01.dat ... _n10.dat

Dependencies
------------
utils.paths, utils.wgen, utils.wgen_calendar

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
from utils.wgen import dates, met_path, weighted_daily
from utils.wgen_calendar import CHUNK_MONTHS, N_CHUNKS, label, month_totals

MM_TO_IN = 0.0393701
WINDOW = pd.date_range("1920-10-01", "2021-09-30", freq="D")   # the template's WY1921-2021
WINDOW_MONTHS = len(WINDOW.to_period("M").unique())            # 1,212
HEADER_ROWS = 104      # template rows before the first month
INIT_MONTHS = 12       # WY1921, kept from the template in every Product B chunk
FIRST_COLUMN = 1393    # template column of the first watershed


def watershed_daily(product: str, cells: pd.DataFrame) -> pd.DataFrame:
    """Area-weighted daily precipitation (mm) of one watershed: Year, Month, Day, precip on the
    rows of the weather files."""
    return weighted_daily(product, [(met_path(product, row.Lat, row.Lon), row.f2)
                                    for row in cells.itertuples(index=False)], ["precip"])


def monthly_single(daily: pd.DataFrame) -> pd.Series:
    """Monthly inches over the months of ``WINDOW`` that the weather files cover completely
    (Historical_Unsplit, Product A)."""
    s = pd.Series(daily["precip"].to_numpy(), index=dates(daily)).reindex(WINDOW) * MM_TO_IN
    r = s.resample("ME")
    return r.sum()[r.count() == r.size()]


def monthly_b(daily: pd.DataFrame) -> pd.DataFrame:
    """Monthly inches of Product B as a labelled table (chunk, Year, Month, WY, precip)."""
    m = label("B", month_totals(daily, "sum"))
    m["precip"] = m["precip"] * MM_TO_IN
    return m


def write_dat(template: pd.DataFrame, values: np.ndarray, first_row: int, out_file: Path,
              n_months: int = WINDOW_MONTHS) -> None:
    """The template's header rows (0 decimals) and first ``n_months`` month rows (3 decimals)
    with ``values`` (months x watersheds) from ``first_row``; the other month rows keep the
    template's values."""
    dat = template.copy()
    dat.iloc[first_row:first_row + len(values), FIRST_COLUMN:FIRST_COLUMN + values.shape[1]] = values
    dat.iloc[:HEADER_ROWS].to_csv(out_file, sep="\t", index=False, header=False, float_format="%.0f")
    dat.iloc[HEADER_ROWS:HEADER_ROWS + n_months].to_csv(out_file, sep="\t", index=False, header=False,
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
    n_months = WINDOW_MONTHS
    if args.clip_period:
        monthly = monthly.loc[args.clip_period[0]:args.clip_period[1]]
        n_months = len(monthly)
    write_dat(template, monthly.to_numpy(), HEADER_ROWS, output_path / cvprecip_file.name, n_months)
    print(f"Rows (months): {n_months}, {monthly.shape[0]} from the weather; "
          f"Watersheds: {monthly.shape[1]}")


if __name__ == "__main__":
    main()
