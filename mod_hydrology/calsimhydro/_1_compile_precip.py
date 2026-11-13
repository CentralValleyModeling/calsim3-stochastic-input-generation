"""
Compile Daily WBA Precipitation for CalSimHydro
===============================================
Area-weighted daily precipitation (in/day) per Water Balance Area (WBA) from the daily weather
of the --product set, written as CalSimHydro's precipitation inputs.

Inputs
------
- reference/WBA_Grid_Info.txt (or --grid_info_file): the cells of each WBA and their weights
  (f2, the area inside the WBA). No WBA 91 polygon exists, so WBA_91 lists WBA_90's cells as a stand-in and gets
  WBA 90's precipitation.
- daily weather of the set (utils.wgen.weighted_daily)

Outputs
-------
Under <generated>/mod_hydrology/calsimhydro/output/_1_compile_precip/ (or --output_path):
- <Historical_Unsplit|Product_A>/pcp/<WBA>_pcp.csv (date, value; every day of the weather
  files) and CS3_DailyPrecipitation.dss (/IWFM/<WBA>/PRECIP//1DAY/PRECIPITATION/, over
  --clip_period)
- Product_B/pcp/<WBA>_pcp_n01.csv ... _n10.csv and CS3_DailyPrecipitation_n01.dss ... _n10.dss,
  each 1 Jan 1920 - 31 Dec 2021 (utils.wgen_calendar.daily_chunk_1920_2021)

Dependencies
------------
utils.paths, utils.wgen, utils.wgen_calendar, utils.dss_io; pydsstools

Usage
-----
    python mod_hydrology/calsimhydro/_1_compile_precip.py --product historical --clip_period 1920-10-01 2018-09-30
    python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30
    python mod_hydrology/calsimhydro/_1_compile_precip.py --product B
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from pydsstools.core import TimeSeriesContainer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import WEATHER_SETS, get_module_generated_dir
from utils.wgen import dates, met_path, weighted_daily
from utils.wgen_calendar import DAYS_1920_2021, N_CHUNKS, daily_chunk_1920_2021

MM_TO_IN = 0.0393701
DSS_PART = "/IWFM/{wba}/PRECIP//1DAY/PRECIPITATION"


def cell_weight(row) -> float:
    """The weight of a cell in its WBA: its area inside the WBA (f2), or pct_area for the
    Gerber cells, which carry no areas (f1 = 0)."""
    return row.f2 if row.f1 != 0 else row.pct_area


def wba_daily_precip(product: str, cells: pd.DataFrame) -> pd.Series:
    """Area-weighted daily precipitation (in/day) of one WBA from its rows of the grid-info
    file, indexed by date (by stamp day for Product B)."""
    daily = weighted_daily(product, [(met_path(product, row.Lat, row.Lon), cell_weight(row))
                                     for row in cells.itertuples(index=False)], ['precip'])
    out = daily['precip'] * MM_TO_IN
    if product != 'B':
        out.index = dates(daily)
    return out


def put_daily(dss, wba: str, start: str, values) -> None:
    tsc = TimeSeriesContainer()
    tsc.pathname = DSS_PART.format(wba=wba.replace('_', ''))
    tsc.startDateTime = f"{start} 24:00"
    tsc.numberValues = len(values)
    tsc.units = "IN/DAY"
    tsc.type = "PER-CUM"
    tsc.interval = 1
    tsc.values = values
    dss.put_ts(tsc)


def write_single(results: dict, output_path: Path, clip_period) -> None:
    """One CSV per WBA over every day, and the DSS file over ``clip_period``."""
    for wba, pcp in results.items():
        pcp.to_csv(output_path / 'pcp' / f"{wba}_pcp.csv", header=False)
    with dss_io.open_dss(str(output_path / "CS3_DailyPrecipitation.dss"), catalog_flag=False) as dss:
        for wba, pcp in results.items():
            if clip_period:
                pcp = pcp[clip_period[0]:clip_period[1]]
            put_daily(dss, wba, f"{pcp.index[0]:%Y-%m-%d}", pcp.values)


def write_product_b(results: dict, output_path: Path) -> None:
    """Per WBA and chunk, a CSV and a DSS record over 1 Jan 1920 - 31 Dec 2021."""
    days = DAYS_1920_2021
    print(f"  Product B: {len(days)} days per chunk, {N_CHUNKS} chunks")
    for k in range(1, N_CHUNKS + 1):
        dss_file = output_path / f"CS3_DailyPrecipitation_n{k:02d}.dss"
        with dss_io.open_dss(str(dss_file), catalog_flag=False) as dss:
            for wba, pcp in results.items():
                values = daily_chunk_1920_2021(pcp.values, k)
                pd.DataFrame({'y': days.year, 'm': days.month, 'd': days.day, 'pcp': values}).to_csv(
                    output_path / 'pcp' / f"{wba}_pcp_n{k:02d}.csv", header=False, index=False)
                put_daily(dss, wba, "01JAN1920", values)
        print(f"    Chunk {k:02d}/{N_CHUNKS}: {dss_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Compile WBA daily precipitation from the daily weather.")
    parser.add_argument('--product', choices=list(WEATHER_SETS), required=True,
                        help='Weather set: historical (Historical_Unsplit), A or B')
    parser.add_argument('--grid_info_file', type=str, default=None,
                        help='File with WBA grid information (default: reference/WBA_Grid_Info.txt)')
    parser.add_argument('--output_path', type=str, default=None,
                        help='Output directory (default: output/_1_compile_precip/<set>)')
    parser.add_argument('--wbas', type=str, nargs='*', default=None, help='WBAs to process (default: all)')
    parser.add_argument('--clip_period', type=str, nargs=2, default=None,
                        help='First and last day (YYYY-MM-DD) of the DSS series, Historical_Unsplit '
                             'and Product A only (default: every day)')
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    grid_info_file = args.grid_info_file or script_dir / 'reference' / 'WBA_Grid_Info.txt'
    output_path = Path(args.output_path or get_module_generated_dir("mod_hydrology/calsimhydro")
                       / 'output' / '_1_compile_precip' / WEATHER_SETS[args.product]['name'])
    (output_path / 'pcp').mkdir(parents=True, exist_ok=True)

    grid_info = pd.read_csv(grid_info_file, sep='\t', header=None,
                            names=['wba_id', 'Lat', 'Lon', 'pct_area', 'f1', 'f2'])
    print(grid_info.head())
    wbas = args.wbas or grid_info['wba_id'].unique()
    results = {}
    for wba in wbas:
        print(f"Processing {wba}")
        results[wba] = wba_daily_precip(args.product, grid_info[grid_info['wba_id'] == wba])
    if args.product == 'B':
        write_product_b(results, output_path)
    else:
        write_single(results, output_path, args.clip_period)
    print(f"Wrote {len(results)} WBAs to {output_path}")


if __name__ == "__main__":
    main()
