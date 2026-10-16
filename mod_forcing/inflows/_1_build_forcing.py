"""
Check the Rim-Inflow Model's Forcing Against BASE
=================================================
A rim-inflow model may read the WGEN weather in a form of its own rather than the text files
in BASE: SAC-SMA, for one, reads a NetCDF store of the 4,410 grid cells it uses. This script
checks that the model's input for a forcing holds the BASE weather it stands for (gate G2), on
a sample of cells or on all of them. The model's adapter (adapters/<inflow_model>.py,
``check_input``) does the comparison; this script supplies the BASE side and keeps the record.

Forcings
--------
- historical : BASE/WGEN/Historical_Unsplit/data_<lat>_<lon>
- A          : BASE/WGEN/Product_A/1/meteo_<lat>_<lon>

Product B is converted from ``BASE/WGEN/Product_B/1`` in phase P3.

Inputs
------
- the model's input for the forcing (adapter ``input_file``), in the checkout ``inflow_repo``
- the BASE WGEN text files above (year month day prcp tmax tmin)

Outputs
-------
- <generated>/mod_forcing/inflows/output/_1_build_forcing/<Historical_Unsplit|Product_A/1>/
  - forcing_identity.csv  (per variable: cells checked, the adapter's measures of the
                           difference, pass; the cells in the input, its path in the
                           checkout and its sha256, which _2_run_product.py records in its
                           manifest too)

_2_run_product.py runs the model only if this file shows a pass on every cell of the input, so
run it with ``--cells all`` first.

Usage
-----
    python mod_forcing/inflows/_1_build_forcing.py --forcing A --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing historical --cells all
    python mod_forcing/inflows/_1_build_forcing.py --forcing A          # quick: 200 cells
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_forcing.inflows.adapters import load
from utils.paths import (INFLOW_FORCINGS, get_base_dir, get_inflow_model, get_inflow_repo,
                         get_module_generated_dir, sha256_file)

_gen = get_module_generated_dir("mod_forcing/inflows")

# forcing -> (BASE folder of the WGEN text files, file prefix)
BASE_WEATHER = {
    "historical": (Path("WGEN") / "Historical_Unsplit", "data_"),
    "A": (Path("WGEN") / "Product_A" / "1", "meteo_"),
}


def read_text(path: Path) -> pd.DataFrame:
    """One WGEN text file: year month day prcp tmax tmin."""
    return pd.read_csv(path, sep=r"\s+", header=None,
                       names=["y", "m", "d", "prcp", "tmax", "tmin"])


def main():
    model = load(get_inflow_model())
    ap = argparse.ArgumentParser(
        description=f"Check the input of the rim-inflow model ({model.LABEL}) against BASE (G2).")
    ap.add_argument("--forcing", choices=list(model.FORCINGS), required=True)
    ap.add_argument("--cells", default="200",
                    help="number of cells to sample (seeded), or 'all' (default 200)")
    args = ap.parse_args()
    n_cells = None if args.cells == "all" else int(args.cells)
    if n_cells is not None and n_cells < 1:
        raise SystemExit("--cells must be at least 1, or 'all'")

    repo = get_inflow_repo()
    path = model.input_file(repo, args.forcing)
    base_sub, prefix = BASE_WEATHER[args.forcing]
    base_dir = get_base_dir() / base_sub
    print(f"Input: {path}")
    print(f"BASE:  {base_dir}")
    out = model.check_input(repo, args.forcing,
                            lambda cell: read_text(base_dir / f"{prefix}{cell}"), n_cells)
    out["input"] = path.relative_to(repo).as_posix()
    out["input_sha256"] = sha256_file(path)

    out_dir = _gen / "output" / "_1_build_forcing" / INFLOW_FORCINGS[args.forcing]
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_dir / "forcing_identity.csv", index=False)
    print(out.to_string(index=False))
    print(f"Wrote {out_dir / 'forcing_identity.csv'}")
    if not out["pass"].all():
        raise SystemExit("G2 FAIL: the input differs from BASE")
    print("G2 PASS")


if __name__ == "__main__":
    main()
