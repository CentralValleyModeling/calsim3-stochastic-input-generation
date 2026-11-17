"""
Hargreaves-Samani Evaporation Calculator for CalSim 3.0 Reservoirs
==================================================================
Core implementation of the Hargreaves-Samani equation for calculating
reservoir evaporation rates from temperature data. Supports all 95
CalSim 3.0 reservoirs with reservoir-specific parameters.

Inputs
------
- The daily weather of a set (utils.wgen), from the cell nearest each reservoir
- reference/reservoir_parameters.json

Outputs
-------
- monthly evaporation series returned to the caller (no files written here)

Dependencies
------------
- utils/wgen.py  (weather files)
"""

import json
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.wgen import nearest_cell, read_met

_PARAMS_FILE = Path(__file__).resolve().parent / "reference" / "reservoir_parameters.json"


class EvaporationCalculator:
    """
    Calculate reservoir evaporation using the Hargreaves-Samani equation.

    Uses reservoir-specific parameters including location, extraterrestrial
    radiation values, and calibration factors.
    """

    # Elevation adjustment lookup table (shared by all reservoirs)
    ELEVATION_ADJUSTMENT = {
        -10: (9.753127783667423e-06, 0.4018592144257773),
        0: (9.81843793393097e-06, 0.4018592144257773),
        5: (9.81843793393097e-06, 0.4788235188020018),
        10: (9.44834455471039e-06, 0.5527877112049688),
        15: (8.838768617819503e-06, 0.6215018942692481),
        20: (7.924415139357678e-06, 0.6834302604091812),
        25: (7.0100540777144056e-06, 0.7366443781538309),
        30: (6.00861723924223e-06, 0.7825727349607635),
        35: (5.050723028672931e-06, 0.8207153774836067),
        40: (4.201677804679286e-06, 0.8521794859009434),
        45: (3.5267917175248557e-06, 0.8779293645889981),
        50: (2.9172214680200613e-06, 0.8989292339497397)
    }

    def __init__(self, reservoir_code: str, params_file: Optional[str] = None):
        """
        Initialize calculator for a specific reservoir.

        Parameters:
        -----------
        reservoir_code : str
            Reservoir code (e.g., 'FOLSM', 'SHSTA')
        params_file : str, optional
            Path to reservoir_parameters.json
        """
        self.reservoir_code = reservoir_code.upper()

        # Load parameters
        if params_file is None:
            params_file = _PARAMS_FILE

        with open(params_file, 'r') as f:
            all_params = json.load(f)

        if self.reservoir_code not in all_params:
            raise ValueError(f"Reservoir '{self.reservoir_code}' not found in database")

        self.params = all_params[self.reservoir_code]
        self.location = {
            'latitude': self.params['latitude'],
            'longitude': self.params['longitude'],
            'elevation_ft': self.params['elevation_ft']
        }

        # Convert string keys to integers
        self.ra_monthly = {int(k): v for k, v in self.params['ra_monthly'].items()}
        self.monthly_cal = {int(k): v for k, v in self.params['monthly_calibration'].items()}
        self.adjustment_factor = self.params.get('adjustment_factor', 1.0)
        self.annual_cal = self.params['annual_calibration']

    def _get_elevation_factor(self, temp_avg_c: float) -> tuple:
        """
        Get elevation adjustment factors using VLOOKUP behavior.

        Mimics Excel's VLOOKUP with approximate match (range_lookup=True),
        which finds the largest temperature value that is <= temp_avg_c.
        This matches the original Excel methodology without interpolation.
        """
        temps = np.array(list(self.ELEVATION_ADJUSTMENT.keys()))

        # Find the largest temperature that is <= temp_avg_c
        # This matches Excel's VLOOKUP approximate match behavior
        if temp_avg_c < temps[0]:
            # Below minimum, use first row
            return self.ELEVATION_ADJUSTMENT[temps[0]]
        elif temp_avg_c >= temps[-1]:
            # Above maximum, use last row
            return self.ELEVATION_ADJUSTMENT[temps[-1]]
        else:
            # Find largest temp <= temp_avg_c
            # searchsorted returns index where temp_avg_c would be inserted
            # So we want index - 1 to get largest value <= temp_avg_c
            idx = np.searchsorted(temps, temp_avg_c, side='right') - 1
            lookup_temp = temps[idx]
            return self.ELEVATION_ADJUSTMENT[lookup_temp]

    def _calculate_elevation_adjustment(self, temp_avg_c: float) -> float:
        """Calculate elevation adjustment factor."""
        slope, intercept = self._get_elevation_factor(temp_avg_c)
        numerator = slope * self.location['elevation_ft'] + intercept
        return numerator / intercept

    def calculate_monthly_regression(
        self,
        tmax_c: float,
        tmin_c: float,
        month: int,
        days_in_month: int
    ) -> float:
        """
        Calculate evaporation with monthly regression calibration (recommended method).

        Parameters:
        -----------
        tmax_c : float
            Maximum temperature (degC)
        tmin_c : float
            Minimum temperature (degC)
        month : int
            Month number (1-12)
        days_in_month : int
            Number of days in month

        Returns:
        --------
        float
            Evaporation rate (inches/month)
        """
        tavg_c = (tmax_c + tmin_c) / 2.0
        ra = self.ra_monthly[month]
        elev_factor = self._calculate_elevation_adjustment(tavg_c)
        temp_diff = max(tmax_c - tmin_c, 0)

        # Hargreaves-Samani equation
        uncalibrated = (elev_factor * 0.0023 * ra *
                       np.sqrt(temp_diff) * (tavg_c + 17.8) *
                       days_in_month / 25.4)

        # Apply monthly regression calibration
        slope = self.monthly_cal[month]['slope']
        intercept = self.monthly_cal[month]['intercept']

        return max(0.0, self.adjustment_factor * (uncalibrated * slope + intercept))

    def process_daily_to_monthly(self, daily: pd.DataFrame) -> pd.DataFrame:
        """
        Monthly evaporation (inches/month) from daily temperatures.

        Parameters:
        -----------
        daily : pd.DataFrame
            Daily rows with Year, Month, tmax and tmin (degC), as utils.wgen.read_met returns
            them; Product B's are stamp months

        Returns:
        --------
        pd.DataFrame
            Year, Month and evaporation_in per month of the rows, in their order; each month
            takes the number of days it has in the rows
        """
        g = daily.groupby(['Year', 'Month'], sort=False)
        monthly = g[['tmax', 'tmin']].mean()
        evap = [self.calculate_monthly_regression(tmax, tmin, month, days)
                for (_, month), tmax, tmin, days in zip(monthly.index, monthly['tmax'],
                                                        monthly['tmin'], g.size())]
        return pd.DataFrame({'Year': monthly.index.get_level_values(0),
                             'Month': monthly.index.get_level_values(1),
                             'evaporation_in': evap})


def reservoir_weather(
    reservoir_code: str,
    product: str,
    params_file: Optional[str] = None
) -> pd.DataFrame:
    """
    Daily weather of the cell of ``product`` nearest a reservoir.

    Parameters:
    -----------
    reservoir_code : str
        Reservoir code
    product : str
        Weather set (a key of utils.paths.WEATHER_SETS)
    params_file : str, optional
        Path to reservoir_parameters.json

    Returns:
    --------
    pd.DataFrame
        Year, Month, Day, precip (mm), tmax and tmin (degC) (utils.wgen.read_met)
    """
    params = get_reservoir_info(reservoir_code, params_file)
    _, _, path, _ = nearest_cell(product, params['latitude'], params['longitude'])
    return read_met(product, path)


def get_all_reservoir_codes(params_file: Optional[str] = None) -> list:
    """
    Get list of all reservoir codes in database.

    Parameters:
    -----------
    params_file : str, optional
        Path to reservoir_parameters.json

    Returns:
    --------
    list
        Sorted list of reservoir codes
    """
    if params_file is None:
        params_file = _PARAMS_FILE

    with open(params_file, 'r') as f:
        all_params = json.load(f)

    return sorted(all_params.keys())


def get_reservoir_info(reservoir_code: str, params_file: Optional[str] = None) -> Dict:
    """
    Get all parameters for a reservoir.

    Parameters:
    -----------
    reservoir_code : str
        Reservoir code
    params_file : str, optional
        Path to reservoir_parameters.json

    Returns:
    --------
    Dict
        Complete parameter dictionary
    """
    if params_file is None:
        params_file = _PARAMS_FILE

    with open(params_file, 'r') as f:
        all_params = json.load(f)

    if reservoir_code not in all_params:
        raise ValueError(f"Reservoir '{reservoir_code}' not found")

    return all_params[reservoir_code]
