"""
Product A Validation Run Pickle Cache Builder
=============================================
Two-scenario wrapper around the shared CalView-style DSS pickle builder
(``utils.dss_pickle_builder``) that pairs the historical baseline DV DSS
with the single Product A DV DSS produced by an external CalSim 3 run.
Used as input to ``_productA_postproc.py`` (or ``_historical_modified_postproc.py``).

Inputs
------
- Historical baseline DV DSS:
  ``BASE/CalSim3/Studies/9.3.1_danube_hist/DSS/output/
  DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss``
- Product A DV DSS (auto-discovered under ``--product-a-root`` by default):
  ``GENERATED/postprocessing/calsim_runs/product_a/dv_out/
  DCR2023_DV_9.3.1_Danube_Hist_v1.7_ProductA.dss``
- Metric definitions: ``reference/metrics.csv``

Outputs
-------
- ``GENERATED/postprocessing/calsim_runs/product_a/pickle_files/``
  (values.pkl, diffs.pkl, units.pkl, fields.pkl, meta.json)

Dependencies
------------
- utils.dss_pickle_builder, utils.paths
- pandas, numpy, pydsstools

Usage
-----
    python postprocessing/calsim_runs/_productA_pickle_builder.py

Or pass an explicit Product A DSS instead of auto-discovery:

    python postprocessing/calsim_runs/_productA_pickle_builder.py --product-a-dss <PATH>
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Dict

RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[1]
REFERENCE_DIR = RUN_DIR / "reference"

sys.path.insert(0, str(REPO_ROOT))

from utils.dss_pickle_builder import Scenario, build_pickles_from_metrics_csv
from utils.paths import get_base_dir, get_generated_dir


BASELINE_DSS = (
    get_base_dir()
    / "CalSim3"
    / "Studies"
    / "9.3.1_danube_hist"
    / "DSS"
    / "output"
    / "DCR2023_DV_9.3.1_Danube_Hist_v1.7.dss"
)

PRODUCT_A_DV_DIR = (
    get_generated_dir()
    / "postprocessing"
    / "calsim_runs"
    / "product_a"
    / "dv_out"
)

PRODUCT_A_PICKLE_DIR = (
    get_generated_dir()
    / "postprocessing"
    / "calsim_runs"
    / "product_a"
    / "pickle_files"
)

_PRODUCT_A_RE = re.compile(r"product[\s_\-]*a", flags=re.IGNORECASE)


def _normalize_glob_pattern(glob_pattern: str) -> str:
    """Allow Windows-style backslashes in --glob while using pathlib.Path.glob."""
    return str(glob_pattern).replace("\\", "/")


def discover_product_a_dss(
    product_a_root: str | Path,
    glob_pattern: str = "**/*.dss",
) -> Path:
    """Discover a single Product A DSS under product_a_root.

    The function first applies the glob, then prefers files whose **filename**
    contains "ProductA", "Product_A", or "Product A". Matching the filename
    instead of the full path avoids false positives from a parent directory
    named ``product_a`` (which would otherwise let auxiliary outputs like
    ``CVGroundwaterBudget.dss`` pass the filter). If more than one candidate
    remains, raises and asks the user to pass --product-a-dss explicitly.
    """
    root = Path(product_a_root)
    if not root.exists():
        raise FileNotFoundError(f"Product A root does not exist: {root}")

    pattern = _normalize_glob_pattern(glob_pattern)
    matches = sorted(path for path in root.glob(pattern) if path.is_file())

    if not matches:
        raise FileNotFoundError(
            f"No DSS files were found beneath {root} using glob {glob_pattern!r}."
        )

    product_a_matches = [path for path in matches if _PRODUCT_A_RE.search(path.name)]
    candidates = product_a_matches if product_a_matches else matches

    if len(candidates) > 1:
        preview = "\n".join(f"  {path}" for path in candidates[:25])
        extra = "" if len(candidates) <= 25 else f"\n  ... and {len(candidates) - 25} more"
        raise RuntimeError(
            "Multiple candidate Product A DSS files were found. "
            "Please pass --product-a-dss explicitly.\n"
            f"Candidates:\n{preview}{extra}"
        )

    return candidates[0]


def build_product_a_pickles(
    baseline_name: str,
    baseline_dss: str | Path,
    product_a_name: str,
    out_dir: str | Path,
    product_a_dss: str | Path | None = None,
    product_a_root: str | Path = PRODUCT_A_DV_DIR,
    glob_pattern: str = "**/*.dss",
    metrics_csv_path: str | Path | None = None,
) -> Dict[str, str]:
    """Build Product A pickle cache using the shared DSS pickle builder."""
    metrics_csv = (
        Path(metrics_csv_path)
        if metrics_csv_path is not None
        else REFERENCE_DIR / "metrics.csv"
    )

    product_a_path = (
        Path(product_a_dss)
        if product_a_dss is not None
        else discover_product_a_dss(product_a_root, glob_pattern)
    )

    scenarios = [
        Scenario(baseline_name, str(baseline_dss)),
        Scenario(product_a_name, str(product_a_path)),
    ]

    return build_pickles_from_metrics_csv(
        scenarios=scenarios,
        baseline_name=baseline_name,
        out_dir=str(out_dir),
        metrics_csv_path=str(metrics_csv),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Product A pickles from a benchmark DSS and one Product A DSS."
    )
    parser.add_argument("--baseline-name", default="Historical", help="Baseline scenario name")
    parser.add_argument(
        "--baseline-dss",
        default=str(BASELINE_DSS),
        help="Path to the benchmark / historical DSS file",
    )
    parser.add_argument(
        "--product-a-name",
        default="Product A",
        help="Scenario name to use for the Product A DSS in values.pkl",
    )
    parser.add_argument(
        "--product-a-dss",
        default=None,
        help="Explicit path to the Product A DSS file. If omitted, --product-a-root and --glob are used.",
    )
    parser.add_argument(
        "--product-a-root",
        default=str(PRODUCT_A_DV_DIR),
        help="Root directory used to discover the Product A DSS when --product-a-dss is omitted.",
    )
    parser.add_argument(
        "--glob",
        default="**/*.dss",
        help="Glob pattern used to find DSS files under --product-a-root.",
    )
    parser.add_argument(
        "--metrics-csv",
        default=str(REFERENCE_DIR / "metrics.csv"),
        help="Path to the shared metrics.csv.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(PRODUCT_A_PICKLE_DIR),
        help="Output directory for the Product A pickle cache.",
    )

    args = parser.parse_args()

    outputs = build_product_a_pickles(
        baseline_name=args.baseline_name,
        baseline_dss=args.baseline_dss,
        product_a_name=args.product_a_name,
        product_a_dss=args.product_a_dss,
        product_a_root=args.product_a_root,
        out_dir=args.out_dir,
        glob_pattern=args.glob,
        metrics_csv_path=args.metrics_csv,
    )

    print("Created:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
