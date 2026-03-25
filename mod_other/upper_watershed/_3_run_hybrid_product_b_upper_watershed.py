
"""
This script builds Product_B hybrid terms timeseries by running both WYT-averaging and QMap workflows.
It reads one input reference file (hybrid_terms.csv), creates the needed runtime inputs for each method, 
and generates intermediate monthly outputs.
Then it computes the final hybrid values term-by-term and timeseries-by-timeseries 
using: Hybrid = (WYT_avg + QMap) / 2.
It writes final files to the Hybrid_product_b_Final folder and removes all intermediate outputs afterward.

"""

from __future__ import annotations
import shutil
import sys
from pathlib import Path
import pandas as pd

# %%
####################################################################
### Part 1 - Calculate WYT averaging ###
####################################################################

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir
from utils.wyt_monthlyavg_framework import compute_wyt_pattern, compute_product_targets, water_year


_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/upper_watershed")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# %% ── CONFIG ───────────────────────────────────────────────────────────
dss_file = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
HYBRID_TERMS_CSV = (
    _REPO_DIR / "mod_other" / "upper_watershed" / "reference" / "hybrid_terms_upper_watershed.csv"
)

# Historical DSS date window used to build the monthly index.
DSS_READ_START = "1921-10-31"
DSS_READ_END = "2021-09-30"

# Output prefix for filenames.
OUTPUT_PREFIX = "upper_watershed"

# The term spec CSV now controls the WYT basin for each term.
# Required columns in wyt_avg_terms.csv:
#   - term_part_b
#   - term_part_c
#   - basin_wyt    (sj or sac; can vary by term)

# Choose target WGEN product(s):
#    "both" -> run Product A then Product B (default)
#    "A"    -> one WYT series (1972–2018)
#    "B"    -> ALWAYS n01..n10; WY 1922–2021
TARGET_PRODUCT = "Both"

_WYT_INPUT_DIRS = {"A": "Product_A", "B": "Product_B"}
_OUTPUT_DIRS = {"A": "hybrid_WYT_product_a", "B": "hybrid_WYT_product_b"}

# Where the historical WYT CSVs live
wyt_hist_dir = str(_REPO_DIR / "mod_hydrology" / "water_year_types" / "reference")

# %% ── RESULTS ROOT ─────────────────────────────────────────────────────
BASE_RESULTS_DIR = _gen / "output"/"_3_run_hybrid_upper_watershed"
RUNTIME_INPUT_DIR = BASE_RESULTS_DIR / "_runtime_inputs"
WYT_RUNTIME_CSV = RUNTIME_INPUT_DIR / "hybrid_wyt_avg_terms.csv"
QMAP_RUNTIME_CSV = RUNTIME_INPUT_DIR / "hybrid_qmap_pairs.csv"
terms_csv = str(WYT_RUNTIME_CSV)

############################################################################################
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

#############################################################################################

def prepare_hybrid_input_files(input_csv: Path) -> tuple[Path, Path]:
    """Build WYT and QMap runtime CSVs from a single hybrid_terms_upper_watershed.csv input."""
    df = pd.read_csv(input_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = [
        "term_part_b",
        "term_part_c",
        "basin_wyt",
        "predictor_part_b",
        "predictor_part_c",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"{input_csv} is missing required columns {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    working = df.copy()
    for col in ("lower_bound", "upper_bound"):
        if col not in working.columns:
            working[col] = pd.NA

    RUNTIME_INPUT_DIR.mkdir(parents=True, exist_ok=True)

    wyt_df = working[["term_part_b", "term_part_c", "basin_wyt"]].drop_duplicates().copy()
    qmap_df = working[
        [
            "term_part_b",
            "term_part_c",
            "predictor_part_b",
            "predictor_part_c",
            "lower_bound",
            "upper_bound",
        ]
    ].drop_duplicates().rename(
        columns={
            "term_part_b": "target_part_b",
            "term_part_c": "target_part_c",
        }
    )

    wyt_df.to_csv(WYT_RUNTIME_CSV, index=False)
    qmap_df.to_csv(QMAP_RUNTIME_CSV, index=False)

    return WYT_RUNTIME_CSV, QMAP_RUNTIME_CSV

def _to_sv_format(df: pd.DataFrame) -> pd.DataFrame:
    """Convert framework long-format target to Part B,Part C,Year,Month,Value."""
    out = pd.DataFrame({
        "Part B": df["part_b"],
        "Part C": df["part_c"],
        "Year": df["date"].dt.year,
        "Month": df["date"].dt.month,
        "Value": df["wyt_monthly_avg"],
    })
    return out


def _write_targets(product_key: str, prefix: str, targets) -> None:
    """Write final SV-format CSVs (Part B, Part C, Year, Month, Value)."""
    prod_dir = BASE_RESULTS_DIR / _OUTPUT_DIRS[product_key]

    print(f"\nProduct {product_key} targets:")

    if product_key == "B":
        final_dir = prod_dir / "hybrid_WYT_product_b_final"
        final_dir.mkdir(parents=True, exist_ok=True)
        for name, df in targets.items():
            sv = _to_sv_format(df)
            tag = name.replace("product_b_", "")  # e.g. "n01"
            out = final_dir / f"{prefix}_productB_qmo_{tag}.csv"
            sv.to_csv(out, index=False)
            print(f"  - {out}")

    elif product_key == "A":
        val_dir = prod_dir / "hybrid_WYT_product_a_validation"
        val_dir.mkdir(parents=True, exist_ok=True)
        for name, df in targets.items():
            sv = _to_sv_format(df)
            wy_min = int(df["date"].apply(water_year).min())
            wy_max = int(df["date"].apply(water_year).max())
            out = val_dir / f"{prefix}_productA_{wy_min}_{wy_max}.csv"
            sv.to_csv(out, index=False)
            print(f"  - {out}")



def main() -> None:
    _install_pandas_me_compat()
    prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    prefix = OUTPUT_PREFIX.strip() if OUTPUT_PREFIX else Path(terms_csv).stem
    choice = TARGET_PRODUCT.strip().upper()

    if choice == "BOTH":
        products = ["A", "B"]
    elif choice in ("A", "B"):
        products = [choice]
    else:
        raise ValueError(f"TARGET_PRODUCT must be 'A', 'B', or 'both', got '{TARGET_PRODUCT}'")

    # Read DSS and compute pattern once
    print("Reading DSS and computing historical pattern...")
    pattern_df, hist_cmp_df, pat_wide, term_specs = compute_wyt_pattern(
        term_specs_csv=terms_csv,
        historical_dssfile=dss_file,
        dss_read_start=DSS_READ_START,
        dss_read_end=DSS_READ_END,
        wyt_input_dir=wyt_hist_dir,
    )

    basin_tags = sorted({spec.wyt_tag for spec in term_specs})
    print(f"Using basin_wyt values from CSV: {', '.join(basin_tags)}")

    # Write historical outputs (same for all products)
    hist_dir = BASE_RESULTS_DIR / "hybrid_WYT_monthly_avg_historical"
    hist_dir.mkdir(parents=True, exist_ok=True)

    pattern_path = hist_dir / f"{prefix}_pattern_by_WYT_month.csv"
    pattern_df.to_csv(pattern_path, index=False)

    hist_cmp_path = hist_dir / f"{prefix}_actual_vs_reconstructed.csv"
    hist_cmp_df.to_csv(hist_cmp_path, index=False)

    print(f"\nHistorical outputs:")
    print(f"  - {pattern_path}")
    print(f"  - {hist_cmp_path}")

    # Compute and write targets per product
    for prod_key in products:
        print(f"\n{'='*60}\nComputing Product {prod_key} targets\n{'='*60}")
        wyt_product_dir = str(
            _wyt_gen / "output" / "_1_calc_WYTs" / _WYT_INPUT_DIRS[prod_key]
        )
        targets = compute_product_targets(
            product=prod_key,
            wyt_target_dir=wyt_product_dir,
            pat_wide=pat_wide,
            term_specs=term_specs,
        )
        _write_targets(prod_key, prefix, targets)


if __name__ == "__main__":
    main()

##############################################################################################
##############################################################################################
#%% 
####################################################################
### Part 2 - Calculate Qmap ###
####################################################################

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

PAIR_CSV = QMAP_RUNTIME_CSV
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
SIM_IN_DIR = _rim_gen / "output" / "_3_qmap_product_b"
OUT_DIR = _gen / "output" / "_3_run_hybrid_upper_watershed"
FINAL_DIR = _gen / "output" / "_3_run_hybrid_upper_watershed"/ "hybrid_qmap_product_b_final"


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


#%%
####################################################################
### Part 3 - Calculate Final Hybrid Product B ###
####################################################################

HYBRID_WYT_FINAL_DIR = _gen / "output" / "_3_run_hybrid_upper_watershed" / "hybrid_WYT_product_b" / "hybrid_WYT_product_b_final"
HYBRID_QMAP_FINAL_DIR = _gen / "output" / "_3_run_hybrid_upper_watershed" / "hybrid_qmap_product_b_final"
HYBRID_FINAL_DIR = _gen / "output" / "_3_run_hybrid_upper_watershed" / "Hybrid_product_b_Final"


def read_final_hybrid_terms(input_csv: Path) -> pd.DataFrame:
    """Read target terms for the final hybrid step from hybrid_terms_upper_watershed.csv."""
    df = pd.read_csv(input_csv)
    df.columns = [str(c).strip().lower() for c in df.columns]

    required = ["term_part_b", "term_part_c"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"{input_csv} is missing required columns {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    terms = df[["term_part_b", "term_part_c"]].drop_duplicates().rename(
        columns={"term_part_b": "part_b", "term_part_c": "part_c"}
    )
    if terms.empty:
        raise ValueError(f"No hybrid terms were found in {input_csv}.")

    return terms.reset_index(drop=True)


def find_hybrid_wyt_tags(wyt_dir: Path) -> list[str]:
    """Find available Product B timeseries tags from the WYT output folder."""
    tags = []
    for path in sorted(wyt_dir.glob("*_productB_qmo_*.csv")):
        stem = path.stem
        if "_qmo_" in stem:
            tags.append(stem.split("_qmo_")[-1])
    return tags


def write_final_hybrid_product_b(
    terms: pd.DataFrame,
    wyt_dir: Path,
    qmap_dir: Path,
    final_dir: Path,
) -> None:
    """Write final hybrid Product B files by averaging WYT and QMap results."""
    final_dir.mkdir(parents=True, exist_ok=True)

    tags = find_hybrid_wyt_tags(wyt_dir)
    if not tags:
        raise FileNotFoundError(
            f"No WYT Product B files found in {wyt_dir}. "
            "Run the hybrid WYT section first."
        )

    total_written = 0

    for ts in tags:
        wyt_path = wyt_dir / f"{OUTPUT_PREFIX}_productB_qmo_{ts}.csv"
        if not wyt_path.exists():
            raise FileNotFoundError(
                "Final hybrid Product B cannot continue because the required "
                f"WYT file is missing for timeseries {ts}: {wyt_path}"
            )

        df_wyt = pd.read_csv(wyt_path)
        df_wyt.columns = [str(c).strip() for c in df_wyt.columns]

        for _, term in terms.iterrows():
            part_b = str(term["part_b"]).strip()
            part_c = str(term["part_c"]).strip()

            qmap_path = qmap_dir / f"{part_b}_productB_{ts}.csv"
            if not qmap_path.exists():
                raise FileNotFoundError(
                    "Final hybrid Product B cannot continue because the required "
                    f"QMap file is missing for term {part_b} / {part_c} and timeseries {ts}: "
                    f"{qmap_path}"
                )

            df_qmap = pd.read_csv(qmap_path)
            df_qmap.columns = [str(c).strip() for c in df_qmap.columns]

            mask = (
                df_wyt["Part B"].astype(str).str.strip().str.upper().eq(part_b.upper())
                & df_wyt["Part C"].astype(str).str.strip().str.upper().eq(part_c.upper())
            )
            df_wyt_term = df_wyt.loc[mask, ["Year", "Month", "Value"]].copy()

            if df_wyt_term.empty:
                raise ValueError(
                    "Final hybrid Product B cannot continue because the required "
                    f"WYT term {part_b} / {part_c} was not found in file {wyt_path} "
                    f"for timeseries {ts}."
                )

            df_qmap_term = df_qmap[["Year", "Month", "Value"]].copy()

            merged = df_wyt_term.merge(
                df_qmap_term,
                on=["Year", "Month"],
                how="inner",
                suffixes=("_wyt", "_qmap"),
            )

            if merged.empty:
                raise ValueError(
                    "Final hybrid Product B cannot continue because there are no overlapping "
                    f"Year/Month rows between WYT and QMap for term {part_b} / {part_c} "
                    f"in timeseries {ts}."
                )

            out_df = pd.DataFrame({
                "Part B": part_b,
                "Part C": part_c,
                "Year": merged["Year"].astype(int),
                "Month": merged["Month"].astype(int),
                "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
            })

            out_path = final_dir / f"{part_b}_productB_hybrid_{ts}.csv"
            out_df.to_csv(out_path, index=False)
            total_written += 1

        print(f"  {ts}: wrote final hybrid Product B CSV(s)")

    print(f"  Final hybrid Product B: {total_written} file(s) written to {final_dir}")


def cleanup_generated_outputs(base_dir: Path, keep_dir: Path) -> None:
    """Delete generated files and folders under base_dir, except keep_dir and its contents."""
    base_dir.mkdir(parents=True, exist_ok=True)
    keep_resolved = keep_dir.resolve()

    for child in base_dir.iterdir():
        if child.resolve() == keep_resolved:
            continue

        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    print(f"  Cleanup complete. Kept final results in {keep_dir}")


def main() -> None:
    _install_pandas_me_compat()
    _, pair_csv = prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    run_product_b_qmap_from_pairs(
        pair_csv=str(pair_csv),
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
    write_product_b_final(OUT_DIR, FINAL_DIR, pair_csv)

    print("\nWriting final hybrid Product B CSVs ...")
    hybrid_terms = read_final_hybrid_terms(HYBRID_TERMS_CSV)
    write_final_hybrid_product_b(
        terms=hybrid_terms,
        wyt_dir=HYBRID_WYT_FINAL_DIR,
        qmap_dir=HYBRID_QMAP_FINAL_DIR,
        final_dir=HYBRID_FINAL_DIR,
    )

    print("\nCleaning up intermediate hybrid outputs ...")
    cleanup_generated_outputs(
        base_dir=_gen / "output" / "_3_run_hybrid_upper_watershed",
        keep_dir=HYBRID_FINAL_DIR,
    )


if __name__ == "__main__":
    main()



