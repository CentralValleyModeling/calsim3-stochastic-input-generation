r"""
Build pickle cache for Product B stochastic runs.

Expected pattern:
- one baseline / benchmark DSS
- ten Product B DSS files for blocks n01 ... n10

The shared builder lives in ../utils/dss_pickle_builder.py and the shared metric
definitions live in ../reference/metrics.csv.

Example:

    python _pickle_builder.py ^
        --baseline-name Historical ^
        --baseline-dss "..\benchmark\DSS\output\benchmark.dss" ^
        --product-b-root "data\GENERATED\postprocessing\calsim_runs\product_b\dv_out" ^
        --glob "**\*.dss" ^
        --out-dir "data\GENERATED\postprocessing\calsim_runs\product_b\pickle_files"

The Product B block scenarios are auto-discovered from the path names using a
case-insensitive n01...n10 pattern.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Dict, List

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
PRODUCT_B_DV_DIR = (
    get_generated_dir()
    / "postprocessing"
    / "calsim_runs"
    / "product_b"
    / "dv_out"
)


_BLOCK_RE = re.compile(r"(?<![A-Za-z0-9])n0*([1-9]|10)(?![A-Za-z0-9])", flags=re.IGNORECASE)


def block_label_from_path(path: Path) -> str | None:
    match = _BLOCK_RE.search(str(path))
    if not match:
        return None
    return f"n{int(match.group(1)):02d}"


def discover_product_b_scenarios(product_b_root: str | Path, glob_pattern: str = "**/*.dss") -> List[Scenario]:
    root = Path(product_b_root)
    if not root.exists():
        raise FileNotFoundError(f"Product B root does not exist: {root}")

    discovered: Dict[str, Path] = {}
    for dss_path in sorted(root.glob(glob_pattern)):
        label = block_label_from_path(dss_path)
        if label is None:
            continue
        discovered.setdefault(label, dss_path)

    if not discovered:
        raise FileNotFoundError(
            f"No Product B DSS files matching n01..n10 were found beneath: {root}"
        )

    scenarios = [Scenario(name=label, dss_path=str(discovered[label])) for label in sorted(discovered)]
    return scenarios


def build_product_b_pickles(
    baseline_name: str,
    baseline_dss: str | Path,
    product_b_root: str | Path,
    out_dir: str | Path,
    glob_pattern: str = "*.dss",
    metrics_csv_path: str | Path | None = None,
) -> Dict[str, str]:
    metrics_csv = Path(metrics_csv_path) if metrics_csv_path is not None else (REFERENCE_DIR / "metrics.csv")
    scenarios = [Scenario(baseline_name, str(baseline_dss))]
    scenarios.extend(discover_product_b_scenarios(product_b_root=product_b_root, glob_pattern=glob_pattern))

    missing_blocks = [
        f"n{i:02d}"
        for i in range(1, 11)
        if f"n{i:02d}" not in {scenario.name for scenario in scenarios[1:]}
    ]
    if missing_blocks:
        print(f"Warning: Product B blocks not discovered: {', '.join(missing_blocks)}")

    return build_pickles_from_metrics_csv(
        scenarios=scenarios,
        baseline_name=baseline_name,
        out_dir=str(out_dir),
        metrics_csv_path=str(metrics_csv),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Product B pickles from a benchmark DSS and n01..n10 DSS blocks.")
    parser.add_argument("--baseline-name", default="Historical", help="Baseline scenario name")
    parser.add_argument(
        "--baseline-dss",
        default=str(BASELINE_DSS),
        help="Path to the benchmark DSS file",
    )
    parser.add_argument(
        "--product-b-root",
        default=str(PRODUCT_B_DV_DIR),
        help="Root directory containing Product B DSS files",
    )
    parser.add_argument("--glob", default="*.dss", help="Glob pattern used to find Product B DSS files")
    parser.add_argument(
        "--metrics-csv",
        default=str(REFERENCE_DIR / "metrics.csv"),
        help="Path to the shared metrics.csv",
    )
    parser.add_argument(
        "--out-dir",
        default=str(get_generated_dir() / "postprocessing" / "calsim_runs" / "product_b" / "pickle_files"),
        help="Output directory for pickle cache",
    )
    args = parser.parse_args()

    outputs = build_product_b_pickles(
        baseline_name=args.baseline_name,
        baseline_dss=args.baseline_dss,
        product_b_root=args.product_b_root,
        out_dir=args.out_dir,
        glob_pattern=args.glob,
        metrics_csv_path=args.metrics_csv,
    )

    print("Created:")
    for key, value in outputs.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
