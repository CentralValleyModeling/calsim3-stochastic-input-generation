"""
Compile Daily Precipitation (mm) for DCD Stations from WGEN Met Files
====================================================================
Averages WGEN daily precipitation across the grids nearest each DCD station
(and the Lodi point) and writes the DETAW precipitation inputs for
Product A (historical) or Product B (10 stochastic chunks).

Inputs
------
- DCD station coordinate CSV (Lat, Lon, Station)
- WGEN met files (Product_A / Product_B)

Outputs
-------
- mm_pcp4.csv, LODI_PT4.csv  (Product A)
- 10 chunk files for stations + Lodi  (Product B)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
Product A (historical, writes mm_pcp4.csv and LODI_PT4.csv):
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product A --clip_period 1921-09-30 2018-09-30

Product B (stochastic, writes 10 chunk files for stations + Lodi):
    python mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py --product B
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


class CompileStationsPrecipMM:
    """
    Compile daily precipitation (mm) for specified stations by averaging across WGEN grids.

    Inputs:
  - coord_file: CSV with columns Lat, Lon (or Long), Station
  - met files: one per grid, named {met_prefix}_{Lat}_{Lon}
               with columns (no header): Year Month Day precip tmax tmin  (precip in mm, tmax/tmin in degC)

    Output:
    - Single CSV with columns:
        year,month,day,DOY,Brentwood,Davis,Galt,Lodi,RioVista,Stockton,Tracy

    Additional:
    - Method export_lodi_with_temps to separately output Lodi daily series:
        columns: Date,Year,Month,DOY,Pcp(mm),Tx(oC),Tn(oC)
    """

    def __init__(
        self,
        coord_file,
        met_path,
        output_csv,
        start_date='1915-01-01',
        end_date='2018-12-31',
        met_prefix='meteo',
        met_sep='\\s+',
        clip_period=None,
        product_b=False,
    ):
        self.coord_file = coord_file
        self.met_path = met_path
        self.output_csv = output_csv
        self.start_date = start_date
        self.end_date = end_date
        self.met_prefix = met_prefix
        self.met_sep = met_sep
        self.clip_period = clip_period
        self.product_b = product_b
        self.ref_dir = os.path.dirname(os.path.abspath(coord_file))
        self.met_columns = ['Year', 'Month', 'Day', 'precip', 'tmax', 'tmin']
        if self.product_b:
            # Product B spans ~1000 years; use PeriodIndex to exceed pandas Timestamp max (~2262)
            self.dates = pd.period_range(start='2025-01-01', end='3033-01-08', freq='D')
        else:
            self.dates = pd.date_range(start=self.start_date, end=self.end_date, freq='D')

        # Expected stations and final column order
        self.station_order = ['Brentwood', 'Davis', 'Galt', 'Lodi', 'RioVista', 'Stockton', 'Tracy']

    def _latlon_str(self, lat, lon):
        # Match file naming with fixed precision (VIC/WGEN grids typically use 5 decimals like 37.90625)
        return f"{lat:.5f}", f"{lon:.5f}"

    def _met_filename(self, lat, lon):
        lat_s, lon_s = self._latlon_str(lat, lon)
        return f"{self.met_prefix}_{lat_s}_{lon_s}"

    def _read_met_precip_series(self, filepath):
        df = pd.read_csv(filepath, sep=self.met_sep, header=None, names=self.met_columns, engine='python')
        # Return precip Series (mm), length must match self.dates
        return df['precip']

    def _read_met_vars_series(self, filepath):
        """
        Return (precip, tmax, tmin) as three Series for a single grid file.
        """
        df = pd.read_csv(filepath, sep=self.met_sep, header=None, names=self.met_columns, engine='python')
        return df['precip'], df['tmax'], df['tmin']

    def _compute_station_series(self, station_df):
        # Deduplicate grid locations
        cols = ['Lat', 'Lon'] if 'Lon' in station_df.columns else ['Lat', 'Long']
        station_df = station_df.drop_duplicates(subset=cols)

        series_list = []
        missing = []

        for _, row in station_df.iterrows():
            lat = float(row['Lat'])
            lon = float(row['Lon'] if 'Lon' in row else row['Long'])
            fn = self._met_filename(lat, lon)
            fp = os.path.join(self.met_path, fn)
            if not os.path.exists(fp):
                missing.append(fp)
                continue
            s = self._read_met_precip_series(fp)
            series_list.append(s)

        if missing:
            raise FileNotFoundError(f"Missing met files for station {station_df.iloc[0]['Station']}: {missing}")

        if not series_list:
            raise ValueError(f"No precipitation series found for station {station_df.iloc[0]['Station']}.")

        n_days = len(self.dates)
        for s in series_list:
            if len(s) != n_days:
                raise ValueError(f"Length mismatch for station {station_df.iloc[0]['Station']}: "
                                f"expected {n_days}, got {len(s)}")

        # Simple average across grids (still in mm)
        avg_mm = (sum(series_list) / len(series_list)).round(2)
        avg_mm.index = self.dates
        return avg_mm

    def _compute_station_df_allvars(self, station_df):
        """
        Compute average precip (mm), tmax (degC), tmin (degC) across grids for the station.
        Returns a DataFrame with index=self.dates and columns ['precip','tmax','tmin'].
        """
        cols = ['Lat', 'Lon'] if 'Lon' in station_df.columns else ['Lat', 'Long']
        station_df = station_df.drop_duplicates(subset=cols)

        p_list, tx_list, tn_list = [], [], []
        missing = []

        for _, row in station_df.iterrows():
            lat = float(row['Lat'])
            lon = float(row['Lon'] if 'Lon' in row else row['Long'])
            fn = self._met_filename(lat, lon)
            fp = os.path.join(self.met_path, fn)
            if not os.path.exists(fp):
                missing.append(fp)
                continue
            p, tx, tn = self._read_met_vars_series(fp)
            p_list.append(p)
            tx_list.append(tx)
            tn_list.append(tn)
            
        if missing:
            raise FileNotFoundError(f"Missing met files for station {station_df.iloc[0]['Station']}: {missing}")

        if not p_list:
            raise ValueError(f"No met series found for station {station_df.iloc[0]['Station']}.")

        n_days = len(self.dates)
        for s in p_list + tx_list + tn_list:
            if len(s) != n_days:
                raise ValueError(f"Length mismatch for station {station_df.iloc[0]['Station']}: "
                                f"expected {n_days}, got {len(s)}")

        df = pd.DataFrame(index=self.dates)
        df['precip'] = (sum(p_list) / len(p_list)).values.round(2)
        df['tmax'] = (sum(tx_list) / len(tx_list)).values.round(2)
        df['tmin'] = (sum(tn_list) / len(tn_list)).values.round(2)
        return df

    def run(self):
        coord = pd.read_csv(self.coord_file)
        # Normalize longitude column name
        if 'Lon' not in coord.columns and 'Long' in coord.columns:
            coord = coord.rename(columns={'Long': 'Lon'})
        coord = coord[coord['Station'].isin(self.station_order)].copy()

        product_label = "Product B" if self.product_b else "Product A"
        print(f"Compiling {len(self.station_order)} stations ({product_label})...")
        results = {}
        for idx, stn in enumerate(self.station_order, 1):
            print(f"  [{idx}/{len(self.station_order)}] {stn}")
            sub = coord[coord['Station'] == stn]
            if sub.empty:
                raise ValueError(f"No rows in coord_file for station '{stn}'")
            results[stn] = self._compute_station_series(sub)

        if self.product_b:
            result_vals = {stn: s.values for stn, s in results.items()}
            self._write_product_b_chunks(result_vals)
            print("Done.")
            return pd.DataFrame(result_vals)

        # Product A: combine, clip, add calendar columns, write single CSV
        df = pd.DataFrame(index=self.dates)
        for stn in self.station_order:
            df[stn] = results[stn].values

        if self.clip_period:
            df = df.loc[self.clip_period[0]:self.clip_period[1]]

        df_out = pd.DataFrame({
            'year':  df.index.year.astype(int),
            'month': df.index.month.astype(int),
            'day':   df.index.day.astype(int),
            'DOY':   df.index.dayofyear.astype(int)
        }, index=df.index)
        for stn in self.station_order:
            df_out[stn] = df[stn].values

        os.makedirs(os.path.dirname(os.path.abspath(self.output_csv)), exist_ok=True)
        df_out.to_csv(self.output_csv, index=False)
        print(f"Wrote {len(df_out)} rows to {self.output_csv}")
        return df_out

    def _write_product_b_chunks(self, result_vals):
        """Split 1000-year daily station precip into 10 CSV chunks of 100 water years each.
        Skips first 273 days (Jan-Sep) to align to Oct water year start.
        Each chunk spans template WY1922-WY2021 (Sep 30 1921 - Sep 2021).
        Sep 30 1921 values are copied from reference/mm_pcp4.csv.
        Output files: {base}_n01{ext} ... {base}_n10{ext}
        """
        skip_days = 273
        date_template_oct = pd.date_range('1921-10-01', '2021-09-30', freq='D')
        days_per_chunk = len(date_template_oct)  # 36524
        total_chunks = 10
        total_needed = skip_days + days_per_chunk * total_chunks
        for stn, vals in result_vals.items():
            if len(vals) < total_needed:
                raise ValueError(f"{stn}: need {total_needed} days, got {len(vals)}")

        # Read Sep 30 1921 reference row from reference/mm_pcp4.csv
        ref_mm = pd.read_csv(os.path.join(self.ref_dir, 'mm_pcp4.csv'), nrows=1)
        sep30_ref = ref_mm.iloc[0]

        # Full date template including Sep 30
        date_template = pd.date_range('1921-09-30', '2021-09-30', freq='D')

        out_dir = os.path.dirname(os.path.abspath(self.output_csv))
        base, ext = os.path.splitext(os.path.basename(self.output_csv))
        os.makedirs(out_dir, exist_ok=True)
        print(f"  Product B: {days_per_chunk}+1 days/chunk, {total_chunks} chunks (skip {skip_days} days, prepend Sep 30 ref)")
        for i in range(total_chunks):
            df_chunk = pd.DataFrame({
                'year':  date_template.year.astype(int),
                'month': date_template.month.astype(int),
                'day':   date_template.day.astype(int),
                'DOY':   date_template.dayofyear.astype(int),
            })
            for stn in self.station_order:
                aligned = result_vals[stn][skip_days:]
                chunk_data = aligned[i * days_per_chunk:(i + 1) * days_per_chunk]
                df_chunk[stn] = [float(sep30_ref[stn])] + list(chunk_data)
            out_file = os.path.join(out_dir, f"{base}_n{i+1:02d}{ext}")
            df_chunk.to_csv(out_file, index=False)
            print(f"    Chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def _write_product_b_lodi_chunks(self, df_vars, output_csv_lodi):
        """Split 1000-year daily Lodi met into 10 CSV chunks of 100 water years each.
        Sep 30 1921 values are copied from reference/LODI_PT4.csv."""
        skip_days = 273
        date_template_oct = pd.date_range('1921-10-01', '2021-09-30', freq='D')
        days_per_chunk = len(date_template_oct)
        total_chunks = 10
        total_needed = skip_days + days_per_chunk * total_chunks
        precip_vals = df_vars['precip'].values
        tmax_vals   = df_vars['tmax'].values
        tmin_vals   = df_vars['tmin'].values
        if len(precip_vals) < total_needed:
            raise ValueError(f"Lodi: need {total_needed} days, got {len(precip_vals)}")

        # Read Sep 30 1921 reference row from reference/LODI_PT4.csv
        ref_lodi = pd.read_csv(os.path.join(self.ref_dir, 'LODI_PT4.csv'), nrows=1)
        sep30_lodi = ref_lodi.iloc[0]

        # Full date template including Sep 30
        date_template = pd.date_range('1921-09-30', '2021-09-30', freq='D')

        out_dir = os.path.dirname(os.path.abspath(output_csv_lodi))
        base, ext = os.path.splitext(os.path.basename(output_csv_lodi))
        os.makedirs(out_dir, exist_ok=True)
        print(f"  Product B Lodi: {days_per_chunk}+1 days/chunk, {total_chunks} chunks (skip {skip_days} days, prepend Sep 30 ref)")
        for i in range(total_chunks):
            p_chunk  = precip_vals[skip_days:][i * days_per_chunk:(i + 1) * days_per_chunk]
            tx_chunk = tmax_vals  [skip_days:][i * days_per_chunk:(i + 1) * days_per_chunk]
            tn_chunk = tmin_vals  [skip_days:][i * days_per_chunk:(i + 1) * days_per_chunk]
            df_chunk = pd.DataFrame({
                'Date':    date_template.strftime('%Y-%m-%d'),
                'Year':    date_template.year.astype(int),
                'Month':   date_template.month.astype(int),
                'DOY':     date_template.dayofyear.astype(int),
                'Pcp(mm)': [float(sep30_lodi['Pcp(mm)'])] + list(p_chunk),
                'Tx(oC)':  [float(sep30_lodi['Tx(oC)'])] + list(tx_chunk),
                'Tn(oC)':  [float(sep30_lodi['Tn(oC)'])] + list(tn_chunk),
            })
            out_file = os.path.join(out_dir, f"{base}_n{i+1:02d}{ext}")
            df_chunk.to_csv(out_file, index=False)
            print(f"    Lodi chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def export_lodi_with_temps(self, output_csv_lodi):
        """
        Create a CSV for Lodi with columns:
        Date,Year,Month,DOY,Pcp(mm),Tx(oC),Tn(oC)
        """
        coord = pd.read_csv(self.coord_file)
        if 'Lon' not in coord.columns and 'Long' in coord.columns:
            coord = coord.rename(columns={'Long': 'Lon'})

        lodi_df = coord[coord['Station'] == 'Lodi'].copy()
        if lodi_df.empty:
            raise ValueError("No rows in coord_file for station 'Lodi'")

        df_vars = self._compute_station_df_allvars(lodi_df)

        if self.product_b:
            self._write_product_b_lodi_chunks(df_vars, output_csv_lodi)
            return df_vars

        # Product A: clip, build output columns, write single CSV
        if self.clip_period:
            df_vars = df_vars.loc[self.clip_period[0]:self.clip_period[1]]

        # Build output with requested columns and names
        df_out = pd.DataFrame(index=df_vars.index)
        df_out['Date'] = df_out.index.strftime('%Y-%m-%d')
        df_out['Year'] = df_out.index.year.astype(int)
        df_out['Month'] = df_out.index.month.astype(int)
        df_out['DOY'] = df_out.index.dayofyear.astype(int)
        df_out['Pcp(mm)'] = df_vars['precip'].astype(float).values
        df_out['Tx(oC)'] = df_vars['tmax'].astype(float).values
        df_out['Tn(oC)'] = df_vars['tmin'].astype(float).values

        # Write CSV
        df_out.to_csv(output_csv_lodi, index=False)
        return df_out


def main(): 
    ap = argparse.ArgumentParser(description="Compile daily precipitation (mm) for DCD stations from WGEN met files.") 
    ap.add_argument('--coord_file', default=None,
                    help='Path to station coordinate CSV. Defaults to ./input/USBR_LTO_ClimateChange_DCD_StnsVICCoordinates_20210425.csv') 
    ap.add_argument('--met_path', default=None,
                    help='Directory containing WGEN met files. Default resolved from config.') 
    ap.add_argument('--output_csv', default=None,
                    help='Output CSV path. Defaults to ./output/Product_A/mm_pcp4.csv or Product_B/mm_pcp4.csv.') 
    ap.add_argument('--start_date', default='1915-01-01', help='Start date (YYYY-MM-DD)') 
    ap.add_argument('--end_date', default='2018-12-31', help='End date (YYYY-MM-DD)') 
    ap.add_argument('--met_prefix', default='meteo', help='Met file prefix (default: meteo)') 
    ap.add_argument('--met_sep', default='\s+', help='Separator for met files (regex OK)') 
    ap.add_argument('--clip_period', nargs=2, default=None, help='Optional clip start end (YYYY-MM-DD) [Product A only]') 
    ap.add_argument('--lodi_output_csv', default=None, help='Optional path to write Lodi precip and temperature CSV') 
    ap.add_argument('--product', choices=['A', 'B'], required=True,
                    help='Product to generate: A (historical 1921-2018) or B (stochastic 1000-yr chunks).')
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_hydrology/delta_channel_depletion")

    coord_file = args.coord_file or str(
        script_dir / 'reference' / 'USBR_LTO_ClimateChange_DCD_StnsVICCoordinates_20210425.csv'
    )
    product_b = args.product == 'B'
    if product_b:
        met_path   = args.met_path   or str(_base / 'WGEN' / 'Product_B' / '1')
        output_csv = args.output_csv or str(_gen / 'output' / '_1_compile_precip_DETAW' / 'Product_B' / 'mm_pcp4.csv')
        lodi_csv   = args.lodi_output_csv or str(_gen / 'output' / '_1_compile_precip_DETAW' / 'Product_B' / 'LODI_PT4.csv')
    else:
        met_path   = args.met_path   or str(_base / 'WGEN' / 'Product_A' / '1')
        output_csv = args.output_csv or str(_gen / 'output' / '_1_compile_precip_DETAW' / 'Product_A' / 'mm_pcp4.csv')
        lodi_csv   = args.lodi_output_csv or str(_gen / 'output' / '_1_compile_precip_DETAW' / 'Product_A' / 'LODI_PT4.csv')

    runner = CompileStationsPrecipMM(
        coord_file=coord_file,
        met_path=met_path,
        output_csv=output_csv,
        start_date=args.start_date,
        end_date=args.end_date,
        met_prefix=args.met_prefix,
        met_sep=args.met_sep,
        clip_period=args.clip_period,
        product_b=product_b,
    )
    runner.run()

    if product_b or lodi_csv:
        runner.export_lodi_with_temps(lodi_csv)

if __name__ == "__main__":
    main()