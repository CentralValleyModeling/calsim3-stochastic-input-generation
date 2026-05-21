"""
Build Product B hybrid terms: Hybrid = (WYT_avg + QMap) / 2.

For each term in hybrid_terms_miscellaneous.csv, this script:
  1. Computes WYT monthly averages for Product B (10 chunks)
  2. Runs Product B quantile mapping using matched rim inflow predictors
  3. Averages the two results to produce final hybrid values

Intermediate outputs:  output/_3_hybrid/
Final Product B CSVs:  output/_product_b_final/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# %%
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets
from utils.qmap_product_b_from_pairs import (
    run_product_b_qmap_from_pairs,
    read_qmap_pairs,
    build_output_filename,
    find_timeseries_in_dir,
)

# ── Paths ──────────────────────────────────────────────────────────────
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/miscellaneous")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")
_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")

# ── Config ─────────────────────────────────────────────────────────────
DSS_FILE = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
HYBRID_TERMS_CSV = (
    _REPO_DIR / "mod_other" / "miscellaneous" / "reference" / "hybrid_terms_miscellaneous.csv"
)
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"
OUTPUT_PREFIX = "miscellaneous"
WYT_HIST_DIR = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")
WYT_PRODUCT_B_DIR = str(_wyt_gen / "output" / "_1_calc_WYTs" / "Product_B")
SIM_IN_DIR = _rim_gen / "output" / "_3_qmap_product_b"

# ── Output directories ────────────────────────────────────────────────
BASE_RESULTS_DIR = _gen / "output" / "_3_hybrid_product_b"
WYT_INTERMEDIATE_DIR = BASE_RESULTS_DIR / "hybrid_WYT_product_b"
QMAP_INTERMEDIATE_DIR = BASE_RESULTS_DIR / "hybrid_qmap_product_b"
FINAL_DIR = _gen / "output" / "_product_b_final"


# %% ── Helpers ─────────────────────────────────────────────────────────
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

    qmap_df = working[
        ["term_part_b", "term_part_c", "predictor_part_b", "predictor_part_c", "lower_bound", "upper_bound"]
    ].drop_duplicates().rename(columns={"term_part_b": "target_part_b", "term_part_c": "target_part_c"})

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


# %%
####################################################################
### Part 1 - WYT Averaging (Product B) ###
####################################################################

def run_wyt_product_b(prefix: str, wyt_terms_df: pd.DataFrame) -> None:
    """Compute WYT monthly averages and write intermediate Product B CSVs."""
    # Write a temporary CSV for the framework (expects a file path)
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
    hist_dir = BASE_RESULTS_DIR / "hybrid_WYT_monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)
    pattern_df.to_csv(hist_dir / f"{prefix}_pattern_by_WYT_month.csv", index=False)
    hist_cmp_df.to_csv(hist_dir / f"{prefix}_actual_vs_reconstructed.csv", index=False)
    print(f"  Historical pattern: {hist_dir}")

    # Compute Product B targets
    print(f"\n{'='*60}\nComputing Product B WYT targets\n{'='*60}")
    targets = compute_product_targets(
        product="B",
        wyt_target_dir=WYT_PRODUCT_B_DIR,
        pat_wide=pat_wide,
        term_specs=term_specs,
    )

    WYT_INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in targets.items():
        sv = _to_sv_format(df)
        tag = name.replace("product_b_", "")
        for part_b, grp in sv.groupby("Part B"):
            out = WYT_INTERMEDIATE_DIR / f"{part_b}_product_b_{tag}.csv"
            grp.to_csv(out, index=False)
            print(f"  - {out}")

    wyt_csv.unlink(missing_ok=True)


# %%
####################################################################
### Part 2 - Quantile Mapping (Product B) ###
####################################################################

def run_qmap_product_b(qmap_pairs_df: pd.DataFrame) -> None:
    """Run Product B quantile mapping and write intermediate CSVs."""
    # Write a temporary CSV for the framework (expects a file path)
    qmap_csv = BASE_RESULTS_DIR / "_qmap_pairs_tmp.csv"
    BASE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    qmap_pairs_df.to_csv(qmap_csv, index=False)

    run_product_b_qmap_from_pairs(
        pair_csv=str(qmap_csv),
        dss_file=DSS_FILE,
        sim_in_dir=str(SIM_IN_DIR),
        out_dir=str(BASE_RESULTS_DIR),
        train_start="1921-10-01",
        train_end="2021-09-30",
        product_b_start="1921-10-31",
        product_b_end="2021-09-30",
        output_tag="qmap",
    )

    # Reformat into SV-format intermediates
    QMAP_INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    df_pairs = read_qmap_pairs(qmap_csv)
    timeseries_list = find_timeseries_in_dir(SIM_IN_DIR)

    total = 0
    for ts in timeseries_list:
        for _, row in df_pairs.iterrows():
            target_b = row["target_part_b"]
            target_c = row["target_part_c"]
            src_fname = build_output_filename(target_b, ts, output_tag="qmap")
            src_path = BASE_RESULTS_DIR / src_fname
            if not src_path.exists():
                continue

            df = pd.read_csv(src_path)
            src_path.unlink()
            final_df = pd.DataFrame({
                "Part B": target_b,
                "Part C": target_c,
                "Year": df["Year"].astype(int),
                "Month": df["Month"].astype(int),
                "Value": df["qmap_target"],
            })
            final_df.to_csv(QMAP_INTERMEDIATE_DIR / f"{target_b}_product_b_{ts}.csv", index=False)
            total += 1

        print(f"  {ts}: wrote QMap intermediate CSV(s)")

    qmap_csv.unlink(missing_ok=True)
    print(f"  QMap intermediates: {total} file(s)")


# %%
####################################################################
### Part 3 - Final Hybrid = (WYT + QMap) / 2 ###
####################################################################

def run_final_hybrid(prefix: str) -> None:
    """Average WYT and QMap results and write final Product B CSVs."""
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    terms_df = pd.read_csv(HYBRID_TERMS_CSV)
    terms_df.columns = [str(c).strip().lower() for c in terms_df.columns]
    terms = terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    # Detect available timeseries tags from WYT output
    tags = set()
    for path in sorted(WYT_INTERMEDIATE_DIR.glob("*_product_b_*.csv")):
        idx = path.stem.rfind("_product_b_")
        if idx >= 0:
            tags.add(path.stem[idx + len("_product_b_"):])
    tags = sorted(tags)
    if not tags:
        raise FileNotFoundError(f"No WYT Product B files in {WYT_INTERMEDIATE_DIR}")

    total = 0
    for ts in tags:
        for _, term in terms.iterrows():
            part_b = str(term["term_part_b"]).strip()
            part_c = str(term["term_part_c"]).strip()

            wyt_path = WYT_INTERMEDIATE_DIR / f"{part_b}_product_b_{ts}.csv"
            if not wyt_path.exists():
                raise FileNotFoundError(f"Missing WYT file for {part_b} {ts}: {wyt_path}")

            qmap_path = QMAP_INTERMEDIATE_DIR / f"{part_b}_product_b_{ts}.csv"
            if not qmap_path.exists():
                raise FileNotFoundError(f"Missing QMap file for {part_b} {ts}: {qmap_path}")

            df_wyt = pd.read_csv(wyt_path)
            df_qmap = pd.read_csv(qmap_path)

            merged = df_wyt[["Year", "Month", "Value"]].merge(
                df_qmap[["Year", "Month", "Value"]],
                on=["Year", "Month"],
                how="inner",
                suffixes=("_wyt", "_qmap"),
            )

            if merged.empty:
                raise ValueError(f"No overlapping Year/Month for {part_b}/{part_c} in {ts}")

            out_df = pd.DataFrame({
                "Part B": part_b,
                "Part C": part_c,
                "Year": merged["Year"].astype(int),
                "Month": merged["Month"].astype(int),
                "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
            })
            out_df.to_csv(FINAL_DIR / f"{part_b}_product_b_{ts}.csv", index=False)
            total += 1

        print(f"  {ts}: wrote final hybrid CSV(s)")

    print(f"  Final hybrid: {total} file(s) written to {FINAL_DIR}")


# %%
####################################################################
### Main ###
####################################################################

def main() -> None:
    wyt_terms_df, qmap_pairs_df = prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    print("\n=== Part 1: WYT Averaging (Product B) ===")
    run_wyt_product_b(OUTPUT_PREFIX, wyt_terms_df)

    print("\n=== Part 2: Quantile Mapping (Product B) ===")
    run_qmap_product_b(qmap_pairs_df)

    print("\n=== Part 3: Final Hybrid (Product B) ===")
    run_final_hybrid(OUTPUT_PREFIX)


if __name__ == "__main__":
    main()
