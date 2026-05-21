"""
Upper Watershed Hybrid Terms = (WYT_avg + QMap) / 2 (Product A or Product B)
============================================================================
Single driver for Hybrid = (WYT monthly average + Quantile Mapping) / 2 over
the upper watershed terms in ``reference/hybrid_terms_upper_watershed.csv``.
Three logical parts run in sequence:

  1. WYT monthly averaging (calls utils.wyt_monthlyavg_framework).
  2. Quantile mapping (calls the Product A or Product B engine).
  3. Average the two intermediate per-term results to produce the final SV.

Inputs
------
- ``reference/hybrid_terms_upper_watershed.csv``
- ``BASE/CalSim3/__calsim_sv_default__.dss`` (historical training basis /
  target series for both A and B)
- WYT historical reference: ``mod_hydrology/water_year_types/reference/``
- WYT target by product:
    * A: ``mod_hydrology/water_year_types/output/_1_calc_WYTs/Product_A/``
    * B: ``mod_hydrology/water_year_types/output/_1_calc_WYTs/Product_B/``
- Rim inflow simulation:
    * A: ``mod_hydrology/rim_inflow/output/_2_qmap_historical_validation/
      _product_a_validation/_riminflow_productA_1972_2018.csv``
    * B: ``mod_hydrology/rim_inflow/output/_3_qmap_product_b/
      <PartB>_qmo_n{01..10}.csv``

Outputs
-------
- ``output/_3_hybrid/product_a/`` (--product A) or
  ``output/_3_hybrid/product_b/`` (--product B): intermediates
  (``hybrid_wyt/``, ``hybrid_qmap/``, ``hybrid_wyt_monthly_avg_historical/``)
- ``output/_product_a_validation/<part_b>_product_a_<wy>_<wy>.csv``
  (--product A) -- final hybrid SV
- ``output/_product_b_final/<part_b>_product_b_n{01..10}.csv``
  (--product B) -- final hybrid SV per chunk

Dependencies
------------
- utils.wyt_monthlyavg_framework
- utils.qmap_product_a_from_pairs
- utils.qmap_product_b_from_pairs
- utils.paths

Usage
-----
    python mod_other/upper_watershed/_3_hybrid.py --product A
    python mod_other/upper_watershed/_3_hybrid.py --product B
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import (
    compute_wyt_pattern,
    compute_product_targets,
    water_year,
)
from utils.qmap_product_a_from_pairs import run_product_a_qmap_from_pairs
from utils.qmap_product_b_from_pairs import (
    run_product_b_qmap_from_pairs,
    read_qmap_pairs,
    build_output_filename,
    find_timeseries_in_dir,
)

# -- Paths --------------------------------------------------------------
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/upper_watershed")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

# -- Config (shared) ---------------------------------------------------
DSS_FILE = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
HYBRID_TERMS_CSV = (
    _REPO_DIR / "mod_other" / "upper_watershed" / "reference"
    / "hybrid_terms_upper_watershed.csv"
)
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"
OUTPUT_PREFIX = "upper_watershed"
WYT_HIST_DIR = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# -- Config (Product A specific) ---------------------------------------
WYT_PRODUCT_A_DIR = str(_wyt_gen / "output" / "_1_calc_WYTs" / "Product_A")
PRODUCT_A_RIM_CSV = (
    _rim_gen / "output" / "_2_qmap_historical_validation"
    / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
)
TRAIN_START_A = "1921-10-01"
TRAIN_END_A = "1971-09-30"
SIM_START_A = "1971-10-01"
SIM_END_A = "2018-09-30"
PRODUCT_A_START_WY = 1972
PRODUCT_A_END_WY = 2018

# -- Config (Product B specific) ---------------------------------------
WYT_PRODUCT_B_DIR = str(_wyt_gen / "output" / "_1_calc_WYTs" / "Product_B")
SIM_IN_DIR_B = _rim_gen / "output" / "_3_qmap_product_b"
TRAIN_START_B = "1921-10-01"
TRAIN_END_B = "2021-09-30"
PRODUCT_B_START = "1921-10-31"
PRODUCT_B_END = "2021-09-30"


# -- Helpers -----------------------------------------------------------
def prepare_hybrid_input_files(input_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split hybrid_terms CSV into WYT and QMap DataFrames."""
    df = pd.read_csv(input_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = ["term_part_b", "term_part_c", "basin_wyt",
                "predictor_part_b", "predictor_part_c"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"{input_csv} missing columns {missing}. Found: {list(df.columns)}"
        )

    working = df.copy()
    for col in ("lower_bound", "upper_bound"):
        if col not in working.columns:
            working[col] = pd.NA

    wyt_df = working[["term_part_b", "term_part_c", "basin_wyt"]].drop_duplicates()

    qmap_df = (
        working[
            [
                "term_part_b", "term_part_c",
                "predictor_part_b", "predictor_part_c",
                "lower_bound", "upper_bound",
            ]
        ]
        .drop_duplicates()
        .rename(columns={"term_part_b": "target_part_b",
                         "term_part_c": "target_part_c"})
    )

    return wyt_df, qmap_df


def _to_sv_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert framework long-format target to Part B, Part C, Year, Month, Value."""
    return pd.DataFrame({
        "Part B": df["part_b"],
        "Part C": df["part_c"],
        "Year": df["date"].dt.year,
        "Month": df["date"].dt.month,
        "Value": df["wyt_monthly_avg"],
    })


####################################################################
### Part 1 - WYT Averaging ###
####################################################################

def run_wyt(product: str, prefix: str, wyt_terms_df: pd.DataFrame,
            base_dir: Path, wyt_intermediate_dir: Path) -> None:
    """Compute WYT monthly averages and write intermediate per-product CSVs.

    Naming convention for the per-term WYT intermediate file:
      A: ``<part_b>_product_a_<wy_min>_<wy_max>.csv`` (wy_min/max from framework)
      B: ``<part_b>_product_b_<tag>.csv`` (tag = n01 .. n10 per stochastic chunk)
    """
    wyt_csv = base_dir / "_wyt_terms_tmp.csv"
    base_dir.mkdir(parents=True, exist_ok=True)
    wyt_terms_df.to_csv(wyt_csv, index=False)

    print("Reading DSS and computing historical pattern...")
    pattern_df, hist_cmp_df, pat_wide, term_specs = compute_wyt_pattern(
        term_specs_csv=str(wyt_csv),
        historical_dssfile=DSS_FILE,
        dss_read_start=DSS_READ_START,
        dss_read_end=DSS_READ_END,
        wyt_input_dir=WYT_HIST_DIR,
    )

    basin_tags = sorted({spec.wyt_tag for spec in term_specs})
    print(f"Using basin_wyt values from CSV: {', '.join(basin_tags)}")

    # Write historical diagnostics
    hist_dir = base_dir / "hybrid_wyt_monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)
    pattern_df.to_csv(hist_dir / f"{prefix}_pattern_by_wyt_month.csv", index=False)
    hist_cmp_df.to_csv(hist_dir / f"{prefix}_actual_vs_reconstructed.csv", index=False)
    print(f"  Historical pattern: {hist_dir}")

    print(f"\n{'='*60}\nComputing Product {product} WYT targets\n{'='*60}")
    targets = compute_product_targets(
        product=product,
        wyt_target_dir=WYT_PRODUCT_A_DIR if product == "A" else WYT_PRODUCT_B_DIR,
        pat_wide=pat_wide,
        term_specs=term_specs,
    )

    wyt_intermediate_dir.mkdir(parents=True, exist_ok=True)
    for name, df in targets.items():
        sv = _to_sv_format(df)
        if product == "A":
            wy_min = int(df["date"].apply(water_year).min())
            wy_max = int(df["date"].apply(water_year).max())
            for part_b, grp in sv.groupby("Part B"):
                out = wyt_intermediate_dir / f"{part_b}_product_a_{wy_min}_{wy_max}.csv"
                grp.to_csv(out, index=False)
                print(f"  - {out}")
        else:  # B
            tag = name.replace("product_b_", "")
            for part_b, grp in sv.groupby("Part B"):
                out = wyt_intermediate_dir / f"{part_b}_product_b_{tag}.csv"
                grp.to_csv(out, index=False)
                print(f"  - {out}")

    wyt_csv.unlink(missing_ok=True)


####################################################################
### Part 2 - Quantile Mapping ###
####################################################################

def run_qmap_a(qmap_pairs_df: pd.DataFrame, base_dir: Path,
               qmap_intermediate_dir: Path) -> None:
    """Run Product A QM and write CalSim-format intermediates."""
    qmap_csv = base_dir / "_qmap_pairs_tmp.csv"
    base_dir.mkdir(parents=True, exist_ok=True)
    qmap_pairs_df.to_csv(qmap_csv, index=False)

    qmap_intermediate_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as _tmp_detail:
        run_product_a_qmap_from_pairs(
            pair_csv=qmap_csv,
            dss_file=DSS_FILE,
            product_a_rim_csv=PRODUCT_A_RIM_CSV,
            output_dir=_tmp_detail,
            validation_dir=str(qmap_intermediate_dir),
            train_start=TRAIN_START_A,
            train_end=TRAIN_END_A,
            sim_start=SIM_START_A,
            sim_end=SIM_END_A,
        )

    qmap_csv.unlink(missing_ok=True)
    print(f"  QMap intermediates written to: {qmap_intermediate_dir}")


def run_qmap_b(qmap_pairs_df: pd.DataFrame, base_dir: Path,
               qmap_intermediate_dir: Path) -> None:
    """Run Product B QM and reformat per-chunk detail CSVs into SV format."""
    qmap_csv = base_dir / "_qmap_pairs_tmp.csv"
    base_dir.mkdir(parents=True, exist_ok=True)
    qmap_pairs_df.to_csv(qmap_csv, index=False)

    run_product_b_qmap_from_pairs(
        pair_csv=str(qmap_csv),
        dss_file=DSS_FILE,
        sim_in_dir=str(SIM_IN_DIR_B),
        out_dir=str(base_dir),
        train_start=TRAIN_START_B,
        train_end=TRAIN_END_B,
        product_b_start=PRODUCT_B_START,
        product_b_end=PRODUCT_B_END,
        output_tag="qmap",
    )

    # Reformat per-chunk detail CSVs into SV-format intermediates
    qmap_intermediate_dir.mkdir(parents=True, exist_ok=True)
    df_pairs = read_qmap_pairs(qmap_csv)
    timeseries_list = find_timeseries_in_dir(SIM_IN_DIR_B)

    total = 0
    for ts in timeseries_list:
        for _, row in df_pairs.iterrows():
            target_b = row["target_part_b"]
            target_c = row["target_part_c"]
            src_fname = build_output_filename(target_b, ts, output_tag="qmap")
            src_path = base_dir / src_fname
            if not src_path.exists():
                continue

            df = pd.read_csv(src_path)
            src_path.unlink()
            final_df = pd.DataFrame({
                "Part B": target_b,
                "Part C": target_c,
                "Year": df["year"].astype(int),
                "Month": df["month"].astype(int),
                "Value": df["target_qm_sim"],
            })
            final_df.to_csv(
                qmap_intermediate_dir / f"{target_b}_product_b_{ts}.csv",
                index=False,
            )
            total += 1
        print(f"  {ts}: wrote QMap intermediate CSV(s)")

    qmap_csv.unlink(missing_ok=True)
    print(f"  QMap intermediates: {total} file(s)")


####################################################################
### Part 3 - Final Hybrid = (WYT + QMap) / 2 ###
####################################################################

def run_final_hybrid_a(wyt_intermediate_dir: Path, qmap_intermediate_dir: Path,
                       final_dir: Path) -> None:
    """Average WYT and QMap results and write final Product A CSVs."""
    final_dir.mkdir(parents=True, exist_ok=True)

    terms_df = pd.read_csv(HYBRID_TERMS_CSV)
    terms_df.columns = [str(c).strip().lower() for c in terms_df.columns]
    terms = terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    total = 0
    for _, term in terms.iterrows():
        part_b = str(term["term_part_b"]).strip()
        part_c = str(term["term_part_c"]).strip()

        # WYT intermediate: named with wy_min/wy_max from framework
        wyt_candidates = sorted(
            wyt_intermediate_dir.glob(f"{part_b}_product_a_*.csv")
        )
        if not wyt_candidates:
            raise FileNotFoundError(
                f"No WYT Product A intermediate found for {part_b} in "
                f"{wyt_intermediate_dir}"
            )
        wyt_path = wyt_candidates[0]

        # QMap intermediate: named with start/end WY from qmap utility
        qmap_path = (
            qmap_intermediate_dir
            / f"{part_b}_productA_{PRODUCT_A_START_WY}_{PRODUCT_A_END_WY}.csv"
        )
        if not qmap_path.exists():
            raise FileNotFoundError(
                f"Missing QMap Product A intermediate for {part_b}: {qmap_path}"
            )

        df_wyt = pd.read_csv(wyt_path)
        df_qmap = pd.read_csv(qmap_path)

        merged = df_wyt[["Year", "Month", "Value"]].merge(
            df_qmap[["Year", "Month", "Value"]],
            on=["Year", "Month"],
            how="inner",
            suffixes=("_wyt", "_qmap"),
        )

        if merged.empty:
            raise ValueError(
                f"No overlapping Year/Month between WYT and QMap for "
                f"{part_b}/{part_c}"
            )

        out_df = pd.DataFrame({
            "Part B": part_b,
            "Part C": part_c,
            "Year": merged["Year"].astype(int),
            "Month": merged["Month"].astype(int),
            "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
        })

        out_path = (
            final_dir
            / f"{part_b}_product_a_{PRODUCT_A_START_WY}_{PRODUCT_A_END_WY}.csv"
        )
        out_df.to_csv(out_path, index=False)
        print(f"  - {out_path}")
        total += 1

    print(f"  Final hybrid: {total} file(s) written to {final_dir}")


def run_final_hybrid_b(wyt_intermediate_dir: Path, qmap_intermediate_dir: Path,
                       final_dir: Path) -> None:
    """Average WYT and QMap results per chunk and write final Product B CSVs."""
    final_dir.mkdir(parents=True, exist_ok=True)

    terms_df = pd.read_csv(HYBRID_TERMS_CSV)
    terms_df.columns = [str(c).strip().lower() for c in terms_df.columns]
    terms = terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    # Detect available timeseries tags from WYT output
    tags = set()
    for path in sorted(wyt_intermediate_dir.glob("*_product_b_*.csv")):
        idx = path.stem.rfind("_product_b_")
        if idx >= 0:
            tags.add(path.stem[idx + len("_product_b_"):])
    tags = sorted(tags)
    if not tags:
        raise FileNotFoundError(
            f"No WYT Product B files in {wyt_intermediate_dir}"
        )

    total = 0
    for ts in tags:
        for _, term in terms.iterrows():
            part_b = str(term["term_part_b"]).strip()
            part_c = str(term["term_part_c"]).strip()

            wyt_path = wyt_intermediate_dir / f"{part_b}_product_b_{ts}.csv"
            if not wyt_path.exists():
                raise FileNotFoundError(
                    f"Missing WYT file for {part_b} {ts}: {wyt_path}"
                )

            qmap_path = qmap_intermediate_dir / f"{part_b}_product_b_{ts}.csv"
            if not qmap_path.exists():
                raise FileNotFoundError(
                    f"Missing QMap file for {part_b} {ts}: {qmap_path}"
                )

            df_wyt = pd.read_csv(wyt_path)
            df_qmap = pd.read_csv(qmap_path)

            merged = df_wyt[["Year", "Month", "Value"]].merge(
                df_qmap[["Year", "Month", "Value"]],
                on=["Year", "Month"],
                how="inner",
                suffixes=("_wyt", "_qmap"),
            )

            if merged.empty:
                raise ValueError(
                    f"No overlapping Year/Month for {part_b}/{part_c} in {ts}"
                )

            out_df = pd.DataFrame({
                "Part B": part_b,
                "Part C": part_c,
                "Year": merged["Year"].astype(int),
                "Month": merged["Month"].astype(int),
                "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
            })
            out_df.to_csv(final_dir / f"{part_b}_product_b_{ts}.csv", index=False)
            total += 1

        print(f"  {ts}: wrote final hybrid CSV(s)")

    print(f"  Final hybrid: {total} file(s) written to {final_dir}")


####################################################################
### Main ###
####################################################################

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upper watershed hybrid terms = (WYT_avg + QMap) / 2"
                    " (Product A or Product B)",
    )
    parser.add_argument(
        "--product", choices=["A", "B"], required=True,
        help="Product to generate: A (1972-2018 historical validation; one "
             "continuous series per term) or B (10 stochastic chunks).",
    )
    args = parser.parse_args()

    if args.product == "A":
        base_dir = _gen / "output" / "_3_hybrid" / "product_a"
        final_dir = _gen / "output" / "_product_a_validation"
    else:
        base_dir = _gen / "output" / "_3_hybrid" / "product_b"
        final_dir = _gen / "output" / "_product_b_final"

    wyt_intermediate_dir = base_dir / "hybrid_wyt"
    qmap_intermediate_dir = base_dir / "hybrid_qmap"

    wyt_terms_df, qmap_pairs_df = prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    print(f"\n=== Part 1: WYT Averaging (Product {args.product}) ===")
    run_wyt(args.product, OUTPUT_PREFIX, wyt_terms_df,
            base_dir, wyt_intermediate_dir)

    print(f"\n=== Part 2: Quantile Mapping (Product {args.product}) ===")
    if args.product == "A":
        run_qmap_a(qmap_pairs_df, base_dir, qmap_intermediate_dir)
    else:
        run_qmap_b(qmap_pairs_df, base_dir, qmap_intermediate_dir)

    print(f"\n=== Part 3: Final Hybrid (Product {args.product}) ===")
    if args.product == "A":
        run_final_hybrid_a(wyt_intermediate_dir, qmap_intermediate_dir, final_dir)
    else:
        run_final_hybrid_b(wyt_intermediate_dir, qmap_intermediate_dir, final_dir)


if __name__ == "__main__":
    main()
