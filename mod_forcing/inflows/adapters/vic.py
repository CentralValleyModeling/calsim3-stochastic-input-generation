"""
VIC 4.2.d
=========
Adapter of VIC 4.2.d with the CalSim LTO parameters (``inflow_model`` ``vic``), the model of
v1.0's rim inflows: each arc is the area-weighted RUNOFF + BASEFLOW of its GridInfo cells, as
v1.0 routed it.

- Model folder (``inflow_repo``): v1.0's ``VIC_Support_4.2.d`` in the archive, read only. Not a
  git repository, so ``inflow_pin`` is the sha256 of its files (``FILES``).
- Environment (``inflow_env``): the WSL distribution vicNl runs in, on its own file system.
- Forcing: one text file per cell (prcp, tmax, tmin, wind), built from BASE with the LTO wind;
  the historical x10 spikes are divided by 10. Product B runs in one pass and its flux rows are
  read by position, one per stamp day.
- Flux store: the daily fluxes stay in <generated>/mod_forcing/inflows/vic_fluxes/, one xz file
  per cell (``fluxes_<cell>.xz``, about a sixth of VIC's text), and are reused while the model
  version and inputs match. G1 reruns 8 cells and requires them to repeat the store byte for
  byte.
"""

import hashlib
import json
import lzma
import os
import shlex
import subprocess
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from mod_forcing.inflows.adapters import x10_days, ymd
from utils.paths import (INFLOW_FORCINGS, get_base_dir, get_module_generated_dir, remove_tree,
                         sha256_file)
from utils.wgen_calendar import require_stamp_days, stamp_month_of_day

LABEL = "VIC"
FORCINGS = {"historical": "Historical_Unsplit", "A": "WGEN_Product_A_1", "B": "WGEN_Product_B_1"}
BUILT = {"historical", "A", "B"}

# the model's files, relative to its folder; version() hashes them
FILES = {
    "binary": "src/vicNl",
    "soil": "parameters/Soil_Parameters_LTO_4097.txt",
    "veg_library": "parameters/LDAS_veg_lib",
    "veg_parameters": "parameters/vic.veg.0625.new.cal.adj.can",
    "snow_bands": "parameters/vic.snow.0625.new.cal.adj.can",
    **{f"global_{f}": f"global_{name}.txt" for f, name in FORCINGS.items()},
}
# global-file keys that name a path: replaced in each run's copy of the file
PATH_KEYS = {"SOIL": "soil", "VEGLIB": "veg_library", "VEGPARAM": "veg_parameters",
             "SNOW_BAND": "snow_bands"}

_REPO = Path(__file__).resolve().parents[3]
GRID_INFO = _REPO / "mod_forcing" / "climate" / "reference" / "GridInfo"
MAPPING_CSV = _REPO / "mod_hydrology" / "rim_inflow" / "reference" / "CalSim3_inflow_mapping.csv"
X10_CSV = _REPO / "mod_hydrology" / "rim_inflow" / "reference" / "prcp_x10_artifacts.csv"
ARC_GRID = {"I_SHSTA": "I_SHSTA_no_gooselake"}     # Shasta's drainage without the Goose Lake cells
VALLEY_NODE = "I_SRBB_VAL"

WIND_DIR = Path("Historical_Climate_LTO") / "1_Historical"          # under BASE
WIND_START = "1915-01-01"                                           # first row of a wind file
RESAMPLED = Path("WGEN") / "resampled.dates_Product_B_1000yr.csv"  # under BASE
FLUX_COLUMNS = ["year", "month", "day", "evap", "runoff", "baseflow", "pet_h2osurf", "pet_short"]
MM_KM2_TO_TAF = 1e12 * 8.10714e-13 / 1e3       # v1.0's factor: 1 mm on 1 km^2, in TAF
X10_DECIMALS = 4
N_G1 = 8                                        # cells G1 reruns
XZ_PRESET = 6                                   # the flux store's xz level
WORKERS = min(16, os.cpu_count() or 1)


# ---------------------------------------------------------------------------
# The model, its cells and its version
# ---------------------------------------------------------------------------

def version(repo: Path) -> dict:
    """The sha256 of the model's files (``FILES``): of the lines ``<path> <sha256>`` in path
    order. A change to any of them changes it, so no file counts as modified."""
    lines = [f"{rel} {sha256_file(repo / rel)}" for rel in sorted(FILES.values())]
    return {"version": hashlib.sha256("\n".join(lines).encode()).hexdigest(), "modified": []}


def soil_lines(repo: Path) -> dict[str, str]:
    """Cell key (``<lat>_<lon>``, 5 decimals as in the file names) -> its line of the soil
    parameter file, for the cells VIC runs (run flag 1)."""
    out = {}
    with open(repo / FILES["soil"], newline="") as fh:
        for line in fh:
            tok = line.split()
            if tok and tok[0] == "1":
                out[f"{float(tok[2]):.5f}_{float(tok[3]):.5f}"] = line
    return out


def inputs(repo: Path, forcing: str, build_dir: Path) -> list[Path]:
    """The forcing file of each cell VIC runs."""
    return [build_dir / f"meteo_{k}" for k in soil_lines(repo)]


def flux_store(forcing: str) -> Path:
    return get_module_generated_dir("mod_forcing/inflows") / "vic_fluxes" / INFLOW_FORCINGS[forcing]


def stored(store: Path, key: str) -> Path:
    """A cell's flux file in the store."""
    return store / f"fluxes_{key}.xz"


# ---------------------------------------------------------------------------
# Forcing: build and check (G2)
# ---------------------------------------------------------------------------

def _wind(key: str) -> np.ndarray:
    w = pd.read_csv(get_base_dir() / WIND_DIR / f"data_{key}", sep=r"\s+", header=None, usecols=[3])
    return w[3].to_numpy(float)


def _day_offsets(w: pd.DataFrame) -> np.ndarray:
    """Days from WIND_START of a WGEN file's dated rows."""
    d = pd.to_datetime(pd.DataFrame({"year": w["y"], "month": w["m"], "day": w["d"]}))
    return ((d - pd.Timestamp(WIND_START)).dt.days).to_numpy()


def _resampled_offsets() -> np.ndarray:
    """Product B: per stamp day, the day (from WIND_START) whose wind it takes."""
    r = pd.read_csv(get_base_dir() / RESAMPLED)
    require_stamp_days(len(r), RESAMPLED.name)
    d = pd.to_datetime(r["resmplDatesLoc"], format="%m/%d/%Y")
    return ((d - pd.Timestamp(WIND_START)).dt.days).to_numpy()


def _forcing_values(forcing: str, key: str, w: pd.DataFrame, x10: set, resampled) -> tuple:
    """The four forcing columns of a cell from its WGEN rows ``w`` (prcp with the x10 spikes
    divided by 10 for historical), and the positions of those spikes."""
    wind = _wind(key)
    pos = resampled if forcing == "B" else _day_offsets(w)
    if pos.min() < 0 or pos.max() >= len(wind):
        raise SystemExit(f"cell {key}: days outside the wind record ({len(wind)} days from {WIND_START})")
    prcp = w["prcp"].to_numpy(float).copy()
    hits = np.flatnonzero(np.isin(ymd(w), list(x10))) if x10 else np.array([], dtype=int)
    prcp[hits] = [float(f"{v / 10:.{X10_DECIMALS}f}") for v in prcp[hits]]
    return (prcp, w["tmax"].to_numpy(float), w["tmin"].to_numpy(float), wind[pos]), hits


def _write_cell(job) -> str:
    forcing, key, read_base, out, x10, resampled = job
    w = read_base(key)
    if forcing == "B":
        require_stamp_days(len(w), f"BASE cell {key}")
    cols, _ = _forcing_values(forcing, key, w, x10, resampled)
    pd.DataFrame(dict(zip(("prcp", "tmax", "tmin", "wind"), cols))).to_csv(
        out, sep="\t", header=False, index=False, lineterminator="\n")
    return key


def build_inputs(repo: Path, forcing: str, read_base, build_dir: Path, source: str) -> list[Path]:
    """Write the forcing file of every cell VIC runs: WGEN's prcp, tmax and tmin, and the LTO
    wind of the same day (historical, A) or of the day WGEN resampled (B); in the historical
    forcing the x10 spikes divided by 10 to 4 decimals, as v1.0's rerun of them did."""
    keys = list(soil_lines(repo))
    build_dir.mkdir(parents=True, exist_ok=True)
    resampled = _resampled_offsets() if forcing == "B" else None
    x10 = x10_days(X10_CSV, keys) if forcing == "historical" else {}
    jobs = [(forcing, k, read_base, build_dir / f"meteo_{k}", x10.get(k, set()), resampled)
            for k in keys]
    with ProcessPoolExecutor(WORKERS) as pool:
        for i, _ in enumerate(pool.map(_write_cell, jobs, chunksize=8), 1):
            if i % 500 == 0:
                print(f"  {i}/{len(keys)} cells written", flush=True)
    (build_dir / "forcing_source.json").write_text(json.dumps(
        {"source": source, "wind": (Path("BASE") / WIND_DIR).as_posix(),
         "wind_days": "resampled dates" if forcing == "B" else "same day",
         "x10_spikes_divided": sum(len(v) for v in x10.values())}, indent=1))
    return inputs(repo, forcing, build_dir)


def _check_cell(job) -> dict:
    forcing, key, path, read_base, x10, resampled = job
    got = pd.read_csv(path, sep=r"\s+", header=None).to_numpy(float)
    w = read_base(key)
    if got.shape != (len(w), 4):
        raise SystemExit(f"{path.name}: {got.shape[0]} rows x {got.shape[1]}, BASE has {len(w)} days")
    want, hits = _forcing_values(forcing, key, w, x10, resampled)
    out = {"key": key, "days": len(w), "x10_pairs": len(hits)}
    for j, v in enumerate(("prcp", "tmax", "tmin", "wind")):
        diff = np.abs(got[:, j] - want[j])
        out[v] = (float(diff.max()), int((diff > 0).sum()))
    return out


def check_inputs(repo: Path, forcing: str, files: list[Path], read_base,
                 n_cells: int | None) -> pd.DataFrame:
    """Gate G2: every value of the forcing files of ``n_cells`` seeded cells, or of all, against
    BASE: prcp, tmax and tmin against WGEN, wind against the LTO wind record. Values must match
    exactly, as text read back."""
    keys = list(soil_lines(repo))
    by_key = dict(zip(keys, files, strict=True))
    if n_cells is None or n_cells >= len(keys):
        pick = keys
    else:
        pick = [keys[i] for i in np.sort(np.random.default_rng(0).choice(len(keys), n_cells,
                                                                          replace=False))]
    resampled = _resampled_offsets() if forcing == "B" else None
    x10 = x10_days(X10_CSV, keys) if forcing == "historical" else {}
    print(f"{len(keys)} forcing files; checking {len(pick)}")
    jobs = [(forcing, k, by_key[k], read_base, x10.get(k, set()), resampled) for k in pick]
    rows = []
    with ProcessPoolExecutor(WORKERS) as pool:
        for i, r in enumerate(pool.map(_check_cell, jobs, chunksize=8), 1):
            for v in ("prcp", "tmax", "tmin", "wind"):
                rows.append({"variable": v, "cells": 1, "days": r["days"],
                             "max_abs_diff": r[v][0], "outside_tol": r[v][1],
                             "x10_pairs": r["x10_pairs"] if v == "prcp" else 0,
                             "input": by_key[r["key"]]})
            if i % 500 == 0:
                print(f"  {i}/{len(pick)} cells", flush=True)
    out = pd.DataFrame(rows)
    out["pass"] = out["outside_tol"] == 0
    return out[["variable", "cells", "days", "max_abs_diff", "outside_tol", "x10_pairs", "pass",
                "input"]]


# ---------------------------------------------------------------------------
# Running VIC under WSL
# ---------------------------------------------------------------------------

def _wsl_path(p: Path) -> str:
    """A Windows path as WSL sees it (/mnt/<drive>/...), with short (8.3) names expanded."""
    s = os.path.realpath(str(p).removeprefix("\\\\?\\")).removeprefix("\\\\?\\")
    return f"/mnt/{s[0].lower()}{s[2:]}".replace("\\", "/")


def _bash(env: str, script: str) -> str:
    return subprocess.run(["wsl", "-d", env, "-e", "bash", "-c", script], capture_output=True,
                          text=True, check=True).stdout


def check_environment(repo: Path, env: str) -> dict:
    """The WSL distribution's machine type, and the version line vicNl prints there."""
    out = _bash(env, f"uname -m; {shlex.quote(_wsl_path(repo / FILES['binary']))} -v 2>&1 | head -1")
    machine, vic = (out.strip().splitlines() + ["", ""])[:2]
    return {"wsl_distro": env, "machine": machine, "vicNl": vic.strip("* ").strip(),
            "ok": machine == "x86_64" and "VIC Version 4.2.d" in vic}


def _global_file(repo: Path, forcing: str, stage: str, soil: str) -> str:
    """The forcing's global file with every path pointing into the staging folder."""
    text = (repo / FILES[f"global_{forcing}"]).read_text().splitlines()
    out, seen = [], set()
    for line in text:
        tok = line.split()
        key = tok[0] if tok else ""
        if key in PATH_KEYS:
            named = Path(tok[2] if key == "SNOW_BAND" else tok[1]).name
            if named != Path(FILES[PATH_KEYS[key]]).name:
                raise SystemExit(f"{FILES[f'global_{forcing}']}: {key} names {named}, not "
                                 f"{FILES[PATH_KEYS[key]]}")
            path = soil if key == "SOIL" else f"{stage}/params/{named}"
            line = f"SNOW_BAND\t{tok[1]} {path}" if key == "SNOW_BAND" else f"{key}\t{path}"
        elif key == "FORCING1":
            line = f"FORCING1\t{stage}/forcing/meteo_"
        elif key == "RESULT_DIR":
            line = f"RESULT_DIR\t{stage}/out"
        else:
            out.append(line)
            continue
        seen.add(key)
        out.append(line)
    missing = ({"FORCING1", "RESULT_DIR"} | set(PATH_KEYS)) - seen
    if missing:
        raise SystemExit(f"{FILES[f'global_{forcing}']}: no {sorted(missing)}")
    return "\n".join(out) + "\n"


def run_cells(repo: Path, env: str, forcing: str, keys: list[str], forcing_dir: Path,
              dest: Path) -> list[list[str]]:
    """Run VIC on ``keys`` under WSL, in up to WORKERS parallel batches, and copy their flux
    files (``fluxes_<key>``) into ``dest``; return the command that ran each batch."""
    soil = soil_lines(repo)
    home = _bash(env, "echo $HOME").strip()
    stage = f"{home}/csstochastic_vic/{uuid.uuid4().hex}"
    unc = Path(f"\\\\wsl.localhost\\{env}" + stage.replace("/", "\\"))
    q = shlex.quote
    _bash(env, f"mkdir -p {q(stage)}/forcing {q(stage)}/params {q(stage)}/out")
    try:
        (unc / "cells.txt").write_text("".join(f"meteo_{k}\n" for k in keys), newline="\n")
        params = " ".join(q(_wsl_path(repo / FILES[r])) for r in ("binary", *PATH_KEYS.values()))
        _bash(env, f"cp {params} {q(stage)}/params/ && cd {q(_wsl_path(forcing_dir))} && "
                   f"xargs -a {q(stage)}/cells.txt cp -t {q(stage)}/forcing/")
        batches = [keys[i::WORKERS] for i in range(min(WORKERS, len(keys)))]
        cmds = []
        for b, batch in enumerate(batches):
            (unc / f"soil_{b:02d}.txt").write_text("".join(soil[k] for k in batch), newline="")
            (unc / f"global_{b:02d}.txt").write_text(
                _global_file(repo, forcing, stage, f"{stage}/soil_{b:02d}.txt"), newline="\n")
            cmds.append(["wsl", "-d", env, "vicNl", "-g", f"global_{b:02d}.txt",
                         f"({len(batch)} cells)"])
        script = (f"cd {q(stage)} || exit 1; " + " ".join(
            f"( params/vicNl -g global_{b:02d}.txt > vic_{b:02d}.log 2>&1; echo $? > rc_{b:02d} ) &"
            for b in range(len(batches))) + " wait")
        print(f"VIC: {len(keys)} cells in {len(batches)} batches under WSL {env}", flush=True)
        _bash(env, script)
        failed = [b for b in range(len(batches)) if (unc / f"rc_{b:02d}").read_text().strip() != "0"]
        if failed:
            tail = (unc / f"vic_{failed[0]:02d}.log").read_text()[-2000:]
            raise SystemExit(f"vicNl failed in batch(es) {failed}:\n{tail}")
        dest.mkdir(parents=True, exist_ok=True)
        _bash(env, f"cd {q(stage)}/out && find . -name 'fluxes_*' -print0 | "
                   f"xargs -0 cp -t {q(_wsl_path(dest))}")
        made = {p.name for p in dest.glob("fluxes_*")}
        lost = [k for k in keys if f"fluxes_{k}" not in made]
        if lost:
            raise SystemExit(f"VIC wrote no fluxes for {len(lost)} cell(s), e.g. {lost[:3]}")
        return cmds
    finally:
        _bash(env, f"rm -rf {q(stage)}")


def _compress(path: Path) -> None:
    """Replace one flux file by its xz copy, once the copy reads back to the same bytes."""
    raw = path.read_bytes()
    xz = path.with_name(path.name + ".xz")
    tmp = xz.with_name(xz.name + ".tmp")
    tmp.write_bytes(lzma.compress(raw, preset=XZ_PRESET))
    if lzma.decompress(tmp.read_bytes()) != raw:
        raise SystemExit(f"{tmp}: does not decompress to {path.name}")
    tmp.replace(xz)
    path.unlink()


def compress_store(store: Path) -> int:
    """xz-compress the store's uncompressed flux files; return how many there were."""
    raw = [p for p in store.glob("fluxes_*") if not p.name.endswith(".xz")]
    with ProcessPoolExecutor(WORKERS) as pool:
        list(pool.map(_compress, raw, chunksize=4))
    return len(raw)


def _store_identity(repo: Path, forcing: str, files: list[Path]) -> dict:
    """What the store's fluxes must come from: the model version and the inputs, by the sha256
    G2 recorded (``forcing_identity.csv`` beside them; _2_run_product.py checked it is current)."""
    g2 = pd.read_csv(files[0].parent / "forcing_identity.csv")
    sha = dict(zip(g2["input"], g2["input_sha256"]))
    return {"model_version": version(repo)["version"], "forcing": forcing,
            "inputs": {f.name: sha[f.name] for f in files}}


def run(repo: Path, env: str, forcing: str, files: list[Path], out_dir: Path) -> list[list[str]]:
    """Fill or reuse the flux store (module docstring), rerun G1's cells, and route the store's
    fluxes to the arcs (``out_dir/arc_monthly.csv``)."""
    store, want = flux_store(forcing), _store_identity(repo, forcing, files)
    keys = list(soil_lines(repo))
    have = json.loads((store / "store.json").read_text()) if (store / "store.json").exists() else {}
    reused = all(have.get(k) == want[k] for k in want)
    cmds = []
    if not reused:
        remove_tree(store)
        cmds += run_cells(repo, env, forcing, keys, files[0].parent, store)
        print(f"Compressing {compress_store(store)} flux files (xz)", flush=True)
        (store / "store.json").write_text(json.dumps(
            {**want, "source": f"VIC run of {datetime.now(timezone.utc):%Y-%m-%d}",
             "cells": len(keys)}, indent=1))
    pick = sorted(np.random.default_rng(0).choice(keys, N_G1, replace=False).tolist())
    cmds += run_cells(repo, env, forcing, pick, files[0].parent, out_dir / "g1")
    same = [(out_dir / "g1" / f"fluxes_{k}").read_bytes() == lzma.decompress(stored(store, k).read_bytes())
            for k in pick]
    g1 = {"store": str(store), "store_source": json.loads((store / "store.json").read_text())["source"],
          "reused": reused, "cells": pick, "identical": same, "pass": all(same)}
    (out_dir / "g1.json").write_text(json.dumps(g1, indent=1))
    print(f"G1: {sum(same)}/{len(pick)} cells repeat the flux store byte for byte", flush=True)
    if g1["pass"]:
        route(forcing, store).to_csv(out_dir / "arc_monthly.csv", index=False, float_format="%.10g")
    return cmds


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def arc_grids() -> dict[str, Path]:
    """Arc -> GridInfo file, for the arcs the builder reads (arc, and gap where the arc has a
    GridInfo) and the valley node."""
    m = pd.read_csv(MAPPING_CSV, keep_default_na=False)
    out = {}
    for arc, method in zip(m["CS3_Inflow"], m["Method"]):
        if method not in ("arc", "gap"):
            continue
        path = GRID_INFO / f"CS3_{ARC_GRID.get(arc, arc)}_GridInfo.txt"
        if path.exists():
            out[arc] = path
        elif method == "arc":
            raise SystemExit(f"{arc}: no GridInfo file {path.name}")
    out[VALLEY_NODE] = GRID_INFO / f"CS3_{VALLEY_NODE}_GridInfo.txt"
    return out


def _monthly(job) -> tuple[str, np.ndarray, np.ndarray]:
    """One flux file: its RUNOFF + BASEFLOW (mm) summed by month, and the months' index (months
    since January of the first year for historical and A; stamp months for B)."""
    forcing, path = job
    f = pd.read_csv(path, sep=r"\s+", header=None, names=FLUX_COLUMNS,
                    usecols=["year", "month", "runoff", "baseflow"])
    q = f["runoff"].to_numpy(float) + f["baseflow"].to_numpy(float)
    if forcing == "B":
        require_stamp_days(len(f), path.name)
        month = stamp_month_of_day()
    else:
        month = (f["year"].to_numpy() - f["year"].iloc[0]) * 12 + f["month"].to_numpy() - 1
    sums = np.bincount(month, weights=q)
    return path.name.removeprefix("fluxes_").removesuffix(".xz"), sums, np.array([f["year"].iloc[0]])


def route(forcing: str, store: Path) -> pd.DataFrame:
    """Every arc's monthly flow in TAF from the store's fluxes, over its complete water years."""
    grids = {a: pd.read_csv(p, sep="\t", header=None, names=["id", "lat", "lon", "f1", "f2"])
             for a, p in arc_grids().items()}
    for g in grids.values():
        g["key"] = [f"{la:.5f}_{lo:.5f}" for la, lo in zip(g["lat"], g["lon"])]
    keys = sorted(set().union(*(set(g["key"]) for g in grids.values())))
    absent = [k for k in keys if not stored(store, k).exists()]
    if absent:
        raise SystemExit(f"{store}: no fluxes for {len(absent)} GridInfo cell(s), e.g. {absent[:3]}")
    print(f"Routing {len(grids)} arcs from {len(keys)} cells' fluxes", flush=True)
    with ProcessPoolExecutor(WORKERS) as pool:
        got = list(pool.map(_monthly, [(forcing, stored(store, k)) for k in keys], chunksize=8))
    first = {int(y[0]) for _, _, y in got}
    if len(first) != 1 or len({len(s) for _, s, _ in got}) != 1:
        raise SystemExit(f"{store}: the flux files cover different spans")
    cell = {k: s for k, s, _ in got}
    n = len(got[0][1])
    if forcing == "B":
        year, month = np.arange(n) // 12 + 1, np.arange(n) % 12 + 1      # stamp years from 1
    else:
        year, month = first.pop() + np.arange(n) // 12, np.arange(n) % 12 + 1
    wy = pd.Series(year + (month >= 10))
    whole = (wy.map(wy.value_counts()) == 12).to_numpy()        # complete water years only
    rows = []
    for arc, g in grids.items():
        frac = (g["f2"] / g["f1"]).to_numpy()
        depth = sum(fr * cell[k] for fr, k in zip(frac, g["key"])) / frac.sum()
        taf = depth * g["f2"].sum() * MM_KM2_TO_TAF
        rows.append(pd.DataFrame({"arc": arc, "year": year[whole], "month": month[whole],
                                  "taf": taf[whole],
                                  "kind": "valley" if arc == VALLEY_NODE else "area_weighted"}))
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------------------
# After the run
# ---------------------------------------------------------------------------

def describe(repo: Path, forcing: str, out_dir: Path) -> dict:
    g1 = json.loads((out_dir / "g1.json").read_text())
    return {"model": "VIC 4.2.d (CalSim LTO parameters), area-weighted RUNOFF + BASEFLOW",
            "files": FILES,
            "run": {"flux_store": g1["store"], "store_source": g1["store_source"],
                    "store_reused": g1["reused"], "workers": WORKERS,
                    "arc_gridinfo": {a: p.name for a, p in arc_grids().items()}}}


def gates(repo: Path, forcing: str, out_dir: Path) -> dict:
    """G1: the 8 seeded cells rerun now repeat the flux store byte for byte."""
    return {"G1": json.loads((out_dir / "g1.json").read_text())}


def arc_flows(forcing: str, out_dir: Path) -> pd.DataFrame:
    return pd.read_csv(out_dir / "arc_monthly.csv")
