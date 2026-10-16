"""
Rim-Inflow Model Adapters
=========================
mod_forcing/inflows runs one rim-inflow model: any model kept in a git repository that turns
the WGEN weather into monthly flows on the CalSim3 rim-inflow arcs. The config names the model
(``inflow_model``), its checkout (``inflow_repo``), the commit the product is pinned to
(``inflow_commit``) and the environment it runs in (``inflow_env``).

The two drivers do what every model shares: the pin check on the checkout, gate G2 and its
record, the run in a temporary folder, the water-year dating of the flows and the run manifest.
What is particular to a model sits in its adapter, the module of this package named after
``inflow_model``, which defines:

LABEL
    The model's name in messages.
FORCINGS
    Forcing key (``historical``, ``A``) -> the model's name for its input of that forcing.
input_file(repo, forcing) -> Path
    The weather file the model reads for a forcing. G2 checks it, and its sha256 ties the
    check to the run.
check_input(repo, forcing, read_base, n_cells) -> DataFrame
    Gate G2: compare that file with BASE on ``n_cells`` cells, or on all of them if None.
    ``read_base(cell)`` returns one WGEN cell (y, m, d, prcp, tmax, tmin). One row per
    variable, with at least ``cells`` (cells checked), ``input_cells`` (cells in the file)
    and ``pass``.
check_environment(repo, env) -> dict
    What ``env`` runs, for the manifest; ``ok`` is False unless it runs the model in ``repo``.
command(repo, env, forcing, out_dir) -> list[str]
    The command that runs the model on a forcing and writes into ``out_dir``. The driver runs
    it with ``repo`` as working directory.
describe(repo, out_dir) -> dict
    After a run: ``model`` (a label that names the trained version), ``files`` (role -> path
    in ``repo`` of each file the run used; the manifest records their sha256) and ``run``
    (anything else to record).
reproduce(repo, forcing, out_dir) -> dict | None
    Gate G1: compare the run with the series the model tracks at the pin; the dict has a
    ``pass`` key. None if the model tracks no series.
arc_flows(out_dir) -> DataFrame
    The run's flows: ``arc`` (CalSim3 name), ``month`` (YYYY-MM), ``taf`` (TAF in the month)
    and ``kind``, over complete water years.

The rim-inflow builder takes the arcs named in mod_hydrology/rim_inflow/reference/
CalSim3_inflow_mapping.csv, so a model must deliver those arcs.
"""

import importlib
from types import ModuleType


def load(name: str) -> ModuleType:
    """The adapter of the rim-inflow model ``name`` (config ``inflow_model``)."""
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as e:
        if e.name != f"{__name__}.{name}":
            raise
        raise SystemExit(f"inflow_model {name!r}: no adapter {name}.py in mod_forcing/inflows/adapters")
