# %%
# This script calculates R² between ONE CalSim DSS inflow (part B = C_CBD001HIST)
# and ALL VIC inflows found in vic_path over their overlapping periods.

import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import get_base_dir, get_module_generated_dir


# ===================== USER INPUTS =====================
DSS_PART_B = "C_SFY007_SV"

dss_path = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"

vic_path = str(get_module_generated_dir("mod_forcing/vic") / "output" / "routed" / "Historical")
# ======================================================


# %% --- Read DSS monthly inflow for ONE part_b ---
full_index = pd.date_range("1915-01-31", "2021-12-31", freq="ME")
dss_series = None

with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:

    all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")

    # keep only paths with desired part B
    wanted_paths = [
        p for p in all_paths
        if p.strip("/").split("/")[1].upper() == DSS_PART_B
    ]

    if not wanted_paths:
        raise ValueError(f"No DSS paths found for part B = {DSS_PART_B}")

    master = pd.Series(index=full_index, dtype="float64")

    for p in sorted(wanted_paths, key=lambda x: x.strip("/").split("/")[3]):
        ts = dss.read_ts(p, trim_missing=True)

        vals = np.asarray(ts.values, dtype=float)
        vals[vals <= -900] = np.nan  # DSS missing codes → NaN

        idx = (
            pd.to_datetime(ts.pytimes)
              .to_period("M") - 1
        ).to_timestamp("M")

        master.update(pd.Series(vals, index=idx))

    if not master.notna().any():
        raise ValueError("DSS inflow series contains no valid data.")

    dss_series = master
    dss_series.name = DSS_PART_B

print(f"DSS inflow loaded: {DSS_PART_B}")
print(dss_series.dropna().head())


# %% --- Read VIC inflows ---
vic_series = {}

for file in os.listdir(vic_path):
    if not file.endswith("_qmo.csv"):
        continue

    vic_name = file[len("CS3_") : -len("_qmo.csv")]
    fpath = os.path.join(vic_path, file)

    df_v = pd.read_csv(fpath, header=None)
    df_v.iloc[:, 0] = pd.to_datetime(df_v.iloc[:, 0], errors="coerce")

    ser = pd.Series(
        df_v.iloc[:, 1].values,
        index=df_v.iloc[:, 0].values,
        name=vic_name
    ).sort_index()

    vic_series[vic_name] = ser

vic_monthly_df = pd.DataFrame(vic_series).sort_index()

print(f"Loaded {len(vic_monthly_df.columns)} VIC inflow series")


# %% --- Correlation: DSS vs ALL VIC ---
results = []

for vic_name in vic_monthly_df.columns:
    r = dss_series.corr(vic_monthly_df[vic_name])
    r2 = float(r**2) if pd.notnull(r) else np.nan

    results.append([
        DSS_PART_B,
        vic_name,
        r2
    ])

results_df = pd.DataFrame(
    results,
    columns=["DSS Inflow", "VIC Inflow", "R²"]
)

# %% --- Save output ---
out_path = "output/_1_calc_correlations/r2_calsim_vs_vic.csv"
os.makedirs(os.path.dirname(out_path), exist_ok=True)

results_df.to_csv(out_path, index=False)

print(f"Correlation results written to: {out_path}")
