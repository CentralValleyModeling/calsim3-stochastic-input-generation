"""
Quantile-Mapping Product A Validation 
=======================================================
Thin driver that configures paths and calls the reusable Product A
split-sample QM validation utility.

For each (target, predictor) pair in ``reference/qmap_pairs.csv``:

- **Training** (1921-1971): Both basis and target from CalSim3 baseline DSS.
- **Simulation** (1972-2018): Product A QMAP'd predictor from rim_inflow output
  is mapped to the target domain and validated against CalSim3 actuals.

Inputs
------
- CalSim baseline DSS: CalSim3/__calsim_sv_default__.dss
- Product A QMAP'd rim inflows: mod_hydrology/rim_inflow/output/
    _2_qmap_historical_validation/_product_a_validation/_riminflow_productA_1972_2018.csv
- Pair definitions: reference/qmap_pairs.csv

Outputs
-------
- <generated>/output/_2_qmap/product_a/   (detail CSVs + figures)
- <generated>/output/_product_a_validation/ (CalSim-format validation CSVs)

Dependencies
------------
- mod_hydrology/rim_inflow/_2_qmap_historical_validation.py
- utils/qmap_product_a_from_pairs.py  (split-sample QM engine)
- utils/quantile_mapping.py           (qmap_single)
- utils/paths.py                      (data-dir resolution)

Usage
-----
    cd mod_other/upper_watershed
    python _2_qmap_product_a.py

Negative values can be controlled per pair via an optional ``allow_negative``
column in qmap_pairs.csv (True/False).  If the column is absent, the
``ALLOW_NEGATIVE`` flag below is used as the fallback default for all pairs.
"""

# %% -- IMPORTS ---------------------------------------------------------------
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.qmap_product_a_from_pairs import run_product_a_qmap_from_pairs

# %% -- CONFIG ----------------------------------------------------------------
ALLOW_NEGATIVE = False  # Fallback when CSV has no allow_negative column

# %% -- PATHS -----------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_other/upper_watershed")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

# %% -- RUN -------------------------------------------------------------------
run_product_a_qmap_from_pairs(
    pair_csv=_SCRIPT_DIR / "reference" / "qmap_pairs.csv",
    dss_file=get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss",
    product_a_rim_csv=(
        _rim_gen / "output" / "_2_qmap_historical_validation"
        / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
    ),
    output_dir=_gen / "output" / "_2_qmap" / "product_a",
    validation_dir=_gen / "output" / "_product_a_validation",
    allow_negative=ALLOW_NEGATIVE,
)
