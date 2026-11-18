"""
Prepare a DETAW-DCD Run for a Weather Set
=========================================
Writes a weather set's daily weather and Sacramento Valley water year types (WYT) into a DETAW-DCD
run folder, a copy of DeltaChannelDepletion_Runs/DCD_Calsim3_PlanningStudy_1921-2018, which runs
in DCD.py's CalSim mode. The run covers 30 Sep 1921 to 30 Sep 2018 (Historical_Unsplit, Product
A) or 30 Sep 2021 (a Product B chunk). DETAW stops at the last row of LODI_PT.csv. It and the
DCD kernel read the per-year files by position from water year 1922, so each file holds exactly
the water years 1922 to the last, in order.

The planning study repeats the historical 2015 land use in every year, and every set runs on it
with its own WYT in the TYPE column. The script writes all 168 Landuse files; DETAW reads the WYT
from SA0001.csv, and in a C or D year it takes the crop dates and coefficients of critical.csv in
place of noncritical.csv.

The script leaves the groundwater rate files as the run folder holds them. The CalSim mode reads
GW_RATES_CALSIM3.TXT, 0.40 in every year; only the DSM2 and SCHISM modes read GW_RATES.TXT. For a
Product B run, add rows 2019-2021 at 0.40 to GW_RATES_CALSIM3.TXT by hand, since the script
refuses a file that does not cover the run.

Next, run ``python DCD.py`` in <run>/DCD (Python 3.12 with pyhecdss from channel cadwr-dms,
xarray, numba, netcdf4, h5netcdf and scipy). It runs DETAW and the DCD kernel and copies the
CalSim outputs to DCD/Output/CALSIM3. Then run _1c_build_cs3sv_dss.py on the run folder.

Inputs
------
- <generated>/mod_hydrology/delta_channel_depletion/output/_1_compile_precip_DETAW/<set>/
  mm_pcp.csv, LODI_PT.csv (Product B: mm_pcp_nKK.csv, LODI_PT_nKK.csv)
- <generated>/mod_hydrology/water_year_types/output/_1_calc_WYTs/<set>/_SacWYT.csv
  (Product B: _SacWYT_nKK.csv)
- <run>/DCD/NODCU/GW_RATES_CALSIM3.TXT, checked to hold one row per water year of the run

Outputs
-------
The script rewrites these files of the run folder in place, keeping each file's line endings:
- DETAW/Input/planning_study/mm_pcp.csv, LODI_PT.csv: _1's rows of the run period
- DETAW/Input/planning_study/calender.txt: year, month, day and day of year of each day
- DETAW/Input/planning_study/Landuse/SA0001.csv ... SA0168.csv: one row per water year, the
  file's last land use row with that year and its WYT
- DCD/NODCU/WYTYPES, DCD/NODCU/DCD_Cal/WYTYPES: "<WYT> <year>" per water year, AN as A, BN as B;
  the kernel reads one row per year but does not use the types

Dependencies
------------
utils.paths, utils.wgen_calendar

Usage
-----
    python mod_hydrology/delta_channel_depletion/_1b_prepare_dcd_run.py --product historical --run-dir <run>
    python mod_hydrology/delta_channel_depletion/_1b_prepare_dcd_run.py --product A --run-dir <run>
    python mod_hydrology/delta_channel_depletion/_1b_prepare_dcd_run.py --product B --chunk 3 --run-dir <run>
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import DELIVERY_WY, WEATHER_SETS, get_module_generated_dir
from utils.wgen_calendar import LABEL_WY, N_CHUNKS

FIRST_DAY = pd.Timestamp("1921-09-30")  # DETAW's fixed start (start1 in DETAW.py)
FIRST_WY = 1922                         # DCD.py's begwy
N_ISLANDS = 168
WYTYPES_LABEL = {"AN": "A", "BN": "B"}
PLANNING = Path("DETAW") / "Input" / "planning_study"
NODCU = Path("DCD") / "NODCU"


def read_lines(path: Path) -> list:
    """The lines of ``path`` with their line endings."""
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read().splitlines(keepends=True)


def eol_of(lines: list, default: str = "\r\n") -> str:
    """The line ending of the first line that has one."""
    for ln in lines:
        body = ln.rstrip("\r\n")
        if body != ln:
            return ln[len(body):]
    return default


def finish(lines: list, final_newline: bool) -> str:
    """Join ``lines`` (each with its ending), dropping the last ending when the file had none."""
    text = "".join(lines)
    return text if final_newline else text.rstrip("\r\n")


def had_final_newline(lines: list) -> bool:
    return bool(lines) and lines[-1].endswith(("\n", "\r"))


def write_text(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def clip_daily(src: Path, dst: Path, days: pd.DatetimeIndex, day_of) -> str:
    """_1's header and rows of ``days`` with ``dst``'s line endings; ``day_of`` dates a row."""
    lines = read_lines(src)
    keep = {d: None for d in days}
    for ln in lines[1:]:
        d = day_of(ln.rstrip("\r\n").split(","))
        if d in keep:
            if keep[d] is not None:
                raise ValueError(f"{src} repeats {d.date()}")
            keep[d] = ln
    missing = [d.date() for d, ln in keep.items() if ln is None]
    if missing:
        raise ValueError(f"{src} lacks {len(missing)} days of the run, first {missing[0]}")
    old = read_lines(dst) if dst.exists() else lines
    eol = eol_of(old)
    rows = [ln.rstrip("\r\n") + eol for ln in [lines[0]] + list(keep.values())]
    return finish(rows, had_final_newline(old))


def calender_text(dst: Path, days: pd.DatetimeIndex) -> str:
    old = read_lines(dst)
    eol = eol_of(old)
    rows = [f"{d.year}\t{d.month}\t{d.day}\t{d.dayofyear}{eol}" for d in days]
    return finish(rows, had_final_newline(old))


def landuse_text(path: Path, years: range, wyt: dict) -> str:
    """The Landuse file ``path`` with one row per water year of ``years``: its last row (the land
    use) with that year, in the file's year format ("1922" or "1922.0"), and the year's WYT."""
    lines = read_lines(path)
    rows = [ln for ln in lines[2:] if ln.strip()]
    if not rows:
        raise ValueError(f"{path} holds no land use rows")
    body = rows[-1].rstrip("\r\n")
    eol = rows[-1][len(body):] or eol_of(lines)
    year, _, rest = body.split(",", 2)
    last = str(int(float(year)))
    out = lines[:2] + [f"{year.replace(last, str(y), 1)},{wyt[y]},{rest}{eol}" for y in years]
    return finish(out, had_final_newline(lines))


def check_gw_rates(path: Path, years: range) -> None:
    """Refuse a groundwater rate file whose rows do not begin with the water years of ``years``
    in order; the DCD kernel reads one row per water year by position."""
    file_years = [int(ln.split()[0]) for ln in read_lines(path) if ln.strip()]
    if file_years[:len(years)] != list(years):
        held = f"{file_years[0]}-{file_years[-1]}" if file_years else "none"
        raise ValueError(f"{path} needs one row per water year {years[0]}-{years[-1]}, in order; "
                         f"it holds {len(file_years)} rows, water years {held}")


def wytypes_text(path: Path, years: range, wyt: dict) -> str:
    old = read_lines(path)
    eol = eol_of(old)
    rows = [f"{WYTYPES_LABEL.get(wyt[y], wyt[y])} {y}{eol}" for y in years]
    return finish(rows, had_final_newline(old))


def load_wyt(path: Path, years: range) -> dict:
    """{water year: W, AN, BN, D or C} of ``years`` from a _SacWYT csv."""
    df = pd.read_csv(path)
    df = df[df["water_year"].isin(years)]
    labels = df["wyt_label"].astype(str).str.strip().str.upper()
    repeated = sorted(set(df["water_year"][df["water_year"].duplicated()]))
    bad = sorted(set(labels) - {"W", "AN", "BN", "D", "C"})
    missing = sorted(set(years) - set(df["water_year"]))
    if repeated or bad or missing:
        raise ValueError(f"{path}: repeated water years {repeated}, unknown labels {bad}, "
                         f"missing water years {missing}")
    return dict(zip(df["water_year"].astype(int), labels))


def main():
    ap = argparse.ArgumentParser(description="Write a weather set's weather and water year types "
                                             "into a DETAW-DCD run folder.")
    ap.add_argument("--product", choices=list(WEATHER_SETS), required=True,
                    help="Weather set: historical (Historical_Unsplit), A or B")
    ap.add_argument("--chunk", type=int, choices=range(1, N_CHUNKS + 1), metavar="N",
                    help=f"Product B chunk, 1-{N_CHUNKS} (required with --product B)")
    ap.add_argument("--run-dir", type=Path, required=True,
                    help="The DETAW-DCD run folder (holds DETAW/ and DCD/)")
    args = ap.parse_args()
    if (args.product == "B") != (args.chunk is not None):
        ap.error("--chunk goes with --product B, and only with it")

    run = args.run_dir.resolve()
    dcd_py = run / "DCD" / "DCD.py"
    if not re.search(r"subdirs\s*=.*\[[^]]*['\"]CALSIM3['\"]", dcd_py.read_text()):
        raise ValueError(f"{dcd_py} does not create Output/CALSIM3 (its output subfolder list "
                         f"needs 'CALSIM3')")
    name = WEATHER_SETS[args.product]["name"]
    tag = f"_n{args.chunk:02d}" if args.chunk else ""
    last_wy = LABEL_WY[1] if args.chunk else DELIVERY_WY[1]
    years = range(FIRST_WY, last_wy + 1)
    days = pd.date_range(FIRST_DAY, f"{last_wy}-09-30", freq="D")

    src = (get_module_generated_dir("mod_hydrology/delta_channel_depletion") / "output"
           / "_1_compile_precip_DETAW" / name)
    wyt_csv = (get_module_generated_dir("mod_hydrology/water_year_types") / "output"
               / "_1_calc_WYTs" / name / f"_SacWYT{tag}.csv")
    wyt = load_wyt(wyt_csv, years)
    print(f"{name}{tag}: water years {years[0]}-{years[-1]}, {len(days)} days, run {run}")

    landuse = sorted((run / PLANNING / "Landuse").glob("SA*.csv"))
    if len(landuse) != N_ISLANDS:
        raise ValueError(f"{run / PLANNING / 'Landuse'} holds {len(landuse)} SA*.csv files, "
                         f"not {N_ISLANDS}")
    check_gw_rates(run / NODCU / "GW_RATES_CALSIM3.TXT", years)
    # Every file is built before any is written, so a failed check leaves the run unchanged
    texts = {
        run / PLANNING / "mm_pcp.csv": clip_daily(
            src / f"mm_pcp{tag}.csv", run / PLANNING / "mm_pcp.csv", days,
            lambda f: pd.Timestamp(int(f[0]), int(f[1]), int(f[2]))),
        run / PLANNING / "LODI_PT.csv": clip_daily(
            src / f"LODI_PT{tag}.csv", run / PLANNING / "LODI_PT.csv", days,
            lambda f: pd.Timestamp(f[0])),
        run / PLANNING / "calender.txt": calender_text(run / PLANNING / "calender.txt", days),
    }
    for p in landuse:
        texts[p] = landuse_text(p, years, wyt)
    for p in (run / NODCU / "WYTYPES", run / NODCU / "DCD_Cal" / "WYTYPES"):
        texts[p] = wytypes_text(p, years, wyt)

    changed = 0
    for p, text in texts.items():
        if "".join(read_lines(p)) != text:
            write_text(p, text)
            changed += 1
    print(f"Wrote {changed} of {len(texts)} files ({len(texts) - changed} already current)")


if __name__ == "__main__":
    main()
