"""
Day-Volume Fraction Analysis and WY Matching Validation
=======================================================
Reverse-engineers the historical bootstrap methodology used to assign
daily VOL-FRACTION patterns to water years 1921-1954 by matching them
to observation-based candidate years 1955-2003 via annual flow index.

Workflow
--------
1. Extract all VOL-FRACTION records (Part C) from CalSim baseline DSS.
2. Extract reference inflow series (14 Part B/C pairs) from the same DSS.
3. Compute annual flow index per water year (sum of all reference inflows).
4. Match each target WY (1921-1954) to the nearest candidate WY (1955-2003).
5. Validate matches by computing RMSE of vol-fraction pattern vectors.

Dependencies
------------
None -- reads directly from CalSim baseline DSS (no upstream scripts required).

Inputs
------
- CalSim baseline DSS: BASE/CalSim3/__calsim_sv_default__.dss
    VOL-FRACTION records and reference inflow series
- Reference inflows:   reference/reference_inflows.csv
    14 Part B / Part C pairs defining the flow index components

Outputs
-------
- GENERATED/mod_other/day_volume_fractions/output/_1_vol_fractions_analysis/
    wy_matches.csv  (target WY, matched candidate WY, flow indices, RMSE)

Usage
-----
    python mod_other/day_volume_fractions/_1_vol_fractions_analysis.py
"""

# %% Imports
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

# %% Paths
_GEN_DIR = get_module_generated_dir("mod_other/day_volume_fractions")
DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
REFERENCE_CSV = Path(__file__).resolve().parent / "reference" / "reference_inflows.csv"
script_name = Path(__file__).stem
DEFAULT_OUTDIR = _GEN_DIR / "output" / script_name
OUT_MATCH_CSV = DEFAULT_OUTDIR / "wy_matches.csv"

# Water year ranges
TARGET_WY = range(1921, 1955)   # 1921-1954: bootstrapped from candidates
CANDIDATE_WY = range(1955, 2004)  # 1955-2003: observation-based pool


# %% Helper: read a single DSS monthly time series (multi-block merge)
def _read_dss_series(dss, plist):
    """Merge multi-block DSS paths into a single Series, sorted by Part D."""
    master = {}
    for p in sorted(plist, key=lambda x: x.strip("/").split("/")[3]):
        ts = dss.read_ts(p, trim_missing=True)
        vals = np.asarray(ts.values, dtype=float)
        vals[vals <= -900] = np.nan
        idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
        s = pd.Series(vals, index=idx)
        master.update(s.to_dict())
    return pd.Series(master).sort_index() if master else pd.Series(dtype="float64")


# %% Extract Vol-Fraction records
def extract_vol_fractions(dss_path: Path) -> pd.DataFrame:
    """Read all monthly series with Part C = 'VOL-FRACTION' from a DSS file."""

    dss_monthly = {}
    print(f"Opening DSS: {Path(dss_path).name}")
    with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        print(f"  {len(all_paths)} monthly paths in catalog")

        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            if len(parts) < 6:
                continue
            part_b = parts[1].upper()
            part_c = parts[2].upper()
            if part_c == "VOL-FRACTION":
                buckets.setdefault(part_b, []).append(p)

        print(f"  {len(buckets)} Part B keys with Part C = VOL-FRACTION")

        for part_b in sorted(buckets):
            series = _read_dss_series(dss, buckets[part_b])
            if series.notna().any():
                series.name = part_b
                dss_monthly[part_b] = series
                print(f"    Extracted: {part_b}  ({series.notna().sum()} months)")

    df = pd.DataFrame(dss_monthly).sort_index()
    print(f"Vol-fraction extraction: {df.shape[1]} series, {df.shape[0]} months")
    return df


# %% Extract reference inflow records
def extract_reference_inflows(dss_path: Path, ref_csv: Path) -> pd.DataFrame:
    """Read reference inflow series (Part B / Part C pairs) from DSS."""

    ref = pd.read_csv(ref_csv)
    wanted = {(r["partb"].strip().upper(), r["partc"].strip().upper()) for _, r in ref.iterrows()}
    print(f"Reference inflows: {len(wanted)} Part B/C pairs requested")

    dss_monthly = {}
    with HecDss.Open(str(dss_path), version=6, catalog_flag=True) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")

        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            if len(parts) < 6:
                continue
            key = (parts[1].upper(), parts[2].upper())
            if key in wanted:
                buckets.setdefault(key, []).append(p)

        print(f"  {len(buckets)} matching Part B/C keys found in DSS")

        for key in sorted(buckets):
            part_b, part_c = key
            series = _read_dss_series(dss, buckets[key])
            if series.notna().any():
                series.name = part_b
                dss_monthly[part_b] = series
                print(f"    Extracted: {part_b}/{part_c}  ({series.notna().sum()} months)")

    df = pd.DataFrame(dss_monthly).sort_index()
    print(f"Inflow extraction: {df.shape[1]} series, {df.shape[0]} months")
    return df


# %% Compute annual flow index by water year
def compute_annual_index(df_inflows: pd.DataFrame, components: list) -> pd.Series:
    """Sum listed components over each water year (Oct-Sep)."""
    df = df_inflows.copy()
    df.index = pd.to_datetime(df.index)
    df["WY"] = df.index.year + (df.index.month >= 10).astype(int)

    # Keep only requested columns that exist
    cols = [c for c in components if c in df.columns]
    if not cols:
        raise ValueError(f"None of {components} found in inflow columns: {list(df.columns)}")

    annual = df.groupby("WY")[cols].sum().sum(axis=1)
    annual.name = "flow_index"
    return annual


# %% Match target WYs to nearest candidate WY by flow index
def match_water_years(annual_index: pd.Series, target_wys, candidate_wys) -> pd.DataFrame:
    """For each target WY, find the candidate WY with nearest annual flow index."""

    target_idx = annual_index.reindex(target_wys).dropna()
    candidate_idx = annual_index.reindex(candidate_wys).dropna()

    if target_idx.empty or candidate_idx.empty:
        raise ValueError("No valid flow index values for target or candidate WYs")

    records = []
    for wy in target_idx.index:
        diffs = (candidate_idx - target_idx[wy]).abs()
        best_wy = diffs.idxmin()
        records.append({
            "WY_target": wy,
            "WY_matched_by_flow_index": best_wy,
            "annual_flow_target": target_idx[wy],
            "annual_flow_matched": candidate_idx[best_wy],
        })

    df_match = pd.DataFrame(records)
    print(f"Matched {len(df_match)} target WYs to candidates")
    return df_match


# %% Validate matches via RMSE of vol-fraction patterns
def compute_rmse_matrix(df_vf: pd.DataFrame, target_wys, candidate_wys) -> pd.DataFrame:
    """Compute RMSE between each target WY and each candidate WY vol-fraction pattern.

    Each WY pattern is the 12-month vector of vol-fraction values (Oct-Sep).
    """
    df = df_vf.copy()
    df.index = pd.to_datetime(df.index)
    df["WY"] = df.index.year + (df.index.month >= 10).astype(int)

    # Build WY x (month*location) matrix -- flatten each WY into a single vector
    grouped = df.drop(columns="WY").groupby(df["WY"])

    def _flatten(grp):
        return grp.values.flatten()

    wy_vectors = {}
    for wy, grp in grouped:
        vec = grp.sort_index().values.flatten()
        if not np.all(np.isnan(vec)):
            wy_vectors[wy] = vec

    # Compute RMSE matrix
    t_wys = sorted(set(target_wys) & set(wy_vectors.keys()))
    c_wys = sorted(set(candidate_wys) & set(wy_vectors.keys()))

    rmse_data = {}
    for t_wy in t_wys:
        row = {}
        for c_wy in c_wys:
            v_t = wy_vectors[t_wy]
            v_c = wy_vectors[c_wy]
            n = min(len(v_t), len(v_c))
            diff = v_t[:n] - v_c[:n]
            valid = ~np.isnan(diff)
            if valid.any():
                row[c_wy] = np.sqrt(np.nanmean(diff[valid] ** 2))
            else:
                row[c_wy] = np.nan
        rmse_data[t_wy] = row

    df_rmse = pd.DataFrame(rmse_data).T
    df_rmse.index.name = "target_wy"
    df_rmse.columns.name = "candidate_wy"
    return df_rmse


def validate_matches(df_match: pd.DataFrame, df_rmse: pd.DataFrame) -> pd.DataFrame:
    """Add RMSE and best-RMSE-candidate columns to match table for validation."""

    df = df_match.copy()
    rmse_vals = []
    best_rmse_wys = []

    for _, row in df.iterrows():
        t_wy = row["WY_target"]
        m_wy = row["WY_matched_by_flow_index"]

        if t_wy in df_rmse.index and m_wy in df_rmse.columns:
            rmse_vals.append(df_rmse.loc[t_wy, m_wy])
        else:
            rmse_vals.append(np.nan)

        if t_wy in df_rmse.index:
            best_rmse_wys.append(df_rmse.loc[t_wy].idxmin())
        else:
            best_rmse_wys.append(np.nan)

    df["RMSE_of_flow_index_match"] = rmse_vals
    df["WY_best_RMSE_match"] = best_rmse_wys
    df["flow_index_confirms_RMSE"] = df["WY_matched_by_flow_index"] == df["WY_best_RMSE_match"]

    n_confirm = df["flow_index_confirms_RMSE"].sum()
    print(f"  {n_confirm}/{len(df)} flow-index match == RMSE-best match")
    return df


# %% Main
def main():
    DEFAULT_OUTDIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract vol-fraction records
    print("=" * 60)
    print("Step 1: Extract VOL-FRACTION from DSS")
    print("=" * 60)
    df_vf = extract_vol_fractions(DEFAULT_DSS)

    # Step 2: Extract reference inflow records
    print("\n" + "=" * 60)
    print("Step 2: Extract reference inflows from DSS")
    print("=" * 60)
    df_inflows = extract_reference_inflows(DEFAULT_DSS, REFERENCE_CSV)

    # Step 3: Compute annual flow index from all reference inflows and match WYs
    print("\n" + "=" * 60)
    print("Step 3: Compute annual flow index and match WYs")
    print("=" * 60)
    components = list(df_inflows.columns)
    print(f"Using all {len(components)} reference inflows: {', '.join(components)}")

    annual_idx = compute_annual_index(df_inflows, components)
    df_match = match_water_years(annual_idx, TARGET_WY, CANDIDATE_WY)

    # Step 4: Validate with RMSE of vol-fraction patterns
    print("\n  Computing RMSE validation matrix...")
    df_rmse = compute_rmse_matrix(df_vf, TARGET_WY, CANDIDATE_WY)
    df_match = validate_matches(df_match, df_rmse)

    df_match.to_csv(OUT_MATCH_CSV, index=False)
    print(f"  Saved: {OUT_MATCH_CSV.name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
