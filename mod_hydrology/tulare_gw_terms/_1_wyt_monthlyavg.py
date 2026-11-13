"""
Tulare Groundwater Terms - WYT Monthly-Average Reconstruction
=============================================================
Runner that defines the Tulare GW term specs, calls the shared WYT
monthly-average framework, and writes the Product A / Product B outputs.

Inputs
------
- CalSim baseline DSS (historical term series)
- reference/wyt_avg_terms.csv (term specs + WYT basin per term)
- water_year_types WYT indices of the weather set (Historical_Unsplit, Product A or Product B)

Outputs
-------
- <generated>/output/_1_wyt_monthlyavg/monthly_avg_historical/
    pattern CSV and actual-vs-reconstructed CSV
- <generated>/output/_1_wyt_monthlyavg/figures/historical/
    TS+CDF and monthly error box per term (historical method check)
- <generated>/output/_1_wyt_monthlyavg/<_historical_unsplit_validation|_product_a_validation>/
    final delivery SV CSVs (--product historical, A)
- <generated>/output/_1_wyt_monthlyavg/figures/<historical_unsplit|product_a>/
    TS+CDF and monthly error box per term (--product historical, A)
- <generated>/output/_1_wyt_monthlyavg/_product_b_final/
    final Product B per-chunk SV CSVs (--product B)

Dependencies
------------
- utils/wyt_monthlyavg_framework.py  (WYT reconstruction engine)
- utils/validation_plots.py          (TS+CDF and monthly box helpers; transitive)
- utils/paths.py                     (data-dir resolution)

Usage
-----
    python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product historical
    python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product A
    python mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py --product B
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import WEATHER_SETS, delivery_dir, get_base_dir, get_module_generated_dir
from utils.csv_io import write_delivery_csv
from utils.wgen_calendar import write_chunk_csvs
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets, plot_wyt_hist_validation, plot_actual_vs_recon_validation


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_hydrology/tulare_gw_terms")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# -- CONFIG -----------------------------------------------------------
dss_file = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
terms_csv = str(_SCRIPT_DIR / "reference" / "wyt_avg_terms.csv")

# Historical DSS date window used to build the monthly index.
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"

# Output prefix for filenames.
OUTPUT_PREFIX = "tulare_gw_terms"

# The term spec CSV now controls the WYT basin for each term.
# Required columns in wyt_avg_terms.csv:
#   - term_part_b
#   - term_part_c
#   - basin_wyt    (sj or sac; can vary by term)

# Where the historical WYT CSVs live
wyt_hist_dir = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# -- RESULTS ROOT -----------------------------------------------------
BASE_RESULTS_DIR = _gen / "output"/"_1_wyt_monthlyavg"


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


def _chunk_table(targets) -> pd.DataFrame:
    """Product B targets ({"product_b_nXX": frame}) as one SV-format table with a ``chunk``
    column, for utils.wgen_calendar.write_chunk_csvs."""
    return pd.concat([_to_sv_format(df).assign(chunk=int(name[-2:])) for name, df in targets.items()],
                     ignore_index=True)


def _write_targets(product_key: str, prefix: str, targets) -> None:
    """Write final SV-format CSVs (Part B, Part C, Year, Month, Value)."""
    print(f"\n{WEATHER_SETS[product_key]['name']} targets:")

    if product_key == "B":
        for out in write_chunk_csvs(_chunk_table(targets), BASE_RESULTS_DIR / "_product_b_final",
                                    f"{prefix}_productB_qmo"):
            print(f"  - {out}")

    else:
        val_dir = delivery_dir(BASE_RESULTS_DIR, product_key)
        for name, df in targets.items():
            print(f"  - {write_delivery_csv(_to_sv_format(df), val_dir, prefix, product_key)}")



def main() -> None:
    ap = argparse.ArgumentParser(
        description="Tulare GW terms via WYT monthly-average reconstruction.")
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
