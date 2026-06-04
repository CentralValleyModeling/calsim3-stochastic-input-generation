"""
Aggregate Routed Rim Inflows into Composite Basins
==================================================
Some CalSim index points drain an area that the VIC routing only covers as a
set of smaller sub-basins.  This step sums existing routed component series
(written by _2_compile_rim_inflows.py) into a single composite routed series so
it can serve as a quantile-mapping basis in mod_hydrology/rim_inflow.

Currently defined aggregations
------------------------------
- SRBB (Sacramento River at Bend Bridge) = Shasta inflow + the seven
  tributaries draining to the Sacramento above the Bend Bridge gauge (node
  SAC257), per the CalSim3 domain GIS (Incr_Drain == "Above SAC257"):
  Cow, Battle, Bear, Clear (+ Clear inflow to Whiskeytown), Cottonwood, and
  S. Fork Cottonwood creeks.  The Shasta-only routing (CS3_I_SHSTA) stops at
  the dam and under-represents Bend Bridge, so UNIMP_SRBB is quantile-mapped
  against this composite instead of I_SHSTA.

Inputs / Outputs (mirrors _2_compile_rim_inflows.py layout)
-----------------------------------------------------------
- Product A:  output/routed/Product_A/1/CS3_<comp>_qmo.csv     -> CS3_SRBB_qmo.csv
- Product B:  output/routed/Product_B/1/CS3_<comp>_qmo_n##.csv -> CS3_SRBB_qmo_n##.csv

Usage
-----
    python mod_forcing/vic/_3_aggregate_routings.py --product A
    python mod_forcing/vic/_3_aggregate_routings.py --product B
    python mod_forcing/vic/_3_aggregate_routings.py --product both
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

# ==== CONFIG =================================================================
# Composite routed series -> list of routed component names (the VIC stem of
# each CS3_<stem>_qmo*.csv routed file produced by _2_compile_rim_inflows.py).
AGGREGATIONS = {
    "SRBB": [
        "I_SHSTA",   # Sacramento River inflow to Shasta Lake
        "I_COW014",  # Cow Creek
        "I_BTL006",  # Battle Creek
        "I_BCN010",  # Bear Creek
        "I_CLR011",  # Clear Creek below Whiskeytown
        "I_WKYTN",   # Clear Creek inflow to Whiskeytown
        "I_CWD018",  # Cottonwood Creek near Olinda
        "I_SCW008",  # South Fork Cottonwood Creek
    ],
}


def _routed_dir(product: str) -> Path:
    vic_gen = get_module_generated_dir("mod_forcing/vic")
    sub = "Product_A" if product == "A" else "Product_B"
    return Path(str(vic_gen)) / "output" / "routed" / sub / "1"


def _aggregate_product_a(name: str, components: list[str], routed_dir: Path) -> None:
    """Sum component CS3_<comp>_qmo.csv (date,value) into CS3_<name>_qmo.csv."""
    series = {}
    for comp in components:
        fpath = routed_dir / f"CS3_{comp}_qmo.csv"
        if not fpath.exists():
            raise FileNotFoundError(f"Missing component for {name}: {fpath}")
        df = pd.read_csv(fpath, header=None, index_col=0)
        series[comp] = df.iloc[:, 0]

    wide = pd.concat(series, axis=1)
    if wide.isna().any().any():
        missing = wide.index[wide.isna().any(axis=1)]
        raise ValueError(
            f"{name}: component series are not date-aligned; "
            f"{len(missing)} date(s) absent from at least one component "
            f"(first: {missing[0]})."
        )

    total = wide.sum(axis=1)
    out = routed_dir / f"CS3_{name}_qmo.csv"
    total.to_csv(out, header=False)
    print(f"  [A] {out.name}: summed {len(components)} components, {len(total)} months")


def _aggregate_product_b(name: str, components: list[str], routed_dir: Path) -> None:
    """Sum component CS3_<comp>_qmo_n##.csv (y,m,value) per chunk -> CS3_<name>_qmo_n##.csv."""
    # Discover chunk suffixes from the first component
    first = components[0]
    chunk_files = sorted(routed_dir.glob(f"CS3_{first}_qmo_*.csv"))
    if not chunk_files:
        raise FileNotFoundError(
            f"No Product B chunks found for component {first} in {routed_dir}"
        )
    suffixes = [f.name.split("_qmo_", 1)[1].rsplit(".csv", 1)[0] for f in chunk_files]

    for ts in suffixes:
        ym = None
        value_cols = []
        for comp in components:
            fpath = routed_dir / f"CS3_{comp}_qmo_{ts}.csv"
            if not fpath.exists():
                raise FileNotFoundError(f"Missing component for {name} chunk {ts}: {fpath}")
            df = pd.read_csv(fpath, header=None)
            cur_ym = df.iloc[:, [0, 1]].reset_index(drop=True)
            if ym is None:
                ym = cur_ym
            elif not cur_ym.equals(ym):
                raise ValueError(
                    f"{name} chunk {ts}: component {comp} year/month columns "
                    f"do not match {first}."
                )
            value_cols.append(df.iloc[:, 2].reset_index(drop=True))

        total = pd.concat(value_cols, axis=1).sum(axis=1)
        out_df = pd.concat([ym, total.rename(2)], axis=1)
        out = routed_dir / f"CS3_{name}_qmo_{ts}.csv"
        out_df.to_csv(out, header=False, index=False)
    print(f"  [B] CS3_{name}_qmo_n##.csv: summed {len(components)} components across {len(suffixes)} chunks")


def main():
    parser = argparse.ArgumentParser(description="Aggregate routed rim inflows into composite basins.")
    parser.add_argument("--product", choices=["A", "B", "both"], required=True,
                        help="Product to aggregate: A, B, or both.")
    parser.add_argument("--names", nargs="*", default=None,
                        help="Composite names to build (default: all defined).")
    args = parser.parse_args()

    names = args.names or list(AGGREGATIONS)
    products = ["A", "B"] if args.product == "both" else [args.product]

    for product in products:
        routed_dir = _routed_dir(product)
        if not routed_dir.exists():
            raise FileNotFoundError(f"Routed directory not found: {routed_dir}")
        print(f"Product {product}: {routed_dir}")
        for name in names:
            if name not in AGGREGATIONS:
                raise KeyError(f"Unknown aggregation '{name}'. Defined: {list(AGGREGATIONS)}")
            components = AGGREGATIONS[name]
            if product == "A":
                _aggregate_product_a(name, components, routed_dir)
            else:
                _aggregate_product_b(name, components, routed_dir)

    print("Done.")


if __name__ == "__main__":
    main()
