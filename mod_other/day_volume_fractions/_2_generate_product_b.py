"""
Generate Product B Day-Volume Fractions
=======================================
For each Product B chunk (10 x 100 water years), match every synthetic
water year to the nearest historical water year by annual flow index,
then borrow the matched year's daily VOL-FRACTION pattern.

February leap-year handling: if source and target February have different
day counts (28 vs 29), the daily fractions are resampled via cumulative-
volume interpolation so the monthly sum stays 1.

Dependencies
------------
Upstream scripts that must run first:
  - mod_hydrology/rim_inflow/_3_qmap_productB.py  (Product B qmap inflows)

Inputs
------
- CalSim baseline DSS:  BASE/CalSim3/__calsim_sv_default__.dss
    VOL-FRACTION records (Part C) and reference inflow series
- Reference inflows:    reference/reference_inflows.csv
    Part B / Part C pairs defining the annual flow index components
- Product B rim inflows: GENERATED/mod_hydrology/rim_inflow/output/_3_qmap_product_b/
    <PartB>_qmo_n01.csv ... n10.csv (qmap_postAdj or qmap_preAdj)

Outputs
-------
- GENERATED/mod_other/day_volume_fractions/output/_product_b_final/
    vol_fraction_productB_n01.csv ... n10.csv
        Columns: Part B, Part C, Year, Month, Value
- GENERATED/mod_other/day_volume_fractions/output/_2_generate_product_b/
    wy_matches_n01.csv ... n10.csv
        Columns: WY, matched_historical_WY, annual_flow_synthetic, annual_flow_historical

Usage
-----
    python mod_other/day_volume_fractions/_2_generate_product_b.py
"""

# %% Imports
import calendar
import os
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

# %% Paths
_GEN_DIR = get_module_generated_dir("mod_other/day_volume_fractions")
DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
REFERENCE_CSV = Path(__file__).resolve().parent / "reference" / "reference_inflows.csv"
RIM_INFLOW_DIR = get_module_generated_dir("mod_hydrology/rim_inflow") / "output" / "_3_qmap_product_b"

script_name = Path(__file__).stem
DEFAULT_OUTDIR = _GEN_DIR / "output" / script_name
PRODUCT_B_FINAL = _GEN_DIR / "output" /"_product_b_final"

N_CHUNKS = 10
MAX_WORKERS = max(1, (os.cpu_count() or 4) - 1)


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


# %% Extract all Vol-Fraction records from historical DSS
def extract_vol_fractions(dss_path: Path) -> pd.DataFrame:
    """Read all monthly series with Part C = 'VOL-FRACTION' from DSS."""

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

    df = pd.DataFrame(dss_monthly).sort_index()
    print(f"  Extracted {df.shape[1]} vol-fraction series, {df.shape[0]} months")
    return df


# %% Build historical vol-fraction lookup keyed by WY
def build_vf_by_wy(df_vf: pd.DataFrame) -> dict:
    """Return {wy: DataFrame of 12 monthly rows} for all available WYs."""
    df = df_vf.copy()
    df.index = pd.to_datetime(df.index)
    df["WY"] = df.index.year + (df.index.month >= 10).astype(int)
    df["Month"] = df.index.month

    lookup = {}
    for wy, grp in df.groupby("WY"):
        if len(grp) == 12:
            lookup[wy] = grp.sort_values("Month").drop(columns="WY").reset_index(drop=True)
    return lookup


# %% Build historical annual flow index from DSS inflows
def build_historical_annual_index(dss_path: Path, ref_csv: Path) -> pd.Series:
    """Extract reference inflows from DSS and compute annual flow sum per WY."""

    ref = pd.read_csv(ref_csv)
    wanted = {(r["partb"].strip().upper(), r["partc"].strip().upper()) for _, r in ref.iterrows()}

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

        found_keys = set(buckets.keys())
        missing = wanted - found_keys
        if missing:
            print(f"  WARNING: {len(missing)} reference inflows NOT found in DSS:")
            for pb, pc in sorted(missing):
                print(f"    - {pb}/{pc}")
        print(f"  Found {len(found_keys)}/{len(wanted)} reference inflows in DSS")

        for key in sorted(buckets):
            part_b, _ = key
            series = _read_dss_series(dss, buckets[key])
            if series.notna().any():
                dss_monthly[part_b] = series

    df = pd.DataFrame(dss_monthly).sort_index()
    df.index = pd.to_datetime(df.index)
    df["WY"] = df.index.year + (df.index.month >= 10).astype(int)

    annual = df.groupby("WY")[list(dss_monthly.keys())].sum().sum(axis=1)
    annual.name = "flow_index"
    print(f"  Historical annual index: {len(annual)} water years")
    return annual


# %% Load Product B inflows for one chunk from rim_inflow CSVs
def load_chunk_inflows(rim_dir: Path, chunk: int, ref_csv: Path) -> pd.DataFrame:
    """Read qmap_postAdj from rim inflow Product B CSVs for one chunk.

    Returns DataFrame with columns = Part B names, indexed by (Year, Month).
    """
    ref = pd.read_csv(ref_csv)
    partb_list = [r["partb"].strip().upper() for _, r in ref.iterrows()]

    chunk_tag = f"n{chunk:02d}"
    series_dict = {}
    missing = []

    for partb in partb_list:
        # Filename pattern: <CalSim>_qmo_n01.csv
        csv_path = rim_dir / f"{partb}_qmo_{chunk_tag}.csv"
        if not csv_path.exists():
            missing.append(partb)
            continue

        df = pd.read_csv(csv_path)
        # Use qmap_postAdj (mass-balance adjusted), fall back to qmap_preAdj
        val_col = "qmap_postAdj" if "qmap_postAdj" in df.columns else "qmap_preAdj"
        sub = df[["Year", "Month", val_col]].copy()
        sub = sub.rename(columns={val_col: partb})
        sub = sub.set_index(["Year", "Month"])
        series_dict[partb] = sub[partb]

    if not series_dict:
        return pd.DataFrame()

    result = pd.DataFrame(series_dict)
    if missing:
        print(f"    WARNING: {len(missing)}/{len(partb_list)} inflows NOT found for {chunk_tag}:")
        for m in missing:
            print(f"      - {m}_qmo_{chunk_tag}.csv")
    print(f"    Chunk {chunk_tag}: loaded {len(series_dict)}/{len(partb_list)} inflows, {len(result)} months")
    return result


# %% Compute annual flow index from chunk inflows
def compute_chunk_annual_index(df_chunk: pd.DataFrame) -> pd.Series:
    """Sum all inflow columns by water year for a Product B chunk."""
    df = df_chunk.copy()
    df = df.reset_index()
    df["WY"] = np.where(df["Month"] >= 10, df["Year"] + 1, df["Year"])

    flow_cols = [c for c in df.columns if c not in ("Year", "Month", "WY")]
    annual = df.groupby("WY")[flow_cols].sum().sum(axis=1)
    annual.name = "flow_index"
    return annual


# %% Match each synthetic WY to nearest historical WY
def match_to_historical(
    synthetic_index: pd.Series,
    hist_index: pd.Series,
    available_wys: set | None = None,
) -> pd.DataFrame:
    """For each synthetic WY, find the historical WY with nearest annual flow.

    Parameters
    ----------
    available_wys : set, optional
        If provided, restrict matching to only these historical WYs
        (e.g. those present in the vol-fraction lookup).
    """
    if available_wys is not None:
        hist_index = hist_index[hist_index.index.isin(available_wys)]

    records = []
    for wy in synthetic_index.index:
        diffs = (hist_index - synthetic_index[wy]).abs()
        best_wy = diffs.idxmin()
        records.append({
            "WY": int(wy),
            "matched_historical_WY": int(best_wy),
            "annual_flow_synthetic": synthetic_index[wy],
            "annual_flow_historical": hist_index[best_wy],
        })
    return pd.DataFrame(records)


# %% Resample daily fractions for February leap-year mismatch
def _resample_feb_fractions(fractions, tgt_days):
    """Cumulative-volume interpolation: redistribute daily fractions
    onto *tgt_days* bins, preserving the total (sum stays the same).
    """
    n_src = len(fractions)
    cum_src = np.concatenate(([0.0], np.cumsum(fractions)))
    t_src = np.linspace(0.0, 1.0, n_src + 1)
    t_tgt = np.linspace(0.0, 1.0, tgt_days + 1)
    cum_tgt = np.interp(t_tgt, t_src, cum_src)
    return np.diff(cum_tgt)


# %% Borrow vol-fraction pattern and format as standard Product B output
def build_product_b_vf(df_match: pd.DataFrame, vf_lookup: dict) -> pd.DataFrame:
    """For each matched WY, borrow vol-fraction pattern from historical year.

    Returns long-format DataFrame: Part B, Part C, Year, Month, Value

    February handling: Part B columns are daily bins whose fractions sum to 1
    for each month.  If source and target February have the same day count
    (both 28 or both 29), use the fractions directly.  If they differ,
    resample via cumulative-volume interpolation so the sum stays 1.
    """
    rows = []
    for _, match_row in df_match.iterrows():
        syn_wy = int(match_row["WY"])
        hist_wy = int(match_row["matched_historical_WY"])

        if hist_wy not in vf_lookup:
            print(f"    Warning: no vol-fraction data for historical WY {hist_wy}")
            continue

        vf_data = vf_lookup[hist_wy]  # DataFrame with Month column + Part B columns
        part_b_cols = sorted(c for c in vf_data.columns if c != "Month")

        # February day counts for source / target
        src_feb_days = 29 if calendar.isleap(hist_wy) else 28
        tgt_feb_days = 29 if calendar.isleap(syn_wy) else 28
        feb_mismatch = (src_feb_days != tgt_feb_days)

        for _, vf_row in vf_data.iterrows():
            month = int(vf_row["Month"])
            # Compute calendar year from WY and month
            if month >= 10:
                year = syn_wy - 1
            else:
                year = syn_wy

            # -- February with a day-count mismatch: resample daily bins --
            if month == 2 and feb_mismatch:
                # Collect non-NaN daily fractions in Part B sort order
                src_parts = []
                src_vals = []
                for pb in part_b_cols:
                    v = vf_row[pb]
                    if not np.isnan(v):
                        src_parts.append(pb)
                        src_vals.append(v)

                new_fracs = _resample_feb_fractions(
                    np.array(src_vals), tgt_feb_days,
                )

                written_parts = set()
                for i, new_val in enumerate(new_fracs):
                    if i < len(src_parts):
                        pb = src_parts[i]
                    else:
                        # Extra day (28 -> 29): pick next unused Part B bin
                        used = set(src_parts)
                        extra = [p for p in part_b_cols if p not in used]
                        pb = extra[0] if extra else src_parts[-1]
                    written_parts.add(pb)
                    rows.append({
                        "Part B": pb,
                        "Part C": "VOL-FRACTION",
                        "Year": year,
                        "Month": month,
                        "Value": new_val,
                    })
                # Write 0 for any Part B columns not covered by resampling
                for pb in part_b_cols:
                    if pb not in written_parts:
                        rows.append({
                            "Part B": pb,
                            "Part C": "VOL-FRACTION",
                            "Year": year,
                            "Month": month,
                            "Value": 0.0,
                        })
                continue

            # -- All other months (or Feb with matching day count): direct --
            for part_b in part_b_cols:
                val = vf_row[part_b]
                # Write 0.0 for NaN (day does not contribute flow)
                # so every Part B gets a row for every month.
                rows.append({
                    "Part B": part_b,
                    "Part C": "VOL-FRACTION",
                    "Year": year,
                    "Month": month,
                    "Value": 0.0 if np.isnan(val) else val,
                })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["Part B", "Year", "Month"]).reset_index(drop=True)
    return df


# %% Process a single chunk (top-level for pickling by ProcessPoolExecutor)
def _process_chunk(chunk, rim_dir, ref_csv, hist_annual, vf_lookup, out_dir, match_dir):
    """Process one Product B chunk: load inflows, match WYs, write output."""
    chunk_tag = f"n{chunk:02d}"

    df_chunk = load_chunk_inflows(rim_dir, chunk, ref_csv)
    if df_chunk.empty:
        return chunk_tag, 0, "no inflow data"

    syn_annual = compute_chunk_annual_index(df_chunk)
    df_match = match_to_historical(syn_annual, hist_annual,
                                    available_wys=set(vf_lookup.keys()))
    df_vf_chunk = build_product_b_vf(df_match, vf_lookup)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"vol_fraction_productB_{chunk_tag}.csv"
    df_vf_chunk.to_csv(out_csv, index=False)

    match_dir.mkdir(parents=True, exist_ok=True)
    match_csv = match_dir / f"wy_matches_{chunk_tag}.csv"
    df_match.to_csv(match_csv, index=False)

    return chunk_tag, len(df_vf_chunk), "ok"


# %% Main
def main():
    PRODUCT_B_FINAL.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract historical vol-fraction patterns from DSS
    print("=" * 60)
    print("Step 1: Extract historical VOL-FRACTION from DSS")
    print("=" * 60)
    df_vf = extract_vol_fractions(DEFAULT_DSS)
    vf_lookup = build_vf_by_wy(df_vf)
    print(f"  {len(vf_lookup)} complete water years available for borrowing")

    # Step 2: Build historical annual flow index
    print("\n" + "=" * 60)
    print("Step 2: Build historical annual flow index")
    print("=" * 60)
    hist_annual = build_historical_annual_index(DEFAULT_DSS, REFERENCE_CSV)

    # Step 3: Process Product B chunks in parallel
    print("\n" + "=" * 60)
    print(f"Step 3: Process Product B chunks ({MAX_WORKERS} workers)")
    print("=" * 60)

    futures = {}
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for chunk in range(1, N_CHUNKS + 1):
            fut = pool.submit(
                _process_chunk, chunk,
                RIM_INFLOW_DIR, REFERENCE_CSV, hist_annual,
                vf_lookup, PRODUCT_B_FINAL, DEFAULT_OUTDIR,
            )
            futures[fut] = chunk

        for fut in as_completed(futures):
            chunk_tag, n_records, status = fut.result()
            if status == "ok":
                print(f"  {chunk_tag}: {n_records} vol-fraction records")
            else:
                print(f"  {chunk_tag}: skipped ({status})")

    print("\nDone.")


if __name__ == "__main__":
    main()
