"""
Quantile-Mapping Product A Validation -- miscellaneous SVs
=========================================================
Thin driver that configures paths and calls the reusable Product A
split-sample QM validation utility for the miscellaneous module.

For each (target, predictor) pair in ``reference/qmap_pairs.csv``:

- **Training** (1921-1971): Both basis and target from CalSim3 baseline DSS.
- **Simulation** (1972-2018): Product A QMAP'd predictor from rim_inflow output
  is mapped to the target domain and validated against CalSim3 actuals.

Currently maps TULE_WET_INDX from I_PEDRO inflow (see qmap_pairs.csv).

Inputs
------
- CalSim baseline DSS: CalSim3/__calsim_sv_default__.dss
- Product A QMAP'd rim inflows: mod_hydrology/rim_inflow/output/
    _2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv
- Pair definitions: reference/qmap_pairs.csv

Outputs
-------
- <generated>/output/_4_qmap_product_a/   (detail CSVs + figures)
- <generated>/output/_product_a_validation/  (CalSim-format validation CSVs)

Dependencies
------------
- mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
- utils/qmap_product_a_from_pairs.py  (split-sample QM engine)
- utils/quantile_mapping.py           (qmap_single)
- utils/paths.py                      (data-dir resolution)

Usage
-----
    cd mod_other/miscellaneous
    python _4_qmap_product_a.py

Negative values can be controlled per pair via an optional ``allow_negative``
column in qmap_pairs.csv (True/False).  If the column is absent, the
``ALLOW_NEGATIVE`` flag below is used as the fallback default for all pairs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.qmap_product_a_from_pairs import run_product_a_qmap_from_pairs

# Fallback when qmap_pairs.csv has no allow_negative column
ALLOW_NEGATIVE = False


def main():
    script_dir = Path(__file__).resolve().parent
    gen = get_module_generated_dir("mod_other/miscellaneous")
    rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

    run_product_a_qmap_from_pairs(
        pair_csv=script_dir / "reference" / "qmap_pairs.csv",
        dss_file=get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss",
        product_a_rim_csv=(
            rim_gen / "output" / "_2_qmap_historical_validation"
            / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
        ),
        output_dir=gen / "output" / "_4_qmap_product_a",
        validation_dir=gen / "output" / "_product_a_validation",
        allow_negative=ALLOW_NEGATIVE,
    )


if __name__ == "__main__":
    main()
