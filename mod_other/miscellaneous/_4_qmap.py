"""
Miscellaneous Quantile Mapping
==============================
Thin driver around the shared QM engines for the miscellaneous module.
For ``--product historical`` and ``A`` it calls
``utils.qmap_single_from_pairs.run_single_qmap_from_pairs`` (1922-2018 simulation). For ``--product B``
it calls ``utils.qmap_product_b_from_pairs.run_product_b_qmap_from_pairs``
for each of the 10 stochastic chunks, then reformats the per-chunk detail
CSVs into final ``Part B, Part C, Year, Month, Value`` files.

For each (target, predictor) pair in ``reference/qmap_pairs.csv``:

- The map is fitted on WY1950-2018, the same fit for A and B, by the pair's
  ``fit`` (utils.qmap_fit): ``pass`` trains on the CalSim3 predictor,
  ``absorb`` on the rim-inflow model's historical-unsplit predictor. The
  target is CalSim3's.
- Simulation (Historical_Unsplit and A: 1922-2018; B: 10 chunks of 100 WY each) maps the
  rim-inflow model's predictor onto the target domain.

Inputs
------
- ``reference/qmap_pairs.csv`` (pair definitions and fit; shared by A and B)
- CalSim baseline DSS: ``BASE/CalSim3/__calsim_sv_default__.dss``
- Rim-inflow predictors (utils.paths.get_rim_inflow_outputs): Historical_Unsplit
  ``_riminflow_historicalUnsplit_1922_2018.csv``, Product A
  ``_riminflow_productA_1922_2018.csv``, Product B ``<PartB>_qmo_n{01..10}.csv``;
  the historical-unsplit run for absorb fits

Outputs
-------
- ``output/_4_qmap/<historical_unsplit|product_a>/`` -- detail CSVs + figures
  (--product historical, A)
- ``output/<_historical_unsplit_validation|_product_a_validation>/`` -- delivery CSVs
  (incl. ``TULE_WET_INDX_<historicalUnsplit|productA>_1922_2018.csv``)
- ``output/_4_qmap/product_b/`` -- B per-chunk detail CSVs (--product B)
- ``output/_product_b_final/<part_b>_productB_n{01..10}.csv`` -- B final
  per-chunk CSVs in CalSim format

Dependencies
------------
- utils.qmap_single_from_pairs (single-series QM engine)
- utils.qmap_product_b_from_pairs (chunked Product B QM engine)
- utils.quantile_mapping (qmap_single; deterministic via QMAP_SEED)
- utils.paths

Usage
-----
    python mod_other/miscellaneous/_4_qmap.py --product historical
    python mod_other/miscellaneous/_4_qmap.py --product A
    python mod_other/miscellaneous/_4_qmap.py --product B
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
        description="Miscellaneous quantile mapping",
    )
    parser.add_argument(
        "--product", choices=list(WEATHER_SETS), required=True,
        help="Weather set: historical (Historical_Unsplit) or A (1922-2018), or B (10 "
             "stochastic chunks); all use the WY1950-2018 fit.",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    gen = get_module_generated_dir("mod_other/miscellaneous")
    pair_csv = script_dir / "reference" / "qmap_pairs.csv"
    dss_file = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"

    if args.product != "B":
        run_single_qmap_from_pairs(
            product=args.product,
            pair_csv=pair_csv,
            dss_file=dss_file,
            rim_csv=get_rim_inflow_outputs(args.product)["sv"],
            output_dir=gen / "output" / "_4_qmap" / WEATHER_SETS[args.product]["slug"],
            validation_dir=delivery_dir(gen / "output", args.product),
            allow_negative=ALLOW_NEGATIVE,
        )
        return

    # --product B
    sim_in_dir = get_rim_inflow_outputs("B")["dir"]
    out_dir = gen / "output" / "_4_qmap" / "product_b"
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
