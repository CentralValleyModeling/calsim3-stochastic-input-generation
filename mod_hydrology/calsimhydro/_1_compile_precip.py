"""
Compile Daily WBA Precipitation for CalSimHydro
===============================================
Reads WBA grid info and daily WGEN meteorology, computes area-weighted daily
precipitation per Water Balance Area, and writes the CalSimHydro precip
inputs (CSV, optional DSS) for Product A (1921-2018) or Product B (chunked).

Inputs
------
- WBA grid-info file (grid weights per WBA)
- WGEN met files (Product_A / Product_B)

Outputs
-------
- <generated>/output/_1_compile_precip/Product_A/  (daily WBA precip; optional DSS)
- <generated>/output/_1_compile_precip/Product_B/  (with --product B)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
    python mod_hydrology/calsimhydro/_1_compile_precip.py --product A --clip_period 1920-10-01 2018-09-30
    python mod_hydrology/calsimhydro/_1_compile_precip.py --product B
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from pydsstools.core import TimeSeriesContainer

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wgen_calendar import N_CHUNKS, STAMP_DAYS, daily_chunk_1920_2021, require_stamp_days


class compile_wba_precip:
    """
    Class to compile daily WBA precip from met files.
    This class reads grid information and aggregates precip.
    It can handle multiple WBA selections and outputs the results to specified files.
    Attributes:
        grid_info_file (str): Path to the WBA grid information file.
        met_path (str): Path to the directory containing precipitation files.
        output_path (str): Path to the directory where output files will be saved.
        start_date (str): Start date for the data range (default '1915-01-01').
        end_date (str): End date for the data range (default '2021-12-31').
        met_columns (list): List of columns expected in the meteorology files.
        dates (pd.DatetimeIndex): Date range from start_date to end_date.
    """
    def __init__(self, grid_info_file, met_path, output_path, start_date, end_date, met_prefix, met_sep, clip_period, product_b=False):
        self.grid_info_file = os.path.join(grid_info_file)
        self.met_path = os.path.join(met_path)
        self.output_path = output_path
        self.start_date = start_date
        self.end_date = end_date
        self.met_columns = [
            'Year', 'Month', 'Day',
            'precip', 'tmax', 'tmin'
        ]
        self.met_prefix = met_prefix
        self.met_sep = met_sep
        self.product_b = product_b
        if self.product_b:
            # Product B: one WGEN row per stamp day (utils.wgen_calendar)
            self.dates = pd.RangeIndex(STAMP_DAYS)
        else:
            self.dates = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        self.clip_period = clip_period
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

    def _cell_weight(self, row):
        # When f1=0 or f2=0, fall back to pct_area as the cell weight.
        if row['f1'] != 0:
            return row['f2'] / row['f1']
        return row['pct_area']

    def compute_precip_from_met(self, met, grid_info_row):
        # Compute precip from met and grid info row
        pcp = met['precip']
        pcp_adj = pcp * self._cell_weight(grid_info_row)
        return pcp_adj

    def compute_precip(self, grid_info):
        # Compute precip for a given grid info file
        pcp_wba_daily = pd.Series(dtype=float)
        wba_pct_area = 0
        for i, row in grid_info.iterrows():
            met_path = os.path.join(self.met_path, f"{self.met_prefix}_{row.Lat}_{row.Lon}")
            if os.path.exists(met_path):
                met_df = pd.read_csv(met_path, sep=self.met_sep, header=None, names=self.met_columns, engine='python')
                if self.product_b:
                    require_stamp_days(len(met_df), met_path)
                pcp = self.compute_precip_from_met(met_df, row)
                pcp_wba_daily = pcp_wba_daily.add(pcp, fill_value=0)
                wba_pct_area += self._cell_weight(row)
            else:
                raise FileNotFoundError(f"met file not found: {met_path}")
        pcp_wba_daily = pcp_wba_daily / wba_pct_area
        pcp_wba_daily = pcp_wba_daily * 0.0393701  # convert mm to inch
        pcp_wba_daily.index = self.dates[:len(pcp_wba_daily)]
        return pcp_wba_daily

    def _write_product_b_chunks(self, results, pcp_dir):
        # Per WBA and chunk, 1 Jan 1920 - 31 Dec 2021 (utils.wgen_calendar.daily_chunk_1920_2021).
        date_template = pd.date_range('1920-01-01', '2021-12-31', freq='D')
        print(f"  Product B: {len(date_template)} days per chunk, {N_CHUNKS} chunks")
        for wba, pcp_data in results.items():
            for i in range(N_CHUNKS):
                chunk_values = daily_chunk_1920_2021(pcp_data.values, i + 1)
                df = pd.DataFrame({
                    'y': date_template.year,
                    'm': date_template.month,
                    'd': date_template.day,
                    'pcp': chunk_values
                })
                out_file = os.path.join(pcp_dir, f"{wba}_pcp_n{i+1:02d}.csv")
                df.to_csv(out_file, header=False, index=False)
                print(f"    Chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def run(self, select_wba):
        # Main method to run the compilation for selected wbas
        wbas_grid_info_file = pd.read_csv(self.grid_info_file, sep='\t', header=None, names=['wba_id', 'Lat', 'Lon', 'pct_area', 'f1', 'f2'])
        print(wbas_grid_info_file.head())
        if select_wba is None:
            wba_to_process = wbas_grid_info_file['wba_id'].unique()
        else:
            wba_to_process = [] + select_wba
        results = {}
        pcp_dir = os.path.join(self.output_path, 'pcp')
        os.makedirs(pcp_dir, exist_ok=True)
        for wba in wba_to_process:
            print(f"Processing {wba}")
            grids_in_wba = wbas_grid_info_file[wbas_grid_info_file['wba_id'] == wba].copy()
            pcp_wba_daily = self.compute_precip(grids_in_wba)
            if not self.product_b:
                output_file = os.path.join(pcp_dir, f"{wba}_pcp.csv")
                pcp_wba_daily.to_csv(output_file, header=False)
            print(f"Computed daily precip for {wba}")
            results[wba] = pcp_wba_daily
        if self.product_b:
            self._write_product_b_chunks(results, pcp_dir)
        return results

    def write_to_dss(self, results):
        # Write results to DSS
        if self.product_b:
            self._write_product_b_dss(results)
            return
        dss_file = os.path.join(self.output_path, "CS3_DailyPrecipitation.dss")
        with dss_io.open_dss(dss_file, catalog_flag=False) as dss:
            for wba, pcp_data in results.items():
                if self.clip_period:
                    pcp_data = pcp_data[self.clip_period[0]:self.clip_period[1]]
                tsc = TimeSeriesContainer()
                tsc.pathname = f"/IWFM/{wba.replace('_','')}/PRECIP//1DAY/PRECIPITATION"
                tsc.startDateTime = f"{self.clip_period[0]} 24:00"
                tsc.numberValues = len(pcp_data)
                tsc.units = "IN/DAY"
                tsc.type = "PER-CUM"
                tsc.interval = 1
                tsc.values = pcp_data.values
                dss.put_ts(tsc)

    def _write_product_b_dss(self, results):
        # Write 10 per-chunk DSS files, Jan 1920 - Dec 2021 each.
        start_dt_str = "01JAN1920 24:00"
        for i in range(N_CHUNKS):
            dss_file = os.path.join(self.output_path, f"CS3_DailyPrecipitation_n{i+1:02d}.dss")
            print(f"  Writing DSS chunk {i+1:02d}/10: {os.path.basename(dss_file)}")
            with dss_io.open_dss(dss_file, catalog_flag=False) as dss:
                for wba, pcp_data in results.items():
                    chunk_values = daily_chunk_1920_2021(pcp_data.values, i + 1)
                    tsc = TimeSeriesContainer()
                    tsc.pathname = f"/IWFM/{wba.replace('_','')}/PRECIP//1DAY/PRECIPITATION"
                    tsc.startDateTime = start_dt_str
                    tsc.numberValues = len(chunk_values)
                    tsc.units = "IN/DAY"
                    tsc.type = "PER-CUM"
                    tsc.interval = 1
                    tsc.values = chunk_values
                    dss.put_ts(tsc)

def main():
    # Parse command-line arguments and run the compilation
    parser = argparse.ArgumentParser(description="Compile WBA daily precip from WGEN met files.")
    parser.add_argument('--grid_info_file', type=str, default=None, help='File with WBA grid information (default: reference/WBA_Grid_Info.txt)')
    parser.add_argument('--met_path', type=str, default=None,
                        help='Path to WGEN met directory.')
    parser.add_argument('--output_path', type=str, default=None,
                        help='Path to output directory.')
    parser.add_argument('--start_date', type=str, default='1915-01-01', help='Start date (YYYY-MM-DD) [Product A only]')
    parser.add_argument('--end_date', type=str, default='2018-12-31', help='End date (YYYY-MM-DD) [Product A only]')
    parser.add_argument('--wbas', type=str, nargs='*', default=None, help='wba names to select (optional)')
    parser.add_argument('--met_prefix', type=str, default='meteo', help='Prefix for met files')
    parser.add_argument('--met_sep', type=str, default='\\s+', help='Separator for met files')
    parser.add_argument('--clip_period', type=str, nargs=2, default=None, help='Clip period as start and end date (YYYY-MM-DD) [Product A only]')
    parser.add_argument('--product', choices=['A', 'B'], required=True,
                        help='Product to generate: A (historical 1921-2018) or B (stochastic 1000-yr chunks).')
    args = parser.parse_args()

    # Resolve defaults based on product
    _script_dir = Path(__file__).resolve().parent
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_hydrology/calsimhydro")

    grid_info_file = args.grid_info_file or str(_script_dir / 'reference' / 'WBA_Grid_Info.txt')
    product_b = args.product == 'B'
    if product_b:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_B' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip' / 'Product_B')
    else:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_A' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip' / 'Product_A')

    rim = compile_wba_precip(
        grid_info_file=grid_info_file,
        met_path=met_path,
        output_path=output_path,
        start_date=args.start_date,
        end_date=args.end_date,
        met_prefix=args.met_prefix,
        met_sep=args.met_sep,
        clip_period=args.clip_period,
        product_b=product_b
    )
    wba_precip = rim.run(select_wba=args.wbas)
    rim.write_to_dss(wba_precip)

if __name__ == "__main__":
    # Product A (defaults: WGEN/Product_A/1, output/Product_A):
    # python _1_compile_precip.py --product A --grid_info_file ./reference/WBA_Grid_Info.txt --clip_period 1920-10-01 2018-09-30
    # Product B (defaults: WGEN/Product_B/1, output/Product_B; writes 10 chunk files per WBA):
    # python _1_compile_precip.py --product B --grid_info_file ./reference/WBA_Grid_Info.txt
    main()