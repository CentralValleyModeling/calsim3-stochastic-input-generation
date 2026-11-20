"""
Build the CalSim 3 DSS of a DETAW-DCD Run
=========================================
Writes CS3sv_DCD_PRISM_Dtrnd.dss, the 28 monthly series CalSim 3 takes from a DETAW-DCD run, as
a DSS 6 file: the 24 node series of the run's DCD_<Mon><year>_Lch5_mon_C3.dss (IRR, SEEP and DRN
of eight nodes), copied with their pathnames, units and type, and four island sums of
DCD_island_month.dss. Each sum is the monthly DP-FLOW or GW-FLOW (CFS) of the 168 islands, each
island's flow times its Delta or WBA 50 weight. A record name that appears in both groups, an
irregular record or a gap in a record stops the script before it writes.

DCD.py names the node file after the last month of its weather (DCD_Sep2018_Lch5_mon_C3.dss
for a run ending in September 2018), so the script takes the one DCD_*_Lch*_mon_C3.dss of the
run. Run it after DCD.py (see _1b_prepare_dcd_run.py); _2_postprocess_single.py reads its output.

DCD.py goes on when DETAW fails, and its kernel then reruns on the previous DETAW output. So the
script first checks that DETAW ran on the run's weather: the island precipitation of percip.nc
must have one day per line of calender.txt and equal the station precipitation of mm_pcp.csv
times the island weights of Percentage.csv.

Inputs
------
- <run>/DCD/Output/CALSIM3/DCD_island_month.dss: /DICU-ISLAND/<island>/DP-FLOW and GW-FLOW
- <run>/DCD/Output/CALSIM3/DCD_*_Lch*_mon_C3.dss
- <run>/DETAW/Output/percip.nc and <run>/DETAW/Input/planning_study/mm_pcp.csv, Percentage.csv
  and calender.txt, for the check
- reference/WeightedRatiosForDCD.csv: Island, Delta, WBA50 (the share of each island in the
  Delta and in WBA 50)

Outputs
-------
- <run>/DCD/Output/CALSIM3/CS3sv_DCD_PRISM_Dtrnd.dss (DSS 6), the node records plus
  /CALSIM/DP_DELTA_DCD/DP-FLOW//1MON/L2015A/, /CALSIM/DP_WBA50_DCD/DP-FLOW//1MON/L2015A/,
  /CALSIM/GW_DELTA_DCD/GW-FLOW//1MON/L2015A/, /CALSIM/GW_WBA50_DCD/GW-FLOW//1MON/L2015A/

Dependencies
------------
utils.dss_io; pydsstools, netCDF4

Usage
-----
    python mod_hydrology/delta_channel_depletion/_1c_build_cs3sv_dss.py --run-dir <run>
"""

import argparse
import os
import sys
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd
from pydsstools.core import TimeSeriesContainer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io

WEIGHTS_CSV = Path(__file__).resolve().parent / "reference" / "WeightedRatiosForDCD.csv"
OUT_DIR = Path("DCD") / "Output" / "CALSIM3"
PLANNING = Path("DETAW") / "Input" / "planning_study"
PERCIP_NC = Path("DETAW") / "Output" / "percip.nc"
N_ISLANDS = 168
CS3SV = "CS3sv_DCD_PRISM_Dtrnd.dss"
# Part B of each island sum: (Part C of the island records, weight column)
SUMS = {"DP_DELTA_DCD": ("DP-FLOW", "Delta"), "DP_WBA50_DCD": ("DP-FLOW", "WBA50"),
        "GW_DELTA_DCD": ("GW-FLOW", "Delta"), "GW_WBA50_DCD": ("GW-FLOW", "WBA50")}
A_PART, F_PART = "CALSIM", "L2015A"


def check_detaw_current(run: Path) -> None:
    """Refuse a run whose DETAW output was not computed from its weather. DETAW/Output/percip.nc
    must hold one day per line of calender.txt and equal the station precipitation of mm_pcp.csv
    times the island weights of Percentage.csv, each station taking the Percentage column that
    starts with its first two letters, as DETAW.py matches them."""
    calender = [ln for ln in (run / PLANNING / "calender.txt").read_text().splitlines() if ln.strip()]
    pcp = pd.read_csv(run / PLANNING / "mm_pcp.csv")
    stations = list(pcp.columns[4:])
    per = pd.read_csv(run / PLANNING / "Percentage.csv", nrows=N_ISLANDS)
    weights = np.vstack([per[[c for c in per.columns[1:] if c[:2] == s[:2]][0]].to_numpy(dtype=float)
                         for s in stations])
    # Read from memory: the netCDF library does not open \\?\ long paths
    with netCDF4.Dataset("percip.nc", memory=(run / PERCIP_NC).read_bytes()) as ds:
        island_pcp = np.asarray(ds["precip"][:], dtype=float)
    if not len(calender) == len(pcp) == len(island_pcp):
        raise ValueError(f"{run / PERCIP_NC} holds {len(island_pcp)} days, calender.txt {len(calender)} "
                         f"and mm_pcp.csv {len(pcp)}: DETAW did not run on this weather")
    if not np.allclose(pcp[stations].to_numpy(dtype=float) @ weights, island_pcp, rtol=1e-9, atol=1e-9):
        raise ValueError(f"{run / PERCIP_NC} does not match mm_pcp.csv and Percentage.csv: DETAW did "
                         f"not run on this weather")


def read_records(dss_file: Path, part_c: str = "*") -> dict:
    """{(A, B, C, E, F) upper-cased: record} over the blocks of each record; a record is a dict
    of parts (as written), units, type, interval and the monthly Series on pydsstools times."""
    blocks = {}
    with dss_io.open_dss(dss_file) as dss:
        for path in dss.getPathnameList(f"/*/*/{part_c}/*/*/*/"):
            parts = path.strip("/").split("/")
            if parts[4].upper().startswith("IR-"):
                raise ValueError(f"{dss_file.name}: irregular record {path}")
            ts = dss.read_ts(path, trim_missing=True)
            if len(ts.values):
                key = tuple(parts[i].upper() for i in (0, 1, 2, 4, 5))
                blocks.setdefault(key, []).append((parts, ts.units, ts.type, ts.interval,
                    pd.Series(np.asarray(ts.values, dtype=float), index=pd.DatetimeIndex(ts.pytimes))))
    records = {}
    for key, bl in blocks.items():
        if len({(u, t) for _, u, t, _, _ in bl}) > 1:
            raise ValueError(f"{dss_file.name}: the blocks of {key} differ in units or type")
        series = pd.concat([s for *_, s in bl]).sort_index()
        months = series.index.to_period("M")
        if months.has_duplicates or len(months) != (months[-1] - months[0]).n + 1:
            raise ValueError(f"{dss_file.name}: {key} has repeated or missing months")
        parts, units, kind, interval, _ = bl[0]
        records[key] = {"parts": parts, "units": units, "type": kind, "interval": interval,
                        "series": series}
    return records


def island_sums(island_file: Path) -> dict:
    """The four island sums, keyed like read_records."""
    w = pd.read_csv(WEIGHTS_CSV).set_index("Island")
    if w.index.has_duplicates:
        raise ValueError(f"{WEIGHTS_CSV.name} repeats an island")
    out = {}
    for part_c in sorted({c for c, _ in SUMS.values()}):
        recs = read_records(island_file, part_c)
        islands = {int(k[1]): r for k, r in recs.items()}
        if set(islands) != set(w.index):
            raise ValueError(f"{island_file.name} {part_c} islands {len(islands)} do not match "
                             f"the {len(w)} of {WEIGHTS_CSV.name}")
        first = next(iter(islands.values()))
        if any(not r["series"].index.equals(first["series"].index) or
               (r["units"], r["type"]) != (first["units"], first["type"]) for r in islands.values()):
            raise ValueError(f"{island_file.name} {part_c}: islands differ in period, units or type")
        flows = np.vstack([islands[i]["series"].to_numpy() for i in w.index])
        for part_b, (c, col) in SUMS.items():
            if c != part_c:
                continue
            parts = [A_PART, part_b, first["parts"][2], "", first["parts"][4], F_PART]
            values = w[col].to_numpy(dtype=float) @ flows
            out[tuple(parts[i].upper() for i in (0, 1, 2, 4, 5))] = {
                "parts": parts, "units": first["units"], "type": first["type"],
                "interval": first["interval"],
                "series": pd.Series(values, index=first["series"].index)}
    return out


def write_records(dss_file: Path, records: dict) -> None:
    with dss_io.open_dss(dss_file, version=6, catalog_flag=False, create=True) as dss:
        for rec in records.values():
            a, b, c, _, e, f = rec["parts"]
            tsc = TimeSeriesContainer()
            tsc.pathname = f"/{a}/{b}/{c}//{e}/{f}/"
            tsc.startDateTime = rec["series"].index[0].strftime("%d%b%Y %H:%M")
            tsc.numberValues = len(rec["series"])
            tsc.units = rec["units"]
            tsc.type = rec["type"]
            tsc.interval = rec["interval"]
            tsc.values = rec["series"].to_numpy(dtype=float)
            dss.put_ts(tsc)


def main():
    ap = argparse.ArgumentParser(description="Build CS3sv_DCD_PRISM_Dtrnd.dss (DSS 6) of a "
                                             "DETAW-DCD run.")
    ap.add_argument("--run-dir", type=Path, required=True,
                    help="The DETAW-DCD run folder (holds DETAW/ and DCD/)")
    args = ap.parse_args()

    run = args.run_dir.resolve()
    check_detaw_current(run)
    out_dir = run / OUT_DIR
    nodes = sorted(out_dir.glob("DCD_*_Lch*_mon_C3.dss"))
    if len(nodes) != 1:
        raise FileNotFoundError(f"{out_dir} holds {len(nodes)} DCD_*_Lch*_mon_C3.dss files, not 1")
    records = read_records(nodes[0])
    sums = island_sums(out_dir / "DCD_island_month.dss")
    both = sorted(set(records) & set(sums))
    if both:
        raise ValueError(f"{nodes[0].name} already holds the island sums {both}")
    records.update(sums)
    print(f"{nodes[0].name}: {len(records) - len(sums)} records; island sums: {len(sums)}")

    # Written beside the old file, then moved over it, so a failed write leaves the old file
    tmp = out_dir / f"_{CS3SV}"
    tmp.unlink(missing_ok=True)
    write_records(tmp, records)
    os.replace(tmp, out_dir / CS3SV)
    print(f"Wrote {len(records)} records to {out_dir / CS3SV}")


if __name__ == "__main__":
    main()
