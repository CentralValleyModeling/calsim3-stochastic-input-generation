#!/usr/bin/env python3
"""
Reservoir Storage-Level Index Curve Generator (Product A & B)
=============================================================

Generates reservoir storage-level index curves for Product A and Product B
using schedule tables from reference CSVs and water year type series.

Two types of series are supported:
  - **Monthly repeating** (from reservoir_schedule_monthly.csv): same 12 values
    repeated every year regardless of water year type.
  - **WYT-driven** (from reservoir_schedule_wyt.csv): value depends on the
    water year type (W/AN/BN/D/C) for each year, with per-series basin_wyt
    assignment (Sac or SJ).

Dependencies:
  - mod_hydrology/water_year_types/_1_calc_WYTs.py  (Product A/B WYT CSVs)
  - BASE/CalSim3/__calsim_sv_default__.dss           (historical validation + first-month gap fill)

Inputs:
  - reference/reservoir_schedule_monthly.csv  (partb, partc, month_wy, target_storage_taf, pattern)
  - reference/reservoir_schedule_wyt.csv      (partb, partc, year_type, target_storage_taf, year_type_basis, basin_wyt)
  - mod_hydrology/water_year_types/reference/  (_Historical_SacWYT.csv, _Historical_SJWYT.csv)
  - GENERATED/mod_hydrology/water_year_types/output/_1_calc_WYTs/Product_A/  (_SacWYT.csv, _SJWYT.csv)
  - GENERATED/mod_hydrology/water_year_types/output/_1_calc_WYTs/Product_B/  (_SacWYT_{ens}.csv, _SJWYT_{ens}.csv)

Outputs are written under:
  <generated>/output/_1_wyt_index_curves/          (historical validation CSV + figures/historical/ per-series TS+CDF with R2/NSE/PBIAS)
  <generated>/output/_1_wyt_index_curves/figures/product_a/  (Product A vs historical actuals per-series TS+CDF, --product A)
  <generated>/output/_product_a_validation/         (Product A)
  <generated>/output/_product_b_final/              (Product B)

Output CSV format: Part B, Part C, Year, Month, Value

Usage
-----
    python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product A
    python mod_reservoir/storage_curves/_1_wyt_index_curves.py --product B
"""
# -- IMPORTS ---------------------------------------------------------------
import argparse
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils import dss_io
from utils.validation_plots import Series, plot_ts_cdf

# -- CONSTANTS -------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REF = _SCRIPT_DIR / "reference"
_gen = get_module_generated_dir("mod_reservoir/storage_curves")
BASE_RESULTS_DIR = _gen / "output"
HIST_VALIDATION_DIR = BASE_RESULTS_DIR / "_1_wyt_index_curves"
HIST_PLOT_DIR = HIST_VALIDATION_DIR / "figures" / "historical"
PROD_A_PLOT_DIR = HIST_VALIDATION_DIR / "figures" / "product_a"
PRODUCT_A_DIR = BASE_RESULTS_DIR / "_product_a_validation"
PRODUCT_B_DIR = BASE_RESULTS_DIR / "_product_b_final"

_WYT_HIST_DIR = _REPO_ROOT / "mod_hydrology" / "water_year_types" / "reference"
_WYT_GEN = get_module_generated_dir("mod_hydrology/water_year_types")
_WYT_PRODUCT_DIRS = {"A": "Product_A", "B": "Product_B"}

_MONTH_NUM = {
    "October": 10, "November": 11, "December": 12,
    "January": 1, "February": 2, "March": 3,
    "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9,
}

_BASIN_WYT_FILES = {
    "sac": {"hist": "_Historical_SacWYT.csv", "prodA": "_SacWYT.csv", "prodB": "_SacWYT_{ens}.csv"},
    "sj":  {"hist": "_Historical_SJWYT.csv",  "prodA": "_SJWYT.csv",  "prodB": "_SJWYT_{ens}.csv"},
}

OUTPUT_PREFIX = "storage_curves"

_DEFAULT_DSS = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"


# -- DSS READER -------------------------------------------------------------

def read_dss_data(
    dss_path: Path,
    specs: list,
) -> Dict[Tuple[str, str], pd.Series]:
    """Read monthly time series from a DSS file for the given (Part B, Part C) pairs.

    Parameters
    ----------
    dss_path : Path
        Path to the DSS file.
    specs : list of (str, str)
        List of (Part B, Part C) tuples to extract.

    Returns
    -------
    dict[(str, str), pd.Series]
        Monthly time series keyed by (Part B upper, Part C upper).
    """
    dss_path = Path(dss_path).resolve()
    print(f"    Reading DSS: {dss_path.name}")

    requested = {
        (b.strip().upper(), c.strip().upper())
        for b, c in specs
        if b.strip() and c.strip()
    }
    if not requested:
        return {}

    out: Dict[Tuple[str, str], pd.Series] = {}
    with dss_io.open_dss(str(dss_path), version=6, catalog_flag=False) as dss:
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*/")
        print(f"    Catalog: {len(all_paths)} monthly paths found")

        bucket: Dict[Tuple[str, str], list] = {}
        for p in all_paths:
            parts = p.strip("/").split("/")
            if len(parts) < 6:
                continue
            key = (parts[1].strip().upper(), parts[2].strip().upper())
            if key in requested:
                bucket.setdefault(key, []).append(p)

        print(f"    Matched {len(bucket)} of {len(requested)} schedule SVs")

        for key in sorted(requested):
            if key not in bucket:
                continue
            master = pd.Series(dtype=float)
            for p in sorted(bucket[key], key=lambda x: (x.strip("/").split("/")[3], x)):
                ts = dss.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals = np.where(vals <= -900, np.nan, vals)
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                master = master.combine_first(pd.Series(vals, index=idx))
            if master.notna().any():
                out[key] = master.sort_index()

    print(f"    Result: {len(out)} variables")
    return out


# -- HELPERS ----------------------------------------------------------------

def water_year(dt) -> int:
    """CA convention: WY N is Oct(N-1) - Sep(N)."""
    dt = pd.Timestamp(dt)
    return int(dt.year + (1 if dt.month >= 10 else 0))


def _make_monthly_index(wy_min: int, wy_max: int) -> pd.DataFrame:
    """Monthly dates spanning WY_min..WY_max inclusive, aligned to month-end."""
    start = pd.Timestamp(wy_min - 1, 10, 1) + pd.offsets.MonthEnd(0)
    end = pd.Timestamp(wy_max, 9, 1) + pd.offsets.MonthEnd(0)
    dates = pd.date_range(start=start, end=end, freq="ME")
    out = pd.DataFrame({"date": dates})
    out["WY"] = out["date"].apply(water_year).astype(int)
    out["month"] = out["date"].dt.month.astype(int)
    return out


# -- SCHEDULE READERS -------------------------------------------------------

def read_monthly_schedule(csv_path: Path) -> pd.DataFrame:
    """Load reservoir_schedule_monthly.csv as raw long-form DataFrame."""
    return pd.read_csv(csv_path)


def read_wyt_schedule(csv_path: Path) -> pd.DataFrame:
    """Load reservoir_schedule_wyt.csv as raw long-form DataFrame."""
    return pd.read_csv(csv_path)


def _collect_partbc_specs(monthly_sched: pd.DataFrame, wyt_sched: pd.DataFrame) -> list:
    """Collect unique (Part B, Part C) pairs from both schedule DataFrames."""
    specs = []
    for _, row in monthly_sched.drop_duplicates(subset="partb").iterrows():
        specs.append((row["partb"], row["partc"]))
    for _, row in wyt_sched.drop_duplicates(subset="partb").iterrows():
        specs.append((row["partb"], row["partc"]))
    return specs


# -- WYT LOADERS ------------------------------------------------------------

def _read_wyt_csv(path: Path) -> pd.DataFrame:
    """Read a WYT CSV, return DataFrame with columns [WY, WYT]."""
    df = pd.read_csv(path)
    out = df[["water_year", "wyt_label"]].copy()
    out.columns = ["WY", "WYT"]
    out["WY"] = out["WY"].astype(int)
    out["WYT"] = out["WYT"].str.strip().str.upper()
    return out


def _load_wyt(wyt_dir: Path, basins: set, product: str, ensemble: str = "") -> Dict[str, pd.DataFrame]:
    """Load WYT tables for the given basins and product.

    Parameters
    ----------
    product : str
        'hist', 'A', or 'B'.
    ensemble : str
        Required for Product B, e.g. 'n01'.
    """
    tables = {}
    for basin in sorted(basins):
        info = _BASIN_WYT_FILES[basin]
        if product == "hist":
            fname = info["hist"]
        elif product == "A":
            fname = info["prodA"]
        elif product == "B":
            fname = info["prodB"].format(ens=ensemble)
        else:
            raise ValueError(f"Unknown product '{product}'")
        path = wyt_dir / fname
        print(f"    Loading WYT: {path.name} (basin={basin})")
        tables[basin] = _read_wyt_csv(path)
    return tables


# -- CORE: GENERATE TARGET TIME SERIES -------------------------------------

def generate_targets(
    monthly_sched: pd.DataFrame,
    wyt_sched: pd.DataFrame,
    wyt_tables: Dict[str, pd.DataFrame],
    map_wyt_by: str = None,
) -> pd.DataFrame:
    """Generate target storage-level time series for all schedule series.

    Parameters
    ----------
    monthly_sched : pd.DataFrame
        Raw monthly schedule (partb, partc, month_wy, target_storage_taf).
    wyt_sched : pd.DataFrame
        Raw WYT schedule (partb, partc, year_type, target_storage_taf,
        year_type_basis, basin_wyt).
    wyt_tables : dict
        basin key -> DataFrame with [WY, WYT].
    map_wyt_by : str or None
        Force all WYT series to map by calendar year ('cy') or water
        year ('wy'), ignoring the per-series year_type_basis in the CSV.
        Default None uses year_type_basis from the schedule CSV.

    Returns
    -------
    pd.DataFrame
        Long-form: Part B, Part C, Year, Month, Value
    """
    # Determine date range from WYT tables
    all_wys = pd.concat([t["WY"] for t in wyt_tables.values()])
    wy_min, wy_max = int(all_wys.min()), int(all_wys.max())
    grid = _make_monthly_index(wy_min, wy_max)
    grid["cy"] = grid["date"].dt.year

    results = []

    # --- Monthly repeating series ---
    monthly_series = monthly_sched.drop_duplicates(subset="partb")
    for _, srow in monthly_series.iterrows():
        partb = srow["partb"]
        partc = srow["partc"]
        subset = monthly_sched[monthly_sched["partb"] == partb]
        month_vals = {
            _MONTH_NUM[m]: v
            for m, v in zip(subset["month_wy"], subset["target_storage_taf"])
        }

        sv = grid.copy()
        sv["Value"] = sv["month"].map(month_vals)
        sv["Part B"] = partb
        sv["Part C"] = partc
        results.append(sv[["Part B", "Part C", "date", "Value"]])

    # --- WYT-driven series ---
    wyt_series_info = wyt_sched.drop_duplicates(subset="partb")
    for _, srow in wyt_series_info.iterrows():
        partb = srow["partb"]
        partc = srow["partc"]
        basin = str(srow["basin_wyt"]).strip().lower()

        if basin not in wyt_tables:
            print(f"[WARN] No WYT loaded for basin '{basin}' (series {partb}); skipping")
            continue

        wyt_df = wyt_tables[basin]
        subset = wyt_sched[wyt_sched["partb"] == partb]
        wyt_vals = dict(
            zip(subset["year_type"].str.strip().str.upper(), subset["target_storage_taf"])
        )

        # Determine WYT mapping basis: override or per-series from CSV
        if map_wyt_by is not None:
            key_col = "WY" if map_wyt_by.lower() == "wy" else "cy"
        else:
            basis_vals = subset["year_type_basis"].dropna().str.strip().str.lower().unique()
            if len(basis_vals) != 1:
                raise ValueError(
                    f"Series {partb}: expected exactly one year_type_basis, "
                    f"got {list(basis_vals)}"
                )
            basis = basis_vals[0]
            if basis in ("wy", "water_year"):
                key_col = "WY"
            else:
                key_col = "cy"

        sv = grid.copy()
        wyt_merge = wyt_df.rename(columns={"WY": key_col})
        sv = sv.merge(wyt_merge, on=key_col, how="left")
        sv["Value"] = sv["WYT"].map(wyt_vals)
        sv["Part B"] = partb
        sv["Part C"] = partc
        results.append(sv[["Part B", "Part C", "date", "Value"]])

    if not results:
        return pd.DataFrame(columns=["Part B", "Part C", "Year", "Month", "Value"])

    combined = pd.concat(results, ignore_index=True)
    combined["Year"] = combined["date"].dt.year
    combined["Month"] = combined["date"].dt.month
    out = combined[["Part B", "Part C", "Year", "Month", "Value"]].sort_values(
        ["Part B", "Year", "Month"]
    ).reset_index(drop=True)
    return out


# -- OUTPUT WRITERS ---------------------------------------------------------

def _write_product_a(df: pd.DataFrame, prefix: str) -> None:
    """Write Product A validation CSV."""
    PRODUCT_A_DIR.mkdir(parents=True, exist_ok=True)

    dates = pd.to_datetime(
        df[["Year", "Month"]].assign(Day=1).rename(
            columns={"Year": "year", "Month": "month", "Day": "day"}
        )
    )
    wy_min = int(dates.apply(water_year).min())
    wy_max = int(dates.apply(water_year).max())

    out_path = PRODUCT_A_DIR / f"{prefix}_productA_{wy_min}_{wy_max}.csv"
    df.to_csv(out_path, index=False)
    print(f"  [OK] {out_path}")


def _write_product_b(df: pd.DataFrame, ensemble: str) -> None:
    """Write one Product B ensemble CSV, one file per Part B."""
    PRODUCT_B_DIR.mkdir(parents=True, exist_ok=True)
    for partb, sub in df.groupby("Part B"):
        out_path = PRODUCT_B_DIR / f"{partb}_productB_{ensemble}.csv"
        sub.to_csv(out_path, index=False)
        print(f"  [OK] {out_path.name}")


# -- PLOTTING ---------------------------------------------------------------

def _plot_actual_vs_reconstructed(
    dates: pd.Series,
    actual: pd.Series,
    reconstructed: pd.Series,
    partb: str,
    out_path: Path,
    recon_label: str = "Reconstructed",
) -> None:
    """Monthly time series + non-exceedance CDF for one series.

    Thin wrapper over :func:`utils.validation_plots.plot_ts_cdf` that pairs the
    historical DSS actual with the reconstructed schedule series and lets the
    helper compute R2 / NSE / PBIAS from the Historical baseline
    (``compute_metrics_from=0``).
    """
    plot_ts_cdf(
        series=[
            Series("Historical", dates, actual.to_numpy(dtype=float),
                   linewidth=0.8),
            Series(recon_label, dates,
                   reconstructed.to_numpy(dtype=float)),
        ],
        title=f"{partb} (TAF)",
        unit="TAF",
        compute_metrics_from=0,
        out_path=out_path,
    )
    print(f"  [PLOT] {out_path.name}")


def run_product_a_plots(
    df: pd.DataFrame,
    dss_data: Dict[Tuple[str, str], pd.Series],
) -> None:
    """Plot Product A targets against historical DSS actuals (WY 1972-2018).

    Mirrors the historical validation figures but pairs the Product A series
    (schedule targets applied to Product A WYT classifications) with the
    historical CalSim inputs, labeled ``Historical`` vs ``Product A``.
    Written to ``figures/product_a/<Part B>.png``.
    """
    print(f"\n{'='*60}")
    print("Product A validation plots (actual vs Product A)")
    print(f"{'='*60}")
    PROD_A_PLOT_DIR.mkdir(parents=True, exist_ok=True)

    tmp = df.copy()
    tmp["date"] = pd.to_datetime(
        tmp[["Year", "Month"]].assign(Day=1).rename(
            columns={"Year": "year", "Month": "month", "Day": "day"}
        )
    ) + pd.offsets.MonthEnd(0)

    plot_start = pd.Timestamp("1971-10-01")
    plot_end = pd.Timestamp("2018-09-30")
    for (partb, partc), sub in tmp.groupby(["Part B", "Part C"]):
        key = (str(partb).strip().upper(), str(partc).strip().upper())
        if key not in dss_data:
            print(f"  [WARN] No DSS actuals for {partb}/{partc}; skipping plot")
            continue
        sub = sub.sort_values("date")
        sub = sub[(sub["date"] >= plot_start) & (sub["date"] <= plot_end)]
        actual_s = dss_data[key].reindex(sub["date"]).astype(float)
        _plot_actual_vs_reconstructed(
            dates=sub["date"],
            actual=actual_s,
            reconstructed=pd.to_numeric(sub["Value"], errors="coerce"),
            partb=partb,
            out_path=PROD_A_PLOT_DIR / f"{partb}.png",
            recon_label="Product A",
        )


# -- HISTORICAL VALIDATION --------------------------------------------------

def run_historical_validation(
    monthly_sched: pd.DataFrame,
    wyt_sched: pd.DataFrame,
    dss_data: Dict[Tuple[str, str], pd.Series],
    map_wyt_by: str = None,
) -> None:
    """Compare historical DSS actuals against reconstructed schedule + historical WYT,
    and write actual_vs_reconstructed.csv + per-series plots."""
    print(f"\n{'='*60}")
    print("Historical validation (actual vs reconstructed)")
    print(f"{'='*60}")

    # Determine which WYT basins are needed
    basins = set(wyt_sched["basin_wyt"].str.strip().str.lower().unique())

    # Load historical WYT
    wyt_tables = _load_wyt(_WYT_HIST_DIR, basins, product="hist")

    # Generate reconstructed targets from schedule + historical WYT
    recon = generate_targets(monthly_sched, wyt_sched, wyt_tables, map_wyt_by=map_wyt_by)

    # Build long-form actual-vs-reconstructed table
    recon["date"] = pd.to_datetime(
        recon[["Year", "Month"]].assign(Day=1).rename(
            columns={"Year": "year", "Month": "month", "Day": "day"}
        )
    ) + pd.offsets.MonthEnd(0)

    # Build per-series basin_wyt lookup
    basin_map = {}
    for _, row in monthly_sched.drop_duplicates(subset="partb").iterrows():
        basin_map[row["partb"]] = None
    for _, row in wyt_sched.drop_duplicates(subset="partb").iterrows():
        basin_map[row["partb"]] = str(row["basin_wyt"]).strip().lower()

    # Map DSS actuals into a lookup keyed by ((partb, partc), date)
    dss_lookup = {}
    for (partb, partc), series in dss_data.items():
        for dt, val in series.items():
            dss_lookup[((partb, partc), pd.Timestamp(dt))] = val

    rows = []
    for _, r in recon.iterrows():
        partb = r["Part B"]
        date = r["date"]
        wy = water_year(date)
        basin = basin_map.get(partb)
        if basin and basin in wyt_tables:
            wyt_row = wyt_tables[basin]
            match = wyt_row.loc[wyt_row["WY"] == wy, "WYT"]
            wyt_label = match.iloc[0] if len(match) > 0 else ""
        else:
            wyt_label = ""
        partc = r["Part C"]
        rows.append({
            "date": date,
            "wyt": wyt_label,
            "partb": partb,
            "partc": partc,
            "schedule_type": "wyt" if basin else "monthly",
            "actual": dss_lookup.get(((partb, partc), date), np.nan),
            "reconstructed": r["Value"],
        })

    out = pd.DataFrame(rows).sort_values(["partb", "date"]).reset_index(drop=True)
    out = out[out["date"] >= "1921-10-31"].reset_index(drop=True)

    # Fill NaN reconstructed (first 3 months with no WYT) from DSS actuals
    mask = out["reconstructed"].isna() & out["actual"].notna()
    out.loc[mask, "reconstructed"] = out.loc[mask, "actual"]

    # Write CSV
    HIST_VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    out_path = HIST_VALIDATION_DIR / f"{OUTPUT_PREFIX}_actual_vs_reconstructed.csv"
    out.to_csv(out_path, index=False)
    print(f"  [OK] {out_path}")

    # Generate per-series plots (validation window: WY 1972-2018)
    HIST_PLOT_DIR.mkdir(parents=True, exist_ok=True)
    plot_start = pd.Timestamp("1971-10-01")
    plot_end = pd.Timestamp("2018-09-30")
    for partb in sorted(out["partb"].unique()):
        sub = out[out["partb"] == partb].copy()
        sub = sub.sort_values("date")
        sub = sub[(sub["date"] >= plot_start) & (sub["date"] <= plot_end)]
        actual_s = pd.to_numeric(sub["actual"], errors="coerce")
        recon_s = pd.to_numeric(sub["reconstructed"], errors="coerce")
        _plot_actual_vs_reconstructed(
            dates=sub["date"],
            actual=actual_s,
            reconstructed=recon_s,
            partb=partb,
            out_path=HIST_PLOT_DIR / f"{partb}.png",
        )


# -- MAIN ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Generate reservoir storage-level index curves for Product A and B."
    )
    ap.add_argument("--product", type=str, choices=["A", "B"], required=True,
                    help='Product to generate: A (historical 1921-2018) or B (stochastic 1000-yr chunks).')
    ap.add_argument("--yr-type-map", type=str, choices=["cy", "wy"], default=None,
                    help="Force all WYT series to map by Calendar Year (cy) or "
                         "Water Year (wy), ignoring per-series year_type_basis. "
                         "Default: use year_type_basis from CSV")
    args = ap.parse_args()

    products = [args.product.strip().upper()]

    # Read schedule CSVs
    monthly_sched = read_monthly_schedule(_REF / "reservoir_schedule_monthly.csv")
    wyt_sched = read_wyt_schedule(_REF / "reservoir_schedule_wyt.csv")

    # Determine which WYT basins are needed
    basins = set(wyt_sched["basin_wyt"].str.strip().str.lower().unique())
    print(f"WYT basins referenced: {sorted(basins)}")

    # Read historical DSS actuals (used for validation + first-month gap fill)
    partbc_specs = _collect_partbc_specs(monthly_sched, wyt_sched)
    dss_data = read_dss_data(_DEFAULT_DSS, partbc_specs)

    # Historical validation (actual DSS vs reconstructed from schedule + hist WYT)
    run_historical_validation(
        monthly_sched, wyt_sched, dss_data, map_wyt_by=args.yr_type_map
    )

    wyt_product_dir = _WYT_GEN / "output" / "_1_calc_WYTs"

    def _fill_from_dss(df: pd.DataFrame) -> None:
        """
        Fill NaN values in-place using historical DSS actuals, but only for the
        known initial boundary gap (first few months per Part B/C).

        Any NaNs outside the initial boundary window, or NaNs that remain after
        attempting the boundary fill, will raise a ValueError instead of being
        silently back-filled.
        """
        # Quick exit if there are no NaNs at all
        if not df["Value"].isna().any():
            return

        # Construct end-of-month timestamps corresponding to Year/Month columns
        dates = (
            pd.to_datetime(
                df[["Year", "Month"]]
                .assign(Day=1)
                .rename(columns={"Year": "year", "Month": "month", "Day": "day"})
            )
            + pd.offsets.MonthEnd(0)
        )

        # Allow DSS fills only in the first few months of each Part B/C series
        boundary_months = 3  # corresponds to first Oct-Dec when using WY alignment

        df["Value"].isna()

        # First, validate that all NaNs are within the allowed boundary window
        invalid_nan_info = []
        for (part_b, part_c), grp_idx in df.groupby(["Part B", "Part C"]).groups.items():
            grp_idx = list(grp_idx)
            grp = df.loc[grp_idx].sort_values(["Year", "Month"])
            grp_nan = grp["Value"].isna()
            if not grp_nan.any():
                continue

            # Indices of the first `boundary_months` rows in time order
            boundary_idx = set(grp.head(boundary_months).index)
            nan_idx = set(grp[grp_nan].index)

            # NaNs that occur outside the initial boundary window are invalid
            invalid_idx = nan_idx.difference(boundary_idx)
            if invalid_idx:
                # Capture a few offending rows for the error message
                for bad in sorted(invalid_idx)[:5]:
                    row = df.loc[bad]
                    invalid_nan_info.append(
                        f"(Part B={row['Part B']}, Part C={row['Part C']}, "
                        f"Year={int(row['Year'])}, Month={int(row['Month'])})"
                    )

        if invalid_nan_info:
            details = "; ".join(invalid_nan_info)
            raise ValueError(
                "Encountered NaN Value entries outside the allowed initial "
                "boundary gap when generating reservoir WYT index curves. "
                "These likely indicate missing schedule rows, WYT labels, or "
                "merge issues that must be fixed upstream. Offending points: "
                f"{details}"
            )

        # Perform the allowed DSS-based fills within the boundary window
        for (part_b, part_c), grp_idx in df.groupby(["Part B", "Part C"]).groups.items():
            grp_idx = list(grp_idx)
            grp = df.loc[grp_idx].sort_values(["Year", "Month"])
            boundary_idx = grp.head(boundary_months).index
            # Only consider NaNs within the boundary window
            fill_idx = [i for i in boundary_idx if df.at[i, "Value"] is np.nan or pd.isna(df.at[i, "Value"])]
            for idx in fill_idx:
                key = (part_b, part_c)
                dt = dates[idx]
                if key in dss_data:
                    val = dss_data[key].get(dt, np.nan)
                    if not np.isnan(val):
                        df.at[idx, "Value"] = val

        # Final safety check: no NaNs should remain anywhere
        remaining_nans = df["Value"].isna()
        if remaining_nans.any():
            bad_rows = df[remaining_nans].head(5)
            examples = [
                f"(Part B={row['Part B']}, Part C={row['Part C']}, "
                f"Year={int(row['Year'])}, Month={int(row['Month'])})"
                for _, row in bad_rows.iterrows()
            ]
            raise ValueError(
                "NaN Value entries remain after attempting allowed DSS "
                "boundary gap fill in reservoir WYT index curves. This "
                "likely indicates missing DSS coverage or schedule issues "
                "that must be addressed. Example points: "
                + "; ".join(examples)
            )
    for prod in products:
        print(f"\n{'='*60}")
        print(f"Generating Product {prod}")
        print(f"{'='*60}")

        if prod == "A":
            wyt_dir = wyt_product_dir / _WYT_PRODUCT_DIRS["A"]
            wyt_tables = _load_wyt(wyt_dir, basins, product="A")
            df = generate_targets(
                monthly_sched, wyt_sched, wyt_tables, map_wyt_by=args.yr_type_map
            )
            _fill_from_dss(df)
            _write_product_a(df, OUTPUT_PREFIX)
            run_product_a_plots(df, dss_data)

        elif prod == "B":
            for i in range(1, 11):
                ensemble = f"n{i:02d}"
                print(f"\n  --- Ensemble {ensemble} ---")
                wyt_dir = wyt_product_dir / _WYT_PRODUCT_DIRS["B"]
                wyt_tables = _load_wyt(wyt_dir, basins, product="B", ensemble=ensemble)
                df = generate_targets(
                    monthly_sched, wyt_sched, wyt_tables, map_wyt_by=args.yr_type_map
                )
                _fill_from_dss(df)
                _write_product_b(df, ensemble)

    print("\nDone.")


if __name__ == "__main__":
    main()
