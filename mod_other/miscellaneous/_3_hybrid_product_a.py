"""
Build Product A Hybrid Terms (miscellaneous)
============================================
Hybrid = (WYT_avg + QMap) / 2.

For each term in hybrid_terms_miscellaneous.csv, this script:
  1. Computes WYT monthly averages for Product A (1972-2018)
  2. Runs Product A quantile mapping using matched rim inflow predictors
  3. Averages the two results to produce final hybrid values

Intermediate outputs:  output/_3_hybrid_product_a/
Final Product A CSVs:  output/_product_a_validation/
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets, water_year
from utils.qmap_product_a_from_pairs import run_product_a_qmap_from_pairs

# -- Paths --------------------------------------------------------------
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/miscellaneous")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

# -- Config -------------------------------------------------------------
DSS_FILE = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
HYBRID_TERMS_CSV = (
    _REPO_DIR / "mod_other" / "miscellaneous" / "reference"
    / "hybrid_terms_miscellaneous.csv"
)
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"
OUTPUT_PREFIX = "miscellaneous"
WYT_HIST_DIR = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")
WYT_PRODUCT_A_DIR = str(_wyt_gen / "output" / "_1_calc_WYTs" / "Product_A")
PRODUCT_A_RIM_CSV = (
    _rim_gen / "output" / "_2_qmap_historical_validation"
    / "_product_a_validation" / "_riminflow_productA_1972_2018.csv"
)

# Product A time window (matching _4_qmap.py --product A)
TRAIN_START = "1921-10-01"
TRAIN_END = "1971-09-30"
SIM_START = "1971-10-01"
SIM_END = "2018-09-30"
PRODUCT_A_START_WY = 1972
PRODUCT_A_END_WY = 2018

# -- Output directories ------------------------------------------------
BASE_RESULTS_DIR = _gen / "output" / "_3_hybrid_product_a"
WYT_INTERMEDIATE_DIR = BASE_RESULTS_DIR / "hybrid_wyt_product_a"
QMAP_INTERMEDIATE_DIR = BASE_RESULTS_DIR / "hybrid_qmap_product_a"    # CalSim-format CSVs (Part 3 input)
FINAL_DIR = _gen / "output" / "_product_a_validation"


# -- Helpers ---------------------------------------------------------
def prepare_hybrid_input_files(input_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split hybrid_terms CSV into WYT and QMap DataFrames."""
    df = pd.read_csv(input_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = ["term_part_b", "term_part_c", "basin_wyt", "predictor_part_b", "predictor_part_c"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{input_csv} missing columns {missing}. Found: {list(df.columns)}")

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
        .rename(columns={"term_part_b": "target_part_b", "term_part_c": "target_part_c"})
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
### Part 1 - WYT Averaging (Product A) ###
####################################################################

def run_wyt_product_a(prefix: str, wyt_terms_df: pd.DataFrame) -> None:
    """Compute WYT monthly averages and write intermediate Product A CSVs."""
    wyt_csv = BASE_RESULTS_DIR / "_wyt_terms_tmp.csv"
    BASE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
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
    hist_dir = BASE_RESULTS_DIR / "hybrid_wyt_monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)
    pattern_df.to_csv(hist_dir / f"{prefix}_pattern_by_wyt_month.csv", index=False)
    hist_cmp_df.to_csv(hist_dir / f"{prefix}_actual_vs_reconstructed.csv", index=False)
    print(f"  Historical pattern: {hist_dir}")

    # Compute Product A targets
    print(f"\n{'='*60}\nComputing Product A WYT targets\n{'='*60}")
    targets = compute_product_targets(
        product="A",
        wyt_target_dir=WYT_PRODUCT_A_DIR,
        pat_wide=pat_wide,
        term_specs=term_specs,
    )

    WYT_INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in targets.items():
        sv = _to_sv_format(df)
        wy_min = int(df["date"].apply(water_year).min())
        wy_max = int(df["date"].apply(water_year).max())
        for part_b, grp in sv.groupby("Part B"):
            out = WYT_INTERMEDIATE_DIR / f"{part_b}_product_a_{wy_min}_{wy_max}.csv"
            grp.to_csv(out, index=False)
            print(f"  - {out}")

    wyt_csv.unlink(missing_ok=True)


####################################################################
### Part 2 - Quantile Mapping (Product A) ###
####################################################################

def run_qmap_product_a(qmap_pairs_df: pd.DataFrame) -> None:
    """Run Product A quantile mapping and write intermediate CSVs."""
    qmap_csv = BASE_RESULTS_DIR / "_qmap_pairs_tmp.csv"
    BASE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    qmap_pairs_df.to_csv(qmap_csv, index=False)

    QMAP_INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as _tmp_detail:
        run_product_a_qmap_from_pairs(
            pair_csv=qmap_csv,
            dss_file=DSS_FILE,
            product_a_rim_csv=PRODUCT_A_RIM_CSV,
            output_dir=_tmp_detail,
            validation_dir=str(QMAP_INTERMEDIATE_DIR),
            train_start=TRAIN_START,
            train_end=TRAIN_END,
            sim_start=SIM_START,
            sim_end=SIM_END,
        )

    qmap_csv.unlink(missing_ok=True)
    print(f"  QMap intermediates written to: {QMAP_INTERMEDIATE_DIR}")


####################################################################
### Part 3 - Final Hybrid = (WYT + QMap) / 2 ###
####################################################################

def run_final_hybrid(prefix: str) -> None:
    """Average WYT and QMap results and write final Product A CSVs."""
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    terms_df = pd.read_csv(HYBRID_TERMS_CSV)
    terms_df.columns = [str(c).strip().lower() for c in terms_df.columns]
    terms = terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    total = 0
    for _, term in terms.iterrows():
        part_b = str(term["term_part_b"]).strip()
        part_c = str(term["term_part_c"]).strip()

        # Locate WYT intermediate (named with wy_min/wy_max from framework)
        wyt_candidates = sorted(WYT_INTERMEDIATE_DIR.glob(f"{part_b}_product_a_*.csv"))
        if not wyt_candidates:
            raise FileNotFoundError(
                f"No WYT Product A intermediate found for {part_b} in {WYT_INTERMEDIATE_DIR}"
            )
        wyt_path = wyt_candidates[0]

        # Locate QMap intermediate (named with start/end WY from qmap utility)
        qmap_path = (
            QMAP_INTERMEDIATE_DIR
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
                f"No overlapping Year/Month between WYT and QMap for {part_b}/{part_c}"
            )

        out_df = pd.DataFrame({
            "Part B": part_b,
            "Part C": part_c,
            "Year": merged["Year"].astype(int),
            "Month": merged["Month"].astype(int),
            "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
        })

        out_path = FINAL_DIR / f"{part_b}_product_a_{PRODUCT_A_START_WY}_{PRODUCT_A_END_WY}.csv"
        out_df.to_csv(out_path, index=False)
        print(f"  - {out_path}")
        total += 1

    print(f"  Final hybrid: {total} file(s) written to {FINAL_DIR}")


####################################################################
### Main ###
####################################################################

def main() -> None:
    wyt_terms_df, qmap_pairs_df = prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    print("\n=== Part 1: WYT Averaging (Product A) ===")
    run_wyt_product_a(OUTPUT_PREFIX, wyt_terms_df)

    print("\n=== Part 2: Quantile Mapping (Product A) ===")
    run_qmap_product_a(qmap_pairs_df)

    print("\n=== Part 3: Final Hybrid (Product A) ===")
    run_final_hybrid(OUTPUT_PREFIX)


if __name__ == "__main__":
    main()
