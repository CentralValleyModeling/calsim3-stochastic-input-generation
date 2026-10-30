"""
Run the Rim-Inflow Model
========================
Runs the rim-inflow model on one forcing, checks it, and writes its monthly arc flows as the
one table the rim-inflow SVs are built from.

The model is the one the config names (``inflow_model``): SAC-SMA's dPL-CalSim with its share
model (adapters/sacsma.py), which v1.1 delivers, or VIC 4.2.d (adapters/vic.py). It lives in
its own folder (``inflow_repo``), pinned to one version (``inflow_pin``: for SAC-SMA a commit
of its git repository), and runs there as an external command in its own environment
(``inflow_env``). Its adapter runs it, checks the environment and the result, and reads the
flows. The run writes into a temporary folder, deleted after it. A GENERATED folder holds the
chain of one model (config ``generated_dir``), so the script will not replace another model's
run.

Forcings
--------
- historical : WGEN NonDetrend-Unsplit (SAC-SMA's training forcing): the reference for skill
               and for the absorb fits of the second stage
- A          : WGEN Product A scenario 1
- B          : WGEN Product B scenario 1, 1,008 stamp years, delivered as 10 chunks of 100 water
               years (utils.wgen_calendar); SAC-SMA runs it in segments (adapters/sacsma.py)

Checks
------
- The model's version (adapter ``version``) must be the pin, with no modified files, and the
  environment must run the model from that folder; ``--allow-dirty`` runs anyway and the
  manifest records the state.
- Gate G2, before the run: forcing_identity.csv of _1_build_forcing.py must show a pass on
  every cell of every input file, for each file's current sha256.
- The adapter's gates, after the run: G1 (the series repeats the one the model tracks at the
  pin) where the model tracks one; G6 (each segment of a run in segments starts from the state
  the one before kept) for a run in segments. If G1 fails, the script writes only the manifest;
  if G6 fails, the adapter stops before the join and the script writes nothing.

Inputs
------
- the model checkout and the files the run used
- <generated>/mod_forcing/inflows/output/_1_build_forcing/<forcing>/: forcing_identity.csv,
  and the inputs written there (Product B)

Outputs
-------
- <generated>/mod_forcing/inflows/output/_2_run_product/<Historical_Unsplit|Product_A/1|Product_B/1>/
  (deleted first)
  - arc_inflow_monthly.csv  (date, WY, month, arc, taf, kind; Product B adds chunk first),
                            utils.paths.get_arc_inflows: the model's arcs over the complete
                            water years of the run (for SAC-SMA the 196 arcs and the
                            Sacramento valley node I_SRBB_VAL); date is the month end, flows
                            in TAF per month. Product B's months carry the labels of their
                            chunk, WY1922-2021.
  - run_manifest.json       model, version, environment, sha256 of every file the run used,
                            forcing, water years, commands and every gate's result. The
                            rim-inflow builder reads only flows whose manifest names the
                            configured model and pin (utils.paths.require_pinned_run).

Usage
-----
    python mod_forcing/inflows/_2_run_product.py --forcing historical
    python mod_forcing/inflows/_2_run_product.py --forcing A
    python mod_forcing/inflows/_2_run_product.py --forcing B
"""

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_forcing.inflows.adapters import label, load
from utils.paths import (INFLOW_FORCINGS, INFLOW_PROVENANCE, get_arc_inflows, get_inflow_env,
                         get_inflow_model, get_inflow_pin, get_inflow_repo,
                         get_module_generated_dir, remove_tree, sha256_file)
from utils.wgen_calendar import chunk_months

_gen = get_module_generated_dir("mod_forcing/inflows")


def check_g2(forcing: str, input_sha: dict[str, str]) -> dict:
    """Gate G2: stop unless _1_build_forcing.py passed on every cell of each of these inputs
    (name -> sha256); return the record of it."""
    path = _gen / "output" / "_1_build_forcing" / INFLOW_FORCINGS[forcing] / "forcing_identity.csv"
    rerun = f"run _1_build_forcing.py --forcing {forcing} --cells all"
    if not path.exists():
        raise SystemExit(f"G2 has not been run on this input: {path} is missing; {rerun}")
    g2 = pd.read_csv(path)
    if not g2["pass"].all():
        raise SystemExit(f"{path}: G2 failed: the input differs from BASE")
    checked = dict(zip(g2["input"], g2["input_sha256"]))
    if checked != input_sha:
        raise SystemExit(f"{path}: G2 checked other inputs, or other versions of them; {rerun}")
    return {"inputs": len(input_sha), "pass": True}


def tidy(forcing: str, flows: pd.DataFrame) -> pd.DataFrame:
    """The adapter's flows, one row per arc and month, dated by month end and water year; for
    Product B, by the chunk and its label month."""
    if flows["taf"].isna().any():
        raise SystemExit(f"missing flows in {flows.loc[flows['taf'].isna(), 'arc'].unique()}")
    out = flows[["arc", "taf", "kind"]].copy()
    cols = ["date", "WY", "month", "arc", "taf", "kind"]
    keys = ["arc", "date"]
    if forcing == "B":
        lab = chunk_months(flows["year"], flows["month"])
        inside = (lab["chunk"] > 0).to_numpy()
        out, lab = out[inside].copy(), lab[inside]
        out["chunk"] = lab["chunk"].to_numpy()
        year, month = lab["Year"].to_numpy(), lab["Month"].to_numpy()
        cols, keys = ["chunk", *cols], ["chunk", *keys]
    else:
        year, month = flows["year"].to_numpy(), flows["month"].to_numpy()
    start = pd.to_datetime(pd.DataFrame({"year": year, "month": month, "day": 1}))
    out["date"] = (start + pd.offsets.MonthEnd(0)).to_numpy()
    out["WY"] = year + (month >= 10)
    out["month"] = month
    return out[cols].sort_values(keys).reset_index(drop=True)


def main():
    model = load(get_inflow_model())
    ap = argparse.ArgumentParser(description=f"Run the rim-inflow model ({model.LABEL}) on one forcing.")
    ap.add_argument("--forcing", choices=list(model.FORCINGS), required=True)
    ap.add_argument("--allow-dirty", action="store_true",
                    help="run even if the model is off the pin or has modified files")
    args = ap.parse_args()

    repo, env, pin = get_inflow_repo(), get_inflow_env(), get_inflow_pin()
    found = model.version(repo)
    environment = model.check_environment(repo, env)
    clean = found["version"] == pin and not found["modified"] and environment["ok"]
    print(f"{model.LABEL}: {repo}")
    print(f"  version {found['version']}, pin {pin}, modified files: {len(found['modified'])}")
    print(f"  environment: {environment}")
    if not clean and not args.allow_dirty:
        raise SystemExit(f"{model.LABEL} is not at the pin, has modified files, or env {env} "
                         "runs it from another folder; restore the pinned version "
                         "(config: inflow_pin) or pass --allow-dirty")

    build_dir = _gen / "output" / "_1_build_forcing" / INFLOW_FORCINGS[args.forcing]
    files = model.inputs(repo, args.forcing, build_dir)
    print("Hashing the model input ...")
    input_sha = {label(f, repo): sha256_file(f) for f in files}
    g2 = check_g2(args.forcing, input_sha)
    print(f"G2 PASS on every cell of {g2['inputs']} input(s)")

    out_dir = _gen / "output" / "_2_run_product" / INFLOW_FORCINGS[args.forcing]
    previous = out_dir / INFLOW_PROVENANCE
    if previous.exists():
        other = json.loads(previous.read_text()).get("inflow_model")
        if other != get_inflow_model():
            raise SystemExit(f"{out_dir} holds a run of {other}; the chain of "
                             f"{get_inflow_model()} goes in its own GENERATED folder "
                             "(config: generated_dir)")
    remove_tree(out_dir)
    out_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="inflow_run_") as tmp:
        run_dir = Path(tmp)
        started = datetime.now(timezone.utc)
        cmds = model.run(repo, env, args.forcing, files, run_dir)
        shown = [[Path(c[0]).stem] + [a.replace(str(run_dir), "<temporary folder>") for a in c[1:]]
                 for c in cmds]

        info = model.describe(repo, args.forcing, run_dir)
        print("Hashing the model files ...")
        hashes = {rel: sha256_file(repo / rel) for rel in info["files"].values()}
        hashes.update(input_sha)
        gates = model.gates(repo, args.forcing, run_dir)
        passed = all(g["pass"] for g in gates.values())
        arcs = tidy(args.forcing, model.arc_flows(args.forcing, run_dir)) if passed else None

    manifest = {
        "tool": "mod_forcing/inflows/_2_run_product.py",
        "inflow_model": get_inflow_model(),
        "model": info["model"],
        "started_utc": started.isoformat(timespec="seconds"),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_repo": str(repo),
        "model_version": found["version"],
        "model_pin": pin,
        "model_clean": clean,
        "environment": environment,
        "forcing": args.forcing,
        "water_years": None if arcs is None else [int(arcs["WY"].min()), int(arcs["WY"].max())],
        "chunks": None if arcs is None or "chunk" not in arcs else int(arcs["chunk"].nunique()),
        "files": {**info["files"], "inputs": list(input_sha)},
        "sha256": hashes,
        "commands": shown,
        "run": info["run"],
        "gates": {"G2": g2, **gates},
    }
    (out_dir / INFLOW_PROVENANCE).write_text(json.dumps(manifest, indent=1))
    for name, g in gates.items():
        print(f"{name}: {'PASS' if g['pass'] else 'FAIL'}")
    if not passed:
        raise SystemExit(f"gate failed: {[n for n, g in gates.items() if not g['pass']]}; "
                         f"see {out_dir / INFLOW_PROVENANCE}")

    path = get_arc_inflows(args.forcing)
    arcs.to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.8g")
    print(f"{arcs['arc'].nunique()} series, WY{arcs['WY'].min()}-{arcs['WY'].max()}"
          + (f" in {manifest['chunks']} chunks" if manifest["chunks"] else "")
          + f", {len(arcs):,} rows")
    print(f"Wrote {out_dir}")


if __name__ == "__main__":
    main()
