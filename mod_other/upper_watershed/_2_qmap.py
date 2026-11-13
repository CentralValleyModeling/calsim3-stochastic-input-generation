"""
Upper Watershed Quantile Mapping
================================
Quantile-maps each target of reference/qmap_pairs.csv (C_NFA048_SV, C_SFY007_SV, C_DER001_SV)
from its rim-inflow predictor: utils.qmap_single_from_pairs for Historical_Unsplit and Product A
over WY1922-2018, utils.qmap_product_b_from_pairs for the 10 Product B chunks.

Each map is fitted on WY1950-2018 by the pair's fit (utils.qmap_fit): pass trains on the CalSim3
predictor, absorb on the rim-inflow model's Historical_Unsplit predictor; the target is CalSim3's.
A predictor written I_A+I_B is the sum of those SVs on both sides. Mapped values are clipped to
the pair's bounds.

Inputs
------
- reference/qmap_pairs.csv: target, predictor, fit, allow_negative (single series), bounds
- <base>/CalSim3/__calsim_sv_default__.dss: targets and the predictors of pass fits
- Rim-inflow SVs (utils.paths.get_rim_inflow_outputs): _riminflow_historicalUnsplit_1922_2018.csv,
  _riminflow_productA_1922_2018.csv, or <Part B>_qmo_n01.csv ... _n10.csv for Product B; the
  Historical_Unsplit calsim_qmap_validation_TS.csv for absorb fits

Outputs
-------
Under <generated>/mod_other/upper_watershed/output/:
- _2_qmap/<historical_unsplit|product_a>/<target>_qmap_validation.csv and figures/
  <target>_timeseries.png, <target>_monthly_error.png, <target>_monthly_pct_error.png
- _historical_unsplit_validation/<target>_historicalUnsplit_1922_2018.csv,
  _product_a_validation/<target>_productA_1922_2018.csv
- _2_qmap/product_b/<target>_qmap_n01.csv ... _n10.csv: Product B detail
- _product_b_final/<target>_productB_n01.csv ... _n10.csv

Delivery and chunk CSVs: Part B, Part C, Year, Month, Value.

Dependencies
------------
utils.paths, utils.qmap_single_from_pairs, utils.qmap_product_b_from_pairs (utils.qmap_fit,
utils.quantile_mapping); pydsstools

Usage
-----
    python mod_other/upper_watershed/_2_qmap.py --product historical
    python mod_other/upper_watershed/_2_qmap.py --product A
    python mod_other/upper_watershed/_2_qmap.py --product B
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import WEATHER_SETS, delivery_dir, get_base_dir, get_module_generated_dir, get_rim_inflow_outputs
from utils.qmap_single_from_pairs import run_single_qmap_from_pairs
from utils.qmap_product_b_from_pairs import (
    run_product_b_qmap_from_pairs,
    write_product_b_sv,
)

# Fallback when qmap_pairs.csv has no allow_negative column (single series only).
ALLOW_NEGATIVE = False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upper Watershed quantile mapping",
    )
    parser.add_argument(
        "--product", choices=list(WEATHER_SETS), required=True,
        help="Weather set: historical (Historical_Unsplit) or A (1922-2018), or B (10 "
             "stochastic chunks); all use the WY1950-2018 fit.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    gen = get_module_generated_dir("mod_other/upper_watershed")
    pair_csv = script_dir / "reference" / "qmap_pairs.csv"
    dss_file = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"

    if args.product != "B":
        run_single_qmap_from_pairs(
            product=args.product,
            pair_csv=pair_csv,
            dss_file=dss_file,
            rim_csv=get_rim_inflow_outputs(args.product)["sv"],
            output_dir=gen / "output" / "_2_qmap" / WEATHER_SETS[args.product]["slug"],
            validation_dir=delivery_dir(gen / "output", args.product),
            allow_negative=ALLOW_NEGATIVE,
        )
        return

    # --product B
    sim_in_dir = get_rim_inflow_outputs("B")["dir"]
    out_dir = gen / "output" / "_2_qmap" / "product_b"
    final_dir = gen / "output" / "_product_b_final"

    run_product_b_qmap_from_pairs(
        pair_csv=str(pair_csv),
        dss_file=str(dss_file),
        sim_in_dir=str(sim_in_dir),
        out_dir=str(out_dir),
        output_tag="qmap",
    )

    print("\nWriting final Product B CSVs ...")
    total = write_product_b_sv(out_dir, final_dir, pair_csv, "productB")
    print(f"  Product B final: {total} file(s) written to {final_dir}")


if __name__ == "__main__":
    main()
