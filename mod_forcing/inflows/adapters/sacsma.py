"""
SAC-SMA dPL-CalSim
==================
Adapter of the rim-inflow model SAC-SMA (``inflow_model`` ``sacsma``): its dPL-CalSim model
(run ``8_calsim`` at the current pin) with its share model, which divides each multi-arc
system's flow among its arcs. It runs through the product command of SAC-SMA's CLI, in the
conda environment ``inflow_env``:

    conda run -n <inflow_env> sacsma dpl calsim product apply --forcing <store> --out <folder>

Without ``--out``, SAC-SMA writes into its own tracked ``artifacts/product/calsim3/``. That
tracked copy is the series G1 compares the run with.

Input. SAC-SMA does not read the WGEN text files during a run. It reads a NetCDF store of the
4,410 grid cells it uses (``prcp``, ``tmin``, ``tmax``, daily) under ``data/inputs/forcing/``:
``historical_livneh_unsplit.nc`` (WGEN NonDetrend-Unsplit, the model's training forcing) and
``wgen_product_a.nc`` (WGEN Product A scenario 1). G2 requires each store value to equal the
text value to float32 precision, with two exceptions the store makes on purpose:

- it sorts an inverted temperature pair (tmin above tmax) into order, so it is compared with
  the sorted text pair;
- in the historical store SAC-SMA divides 289 documented x10 precipitation spikes by 10
  (``prcp_x10_artifacts.csv``), so those (cell, day) pairs are compared with a tenth of the
  text value.

The G2 table reports per variable the days compared, the largest absolute difference, the
values outside tolerance and the x10 pairs among the cells checked.

Output. ``rim_inflow_monthly.csv`` (arc, month, taf, dpl_taf, kind) holds the 196 arcs:
``taf`` is the product flow, ``kind`` share, single-arc system or non-anchor.
``tier2/tier2_monthly.csv`` holds the Sacramento valley node I_SRBB_VAL (UNIMP_SRBB is the sum
of its 8 arcs and this node), and ``tier2/tier2_run_info.json`` names the checkpoint and
extension cells the run used.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

LABEL = "SAC-SMA"
FORCINGS = {"historical": "historical_livneh_unsplit", "A": "wgen_product_a"}

# relative to the SAC-SMA repository; apply uses the default share model
STORE_DIR = Path("data") / "inputs" / "forcing"
X10_CSV = STORE_DIR / "prcp_x10_artifacts.csv"
PRODUCT_DIR = Path("artifacts") / "product" / "calsim3"
SHARE_MODEL = PRODUCT_DIR / "share_model.pt"
VALLEY_NODE = "I_SRBB_VAL"
N_ARCS = 196
RTOL = ATOL = 1e-6          # G2: float32 holds the text's 2-3 decimals well inside this
G1_RTOL = 1e-5
G1_FLOOR = 1e-3             # TAF; G1 takes relative differences against at least this


def conda() -> str:
    path = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not path:
        raise SystemExit("conda not found (CONDA_EXE unset and conda not on PATH)")
    return path


def input_file(repo: Path, forcing: str) -> Path:
    """The NetCDF forcing store of ``forcing``."""
    return repo / STORE_DIR / f"{FORCINGS[forcing]}.nc"


def check_input(repo: Path, forcing: str, read_base, n_cells: int | None) -> pd.DataFrame:
    """Gate G2: the store against the WGEN text files, on ``n_cells`` seeded cells or all."""
    ds = netCDF4.Dataset(input_file(repo, forcing))
    keys = np.asarray(ds["key"][:]).astype(str)
    time = pd.to_datetime(netCDF4.num2date(ds["time"][:], ds["time"].units,
                                           only_use_cftime_datetimes=False,
                                           only_use_python_datetimes=True))
    if n_cells is None or n_cells >= len(keys):
        idx = np.arange(len(keys))
    else:
        idx = np.sort(np.random.default_rng(0).choice(len(keys), n_cells, replace=False))
    print(f"{len(keys)} cells x {len(time)} days in the store; checking {len(idx)} cells")

    x10 = {}    # cell -> day indices of its x10 spikes
    if forcing == "historical":
        t = pd.read_csv(repo / X10_CSV, parse_dates=["date"])
        for k, g in t.groupby("key"):
            x10[k] = time.get_indexer(pd.DatetimeIndex(g["date"]))

    rows = {v: dict(variable=v, cells=0, days=0, max_abs_diff=0.0, outside_tol=0, x10_pairs=0)
            for v in ("prcp", "tmin", "tmax")}
    for n, i in enumerate(idx, 1):
        k = keys[i]
        w = read_base(k)
        if len(w) != len(time):
            raise SystemExit(f"cell {k}: {len(w)} rows in BASE, the store has {len(time)} days")
        dates = pd.to_datetime(dict(year=w["y"], month=w["m"], day=w["d"]))
        if not (dates.to_numpy() == time.to_numpy()).all():
            raise SystemExit(f"cell {k}: the BASE dates differ from the store's time axis")
        lo = np.minimum(w["tmin"].to_numpy(), w["tmax"].to_numpy())
        hi = np.maximum(w["tmin"].to_numpy(), w["tmax"].to_numpy())
        text = {"prcp": w["prcp"].to_numpy(float), "tmin": lo, "tmax": hi}
        for v, ref in text.items():
            got = np.asarray(ds[v][i, :], dtype=float)
            exp = ref.copy()
            if v == "prcp" and k in x10:
                hits = x10[k]
                exp[hits] = exp[hits] / 10.0
                rows[v]["x10_pairs"] += len(hits)
            d = np.abs(got - exp)
            r = rows[v]
            r["cells"] += 1
            r["days"] += len(d)
            r["max_abs_diff"] = max(r["max_abs_diff"], float(d.max()))
            r["outside_tol"] += int((~np.isclose(got, exp, rtol=RTOL, atol=ATOL)).sum())
        if n % 50 == 0:
            print(f"  {n}/{len(idx)} cells")
    ds.close()

    out = pd.DataFrame(rows.values())
    out["pass"] = out["outside_tol"] == 0
    out["input_cells"] = len(keys)
    return out


def check_environment(repo: Path, env: str) -> dict:
    """The repository the conda environment imports the ``sacsma`` package from."""
    out = subprocess.run([conda(), "run", "-n", env, "python", "-c",
                          "import sacsma; print(sacsma.__file__)"],
                         capture_output=True, text=True, check=True).stdout
    package = Path(out.strip().splitlines()[-1]).resolve().parents[1]
    return {"conda_env": env, "package": str(package), "ok": package == repo.resolve()}


def command(repo: Path, env: str, forcing: str, out_dir: Path) -> list[str]:
    return [conda(), "run", "-n", env, "--no-capture-output",
            "sacsma", "dpl", "calsim", "product", "apply",
            "--forcing", FORCINGS[forcing], "--out", str(out_dir)]


def describe(repo: Path, out_dir: Path) -> dict:
    """The checkpoint and extension cells the run used, as its record names them."""
    info = json.loads((out_dir / "tier2" / "tier2_run_info.json").read_text())
    return {"model": f"SAC-SMA dPL-CalSim (run {Path(info['checkpoint']).parents[1].name}) "
                     "with its share model",
            "files": {"checkpoint": info["checkpoint"],
                      "extension_cells": info["extension_cells"],
                      "share_model": SHARE_MODEL.as_posix()},
            "run": {"pass_envelope": info.get("envelope")}}


def rel_diff(new: pd.Series, old: pd.Series) -> dict:
    """Largest relative difference, and the rows where either side is missing."""
    d = (new - old).abs() / np.maximum(old.abs(), G1_FLOOR)
    return {"max_rel_diff": float(d.max()) if d.notna().any() else 0.0,
            "missing": int(d.isna().sum())}


def valley(run_dir: Path, months) -> pd.DataFrame:
    t = pd.read_csv(run_dir / "tier2" / "tier2_monthly.csv", usecols=["arc", "month", "sim_taf"])
    return t[(t["arc"] == VALLEY_NODE) & t["month"].isin(months)]


def reproduce(repo: Path, forcing: str, out_dir: Path) -> dict:
    """Gate G1: the run against the series SAC-SMA tracks for the same forcing: ``taf`` and
    ``dpl_taf`` of every arc-month to a relative difference of 1e-5, the same ``kind``, and
    I_SRBB_VAL. A missing value on either side fails."""
    tracked_dir = repo / PRODUCT_DIR / FORCINGS[forcing]
    a = pd.read_csv(out_dir / "rim_inflow_monthly.csv")
    b = pd.read_csv(tracked_dir / "rim_inflow_monthly.csv")
    m = a.merge(b, on=["arc", "month"], how="outer", suffixes=("", "_tracked"), indicator=True)
    unmatched = int((m["_merge"] != "both").sum())
    m = m[m["_merge"] == "both"]
    va = valley(out_dir, set(a["month"]))
    vb = valley(tracked_dir, set(a["month"]))
    v = va.merge(vb, on="month", how="outer", suffixes=("", "_tracked"))
    out = {"tracked": str(tracked_dir), "arc_months": int(len(m)), "unmatched_rows": unmatched,
           "kind_mismatches": int((m["kind"] != m["kind_tracked"]).sum()),
           "taf": rel_diff(m["taf"], m["taf_tracked"]),
           "dpl_taf": rel_diff(m["dpl_taf"], m["dpl_taf_tracked"]),
           "valley_months": int(len(v)),
           "valley": rel_diff(v["sim_taf"], v["sim_taf_tracked"])}
    diffs = [out[k] for k in ("taf", "dpl_taf", "valley")]
    out["pass"] = bool(unmatched == 0 and out["kind_mismatches"] == 0
                       and out["valley_months"] == a["month"].nunique()
                       and all(d["missing"] == 0 and d["max_rel_diff"] <= G1_RTOL for d in diffs))
    return out


def arc_flows(out_dir: Path) -> pd.DataFrame:
    """The 196 arcs and the valley node (``kind`` valley) over the product's months."""
    prod = pd.read_csv(out_dir / "rim_inflow_monthly.csv", usecols=["arc", "month", "taf", "kind"])
    if prod["arc"].nunique() != N_ARCS:
        raise SystemExit(f"{out_dir}: {prod['arc'].nunique()} arcs, expected {N_ARCS}")
    months = set(prod["month"])
    val = valley(out_dir, months)
    if len(val) != len(months):
        raise SystemExit(f"{out_dir}: {VALLEY_NODE} covers {len(val)} of {len(months)} months")
    val = val.rename(columns={"sim_taf": "taf"}).assign(kind="valley")
    return pd.concat([prod, val[["arc", "month", "taf", "kind"]]], ignore_index=True)
