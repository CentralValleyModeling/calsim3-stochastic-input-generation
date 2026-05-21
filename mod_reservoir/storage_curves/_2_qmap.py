"""
Storage Curves Quantile Mapping (Product A or Product B)
========================================================
Thin driver around the shared QM engines for the reservoir storage_curves
module. For ``--product A`` it calls ``utils.qmap_product_a_from_pairs.
run_product_a_qmap_from_pairs`` (1921-1971 train, 1972-2018 simulate /
validate). For ``--product B`` it calls ``utils.qmap_product_b_from_pairs.
run_product_b_qmap_from_pairs`` for each of the 10 stochastic chunks, then
reformats the per-chunk detail CSVs into final
``Part B, Part C, Year, Month, Value`` files.

For each (target, predictor) pair in ``reference/qmap_pairs.csv``:

- Training (1921-1971 for A; 1921-2021 for B) uses CalSim baseline DSS for
  both basis and target.
- Simulation (A: 1972-2018; B: 10 chunks of 100 WY each) maps the matched
  rim-inflow predictor onto the target domain.

Inputs
------
- ``reference/qmap_pairs.csv`` (pair definitions; shared by A and B)
- CalSim baseline DSS: ``BASE/CalSim3/__calsim_sv_default__.dss``
- Product A: ``mod_hydrology/rim_inflow/output/_2_qmap_historical_validation/
  _product_a_validation/_riminflow_productA_1972_2018.csv``
- Product B: ``mod_hydrology/rim_inflow/output/_3_qmap_product_b/
  <PartB>_qmo_n{01..10}.csv``

Outputs
-------
- ``output/_2_qmap/product_a/`` -- A detail CSVs + figures (--product A)
- ``output/_product_a_validation/`` -- A CalSim-format validation CSVs
- ``output/_2_qmap/product_b/`` -- B per-chunk detail CSVs (--product B)
- ``output/_product_b_final/<part_b>_productB_n{01..10}.csv`` -- B final
  per-chunk CSVs in CalSim format

Dependencies
------------
- utils.qmap_product_a_from_pairs (split-sample QM engine)
- utils.qmap_product_b_from_pairs (chunked Product B QM engine)
- utils.quantile_mapping (qmap_single; deterministic via QMAP_SEED)
- utils.paths

Usage
-----
    python mod_reservoir/storage_curves/_2_qmap.py --product A
    python mod_reservoir/storage_curves/_2_qmap.py --product B
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.qmap_product_a_from_pairs import run_product_a_qmap_from_pairs
from utils.qmap_product_b_from_pairs import (
    run_product_b_qmap_from_pairs,
    read_qmap_pairs,
    build_output_filename,
    find_timeseries_in_dir,
)

# Fallback when qmap_pairs.csv has no allow_negative column (Product A only).
ALLOW_NEGATIVE = False


def _write_product_b_final(out_dir: Path, final_dir: Path, pair_csv: Path,
                           sim_in_dir: Path) -> None:
    """Reformat per-chunk detail CSVs into final CalSim Part B/C/Year/Month/Value CSVs.

    Each target gets one CSV per chunk (n01-n10), named
    ``<target_part_b>_productB_<ts>.csv``.
    """
    final_dir.mkdir(parents=True, exist_ok=True)
    df_pairs = read_qmap_pairs(pair_csv)
    timeseries_list = find_timeseries_in_dir(sim_in_dir)

    total = 0
    for ts in timeseries_list:
        for _, row in df_pairs.iterrows():
            target_b = row["target_part_b"]
            target_c = row["target_part_c"]
            src_fname = build_output_filename(target_b, ts, output_tag="qmap")
            src_path = out_dir / src_fname
            if not src_path.exists():
                continue

            df = pd.read_csv(src_path)
            final_df = pd.DataFrame({
                "Part B": target_b,
                "Part C": target_c,
                "Year": df["year"].astype(int),
                "Month": df["month"].astype(int),
                "Value": df["target_qm_sim"],
            })
            out_fname = f"{target_b}_productB_{ts}.csv"
            final_df.to_csv(final_dir / out_fname, index=False)
            total += 1
        print(f"  {ts}: wrote final Product B CSV(s)")

    print(f"  Product B final: {total} file(s) written to {final_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Storage Curves quantile mapping (Product A or Product B)",
    )
    parser.add_argument(
        "--product", choices=["A", "B"], required=True,
        help="Product to generate: A (split-sample 1921-1971 train / 1972-2018 "
             "simulate-and-validate) or B (10 stochastic chunks).",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    gen = get_module_generated_dir("mod_reservoir/storage_curves")
    rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
    pair_csv = script_dir / "reference" / "qmap_pairs.csv"
    dss_file = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"

    if args.product == "A":
        run_product_a_qmap_from_pairs(
            pair_csv=pair_csv,
            dss_file=dss_file,
            product_a_rim_csv=(
                rim_gen / "output" / "_2_qmap_historical_validation"
                / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
            ),
            output_dir=gen / "output" / "_2_qmap" / "product_a",
            validation_dir=gen / "output" / "_product_a_validation",
            allow_negative=ALLOW_NEGATIVE,
        )
        return

    # --product B
    sim_in_dir = rim_gen / "output" / "_3_qmap_product_b"
    out_dir = gen / "output" / "_2_qmap" / "product_b"
    final_dir = gen / "output" / "_product_b_final"

    run_product_b_qmap_from_pairs(
        pair_csv=str(pair_csv),
        dss_file=str(dss_file),
        sim_in_dir=str(sim_in_dir),
        out_dir=str(out_dir),
        train_start="1921-10-01",
        train_end="2021-09-30",
        product_b_start="1921-10-31",
        product_b_end="2021-09-30",
        output_tag="qmap",
    )

    print("\nWriting final Product B CSVs ...")
    _write_product_b_final(out_dir, final_dir, pair_csv, sim_in_dir)


if __name__ == "__main__":
    main()
