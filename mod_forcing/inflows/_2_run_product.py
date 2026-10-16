"""
Run the Rim-Inflow Model
========================
Runs the rim-inflow model on one forcing, checks it, and writes its monthly arc flows as the
one table the rim-inflow SVs are built from.

The model is the one the config names (``inflow_model``); at present SAC-SMA's dPL-CalSim
with its share model (adapters/sacsma.py). It lives in its own git repository
(``inflow_repo``), pinned to one commit (``inflow_commit``), and runs there as an external
command in its own environment (``inflow_env``). Its adapter builds the command, checks the
environment and the result, and reads the flows. The command writes into a temporary folder,
deleted after the run.

Forcings
--------
- historical : WGEN NonDetrend-Unsplit, the model's training forcing: the reference for skill
               and for the absorb fits of the second stage
- A          : WGEN Product A scenario 1

Product B runs in segments, in phase P3.

Checks
------
- The checkout's HEAD must be the pinned commit, with no modified tracked files, and the
  environment must run the model from that checkout; ``--allow-dirty`` runs anyway and the
  manifest records the state.
- Gate G2, before the run: forcing_identity.csv of _1_build_forcing.py must show a pass on
  every cell of the model's input, for the input's current sha256.
- Gate G1, after the run: the new series must repeat the series the model tracks at the pin
  (the adapter's ``reproduce``; skipped for a model that tracks none). If G1 fails, only the
  manifest is written.

Inputs
------
- the model checkout: its input for the forcing and the files the run used
- <generated>/mod_forcing/inflows/output/_1_build_forcing/<forcing>/forcing_identity.csv

Outputs
-------
- <generated>/mod_forcing/inflows/output/_2_run_product/<Historical_Unsplit|Product_A/1>/
  (deleted first)
  - arc_inflow_monthly.csv  (date, WY, month, arc, taf, kind), utils.paths.get_arc_inflows:
                            the model's arcs over the complete water years of the run (for
                            SAC-SMA the 196 arcs and the Sacramento valley node I_SRBB_VAL);
                            date is the month end, flows in TAF per month
  - run_manifest.json       model, commit, environment, sha256 of every file the run used,
                            forcing, water years, command, the G1 and G2 results. The
                            rim-inflow builder reads only flows whose manifest names the
                            configured model and pinned commit (utils.paths.require_pinned_run).

Usage
-----
    python mod_forcing/inflows/_2_run_product.py --forcing historical
    python mod_forcing/inflows/_2_run_product.py --forcing A
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_forcing.inflows.adapters import load
from utils.paths import (INFLOW_FORCINGS, INFLOW_PROVENANCE, get_arc_inflows, get_inflow_commit,
                         get_inflow_env, get_inflow_model, get_inflow_repo,
                         get_module_generated_dir, remove_tree, sha256_file)

_gen = get_module_generated_dir("mod_forcing/inflows")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def check_g2(forcing: str, input_sha: str) -> int:
    """Gate G2: stop unless _1_build_forcing.py passed on every cell of this input; return the
    number of cells."""
    path = _gen / "output" / "_1_build_forcing" / INFLOW_FORCINGS[forcing] / "forcing_identity.csv"
    rerun = f"run _1_build_forcing.py --forcing {forcing} --cells all"
    if not path.exists():
        raise SystemExit(f"G2 has not been run on this input: {path} is missing; {rerun}")
    g2 = pd.read_csv(path)
    if "input_cells" not in g2 or (g2["cells"] != g2["input_cells"]).any():
        raise SystemExit(f"{path}: G2 checked a sample, not every cell of the input; {rerun}")
    if not g2["pass"].all():
        raise SystemExit(f"{path}: G2 failed: the input differs from BASE")
    if set(g2["input_sha256"]) != {input_sha}:
        raise SystemExit(f"{path}: G2 checked another version of the input; {rerun}")
    return int(g2["input_cells"].iloc[0])


def tidy(flows: pd.DataFrame) -> pd.DataFrame:
    """The adapter's flows, one row per arc and month, dated by month end and water year."""
    if flows["taf"].isna().any():
        raise SystemExit(f"missing flows in {flows.loc[flows['taf'].isna(), 'arc'].unique()}")
    out = flows.copy()
    start = pd.to_datetime(out["month"], format="%Y-%m")
    out["date"] = start + pd.offsets.MonthEnd(0)
    out["WY"] = start.dt.year + (start.dt.month >= 10).astype(int)
    out["month"] = start.dt.month
    out = out[["date", "WY", "month", "arc", "taf", "kind"]]
    return out.sort_values(["arc", "date"]).reset_index(drop=True)


def main():
    model = load(get_inflow_model())
    ap = argparse.ArgumentParser(description=f"Run the rim-inflow model ({model.LABEL}) on one forcing.")
    ap.add_argument("--forcing", choices=list(model.FORCINGS), required=True)
    ap.add_argument("--allow-dirty", action="store_true",
                    help="run even if the model checkout is off the pin or has modified files")
    args = ap.parse_args()

    repo, env, pin = get_inflow_repo(), get_inflow_env(), get_inflow_commit()
    head = git(repo, "rev-parse", "HEAD")
    modified = git(repo, "status", "--porcelain", "--untracked-files=no")
    environment = model.check_environment(repo, env)
    clean = head == pin and not modified and environment["ok"]
    print(f"{model.LABEL}: {repo}")
    print(f"  HEAD {head}, pin {pin}, modified files: {len(modified.splitlines())}")
    print(f"  environment: {environment}")
    if not clean and not args.allow_dirty:
        raise SystemExit(f"{model.LABEL} is not at the pinned commit, has modified tracked files, "
                         f"or env {env} runs it from another checkout; check out the pin "
                         "(config: inflow_commit) or pass --allow-dirty")

    input_path = model.input_file(repo, args.forcing)
    input_rel = input_path.relative_to(repo).as_posix()
    print("Hashing the model input ...")
    input_sha = sha256_file(input_path)
    g2_cells = check_g2(args.forcing, input_sha)
    print(f"G2 PASS on {g2_cells} cells")

    out_dir = _gen / "output" / "_2_run_product" / INFLOW_FORCINGS[args.forcing]
    remove_tree(out_dir)
    out_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="inflow_run_") as tmp:
        run_dir = Path(tmp)
        cmd = model.command(repo, env, args.forcing, run_dir)
        shown = [Path(cmd[0]).stem] + [c if c != str(run_dir) else "<temporary folder>"
                                       for c in cmd[1:]]
        print("Running:", " ".join(shown))
        started = datetime.now(timezone.utc)
        subprocess.run(cmd, cwd=repo, check=True)

        info = model.describe(repo, run_dir)
        print("Hashing the model files ...")
        hashes = {rel: sha256_file(repo / rel) for rel in info["files"].values()}
        hashes[input_rel] = input_sha
        g1 = model.reproduce(repo, args.forcing, run_dir)
        arcs = tidy(model.arc_flows(run_dir)) if g1 is None or g1["pass"] else None

    manifest = {
        "tool": "mod_forcing/inflows/_2_run_product.py",
        "inflow_model": get_inflow_model(),
        "model": info["model"],
        "started_utc": started.isoformat(timespec="seconds"),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_repo": str(repo),
        "model_commit": head,
        "model_pin": pin,
        "model_clean": clean,
        "environment": environment,
        "forcing": args.forcing,
        "water_years": None if arcs is None else [int(arcs["WY"].min()), int(arcs["WY"].max())],
        "files": {**info["files"], "input": input_rel},
        "sha256": hashes,
        "command": shown,
        "run": info["run"],
        "g2": {"cells": g2_cells, "pass": True},
        "g1": g1,
    }
    (out_dir / INFLOW_PROVENANCE).write_text(json.dumps(manifest, indent=1))
    if g1 is None:
        print(f"G1 skipped: {model.LABEL} tracks no series to compare with")
    else:
        print(json.dumps(g1, indent=1))
        if not g1["pass"]:
            raise SystemExit(f"G1 FAIL: the series differs from the one {model.LABEL} tracks")
        print("G1 PASS")

    path = get_arc_inflows(args.forcing)
    arcs.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.8g")
    print(f"{arcs['arc'].nunique()} series, WY{arcs['WY'].min()}-{arcs['WY'].max()}, "
          f"{len(arcs):,} rows")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
