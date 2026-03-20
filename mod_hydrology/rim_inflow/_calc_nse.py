import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

# Load the validation time series
df = pd.read_csv(_gen / "output" / "_2_qmap_historical_validation" / "calsim_qmap_validation_TS.csv")

# Get unique CalSim locations
locations = df['CalSim'].unique()
print(f"Total locations: {len(locations)}")

# NSE columns
nse_cols = ['vic_NSE_TestPeriod', 'qmap_NSE_TestPeriod_preAdj', 'qmap_NSE_TestPeriod_postAdj']

# For each location, NSE is constant across all time steps, so get one value per location
for col in nse_cols:
    if col in df.columns:
        location_nse = df.groupby('CalSim')[col].first()
        avg_nse = location_nse.mean()
        print(f"\n{col}:")
        print(f"  Average: {avg_nse:.4f}")
        print(f"  Median: {location_nse.median():.4f}")
        print(f"  Min: {location_nse.min():.4f}")
        print(f"  Max: {location_nse.max():.4f}")
        print(f"  Count (non-NaN): {location_nse.notna().sum()}")
