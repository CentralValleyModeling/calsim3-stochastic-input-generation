"""
Fit window and predictor sources of the quantile maps driven by the rim-inflow model
====================================================================================
Shared by ``utils.qmap_product_a_from_pairs``, ``utils.qmap_product_b_from_pairs`` (the
``qmap_pairs.csv`` and hybrid-term pairs) and ``mod_hydrology/rim_inflow/_1_build_rim_inflow.py``.

Every fit uses WY1950-2018 (``FIT_WY``). Each pair names its fit in a ``fit`` column:

- ``pass``   : fit the CalSim3 predictor to the CalSim3 target and apply the map to the model's
               predictor. The term carries the model's error, like its predictor.
- ``absorb`` : fit the model's historical-unsplit predictor (``get_rim_inflow_outputs(
               "historical")``) to the CalSim3 target and apply the map to the model's
               predictor. The map absorbs the model's bias and the term keeps CalSim3's level.
               For a term tied to its predictor only statistically. Never fitted on Product A:
               its weather is detrended, so the fit would read the warming as model error.

A predictor may be a sum of rim-inflow SVs, written ``I_DER001+I_DER004+I_SCOTF+I_SFD003``. It
is summed on both sides: the CalSim3 series for a pass fit, the model's series for an absorb
fit and for the series the map is applied to.
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

from utils.paths import get_rim_inflow_outputs, require_pinned_run

FITS = ("pass", "absorb")
FIT_WY = (1950, 2018)
FIT_START = f"{FIT_WY[0] - 1}-10-01"
FIT_END = f"{FIT_WY[1]}-09-30"


def predictor_parts(part_b: str) -> list[str]:
    """The rim-inflow SVs a predictor sums: ``"I_DER001+I_DER004"`` -> ``["I_DER001", "I_DER004"]``."""
    return [p.strip() for p in str(part_b).split("+") if p.strip()]


def predictor_label(part_b: str) -> str:
    """Short console label for a predictor: the name, or the first part and the count of a sum."""
    parts = predictor_parts(part_b)
    return parts[0] if len(parts) == 1 else f"{parts[0]}+...({len(parts)} SVs)"


def read_fit_column(df: pd.DataFrame, csv_name: str) -> pd.Series:
    """The ``fit`` column of a pairs or hybrid-term CSV, lower-cased; every row must be pass or absorb."""
    if "fit" not in df.columns:
        raise KeyError(f"{csv_name}: no 'fit' column; give each pair {' or '.join(FITS)}")
    fit = df["fit"].fillna("").astype(str).str.strip().str.lower()
    bad = df.loc[~fit.isin(FITS)]
    if not bad.empty:
        raise ValueError(f"{csv_name}: fit must be {' or '.join(FITS)}; rows {bad.index.tolist()} "
                         f"have {sorted(set(df.loc[bad.index, 'fit'].astype(str)))}")
    return fit


def sum_parts(parts: list[str], get: Callable[[str], pd.Series | None]) -> pd.Series | None:
    """Sum of ``get(part)`` over ``parts`` on their common months; None if any part has no data."""
    series = []
    for p in parts:
        s = get(p)
        if s is None or s.dropna().empty:
            return None
        series.append(s)
    total = series[0]
    for s in series[1:]:
        total = total.add(s)          # NaN where any part is missing
    return total.dropna().rename("+".join(parts))


def read_historical_predictors(parts) -> dict[str, pd.Series]:
    """The model's historical-unsplit series of ``parts``, month-end indexed (absorb fits). Only
    a historical run of the configured model at the pinned commit is read, so a map is never
    fitted on one model and applied to another."""
    out_files = get_rim_inflow_outputs("historical")
    path = out_files["ts"]
    if not path.exists():
        raise FileNotFoundError(
            f"absorb fits read the historical rim-inflow run, which is missing: {path}\n"
            "Run: python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product historical")
    require_pinned_run(out_files["dir"])
    ts = pd.read_csv(path)
    ts = ts[ts["CalSim"].isin(set(parts))]
    out = {}
    for name, g in ts.groupby("CalSim"):
        dates = (pd.to_datetime(pd.DataFrame({"year": g["Year"], "month": g["Month"], "day": 1}))
                 + pd.offsets.MonthEnd(0))
        out[name] = pd.Series(g["qmap_postAdj"].to_numpy(float), index=dates.to_numpy()).sort_index()
    return out


def training_basis(fit: str, parts: list[str], part_c: str,
                   calsim3: dict, historical: dict) -> pd.Series | None:
    """The predictor series a pair is fitted on, summed over ``parts``: CalSim3 for a pass fit
    (``calsim3`` keyed by upper-case (Part B, Part C)), the model's historical-unsplit run for an
    absorb fit (``historical`` from :func:`read_historical_predictors`). None if a part is missing."""
    if fit == "pass":
        return sum_parts(parts, lambda p: calsim3.get((p.upper(), part_c.upper())))
    return sum_parts(parts, historical.get)
