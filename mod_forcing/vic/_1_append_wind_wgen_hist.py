"""
Append Historical Wind to WGEN Product A Met Files (VIC Forcing)
================================================================

Reads daily wind (4th column) from each Historical_Climate data file, merges
it onto the matching WGEN meteo file by date, and writes the wind-appended
meteo files to the VIC input directory.

Usage
-----
    cd mod_forcing/vic
    python _1_append_wind_wgen_hist.py
"""
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir


# add_wind.py
# This script adds wind data to the WGEN data files for VIC simulations.
def add_wind(hist_file_name,
             hist_dir,
             wgen_dir,
             hist_date_start='1/1/1915',
             hist_date_end='12/31/2021'
             ):
    """    Adds wind data to WGEN climate data files for VIC simulations.
    Parameters
    ----------
    hist_file_name : str
        Name of the historical file containing wind data.
    hist_dir : str
        Directory where the historical wind data files are located.
    wgen_dir : str
        Directory where the WGEN data files are located.
    hist_date_start : str, optional
        Start date for the historical data, by default '1/1/1915'.
    hist_date_end : str, optional
        End date for the historical data, by default '12/31/2021'.

    Returns
    -------
    pd.DataFrame
        Processed DataFrame with wind data added.
    """
    # try:
    #---Open wind---
    data_wind = pd.read_csv(os.path.join(hist_dir, hist_file_name), usecols=[3], sep='\\s+', engine='python', header=None)
    data_wind.columns = ['wind']  # Set column name for wind
    data_wind.insert(0, 'date', pd.date_range(hist_date_start, hist_date_end, freq='D')) # Add date column

    #---Read wgen Data---
    f_name = hist_file_name.replace('data', 'meteo')
    try:
        data_wgen = pd.read_csv(
            os.path.join(wgen_dir, f_name),
            sep='\\s+',
            engine='python',
            header=None,
            names=['year', 'month', 'day', 'pr', 'tmax', 'tmin']
        )
    except FileNotFoundError:
        print(f'File not found: {os.path.join(wgen_dir, f_name)}')
        return None
    # Create a datetime column from year, month, day
    data_wgen['date'] = pd.to_datetime(data_wgen[['year', 'month', 'day']], yearfirst=True)

    #---Combine WGEN and Wind Data---
    data_combined = pd.merge(data_wgen, data_wind, on='date', how='left')
    data_combined.drop(columns=['date','year','month','day'], inplace=True)  # Drop unnecessary columns

    return data_combined


def main():
    #---Set Directories---
    _base = get_base_dir()
    _gen = get_module_generated_dir("mod_forcing/vic")
    #-Scenario-
    wgen_dir = str(_base / 'WGEN' / 'Product_A' / '1')
    #-Wind Location-
    hist_dir = str(_base / 'Historical_Climate' / '1_Historical')
    #-VIC Input Directory-
    out_dir_gen = str(_gen / 'input' / 'Product_A' / '1')

    #---Get File List - LTO Wind = Limiting Factor---
    hist_files = os.listdir(hist_dir)
    print(len(hist_files))
    print(hist_files[:5])

    #---Scenarios---
    wgen_files = os.listdir(wgen_dir)
    print(wgen_files[:5])

    # check if output directory exists, if not create it
    if not os.path.exists(out_dir_gen):
        os.makedirs(out_dir_gen)
        print(f'Created output directory: {out_dir_gen}')

    # Process each historical file and add wind data
    for j in range(len(hist_files)):
        hist_file_name = hist_files[j]
        # print(f'Processing {j+1}/{len(hist_files)}: {hist_file_name}')

        # Call the function to add wind data
        processed_data = add_wind(hist_file_name, hist_dir=hist_dir, wgen_dir=wgen_dir)
        if processed_data is None:
            print(f'Skipping {hist_file_name} due to error.')
            continue  # Skip to the next file if there was an error
        else:
            print(f'Successfully processed {hist_file_name}')
            # Save the processed data to a new file
            out_file_name = hist_file_name.replace('data', 'meteo')

            # Prepend a space to the first column and use tab + one space as the separator
            df_out = processed_data.copy()
            first_col = df_out.columns[0]
            df_out[first_col] = ' ' + df_out[first_col].astype(str)

            # Use numpy.savetxt to allow a multi-character delimiter (tab + space)
            out_path = os.path.join(out_dir_gen, out_file_name)
            np.savetxt(
                out_path,
                df_out.astype(str).to_numpy(),
                fmt='%s',
                delimiter='\t ',
                newline='\n'
            )


if __name__ == "__main__":
    main()
