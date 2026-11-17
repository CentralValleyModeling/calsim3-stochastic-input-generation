"""
Reference ETo correction factors (steps 0 and 5 to 8)
=====================================================
Computes, from the Historical_Unsplit weather (BASE/WGEN/Historical_Unsplit), what the
reference ET of every weather set needs: the area weights of the grid cells in
each polygon, and the F1 factors that correct Hargreaves-Samani ETo against
Spatial CIMIS. It runs once; ``_4_refet_product_et.py`` reads its step 0 and
step 7 outputs for Historical_Unsplit, Product A and Product B alike:

    step 0  grid cell weights of every WBA, subregion and small watershed
            (the ArcPy WTable files of manual sections 3 and 8)
    step 5  Hargreaves-Samani ETo per grid cell and month, 1920-2018
            (manual section 5)
    step 6  monthly mean Spatial CIMIS ETo at the grid cells, per year
            2004-2023 (manual section 6)
    step 7  the F1 correction factors, 2004-2018, the one table step 10 of
            ``_4_refet_product_et.py`` applies to every weather set, and the
            corrected historical ETo (manual section 7)
    step 8  area weighted monthly averages and series per polygon over the
            calibration years 2004-2018 (manual section 8)

Manual: User_Manual_CS3_Domain_v2.pdf (Mohammad Monirul Hasan, DWR MSO),
"Calculating Reference Evapotranspiration (Ref ETo) for California and
CalSim 3 Domain Using PRISM Data and the Hargreaves-Samani Equation". Manual
sections 1 to 4 (PRISM download and extraction) are not used: the grid is
WGEN's. The library ``refet_cimis_adj.py`` states every other departure.

Outputs
-------
    GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step0 ... step8/

Usage
-----
    python mod_forcing/climate/_3_refet_f1_factors.py --step all
    python mod_forcing/climate/_3_refet_f1_factors.py --step 7 8
    python mod_forcing/climate/_3_refet_f1_factors.py --step 8 --plots

Every step runs in the project environment (environment.yml, ``csstochastic``).
Step 6 needs the daily CIMIS rasters in BASE/CIMIS/cimis_eto_rasters.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import refet_cimis_adj as lib  # noqa: E402
from refet_cimis_adj import log, require  # noqa: E402

STEP_CHOICES = ("all", "0", "5", "6", "7", "8")


def parse_steps(values: list[str]) -> list[int]:
    if "all" in values:
        return list(lib.FACTOR_STEPS)
    return sorted({int(value) for value in values})


def build_polygon_weights(historical) -> None:
    """Step 0: grid cell weights of every WBA, subregion and small watershed."""
    log(f"step 0: polygon weights from {historical.weather_dir}")
    counts = lib.build_weight_tables(lib.reference_dir(), historical.weather_dir, lib.factor_step_dir(0))
    log("  wrote " + ", ".join(f"{n} {group}" for group, n in counts.items()) + " weight tables")


def compute_historical_eto(historical, args) -> None:
    """Step 5: Hargreaves-Samani ETo per grid cell and month on the Historical_Unsplit weather."""
    lib.hs_table_step(historical, lib.factor_step_dir(5), args.workers)


def extract_cimis_monthly_means(historical) -> None:
    """Step 6: monthly mean Spatial CIMIS ETo at the grid cells, per year."""
    raster_dir = require(lib.cimis_raster_dir(), "download the Spatial CIMIS daily rasters first")
    cells = lib.scan_cells(historical.weather_dir)
    index = lib.index_rasters(raster_dir, lib.CIMIS_START_YEAR, lib.CIMIS_END_YEAR)
    log(f"step 6: {len(index):,} CIMIS rasters sampled at {len(cells):,} cells")
    written = lib.monthly_means(cells, index, lib.cimis_monthly_dir())
    log(f"  wrote {len(written)} files to {lib.cimis_monthly_dir()}")


def compute_f1_factors(historical) -> None:
    """Step 7: F1 = CIMIS mean / H-S mean per cell and month on the Historical_Unsplit weather, the
    table step 10 applies to every set, and the corrected historical ETo."""
    table = lib.read_hs_table(require(lib.factor_step_dir(5) / lib.ETO_MONTHLY_CSV, "run step 5 first"),
                              historical)
    out = lib.factor_step_dir(7)
    out.mkdir(parents=True, exist_ok=True)
    log(f"step 7: F1 for {len(table):,} cells over {lib.F1_START_YEAR}-{lib.F1_END_YEAR}")
    values = lib.f1_fit(table, out)
    lib.apply_f1_step(table, values, out)


def average_historical_eto_over_polygons(historical) -> None:
    """Step 8: area weighted polygon averages of the corrected ETo over the calibration years."""
    corrected = lib.read_hs_table(
        require(lib.factor_step_dir(7) / lib.ETO_CORRECTED_CSV, "run step 7 first"), historical)
    columns = lib.month_columns(lib.F1_START_YEAR, lib.F1_END_YEAR)
    log(f"step 8: polygon averages over {lib.F1_START_YEAR}-{lib.F1_END_YEAR}")
    lib.polygon_step(corrected, columns, lib.load_weights(), lib.factor_step_dir(8))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--step", nargs="+", default=["all"], choices=STEP_CHOICES)
    parser.add_argument("--workers", type=int, default=None, help="processes for the cell pass (default all cores)")
    parser.add_argument("--plots", action="store_true", help="draw the maps of the requested steps")
    args = parser.parse_args(argv)

    historical = lib.get_product("historical")
    steps = parse_steps(args.step)
    log(f"correction factors: steps {steps}")

    if args.plots:
        lib.factor_maps(steps)
        return

    if 0 in steps:
        build_polygon_weights(historical)
    if 5 in steps:
        compute_historical_eto(historical, args)
    if 6 in steps:
        extract_cimis_monthly_means(historical)
    if 7 in steps:
        compute_f1_factors(historical)
    if 8 in steps:
        average_historical_eto_over_polygons(historical)
    log("done")


if __name__ == "__main__":
    main()
