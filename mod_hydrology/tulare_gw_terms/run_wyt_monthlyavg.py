"""Runner script: defines inputs, calls the framework, and writes outputs.

Outputs are written under:
  <generated>/output/_wyt_monthly_avg_historical
  <generated>/output/_1_wyt_monthly_avg_product_a  or  _2_wyt_monthly_avg_product_b

Framework module:
  utils/wyt_monthlyavg_framework.py
"""

from __future__ import annotations

from pathlib import Path
import sys

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_hydrology/tulare_gw_terms")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# %% ── CONFIG ───────────────────────────────────────────────────────────
dss_file     = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
terms_csv = str(_SCRIPT_DIR / "reference" / "wyt_avg_terms.csv")

# Historical DSS date window used to build the monthly index.
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"

# Output prefix for filenames.
OUTPUT_PREFIX = "tulare_gw_terms"

# Choose which WYT definition to use for averaging:
#    "sj"  -> San Joaquin WYT
#    "sac" -> Sacramento WYT
BASIN_WYT = "sj"

# Choose target WGEN product(s):
#    "both" -> run Product A then Product B (default)
#    "A"    -> one WYT series (1972–2018)
#    "B"    -> ALWAYS n01..n10; WY 1922–2021
TARGET_PRODUCT = "Both"

_WYT_INPUT_DIRS = {"A": "Product_A", "B": "Product_B"}
_OUTPUT_DIRS = {"A": "_1_wyt_monthly_avg_product_a", "B": "_2_wyt_monthly_avg_product_b"}

# Where the WYT CSVs
wyt_hist_dir = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# %% ── RESULTS ROOT ─────────────────────────────────────────────────────
BASE_RESULTS_DIR = _gen / "output"


def _write_targets(product_key: str, prefix: str, targets) -> None:
    """Write target CSVs for a single product."""
    prod_dir = BASE_RESULTS_DIR / _OUTPUT_DIRS[product_key]
    prod_dir.mkdir(parents=True, exist_ok=True)

    wrote = []
    for name, df in targets.items():
        out = prod_dir / f"{prefix}_{name}.csv"
        df.to_csv(out, index=False)
        wrote.append(out)

    print(f"\nProduct {product_key} targets:")
    for p in wrote:
        print(f"  - {p}")


def main() -> None:
    prefix = OUTPUT_PREFIX.strip() if OUTPUT_PREFIX else Path(terms_csv).stem
    choice = TARGET_PRODUCT.strip().upper()

    if choice == "BOTH":
        products = ["A", "B"]
    elif choice in ("A", "B"):
        products = [choice]
    else:
        raise ValueError(f"TARGET_PRODUCT must be 'A', 'B', or 'both', got '{TARGET_PRODUCT}'")

    # Read DSS and compute pattern once
    print("Reading DSS and computing historical pattern...")
    pattern_df, hist_cmp_df, pat_wide, term_specs, tag = compute_wyt_pattern(
        term_specs_csv=terms_csv,
        historical_dssfile=dss_file,
        dss_read_start=DSS_READ_START,
        dss_read_end=DSS_READ_END,
        basin=BASIN_WYT,
        wyt_input_dir=wyt_hist_dir,
    )

    # Write historical outputs (same for all products)
    hist_dir = BASE_RESULTS_DIR / "0_wyt_monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)

    pattern_path = hist_dir / f"{prefix}_pattern_by_WYT_month.csv"
    pattern_df.to_csv(pattern_path, index=False)

    hist_cmp_path = hist_dir / f"{prefix}_actual_vs_synthetic.csv"
    hist_cmp_df.to_csv(hist_cmp_path, index=False)

    print(f"\nHistorical outputs:")
    print(f"  - {pattern_path}")
    print(f"  - {hist_cmp_path}")

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
            tag=tag,
        )
        _write_targets(prod_key, prefix, targets)


if __name__ == "__main__":
    main()
