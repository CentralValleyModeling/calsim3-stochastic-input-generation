"""
Append Historical Wind to WGEN Met Files (VIC Forcing)
======================================================

WGEN outputs precip and temperature but not wind. This script appends daily
wind (4th column of the ``Historical_Climate_LTO/1_Historical`` wind files), matched
by date, to the WGEN climate files and writes complete VIC forcing files
(``meteo_LAT_LON``: pr, tmax, tmin, wind) to the VIC input directory.

Two historical climate sources are supported, selected with ``--source``:

- ``Product_A`` (default) -- the per-scenario WGEN historical-length ensemble in
  ``WGEN/Product_A/{scenario}``. WGEN files are named ``meteo_LAT_LON``, so each
  wind cell's climate file is found by the ``data`` -> ``meteo`` rename.
  Output: ``input/Product_A/{scenario}/meteo_*``.

- ``Historical_Unsplit`` -- a single continuous 1915-2018 WGEN sequence in
  ``WGEN/Historical_Unsplit``. Those climate files share the ``data_LAT_LON``
  naming of the wind files, so a cell's climate and wind are matched by identical
  name (no rename). Output: ``input/Historical_Unsplit/meteo_*``.

Wind spans 1915-2021 and covers both climate records (each 1915-2018), so every
climate date has a matching wind value.

Usage
-----
    python mod_forcing/vic/_1_append_wind_wgen_hist.py
    python mod_forcing/vic/_1_append_wind_wgen_hist.py --source Product_A --scenario 1
    python mod_forcing/vic/_1_append_wind_wgen_hist.py --source Historical_Unsplit
"""
import argparse
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


def add_wind(wind_file_name,
             climate_file_name,
             wind_dir,
             climate_dir,
             wind_date_start='1/1/1915',
             wind_date_end='12/31/2021'):
    """Append wind (4th column of the wind file) to a WGEN climate file, matched
    by date.

    Parameters
    ----------
    wind_file_name : str
        ``data_LAT_LON`` wind file (wind in column index 3).
    climate_file_name : str
        WGEN climate file for the same cell (columns: year, month, day, pr,
        tmax, tmin). Named ``meteo_*`` for Product_A, ``data_*`` for
        Historical_Unsplit -- resolved by the caller.
    wind_dir : str
        Directory of the Historical_Climate_LTO wind files.
    climate_dir : str
        Directory of the WGEN climate files.
    wind_date_start, wind_date_end : str
        Date span of the wind record (daily), by default 1915-2021.

    Returns
    -------
    pd.DataFrame or None
        Columns [pr, tmax, tmin, wind] in VIC forcing order, or ``None`` if the
        matching climate file is missing.
    """
    # --- wind: 4th column (index 3), dated daily over the wind record ---
    data_wind = pd.read_csv(os.path.join(wind_dir, wind_file_name),
                            usecols=[3], sep=r'\s+', engine='python', header=None)
    data_wind.columns = ['wind']
    data_wind.insert(0, 'date', pd.date_range(wind_date_start, wind_date_end, freq='D'))

    # --- climate: year, month, day, pr, tmax, tmin ---
    climate_path = os.path.join(climate_dir, climate_file_name)
    try:
        data_clim = pd.read_csv(climate_path, sep=r'\s+', engine='python', header=None,
                                names=['year', 'month', 'day', 'pr', 'tmax', 'tmin'])
    except FileNotFoundError:
        return None
    data_clim['date'] = pd.to_datetime(data_clim[['year', 'month', 'day']], yearfirst=True)

    # --- merge wind onto climate by date, keep VIC column order ---
    data_combined = pd.merge(data_clim, data_wind, on='date', how='left')
    data_combined.drop(columns=['date', 'year', 'month', 'day'], inplace=True)
    return data_combined


def main():
    parser = argparse.ArgumentParser(
        description="Append historical wind to WGEN met files for VIC forcing."
    )
    parser.add_argument('--source', choices=['Product_A', 'Historical_Unsplit'],
                        default='Product_A',
                        help="Climate source: Product_A (per-scenario WGEN ensemble, "
                             "default) or Historical_Unsplit (continuous 1915-2018 WGEN).")
    parser.add_argument('--scenario', default='1',
                        help="Product_A scenario subdirectory (default '1'); "
                             "ignored for Historical_Unsplit.")
    args = parser.parse_args()

    # ---Set Directories---
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_forcing/vic")
    # -Wind Location- (same for both sources; the limiting set)
    wind_dir = str(_base / 'Historical_Climate_LTO' / '1_Historical')

    if args.source == 'Product_A':
        # WGEN files are named meteo_*; match each wind cell by data -> meteo rename.
        climate_dir = str(_base / 'WGEN' / 'Product_A' / args.scenario)
        out_dir_gen = str(_gen / 'input' / 'Product_A' / args.scenario)
        climate_named_meteo = True
    else:  # Historical_Unsplit
        # Climate files share the wind files' data_* naming; match by identical name.
        climate_dir = str(_base / 'WGEN' / 'Historical_Unsplit')
        out_dir_gen = str(_gen / 'input' / 'Historical_Unsplit')
        climate_named_meteo = False

    # Wind is the limiting set; iterate wind files and require a matching climate
    # file (skip cells that have wind but no WGEN climate).
    wind_files = sorted(f for f in os.listdir(wind_dir) if f.startswith('data_'))
    print(f'Source: {args.source} -> {out_dir_gen}')
    print(f'{len(wind_files)} wind files in {wind_dir}')

    if not os.path.exists(out_dir_gen):
        os.makedirs(out_dir_gen)
        print(f'Created output directory: {out_dir_gen}')

    n_ok = 0
    n_skip = 0
    n_nan = 0
    for i, wind_file_name in enumerate(wind_files):
        climate_file_name = (wind_file_name.replace('data', 'meteo')
                             if climate_named_meteo else wind_file_name)
        processed_data = add_wind(wind_file_name, climate_file_name,
                                  wind_dir=wind_dir, climate_dir=climate_dir)
        if processed_data is None:
            n_skip += 1
            continue

        if processed_data['wind'].isna().any():
            # Should not happen (wind 1915-2021 covers climate 1915-2018), but
            # guard against silently writing NaN wind into VIC forcing.
            n_nan += 1
            print(f'WARNING: NaN wind after merge for {wind_file_name}')

        out_file_name = wind_file_name.replace('data', 'meteo')

        # Prepend a space to the first column and use tab + one space as the
        # separator, matching the existing meteo_* VIC forcing format.
        df_out = processed_data.copy()
        first_col = df_out.columns[0]
        df_out[first_col] = ' ' + df_out[first_col].astype(str)
        np.savetxt(
            os.path.join(out_dir_gen, out_file_name),
            df_out.astype(str).to_numpy(),
            fmt='%s',
            delimiter='\t ',
            newline='\n',
        )
        n_ok += 1
        if (i + 1) % 500 == 0:
            print(f'{i + 1}/{len(wind_files)} processed ({n_ok} written, {n_skip} skipped)')

    print(f'Done: {n_ok} meteo files written, {n_skip} skipped (no climate), '
          f'{n_nan} with NaN wind -> {out_dir_gen}')


if __name__ == "__main__":
    main()
