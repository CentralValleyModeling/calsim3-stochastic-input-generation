import os
import sys
import glob
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

class compile_rim_inflows:
    """
    Class to compile rim inflows from fluxes.
    This class reads grid information and fluxes, computes runoff, and aggregates it.
    It can handle multiple watershed selections and outputs the results to specified files.
    Attributes:
        grid_info_path (str): Path to the directory containing grid info files.
        fluxes_path (str): Path to the directory containing VIC flux files.
        output_path (str): Path to the directory where output files will be saved.
        start_date (str): Start date for the data range (default '1915-01-01').
        end_date (str): End date for the data range (default '2021-12-31').
        product_b (bool): If True, uses Product B date handling and chunked outputs.
        flux_columns (list): List of columns expected in the flux files.
        dates (pd.DatetimeIndex|pd.PeriodIndex): Date range from start_date to end_date.
        fluxes (pd.DataFrame): DataFrame to hold flux data.
    """
    def __init__(self, grid_info_path, fluxes_path, output_path, start_date='1915-01-01', end_date='2021-12-31', product_b=False, full_vic=False):
        self.grid_info_path = os.path.join(grid_info_path)
        self.fluxes_path = os.path.join(fluxes_path)
        self.output_path = output_path
        self.start_date = start_date
        self.end_date = end_date
        self.product_b = product_b
        if full_vic:
            self.flux_columns = [
                'Year', 'Month', 'Day',
                'PREC', 'EVAP', 'RUNOFF', 'BASEFLOW', 
                'AIR_TEMP_MIN', 'AIR_TEMP_MAX', 'AIR_TEMP_AVG', 'SOIL_MOIST',
                'R_NET', 'REL_HUMID', 'SWE', 
                'WIND', 'LONGWAVE', 'SHORTWAVE', 
                'VP', 'ALBEDO', 'PET_SATSOIL', 
                'PET_H2OSURF', 'PET_SHORT', 'PET_TALL', 'PET_NATVEG'
            ]
        else:
            self.flux_columns = [
                'Year', 'Month', 'Day',
                'EVAP', 'RUNOFF', 'BASEFLOW', 
                'PET_H2OSURF', 'PET_SHORT'
            ]
        # Product B runs far beyond pandas Timestamp max; use PeriodIndex for safety
        if self.product_b:
            self.dates = pd.period_range(start='2025-01-01', end='3033-01-08', freq='D')
        else:
            self.dates = pd.date_range(start=self.start_date, end=self.end_date, freq='D')
        if not os.path.exists(self.output_path):
            os.makedirs(self.output_path)

    def compute_runoff_from_flux(self, fluxes, grid_info_row):
        # Compute runoff from fluxes and grid info row
        q = fluxes['RUNOFF'] + fluxes['BASEFLOW']
        q_adj = q * (grid_info_row['f2'] / grid_info_row['f1'])
        return q_adj

    def gather_grid_info_files(self):
        # Gather all grid info files in the specified directory
        rim_inflows_grid_info_files = glob.glob(os.path.join(self.grid_info_path, '*_GridInfo.txt'))
        if not rim_inflows_grid_info_files:
            raise FileNotFoundError("No grid info files found in the specified path.")
        return rim_inflows_grid_info_files

    def read_grid_info(self, grid_info_file):
        # Read a grid info file into a DataFrame
        if not os.path.exists(grid_info_file):
            raise FileNotFoundError(f"Grid info file not found: {grid_info_file}")
        grid_info = pd.read_csv(grid_info_file, sep='\t', header=None, names=['id', 'Lat', 'Lon', 'f1', 'f2'])
        return grid_info

    def compute_runoff(self, grid_info_file):
        # Compute runoff for a given grid info file
        grid_info = self.read_grid_info(grid_info_file)
        print(f"  Reading {len(grid_info)} grid cells...")
        q_routed = pd.Series(dtype=float)
        q_area = 0
        q_pct_area = 0
        for idx, row in grid_info.iterrows():
            flux_path = os.path.join(self.fluxes_path, f"fluxes_{row.Lat}_{row.Lon}")
            if os.path.exists(flux_path):
                flux_df = pd.read_csv(flux_path, sep='\t', header=None, names=self.flux_columns, index_col=None)
                runoff = self.compute_runoff_from_flux(flux_df, row)
                q_routed = q_routed.add(runoff, fill_value=0)
                q_pct_area += row['f2'] / row['f1']
                q_area += row['f2']
            else:
                raise FileNotFoundError(f"Flux file not found: {flux_path}")
        q_routed = q_routed / q_pct_area
        q_routed = q_routed * q_area * 1e12 * 8.10714e-13 / 1e3  # convert mm to taf
        q_routed.index = self.dates
        # Resample daily to monthly totals
        print(f"  Resampling {len(q_routed)} daily values to monthly...")
        if isinstance(q_routed.index, pd.PeriodIndex):
            # Product B: PeriodIndex can exceed Timestamp max (~2262), use groupby on period
            q_routed_monthly = q_routed.groupby(q_routed.index.asfreq('M')).sum()
        else:
            q_routed_monthly = q_routed.resample('M').sum()
        print(f"  Generated {len(q_routed_monthly)} monthly values.")
        return q_routed_monthly

    def _write_product_b_chunks(self, monthly_series, output_base_path):
        # Create 10 chunks of 100 full water years (Oct-Sep) each
        # Water year convention: Oct 1921 - Sep 2021 (WY1922-WY2021)
        # Skip first 9 months (Jan-Sep of year 1) to align to October start
        months_per_chunk = 100 * 12  # 1200 months = 100 water years
        total_chunks = 10
        skip_months = 9  # Skip Jan-Sep of year 1 to start at October
        
        total_needed = skip_months + (months_per_chunk * total_chunks)  # 9 + 12000 = 12009 months
        if len(monthly_series) < total_needed:
            raise ValueError(f"Product B monthly series has {len(monthly_series)} months; need at least {total_needed}.")
        
        # Skip first 9 months to align to October (water year start)
        aligned = monthly_series.iloc[skip_months:]
        
        # Build date template for 100 water years: Oct 1921 - Sep 2021
        # WY1922 = Oct 1921 - Sep 1922, ..., WY2021 = Oct 2020 - Sep 2021
        years_list = []
        months_list = []
        for wy in range(1922, 2022):  # Water years 1922-2021
            # Oct-Dec of previous calendar year
            for m in [10, 11, 12]:
                years_list.append(wy - 1)
                months_list.append(m)
            # Jan-Sep of the water year's calendar year
            for m in range(1, 10):
                years_list.append(wy)
                months_list.append(m)
        
        years_template = np.array(years_list)    # 1200 elements
        months_template = np.array(months_list)  # 1200 elements

        print(f"  Writing {total_chunks} chunks of {months_per_chunk//12} water years each...")
        for i in range(total_chunks):
            start = i * months_per_chunk
            end = (i + 1) * months_per_chunk
            s = aligned.iloc[start:end]

            # Build a DataFrame with year, month, value columns
            df = s.to_frame(name='qmo').reset_index(drop=True)
            df.insert(0, 'y', years_template)
            df.insert(1, 'm', months_template)

            out_file = f"{output_base_path}_qmo_n{i+1:02d}.csv"
            df.to_csv(out_file, header=False, index=False)
            print(f"    Wrote chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def run(self, select_watershed=None):
        # Main method to run the compilation for selected watersheds
        rim_inflows_grid_info_files = self.gather_grid_info_files()
        if select_watershed:
            rim_inflows_grid_info_files = [f for f in rim_inflows_grid_info_files if any(ws in f for ws in select_watershed)]
        print(f"Processing {len(rim_inflows_grid_info_files)} watershed(s)...")
        results = {}
        for i, grid_info_file in enumerate(rim_inflows_grid_info_files, 1):
            base_name = os.path.basename(grid_info_file).replace('_GridInfo.txt', '')
            print(f"\n[{i}/{len(rim_inflows_grid_info_files)}] {base_name}")
            q_routed_monthly = self.compute_runoff(grid_info_file)
            if self.product_b:
                output_base = os.path.join(self.output_path, base_name)
                self._write_product_b_chunks(q_routed_monthly, output_base)
            else:
                output_file = os.path.join(self.output_path, f"{base_name}_qmo.csv")
                q_routed_monthly.to_csv(output_file, header=False)
                print(f"  Wrote: {os.path.basename(output_file)}")
            results[grid_info_file] = q_routed_monthly
        print(f"\nCompleted {len(results)} watershed(s).")
        return results

def main():
    # Parse command-line arguments and run the compilation
    _vic_gen = get_module_generated_dir("mod_hydrology/vic")
    _script_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Compile rim inflows from VIC fluxes.")
    parser.add_argument('--grid_info_path', type=str, default=None, help='Path to grid info directory (default: reference/GridInfo)')
    parser.add_argument('--fluxes_path', type=str, default=None, help='Path to VIC fluxes directory')
    parser.add_argument('--full_vic', action='store_true', help='If set, use full VIC output (default is trimmed).')
    parser.add_argument('--output_path', type=str, default=None, help='Path to output directory')
    parser.add_argument('--start_date', type=str, default='1915-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end_date', type=str, default='2018-12-31', help='End date (YYYY-MM-DD)')
    parser.add_argument('--watersheds', type=str, nargs='*', default=None, help='Watershed names to select (optional)')
    parser.add_argument('--Product_B', action='store_true', help='If set, split outputs into ten 100-year chunks (trim last ~8 years).')
    args = parser.parse_args()

    grid_info_path = args.grid_info_path or str(_script_dir / 'reference' / 'GridInfo')

    if args.Product_B:
        fluxes_path = args.fluxes_path or str(_vic_gen / 'output' / 'fluxes' / 'Product_B' / '1')
        output_path = args.output_path or str(_vic_gen / 'output' / 'routed' / 'Product_B' / '1')
    else:
        fluxes_path = args.fluxes_path or str(_vic_gen / 'output' / 'fluxes' / 'Product_A' / '1')
        output_path = args.output_path or str(_vic_gen / 'output' / 'routed' / 'Product_A' / '1')

    rim = compile_rim_inflows(
        grid_info_path=grid_info_path,
        fluxes_path=fluxes_path,
        output_path=output_path,
        start_date=args.start_date,
        end_date=args.end_date,
        product_b=args.Product_B,
        full_vic=args.full_vic
    )
    rim.run(select_watershed=args.watersheds)

if __name__ == "__main__":
    # Historical:
    # python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo --fluxes_path ./output/fluxes/Historical --output_path ./output/routed/Historical --watersheds CS3_8RI_DPR_I
    # Product A:
    # python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo --fluxes_path ./output/fluxes/Product_A/1 --output_path ./output/routed/Product_A/1 --watersheds CS3_8RI_OROVI
    # Product B (writes 10 chunk files per watershed):
    # python _2_compile_rim_inflows.py --grid_info_path ./reference/GridInfo --fluxes_path ./output/fluxes/Product_B/1 --output_path ./output/routed/Product_B/1 --Product_B --watersheds CS3_8RI_OROVI
    main()
