"""
SJR Restoration Flow Requirements
==================================
Reconstruct monthly REST_REQ_NP and REST_REQ_P from UNIMP_SJ unimpaired
flow data, for historical comparison, Product A, and Product B.

Dependencies
------------
- mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
    Product A UNIMP_SJ is read from the CalSim-format validation CSV:
    ``data/GENERATED/mod_hydrology/rim_inflow/output/_2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv``
    (filtered by Part B == UNIMP_SJ)

- mod_hydrology/rim_inflow/_3_qmap_productB.py
    Product B UNIMP_SJ is read from per-chunk CSVs:
    ``data/GENERATED/mod_hydrology/rim_inflow/output/_3_qmap_product_b/UNIMP_SJ_qmo_n*.csv``
"""
from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils import dss_io

# -----------------------------------------------------------------------------
# User-facing defaults
# -----------------------------------------------------------------------------
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
DEFAULT_DSS_READ_START = "1915-01-31"
DEFAULT_DSS_READ_END = "2021-12-31"
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
DEFAULT_PRODUCT_A = _rim_gen / "output" / "_2_qmap_historical_validation" /"_product_a_validation"/"_riminflow_productA_1972_2018.csv"
DEFAULT_PRODUCT_B_DIR = _rim_gen / "output" / "_3_qmap_product_b"
_gen = get_module_generated_dir("mod_other/instream_flows")
DEFAULT_OUT_HIST = _gen / "output" / "_2_sjr_rest_req"
DEFAULT_OUT_A = _gen / "output" / "_product_a_validation"
DEFAULT_OUT_B = _gen / "output" / "_product_b_final"

#  Conversion Constants
# -----------------------------------------------------------------------------
CFS_DAY_TO_TAF = 86400.0 / (1000.0 * 43560.0)

# Pulse is built from the April second-half, non-pulse is the residual over 14 days.
APRIL_NONPULSE_DAYS = 14
APRIL_PULSE_DAYS = 16

# -----------------------------------------------------------------------------
# Annual Release Thresholds (from Method sheet)
# -----------------------------------------------------------------------------
CRITICAL_LOW_RELEASE = 116.8660524
CRITICAL_HIGH_RELEASE = 187.78502225
DRY_LOWER_RELEASE = 272.278
NORMAL_DRY_RELEASE = 330.256
NORMAL_WET_RELEASE = 400.256
NWET_PLUS_RELEASE = 547.444
WET_RELEASE = 673.4872385

# -----------------------------------------------------------------------------
# release schedules from alpha sheet.
# Periods:
#   1 Mar 1-15
#   2 Mar 16-31
#   3 Apr 1-15
#   4 Apr 16-30 
#   5 May-Jun 
#   6 Jul-Aug 
#   7 Sep
#   8 Oct
#   9 Nov 1-6
#  10 Nov 7-10
#  11 Nov 11-Dec 31 
#  12 Jan-Feb 
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class AlphaProfile:
    name: str
    annual_release_taf: float
    cfs_blocks: tuple[float, ...]


ALPHA_PROFILES: tuple[AlphaProfile, ...] = (
    AlphaProfile(
        "Critical-Low",
        116.8660524,
        (130.0, 130.0, 150.0, 150.0, 190.0, 230.0, 210.0, 160.0, 130.0, 120.0, 120.0, 100.0),
    ),
    AlphaProfile(
        "Critical-High",
        187.78502225,
        (500.0, 1500.0, 200.0, 200.0, 215.0, 255.0, 260.0, 160.0, 400.0, 120.0, 120.0, 110.0),
    ),
    AlphaProfile(
        "CH-->Dry 1",
        196.71063725,
        (500.0, 1500.0, 350.0, 350.0, 215.0, 255.0, 260.0, 160.0, 400.0, 120.0, 120.0, 110.0),
    ),
    AlphaProfile(
        "CH-->Dry 2",
        218.13211325,
        (500.0, 1500.0, 350.0, 350.0, 215.0, 255.0, 260.0, 260.0, 400.0, 260.0, 260.0, 110.0),
    ),
    AlphaProfile(
        "CH-->Dry 3",
        238.83954005,
        (500.0, 1500.0, 350.0, 350.0, 215.0, 255.0, 350.0, 350.0, 400.0, 350.0, 350.0, 110.0),
    ),
    AlphaProfile(
        "CH-->Dry 4",
        266.92547525,
        (500.0, 1500.0, 350.0, 350.0, 215.0, 255.0, 350.0, 350.0, 400.0, 350.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "CH-->Dry 5",
        294.941989,
        (500.0, 1500.0, 350.0, 350.0, 350.0, 350.0, 350.0, 350.0, 400.0, 350.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "Dry",
        301.289093,
        (500.0, 1500.0, 350.0, 350.0, 350.0, 350.0, 350.0, 350.0, 700.0, 700.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "Normal-Dry",
        365.2560005,
        (500.0, 1500.0, 2500.0, 350.0, 350.0, 350.0, 350.0, 350.0, 700.0, 700.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "Normal-Wet",
        473.850983,
        (500.0, 1500.0, 2500.0, 4000.0, 350.0, 350.0, 350.0, 350.0, 700.0, 700.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "N-Wet (+)",
        563.00000,
        (500.0, 1500.0, 2500.0, 4000.0, 1086.8169, 350.0, 350.0, 350.0, 700.0, 700.0, 350.0, 350.0),
    ),
    AlphaProfile(
        "Wet",
        673.4872385,
        (500.0, 1500.0, 2500.0, 4000.0, 2000.0, 350.0, 350.0, 350.0, 700.0, 700.0, 350.0, 350.0),
    ),
)


# April monthly total uses 15 + 15 days, but Final FNA pulse split uses 14 / 16.
# November is split 6 + 4 + 20 days.


# -----------------------------------------------------------------------------
# Text / DSS helpers
# -----------------------------------------------------------------------------
def clean_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def norm_token(value: object) -> str:
    return clean_text(value).upper()


def read_calsim_monthly_pairs(
    dssfile: str | Path,
    specs: list[tuple[str, str]],
    dss_read_start: str = DEFAULT_DSS_READ_START,
    dss_read_end: str = DEFAULT_DSS_READ_END,
) -> dict[tuple[str, str], pd.Series]:
    """
    Read multiple CalSim monthly DSS series keyed by (B-part, C-part).
    Matching is case-insensitive on pathname B and C parts. All monthly paths
    matching a requested (B, C) pair are stitched together by updating a common
    monthly index.
    """
    requested = {
        (norm_token(b), norm_token(c))
        for b, c in specs
        if clean_text(b) and clean_text(c)
    }
    if not requested:
        return {}

    # Direct open (no junction; catalog_flag=True) + the shared faithful read
    # loop in utils.dss_io. dss_io.read_monthly_series is a byte-equivalent
    # copy of the prior inline loop: same "/*/*/*/*/1MON/*" catalog query,
    # same case-insensitive (B, C) bucketing, same (D-part, path) sort,
    # same -900 sentinel and end-of-month index shift, same master.update
    # stitch onto a fixed month-end index.
    with dss_io.open_dss(str(dssfile), version=6, catalog_flag=True,
                         use_junction=False) as dss:
        return dss_io.read_monthly_series(
            dss, requested, dss_read_start, dss_read_end)


# -----------------------------------------------------------------------------
# Inflow input helpers
# -----------------------------------------------------------------------------
def water_year(dt: pd.Timestamp) -> int:
    return int(dt.year + 1) if dt.month >= 10 else int(dt.year)


def restoration_year_for_month(dt: pd.Timestamp) -> int:
    """
    Calendar month -> Restoration Year identifier.
    Mar-Dec belong to their calendar year restoration year.
    Jan-Feb belong to the previous restoration year.
    """
    return int(dt.year) if dt.month >= 3 else int(dt.year - 1)


def read_unimp_csv(path: str | Path) -> pd.Series:
    """Read UNIMP_SJ monthly flow from a rim-inflow output CSV.

    Supports two formats:
    - Product A (CalSim format): columns ``Part B``, ``Year``, ``Month``, ``Value``
    - Product B (qmap format):   columns ``CalSim``, ``Year``, ``Month``, ``qmap_postAdj``
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_csv(path)

    # Detect format and normalise to common column names
    if "Part B" in df.columns:
        # Product A CalSim format
        name_col, val_col = "Part B", "Value"
    elif "CalSim" in df.columns:
        # Product B qmap format
        name_col, val_col = "CalSim", "qmap_postAdj"
    else:
        raise ValueError(
            f"{path} has neither 'Part B' nor 'CalSim' column. "
            f"Found: {sorted(df.columns)}"
        )

    for req in (name_col, val_col, "Year", "Month"):
        if req not in df.columns:
            raise ValueError(f"{path} is missing required column: {req}")

    df = df.copy()
    if df[name_col].astype(str).str.upper().nunique() > 1:
        df = df[df[name_col].astype(str).str.upper() == "UNIMP_SJ"]
    dates = pd.to_datetime(
        {"year": df["Year"].astype(int), "month": df["Month"].astype(int), "day": 1}
    ) + pd.offsets.MonthEnd(0)
    series = pd.Series(df[val_col].astype(float).to_numpy(), index=dates).sort_index()
    series.name = "UNIMP_SJ"
    return series


def build_water_year_totals(monthly_unimp_sj: pd.Series) -> pd.Series:
    df = monthly_unimp_sj.rename("value").to_frame()
    df["wy"] = [water_year(ts) for ts in df.index]
    grouped = df.groupby("wy")["value"]
    counts = grouped.count()
    wy_totals = grouped.sum().sort_index()
    # Edge years in the provided csv may be partial. Keep only complete Oct-Sep years.
    wy_totals = wy_totals[counts == 12]
    wy_totals.name = "WY_UNIMP_SJ_TAF"
    if wy_totals.empty:
        raise ValueError("No complete Oct-Sep water years were found in UNIMP_SJ input")
    return wy_totals


# -----------------------------------------------------------------------------
# schedule logic 
# -----------------------------------------------------------------------------
def linear_interp(x: float, x0: float, y0: float, x1: float, y1: float) -> float:
    if math.isclose(x1, x0, abs_tol=1e-12):
        return y0
    return y0 + (x - x0) * (y1 - y0) / (x1 - x0)


def annual_release_from_runoff(runoff_taf: float) -> float:
    """
    < 400 TAF -> 116.9 (Critical-Low)
    400-670 -> 187.8 (Critical-High) - flat, a discontinuity
    670-930 -> interpolate between Dry (272.3) and Normal-Dry (330.3)
    930-1450 -> interpolate between Normal-Dry and Normal-Wet (400.3)
    1450-2500 -> interpolate between Normal-Wet and N-Wet+ (547.4)
    >= 2500 -> 673.5 (Wet) - another flat discontinuity
    """
    r = float(runoff_taf)
    if r < 400.0:
        return CRITICAL_LOW_RELEASE
    if r < 670.0:
        return CRITICAL_HIGH_RELEASE
    if r < 930.0:
        return linear_interp(r, 670.0, DRY_LOWER_RELEASE, 930.0, NORMAL_DRY_RELEASE)
    if r < 1450.0:
        return linear_interp(r, 930.0, NORMAL_DRY_RELEASE, 1450.0, NORMAL_WET_RELEASE)
    if r < 2500.0:
        return linear_interp(r, 1450.0, NORMAL_WET_RELEASE, 2500.0, NWET_PLUS_RELEASE)
    return WET_RELEASE


def alpha_blocks_from_annual_release(annual_release_taf: float) -> np.ndarray:
    """Interpolate between alpha profiles based on annual release."""
    r = float(annual_release_taf)
    profiles = ALPHA_PROFILES
    if r <= profiles[0].annual_release_taf:
        return np.array(profiles[0].cfs_blocks, dtype=float)
    if r >= profiles[-1].annual_release_taf:
        return np.array(profiles[-1].cfs_blocks, dtype=float)

    for lo, hi in zip(profiles[:-1], profiles[1:]):
        if lo.annual_release_taf <= r <= hi.annual_release_taf:
            lo_arr = np.array(lo.cfs_blocks, dtype=float)
            hi_arr = np.array(hi.cfs_blocks, dtype=float)
            ratio = (r - lo.annual_release_taf) / (hi.annual_release_taf - lo.annual_release_taf)
            return lo_arr + ratio * (hi_arr - lo_arr)

    raise RuntimeError(f"Could not bracket annual release {r}")


def schedule_out_monthly_taf(blocks: np.ndarray, year: int) -> dict[pd.Timestamp, float]:
    """
    Converts the 12 cfs blocks into 12 monthly TAF totals for a given restoration year.
    The `year` argument is the Restoration Year label: Mar-Dec use that CY; Jan-Feb use CY+1.
    """
    feb_year = year + 1
    feb_days = 29 if pd.Timestamp(feb_year, 2, 1).is_leap_year else 28

    totals = {
        pd.Timestamp(year, 3, 31): (blocks[0] * 15 + blocks[1] * 16) * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 4, 30): (blocks[2] * 15 + blocks[3] * 15) * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 5, 31): blocks[4] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 6, 30): blocks[4] * 30 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 7, 31): blocks[5] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 8, 31): blocks[5] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 9, 30): blocks[6] * 30 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 10, 31): blocks[7] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 11, 30): (blocks[8] * 6 + blocks[9] * 4 + blocks[10] * 20) * CFS_DAY_TO_TAF,
        pd.Timestamp(year, 12, 31): blocks[10] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year + 1, 1, 31): blocks[11] * 31 * CFS_DAY_TO_TAF,
        pd.Timestamp(year + 1, 2, feb_days): blocks[11] * feb_days * CFS_DAY_TO_TAF,
    }
    return totals


def final_fna_monthly_np_p(blocks: np.ndarray, dt: pd.Timestamp) -> tuple[float, float]:
    """
    Compute monthly NP/P CalSim inputs directly from alpha blocks.
    Returns (NP_taf, P_taf) after rounding cfs to integer.
    """
    month = int(dt.month)
    days = int(dt.day)  # month-end timestamp

    if month == 4:
        # April: pulse from block 3 over 16 days, non-pulse is residual
        total_taf = (blocks[2] * 15 + blocks[3] * 15) * CFS_DAY_TO_TAF
        p_taf = round(blocks[3]) * APRIL_PULSE_DAYS * CFS_DAY_TO_TAF
        np_taf = total_taf - p_taf
        return float(np_taf), float(p_taf)

    if month == 3:
        np_cfs = round((blocks[0] * 15 + blocks[1] * 16) / 31)
    elif month == 11:
        np_cfs = round((blocks[8] * 6 + blocks[9] * 4 + blocks[10] * 20) / 30)
    elif month in (5, 6):
        np_cfs = round(blocks[4])
    elif month in (7, 8):
        np_cfs = round(blocks[5])
    elif month == 9:
        np_cfs = round(blocks[6])
    elif month == 10:
        np_cfs = round(blocks[7])
    elif month == 12:
        np_cfs = round(blocks[10])
    else:  # Jan, Feb
        np_cfs = round(blocks[11])

    np_taf = np_cfs * days * CFS_DAY_TO_TAF
    return float(np_taf), 0.0


def reconstruct_rest_req(
    monthly_unimp_sj: pd.Series,
) -> pd.DataFrame:
    """
    Reconstruct monthly REST_REQ_NP and REST_REQ_P from a monthly UNIMP_SJ series.

    Restoration years whose water year is incomplete in the input data are
    skipped.  Callers should fill those leading-edge months from the default
    CalSim DSS values (see ``get_default_calsim_rest_req``).
    """
    monthly_unimp_sj = monthly_unimp_sj.sort_index().astype(float)
    if not isinstance(monthly_unimp_sj.index, pd.DatetimeIndex):
        raise TypeError("monthly_unimp_sj must have a DatetimeIndex")
    if not all(ts.is_month_end for ts in monthly_unimp_sj.index):
        raise ValueError("monthly_unimp_sj index must be month-end timestamps")

    wy_totals = build_water_year_totals(monthly_unimp_sj)
    restoration_years = sorted({restoration_year_for_month(ts) for ts in monthly_unimp_sj.index})

    schedule_cache: dict[int, tuple[float, np.ndarray, dict[pd.Timestamp, float]]] = {}
    for ry in restoration_years:
        if ry not in wy_totals.index:
            continue
        annual_release = annual_release_from_runoff(float(wy_totals.loc[ry]))
        alpha_blocks = alpha_blocks_from_annual_release(annual_release)
        monthly_totals = schedule_out_monthly_taf(alpha_blocks, ry)
        schedule_cache[ry] = (annual_release, alpha_blocks, monthly_totals)

    out_rows: list[dict[str, object]] = []
    for dt, inflow in monthly_unimp_sj.items():
        ry = restoration_year_for_month(dt)
        if ry not in schedule_cache:
            # Not enough months exist to form the required Oct-Sep water year.
            continue
        annual_release, alpha_blocks, monthly_totals = schedule_cache[ry]
        total_taf = monthly_totals[dt]
        np_taf, p_taf = final_fna_monthly_np_p(alpha_blocks, dt)
        out_rows.append(
            {
                "Date": dt,
                "UNIMP_SJ": float(inflow),
                "restoration_year": ry,
                "wy_total_unimp_sj": float(wy_totals.loc[ry]),
                "annual_release_taf": float(annual_release),
                "schedule_total_taf": float(total_taf),
                "reconstructed_REST_REQ_NP": float(np_taf),
                "reconstructed_REST_REQ_P": float(p_taf),
            }
        )

    df = pd.DataFrame(out_rows).set_index("Date").sort_index()
    return df


# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------
def to_output_format(series: pd.Series, part_b: str, part_c: str) -> pd.DataFrame:
    df = series.rename("Value").to_frame()
    df["Year"] = df.index.year
    df["Month"] = df.index.month
    df.insert(0, "Part C", part_c)
    df.insert(0, "Part B", part_b)
    return df[["Part B", "Part C", "Year", "Month", "Value"]].reset_index(drop=True)



# -----------------------------------------------------------------------------
# Main orchestration
# -----------------------------------------------------------------------------
def get_default_calsim_rest_req(
    dssfile: Path = DSS_FILE,
    pulse_bpart: str = "REST_REQ_P",
    nonpulse_bpart: str = "REST_REQ_NP",
    part_c: str = "RELEASE-HYDROGRAPH",
) -> dict[str, pd.Series]:
    """Read default CalSim REST_REQ_NP and REST_REQ_P from DSS.

    Used for leading-edge months (e.g. Oct 1971-Feb 1972 for Product A,
    Oct 1921-Feb 1922 for Product B) where the input UNIMP_SJ data does
    not cover a complete water year needed for reconstruction.
    """
    series_map = read_calsim_monthly_pairs(
        dssfile,
        [(nonpulse_bpart, part_c), (pulse_bpart, part_c)],
    )
    return {
        nonpulse_bpart: series_map.get(
            (norm_token(nonpulse_bpart), norm_token(part_c)),
            pd.Series(dtype=float),
        ),
        pulse_bpart: series_map.get(
            (norm_token(pulse_bpart), norm_token(part_c)),
            pd.Series(dtype=float),
        ),
    }


def build_historical_comparison(
    dssfile: Path,
    outdir: Path,
    pulse_bpart: str,
    nonpulse_bpart: str,
    part_c: str,
    unimp_bpart: str = "UNIMP_SJ",
) -> Path:
    specs = [
        (unimp_bpart, "FLOW-UNIMPAIRED"),
        (pulse_bpart, part_c),
        (nonpulse_bpart, part_c),
    ]
    series_map = read_calsim_monthly_pairs(dssfile, specs)

    unimp_key = (norm_token(unimp_bpart), "FLOW-UNIMPAIRED")
    if unimp_key not in series_map:
        found = sorted(set(f"{b}/{c}" for b, c in series_map))
        raise KeyError(
            f"Could not find {unimp_bpart}/FLOW-UNIMPAIRED in DSS.\n"
            f"Available B/C pairs: {found[:20]}{'...' if len(found) > 20 else ''}"
        )
    unimp_sj = series_map[unimp_key]

    p_key = (norm_token(pulse_bpart), norm_token(part_c))
    np_key = (norm_token(nonpulse_bpart), norm_token(part_c))
    actual_p = series_map.get(p_key, pd.Series(dtype=float))
    actual_np = series_map.get(np_key, pd.Series(dtype=float))

    recon = reconstruct_rest_req(unimp_sj.dropna())
    comp = recon[["UNIMP_SJ", "reconstructed_REST_REQ_P", "reconstructed_REST_REQ_NP"]].copy()
    comp = comp.rename(columns={"UNIMP_SJ": "actual_UNIMP_SJ"})
    comp["actual_REST_REQ_P"] = actual_p.reindex(comp.index)
    comp["actual_REST_REQ_NP"] = actual_np.reindex(comp.index)
    comp = comp[
        [
            "actual_UNIMP_SJ",
            "actual_REST_REQ_P",
            "reconstructed_REST_REQ_P",
            "actual_REST_REQ_NP",
            "reconstructed_REST_REQ_NP",
        ]
    ]
    comp = comp[comp.index >= "1921-10-31"]
    comp = comp.reset_index().rename(columns={"index": "Date"})
    comp["Date"] = pd.to_datetime(comp["Date"]).dt.strftime("%Y-%m-%d")

    outdir.mkdir(parents=True, exist_ok=True)
    outpath = outdir / "actual_vs_reconstructed.csv"
    comp.to_csv(outpath, index=False)
    return outpath


def _fill_leading_edge(
    inflow_index: pd.DatetimeIndex,
    recon: pd.DataFrame,
    default_rest_req: dict[str, pd.Series] | None,
    pulse_bpart: str,
    nonpulse_bpart: str,
) -> tuple[pd.Series, pd.Series]:
    """Return (np_series, p_series) with leading-edge months filled from DSS defaults."""
    np_series = recon["reconstructed_REST_REQ_NP"]
    p_series = recon["reconstructed_REST_REQ_P"]
    if default_rest_req is not None:
        missing = inflow_index.difference(recon.index)
        if not missing.empty:
            dss_np = default_rest_req.get(nonpulse_bpart, pd.Series(dtype=float))
            dss_p = default_rest_req.get(pulse_bpart, pd.Series(dtype=float))
            np_series = pd.concat([dss_np.reindex(missing).dropna(), np_series]).sort_index()
            p_series = pd.concat([dss_p.reindex(missing).dropna(), p_series]).sort_index()
    return np_series, p_series


def run_product_a(
    product_a_csv: Path,
    outdir: Path,
    pulse_bpart: str,
    nonpulse_bpart: str,
    part_c: str,
    default_rest_req: dict[str, pd.Series] | None = None,
) -> list[Path]:
    inflow = read_unimp_csv(product_a_csv)
    recon = reconstruct_rest_req(inflow)
    np_series, p_series = _fill_leading_edge(
        inflow.index, recon, default_rest_req, pulse_bpart, nonpulse_bpart,
    )
    outdir.mkdir(parents=True, exist_ok=True)
    pulse_path = outdir / "_SJRRPreqPulse_productA_1972_2018.csv"
    np_path = outdir / "_SJRRPreqNonPulse_productA_1972_2018.csv"
    to_output_format(p_series, pulse_bpart, part_c).to_csv(pulse_path, index=False)
    to_output_format(np_series, nonpulse_bpart, part_c).to_csv(np_path, index=False)
    return [pulse_path, np_path]


def infer_b_suffix(path: Path) -> str:
    match = re.search(r"_n(\d{2})\.csv$", path.name, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Could not infer n## suffix from {path.name}")
    return f"n{match.group(1)}"


def run_product_b(
    product_b_dir: Path,
    outdir: Path,
    pulse_bpart: str,
    nonpulse_bpart: str,
    part_c: str,
    default_rest_req: dict[str, pd.Series] | None = None,
) -> list[Path]:
    if product_b_dir.is_file():
        files = [product_b_dir]
    else:
        files = sorted(product_b_dir.glob("UNIMP_SJ_qmo_n*.csv"))
    if not files:
        raise FileNotFoundError(f"No product B files found in {product_b_dir}")

    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for f in files:
        suffix = infer_b_suffix(f)
        inflow = read_unimp_csv(f)
        recon = reconstruct_rest_req(inflow)
        np_series, p_series = _fill_leading_edge(
            inflow.index, recon, default_rest_req, pulse_bpart, nonpulse_bpart,
        )
        pulse_path = outdir / f"_SJRRPreqPulse_productB_qmo_{suffix}.csv"
        np_path = outdir / f"_SJRRPreqNonPulse_productB_qmo_{suffix}.csv"
        to_output_format(p_series, pulse_bpart, part_c).to_csv(pulse_path, index=False)
        to_output_format(np_series, nonpulse_bpart, part_c).to_csv(np_path, index=False)
        written.extend([pulse_path, np_path])
    return written


if __name__ == "__main__":
    written: list[Path] = []

    # Read default CalSim REST_REQ values once - used for leading-edge months
    # (e.g. Oct 1971-Feb 1972, Oct 1921-Feb 1922) that lack complete WY data
    # for reconstruction.
    default_rest_req = get_default_calsim_rest_req(dssfile=DSS_FILE)

    written.append(
        build_historical_comparison(
            dssfile=DSS_FILE,
            outdir=DEFAULT_OUT_HIST,
            pulse_bpart="REST_REQ_P",
            nonpulse_bpart="REST_REQ_NP",
            part_c="RELEASE-HYDROGRAPH",
        )
    )

    written.extend(
        run_product_a(
            product_a_csv=DEFAULT_PRODUCT_A,
            outdir=DEFAULT_OUT_A,
            pulse_bpart="REST_REQ_P",
            nonpulse_bpart="REST_REQ_NP",
            part_c="RELEASE-HYDROGRAPH",
            default_rest_req=default_rest_req,
        )
    )

    written.extend(
        run_product_b(
            product_b_dir=DEFAULT_PRODUCT_B_DIR,
            outdir=DEFAULT_OUT_B,
            pulse_bpart="REST_REQ_P",
            nonpulse_bpart="REST_REQ_NP",
            part_c="RELEASE-HYDROGRAPH",
            default_rest_req=default_rest_req,
        )
    )

    print("Created files:")
    for path in written:
        print(path)
