"""
Historical vs Modified Historical Postprocessing
================================================
Thin wrapper around the Product A postprocessing engine
(``_productA_postproc.run_post_processing_package``). Only the input pickle
dir, output dir, and default WY periods differ.

Inputs
------
- Pickle cache: ``GENERATED/postprocessing/calsim_runs/historical_modified/
  pickle_files/`` (values.pkl, diffs.pkl, units.pkl, fields.pkl)

Outputs
-------
- ``GENERATED/postprocessing/calsim_runs/historical_modified/output/``
  - ``annual_WY_summary.xlsx``
  - ``figures/<period>/<metric>.png`` (monthly time series + non-exceedance CDF)

Dependencies
------------
- ``_productA_postproc.run_post_processing_package`` (same module dir)
- utils.paths
- utils.validation_plots (transitive, via _productA_postproc)
- pandas, openpyxl

Usage
-----
    python postprocessing/calsim_runs/_historical_modified_postproc.py
    python postprocessing/calsim_runs/_historical_modified_postproc.py --skip-drought
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(RUN_DIR))

from utils.paths import get_generated_dir
from _productA_postproc import Period, run_post_processing_package


# -----------------------------
# Defaults (resolved via utils.paths so config.json is honored)
# -----------------------------
PICKLE_DIR = (
    get_generated_dir()
    / "postprocessing" / "calsim_runs"
    / "historical_modified" / "pickle_files"
)

OUT_DIR = (
    get_generated_dir()
    / "postprocessing" / "calsim_runs"
    / "historical_modified" / "output"
)


FULL_WY1922_2021 = Period(
    name="Full_WY1922_2021",
    start=pd.Timestamp("1921-10-01"),
    end=pd.Timestamp("2021-09-30"),
    wy_start=1922,
    wy_end=2021,
)

DROUGHT_WY1987_1992 = Period(
    name="Drought_WY1987_1992",
    start=pd.Timestamp("1986-10-01"),
    end=pd.Timestamp("1992-09-30"),
    wy_start=1987,
    wy_end=1992,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Postprocess the Historical vs Modified Historical pickle cache."
    )
    parser.add_argument("--pickle-dir", default=str(PICKLE_DIR),
                        help="Directory containing values.pkl, diffs.pkl, units.pkl, fields.pkl.")
    parser.add_argument("--baseline-name", default="Historical",
                        help="Baseline scenario name, must exist in values.pkl.")
    parser.add_argument("--out-dir", default=str(OUT_DIR),
                        help="Directory to write annual_WY_summary.xlsx and figures/.")
    parser.add_argument("--skip-drought", action="store_true",
                        help="If set, skip the Drought_WY1987_1992 period.")

    args = parser.parse_args()

    pickle_dir = Path(args.pickle_dir)
    if not pickle_dir.is_dir():
        raise FileNotFoundError(f"Pickle directory not found: {pickle_dir}")

    periods = [FULL_WY1922_2021]
    if not args.skip_drought:
        periods.append(DROUGHT_WY1987_1992)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs = run_post_processing_package(
        pickle_dir=str(pickle_dir),
        baseline_name=args.baseline_name,
        out_dir=str(out_dir),
        periods=periods,
    )

    print("Post-processing complete:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
