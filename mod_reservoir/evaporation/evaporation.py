"""
Hargreaves-Samani Evaporation Calculator for CalSim 3.0 Reservoirs

Core implementation of the Hargreaves-Samani equation for calculating
reservoir evaporation rates using temperature data. Supports all 95
CalSim 3.0 reservoirs with reservoir-specific parameters.
"""

import sys
import numpy as np
import pandas as pd
from typing import Dict, Optional
from pathlib import Path
import calendar
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_base_dir

_gen = get_module_generated_dir("mod_reservoir/evaporation")
_PARAMS_FILE = Path(__file__).resolve().parent / "reference" / "reservoir_parameters.json"
_WGEN_PA_DIR  = get_base_dir() / "WGEN" / "Product_A" / "1"


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
            Maximum temperature (°C)
        tmin_c : float
            Minimum temperature (°C)
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

    def process_monthly_timeseries(
        self,
        dates: pd.DatetimeIndex,
        tmax_c: np.ndarray,
        tmin_c: np.ndarray
    ) -> pd.DataFrame:
        """
        Process monthly temperature data to calculate evaporation rates.

        Parameters:
        -----------
        dates : pd.DatetimeIndex
            Monthly dates
        tmax_c : np.ndarray
            Monthly average maximum temperatures (°C)
        tmin_c : np.ndarray
            Monthly average minimum temperatures (°C)

        Returns:
        --------
        pd.DataFrame
            Monthly evaporation rates
        """
        evap_rates = []

        for date, tmax, tmin in zip(dates, tmax_c, tmin_c):
            month = date.month
            days = calendar.monthrange(date.year, month)[1]
            evap = self.calculate_monthly_regression(tmax, tmin, month, days)
            evap_rates.append(evap)

        df = pd.DataFrame({
            'evaporation_in': evap_rates
        }, index=dates)

        return df

    def process_daily_to_monthly(
        self,
        daily_data: pd.DataFrame,
        tmax_col: str = 'tmax_c',
        tmin_col: str = 'tmin_c'
    ) -> pd.DataFrame:
        """
        Convert daily temperature data to monthly evaporation rates.

        Parameters:
        -----------
        daily_data : pd.DataFrame
            Daily temperature data with datetime index
        tmax_col : str
            Column name for maximum temperature
        tmin_col : str
            Column name for minimum temperature

        Returns:
        --------
        pd.DataFrame
            Monthly evaporation rates
        """
        # Resample to monthly averages
        try:
            monthly = daily_data.resample('ME').agg({
                tmax_col: 'mean',
                tmin_col: 'mean'
            })
        except ValueError:
            monthly = daily_data.resample('M').agg({
                tmax_col: 'mean',
                tmin_col: 'mean'
            })

        return self.process_monthly_timeseries(
            monthly.index,
            monthly[tmax_col].values,
            monthly[tmin_col].values
        )


def load_climate_data(
    file_path: str,
    start_date: str = '1915-01-01'
) -> pd.DataFrame:
    """
    Load gridded climate data from Product_A WGEN format files.

    File format (6 space-delimited columns):
    1. Year
    2. Month
    3. Day
    4. Precipitation (mm) - not used
    5. Maximum temperature (°C)
    6. Minimum temperature (°C)

    Parameters:
    -----------
    file_path : str
        Path to climate data file
    start_date : str
        Start date for time series (default: '1915-01-01')

    Returns:
    --------
    pd.DataFrame
        Daily climate data with datetime index
    """
    data = np.loadtxt(file_path)
    
    # Create dates from year, month, day columns
    dates = pd.to_datetime({
        'year': data[:, 0].astype(int),
        'month': data[:, 1].astype(int),
        'day': data[:, 2].astype(int)
    })

    df = pd.DataFrame({
        'precip_mm': data[:, 3],
        'tmax_c': data[:, 4],
        'tmin_c': data[:, 5]
    }, index=dates)

    return df


def find_nearest_weather_file(
    reservoir_code: str,
    weather_dir=None,
    params_file: Optional[str] = None
) -> Optional[str]:
    """
    Find nearest weather data file for a reservoir from Product_A WGEN data.

    Parameters:
    -----------
    reservoir_code : str
        Reservoir code
    weather_dir : str
        Directory containing weather files (Product_A)
    params_file : str, optional
        Path to reservoir_parameters.json

    Returns:
    --------
    str or None
        Path to nearest weather file
    """
    if params_file is None:
        params_file = _PARAMS_FILE
    if weather_dir is None:
        weather_dir = _WGEN_PA_DIR

    with open(params_file, 'r') as f:
        all_params = json.load(f)

    if reservoir_code not in all_params:
        return None

    params = all_params[reservoir_code]
    res_lat = params['latitude']
    res_lon = params['longitude']

    weather_path = Path(weather_dir)
    if not weather_path.exists():
        return None

    min_dist = float('inf')
    nearest_file = None

    # Product_A files are named: meteo_LAT_LON
    for file in weather_path.glob('meteo_*'):
        parts = file.name.split('_')
        if len(parts) != 3:
            continue

        try:
            file_lat = float(parts[1])
            file_lon = float(parts[2])
            dist = np.sqrt((file_lat - res_lat)**2 + (file_lon - res_lon)**2)

            if dist < min_dist:
                min_dist = dist
                nearest_file = str(file)
        except ValueError:
            continue

    return nearest_file


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
