"""
Compile Monthly Area-Weighted Precipitation for Small Watersheds
================================================================
Reads grid info and daily WGEN meteorology, computes area-weighted monthly
precip (inches/month) per small watershed, and writes the result into a
CVprecip .dat template for Product A (historical) or Product B (10 chunks).

Inputs
------
- Small-watershed grid-info file
- WGEN met files (Product_A / Product_B)

Outputs
-------
- CVprecip .dat  (Product A)
- 10 chunk .dat files  (Product B)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
Product A (historical, clip to WY 1921-2018):
    python _1_compile_precip_sws.py --clip_period 1920-10-01 2018-09-30

Product B (stochastic, writes 10 chunk .dat files):
    python _1_compile_precip_sws.py --Product_B
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


class CompileSmallWatershedPrecip:
    """
    Compile monthly (sum of daily) precipitation for each small watershed from VIC met files (area‑weighted).
    Grid info file columns assumed:
        watershed_id  Lat  Lon  pct_area  f1  f2
    Weight used = f2 / f1 (see WBA documentation for details).
    Output: wide monthly matrix (rows = months, columns = watershed ids) in inches/month.
    """

    def __init__(self,
                 grid_info_file: str,
                 met_path: str,
                 met_prefix: str,
                 met_sep: str,
                 start_date: str,
                 end_date: str,
                 clip_period: Optional[List[str]],
                 mm_to_in: float = 0.0393701,
                 product_b: bool = False):
        self.grid_info_file = grid_info_file
        self.met_path = met_path
        self.met_prefix = met_prefix
        self.met_sep = met_sep
        self.start_date = start_date
        self.end_date = end_date
        self.clip_period = clip_period
        self.mm_to_in = mm_to_in
        self.product_b = product_b
        self.met_columns = ["Year", "Month", "Day", "precip", "tmax", "tmin"]
        if self.product_b:
            # Product B spans ~1000 years; use PeriodIndex to exceed pandas Timestamp max (~2262)
            self.date_index = pd.period_range(start='2025-01-01', end='3033-01-08', freq='D')
        else:
            self.date_index = pd.date_range(start=start_date, end=end_date, freq="D")

    
    def _read_grid_info(self) -> pd.DataFrame:
        return pd.read_csv(
            self.grid_info_file,
            sep=r"\s+",
            header=None,
            names=["watershed_id", "Lat", "Lon", "pct_area", "f1", "f2"],
            engine="python"
        )

    def _build_met_filepath(self, lat: float, lon: float) -> str:
        # Match naming pattern used in WBA script: {prefix}_{Lat}_{Lon}
        return os.path.join(self.met_path, f"{self.met_prefix}_{lat}_{lon}")

    def _read_met(self, path: str) -> pd.DataFrame:
        df = pd.read_csv(path,
                         sep=self.met_sep,
                         header=None,
                         names=self.met_columns,
                         engine="python")
        df["date"] = pd.to_datetime(df[["Year", "Month", "Day"]])
        # Restrict to overall date window early to reduce memory
        df = df[(df["date"] >= self.start_date) & (df["date"] <= self.end_date)]
        df = df.set_index("date")
        return df

    def _read_met_product_b(self, path: str) -> pd.Series:
        """Read precip column from a Product B WGEN met file (no real dates; assign PeriodIndex)."""
        df = pd.read_csv(path,
                         sep=self.met_sep,
                         header=None,
                         names=self.met_columns,
                         engine="python",
                         usecols=[3])  # only precip column
        s = df.iloc[:, 0].reset_index(drop=True)
        s.index = self.date_index[:len(s)]
        return s

    def _aggregate_watershed_monthly(self, grid_subset: pd.DataFrame) -> pd.Series:
        """
        Area weighted precip (mm) -> convert to inches.
        """
        weighted_sum = None
        weight_total = 0.0

        for _, row in grid_subset.iterrows():
            met_file = self._build_met_filepath(row.Lat, row.Lon)
            if not os.path.exists(met_file):
                raise FileNotFoundError(f"Missing met file: {met_file}")
            met_df = self._read_met(met_file)
            # Ensure full date coverage (fill missing with NaN)
            met_p = met_df.reindex(self.date_index)["precip"]
            weight = row.f2 / row.f1
            contrib = met_p * weight
            weighted_sum = contrib if weighted_sum is None else (weighted_sum + contrib)
            weight_total += weight

        series_mm = weighted_sum / weight_total
        in_series = (series_mm * self.mm_to_in).resample('M').sum()
        in_series.name = grid_subset.iloc[0].watershed_id
        return in_series

    def _aggregate_watershed_monthly_product_b(self, grid_subset: pd.DataFrame) -> pd.Series:
        """Area-weighted daily precip (mm) → monthly inches for Product B (PeriodIndex, no real dates)."""
        weighted_sum = None
        weight_total = 0.0
        for _, row in grid_subset.iterrows():
            met_file = self._build_met_filepath(row.Lat, row.Lon)
            if not os.path.exists(met_file):
                raise FileNotFoundError(f"Missing met file: {met_file}")
            met_p = self._read_met_product_b(met_file)
            weight = row.f2 / row.f1
            weighted_sum = met_p * weight if weighted_sum is None else (weighted_sum + met_p * weight)
            weight_total += weight
        series_mm = weighted_sum / weight_total
        # PeriodIndex: group by monthly period
        monthly_in = series_mm.groupby(series_mm.index.asfreq('M')).sum() * self.mm_to_in
        monthly_in.name = grid_subset.iloc[0].watershed_id
        return monthly_in

    def compile_all(self) -> pd.DataFrame:
        grid = self._read_grid_info()
        ws_ids = sorted(grid.watershed_id.unique())
        product_label = "Product B" if self.product_b else "Product A"
        print(f"Compiling {len(ws_ids)} watersheds ({product_label})...")
        agg_fn = self._aggregate_watershed_monthly_product_b if self.product_b else self._aggregate_watershed_monthly
        series_list = []
        for idx, wsid in enumerate(ws_ids, 1):
            print(f"  [{idx}/{len(ws_ids)}] Watershed {wsid}")
            subset = grid[grid.watershed_id == wsid]
            s = agg_fn(subset)
            s.name = str(wsid)
            series_list.append(s)
        print("Concatenating results...")
        monthly_df = pd.concat(series_list, axis=1)
        if not self.product_b and self.clip_period:
            monthly_df = monthly_df.loc[self.clip_period[0]: self.clip_period[1]]
            print(f"Clipped to {self.clip_period[0]} – {self.clip_period[1]}: {len(monthly_df)} months")
        else:
            print(f"Total months: {len(monthly_df)}")
        return monthly_df

    def write_product_b_chunks(self, df: pd.DataFrame, cvprecip_file: str, output_path: str) -> None:
        """Split 1000-year monthly precip into 10 .dat files of 100 water years each.
        Skips first 9 months (Jan-Sep of synthetic year 1) to align to Oct water year start.
        Each chunk spans template WY1922-WY2021 (Oct 1921 - Sep 2021);
        WY1921 (rows 104-115) is preserved from the template as initialization.
        Output files are named {base}_n01.dat ... {base}_n10.dat.
        """
        months_per_chunk = 100 * 12  # 1200 months (WY1922-WY2021)
        skip_months = 9             # Jan-Sep of synthetic year 1
        total_chunks = 10
        header_rows = 104
        init_months = 12            # WY1921 initialization preserved from template
        total_needed = skip_months + months_per_chunk * total_chunks
        if len(df) < total_needed:
            raise ValueError(f"Product B monthly series has {len(df)} months; need at least {total_needed}.")
        os.makedirs(output_path, exist_ok=True)
        cvprecip_dat_template = pd.read_csv(cvprecip_file, delimiter='\t', header=None)
        print(f"  Template shape: {cvprecip_dat_template.shape}")
        aligned = df.iloc[skip_months:].reset_index(drop=True)
        base_name, ext = os.path.splitext(os.path.basename(cvprecip_file))
        print(f"  Product B: {months_per_chunk} months/chunk, {total_chunks} chunks (skip {skip_months} months)")
        for i in range(total_chunks):
            chunk = aligned.iloc[i * months_per_chunk:(i + 1) * months_per_chunk].values
            dat = cvprecip_dat_template.copy()
            # Write synthetic data after the initialization period (WY1921)
            dat.iloc[header_rows + init_months:header_rows + init_months + months_per_chunk, 1393:(1393 + df.shape[1])] = chunk
            out_name = f"{base_name}_n{i+1:02d}{ext}"
            out_file = os.path.join(output_path, out_name)
            dat.iloc[:header_rows].to_csv(out_file, sep='\t', index=False, header=False, float_format='%.0f')
            dat.iloc[header_rows:header_rows + init_months + months_per_chunk].to_csv(out_file, sep='\t', index=False, header=False, float_format='%.3f', mode='a')
            print(f"    Chunk {i+1:02d}/10: {os.path.basename(out_file)}")

    def write_matrix(self,
                     df: pd.DataFrame,
                     cvprecip_file: str,
                     output_path: str):
        print(f"Loading template: {cvprecip_file}")
        cvprecip_dat = pd.read_csv(cvprecip_file, delimiter='\t', header=None)
        print(f"  Template shape: {cvprecip_dat.shape}")
        print(f"  Data shape:     {df.shape}")
        n_months = len(df)
        cvprecip_dat.iloc[104:104 + n_months, 1393:(1393 + df.shape[1])] = df.values
        out_file = os.path.join(output_path, os.path.basename(cvprecip_file))
        os.makedirs(output_path, exist_ok=True)
        cvprecip_dat.iloc[:104].to_csv(out_file, sep='\t', index=False, header=False, float_format='%.0f')
        cvprecip_dat.iloc[104:104 + n_months].to_csv(out_file, sep='\t', index=False, header=False, float_format='%.3f', mode='a')
        print(f"  Written: {out_file}")


def parse_args():
    p = argparse.ArgumentParser(description="Compile monthly small watershed precipitation matrix (INCHES/MONTH).")
    p.add_argument("--grid_info_file", default=None, help="Path to SmallWatersheds grid info file. Defaults to reference/SmallWatersheds_Grid_Info_20200915_RowBased.txt.")
    p.add_argument("--met_path", default=None,
                   help="Directory containing WGEN met files. Default resolved from config.")
    p.add_argument("--CVprecip_file", default=None,
                   help=".dat template file path. Defaults to reference/CVprecipWY1921_2021.dat.")
    p.add_argument("--met_prefix", default="meteo", help="Met file prefix (default: meteo).")
    p.add_argument("--met_sep", default=r"\s+", help="Met file separator regex (default: whitespace).")
    p.add_argument("--start_date", default="1920-10-01", help="Start date (default: 1920-10-01).")
    p.add_argument("--end_date", default="2021-09-30", help="End date (default: 2021-09-30).")
    p.add_argument("--clip_period", nargs=2, default=None, help="Clip start end (YYYY-MM-DD YYYY-MM-DD) [Product A only].")
    p.add_argument("--output_path", default=None,
                   help="Output directory. Default resolved from config.")
    p.add_argument("--Product_B", action="store_true",
                   help="If set, read WGEN Product B files and split output into ten 100-WY chunk CSVs.")
    return p.parse_args()


def main():
    args = parse_args()

    script_dir = Path(__file__).resolve().parent
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_hydrology/small_watersheds")

    grid_info_file = args.grid_info_file or str(
        script_dir / 'reference' / 'SmallWatersheds_Grid_Info_20200915_RowBased.txt'
    )
    cvprecip_file = args.CVprecip_file or str(
        script_dir / 'reference' / 'CVprecipWY1921_2021.dat'
    )
    if args.Product_B:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_B' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip_sws' / 'Product_B')
    else:
        met_path = args.met_path or str(_base / 'WGEN' / 'Product_A' / '1')
        output_path = args.output_path or str(_gen / 'output' / '_1_compile_precip_sws' / 'Product_A')

    compiler = CompileSmallWatershedPrecip(
        grid_info_file=grid_info_file,
        met_path=met_path,
        met_prefix=args.met_prefix,
        met_sep=args.met_sep,
        start_date=args.start_date,
        end_date=args.end_date,
        clip_period=args.clip_period,
        product_b=args.Product_B,
    )
    df = compiler.compile_all()

    if args.Product_B:
        compiler.write_product_b_chunks(df, cvprecip_file, output_path)
    else:
        compiler.write_matrix(df, cvprecip_file, output_path)
        print(f"Wrote monthly matrix: {os.path.basename(cvprecip_file)}")

    print(f"Rows (months): {df.shape[0]}, Watersheds: {df.shape[1]}")

if __name__ == "__main__":
    # Product A:
    # python _1_compile_precip_sws.py --clip_period 1920-10-01 2018-09-30
    # Product B (writes 10 chunk .dat files):
    # python _1_compile_precip_sws.py --Product_B
    main()