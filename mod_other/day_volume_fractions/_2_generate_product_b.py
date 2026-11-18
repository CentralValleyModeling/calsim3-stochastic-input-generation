"""
Generate Product B Day-Volume Fractions
=======================================
Daily VOL-FRACTION patterns of each Product B chunk: every chunk water year takes the CalSim3
baseline pattern of the donor water year (WY1955 or later, 12 complete months) with the nearest
annual flow index, the water-year sum of the reference inflows.

When donor and target February differ in day count, the donor's fractions on its real February
days are resampled by cumulative-volume interpolation onto the target's real days, so the month
still sums to 1. Days past the end of a month get 0, and the script stops if any month of a chunk
does not sum to 1 over its days.

Inputs
------
- <base>/CalSim3/__calsim_sv_default__.dss: VOL-FRACTION series and the reference inflows
- reference/reference_inflows.csv: Part B / Part C pairs of the annual flow index
- Product B rim inflows (utils.paths.get_rim_inflow_outputs): <Part B>_qmo_n01.csv ... _n10.csv
  of each reference inflow (qmap_postAdj), from
  mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product B

Outputs
-------
- <generated>/mod_other/day_volume_fractions/output/_product_b_final/
  vol_fraction_productB_n01.csv ... _n10.csv: Part B, Part C, Year, Month, Value
- <generated>/mod_other/day_volume_fractions/output/_2_generate_product_b/
  wy_matches_n01.csv ... _n10.csv: WY, matched_historical_WY, annual_flow_synthetic,
  annual_flow_historical

Dependencies
------------
utils.paths, utils.dss_io, utils.wgen_calendar; pydsstools

Usage
-----
    python mod_other/day_volume_fractions/_2_generate_product_b.py
"""

# Imports
import calendar
import os
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import get_base_dir, get_module_generated_dir, get_rim_inflow_outputs
from utils.wgen_calendar import N_CHUNKS, require_label_months, water_year

# Paths
_GEN_DIR = get_module_generated_dir("mod_other/day_volume_fractions")
DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
REFERENCE_CSV = Path(__file__).resolve().parent / "reference" / "reference_inflows.csv"
RIM_INFLOW_DIR = get_rim_inflow_outputs("B")["dir"]

script_name = Path(__file__).stem
DEFAULT_OUTDIR = _GEN_DIR / "output" / script_name
PRODUCT_B_FINAL = _GEN_DIR / "output" /"_product_b_final"

MAX_WORKERS = max(1, (os.cpu_count() or 4) - 1)

# Earliest water year allowed in the donor pool. Patterns before 1955 are
# themselves borrowed (a 1921-1954 year copies a 1955-2003 year), so they must
# not serve as donor candidates; only the observation-based 1955-2021 record is
# eligible.
DONOR_WY_MIN = 1955


# Helper: read a single DSS monthly time series (multi-block merge)
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


# Extract all Vol-Fraction records from historical DSS
def extract_vol_fractions(dss_path: Path) -> pd.DataFrame:
    """Read all monthly series with Part C = 'VOL-FRACTION' from DSS."""

    dss_monthly = {}
    print(f"Opening DSS: {Path(dss_path).name}")
    with dss_io.open_dss(dss_path, version=6, catalog_flag=True) as dss:
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


# Build historical vol-fraction lookup keyed by WY
def build_vf_by_wy(df_vf: pd.DataFrame, min_wy: int = DONOR_WY_MIN) -> dict:
    """Return {wy: DataFrame of 12 monthly rows} for eligible donor WYs.

    Only water years >= ``min_wy`` with a complete 12-month record are kept.
    Pre-1955 years are excluded because their patterns are themselves borrowed
    from the 1955-2003 pool.
    """
    df = df_vf.copy()
    df.index = pd.to_datetime(df.index)
    df["WY"] = water_year(df.index.year, df.index.month)
    df["Month"] = df.index.month

    lookup = {}
    for wy, grp in df.groupby("WY"):
        if wy >= min_wy and len(grp) == 12:
            lookup[wy] = grp.sort_values("Month").drop(columns="WY").reset_index(drop=True)
    return lookup


# Build historical annual flow index from DSS inflows
def build_historical_annual_index(dss_path: Path, ref_csv: Path) -> pd.Series:
    """Extract reference inflows from DSS and compute annual flow sum per WY."""

    ref = pd.read_csv(ref_csv)
    wanted = {(r["partb"].strip().upper(), r["partc"].strip().upper()) for _, r in ref.iterrows()}

    dss_monthly = {}
    with dss_io.open_dss(dss_path, version=6, catalog_flag=True) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*")
        buckets = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            if len(parts) < 6:
                continue
            key = (parts[1].upper(), parts[2].upper())
            if key in wanted:
                buckets.setdefault(key, []).append(p)

        # The synthetic index sums every reference inflow, so the historical one must too
        missing = wanted - set(buckets)
        if missing:
            raise ValueError(f"{len(missing)} reference inflows not found in {Path(dss_path).name}: "
                             + ", ".join(f"{pb}/{pc}" for pb, pc in sorted(missing)))
        print(f"  Found {len(buckets)}/{len(wanted)} reference inflows in DSS")

        for key in sorted(buckets):
            part_b, _ = key
            series = _read_dss_series(dss, buckets[key])
            if not series.notna().any():
                raise ValueError(f"reference inflow {part_b} has no values in {Path(dss_path).name}")
            dss_monthly[part_b] = series

    df = pd.DataFrame(dss_monthly).sort_index()
    df.index = pd.to_datetime(df.index)
    df["WY"] = water_year(df.index.year, df.index.month)

    annual = df.groupby("WY")[list(dss_monthly.keys())].sum().sum(axis=1)
    annual.name = "flow_index"
    print(f"  Historical annual index: {len(annual)} water years")
    return annual


# Load Product B inflows for one chunk from rim_inflow CSVs
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

        df = pd.read_csv(csv_path, usecols=["Year", "Month", "qmap_postAdj"])
        require_label_months(df["Year"], df["Month"], csv_path.name)
        series_dict[partb] = df.set_index(["Year", "Month"])["qmap_postAdj"].rename(partb)

    if missing:
        raise FileNotFoundError(
            f"{len(missing)}/{len(partb_list)} rim inflows of chunk {chunk_tag} missing in "
            f"{rim_dir}: " + ", ".join(f"{m}_qmo_{chunk_tag}.csv" for m in missing))

    result = pd.DataFrame(series_dict)
    print(f"    Chunk {chunk_tag}: loaded {len(series_dict)}/{len(partb_list)} inflows, {len(result)} months")
    return result


# Compute annual flow index from chunk inflows
def compute_chunk_annual_index(df_chunk: pd.DataFrame) -> pd.Series:
    """Sum all inflow columns by water year for a Product B chunk."""
    df = df_chunk.copy()
    df = df.reset_index()
    df["WY"] = water_year(df["Year"], df["Month"])

    flow_cols = [c for c in df.columns if c not in ("Year", "Month", "WY")]
    annual = df.groupby("WY")[flow_cols].sum().sum(axis=1)
    annual.name = "flow_index"
    return annual


# Match each synthetic WY to nearest historical WY
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


# Resample daily fractions for February leap-year mismatch
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


def _day_number(part_b: str) -> int:
    """DAY7 -> 7."""
    if not (part_b.startswith("DAY") and part_b[3:].isdigit()):
        raise ValueError(f"VOL-FRACTION Part B {part_b!r} is not DAY<n>")
    return int(part_b[3:])


def day_columns(columns) -> list:
    """The DAY<n> columns in day order, which must run DAY1, DAY2, ... without a gap."""
    days = sorted((c for c in columns if c != "Month"), key=_day_number)
    if [_day_number(c) for c in days] != list(range(1, len(days) + 1)):
        raise ValueError(f"VOL-FRACTION days are not DAY1..DAY{len(days)}: {days}")
    return days


# Borrow vol-fraction pattern and format as standard Product B output
def build_product_b_vf(df_match: pd.DataFrame, vf_lookup: dict) -> pd.DataFrame:
    """For each matched WY, borrow vol-fraction pattern from historical year.

    Returns long-format DataFrame: Part B, Part C, Year, Month, Value

    February handling: Part B columns are daily bins DAY1..DAY31 whose fractions sum to 1
    for each month.  If source and target February have the same day count
    (both 28 or both 29), use the fractions directly.  If they differ, the
    source's real days are resampled onto the target's real days via
    cumulative-volume interpolation so the sum stays 1.
    """
    rows = []
    for _, match_row in df_match.iterrows():
        syn_wy = int(match_row["WY"])
        hist_wy = int(match_row["matched_historical_WY"])

        if hist_wy not in vf_lookup:
            print(f"    Warning: no vol-fraction data for historical WY {hist_wy}")
            continue

        vf_data = vf_lookup[hist_wy]  # DataFrame with Month column + Part B columns
        part_b_cols = day_columns(vf_data.columns)

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

            # -- February with a day-count mismatch: resample the real days --
            if month == 2 and feb_mismatch:
                src_vals = np.nan_to_num(
                    np.array([vf_row[pb] for pb in part_b_cols[:src_feb_days]], dtype=float))
                new_fracs = dict(zip(part_b_cols[:tgt_feb_days],
                                     _resample_feb_fractions(src_vals, tgt_feb_days)))
                for pb in part_b_cols:
                    rows.append({
                        "Part B": pb,
                        "Part C": "VOL-FRACTION",
                        "Year": year,
                        "Month": month,
                        "Value": new_fracs.get(pb, 0.0),
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


def check_month_sums(df: pd.DataFrame, label: str, tol: float = 1e-6) -> None:
    """Every month sums to 1 over its real days and holds 0 on the days past its end."""
    day = df["Part B"].map(_day_number)
    month_days = [calendar.monthrange(int(y), int(m))[1] for y, m in zip(df["Year"], df["Month"])]
    real = day <= np.asarray(month_days)
    sums = df["Value"].where(real, 0.0).groupby([df["Year"], df["Month"]]).sum()
    spill = df["Value"].where(~real, 0.0).abs().groupby([df["Year"], df["Month"]]).sum()
    bad = sums.index[((sums - 1).abs() > tol) | (spill > tol)]
    if len(bad):
        y, m = bad[0]
        raise ValueError(f"{label}: {len(bad)} months do not sum to 1 over their days, first "
                         f"{y}-{m:02d} (real days {sums[(y, m)]:.6f}, past the end {spill[(y, m)]:.6f})")


# Process a single chunk (top-level for pickling by ProcessPoolExecutor)
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
    check_month_sums(df_vf_chunk, f"chunk {chunk_tag}")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"vol_fraction_productB_{chunk_tag}.csv"
    df_vf_chunk.to_csv(out_csv, index=False)

    match_dir.mkdir(parents=True, exist_ok=True)
    match_csv = match_dir / f"wy_matches_{chunk_tag}.csv"
    df_match.to_csv(match_csv, index=False)

    return chunk_tag, len(df_vf_chunk), "ok"


# Main
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
