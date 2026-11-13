"""
Upper Watershed Hybrid Terms = (WYT_avg + QMap) / 2
===================================================
Each term of reference/hybrid_terms_upper_watershed.csv (C_MFY044_SV) as the mean of its WYT
monthly average (utils.wyt_monthlyavg_framework) and its quantile map from a rim-inflow predictor
(utils.qmap_single_from_pairs for Historical_Unsplit and Product A,
utils.qmap_product_b_from_pairs for Product B).

The quantile map is fitted on WY1950-2018 by the term's fit (utils.qmap_fit): pass trains on the
CalSim3 predictor, absorb on the rim-inflow model's Historical_Unsplit predictor. A predictor
written I_A+I_B is the sum of those SVs. The WYT part applies the CalSim3 pattern to the year
types of the set.

Inputs
------
- reference/hybrid_terms_upper_watershed.csv: term_part_b, term_part_c, basin_wyt,
  predictor_part_b, predictor_part_c, fit, lower_bound, upper_bound
- <base>/CalSim3/__calsim_sv_default__.dss: the terms (WYT pattern, QM target) and the predictors
  of pass fits
- mod_hydrology/water_year_types/reference/_Historical_SacWYT.csv, _Historical_SJWYT.csv
- <generated>/mod_hydrology/water_year_types/output/_1_calc_WYTs/<set name>/: the set's WYT CSVs
- Rim-inflow SVs (utils.paths.get_rim_inflow_outputs): _riminflow_historicalUnsplit_1922_2018.csv,
  _riminflow_productA_1922_2018.csv, or <Part B>_qmo_n01.csv ... _n10.csv for Product B; the
  Historical_Unsplit calsim_qmap_validation_TS.csv for absorb fits

Outputs
-------
Under <generated>/mod_other/upper_watershed/output/:
- _3_hybrid/<historical_unsplit|product_a|product_b>/: hybrid_wyt/ and hybrid_qmap/ (the two
  parts per term), hybrid_wyt_monthly_avg_historical/ (pattern and baseline check)
- _3_hybrid/figures/<historical_unsplit|product_a>/<Part B>.png and <Part B>_monthly_error.png
- _historical_unsplit_validation/<Part B>_historicalUnsplit_1922_2018.csv,
  _product_a_validation/<Part B>_productA_1922_2018.csv
- _product_b_final/<Part B>_product_b_n01.csv ... _n10.csv (--product B)

Delivery and chunk CSVs: Part B, Part C, Year, Month, Value.

Dependencies
------------
utils.paths, utils.csv_io, utils.wgen_calendar, utils.wyt_monthlyavg_framework,
utils.qmap_single_from_pairs, utils.qmap_product_b_from_pairs; pydsstools

Usage
-----
    python mod_other/upper_watershed/_3_hybrid.py --product historical
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
from utils.csv_io import delivery_name, write_delivery_csv
from utils.paths import (DELIVERY, WEATHER_SETS, delivery_dir, get_base_dir, get_module_generated_dir,
                         get_rim_inflow_outputs)
from utils.wyt_monthlyavg_framework import (
    compute_wyt_pattern,
    compute_product_targets,
    product_b_target_table,
    plot_actual_vs_recon_validation,
    target_sv,
)
from utils.qmap_single_from_pairs import run_single_qmap_from_pairs
from utils.qmap_product_b_from_pairs import (
    PRODUCT_B_CHUNKS,
    run_product_b_qmap_from_pairs,
    write_product_b_sv,
)
from utils.wgen_calendar import write_chunk_csvs

# -- Paths --------------------------------------------------------------
_REPO_DIR = Path(__file__).resolve().parents[2]
_gen = get_module_generated_dir("mod_other/upper_watershed")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

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

# WYT targets by weather set: <WYT_DIR>/<set name>
WYT_DIR = _wyt_gen / "output" / "_1_calc_WYTs"

# -- Config (Product B specific) ---------------------------------------
SIM_IN_DIR_B = get_rim_inflow_outputs("B")["dir"]


# -- Helpers -----------------------------------------------------------
def read_terms(path: Path) -> pd.DataFrame:
    """The hybrid_terms CSV with lower-case column names, without the rows whose every cell is
    blank (a spreadsheet can leave them below the table)."""
    df = pd.read_csv(path).dropna(how="all")
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def prepare_hybrid_input_files(input_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split hybrid_terms CSV into WYT and QMap DataFrames."""
    df = read_terms(input_csv)

    required = ["term_part_b", "term_part_c", "basin_wyt",
                "predictor_part_b", "predictor_part_c", "fit"]
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
                "predictor_part_b", "predictor_part_c", "fit",
                "lower_bound", "upper_bound",
            ]
        ]
        .drop_duplicates()
        .rename(columns={"term_part_b": "target_part_b",
                         "term_part_c": "target_part_c"})
    )

    return wyt_df, qmap_df


def _load_final_single_as_long(final_dir: Path, product: str) -> pd.DataFrame:
    """Load the delivery CSVs of a single series into long format for
    plot_actual_vs_recon_validation."""
    frames = []
    for path in sorted(Path(final_dir).glob(f"*_{DELIVERY[product]['tag']}_*.csv")):
        df = pd.read_csv(path)
        df.columns = [str(c).strip() for c in df.columns]
        date = pd.to_datetime(
            dict(year=df["Year"].astype(int), month=df["Month"].astype(int), day=1)
        ) + pd.offsets.MonthEnd(0)
        frames.append(pd.DataFrame({
            "date": date,
            "part_b": df["Part B"].astype(str),
            "part_c": df["Part C"].astype(str),
            "wyt_monthly_avg": pd.to_numeric(df["Value"], errors="coerce"),
        }))
    if not frames:
        return pd.DataFrame(columns=["date", "part_b", "part_c", "wyt_monthly_avg"])
    return pd.concat(frames, ignore_index=True)


####################################################################
### Part 1 - WYT Averaging ###
####################################################################

def run_wyt(product: str, prefix: str, wyt_terms_df: pd.DataFrame,
            base_dir: Path, wyt_intermediate_dir: Path):
    """Compute WYT monthly averages and write intermediate per-product CSVs.

    Naming convention for the per-term WYT intermediate file:
      historical, A: ``utils.csv_io.delivery_name(<part_b>, product)``
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

    print(f"\n{'='*60}\nComputing {WEATHER_SETS[product]['name']} WYT targets\n{'='*60}")
    targets = compute_product_targets(
        product=product,
        wyt_target_dir=str(WYT_DIR / WEATHER_SETS[product]["name"]),
        pat_wide=pat_wide,
        term_specs=term_specs,
    )

    wyt_intermediate_dir.mkdir(parents=True, exist_ok=True)
    if product != "B":
        for name, df in targets.items():
            for part_b, grp in target_sv(df).groupby("Part B"):
                print(f"  - {write_delivery_csv(grp, wyt_intermediate_dir, part_b, product)}")
    else:  # targets {"product_b_nXX": frame}
        sv = product_b_target_table(targets)
        for part_b, grp in sv.groupby("Part B"):
            for out in write_chunk_csvs(grp, wyt_intermediate_dir, f"{part_b}_product_b"):
                print(f"  - {out}")

    wyt_csv.unlink(missing_ok=True)
    return hist_cmp_df, term_specs


####################################################################
### Part 2 - Quantile Mapping ###
####################################################################

def run_qmap_single(product: str, qmap_pairs_df: pd.DataFrame, base_dir: Path,
                    qmap_intermediate_dir: Path) -> None:
    """Run the QM of a single series and write CalSim-format intermediates."""
    qmap_csv = base_dir / "_qmap_pairs_tmp.csv"
    base_dir.mkdir(parents=True, exist_ok=True)
    qmap_pairs_df.to_csv(qmap_csv, index=False)

    qmap_intermediate_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as _tmp_detail:
        run_single_qmap_from_pairs(
            product=product,
            pair_csv=qmap_csv,
            dss_file=DSS_FILE,
            rim_csv=get_rim_inflow_outputs(product)["sv"],
            output_dir=_tmp_detail,
            validation_dir=str(qmap_intermediate_dir),
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
        output_tag="qmap",
    )

    # Reformat per-chunk detail CSVs into SV-format intermediates
    total = write_product_b_sv(base_dir, qmap_intermediate_dir, qmap_csv, "product_b",
                               remove_details=True)

    qmap_csv.unlink(missing_ok=True)
    print(f"  QMap intermediates: {total} file(s)")


####################################################################
### Part 3 - Final Hybrid = (WYT + QMap) / 2 ###
####################################################################

def run_final_hybrid_single(product: str, wyt_intermediate_dir: Path,
                            qmap_intermediate_dir: Path, final_dir: Path) -> None:
    """Average WYT and QMap results and write the final delivery CSVs of a single series."""
    final_dir.mkdir(parents=True, exist_ok=True)

    terms_df = read_terms(HYBRID_TERMS_CSV)
    terms =terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    total = 0
    for _, term in terms.iterrows():
        part_b = str(term["term_part_b"]).strip()
        part_c = str(term["term_part_c"]).strip()

        # Both intermediates cover DELIVERY_WY (csv_io.write_delivery_csv)
        wyt_path = wyt_intermediate_dir / delivery_name(part_b, product)
        qmap_path = qmap_intermediate_dir / delivery_name(part_b, product)
        for path in (wyt_path, qmap_path):
            if not path.exists():
                raise FileNotFoundError(f"Missing intermediate for {part_b}: {path}")

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

        print(f"  - {write_delivery_csv(out_df, final_dir, part_b, product)}")
        total += 1

    print(f"  Final hybrid: {total} file(s) written to {final_dir}")


def run_final_hybrid_b(wyt_intermediate_dir: Path, qmap_intermediate_dir: Path,
                       final_dir: Path) -> None:
    """Average WYT and QMap results per chunk and write final Product B CSVs."""
    terms_df = read_terms(HYBRID_TERMS_CSV)
    terms =terms_df[["term_part_b", "term_part_c"]].drop_duplicates()

    total = 0
    for _, term in terms.iterrows():
        part_b = str(term["term_part_b"]).strip()
        part_c = str(term["term_part_c"]).strip()
        frames = []
        for chunk, ts in enumerate(PRODUCT_B_CHUNKS, 1):
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

            frames.append(pd.DataFrame({
                "chunk": chunk,
                "Part B": part_b,
                "Part C": part_c,
                "Year": merged["Year"].astype(int),
                "Month": merged["Month"].astype(int),
                "Value": (merged["Value_wyt"] + merged["Value_qmap"]) / 2.0,
            }))
        total += len(write_chunk_csvs(pd.concat(frames, ignore_index=True), final_dir,
                                      f"{part_b}_product_b"))

    print(f"  Final hybrid: {total} file(s) written to {final_dir}")


####################################################################
### Main ###
####################################################################

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upper watershed hybrid terms = (WYT_avg + QMap) / 2",
    )
    parser.add_argument(
        "--product", choices=list(WEATHER_SETS), required=True,
        help="Weather set: historical (Historical_Unsplit) or A (WY1922-2018; one "
             "continuous series per term), or B (10 stochastic chunks).",
    )
    args = parser.parse_args()

    product = args.product
    name = WEATHER_SETS[product]["name"]
    base_dir = _gen / "output" / "_3_hybrid" / WEATHER_SETS[product]["slug"]
    final_dir = (_gen / "output" / "_product_b_final" if product == "B"
                 else delivery_dir(_gen / "output", product))

    wyt_intermediate_dir = base_dir / "hybrid_wyt"
    qmap_intermediate_dir = base_dir / "hybrid_qmap"

    wyt_terms_df, qmap_pairs_df = prepare_hybrid_input_files(HYBRID_TERMS_CSV)

    print(f"\n=== Part 1: WYT Averaging ({name}) ===")
    hist_cmp_df, term_specs = run_wyt(
        product, OUTPUT_PREFIX, wyt_terms_df,
        base_dir, wyt_intermediate_dir,
    )

    print(f"\n=== Part 2: Quantile Mapping ({name}) ===")
    if product != "B":
        run_qmap_single(product, qmap_pairs_df, base_dir, qmap_intermediate_dir)
    else:
        run_qmap_b(qmap_pairs_df, base_dir, qmap_intermediate_dir)

    print(f"\n=== Part 3: Final Hybrid ({name}) ===")
    if product != "B":
        run_final_hybrid_single(product, wyt_intermediate_dir, qmap_intermediate_dir, final_dir)
        figures_dir = _gen / "output" / "_3_hybrid" / "figures" / WEATHER_SETS[product]["slug"]
        recon_long = _load_final_single_as_long(final_dir, product)
        plot_actual_vs_recon_validation(
            recon_long, hist_cmp_df, term_specs, figures_dir, label=WEATHER_SETS[product]["label"],
        )
        print(f"  Figures: {figures_dir}/ (TS+CDF per term)")
    else:
        run_final_hybrid_b(wyt_intermediate_dir, qmap_intermediate_dir, final_dir)


if __name__ == "__main__":
    main()
