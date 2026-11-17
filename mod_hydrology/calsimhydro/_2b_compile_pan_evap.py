"""
Compile Gerber Pan Evaporation for CalSimHydro
==============================================
Monthly Hargreaves-Samani reference ET (inches) at the eight Gerber cells from WGEN temperature,
quantile-mapped onto the CalSim 3 Gerber pan evaporation record: CalSimHydro's WBA 02 pan
evaporation.

The quantile map is fit on Historical_Unsplit against the CS3 record over WY1921-2018 and
applied to the --product weather, so the temperature of Products A and B carries into their
pan evaporation. Product B is mapped over all its stamp months, then cut into chunks.

Inputs
------
- reference/WBA_Grid_Info.txt: the Gerber cells and pct_area weights
- daily tmax and tmin (utils.wgen.read_met) of Historical_Unsplit and of the --product set
- reference/CS3_PanEvapGerber.dss: /CALSIM/WBA02/PAN-EVAP//1MON/PAN-EVAP/, WY1921-2018, the
  QM target

Outputs
-------
Under <generated>/mod_hydrology/calsimhydro/output/_2_compile_et/, beside the ET of
_2_compile_et.py:
- <Historical_Unsplit|Product_A>/PanEvap_QMAP_results.csv (date, hs_eto_in, pan_evap_in,
  cs3_pan_evap_in) and CS3_PanEvap.dss, WY1921-2018
- Product_B/PanEvap_QMAP_results.csv by stamp month, and CS3_PanEvap_n01.dss ... _n10.dss,
  each Jan 1920 - Dec 2021 (utils.wgen_calendar.monthly_chunk_1920_2021)

Dependencies
------------
utils.paths, utils.dss_io, utils.quantile_mapping, utils.wgen, utils.wgen_calendar; pydsstools

Usage
-----
    python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product historical
    python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product A
    python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product B
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.core import TimeSeriesContainer

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import WEATHER_SETS, get_module_generated_dir
from utils.quantile_mapping import qmap_single
from utils.wgen import dates, met_path, read_met
from utils.wgen_calendar import (N_CHUNKS, monthly_chunk_1920_2021, stamp_day_of_year, stamp_month_of_day,
                                 water_year)

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
PAN_PATH = "/CALSIM/WBA02/PAN-EVAP//1MON/PAN-EVAP/"
# WY 1921-2018, the CalSimHydro period of Historical_Unsplit and Product A
MONTHS = pd.date_range("1920-10-31", "2018-09-30", freq="ME")
MM_PER_INCH = 25.4

PRODUCTS = ("historical", "A", "B")


def gerber_cells(grid_info_file: Path) -> pd.DataFrame:
    grid = pd.read_csv(
        grid_info_file,
        sep="\t",
        header=None,
        names=["wba_id", "lat", "lon", "pct_area", "area_grid", "area_wba"],
    )
    return grid.loc[grid["wba_id"] == "Gerber", ["lat", "lon", "pct_area"]]


def hargreaves_samani_mm(lat_deg: float, doy: np.ndarray, tmax: np.ndarray, tmin: np.ndarray) -> np.ndarray:
    """Daily Hargreaves-Samani ETo (mm/day) on days of the year ``doy``, the form of step 10a in
    mod_forcing/climate/_3_refet_cimis_adj."""
    phi = np.radians(lat_deg)
    dr =1 + 0.033 * np.cos(2 * np.pi * doy / 365.25)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365.25 - 1.39)
    omega_s = np.arccos(-np.tan(phi) * np.tan(delta))
    ra_mj = (24 * 60 / np.pi) * 0.0820 * dr * (
        omega_s * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(omega_s)
    )
    delta_t = np.maximum(tmax - tmin, 0.0)
    return 0.0023 * (ra_mj / 2.45) * ((tmax + tmin) / 2.0 + 17.8) * np.sqrt(delta_t)


def monthly_gerber_eto(product: str, cells: pd.DataFrame) -> pd.Series:
    """Area-weighted monthly Hargreaves-Samani ETo (inches) over the Gerber cells, WY 1921-2018,
    of a single series (Historical_Unsplit or Product A)."""
    total = None
    for cell in cells.itertuples():
        met = read_met(product, met_path(product, cell.lat, cell.lon), usecols=["tmax", "tmin"])
        days = dates(met)
        eto = hargreaves_samani_mm(cell.lat, days.dayofyear.to_numpy(), met["tmax"].to_numpy(),
                                   met["tmin"].to_numpy())
        weighted = pd.Series(eto * cell.pct_area, index=days)
        total = weighted if total is None else total + weighted
    monthly = (total / cells["pct_area"].sum()).resample("ME").sum() / MM_PER_INCH
    monthly = monthly.reindex(MONTHS)
    if monthly.isna().any():
        raise ValueError(f"The Gerber cells of {WEATHER_SETS[product]['name']} do not cover WY 1921-2018")
    return monthly


def stamp_monthly_gerber_eto(cells: pd.DataFrame) -> np.ndarray:
    """Area-weighted monthly Hargreaves-Samani ETo (inches) over the Gerber cells of Product B,
    one value per stamp month from January of stamp year 1 (utils.wgen_calendar)."""
    total = None
    for cell in cells.itertuples():
        # read_met checks that the rows are the stamp days in order, so row i is stamp day i
        met = read_met("B", met_path("B", cell.lat, cell.lon), usecols=["tmax", "tmin"])
        eto = hargreaves_samani_mm(cell.lat, stamp_day_of_year(), met["tmax"].to_numpy(),
                                   met["tmin"].to_numpy()) * cell.pct_area
        total = eto if total is None else total + eto
    return np.bincount(stamp_month_of_day(), weights=total / cells["pct_area"].sum()) / MM_PER_INCH


def read_cs3_pan() -> pd.Series:
    with dss_io.open_dss(REFERENCE_DIR / "CS3_PanEvapGerber.dss", catalog_flag=False) as dss:
        ts = dss.read_ts(PAN_PATH, window=("31OCT1920 00:00:00", "30SEP2018 24:00:00"))
    values = np.asarray(ts.values, dtype=float)
    if len(values) != len(MONTHS) or (values <= -900).any():
        raise ValueError(f"{PAN_PATH} does not cover WY 1921-2018")
    return pd.Series(values, index=MONTHS)


def qmap_frame(monthly: pd.Series) -> pd.DataFrame:
    """The water year, month, value frame that qmap_single takes."""
    return pd.DataFrame({
        "year": water_year(monthly.index.year, monthly.index.month),
        "month": monthly.index.month,
        "value": monthly.to_numpy(),
    })


def write_dss(dss_file: Path, pan, start: str) -> None:
    """Write the monthly pan evaporation ``pan`` (inches) from the month ending at ``start``."""
    tsc = TimeSeriesContainer()
    tsc.pathname = PAN_PATH
    tsc.startDateTime = start
    tsc.numberValues = len(pan)
    tsc.units = "Inch"
    tsc.type = "PER-CUM"
    tsc.interval = 1
    tsc.values = np.asarray(pan, dtype=float)
    # A fresh file, so no record from an earlier run survives next to this one
    dss_file.unlink(missing_ok=True)
    with dss_io.open_dss(dss_file, version=6, catalog_flag=False) as dss:
        dss.put_ts(tsc)


def write_product_b(cells: pd.DataFrame, hist_eto: pd.Series, cs3_pan: pd.Series, out_dir: Path):
    """Quantile-map Product B's ETo over all its stamp months with the Historical_Unsplit fit,
    write the stamp-month table and one DSS per chunk (January 1920 to December 2021), and
    return the pan evaporation and the ETo by stamp month."""
    eto = stamp_monthly_gerber_eto(cells)
    i = np.arange(len(eto))
    sim = pd.DataFrame({"year": i // 12 + 1, "month": i % 12 + 1, "value": eto})
    pan = qmap_single(sim, qmap_frame(hist_eto), qmap_frame(cs3_pan))["quantile_mapped_value"].to_numpy()
    pd.DataFrame({"Year": sim["year"], "Month": sim["month"], "hs_eto_in": eto, "pan_evap_in": pan}).to_csv(
        out_dir / "PanEvap_QMAP_results.csv", index=False, float_format="%.4f")
    for k in range(1, N_CHUNKS + 1):
        write_dss(out_dir / f"CS3_PanEvap_n{k:02d}.dss", monthly_chunk_1920_2021(pan, k), "31JAN1920 24:00:00")
    return pan, eto


def main():
    parser = argparse.ArgumentParser(
        description="Quantile-map Hargreaves-Samani ETo at the Gerber cells onto the CS3 pan evaporation record."
    )
    parser.add_argument(
        "--product",
        choices=PRODUCTS,
        required=True,
        help="Weather to map: historical (Historical_Unsplit, not detrended), A (Product A "
             "scenario 1) or B (Product B, 10 chunks).",
    )
    args = parser.parse_args()

    cells = gerber_cells(REFERENCE_DIR / "WBA_Grid_Info.txt")
    hist_eto = monthly_gerber_eto("historical", cells)
    out_folder = WEATHER_SETS[args.product]["name"]
    cs3_pan = read_cs3_pan()

    # Beside the CalSimHydro RefET and CropET of _2_compile_et.py
    out_dir = get_module_generated_dir("mod_hydrology/calsimhydro") / "output" / "_2_compile_et" / out_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.product == "B":
        pan, eto = write_product_b(cells, hist_eto, cs3_pan, out_dir)
    else:
        eto = hist_eto if args.product == "historical" else monthly_gerber_eto(args.product, cells)
        mapped = qmap_single(qmap_frame(eto), qmap_frame(hist_eto), qmap_frame(cs3_pan))
        pan = pd.Series(mapped["quantile_mapped_value"].to_numpy(), index=MONTHS)
        table = pd.DataFrame({"hs_eto_in": eto, "pan_evap_in": pan, "cs3_pan_evap_in": cs3_pan})
        table.rename_axis("date").to_csv(out_dir / "PanEvap_QMAP_results.csv", float_format="%.4f")
        write_dss(out_dir / "CS3_PanEvap.dss", pan, "31OCT1920 24:00:00")

    years = len(pan) / 12
    print(f"{out_folder}: pan evaporation {pan.sum() / years:.1f} in/yr, "
          f"CS3 record {cs3_pan.sum() / (len(MONTHS) / 12):.1f} in/yr, HS ETo {eto.sum() / years:.1f} in/yr")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
