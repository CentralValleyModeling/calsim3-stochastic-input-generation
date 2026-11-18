"""
Prepare a DETAW-DCD Run for a Weather Set
=========================================
Writes one weather set's daily weather and Sacramento Valley water year types into a DETAW-DCD
CalSim 3 run folder, from 30 Sep 1921 through 30 Sep of the run's last water year: 2018 for
Historical_Unsplit and Product A, 2021 for a Product B chunk. DETAW takes the last year from
the last row of LODI_PT.csv, and the DCD kernel reads WYTYPES and GW_RATES one row per water
year from 1922, so every per-year file holds exactly the water years 1922 to that year, in order.

A run folder is a copy of DeltaChannelDepletion_Runs/DCD_Calsim3_PlanningStudy_1921-2018 (DETAW/,
DCD/). After this script:

1. Run ``python DCD.py`` inside <run>/DCD in a Python 3.12 environment with pyhecdss (channel
   cadwr-dms), xarray, numba, netcdf4, h5netcdf and scipy. DCD.py runs DETAW, then the DCD
   kernel (DCD/NODCU/DCD_Cal, which the run needs; its DCD_outputs/ may be emptied first), and
   copies the CalSim outputs to DCD/Output/CALSIM3, which DCD.py creates from the CALSIM3 entry
   of its output subfolder list.
2. Run _1c_build_cs3sv_dss.py on the run folder.

Inputs
------
- <generated>/mod_hydrology/delta_channel_depletion/output/_1_compile_precip_DETAW/<set>/
  mm_pcp4.csv and LODI_PT4.csv (Product B: mm_pcp4_nKK.csv, LODI_PT4_nKK.csv)
- <generated>/mod_hydrology/water_year_types/output/_1_calc_WYTs/<set>/_SacWYT.csv
  (Product B: _SacWYT_nKK.csv): water_year, wyt_label
- The run folder's own Landuse, GW_RATES and WYTYPES files, rewritten in place

Outputs
-------
In the run folder (--run-dir), each file keeping its line endings:
- DETAW/Input/planning_study/mm_pcp.csv, LODI_PT.csv: _1's rows of the run period
- DETAW/Input/planning_study/calender.txt: year, month, day and day of year of each day of the
  run period, tab separated
- DETAW/Input/planning_study/Landuse/SA0001.csv ... SA0168.csv: TYPE (column 2) is the set's
  Sacramento WYT (W, AN, BN, D, C) and the land use stays; the land use ends in 2018, so the
  rows after 2018 repeat the 2018 row
- DCD/NODCU/WYTYPES and DCD/NODCU/DCD_Cal/WYTYPES: one "<label> <year>" line per water year,
  AN written A and BN written B
- DCD/NODCU/GW_RATES.TXT, GW_RATES_CALSIM3.TXT: the rows after 2018 repeat the 2018 rate

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
LANDUSE_LAST_WY = 2018                  # the last year of the land use and groundwater rates
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


def per_year_text(path: Path, n_header: int, years: range, year_of, edit) -> str:
    """Rows of ``path`` for ``years`` in order, a year after LANDUSE_LAST_WY copying that year's
    row; ``edit(line, year)`` turns the source row (without its ending) into the row of ``year``."""
    lines = read_lines(path)
    rows = {}
    for ln in lines[n_header:]:
        if not ln.strip():
            continue
        y = year_of(ln)
        if y in rows:
            raise ValueError(f"{path} repeats water year {y}")
        rows[y] = ln
    missing = [y for y in years if min(y, LANDUSE_LAST_WY) not in rows]
    if missing:
        raise ValueError(f"{path} lacks water years {missing}")
    eol = eol_of(lines)
    out = list(lines[:n_header])
    for y in years:
        src = rows[min(y, LANDUSE_LAST_WY)]
        body = src.rstrip("\r\n")
        out.append(edit(body, y) + (src[len(body):] or eol))
    return finish(out, had_final_newline(lines))


def landuse_edit(wyt: dict):
    def edit(body, y):
        fields = body.split(",")
        if int(float(fields[0])) != y:
            fields[0] = str(y)
        fields[1] = wyt[y]
        return ",".join(fields)
    return edit


def gw_rates_edit(body, y):
    year_text = body.split()[0]
    return body if int(year_text) == y else body.replace(year_text, str(y), 1)


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
    # Every file is built before any is written, so a failed check leaves the run unchanged
    texts = {
        run / PLANNING / "mm_pcp.csv": clip_daily(
            src / f"mm_pcp4{tag}.csv", run / PLANNING / "mm_pcp.csv", days,
            lambda f: pd.Timestamp(int(f[0]), int(f[1]), int(f[2]))),
        run / PLANNING / "LODI_PT.csv": clip_daily(
            src / f"LODI_PT4{tag}.csv", run / PLANNING / "LODI_PT.csv", days,
            lambda f: pd.Timestamp(f[0])),
        run / PLANNING / "calender.txt": calender_text(run / PLANNING / "calender.txt", days),
    }
    for p in landuse:
        texts[p] = per_year_text(p, 2, years, lambda ln: int(float(ln.split(",")[0])),
                                 landuse_edit(wyt))
    for f in ("GW_RATES.TXT", "GW_RATES_CALSIM3.TXT"):
        texts[run / NODCU / f] = per_year_text(run / NODCU / f, 0, years,
                                               lambda ln: int(ln.split()[0]), gw_rates_edit)
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
