from __future__ import annotations

"""
Wrapper script for Product-B quantile mapping of non-rimflow/non-ET terms.

This script defines paths and calls the quantile-mapping logic in
``utils.qmap_product_b_from_pairs``.

Copy this script to each module folder and update the paths below as needed.
"""

import sys
from pathlib import Path

# Add repo root to path for utils imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.paths import get_base_dir, get_module_generated_dir
from utils.qmap_product_b_from_pairs import run_product_b_qmap_from_pairs

_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_reservoir/storage_curves")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

PAIR_CSV = _SCRIPT_DIR / "reference" / "qmap_pairs.csv"
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
SIM_IN_DIR = _rim_gen / "_3_qmap_product_b"
OUT_DIR = _gen /"output"/"_2_qmap_product_b_mammoth_storage"


def main() -> None:
    run_product_b_qmap_from_pairs(
        pair_csv=str(PAIR_CSV),
        dss_file=str(DSS_FILE),
        sim_in_dir=str(SIM_IN_DIR),
        out_dir=str(OUT_DIR),
        train_start="1921-10-01",
        train_end="2021-09-30",
        product_b_start="1921-10-31",
        product_b_end="2021-09-30",
        output_tag="qmap",
    )


if __name__ == "__main__":
    main()
