"""
Compile Gerber Pan Evaporation for CalSimHydro
==============================================
Computes Hargreaves-Samani reference ET at the eight Gerber grid cells from
WGEN temperature and quantile-maps it onto the CalSim 3 Gerber pan
evaporation record, writing the WBA 02 pan evaporation for WY 1921-2018.

The quantile map is fit on Historical_Unsplit weather against the CS3 record
over WY 1921-2018 and applied to the weather of the chosen product, so the
temperature changes in Product A's weather carry into its pan evaporation.

Inputs
------
- reference/WBA_Grid_Info.txt  (the Gerber cells)
- WGEN met files: Historical_Unsplit, and Product_A/1 for --product A
- reference/CS3_PanEvapGerber.dss  (quantile-mapping target)

Outputs
-------
- <generated>/output/_2_compile_et/Historical_Unsplit/  (PanEvap_QMAP_results.csv, CS3_PanEvap.dss)
- <generated>/output/_2_compile_et/Product_A/            (with --product A)

Dependencies
------------
- utils/dss_io.py, utils/quantile_mapping.py
- utils/paths.py  (data-dir resolution)

Usage
-----
    python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product Historical_Unsplit
    python mod_hydrology/calsimhydro/_2b_compile_pan_evap.py --product A
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
from utils.paths import get_base_dir, get_module_generated_dir
from utils.quantile_mapping import qmap_single

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
PAN_PATH = "/CALSIM/WBA02/PAN-EVAP//1MON/PAN-EVAP/"
# WY 1921-2018, the CalSimHydro Product A period
MONTHS = pd.date_range("1920-10-31", "2018-09-30", freq="ME")
MM_PER_INCH = 25.4

# --product choice: (WGEN folder, met file prefix, output folder)
WEATHER = {
    "Historical_Unsplit": ("Historical_Unsplit", "data", "Historical_Unsplit"),
    "A": ("Product_A/1", "meteo", "Product_A"),
}


def gerber_cells(grid_info_file: Path) -> pd.DataFrame:
    grid = pd.read_csv(
        grid_info_file,
        sep="\t",
        header=None,
        names=["wba_id", "lat", "lon", "pct_area", "area_grid", "area_wba"],
    )
    return grid.loc[grid["wba_id"] == "Gerber", ["lat", "lon", "pct_area"]]


def hargreaves_samani_mm(lat_deg: float, dates: pd.DatetimeIndex, tmax: np.ndarray, tmin: np.ndarray) -> np.ndarray:
    """Daily Hargreaves-Samani ETo (mm/day), the form of step 10a in mod_forcing/climate/_3_refet_cimis_adj."""
    phi = np.radians(lat_deg)
    doy = dates.dayofyear.to_numpy()
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365.25)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365.25 - 1.39)
    omega_s = np.arccos(-np.tan(phi) * np.tan(delta))
    ra_mj = (24 * 60 / np.pi) * 0.0820 * dr * (
        omega_s * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(omega_s)
    )
    delta_t = np.maximum(tmax - tmin, 0.0)
    return 0.0023 * (ra_mj / 2.45) * ((tmax + tmin) / 2.0 + 17.8) * np.sqrt(delta_t)


def monthly_gerber_eto(met_dir: Path, prefix: str, cells: pd.DataFrame) -> pd.Series:
    """Area-weighted monthly Hargreaves-Samani ETo (inches) over the Gerber cells, WY 1921-2018."""
    total = None
    for cell in cells.itertuples():
        met = pd.read_csv(
            met_dir / f"{prefix}_{cell.lat}_{cell.lon}",
            sep=r"\s+",
            header=None,
            names=["year", "month", "day", "precip", "tmax", "tmin"],
        )
        dates = pd.DatetimeIndex(pd.to_datetime(met[["year", "month", "day"]]))
        eto = hargreaves_samani_mm(cell.lat, dates, met["tmax"].to_numpy(), met["tmin"].to_numpy())
        weighted = pd.Series(eto * cell.pct_area, index=dates)
        total = weighted if total is None else total + weighted
    monthly = (total / cells["pct_area"].sum()).resample("ME").sum() / MM_PER_INCH
    monthly = monthly.reindex(MONTHS)
    if monthly.isna().any():
        raise ValueError(f"Gerber cells in {met_dir} do not cover WY 1921-2018")
    return monthly


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
        "year": monthly.index.year + (monthly.index.month >= 10),
        "month": monthly.index.month,
        "value": monthly.to_numpy(),
    })


def write_dss(dss_file: Path, pan: pd.Series) -> None:
    tsc = TimeSeriesContainer()
    tsc.pathname = PAN_PATH
    tsc.startDateTime = "31OCT1920 24:00:00"
    tsc.numberValues = len(pan)
    tsc.units = "Inch"
    tsc.type = "PER-CUM"
    tsc.interval = 1
    tsc.values = pan.to_numpy(dtype=float)
    # A fresh file, so no record from an earlier run survives next to this one
    dss_file.unlink(missing_ok=True)
    with dss_io.open_dss(dss_file, version=6, catalog_flag=False) as dss:
        dss.put_ts(tsc)


def main():
    parser = argparse.ArgumentParser(
        description="Quantile-map Hargreaves-Samani ETo at the Gerber cells onto the CS3 pan evaporation record."
    )
    parser.add_argument(
        "--product",
        choices=list(WEATHER),
        required=True,
        help="Weather to map: Historical_Unsplit (WGEN historical, not detrended) or A (Product A scenario 1).",
    )
    args = parser.parse_args()

    wgen_dir = get_base_dir() / "WGEN"
    cells = gerber_cells(REFERENCE_DIR / "WBA_Grid_Info.txt")
    hist_eto = monthly_gerber_eto(wgen_dir / "Historical_Unsplit", "data", cells)
    met_folder, prefix, out_folder = WEATHER[args.product]
    if args.product == "Historical_Unsplit":
        eto = hist_eto
    else:
        eto = monthly_gerber_eto(wgen_dir / met_folder, prefix, cells)

    cs3_pan = read_cs3_pan()
    mapped = qmap_single(qmap_frame(eto), qmap_frame(hist_eto), qmap_frame(cs3_pan))
    pan = pd.Series(mapped["quantile_mapped_value"].to_numpy(), index=MONTHS)

    # Beside the CalSimHydro RefET and CropET of _2_compile_et.py
    out_dir = get_module_generated_dir("mod_hydrology/calsimhydro") / "output" / "_2_compile_et" / out_folder
    out_dir.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame({"hs_eto_in": eto, "pan_evap_in": pan, "cs3_pan_evap_in": cs3_pan})
    table.rename_axis("date").to_csv(out_dir / "PanEvap_QMAP_results.csv", float_format="%.4f")
    write_dss(out_dir / "CS3_PanEvap.dss", pan)

    years = len(MONTHS) / 12
    print(f"{out_folder}: pan evaporation {pan.sum() / years:.1f} in/yr, "
          f"CS3 record {cs3_pan.sum() / years:.1f} in/yr, HS ETo {eto.sum() / years:.1f} in/yr")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
