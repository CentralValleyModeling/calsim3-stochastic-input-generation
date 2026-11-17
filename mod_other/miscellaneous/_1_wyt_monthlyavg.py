"""
Miscellaneous Terms - WYT Monthly-Average Reconstruction
========================================================
Each term of reference/wyt_avg_terms.csv as its CalSim3 baseline mean by water year type
(W/AN/BN/D/C) and month, applied to the Sacramento or San Joaquin year types of the weather set
(utils.wyt_monthlyavg_framework). Every run also writes the pattern and its check on the CalSim3
year types.

The terms include the rim-inflow SV I_JBP006 (James Bypass inflow): the San Joaquin year types it
needs come from the rim inflows, so mod_hydrology/rim_inflow cannot build it.

Inputs
------
- reference/wyt_avg_terms.csv: term_part_b, term_part_c, basin_wyt (sac or sj)
- <base>/CalSim3/__calsim_sv_default__.dss: the terms, Oct 1921 - Sep 2021
- mod_hydrology/water_year_types/reference/_Historical_SacWYT.csv, _Historical_SJWYT.csv
- <generated>/mod_hydrology/water_year_types/output/_1_calc_WYTs/<set name>/: _SacWYT.csv and
  _SJWYT.csv, or _SacWYT_n01.csv ... _n10.csv and _SJWYT_n01.csv ... _n10.csv for Product_B

Outputs
-------
Under <generated>/mod_other/miscellaneous/output/:
- _1_wyt_monthlyavg/monthly_avg_historical/miscellaneous_pattern_by_WYT_month.csv and
  miscellaneous_actual_vs_reconstructed.csv
- _1_wyt_monthlyavg/figures/historical/<Part B>.png and <Part B>_monthly_error.png: baseline vs
  the reconstruction on the CalSim3 year types, WY1972-2018
- _1_wyt_monthlyavg/figures/<historical_unsplit|product_a>/<Part B>.png and
  <Part B>_monthly_error.png: the set vs the baseline, WY1922-2018
- _historical_unsplit_validation/<Part B>_historicalUnsplit_1922_2018.csv,
  _product_a_validation/<Part B>_productA_1922_2018.csv
- _product_b_final/<Part B>_product_b_n01.csv ... _n10.csv (--product B)

Delivery and chunk CSVs: Part B, Part C, Year, Month, Value.

Dependencies
------------
utils.paths, utils.csv_io, utils.wgen_calendar, utils.wyt_monthlyavg_framework (utils.dss_io,
utils.validation_plots); pydsstools

Usage
-----
    python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product historical
    python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product A
    python mod_other/miscellaneous/_1_wyt_monthlyavg.py --product B
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import WEATHER_SETS, delivery_dir, get_base_dir, get_module_generated_dir
from utils.csv_io import write_delivery_csv
from utils.wgen_calendar import write_chunk_csvs
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets, product_b_target_table, plot_wyt_hist_validation, plot_actual_vs_recon_validation, target_sv


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/miscellaneous")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# -- CONFIG -----------------------------------------------------------
dss_file = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
terms_csv = str(_SCRIPT_DIR / "reference" / "wyt_avg_terms.csv")

# Historical DSS date window used to build the monthly index.
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"

# Output prefix for filenames.
OUTPUT_PREFIX = "miscellaneous"

# The term spec CSV sets the WYT basin of each term.
# Required columns in wyt_avg_terms.csv:
#   - term_part_b
#   - term_part_c
#   - basin_wyt    (sj or sac; can vary by term)

# Where the historical WYT CSVs live
wyt_hist_dir = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# -- RESULTS ROOT ------------------------------------------------------
BASE_RESULTS_DIR = _gen / "output"/"_1_wyt_monthlyavg"
PRODUCT_B_DIR = _gen / "output" / "_product_b_final"


def _write_targets(product_key: str, prefix: str, targets) -> None:
    """Write final SV-format CSVs (Part B, Part C, Year, Month, Value)."""
    print(f"\n{WEATHER_SETS[product_key]['name']} targets:")

    if product_key == "B":
        for part_b, grp in product_b_target_table(targets).groupby("Part B"):
            for out in write_chunk_csvs(grp, PRODUCT_B_DIR, f"{part_b}_product_b"):
                print(f"  - {out}")

    else:
        for name, df in targets.items():
            for part_b, grp in target_sv(df).groupby("Part B"):
                out = write_delivery_csv(grp, delivery_dir(_gen / "output", product_key), part_b, product_key)
                print(f"  - {out}")



def main() -> None:
    ap = argparse.ArgumentParser(
        description="Miscellaneous terms via WYT monthly-average reconstruction.")
    ap.add_argument("--product", choices=list(WEATHER_SETS), required=True,
                    help='Weather set: historical (Historical_Unsplit), A or B')
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

    figures_dir = BASE_RESULTS_DIR / "figures" / "historical"
    plot_wyt_hist_validation(hist_cmp_df, term_specs, figures_dir)

    print("\nHistorical outputs:")
    print(f"  - {pattern_path}")
    print(f"  - {hist_cmp_path}")
    print(f"  - {figures_dir}/ (TS+CDF per term)")

    # Compute and write targets per product
    for prod_key in products:
        print(f"\n{'='*60}\nComputing {WEATHER_SETS[prod_key]['name']} targets\n{'='*60}")
        wyt_product_dir = str(
            _wyt_gen / "output" / "_1_calc_WYTs" / WEATHER_SETS[prod_key]["name"]
        )
        targets = compute_product_targets(
            product=prod_key,
            wyt_target_dir=wyt_product_dir,
            pat_wide=pat_wide,
            term_specs=term_specs,
        )
        _write_targets(prod_key, prefix, targets)

        if prod_key != "B":
            fig_dir = BASE_RESULTS_DIR / "figures" / WEATHER_SETS[prod_key]["slug"]
            plot_actual_vs_recon_validation(targets[prod_key], hist_cmp_df, term_specs, fig_dir,
                                            label=WEATHER_SETS[prod_key]["label"])
            print(f"  - {fig_dir}/ (TS+CDF per term)")


if __name__ == "__main__":
    main()
