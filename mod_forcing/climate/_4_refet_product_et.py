"""
Reference ET and crop ET for one product (steps 10 to 14)
=========================================================
Builds the CalSimHydro ET inputs of one weather set, ``--product historical``
(Historical_Unsplit), ``A`` or ``B`` (the keys of ``utils.paths.WEATHER_SETS``),
from its WGEN weather and the correction factors of ``_3_refet_f1_factors.py``:

    step 10  Hargreaves-Samani ETo per grid cell and month (manual section 5)
             and the F1 correction (manual section 7)
    step 11  area weighted monthly ETo per WBA, subregion and small watershed
             (manual section 8) and CS3_RefETo.dss
    step 12  monthly polygon ETo to daily values by a cubic spline, a Python
             replica of the macro of DWR's CUP+ Excel workbook (manual section 9)
    step 13  daily precipitation per polygon for CUP+
    step 14  the CUP+ (PyCUP) crop ET run on the 43 WBAs, and CS3_ET.dss: its
             records renamed for CalSimHydro plus the 64 crop ET records that do
             not depend on climate (42 SL climatologies, 2 RI terms), copied
             from the existing CalSimHydro input

Manual: User_Manual_CS3_Domain_v2.pdf (Mohammad Monirul Hasan, DWR MSO); the
library ``refet_cimis_adj.py`` states where the code departs from it.

F1 is fit in step 7 of ``_3_refet_f1_factors.py``, on Historical_Unsplit, and
that table is applied to every set: the factor corrects what Hargreaves-Samani
leaves out (radiation, humidity, wind). ``--f1-table`` applies another table
instead; the table used is recorded in ``step10/F1_source.txt``.

Product B is one 1008 year WGEN sequence on its own stamp calendar cut into
ten chunks of 100 water years, each labelled January 1920 to December 2021.
Its per cell tables would be gigabytes, so steps 10, 11 and 13 run as one
pass over the weather that keeps the polygon series only; steps 12 and 14 then
run per chunk and every output carries a chunk suffix ``_n01`` to ``_n10``.

Outputs
-------
    GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/<product>/step10 ... step14/
    GENERATED/mod_hydrology/calsimhydro/output/_2_compile_et/<product>/CS3_RefETo.dss, CS3_ET.dss

Usage
-----
    python mod_forcing/climate/_4_refet_product_et.py --product A
    python mod_forcing/climate/_4_refet_product_et.py --product historical --step 10 11
    python mod_forcing/climate/_4_refet_product_et.py --product B --chunks 1-3 --cup-jobs 3 --cup-np 4
    python mod_forcing/climate/_4_refet_product_et.py --product A --step 11 --plots

Step 14 runs PyCUP with the interpreter named by the ``cupplus_python`` key of
config.json (numpy 1, pandas 2); every other step runs in the project
environment (environment.yml, ``csstochastic``). ``--plots`` draws the maps of the requested steps from their
outputs and stops if a step has not been run.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor

# The repository root for utils, the script folder for refet_cimis_adj.py.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import refet_cimis_adj as lib  # noqa: E402
from refet_cimis_adj import log, require  # noqa: E402

STEP_CHOICES = ("all", "10", "11", "12", "13", "14")


def parse_steps(values: list[str]) -> list[int]:
    if "all" in values:
        return list(lib.PRODUCT_STEPS)
    return sorted({int(value) for value in values})


def parse_chunks(text: str) -> list[int]:
    """``1-10``, ``1,3,5`` or ``all``."""
    if text == "all":
        return list(range(1, lib.N_CHUNKS + 1))
    chunks = set()
    for part in text.split(","):
        if "-" in part:
            first, last = part.split("-")
            chunks.update(range(int(first), int(last) + 1))
        else:
            chunks.add(int(part))
    bad = [chunk for chunk in chunks if not 1 <= chunk <= lib.N_CHUNKS]
    if bad:
        raise ValueError(f"chunks must be between 1 and {lib.N_CHUNKS}: {bad}")
    return sorted(chunks)


def f1_resolver(product: lib.Product, args):
    """A function (cells_or_table, out_dir) -> F1 array. Every set applies the step 7 table,
    fit on the Historical_Unsplit weather; --f1-table applies another file instead."""
    if args.f1_table:
        path, label = pathlib.Path(args.f1_table), "the table given on the command line"
    else:
        path = lib.factor_step_dir(7) / lib.F1_TABLE_CSV
        label = (f"step 7 (F1 fit on Historical_Unsplit over {lib.F1_START_YEAR}-{lib.F1_END_YEAR}, "
                 "applied to every set)")
    # Checked here, before the long pass over the weather, not only when the table is applied.
    require(path, "run _3_refet_f1_factors.py --step 7 first or pass --f1-table")

    def resolve(table, out_dir):
        out_dir = pathlib.Path(out_dir)
        values = lib.f1_from_table(path, table, out_dir)
        if not product.is_chunked:
            # The H-S monthly average over the whole period, drawn by the step 10 maps
            # (Product B keeps no per cell table).
            lib.hs_monthly_average(table, product.start_year, product.end_year)[1].to_csv(
                out_dir / lib.HS_AVG_CSV, index=False)
        (out_dir / lib.F1_SOURCE_TXT).write_text(f"F1 taken from {label}:\n{path}\n", encoding="ascii")
        return values

    log(f"F1 source: {label}")
    return resolve


# -- dated products: one step at a time ---------------------------------------------------

def compute_corrected_eto(product, args, resolve_f1) -> None:
    """Step 10: Hargreaves-Samani ETo per grid cell and month, then the F1 correction."""
    out = lib.product_step_dir(product, 10)
    table = lib.hs_table_step(product, out, args.workers)
    values = resolve_f1(table, out)
    lib.apply_f1_step(table, values, out)


def average_eto_over_polygons(product, args) -> None:
    """Step 11: area weighted monthly ETo per polygon and the CS3_RefETo.dss of the WBAs."""
    corrected = lib.read_hs_table(
        require(lib.product_step_dir(product, 10) / lib.ETO_CORRECTED_CSV, "run step 10 first"), product)
    columns = lib.month_columns(product.start_year, product.end_year)
    log(f"step 11: polygon averages of {len(corrected):,} cells")
    series = lib.polygon_step(corrected, columns, lib.load_weights(), lib.product_step_dir(product, 11))
    lib.refeto_step(series["WBA"], product)


def spline_eto_to_daily(product, chunk=None) -> None:
    """Step 12: daily ETo of the 172 CUP+ areas by the cubic spline of the CUP+ workbook."""
    log(f"step 12{lib.chunk_suffix(chunk)}: spline")
    lib.spline_step(product, lib.product_step_dir(product, 11), lib.product_step_dir(product, 12), chunk)


def build_daily_precipitation(product, args) -> None:
    """Step 13: daily precipitation per polygon from the same weather and weights, for CUP+."""
    lib.precip_step(product, lib.load_weights(), lib.product_step_dir(product, 13), args.workers)


def run_cupplus_crop_et(product, args, chunks: list) -> None:
    """Step 14: the CUP+ crop ET run per chunk and the CS3_ET.dss with the legacy records."""
    python = lib.cupplus_python()
    step12_dir = lib.product_step_dir(product, 12)
    step13_dir = lib.product_step_dir(product, 13)
    jobs = max(1, min(args.cup_jobs, len(chunks)))
    if jobs > 1:
        log(f"step 14: {len(chunks)} PyCUP runs, {jobs} at a time, np={args.cup_np} each")

    def run(chunk):
        return lib.cup_prepare_and_run(product, step12_dir, step13_dir, chunk, args.cup_np, python)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        work_dirs = list(pool.map(run, chunks))
    for chunk, work_dir in zip(chunks, work_dirs):
        lib.cup_finish(product, work_dir, lib.product_step_dir(product, 14), chunk)


def main(argv=None) -> None:
    # allow_abbrev=False: the retired --f1 must not be read as --f1-table.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("--product", required=True, choices=lib.PRODUCT_KEYS,
                        help="historical (Historical_Unsplit), A (Product A) or B (Product B, 10 chunks)")
    parser.add_argument("--step", nargs="+", default=["all"], choices=STEP_CHOICES)
    parser.add_argument("--chunks", default="all", help="Product B chunks, e.g. 1-10 or 1,3 (default all)")
    parser.add_argument("--f1-table", default=None,
                        help="apply this F1_table.csv instead of step 7's (fit on the Historical_Unsplit weather)")
    parser.add_argument("--workers", type=int, default=None, help="processes for the cell pass (default all cores)")
    parser.add_argument("--cup-jobs", type=int, default=1, help="PyCUP runs at a time (Product B chunks)")
    parser.add_argument("--cup-np", type=int, default=lib.DEFAULT_NP, help="PyCUP workers per run (its np key)")
    parser.add_argument("--plots", action="store_true", help="draw the maps of the requested steps")
    args = parser.parse_args(argv)

    product = lib.get_product(args.product)
    steps = parse_steps(args.step)
    chunks = parse_chunks(args.chunks) if product.is_chunked else [None]
    log(f"{product.name}: steps {steps}" + (f", chunks {chunks}" if product.is_chunked else ""))

    if args.plots:
        lib.product_maps(product, steps, chunks)
        return

    if product.is_chunked:
        if any(step in (10, 11, 13) for step in steps):
            resolve_f1 = f1_resolver(product, args)
            lib.product_b_pass(product, resolve_f1, lib.load_weights(), chunks, args.workers)
        if 12 in steps:
            for chunk in chunks:
                spline_eto_to_daily(product, chunk)
        if 14 in steps:
            run_cupplus_crop_et(product, args, chunks)
    else:
        if 10 in steps:
            compute_corrected_eto(product, args, f1_resolver(product, args))
        if 11 in steps:
            average_eto_over_polygons(product, args)
        if 12 in steps:
            spline_eto_to_daily(product)
        if 13 in steps:
            build_daily_precipitation(product, args)
        if 14 in steps:
            run_cupplus_crop_et(product, args, [None])
    log("done")


if __name__ == "__main__":
    main()
