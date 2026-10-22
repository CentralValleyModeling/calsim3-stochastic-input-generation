"""
Rim-Inflow Model Adapters
=========================
mod_forcing/inflows runs one rim-inflow model: any model kept in a git repository that turns
the WGEN weather into monthly flows on the CalSim3 rim-inflow arcs. The config names the model
(``inflow_model``), its checkout (``inflow_repo``), the commit the product is pinned to
(``inflow_commit``) and the environment it runs in (``inflow_env``).

The two drivers do what every model shares: the pin check on the checkout, gate G2 and its
record, the run in a temporary folder, the dating of the flows (water years, and the Product B
chunks of utils.wgen_calendar) and the run manifest. What is particular to a model sits in its
adapter, the module of this package named after ``inflow_model``, which defines:

LABEL
    The model's name in messages.
FORCINGS
    Forcing key (``historical``, ``A``, ``B``) -> the model's name for its input of that forcing.
BUILT
    The forcings whose input _1_build_forcing.py writes from BASE (into ``build_dir``, its
    output folder for the forcing); the model's checkout holds the others.
inputs(repo, forcing, build_dir) -> list[Path]
    The weather files the model reads for a forcing. G2 checks them, and their sha256 ties the
    check to the run.
build_inputs(repo, forcing, read_base, build_dir, source) -> list[Path]
    For a forcing in BUILT: write its input files from BASE (``source``, the folder of the
    WGEN text files, for the files' record).
check_inputs(repo, forcing, files, read_base, n_cells) -> DataFrame
    Gate G2: compare the input files with BASE on ``n_cells`` cells, or on all of them if None.
    ``read_base(cell)`` returns one WGEN cell (y, m, d, prcp, tmax, tmin) and must pickle: the
    adapter may call it in worker processes. One row per input file and variable, with at least
    ``input`` (the file), ``cells`` (cells checked), ``input_cells`` (cells in the file) and
    ``pass``.
check_environment(repo, env) -> dict
    What ``env`` runs, for the manifest; ``ok`` is False unless it runs the model in ``repo``.
run(repo, env, forcing, files, out_dir) -> list[list[str]]
    Run the model on a forcing, with ``repo`` as working directory, writing into ``out_dir``;
    return the commands it ran.
describe(repo, forcing, out_dir) -> dict
    After a run: ``model`` (a label that names the trained version), ``files`` (role -> path
    in ``repo`` of each file the run used; the manifest records their sha256) and ``run``
    (anything else to record).
gates(repo, forcing, out_dir) -> dict
    The checks on a finished run, name -> result with a ``pass`` key: G1 (the series repeats
    the one the model tracks at the pin) where the model tracks one, G6 (each segment of a run
    made in segments starts from the state the one before kept).
arc_flows(forcing, out_dir) -> DataFrame
    The run's flows: ``arc`` (CalSim3 name), ``year`` and ``month`` (calendar months; the
    stamp months of utils.wgen_calendar for Product B), ``taf`` (TAF in the month) and
    ``kind``, over complete water years.

The rim-inflow builder takes the arcs named in mod_hydrology/rim_inflow/reference/
CalSim3_inflow_mapping.csv, so a model must deliver those arcs.
"""

import importlib
from pathlib import Path
from types import ModuleType


def label(path: Path, repo: Path) -> str:
    """How the G2 report and the manifest name an input file: its path in the model's
    checkout, or its file name for one written by _1_build_forcing.py."""
    try:
        return Path(path).relative_to(repo).as_posix()
    except ValueError:
        return Path(path).name


def load(name: str) -> ModuleType:
    """The adapter of the rim-inflow model ``name`` (config ``inflow_model``)."""
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        if e.name != f"{__name__}.{name}":
            raise
        raise SystemExit(f"inflow_model {name!r}: no adapter {name}.py in mod_forcing/inflows/adapters")
