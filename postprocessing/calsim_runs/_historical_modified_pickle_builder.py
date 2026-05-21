"""
Historical vs Modified Historical Pickle Cache Builder
======================================================
Two-scenario wrapper around the shared CalView-style DSS pickle builder
(``utils.dss_pickle_builder``) that compares one historical CalSim 3 DV
against a modified historical run for the Freeport / Vernalis metrics
listed in ``reference/metrics_historical_modified_freeport_vernalis.csv``.

Inputs
------
- Historical baseline DV DSS:
  ``BASE/CalSim3/Studies/9.3.1_danube_hist/DSS/output/
  DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss``
- Modified historical DV DSS:
  ``GENERATED/postprocessing/calsim_runs/historical_modified/dv_out/
  DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss``
- Metric definitions: ``reference/metrics_historical_modified_freeport_vernalis.csv``

Outputs
-------
- ``GENERATED/postprocessing/calsim_runs/historical_modified/pickle_files/``
  (values.pkl, diffs.pkl, units.pkl, fields.pkl, meta.json)

Dependencies
------------
- utils.dss_pickle_builder, utils.paths
- pandas, numpy, pydsstools

Usage
-----
    python postprocessing/calsim_runs/_historical_modified_pickle_builder.py

Long Windows file paths (e.g. on OneDrive) are handled transparently by the
shared builder via ``utils.dss_io.open_dss``, which shortens the path that
HEC-DSS sees via a ``_dss_link`` directory junction.
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
    / "historical_modified" / "dv_out"
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
