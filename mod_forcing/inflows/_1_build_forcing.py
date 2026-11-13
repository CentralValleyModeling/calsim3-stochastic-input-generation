"""
Build and Check the Rim-Inflow Model's Forcing Against BASE
===========================================================
Gate G2: compares the rim-inflow model's input for one forcing with the BASE WGEN weather, on a
seeded sample of cells or on all of them. ``--cells all`` first writes from BASE the inputs the
adapter builds (``BUILT``: SAC-SMA, Product B; VIC, every forcing).

Forcings
--------
- historical : <base>/WGEN/Historical_Unsplit/data_<lat>_<lon>
- A          : <base>/WGEN/Product_A/1/meteo_<lat>_<lon>
- B          : <base>/WGEN/Product_B/1/meteo_<lat>_<lon> (stamp years 1-1008; utils.wgen_calendar)

Inputs
------
- model's input for the forcing (adapter ``inputs``): in the checkout ``inflow_repo``, or for a
  forcing in ``BUILT`` in the output folder below (SAC-SMA: NetCDF stores of its 4,410 cells;
  VIC: one text file per cell with the LTO wind)
- BASE WGEN text files above, read raw (year month day prcp tmax tmin)
- adapter's own references (adapters/<inflow_model>.py), e.g. the x10 spike table for
  historical and, for VIC, the LTO wind under <base>/Historical_Climate_LTO/1_Historical/

Outputs
-------
- <generated>/mod_forcing/inflows/output/_1_build_forcing/<Historical_Unsplit|Product_A/1|Product_B/1>/
  - inputs built here (``--cells all``, forcings in ``BUILT``): SAC-SMA Product B
    wgen_product_b_seg01.nc ... _seg10.nc (0.6-0.75 GB each, 6.8 GB in all); VIC
    meteo_<lat>_<lon> for 4,097 cells (4 GB for historical or A, 32 GB for B) and
    forcing_source.json
  - forcing_identity.csv (``--cells all`` only): per input file and variable, cells checked,
    the adapter's difference measures, pass, the input's name and its sha256.
    _2_run_product.py runs the model only on a pass of every input at these hashes.

A sample prints its table and writes nothing; a failed sample deletes forcing_identity.csv.
Stops when this GENERATED folder holds another model's run (``utils.paths.require_chain_model``).

Dependencies
------------
mod_forcing.inflows.adapters, utils.paths; pandas

Usage
-----
    python mod_forcing/inflows/_1_build_forcing.py --forcing historical --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing A --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing B --cells all   # builds, then checks
    python mod_forcing/inflows/_1_build_forcing.py --forcing A               # 200 cells, no record
"""

import argparse
import functools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_forcing.inflows.adapters import label, load
from utils.paths import (WEATHER_SETS, get_base_dir, get_inflow_model, get_inflow_repo,
                         get_module_generated_dir, require_chain_model, sha256_file)

_gen = get_module_generated_dir("mod_forcing/inflows")

# forcing -> (BASE folder of the WGEN text files, file prefix)
BASE_WEATHER = {
    "historical": (Path("WGEN") / "Historical_Unsplit", "data_"),
    "A": (Path("WGEN") / "Product_A" / "1", "meteo_"),
    "B": (Path("WGEN") / "Product_B" / "1", "meteo_"),
}


def read_cell(base_dir: Path, prefix: str, cell: str) -> pd.DataFrame:
    """One WGEN text file: year month day prcp tmax tmin."""
    return pd.read_csv(base_dir / f"{prefix}{cell}", sep=r"\s+", header=None,
                       names=["y", "m", "d", "prcp", "tmax", "tmin"])


def main():
    model = load(get_inflow_model())
    ap = argparse.ArgumentParser(
        description=f"Build (for the forcings the adapter builds) and check the input of the "
                    f"rim-inflow model ({model.LABEL}) against BASE (G2).")
    ap.add_argument("--forcing", choices=list(model.FORCINGS), required=True)
    ap.add_argument("--cells", default="200",
                    help="number of cells to sample (seeded), or 'all', which also builds the "
                         "inputs the adapter builds (default 200)")
    args = ap.parse_args()
    n_cells = None if args.cells == "all" else int(args.cells)
    if n_cells is not None and n_cells < 1:
        raise SystemExit("--cells must be at least 1, or 'all'")
    require_chain_model(args.forcing)

    repo = get_inflow_repo()
    base_sub, prefix = BASE_WEATHER[args.forcing]
    base_dir = get_base_dir() / base_sub
    read_base = functools.partial(read_cell, base_dir, prefix)
    out_dir = _gen / "output" / "_1_build_forcing" / WEATHER_SETS[args.forcing]["wgen"]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"BASE:  {base_dir}")
    if args.forcing in model.BUILT and n_cells is None:
        print(f"Writing the {model.LABEL} input from BASE into {out_dir}")
        model.build_inputs(repo, args.forcing, read_base, out_dir,
                           (Path("BASE") / base_sub).as_posix())
    files = model.inputs(repo, args.forcing, out_dir)
    missing = [f for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"missing inputs {[f.name for f in missing]}; run with --cells all to "
                         "build them")
    print("Input: " + "\n       ".join(str(f) for f in files))
    out = model.check_inputs(repo, args.forcing, files, read_base, n_cells)
    if n_cells is None:
        print("Hashing the inputs ...")
        out["input_sha256"] = out["input"].map({f: sha256_file(f) for f in files})
    out["input"] = out["input"].map(lambda f: label(f, repo))

    if len(out) <= 40:
        print(out.to_string(index=False))
    else:
        print(out.groupby("variable").agg(files=("input", "nunique"), days=("days", "sum"),
                                          max_abs_diff=("max_abs_diff", "max"),
                                          outside_tol=("outside_tol", "sum"),
                                          x10_pairs=("x10_pairs", "sum"),
                                          passed=("pass", "all")).to_string())
    record = out_dir / "forcing_identity.csv"
    if n_cells is None:
        out.to_csv(record, index=False)
        print(f"Wrote {record}")
    if not out["pass"].all():
        if n_cells is not None and record.exists():
            record.unlink()
            print(f"Removed {record}: the pass it recorded no longer holds")
        raise SystemExit("G2 FAIL: the input differs from BASE")
    print("G2 PASS" if n_cells is None else f"G2 PASS on {n_cells} sampled cells (not recorded)")


if __name__ == "__main__":
    main()
