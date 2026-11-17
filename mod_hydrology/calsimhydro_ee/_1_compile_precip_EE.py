"""
Compile WBA Precipitation for CalSimHydroEE
============================================
Simple-average daily precipitation (in/day) over the grid cells of each Water Balance Area (WBA)
from the daily weather of the --product set, written for CalSimHydroEE. Cells of the coordinate
list with no weather file (water cells of Suisun Bay and the Delta) are left out of the average.

Inputs
------
- reference/CalSimHydroEE_WBA_Coordinate_List.csv (or --coord_file): WBA, Lat, Long, gridID
- daily weather of the set (utils.wgen.weighted_daily)

Outputs
-------
Under <generated>/mod_hydrology/calsimhydro_ee/output/_1_compile_precip_EE/ (or --output_path):
- <Historical_Unsplit|Product_A>/pcp/<WBA>_pcp.csv (date, value; every day) and
  CS3_DailyPrecipitation_EE.dss (/IWFM/E<WBA>/PRECIP//1DAY/PRECIPITATION/, over --clip_period)
- Product_B/pcp/<WBA>_pcp_n01.csv ... _n10.csv and CS3_DailyPrecipitation_EE_n01.dss ... _n10.dss,
  each 1 Jan 1920 - 31 Dec 2021 (utils.wgen_calendar.daily_chunk_1920_2021)
- --no_dss: the CSVs only

Dependencies
------------
utils.paths, utils.wgen, utils.wgen_calendar, utils.dss_io; pydsstools

Usage
-----
    python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product historical
    python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A
    python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A --clip_period 1920-10-01 2018-09-30
    python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product B
    python mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py --product A --wbas 2 5 10 --no_dss
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.core import TimeSeriesContainer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import WEATHER_SETS, get_module_generated_dir
from utils.wgen import dates, met_path, weighted_daily
from utils.wgen_calendar import DAYS_1920_2021, N_CHUNKS, daily_chunk_1920_2021

MM_TO_IN = 0.0393701
DSS_PART = "/IWFM/E{wba}/PRECIP//1DAY/PRECIPITATION"


def wba_daily_precip(product: str, cells: pd.DataFrame) -> pd.Series:
    """Simple-average daily precipitation (in/day) over a WBA's cells that have a weather file,
    indexed by date (by stamp day for Product B)."""
    paths = [met_path(product, row.Lat, row.Long)
             for row in cells.drop_duplicates(subset=['gridID']).itertuples(index=False)]
    found = [p for p in paths if p.exists()]
    missing = [p.name for p in paths if not p.exists()]
    if not found:
        raise ValueError(f"No cell of the WBA has a weather file: {missing}")
    if missing:
        print(f"    no weather file, left out: {', '.join(missing)}")
    daily = weighted_daily(product, [(p, 1.0) for p in found], ['precip'])
    out = daily['precip'] * MM_TO_IN
    if product != 'B':
        out.index = dates(daily)
    return out


def put_daily(dss, wba: str, start: str, values) -> None:
    tsc = TimeSeriesContainer()
    tsc.pathname = DSS_PART.format(wba=wba)
    tsc.startDateTime = f"{start} 24:00"
    tsc.numberValues = len(values)
    tsc.units = "IN/DAY"
    tsc.type = "PER-CUM"
    tsc.interval = 1
    tsc.values = np.asarray(values, dtype=float)
    dss.put_ts(tsc)


def write_single(results: dict, output_path: Path, clip_period, write_dss: bool) -> None:
    """One CSV per WBA over every day, and the DSS file over ``clip_period`` (every day when
    it is not given)."""
    for wba, pcp in results.items():
        pcp.to_csv(output_path / 'pcp' / f"{wba}_pcp.csv", header=False)
    if not write_dss:
        print("DSS output skipped (--no_dss).")
        return
    dss_file = output_path / "CS3_DailyPrecipitation_EE.dss"
    with dss_io.open_dss(str(dss_file), catalog_flag=False) as dss:
        for wba, pcp in results.items():
            if clip_period:
                pcp = pcp[clip_period[0]:clip_period[1]]
            put_daily(dss, wba, f"{pcp.index[0]:%Y-%m-%d}", pcp.values)
    print(f"  Wrote {len(results)} WBAs to {dss_file.name}")


def write_product_b(results: dict, output_path: Path, write_dss: bool) -> None:
    """Per WBA and chunk, a CSV and (unless --no_dss) a DSS record over 1 Jan 1920 - 31 Dec 2021."""
    days = DAYS_1920_2021
    print(f"  Product B: {len(days)} days per chunk, {N_CHUNKS} chunks")
    for k in range(1, N_CHUNKS + 1):
        chunk = {wba: daily_chunk_1920_2021(pcp.values, k) for wba, pcp in results.items()}
        for wba, values in chunk.items():
            pd.DataFrame({'y': days.year, 'm': days.month, 'd': days.day, 'pcp': values}).to_csv(
                output_path / 'pcp' / f"{wba}_pcp_n{k:02d}.csv", header=False, index=False)
        if write_dss:
            with dss_io.open_dss(str(output_path / f"CS3_DailyPrecipitation_EE_n{k:02d}.dss"),
                                 catalog_flag=False) as dss:
                for wba, values in chunk.items():
                    put_daily(dss, wba, "01JAN1920", values)
        print(f"    Chunk {k:02d}/{N_CHUNKS} written")


def main():
    ap = argparse.ArgumentParser(description="Compile simple-average WBA precipitation for CalSimHydroEE.")
    ap.add_argument('--product', choices=list(WEATHER_SETS), required=True,
                    help='Weather set: historical (Historical_Unsplit), A or B')
    ap.add_argument('--coord_file', default=None,
                    help='CalSimHydroEE_WBA_Coordinate_List.csv path (default: reference/...)')
    ap.add_argument('--output_path', default=None,
                    help='Output directory (default: output/_1_compile_precip_EE/<set>)')
    ap.add_argument('--wbas', nargs='*', default=None, help='WBA IDs to process (default: all)')
    ap.add_argument('--clip_period', nargs=2, default=None,
                    help='First and last day (YYYY-MM-DD) of the DSS series, Historical_Unsplit '
                         'and Product A only (default: every day)')
    ap.add_argument('--no_dss', action='store_true', help='Do not write DSS output')
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    coord_file = args.coord_file or script_dir / 'reference' / 'CalSimHydroEE_WBA_Coordinate_List.csv'
    output_path = Path(args.output_path or get_module_generated_dir("mod_hydrology/calsimhydro_ee")
                       / 'output' / '_1_compile_precip_EE' / WEATHER_SETS[args.product]['name'])
    (output_path / 'pcp').mkdir(parents=True, exist_ok=True)

    coord = pd.read_csv(coord_file)
    if args.wbas:
        coord = coord[coord['WBA'].isin({int(x) for x in args.wbas})]
    wba_ids = sorted(coord['WBA'].unique())
    print(f"Compiling {len(wba_ids)} WBAs ({WEATHER_SETS[args.product]['name']})...")
    results = {}
    for i, wba in enumerate(wba_ids, 1):
        print(f"  [{i}/{len(wba_ids)}] WBA {wba}")
        results[str(wba)] = wba_daily_precip(args.product, coord[coord['WBA'] == wba])
    if args.product == 'B':
        write_product_b(results, output_path, not args.no_dss)
    else:
        write_single(results, output_path, args.clip_period, not args.no_dss)
    print(f"Done. {len(results)} WBAs compiled.")


if __name__ == "__main__":
    main()
