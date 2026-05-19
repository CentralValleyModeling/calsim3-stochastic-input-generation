"""
Compile Area-Weighted VIC ET per WBA, Quantile-Mapped to CS3 Monthly ET
=======================================================================
Computes area-weighted VIC ET per Water Balance Area and quantile-maps it to
the CalSim3 monthly ET baseline, writing the CalSimHydro ET inputs for
Product A (1921-2018) or Product B (chunked).

Inputs
------
- VIC flux files; WBA grid info
- CS3 RefETo / CropET / PanEvap DSS (quantile-mapping target)

Outputs
-------
- <generated>/output/_2_compile_et/Product_A/  (monthly QM'd ET CSVs; optional DSS)
- <generated>/output/_2_compile_et/Product_B/  (with --Product_B)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
Product A - single type:
    python _2_compile_et.py --et_type RefET --vic_col_index 7 --write_dss --n_workers 8

Product A - all types at once:
    python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --n_workers 8

Product B - all types at once:
    python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --Product_B --n_workers 16
"""

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

# Local quantile mapping utility
from utils.quantile_mapping import qmap_single


def year_to_wy(date: pd.Timestamp) -> int:
	"""Convert a date to water year (Oct-Sep)."""
	return date.year + 1 if date.month >= 10 else date.year

def wba_to_space(name: str) -> str:
	return name.replace("_", " ")


class CompileWBAET:
	"""
	Compile area-weighted VIC reference ET per WBA, then quantile-map to CS3 for WY 1972-2018.

	Inputs
	- grid_info_file: tab-separated file with columns for WBA id, lat, lon, and percent-area
	  Accepted schema: ['WBA','lat','lon','pct_area', ...] (as in WBA_Grid_Info_20230112_RowBased_rev02.txt)
	- vic_path: folder containing VIC flux files named 'fluxes_{lat}_{lon}' (tab-separated)
	- cshydro_dss: path to CS3 RefETo DSS file, expected pathname:
		/CALSIM/{WBA with space}/REF-ET//1MON/REFETO/
	- output_path: where CSV (and optional DSS) will be written

	Output
	- For each WBA, writes CSV with monthly quantile-mapped ET (inches/month) for WY 1972-2018
	- Optional: write a DSS time series with 1MON interval
	"""

	def __init__(
		self,
		grid_info_file: str,
		vic_path: str,
		cshydro_dss: str,
		et_type: str,
		output_path: str,
		start_date: str = "1915-01-01",
		end_date: str = "2018-12-31",
		vic_col_index: int = 21,
		write_dss: bool = False,
		product_b: bool = False,
		hist_vic_path: Optional[str] = None,
		n_workers: int = 1,
	) -> None:
		self.grid_info_file = grid_info_file
		self.vic_path = vic_path
		self.cshydro_dss = cshydro_dss
		self.et_type = et_type
		self.output_path = output_path
		self.start_date = start_date
		self.end_date = end_date
		self.vic_col_index = vic_col_index
		self.write_dss_flag = write_dss
		self.product_b = product_b
		self.hist_vic_path = hist_vic_path
		self.n_workers = n_workers
		# Product B VIC fluxes span ~1000 years - use PeriodIndex to exceed pandas Timestamp max (~2262)
		if self.product_b:
			self.dates_daily = pd.period_range(start='2025-01-01', end='3033-01-08', freq='D')
		else:
			self.dates_daily = pd.date_range(start=self.start_date, end=self.end_date, freq="D")
		# Historical DatetimeIndex always needed for QM training (Product A dates)
		self.dates_daily_hist = pd.date_range(start=self.start_date, end=self.end_date, freq="D")
		self.crops = ['AL','AP','CO','CR','CU','DB','FI','GR','NV','OG','OR','PA','PO','RI','SB','SF','SL','SO','TH','TM','TR','UR','VI']

		os.makedirs(self.output_path, exist_ok=True)

	# ---------- Data IO helpers ----------
	def _read_grid_info(self) -> pd.DataFrame:
		df = pd.read_csv(
			self.grid_info_file,
			sep="\t",
			header=None,
			names=['wba_id', 'lat', 'lon', 'pct_area', 'area_grid', 'area_wba'],
			engine="python",
		)
		return df[["wba_id", "lat", "lon", "pct_area"]]

	def _read_cshydro_monthly_et(self, wba: str, start: str, end: str) -> pd.DataFrame:
		"""Read CS3 monthly ET from DSS for the given WBA. Returns a DataFrame indexed by month-end."""
		with HecDss.Open(self.cshydro_dss, window=(start, end)) as dss:
			if self.et_type == 'RefET':
				path = f"/CALSIM/{wba}/REF-ET//1MON/REFETO/"
			elif self.et_type == 'CropET':
				path = f"/IWFM/{wba}/RATE_INCH//1MON/EVAPOTRANSPIRATION/"
			elif self.et_type == 'PanEvap':
				path = f"/CALSIM/{wba}/PAN-EVAP//1MON/PAN-EVAP/"
			else:
				raise ValueError(f"Unknown ET type: {self.et_type}")
			ts = dss.read_ts(path, window=(start, end))

		# Build monthly end-of-month index 
		idx = pd.date_range(start="1920-10-31", end="2021-09-30", freq="ME")
		df = pd.DataFrame({"CS3": ts.values}, index=idx)
		return df

	def _read_vic_flux_for_grid(
		self,
		lat: float,
		lon: float,
		path: Optional[str] = None,
		dates=None,
	) -> pd.Series:
		"""Read VIC fluxes file for one grid cell and return the ET column as a daily Series (mm/day).
		If path/dates are omitted, defaults to self.vic_path / self.dates_daily.
		"""
		path = path or self.vic_path
		dates = dates if dates is not None else self.dates_daily
		fname = os.path.join(path, f"fluxes_{lat}_{lon}")
		if not os.path.exists(fname):
			raise FileNotFoundError(f"VIC flux file not found: {fname}")
		df = pd.read_csv(fname, sep="\t", header=None, engine="python")
		vic_col_idx = self.vic_col_index - 1 if self.et_type == 'PanEvap' else self.vic_col_index
		col = df.iloc[:, vic_col_idx].astype(float)
		col.index = dates[:len(col)]
		return col

	# ---------- Core computations ----------
	def _compute_area_weighted_vic_daily(
		self,
		grid_info: pd.DataFrame,
		use_hist: bool = False,
	) -> pd.DataFrame:
		"""Area-weighted VIC daily ET across grids in a WBA (mm/day).
		If use_hist=True, reads from hist_vic_path with historical DatetimeIndex (for QM training).
		"""
		if use_hist:
			path = self.hist_vic_path or self.vic_path
			dates = self.dates_daily_hist
		else:
			path = self.vic_path
			dates = self.dates_daily
		result = pd.Series(0.0, index=dates)
		area_sum = 0.0
		for _, row in grid_info.iterrows():
			et_mm = self._read_vic_flux_for_grid(row.lat, row.lon, path=path, dates=dates)
			weight = float(row.pct_area)
			result = result.add(et_mm * weight, fill_value=0.0)
			area_sum += weight
		if area_sum == 0:
			raise ValueError("Total pct_area is zero for this WBA")
		return pd.DataFrame({'VIC': result / area_sum})

	def _prepare_monthly_inches_frame(
		self, daily_mm: pd.DataFrame
	) -> pd.DataFrame:
		"""Return a monthly DataFrame in inches/month.
		Handles both DatetimeIndex (Product A) and PeriodIndex (Product B).
		"""
		if isinstance(daily_mm.index, pd.PeriodIndex):
			# PeriodIndex can exceed Timestamp max; use groupby on period
			return daily_mm.groupby(daily_mm.index.asfreq('M')).sum() / 25.4
		return daily_mm.resample("ME").sum() / 25.4  # mm -> inches

	def _quantile_map(self, monthly_df: pd.DataFrame) -> pd.Series:
		"""Apply quantile mapping using hist: WY 1921-1971, sim: WY 1972-2018. Returns a Series for sim period."""
		df = monthly_df.copy()
		df["month"] = df.index.month
		df["wy"] = df.index.map(year_to_wy)

		train_period = (1921, 1971)
		test_period = (1972, 2018)

		ETsim = (
			df[(df["wy"] >= test_period[0]) & (df["wy"] <= test_period[1])][
				["wy", "month", "VIC"]
			]
			.rename(columns={"wy": "year", "VIC": "value"})
			.reset_index(drop=True)
		)
		EThist = (
			df[(df["wy"] >= train_period[0]) & (df["wy"] <= train_period[1])][
				["wy", "month", "VIC"]
			]
			.rename(columns={"wy": "year", "VIC": "value"})
			.reset_index(drop=True)
		)
		ETTargetHist = (
			df[(df["wy"] >= train_period[0]) & (df["wy"] <= train_period[1])][
				["wy", "month", "CS3"]
			]
			.rename(columns={"wy": "year", "CS3": "value"})
			.reset_index(drop=True)
		)

		mapped = qmap_single(ETsim, EThist, ETTargetHist)

		# Build a Series aligned to the sim-period monthly dates
		sim_mask = (df["wy"] >= test_period[0]) & (df["wy"] <= test_period[1])
		sim_dates = df.index[sim_mask]
		out = pd.Series(
			mapped["quantile_mapped_value"].values,
			index=sim_dates,
			name="ET_QMAP",
		)
		return out

	def _qmap_product_b(
		self,
		stoch_monthly_vic: pd.DataFrame,
		hist_monthly_merged: pd.DataFrame,
	) -> pd.Series:
		"""Apply QM transfer function to stochastic monthly ET.
		Trains on full historical VIC vs CS3 (WY 1921-2018), applies to the full stochastic sequence.
		hist_monthly_merged must have 'VIC' and 'CS3' columns with a DatetimeIndex.
		stoch_monthly_vic must have a 'VIC' column (PeriodIndex or integer-indexed).
		Returns a plain-values Series (no meaningful datetime index).
		"""
		df_hist = hist_monthly_merged.copy()
		df_hist["month"] = df_hist.index.month
		df_hist["wy"] = df_hist.index.map(year_to_wy)
		train_period = (1921, 2018)  # full historical period
		train_mask = (df_hist["wy"] >= train_period[0]) & (df_hist["wy"] <= train_period[1])
		EThist = (
			df_hist[train_mask][["wy", "month", "VIC"]]
			.rename(columns={"wy": "year", "VIC": "value"})
			.reset_index(drop=True)
		)
		ETTargetHist = (
			df_hist[train_mask][["wy", "month", "CS3"]]
			.rename(columns={"wy": "year", "CS3": "value"})
			.reset_index(drop=True)
		)
		# Build ETsim with sequential synthetic year IDs and calendar month
		vals = stoch_monthly_vic["VIC"].values
		n = len(vals)
		if isinstance(stoch_monthly_vic.index, pd.PeriodIndex):
			months = stoch_monthly_vic.index.month
		else:
			months = [(i % 12) + 1 for i in range(n)]
		ETsim = pd.DataFrame({
			"year": [(i // 12) + 1 for i in range(n)],
			"month": months,
			"value": vals,
		})
		mapped = qmap_single(ETsim, EThist, ETTargetHist)
		return pd.Series(mapped["quantile_mapped_value"].values, name="ET_QMAP")

	def _build_product_b_monthly_chunk(self, values, chunk_idx):
		"""Build Jan 1920 - Dec 2021 monthly data array for one Product B chunk.

		Core (non-overlapping): Oct 1921 - Sep 2021 (1200 months = 100 WY).
		Jan 1921 - Sep 1921: data preceding this chunk's core.
		Oct 2021 - Dec 2021: data following this chunk's core.
		Jan 1920 - Dec 1920: Backfill (duplicate of Jan-Dec 1921).
		"""
		months_per_chunk = 1200
		skip_months = 9
		pre_core_months = 9
		suffix_months = 3

		core_start = skip_months + chunk_idx * months_per_chunk

		pre_core = values[core_start - pre_core_months : core_start]
		core = values[core_start : core_start + months_per_chunk]
		post_core = values[core_start + months_per_chunk : core_start + months_per_chunk + suffix_months]

		# Jan 1921 - Dec 2021 natural data
		natural = np.concatenate([pre_core, core, post_core])

		# Backfill: Jan 1920 - Dec 1920 = copy of Jan-Dec 1921
		backfill = natural[:12]

		return np.concatenate([backfill, natural])

	def _write_product_b_chunks_csv(self, results: Dict[str, pd.Series]) -> None:
		"""Split 1000-year monthly QM ET into 10 chunks.
		Each chunk outputs Jan 1920 - Dec 2021 (1224 months).
		Core: Oct 1921 - Sep 2021 (100 WY, non-overlapping).
		Jan 1920 - Dec 1920: backfill (copy of Jan-Dec 1921).
		Oct 2021 - Dec 2021: from subsequent chunk's data.
		"""
		months_per_chunk = 1200
		skip_months = 9
		total_chunks = 10
		total_needed = skip_months + months_per_chunk * total_chunks + 3
		wba_dir = os.path.join(self.output_path, 'wba')
		os.makedirs(wba_dir, exist_ok=True)
		date_template = pd.date_range('1920-01-31', '2021-12-31', freq='ME')
		print(f"  Product B: {months_per_chunk} core months/chunk, {len(date_template)} output months/chunk, {total_chunks} chunks")
		for wba, series in results.items():
			vals = series.values
			if len(vals) < total_needed:
				raise ValueError(f"{wba}: need {total_needed} months, got {len(vals)}")
			for i in range(total_chunks):
				chunk = self._build_product_b_monthly_chunk(vals, i)
				df = pd.DataFrame({
					'y': date_template.year,
					'm': date_template.month,
					'value': chunk,
				})
				out_file = os.path.join(wba_dir, f"{wba}_{self.et_type}_n{i+1:02d}.csv")
				df.to_csv(out_file, header=False, index=False)
				print(f"    Chunk {i+1:02d}/10: {os.path.basename(out_file)}")

	def _write_product_b_dss(self, results: Dict[str, pd.Series]) -> None:
		"""Write 10 per-chunk DSS files for Product B, Jan 1920 - Dec 2021 each."""
		total_chunks = 10
		start_dt_str = "31JAN1920 24:00:00"
		if self.et_type == 'CropET':
			dss_stem = "CS3_ET"
		elif self.et_type == 'PanEvap':
			dss_stem = "CS3_PanEvap"
		else:
			dss_stem = "CS3_RefET"
		for i in range(total_chunks):
			dss_out = os.path.join(self.output_path, f"{dss_stem}_n{i+1:02d}.dss")
			print(f"  Writing DSS chunk {i+1:02d}/10: {os.path.basename(dss_out)}")
			with HecDss.Open(dss_out, version=6) as dss:
				for wba, series in results.items():
					chunk = self._build_product_b_monthly_chunk(series.values, i)
					tsc = TimeSeriesContainer()
					if self.et_type == 'CropET':
						tsc.pathname = f"/IWFM/{wba}/RATE_INCH//1MON/EVAPOTRANSPIRATION/"
					elif self.et_type == 'PanEvap':
						tsc.pathname = f"/CALSIM/{wba}/PAN-EVAP//1MON/PAN-EVAP/"
					else:
						tsc.pathname = f"/CALSIM/{wba_to_space(wba)}/REF-ET//1MON/REFETO/"
					tsc.startDateTime = start_dt_str
					tsc.numberValues = len(chunk)
					tsc.units = "Inch" if self.et_type == 'PanEvap' else "IN/MONTH"
					tsc.type = "PER-CUM"
					tsc.interval = 1
					tsc.values = chunk.astype(float)
					dss.put_ts(tsc)
			if self.et_type == 'CropET':
				self._copy_static_crop_et_records(dss_out)

	def _copy_static_crop_et_records(self, dss_out_path: str) -> None:
		"""Copy static CropET records (Part D = 01JAN4000) from reference DSS to output DSS.
		These are repeating/constant values that are not modified by Product A or B.
		"""
		with HecDss.Open(self.cshydro_dss) as src:
			all_paths = src.getPathnameList("/*/*/RATE_INCH/01JAN4000/1MON/EVAPOTRANSPIRATION/") or []
			if not all_paths:
				print("  No static CropET records (01JAN4000) found in reference DSS.")
				return
			print(f"  Copying {len(all_paths)} static CropET records (01JAN4000) to {os.path.basename(dss_out_path)}")
			records = []
			for path in all_paths:
				ts = src.read_ts(path)
				records.append((path, ts))

		with HecDss.Open(dss_out_path, version=6) as dst:
			for path, ts in records:
				tsc = TimeSeriesContainer()
				tsc.pathname = path
				tsc.startDateTime = "01JAN4000 24:00:00"
				tsc.numberValues = len(ts.values)
				tsc.units = ts.units
				tsc.type = ts.type
				tsc.interval = 1
				tsc.values = ts.values.astype(float)
				dst.put_ts(tsc)

	# run all
	def _preload_cs3_data(self, wbas: List[str], dss_start: str, dss_end: str) -> Dict[str, pd.DataFrame]:
		"""Read all required CS3 records from DSS into a dict before parallelising.
		pydsstools is not thread-safe, so we collect everything single-threaded here.
		"""
		cache: Dict[str, pd.DataFrame] = {}
		for wba in wbas:
			if self.et_type == 'CropET':
				for crop in self.crops:
					crop_wba = wba.replace("_", "") + '_' + crop + '_ET'
					if 'SL' in crop_wba or 'UR' in crop_wba:
						continue
					cache[crop_wba] = self._read_cshydro_monthly_et(crop_wba, dss_start, dss_end)
			else:
				cshydro_wba = 'WBA02' if wba == 'Gerber' else wba_to_space(wba)
				cache[cshydro_wba] = self._read_cshydro_monthly_et(cshydro_wba, dss_start, dss_end)
		return cache

	def _process_wba(
		self,
		wba: str,
		grids: pd.DataFrame,
		cs3_cache: Dict[str, pd.DataFrame],
	) -> Dict[str, pd.Series]:
		"""All processing for a single WBA - VIC reading, monthly aggregation, QM.
		Safe to run in a thread pool (no DSS I/O; uses pre-cached CS3 data).
		"""
		print(f"Processing {wba}")
		wba_results: Dict[str, pd.Series] = {}
		vic_daily_mm = self._compute_area_weighted_vic_daily(grids)
		vic_monthly_in = self._prepare_monthly_inches_frame(vic_daily_mm)
		if self.product_b:
			hist_daily_mm = self._compute_area_weighted_vic_daily(grids, use_hist=True)
			hist_monthly_in = self._prepare_monthly_inches_frame(hist_daily_mm)
			if self.et_type == 'CropET':
				for crop in self.crops:
					crop_wba = wba.replace("_", "") + '_' + crop + '_ET'
					if 'SL' in crop_wba or 'UR' in crop_wba:
						continue
					cs3_monthly_in = cs3_cache[crop_wba]
					hist_merged = pd.merge(hist_monthly_in, cs3_monthly_in, left_index=True, right_index=True)
					qmap_series = self._qmap_product_b(vic_monthly_in, hist_merged)
					wba_results[crop_wba] = qmap_series
			else:
				cshydro_wba = 'WBA02' if wba == 'Gerber' else wba_to_space(wba)
				cs3_monthly_in = cs3_cache[cshydro_wba]
				hist_merged = pd.merge(hist_monthly_in, cs3_monthly_in, left_index=True, right_index=True)
				qmap_series = self._qmap_product_b(vic_monthly_in, hist_merged)
				wba_results[cshydro_wba] = qmap_series
		else:
			if self.et_type == 'CropET':
				for crop in self.crops:
					crop_wba = wba.replace("_", "") + '_' + crop + '_ET'
					if 'SL' in crop_wba or 'UR' in crop_wba:
						continue
					cs3_monthly_in = cs3_cache[crop_wba]
					monthly_df = pd.merge(vic_monthly_in, cs3_monthly_in, left_index=True, right_index=True)
					qmap_series = self._quantile_map(monthly_df)
					wba_results[crop_wba] = qmap_series
			else:
				cshydro_wba = 'WBA02' if wba == 'Gerber' else wba_to_space(wba)
				cs3_monthly_in = cs3_cache[cshydro_wba]
				monthly_df = pd.merge(vic_monthly_in, cs3_monthly_in, left_index=True, right_index=True)
				qmap_series = self._quantile_map(monthly_df)
				wba_results[cshydro_wba] = qmap_series
		return wba_results

	def run(self, select_wbas: Optional[List[str]] = None) -> Dict[str, pd.Series]:
		grid_info_all = self._read_grid_info()
		if self.et_type == 'PanEvap':
			wbas = ['Gerber']
		elif select_wbas:
			wbas = list(select_wbas)
		else:
			wbas = grid_info_all["wba_id"].unique().tolist()
			wbas.remove('Gerber')

		dss_start = "31OCT1920 00:00:00"
		dss_end = "30SEP2021 24:00:00"

		# Pre-load all CS3 DSS records single-threaded (pydsstools is not thread-safe)
		print("Pre-loading CS3 DSS data...")
		cs3_cache = self._preload_cs3_data(wbas, dss_start, dss_end)

		# Build per-WBA grid subsets, dropping any with no grids
		wba_grids = {
			wba: grid_info_all[grid_info_all["wba_id"] == wba].copy()
			for wba in wbas
		}
		wba_grids = {wba: g for wba, g in wba_grids.items() if not g.empty}

		results: Dict[str, pd.Series] = {}
		if self.n_workers > 1:
			with ProcessPoolExecutor(max_workers=self.n_workers) as executor:
				futures = {
					executor.submit(self._process_wba, wba, grids, cs3_cache): wba
					for wba, grids in wba_grids.items()
				}
				for fut in as_completed(futures):
					wba = futures[fut]
					try:
						results.update(fut.result())
					except Exception as e:
						print(f"  ERROR processing {wba}: {e}")
		else:
			for wba, grids in wba_grids.items():
				results.update(self._process_wba(wba, grids, cs3_cache))

		if self.product_b:
			self._write_product_b_chunks_csv(results)
		else:
			results_df = pd.DataFrame(results)
			results_df.index.name = 'date'
			results_df.to_csv(f"{self.output_path}/{self.et_type}_QMAP_results.csv")

		return results

	def write_to_dss(self, results: Dict[str, pd.Series]) -> None:
		"""Write monthly PER-CUM inches to DSS with 1MON interval."""
		if not results:
			return
		if self.product_b:
			self._write_product_b_dss(results)
			return
		if self.et_type == 'CropET':
			dss_out = self.output_path + "/CS3_ET.dss"
		elif self.et_type == 'PanEvap':
			dss_out = self.output_path + "/CS3_PanEvap.dss"
		elif self.et_type == 'RefET':
			dss_out = self.output_path + "/CS3_RefET.dss"
		if self.et_type == 'CropET':
			self._copy_static_crop_et_records(dss_out)
		with HecDss.Open(dss_out, version=6) as dss:
			for wba, s in results.items():
				# Ensure chronological order
				s = s.sort_index()
				# Use month-end timestamps; for DSS, set start as the end-of-month date at 24:00
				start_dt = "31OCT1971 24:00:00"
				tsc = TimeSeriesContainer()
				if self.et_type == 'CropET':
					tsc.pathname = f"/IWFM/{wba}/RATE_INCH//1MON/EVAPOTRANSPIRATION/"
				elif self.et_type == 'PanEvap':
					tsc.pathname = f"/CALSIM/{wba}/PAN-EVAP//1MON/PAN-EVAP/"
				elif self.et_type == 'RefET':
					tsc.pathname = f"/CALSIM/{wba_to_space(wba)}/REF-ET//1MON/REFETO/"
				tsc.startDateTime = start_dt
				tsc.numberValues = len(s)
				tsc.units = "Inch" if self.et_type=='PanEvap' else "IN/MONTH" # inches per month
				tsc.type = "PER-CUM"
				tsc.interval = 1  # monthly interval
				tsc.values = s.values.astype(float)
				dss.put_ts(tsc)


def main():
	parser = argparse.ArgumentParser(
		description=(
			"Compile VIC reference ET by WBA and quantile-map to CS3 monthly ET for WY 1972-2021."
		)
	)
	parser.add_argument(
		"--grid_info_file",
		type=str,
		default=None,
		help="Path to WBA grid info TSV file (default: reference/WBA_Grid_Info.txt)",
	)
	parser.add_argument(
		"--vic_path",
		type=str,
		default=None,
		help="Path to VIC fluxes directory. Default resolved from config.",
	)
	parser.add_argument(
		"--cshydro_dss",
		type=str,
		default=None,
		help="Path to CS3 DSS file (used when --et_type is a single type).",
	)
	parser.add_argument(
		"--cshydro_refet_dss",
		type=str,
		default=None,
		help="Path to CS3 RefETo DSS file (default: reference/CS3_RefETo.dss).",
	)
	parser.add_argument(
		"--cshydro_cropet_dss",
		type=str,
		default=None,
		help="Path to CS3 CropET DSS file (default: reference/CS3_ET.dss).",
	)
	parser.add_argument(
		"--cshydro_panevap_dss",
		type=str,
		default=None,
		help="Path to CS3 PanEvap DSS file (default: reference/CS3_PanEvapGerber.dss).",
	)
	parser.add_argument(
		"--output_path", type=str, default=None, help="Output directory for CSV (and DSS). Defaults to ./output/_2_compile_et/Product_A or Product_B."
	)
	parser.add_argument(
		"--start_date",
		type=str,
		default="1915-01-01",
		help="Start date for VIC daily coverage (YYYY-MM-DD)",
	)
	parser.add_argument(
		"--end_date",
		type=str,
		default="2018-12-31",
		help="End date for VIC daily coverage (YYYY-MM-DD)",
	)
	parser.add_argument(
		"--vic_col_index",
		type=int,
		default=21,
		help="0-based column index of short grass reference ET in VIC flux files (automatically adjusts by -1 for H20_SURFACE with PanEvap)",
	)
	parser.add_argument(
		"--wbas",
		type=str,
		nargs="*",
		default=None,
		help="Optional list of WBAs to process (e.g., WBA_02 WBA_03)",
	)
	parser.add_argument(
		"--write_dss",
		action="store_true",
		help="If set, also write monthly ET_QMAP time series to DSS",
	)
	parser.add_argument(
		"--et_type",
		type=str,
		default='RefET',
		help="ET type to process: 'RefET', 'CropET', 'PanEvap', or 'all' (runs all three).",
	)

	parser.add_argument(
		"--Product_B",
		action="store_true",
		help="If set, read stochastic VIC fluxes and split QM output into ten 100-WY chunks.",
	)
	parser.add_argument(
		"--hist_vic_path",
		type=str,
		default=None,
		help="Path to historical VIC fluxes used as QM training reference for Product B. "
			 "Default resolved from config.",
	)
	parser.add_argument(
		"--n_workers",
		type=int,
		default=1,
		help="Number of parallel workers for WBA processing (default: 1). Works with both Product A and B. Set to e.g. 8-16 to speed up CropET.",
	)
	args = parser.parse_args()

	# Resolve Product-dependent defaults
	_script_dir = Path(__file__).resolve().parent
	_vic_gen = get_module_generated_dir("mod_forcing/vic")
	_cshydro_gen = get_module_generated_dir("mod_hydrology/calsimhydro")

	# Resolve grid_info_file and DSS defaults from reference/ folder
	if args.grid_info_file is None:
		args.grid_info_file = str(_script_dir / "reference" / "WBA_Grid_Info.txt")
	if args.cshydro_refet_dss is None:
		args.cshydro_refet_dss = str(_script_dir / "reference" / "CS3_RefETo.dss")
	if args.cshydro_cropet_dss is None:
		args.cshydro_cropet_dss = str(_script_dir / "reference" / "CS3_ET.dss")
	if args.cshydro_panevap_dss is None:
		args.cshydro_panevap_dss = str(_script_dir / "reference" / "CS3_PanEvapGerber.dss")
	if args.Product_B:
		vic_path = args.vic_path or str(_vic_gen / 'output' / 'fluxes' / 'Product_B' / '1')
		hist_vic_path = args.hist_vic_path or str(_vic_gen / 'output' / 'fluxes' / 'Product_A' / '1')
		output_path = args.output_path or str(_cshydro_gen / 'output' / '_2_compile_et' / 'Product_B')
	else:
		vic_path = args.vic_path or str(_vic_gen / 'output' / 'fluxes' / 'Product_A' / '1')
		hist_vic_path = None
		output_path = args.output_path or str(_cshydro_gen / 'output' / '_2_compile_et' / 'Product_A')

	# Build the list of (et_type, cshydro_dss) pairs to run
	if args.et_type == 'all':
		if not all([args.cshydro_refet_dss, args.cshydro_cropet_dss, args.cshydro_panevap_dss]):
			raise ValueError(
				"--et_type all requires --cshydro_refet_dss, --cshydro_cropet_dss, and --cshydro_panevap_dss."
			)
		et_runs = [
			('RefET',   args.cshydro_refet_dss),
			('CropET',  args.cshydro_cropet_dss),
			('PanEvap', args.cshydro_panevap_dss),
		]
	else:
		dss_map = {
			'RefET':   args.cshydro_refet_dss,
			'CropET':  args.cshydro_cropet_dss,
			'PanEvap': args.cshydro_panevap_dss,
		}
		cshydro_dss = args.cshydro_dss or dss_map.get(args.et_type)
		et_runs = [(args.et_type, cshydro_dss)]

	for et_type, cshydro_dss in et_runs:
		print(f"\n{'='*60}\nRunning et_type={et_type}\n{'='*60}")
		runner = CompileWBAET(
			grid_info_file=args.grid_info_file,
			vic_path=vic_path,
			cshydro_dss=cshydro_dss,
			et_type=et_type,
			output_path=output_path,
			start_date=args.start_date,
			end_date=args.end_date,
			vic_col_index=args.vic_col_index,
			write_dss=args.write_dss,
			product_b=args.Product_B,
			hist_vic_path=hist_vic_path,
			n_workers=args.n_workers,
		)
		results = runner.run(select_wbas=args.wbas)
		if args.write_dss:
			runner.write_to_dss(results)


if __name__ == "__main__":
	# Product A - single type:
	# python _2_compile_et.py --et_type RefET --vic_col_index 7 --write_dss --n_workers 8
	# Product A - all types at once:
	# python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --n_workers 8
	# Product B - all types at once:
	# python _2_compile_et.py --et_type all --vic_col_index 7 --write_dss --Product_B --n_workers 16
	main()

