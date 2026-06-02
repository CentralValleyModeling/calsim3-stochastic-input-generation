"""
Upper-Watershed Terms - WYT Monthly-Average Reconstruction
==========================================================
Runner that defines the upper-watershed term specs, calls the shared WYT
monthly-average framework, and writes the Product A / Product B outputs.

Inputs
------
- CalSim baseline DSS (historical term series)
- reference/wyt_avg_terms.csv (term specs + WYT basin per term)
- water_year_types WYT indices (Product A / Product B)

Outputs
-------
- <generated>/output/_1_wyt_monthlyavg/monthly_avg_historical/
    pattern CSV, actual-vs-reconstructed CSV, and figures/ (TS+CDF +
    monthly residual box per term)
- <generated>/output/_1_wyt_monthlyavg/product_a/figures/
    TS+CDF and monthly residual box per term (--product A)
- <generated>/output/_product_a_validation/
    final Product A SV CSVs (--product A)
- <generated>/output/_product_b_final/
    final Product B per-chunk SV CSVs (--product B)

Dependencies
------------
- utils/wyt_monthlyavg_framework.py  (WYT reconstruction engine)
- utils/validation_plots.py          (TS+CDF and monthly box helpers; transitive)
- utils/paths.py                     (data-dir resolution)

Usage
-----
    python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product A
    python mod_other/upper_watershed/_1_wyt_monthlyavg.py --product B
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets, plot_wyt_hist_validation, plot_actual_vs_recon_validation, water_year


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/upper_watershed")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# -- CONFIG -----------------------------------------------------------
dss_file = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
terms_csv = str(_SCRIPT_DIR / "reference" / "wyt_avg_terms.csv")

# Historical DSS date window used to build the monthly index.
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"

# Output prefix for filenames.
OUTPUT_PREFIX = "upper_watershed"

# The term spec CSV now controls the WYT basin for each term.
# Required columns in wyt_avg_terms.csv:
#   - term_part_b
#   - term_part_c
#   - basin_wyt    (sj or sac; can vary by term)

_WYT_INPUT_DIRS = {"A": "Product_A", "B": "Product_B"}

# Where the historical WYT CSVs live
wyt_hist_dir = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# -- RESULTS ROOT ------------------------------------------------------
BASE_RESULTS_DIR = _gen / "output"/"_1_wyt_monthlyavg"
PRODUCT_A_DIR = _gen / "output" / "_product_a_validation"
PRODUCT_B_DIR = _gen / "output" / "_product_b_final"


def _to_sv_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert framework long-format target to Part B,Part C,Year,Month,Value."""
    out = pd.DataFrame({
        "Part B": df["part_b"],
        "Part C": df["part_c"],
        "Year": df["date"].dt.year,
        "Month": df["date"].dt.month,
        "Value": df["wyt_monthly_avg"],
    })
    return out


def _write_targets(product_key: str, prefix: str, targets) -> None:
    """Write final SV-format CSVs (Part B, Part C, Year, Month, Value)."""
    print(f"\nProduct {product_key} targets:")

    if product_key == "B":
        PRODUCT_B_DIR.mkdir(parents=True, exist_ok=True)
        for name, df in targets.items():
            sv = _to_sv_format(df)
            tag = name.replace("product_b_", "")
            for part_b, grp in sv.groupby("Part B"):
                out = PRODUCT_B_DIR / f"{part_b}_product_b_{tag}.csv"
                grp.to_csv(out, index=False)
                print(f"  - {out}")

    elif product_key == "A":
        PRODUCT_A_DIR.mkdir(parents=True, exist_ok=True)
        for name, df in targets.items():
            sv = _to_sv_format(df)
            wy_min = int(df["date"].apply(water_year).min())
            wy_max = int(df["date"].apply(water_year).max())
            for part_b, grp in sv.groupby("Part B"):
                out = PRODUCT_A_DIR / f"{part_b}_product_a_{wy_min}_{wy_max}.csv"
                grp.to_csv(out, index=False)
                print(f"  - {out}")



def main() -> None:
    ap = argparse.ArgumentParser(
        description="Upper-Watershed terms via WYT monthly-average reconstruction.")
    ap.add_argument("--product", choices=["A", "B"], required=True,
                    help='Product to generate: A (historical 1921-2018) or B (stochastic 1000-yr chunks).')
    args = ap.parse_args()

    prefix = OUTPUT_PREFIX.strip() if OUTPUT_PREFIX else Path(terms_csv).stem
    products = [args.product]

    # Read DSS and compute pattern once
    print("Reading DSS and computing historical pattern...")
    pattern_df, hist_cmp_df, pat_wide, term_specs = compute_wyt_pattern(
        term_specs_csv=terms_csv,
        historical_dssfile=dss_file,
        dss_read_start=DSS_READ_START,
        dss_read_end=DSS_READ_END,
        wyt_input_dir=wyt_hist_dir,
    )

    basin_tags = sorted({spec.wyt_tag for spec in term_specs})
    print(f"Using basin_wyt values from CSV: {', '.join(basin_tags)}")

    # Write historical outputs (same for all products)
    hist_dir = BASE_RESULTS_DIR / "monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)

    pattern_path = hist_dir / f"{prefix}_pattern_by_WYT_month.csv"
    pattern_df.to_csv(pattern_path, index=False)

    hist_cmp_path = hist_dir / f"{prefix}_actual_vs_reconstructed.csv"
    hist_cmp_df.to_csv(hist_cmp_path, index=False)

    figures_dir = hist_dir / "figures"
    plot_wyt_hist_validation(hist_cmp_df, term_specs, figures_dir)

    print("\nHistorical outputs:")
    print(f"  - {pattern_path}")
    print(f"  - {hist_cmp_path}")
    print(f"  - {figures_dir}/ (TS+CDF per term)")

    # Compute and write targets per product
    for prod_key in products:
        print(f"\n{'='*60}\nComputing Product {prod_key} targets\n{'='*60}")
        wyt_product_dir = str(
            _wyt_gen / "output" / "_1_calc_WYTs" / _WYT_INPUT_DIRS[prod_key]
        )
        targets = compute_product_targets(
            product=prod_key,
            wyt_target_dir=wyt_product_dir,
            pat_wide=pat_wide,
            term_specs=term_specs,
        )
        _write_targets(prod_key, prefix, targets)

        if prod_key == "A":
            prod_a_fig_dir = BASE_RESULTS_DIR / "product_a" / "figures"
            plot_actual_vs_recon_validation(targets["product_a"], hist_cmp_df, term_specs, prod_a_fig_dir)
            print(f"  - {prod_a_fig_dir}/ (TS+CDF per term)")


if __name__ == "__main__":
    main()
