"""
Compile WBA Precipitation for CalSimHydroEE
============================================
Computes simple-average daily precipitation (mm → in) across all VIC grid cells
within each Water Balance Area (WBA) and writes outputs for CalSimHydroEE.

Product A: one CSV per WBA (full period), optional DSS file.
Product B: 10 chunk CSVs per WBA (Jan 1920 – Dec 2021 each, 100-WY core per chunk)
           + optional per-chunk DSS files.

Inputs
------
- reference/CalSimHydroEE_WBA_Coordinate_List.csv
- WGEN/Product_A/1/  or  WGEN/Product_B/1/  (meteo_<Lat>_<Lon> files)

Outputs
-------
- output/_1_compile_precip_EE/Product_A/pcp/<WBA>_pcp.csv
- output/_1_compile_precip_EE/Product_B/pcp/<WBA>_pcp_n01.csv … n10.csv
- (optional) CS3_DailyPrecipitation_EE.dss  /  CS3_DailyPrecipitation_EE_n01.dss … n10.dss

Usage
-----
    # Product A (clip to CalSim validation window)
    cd mod_hydrology/calsimhydro_ee && python _1_compile_precip_EE.py \
        --clip_period 1920-10-01 2018-09-30

    # Product B (10 chunks)
    cd mod_hydrology/calsimhydro_ee && python _1_compile_precip_EE.py --Product_B

    # Process specific WBAs only
    cd mod_hydrology/calsimhydro_ee && python _1_compile_precip_EE.py --wbas 2 5 10

    # Skip DSS output
    cd mod_hydrology/calsimhydro_ee && python _1_compile_precip_EE.py --no_dss
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


class CompileWBAPrecipEE:
    """
    Compile daily WBA precipitation (simple average across grids) for CalSimHydroEE.
    Input coordinate file columns (CSV): WBA,Lat,Long,gridID
    Met file expectation: one file per grid cell, containing columns:
        Year Month Day precip tmax tmin   (precip in mm)
    File naming:
       {met_prefix}_{Lat}_{Long}
    """
    def __init__(
        self,
        coord_file,
        met_path,
        output_path,
        start_date_vic,
        end_date_vic,
        met_prefix,
        met_sep,
        clip_period=None,
        write_dss=True,
        product_b=False,
    ):
        self.coord_file = coord_file
        self.met_path = met_path
        self.output_path = output_path
        self.start_date_vic = start_date_vic
        self.end_date_vic = end_date_vic
        self.met_prefix = met_prefix
        self.met_sep = met_sep
        self.clip_period = clip_period
        self.write_dss_flag = write_dss
        self.product_b = product_b
        self.met_columns = ['Year', 'Month', 'Day', 'precip', 'tmax', 'tmin']
        if self.product_b:
            # Product B spans ~1000 years; use PeriodIndex to exceed pandas Timestamp max (~2262)
            self.dates = pd.period_range(start='2025-01-01', end='3033-01-08', freq='D')
        else:
            self.dates = pd.date_range(start=self.start_date_vic, end=self.end_date_vic, freq='D')
        os.makedirs(self.output_path, exist_ok=True)

    def _met_filename(self, row):
        return f"{self.met_prefix}_{row.Lat}_{row.Long}"

    def _read_met(self, filepath):
        return pd.read_csv(filepath, sep=self.met_sep, header=None, names=self.met_columns, engine='python')

    def _extract_precip_series(self, met_df):
        # Assume precip column is in mm; return Series indexed by internal daily index (0..n-1)
        return met_df['precip']

    def compute_wba_precip(self, wba_df):
        # Deduplicate gridIDs
        wba_df = wba_df.drop_duplicates(subset=['gridID'])
        series_list = []
        for _, row in wba_df.iterrows():
            fn = self._met_filename(row)
            fp = os.path.join(self.met_path, fn)
            if not os.path.exists(fp):
                print(f"Missing met file: {fp}")
                continue
            met_df = self._read_met(fp)
            pcp = self._extract_precip_series(met_df)
            series_list.append(pcp)

        if not series_list:
            raise ValueError("No precipitation series found for WBA.")

        # Align length check
        n_days = len(self.dates)
        for s in series_list:
            if len(s) != n_days:
                raise ValueError(f"Length mismatch: expected {n_days} days, got {len(s)}")

        # Simple average
        avg_mm = sum(series_list) / len(series_list)
        avg_in = avg_mm * 0.0393701
        avg_in.index = self.dates[:len(avg_in)]
        return avg_in

    def run(self, select_wbas=None):
        coord = pd.read_csv(self.coord_file)
        if select_wbas:
            target = set(int(x) for x in select_wbas)
            coord = coord[coord['WBA'].isin(target)]
        wba_ids = sorted(coord['WBA'].unique())
        product_label = "Product B" if self.product_b else "Product A"
        print(f"Compiling {len(wba_ids)} WBAs ({product_label})...")
        results = {}
        pcp_dir = os.path.join(self.output_path, 'pcp')
        os.makedirs(pcp_dir, exist_ok=True)
        for idx, wba_id in enumerate(wba_ids, 1):
            print(f"  [{idx}/{len(wba_ids)}] WBA {wba_id}")
            sub = coord[coord['WBA'] == wba_id].copy()
            pcp = self.compute_wba_precip(sub)
            if not self.product_b:
                out_csv = os.path.join(pcp_dir, f"{wba_id}_pcp.csv")
                pcp.to_csv(out_csv, header=False)
            results[str(wba_id)] = pcp
        if self.product_b:
            self._write_product_b_chunks(results, pcp_dir)
        print(f"Done. {len(results)} WBAs compiled.")
        return results

    def _build_product_b_chunk(self, values, chunk_idx):
        """Build Jan 1920 - Dec 2021 data array for one Product B chunk.

        Core (non-overlapping): Oct 1921 - Sep 2021 (100 water years).
        Jan 1921 - Sep 1921: WGEN data preceding this chunk's core.
        Oct 2021 - Dec 2021: WGEN data following this chunk's core.
        Jan 1920 - Dec 1920: Backfill (duplicate of Jan 1921 - Dec 1921).
        """
        core_template = pd.date_range('1921-10-01', '2021-09-30', freq='D')
        core_days = len(core_template)
        skip_days = 273   # Jan 1 - Sep 30
        pre_core_days = 273
        suffix_days = 92  # Oct 1 - Dec 31

        core_start = skip_days + chunk_idx * core_days

        pre_core = values[core_start - pre_core_days : core_start]
        core = values[core_start : core_start + core_days]
        post_core = values[core_start + core_days : core_start + core_days + suffix_days]

        # Jan 1921 - Dec 2021 natural data
        natural = np.concatenate([pre_core, core, post_core])

        # Backfill: Jan 1920 - Dec 1920 = copy of Jan 1921 - Dec 1921
        # 1921 has 365 days; 1920 is a leap year with 366 days
        jan_dec_1921 = natural[:365]
        backfill = np.concatenate([
            jan_dec_1921[:59],    # Jan 1 - Feb 28 (59 days)
            jan_dec_1921[58:59],  # Feb 29 = copy of Feb 28
            jan_dec_1921[59:]     # Mar 1 - Dec 31 (306 days)
        ])

        return np.concatenate([backfill, natural])

    def _write_product_b_chunks(self, results, pcp_dir):
        # Output Jan 1920 - Dec 2021 per chunk.
        # Core: Oct 1921 - Sep 2021 (100 WY, non-overlapping across chunks).
        # Jan 1920 - Dec 1920: backfill (copy of Jan-Dec 1921).
        # Oct 2021 - Dec 2021: from subsequent chunk's WGEN data.
        date_template = pd.date_range('1920-01-01', '2021-12-31', freq='D')
        core_template = pd.date_range('1921-10-01', '2021-09-30', freq='D')
        core_days = len(core_template)
        skip_days = 273
        total_chunks = 10
        total_needed = skip_days + core_days * total_chunks + 92  # +92 for last chunk's Oct-Dec suffix
        print(f"  Product B: {core_days} core days/chunk, {len(date_template)} output days/chunk, {total_chunks} chunks")
        for wba, pcp_data in results.items():
            values = pcp_data.values
            if len(values) < total_needed:
                raise ValueError(f"{wba}: need {total_needed} days, got {len(values)}")
            for i in range(total_chunks):
                chunk_values = self._build_product_b_chunk(values, i)
                df = pd.DataFrame({
                    'y': date_template.year,
                    'm': date_template.month,
                    'd': date_template.day,
                    'pcp': chunk_values,
                })
                out_file = os.path.join(pcp_dir, f"{wba}_pcp_n{i+1:02d}.csv")
                df.to_csv(out_file, header=False, index=False)
                print(f"    Chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def write_to_dss(self, results):
        if not self.write_dss_flag:
            print("DSS output skipped (--no_dss).")
            return
        if self.product_b:
            self._write_product_b_dss(results)
            return
        dss_file = os.path.join(self.output_path, "CS3_DailyPrecipitation_EE.dss")
        print(f"Writing DSS: {dss_file}")
        with HecDss.Open(dss_file) as dss:
            for wba, series in results.items():
                data = series
                start_for_path = self.start_date_vic
                if self.clip_period:
                    data = data[self.clip_period[0]:self.clip_period[1]]
                    start_for_path = self.clip_period[0]
                tsc = TimeSeriesContainer()
                tsc.pathname = f"/IWFM/E{wba}/PRECIP//1DAY/PRECIPITATION"
                tsc.startDateTime = f"{start_for_path} 24:00"
                tsc.numberValues = len(data)
                tsc.units = "IN/DAY"
                tsc.type = "PER-CUM"
                tsc.interval = 1
                tsc.values = data.values.astype(float)
                dss.put_ts(tsc)
        print(f"  Wrote {len(results)} WBAs to {os.path.basename(dss_file)}")

    def _write_product_b_dss(self, results):
        # Write 10 per-chunk DSS files, Jan 1920 - Dec 2021 each.
        total_chunks = 10
        start_dt_str = "01JAN1920 24:00"
        for i in range(total_chunks):
            dss_file = os.path.join(self.output_path, f"CS3_DailyPrecipitation_EE_n{i+1:02d}.dss")
            print(f"  Writing DSS chunk {i+1:02d}/10: {os.path.basename(dss_file)}")
            with HecDss.Open(dss_file) as dss:
                for wba, pcp_data in results.items():
                    chunk_values = self._build_product_b_chunk(pcp_data.values, i)
                    tsc = TimeSeriesContainer()
                    tsc.pathname = f"/IWFM/E{wba}/PRECIP//1DAY/PRECIPITATION"
                    tsc.startDateTime = start_dt_str
                    tsc.numberValues = len(chunk_values)
                    tsc.units = "IN/DAY"
                    tsc.type = "PER-CUM"
                    tsc.interval = 1
                    tsc.values = chunk_values.astype(float)
                    dss.put_ts(tsc)


def main():
    ap = argparse.ArgumentParser(description="Compile simple-average WBA precipitation for CalSimHydroEE.")
    ap.add_argument('--coord_file', default=None, help='CalSimHydroEE_WBA_Coordinate_List.csv path (default: reference/...)')
    ap.add_argument('--met_path', default=None,
                    help='Directory containing WGEN met files.')
    ap.add_argument('--output_path', default=None,
                    help='Output directory.')
    ap.add_argument('--start_date_vic', default='1915-01-01')
    ap.add_argument('--end_date_vic', default='2018-12-31')
    ap.add_argument('--wbas', nargs='*', default=None, help='Optional list of WBA IDs to process')
    ap.add_argument('--met_prefix', default='meteo', help='Prefix for met files')
    ap.add_argument('--met_sep', default='\\s+', help='Separator for met files (regex OK)')
    ap.add_argument('--clip_period', nargs=2, default=None, help='Optional clip start end (YYYY-MM-DD) [Product A only]')
    ap.add_argument('--no_dss', action='store_true', help='Do not write DSS output')
    ap.add_argument('--Product_B', action='store_true',
                    help='If set, read WGEN Product B files and split outputs into ten 100-WY chunks.')
    args = ap.parse_args()

    _script_dir = Path(__file__).resolve().parent
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_hydrology/calsimhydro_ee")

    coord_file = args.coord_file or str(_script_dir / 'reference' / 'CalSimHydroEE_WBA_Coordinate_List.csv')
    if args.Product_B:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_B' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip_EE' / 'Product_B')
    else:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_A' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip_EE' / 'Product_A')

    runner = CompileWBAPrecipEE(
        coord_file=coord_file,
        met_path=met_path,
        output_path=output_path,
        start_date_vic=args.start_date_vic,
        end_date_vic=args.end_date_vic,
        met_prefix=args.met_prefix,
        met_sep=args.met_sep,
        clip_period=args.clip_period,
        write_dss=not args.no_dss,
        product_b=args.Product_B,
    )
    results = runner.run(select_wbas=args.wbas)
    runner.write_to_dss(results)


if __name__ == "__main__":
    main()