r"""
Build pickle cache for the Historical vs Modified Historical paired comparison.

This is a focused, two-scenario wrapper around the shared builder
(``utils/dss_pickle_builder.py``) that compares one historical CalSim 3 DV
against a modified historical run. Metric definitions live in:

    postprocessing/calsim_runs/reference/metrics_historical_modified_freeport_vernalis.csv

Usage from the repo root::

    python postprocessing\calsim_runs\_historical_modified_pickle_builder.py

Dependencies:
    Use the project environment from ``environment.yml``. This wrapper imports
    ``utils.dss_pickle_builder``, which requires pandas, numpy, and pydsstools.

If HEC-DSS raises a 256-character Fortran CNAME path limit error, rebuild with
short DSS copies::

    if not exist "C:\tmp\dss" mkdir "C:\tmp\dss"
    copy /Y "<historical DSS path>" "C:\tmp\dss\hist.dss"
    copy /Y "<modified historical DSS path>" "C:\tmp\dss\modhist.dss"

    python postprocessing\calsim_runs\_historical_modified_pickle_builder.py --baseline-dss C:\tmp\dss\hist.dss --compare-dss C:\tmp\dss\modhist.dss
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict

RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]

sys.path.insert(0, str(REPO_ROOT))

from utils.dss_pickle_builder import Scenario, build_pickles_from_metrics_csv
from utils.paths import get_base_dir, get_generated_dir


SHORT_PATH_HELP = r"""
HEC-DSS path length note:
    If the default DSS path is longer than 256 characters, pydsstools can fail
    before reading Modified Historical. Rebuild with short DSS copies:

    if not exist "C:\tmp\dss" mkdir "C:\tmp\dss"
    copy /Y "<historical DSS path>" "C:\tmp\dss\hist.dss"
    copy /Y "<modified historical DSS path>" "C:\tmp\dss\modhist.dss"
    python postprocessing\calsim_runs\_historical_modified_pickle_builder.py --baseline-dss C:\tmp\dss\hist.dss --compare-dss C:\tmp\dss\modhist.dss
"""


# -----------------------------
# Defaults (resolved via utils.paths so config.json is honored)
# -----------------------------
HISTORICAL_DSS = (
    get_base_dir()
    / "CalSim3" / "Studies"
    / "9.3.1_danube_hist" / "DSS" / "output"
    / "DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss"
)

MODIFIED_HISTORICAL_DSS = (
    get_generated_dir()
    / "postprocessing" / "calsim_runs"
    / "historical_modified" / "9.3.1_danube_hist_New" / "DSS" / "output"
    / "DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss"
)

METRICS_CSV = RUN_DIR / "reference" / "metrics_historical_modified_freeport_vernalis.csv"

PICKLE_DIR = (
    get_generated_dir()
    / "postprocessing" / "calsim_runs"
    / "historical_modified" / "pickle_files"
)


def _require_file(path: Path, label: str) -> Path:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def main() -> Dict[str, str]:
    parser = argparse.ArgumentParser(
        description="Build pickles for the Historical vs Modified Historical paired comparison.",
        epilog=SHORT_PATH_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--baseline-name", default="Historical",
                        help="Scenario name for the historical baseline DSS.")
    parser.add_argument("--baseline-dss", default=str(HISTORICAL_DSS),
                        help="Path to the historical baseline DSS file.")
    parser.add_argument("--compare-name", default="Modified Historical",
                        help="Scenario name for the modified historical DSS.")
    parser.add_argument("--compare-dss", default=str(MODIFIED_HISTORICAL_DSS),
                        help="Path to the modified historical DSS file.")
    parser.add_argument("--metrics-csv", default=str(METRICS_CSV),
                        help="Path to the metrics CSV that defines the compared variables.")
    parser.add_argument("--out-dir", default=str(PICKLE_DIR),
                        help="Output directory for the pickle cache.")

    args = parser.parse_args()

    baseline_dss = _require_file(Path(args.baseline_dss), "Historical baseline DSS")
    compare_dss = _require_file(Path(args.compare_dss), "Modified Historical DSS")
    metrics_csv = _require_file(Path(args.metrics_csv), "Metrics CSV")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = [
        Scenario(args.baseline_name, str(baseline_dss)),
        Scenario(args.compare_name, str(compare_dss)),
    ]

    outputs = build_pickles_from_metrics_csv(
        scenarios=scenarios,
        baseline_name=args.baseline_name,
        out_dir=str(out_dir),
        metrics_csv_path=str(metrics_csv),
    )

    print("Created:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")

    return outputs


if __name__ == "__main__":
    main()
