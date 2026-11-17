"""
Compile Daily Precipitation (mm) for DCD Stations
=================================================
Averages the daily precipitation of one weather set (``utils.wgen``) across the grid cells
nearest each DCD station, and Lodi's temperatures too, and writes the DETAW precipitation inputs.
Values are rounded to 2 decimals.

Inputs
------
- reference/USBR_LTO_ClimateChange_DCD_StnsVICCoordinates_20210425.csv (Lat, Lon or Long, Station)
- reference/mm_pcp4.csv, reference/LODI_PT4.csv: the 30 Sep 1921 row that heads every Product B
  chunk
- The daily weather of the set (``utils.wgen.read_met``)

Outputs
-------
- output/_1_compile_precip_DETAW/<set>/mm_pcp4.csv (year, month, day, DOY, one column per
  station) and LODI_PT4.csv (Date, Year, Month, DOY, Pcp(mm), Tx(oC), Tn(oC)), over every day of
  the weather files or --clip_period; <set> is Historical_Unsplit or Product_A
- output/_1_compile_precip_DETAW/Product_B/mm_pcp4_n01.csv ... n10.csv and LODI_PT4_n01.csv ...
  n10.csv, each 30 Sep 1921 - 30 Sep 2021 (``utils.wgen_calendar.chunk_days``)

Usage
-----
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product historical
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A --clip_period 1921-09-30 2018-09-30
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product B
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import WEATHER_SETS, get_module_generated_dir
from utils.wgen import dates, met_path, read_met
from utils.wgen_calendar import LABEL_DAYS, N_CHUNKS, chunk_days

STATIONS = ['Brentwood', 'Davis', 'Galt', 'Lodi', 'RioVista', 'Stockton', 'Tracy']
LODI_COLUMNS = {'precip': 'Pcp(mm)', 'tmax': 'Tx(oC)', 'tmin': 'Tn(oC)'}
# The label days of a chunk with the reference row (the day before) first
CHUNK_DAYS = pd.date_range(LABEL_DAYS[0] - pd.Timedelta(days=1), LABEL_DAYS[-1], freq='D')


def station_daily(product: str, cells: pd.DataFrame, columns: list) -> pd.DataFrame:
    """The mean of ``columns`` over a station's cells, rounded to 2 decimals, one row per day of
    the weather files (dated; by stamp day for Product B)."""
    cells = cells.drop_duplicates(subset=['Lat', 'Lon'])
    paths = [met_path(product, r.Lat, r.Lon) for r in cells.itertuples(index=False)]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing weather files for station {cells.iloc[0]['Station']}: {missing}")
    reads = [read_met(product, p, usecols=columns) for p in paths]
    days = reads[0][['Year', 'Month', 'Day']].to_numpy()
    for p, w in zip(paths[1:], reads[1:]):
        if not np.array_equal(w[['Year', 'Month', 'Day']].to_numpy(), days):
            raise ValueError(f"{p}: its days differ from the other cells of the station")
    out = pd.DataFrame({c: (sum(w[c] for w in reads) / len(reads)).round(2) for c in columns})
    if product != 'B':
        out.index = dates(reads[0])
    return out


def calendar_columns(index: pd.DatetimeIndex, names) -> dict:
    """year, month, (day,) DOY columns of ``index`` under ``names``."""
    parts = {'Date': index.strftime('%Y-%m-%d'), 'year': index.year, 'month': index.month,
             'day': index.day, 'DOY': index.dayofyear}
    return {out: np.asarray(parts[key]).astype(int) if key != 'Date' else parts[key]
            for key, out in names}


def write_single(res: dict, output_csv: Path, lodi_csv: Path, clip_period) -> None:
    pcp = pd.DataFrame({stn: res[stn]['precip'] for stn in STATIONS})
    lodi = res['Lodi']
    if clip_period:
        pcp = pcp.loc[clip_period[0]:clip_period[1]]
        lodi = lodi.loc[clip_period[0]:clip_period[1]]
    out = pd.DataFrame(calendar_columns(pcp.index, [('year', 'year'), ('month', 'month'),
                                                    ('day', 'day'), ('DOY', 'DOY')]))
    for stn in STATIONS:
        out[stn] = pcp[stn].to_numpy()
    out.to_csv(output_csv, index=False)
    print(f"Wrote {len(out)} rows to {output_csv}")
    out = pd.DataFrame(calendar_columns(lodi.index, [('Date', 'Date'), ('year', 'Year'),
                                                     ('month', 'Month'), ('DOY', 'DOY')]))
    for col, name in LODI_COLUMNS.items():
        out[name] = lodi[col].astype(float).to_numpy()
    out.to_csv(lodi_csv, index=False)
    print(f"Wrote {len(out)} rows to {lodi_csv}")


def write_product_b(res: dict, output_csv: Path, lodi_csv: Path, ref_dir: Path) -> None:
    """The 10 chunks of ``chunk_days``, each headed by the 30 Sep 1921 reference row."""
    ref_pcp = pd.read_csv(ref_dir / 'mm_pcp4.csv', nrows=1).iloc[0]
    ref_lodi = pd.read_csv(ref_dir / 'LODI_PT4.csv', nrows=1).iloc[0]
    print(f"  Product B: {len(CHUNK_DAYS)} days per chunk, {N_CHUNKS} chunks")
    for k in range(1, N_CHUNKS + 1):
        first, n = chunk_days(k)
        out = pd.DataFrame(calendar_columns(CHUNK_DAYS, [('year', 'year'), ('month', 'month'),
                                                         ('day', 'day'), ('DOY', 'DOY')]))
        for stn in STATIONS:
            out[stn] = [float(ref_pcp[stn])] + list(res[stn]['precip'].to_numpy()[first:first + n])
        out.to_csv(output_csv.with_name(f"{output_csv.stem}_n{k:02d}{output_csv.suffix}"), index=False)
        out = pd.DataFrame(calendar_columns(CHUNK_DAYS, [('Date', 'Date'), ('year', 'Year'),
                                                         ('month', 'Month'), ('DOY', 'DOY')]))
        for col, name in LODI_COLUMNS.items():
            out[name] = [float(ref_lodi[name])] + list(res['Lodi'][col].to_numpy()[first:first + n])
        out.to_csv(lodi_csv.with_name(f"{lodi_csv.stem}_n{k:02d}{lodi_csv.suffix}"), index=False)
        print(f"    Chunk {k:02d}/{N_CHUNKS} written")


def main():
    ap = argparse.ArgumentParser(description="Compile daily precipitation (mm) for the DCD stations.")
    ap.add_argument('--product', choices=list(WEATHER_SETS), required=True,
                    help='Weather set: historical (Historical_Unsplit), A or B')
    ap.add_argument('--coord_file', default=None,
                    help='Station coordinate CSV (default: reference/USBR_LTO_ClimateChange_DCD_'
                         'StnsVICCoordinates_20210425.csv)')
    ap.add_argument('--output_csv', default=None,
                    help='Station CSV (default: output/_1_compile_precip_DETAW/<set>/mm_pcp4.csv)')
    ap.add_argument('--lodi_output_csv', default=None,
                    help='Lodi CSV (default: output/_1_compile_precip_DETAW/<set>/LODI_PT4.csv)')
    ap.add_argument('--clip_period', nargs=2, default=None,
                    help='First and last day (YYYY-MM-DD), Historical_Unsplit and Product A only '
                         '(default: every day)')
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    coord_file = Path(args.coord_file or script_dir / 'reference'
                      / 'USBR_LTO_ClimateChange_DCD_StnsVICCoordinates_20210425.csv')
    out_dir = (get_module_generated_dir("mod_hydrology/delta_channel_depletion") / 'output'
               / '_1_compile_precip_DETAW' / WEATHER_SETS[args.product]['name'])
    output_csv = Path(args.output_csv or out_dir / 'mm_pcp4.csv')
    lodi_csv = Path(args.lodi_output_csv or out_dir / 'LODI_PT4.csv')
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    lodi_csv.parent.mkdir(parents=True, exist_ok=True)

    coord = pd.read_csv(coord_file)
    if 'Lon' not in coord.columns and 'Long' in coord.columns:
        coord = coord.rename(columns={'Long': 'Lon'})
    print(f"Compiling {len(STATIONS)} stations ({WEATHER_SETS[args.product]['name']})...")
    res = {}
    for i, stn in enumerate(STATIONS, 1):
        print(f"  [{i}/{len(STATIONS)}] {stn}")
        cells = coord[coord['Station'] == stn]
        if cells.empty:
            raise ValueError(f"No rows in {coord_file.name} for station '{stn}'")
        res[stn] = station_daily(args.product, cells, list(LODI_COLUMNS) if stn == 'Lodi' else ['precip'])
    if args.product == 'B':
        write_product_b(res, output_csv, lodi_csv, coord_file.parent)
    else:
        write_single(res, output_csv, lodi_csv, args.clip_period)
    print("Done.")


if __name__ == "__main__":
    main()
