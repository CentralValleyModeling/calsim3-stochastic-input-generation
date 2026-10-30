"""
Build and Check the Rim-Inflow Model's Forcing Against BASE
===========================================================
A rim-inflow model may read the WGEN weather in a form of its own rather than the text files
in BASE: SAC-SMA reads a NetCDF store of the 4,410 grid cells it uses, VIC a text file per cell
with the wind added. This script checks that the model's input for a forcing holds the BASE
weather it stands for (gate G2), on a sample of cells or on all of them. Where the model's
folder does not hold that input (the adapter's ``BUILT``: for SAC-SMA, Product B; for VIC,
every forcing), the script first writes it from BASE. The model's adapter
(adapters/<inflow_model>.py) writes and compares the files; this script supplies the BASE side
and keeps the record.

Forcings
--------
- historical : BASE/WGEN/Historical_Unsplit/data_<lat>_<lon>
- A          : BASE/WGEN/Product_A/1/meteo_<lat>_<lon>
- B          : BASE/WGEN/Product_B/1/meteo_<lat>_<lon> (stamp years 1-1008; utils.wgen_calendar)

Inputs
------
- the model's input for the forcing (adapter ``inputs``), in the checkout ``inflow_repo`` or,
  when built here, in the output folder below
- the BASE WGEN text files above (year month day prcp tmax tmin)

Outputs
-------
- <generated>/mod_forcing/inflows/output/_1_build_forcing/<Historical_Unsplit|Product_A/1|Product_B/1>/
  - the inputs built here (SAC-SMA, Product B: wgen_product_b_seg01.nc ... _seg10.nc,
    0.6-0.75 GB each, 6.8 GB in all; VIC: meteo_<lat>_<lon> for 4,097 cells, 4 GB for
    historical or A and 32 GB for B)
  - forcing_identity.csv  (``--cells all`` only; per input file and variable: cells checked,
                           the adapter's measures of the difference, pass; the input's name and
                           its sha256, which _2_run_product.py records in its manifest too)

_2_run_product.py runs the model only if this file shows a pass on every input. A sample of
cells is a quick check: it prints its table and leaves the file as it was.

Usage
-----
    python mod_forcing/inflows/_1_build_forcing.py --forcing A --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing historical --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing B --cells all       # builds, then checks
    python mod_forcing/inflows/_1_build_forcing.py --forcing B --cells all --check-only
    python mod_forcing/inflows/_1_build_forcing.py --forcing A          # quick: 200 cells, not recorded
"""

import argparse
import functools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_forcing.inflows.adapters import label, load
from utils.paths import (INFLOW_FORCINGS, get_base_dir, get_inflow_model, get_inflow_repo,
                         get_module_generated_dir, sha256_file)

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
                    help="number of cells to sample (seeded), or 'all' (default 200)")
    ap.add_argument("--check-only", action="store_true",
                    help="check inputs built earlier instead of writing them again")
    args = ap.parse_args()
    n_cells = None if args.cells == "all" else int(args.cells)
    if n_cells is not None and n_cells < 1:
        raise SystemExit("--cells must be at least 1, or 'all'")

    repo = get_inflow_repo()
    base_sub, prefix = BASE_WEATHER[args.forcing]
    base_dir = get_base_dir() / base_sub
    read_base = functools.partial(read_cell, base_dir, prefix)
    out_dir = _gen / "output" / "_1_build_forcing" / INFLOW_FORCINGS[args.forcing]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"BASE:  {base_dir}")
    if args.forcing in model.BUILT and not args.check_only:
        print(f"Writing the {model.LABEL} input from BASE into {out_dir}")
        model.build_inputs(repo, args.forcing, read_base, out_dir,
                           (Path("BASE") / base_sub).as_posix())
    files = model.inputs(repo, args.forcing, out_dir)
    missing = [f for f in files if not f.exists()]
    if missing:
        raise SystemExit(f"missing inputs {[f.name for f in missing]}; run without --check-only")
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
    if n_cells is None:
        out.to_csv(out_dir / "forcing_identity.csv", index=False)
        print(f"Wrote {out_dir / 'forcing_identity.csv'}")
    if not out["pass"].all():
        raise SystemExit("G2 FAIL: the input differs from BASE")
    print("G2 PASS" if n_cells is None else f"G2 PASS on {n_cells} sampled cells (not recorded)")


if __name__ == "__main__":
    main()
