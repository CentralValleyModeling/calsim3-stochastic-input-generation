from __future__ import annotations

"""
Wrapper script for Product-B quantile mapping of non-rimflow/non-ET terms.

This script defines paths and calls the quantile-mapping logic in
``utils.qmap_product_b_from_pairs``, then writes a second set of chunked
100-year CSVs in final CalSim format (Part B, Part C, Year, Month, Value)
into ``output/_product_b_final/``.

Copy this script to each module folder and update the paths below as needed.
"""

import sys
from pathlib import Path

import pandas as pd

# Add repo root to path for utils imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.paths import get_base_dir, get_module_generated_dir
from utils.qmap_product_b_from_pairs import (
    run_product_b_qmap_from_pairs,
    read_qmap_pairs,
    build_output_filename,
    find_timeseries_in_dir,
)

_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_other/upper_watershed")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

PAIR_CSV = _SCRIPT_DIR / "reference" / "qmap_pairs.csv"
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
SIM_IN_DIR = _rim_gen / "output" / "_3_qmap_product_b"
OUT_DIR = _gen / "output" / "_2_qmap_product_b"
FINAL_DIR = _gen / "output" / "_product_b_final"


def _install_pandas_me_compat() -> None:
    """Support newer 'ME' month-end alias on pandas versions that only accept 'M'."""
    try:
        pd.date_range("2000-01-31", periods=1, freq="ME")
        return
    except Exception:
        pass

    original_date_range = pd.date_range

    def _date_range_compat(*args, **kwargs):
        freq = kwargs.get("freq")
        if isinstance(freq, str) and freq.upper() == "ME":
            kwargs["freq"] = "M"
        return original_date_range(*args, **kwargs)

    pd.date_range = _date_range_compat


def write_product_b_final(out_dir: Path, final_dir: Path, pair_csv: Path) -> None:
    """
    Read the intermediate qmap CSVs and write final Product B format
    (Part B, Part C, Year, Month, Value) chunked per timeseries.

    Each target gets one CSV per chunk (n01-n10), named:
        <target_part_b>_productB_<ts>.csv
    """
    final_dir.mkdir(parents=True, exist_ok=True)
    df_pairs = read_qmap_pairs(pair_csv)
    timeseries_list = find_timeseries_in_dir(SIM_IN_DIR)

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
                "Year": df["Year"].astype(int),
                "Month": df["Month"].astype(int),
                "Value": df["qmap_target"],
            })

            out_fname = f"{target_b}_productB_{ts}.csv"
            final_df.to_csv(final_dir / out_fname, index=False)
            total += 1

        print(f"  {ts}: wrote final Product B CSV(s)")

    print(f"  Product B final: {total} file(s) written to {final_dir}")


def main() -> None:
    _install_pandas_me_compat()

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

    print("\nWriting final Product B CSVs ...")
    write_product_b_final(OUT_DIR, FINAL_DIR, PAIR_CSV)


if __name__ == "__main__":
    main()
