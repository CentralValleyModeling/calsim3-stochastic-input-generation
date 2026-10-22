"""
Centralized path resolver for data directories.

Reads the data root from ``config.json`` (user-local, git-ignored) at the repo
root, falling back to ``config_default.json`` (tracked) when the user file is
absent.  All module scripts should import helpers from this module instead of
hard-coding ``../../data/`` relative paths.

Quick start
-----------
::

    from utils.paths import get_base_dir, get_generated_dir, get_module_generated_dir

    wgen_dir = get_base_dir() / "WGEN" / "Product_A" / "1"
    output   = get_module_generated_dir("mod_hydrology/calsimhydro") / "output"
"""

import csv
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

from utils.env_check import require_env

# Fail fast if the running interpreter is missing pipeline dependencies (e.g.
# user ran the script in the wrong shell). Every numbered pipeline script
# imports from utils.paths, so the check fires once per script invocation.
# See utils/env_check.py for the rationale.
require_env()

# ---------------------------------------------------------------------------
# Locate the repo root (parent of the utils/ folder this file lives in)
# ---------------------------------------------------------------------------
_UTILS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _UTILS_DIR.parent


def _long_path(p: Path) -> Path:
    """On Windows, prepend ``\\\\?\\`` to bypass the 260-char MAX_PATH limit."""
    s = str(p)
    if sys.platform == "win32" and not s.startswith("\\\\?\\"):
        return Path("\\\\?\\" + s)
    return p

# ---------------------------------------------------------------------------
# Load user config, falling back to the default
# ---------------------------------------------------------------------------
_USER_CFG = REPO_ROOT / "config.json"
_DEFAULT_CFG = REPO_ROOT / "config_default.json"


def _load_config() -> dict:
    """Defaults from ``config_default.json``, overridden key by key by ``config.json``."""
    with open(_DEFAULT_CFG, "r") as f:
        cfg = json.load(f)
    if _USER_CFG.exists():
        with open(_USER_CFG, "r") as f:
            cfg.update(json.load(f))
    return cfg


_CFG = _load_config()

# Resolve data_dir relative to the repo root (or use absolute if given)
_raw = Path(_CFG["data_dir"])
DATA_DIR: Path = _long_path(_raw if _raw.is_absolute() else (REPO_ROOT / _raw).resolve())


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_data_dir() -> Path:
    """Return the resolved root data directory."""
    return DATA_DIR


def get_base_dir() -> Path:
    """Return ``<data_dir>/BASE``: original reference and modeling files."""
    return DATA_DIR / "BASE"


def get_generated_dir() -> Path:
    """Return ``<data_dir>/GENERATED``: all module input/output."""
    return DATA_DIR / "GENERATED"


def get_module_generated_dir(module: str) -> Path:
    """Return ``<data_dir>/GENERATED/<module>/``.

    Parameters
    ----------
    module : str
        Slash-separated module path, e.g. ``"mod_hydrology/calsimhydro"``
        or ``"mod_climate"``.
    """
    return get_generated_dir() / module


def get_archive_dir() -> Path:
    """Return ``<data_dir>/<archive_dir>``: the read-only v1.0 GENERATED tree.

    Holds the VIC-based release (git tag ``v1.0``).  Read it, never write to it:
    the VIC fluxes for ET (until the new ET method) and comparisons against v1.0.
    """
    return DATA_DIR / _CFG["archive_dir"]


def get_inflow_model() -> str:
    """Return the rim-inflow model (``inflow_model``), the name of its adapter in
    ``mod_forcing/inflows/adapters``."""
    return _CFG["inflow_model"]


def get_inflow_repo() -> Path:
    """Return the rim-inflow model's git repository (``inflow_repo``, relative to the repo root
    or absolute)."""
    p = Path(_CFG["inflow_repo"])
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def get_inflow_env() -> str:
    """Return the environment the rim-inflow model runs in (``inflow_env``)."""
    return _CFG["inflow_env"]


def get_inflow_commit() -> str:
    """Return the commit of ``inflow_repo`` the rim-inflow product is pinned to (``inflow_commit``)."""
    return _CFG["inflow_commit"]


#: Forcings of the rim-inflow model (``mod_forcing/inflows``) -> their output subfolder.
INFLOW_FORCINGS = {
    "historical": Path("Historical_Unsplit"),
    "A": Path("Product_A") / "1",
    "B": Path("Product_B") / "1",
}

def get_arc_inflows(forcing: str) -> Path:
    """Return the rim-inflow model's monthly arc flows for ``forcing`` (a key of
    ``INFLOW_FORCINGS``): the ``arc_inflow_monthly.csv`` written by
    ``mod_forcing/inflows/_2_run_product.py``."""
    return (get_module_generated_dir("mod_forcing/inflows") / "output" / "_2_run_product"
            / INFLOW_FORCINGS[forcing] / "arc_inflow_monthly.csv")


#: Beside ``arc_inflow_monthly.csv``, and copied into each rim-inflow SV folder: the manifest
#: of the rim-inflow model run the files come from (model, commit, forcing, hashes, gates).
INFLOW_PROVENANCE = "run_manifest.json"


def require_pinned_run(folder: Path) -> dict:
    """Return the run manifest of the rim-inflow model outputs in ``folder``, and stop unless
    they come from the configured model (``inflow_model``) at the pinned commit
    (``inflow_commit``) with no modified tracked files, in a run that passed every gate, on the
    inputs G2 last checked (``forcing_identity.csv`` of ``_1_build_forcing.py``). Outputs left
    over from another model, an earlier pin or an earlier input, or from a step that was not
    re-run after the config or the input changed, fail here."""
    path = folder / INFLOW_PROVENANCE
    if not path.exists():
        raise FileNotFoundError(f"{folder}: no {INFLOW_PROVENANCE}, so the run behind these "
                                "outputs is unknown; re-run mod_forcing/inflows and the "
                                "rim-inflow builder")
    manifest = json.loads(path.read_text())
    if not manifest.get("gates"):
        raise RuntimeError(f"{path}: records no gates; re-run mod_forcing/inflows and the "
                           "rim-inflow builder")
    failed = [name for name, g in manifest["gates"].items() if not g.get("pass")]
    if failed:
        raise RuntimeError(f"{path}: the run failed {', '.join(failed)}")
    run = (manifest.get("inflow_model"), manifest.get("model_commit"))
    pin = (get_inflow_model(), get_inflow_commit())
    if run != pin:
        raise RuntimeError(f"{folder}: built from {run[0]} at {run[1]}, but the config names "
                           f"{pin[0]} at {pin[1]} (inflow_model, inflow_commit); re-run "
                           "mod_forcing/inflows and the rim-inflow builder")
    if manifest.get("model_clean") is not True:
        raise RuntimeError(f"{path}: the run was made with --allow-dirty (modified tracked files, "
                           "or an environment that runs another checkout), so it is not the "
                           "pinned commit's")
    identity = (get_module_generated_dir("mod_forcing/inflows") / "output" / "_1_build_forcing"
                / INFLOW_FORCINGS[manifest["forcing"]] / "forcing_identity.csv")
    with open(identity, newline="") as fh:
        checked = {r["input"]: r["input_sha256"] for r in csv.DictReader(fh)}
    used = {k: manifest["sha256"].get(k) for k in manifest["files"]["inputs"]}
    if used != checked:
        raise RuntimeError(f"{path}: the run read other inputs than G2 last checked ({identity}); "
                           "re-run mod_forcing/inflows/_2_run_product.py and the rim-inflow builder")
    return manifest


def get_rim_inflow_outputs(product: str) -> dict:
    """Return the rim-inflow SV files of ``product`` (``historical``, ``A`` or ``B``) written by
    ``mod_hydrology/rim_inflow/_1_build_rim_inflow.py``. Every reader of rim inflows goes
    through this helper.

    - ``dir``: the product's folder. Product B holds ``<CalSim>_qmo_n01.csv`` ...
      ``_n10.csv`` there (CalSim, Matched_inflow, Year, Month, qmap_postAdj).
    - ``ts`` (historical, A): ``calsim_qmap_validation_TS.csv``, one long table of every SV
      (CalSim, Matched_inflow, Year, Month, qmap_postAdj). Product A covers WY1972-2018,
      historical WY1916-2018.
    - ``sv``, ``sv_dir`` (A): the Product A values in SV format (Part B, Part C, Year, Month,
      Value), ``_riminflow_productA_1972_2018.csv``, and its folder, which the Product A
      compiler scans.
    """
    root = (get_module_generated_dir("mod_hydrology/rim_inflow") / "output"
            / "_1_build_rim_inflow" / INFLOW_FORCINGS[product])
    out = {"dir": root}
    if product != "B":
        out["ts"] = root / "calsim_qmap_validation_TS.csv"
    if product == "A":
        out["sv_dir"] = root / "_product_a_validation"
        out["sv"] = out["sv_dir"] / "_riminflow_productA_1972_2018.csv"
    return out


def _clear_readonly(func, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def sha256_file(path: Path) -> str:
    """The sha256 of a file, read in 16 MB blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def remove_tree(path: Path) -> None:
    """Delete an output folder before it is regenerated. OneDrive marks the folders it has
    synced read-only, which makes Windows refuse to remove them, so the flag is cleared on
    the way."""
    if path.exists():
        shutil.rmtree(path, onerror=_clear_readonly)


def get_inventory_dir() -> Path:
    """Return the repo-level inventory directory."""
    return REPO_ROOT / "inventory"
