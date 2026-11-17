"""
Data Paths and Configuration
============================
Resolves every data location of the pipeline from the configuration, and names the weather sets,
the delivery folders and the rim-inflow model run. Scripts import their paths from here instead
of hard-coding ``../../data/``. Importing the module runs ``utils.env_check.require_env``.

The configuration is ``config_default.json`` (tracked), overridden key by key by the user file:
``config.json`` at the repo root (git-ignored), or the file the environment variable
``CSSTOCHASTIC_CONFIG`` names (absolute or relative to the repo root), e.g. the config of a chain
built on another rim-inflow model. A user key that the defaults lack (keys starting with ``_``
are comments), or a ``CSSTOCHASTIC_CONFIG`` file that does not exist, stops the import. Keys:
``data_dir``, ``generated_dir``, ``archive_dir``, ``inflow_model``, ``inflow_repo``,
``inflow_env``, ``inflow_pin``. On Windows the data paths carry the long-path prefix.

- Folders: ``get_data_dir``, ``get_base_dir`` (``<data_dir>/BASE``), ``get_generated_dir``
  (``<data_dir>/<generated_dir>``), ``get_module_generated_dir``, ``get_archive_dir`` (the
  read-only v1.0 tree), ``get_wgen_dir``, ``get_inventory_dir``.
- Weather sets and delivery: ``WEATHER_SETS`` (keys historical, A, B), ``DELIVERY_WY``,
  ``DELIVERY`` (folder and file tag of the delivery CSVs of historical and A), ``delivery_dir``,
  ``DELIVERY_ROOTS`` and ``delivery_dirs`` (every module's delivery folder, in the compiler's
  order).
- Rim-inflow model: ``get_inflow_model``, ``get_inflow_repo``, ``get_inflow_env``,
  ``get_inflow_pin``, ``get_arc_inflows``, ``get_rim_inflow_outputs``, ``INFLOW_PROVENANCE``.
  ``require_chain_model`` stops when this GENERATED folder holds a run of another model;
  ``require_pinned_run`` stops unless a run comes from the configured model at its pin, with no
  modified files, past every gate, on the inputs G2 last checked.
- ``sha256_file``; ``remove_tree`` (deletes a folder, clearing the read-only flag OneDrive sets).

Inputs
------
- config_default.json, and config.json or the file ``CSSTOCHASTIC_CONFIG`` names
- ``require_chain_model``, ``require_pinned_run``: the ``run_manifest.json`` beside a rim-inflow
  run's outputs; ``require_pinned_run`` also
  ``<generated>/mod_forcing/inflows/output/_1_build_forcing/<wgen folder>/forcing_identity.csv``

Usage
-----
    from utils.paths import get_base_dir, get_module_generated_dir, get_wgen_dir
    wgen_dir = get_wgen_dir("A")          # <base>/WGEN/Product_A/1
    output = get_module_generated_dir("mod_hydrology/calsimhydro") / "output"
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
_USER_CFG = Path(os.environ.get("CSSTOCHASTIC_CONFIG") or "config.json")    # empty = unset
if not _USER_CFG.is_absolute():
    _USER_CFG = REPO_ROOT / _USER_CFG       # scripts run from their own folders
_DEFAULT_CFG = REPO_ROOT / "config_default.json"


def _load_config() -> dict:
    """Defaults from ``config_default.json``, overridden key by key by the user file. The user
    file may set only keys the defaults have (and comments, keys starting with ``_``), so a
    misspelt or retired key stops the run instead of leaving its default in force."""
    with open(_DEFAULT_CFG, "r") as f:
        cfg = json.load(f)
    if os.environ.get("CSSTOCHASTIC_CONFIG") and not _USER_CFG.exists():
        raise SystemExit(f"CSSTOCHASTIC_CONFIG names {_USER_CFG}, which does not exist")
    if _USER_CFG.exists():
        with open(_USER_CFG, "r") as f:
            user = json.load(f)
        unknown = sorted(k for k in user if k not in cfg and not k.startswith("_"))
        if unknown:
            keys = ", ".join(k for k in cfg if not k.startswith("_"))
            raise SystemExit(f"{_USER_CFG}: unknown key(s) {', '.join(unknown)}; "
                             f"{_DEFAULT_CFG.name} has {keys}")
        cfg.update(user)
    return cfg


_CFG = _load_config()

# Resolve data_dir relative to the repo root (or use absolute if given)
_raw = Path(_CFG["data_dir"])
_DATA_ROOT = _raw if _raw.is_absolute() else (REPO_ROOT / _raw).resolve()
DATA_DIR: Path = _long_path(_DATA_ROOT)


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
    """Return ``<data_dir>/<generated_dir>`` (``GENERATED`` by default; an absolute
    ``generated_dir`` stands alone): all module input/output. The SAC-SMA chain uses
    ``GENERATED``; a chain on another rim-inflow model keeps its own folder. The path is
    normalized before the long-path prefix, which Windows reads literally, so a ``..`` in it
    works."""
    return _long_path(Path(os.path.normpath(_DATA_ROOT / _CFG["generated_dir"])))


def get_module_generated_dir(module: str) -> Path:
    """Return ``<generated_dir>/<module>/``.

    Parameters
    ----------
    module : str
        Slash-separated module path, e.g. ``"mod_hydrology/calsimhydro"``
        or ``"mod_climate"``.
    """
    return get_generated_dir() / module


def get_archive_dir() -> Path:
    """Return ``<data_dir>/<archive_dir>``: the read-only v1.0 GENERATED tree.

    Holds the VIC-based release (git tag ``v1.0``), read for comparisons against v1.0
    (rim_inflow/_2_skill_evaluation.py). Never write to it.
    """
    return DATA_DIR / _CFG["archive_dir"]


def get_inflow_model() -> str:
    """Return the rim-inflow model (``inflow_model``), the name of its adapter in
    ``mod_forcing/inflows/adapters``."""
    return _CFG["inflow_model"]


def get_inflow_repo() -> Path:
    """Return the rim-inflow model's folder (``inflow_repo``, relative to the repo root or
    absolute)."""
    p = Path(_CFG["inflow_repo"])
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


def get_inflow_env() -> str:
    """Return the environment the rim-inflow model runs in (``inflow_env``)."""
    return _CFG["inflow_env"]


def get_inflow_pin() -> str:
    """Return the version of the rim-inflow model the product is pinned to (``inflow_pin``), in
    the form its adapter's ``version`` reports: for SAC-SMA a commit of ``inflow_repo``."""
    return _CFG["inflow_pin"]


#: The weather sets, by the key every script's ``--product`` takes. ``name`` is the folder
#: their outputs go to, ``slug`` the lowercase subfolder of a module's intermediates and
#: figures, ``label`` the name on figures, ``wgen`` their folder under ``BASE/WGEN`` (and the
#: subfolder of the rim-inflow model's outputs), ``prefix`` the prefix of its files.
#: Historical_Unsplit is the record without the temperature detrending; Products A and B are
#: WGEN scenario 1 (see ``BASE/WGEN/README.md``). utils.wgen reads them.
WEATHER_SETS = {
    "historical": {"name": "Historical_Unsplit", "slug": "historical_unsplit", "label": "Historical_Unsplit",
                   "wgen": Path("Historical_Unsplit"), "prefix": "data"},
    "A": {"name": "Product_A", "slug": "product_a", "label": "Product A",
          "wgen": Path("Product_A") / "1", "prefix": "meteo"},
    "B": {"name": "Product_B", "slug": "product_b", "label": "Product B",
          "wgen": Path("Product_B") / "1", "prefix": "meteo"},
}

#: The water years a compiled DSS of Historical_Unsplit or Product A takes from the generated
#: SVs; the CalSim 3 baseline starts in October 1921. utils.csv_io.write_delivery_csv clips to it.
DELIVERY_WY = (1922, 2018)

#: Historical_Unsplit and Product A, the sets delivered as one series per SV: the folder in
#: which each module leaves its delivery CSVs for the compiler, and the tag in their names.
DELIVERY = {
    "historical": {"dir": "_historical_unsplit_validation", "tag": "historicalUnsplit"},
    "A": {"dir": "_product_a_validation", "tag": "productA"},
}


def get_wgen_dir(product: str) -> Path:
    """Return the WGEN folder of ``product`` (a key of ``WEATHER_SETS``)."""
    return get_base_dir() / "WGEN" / WEATHER_SETS[product]["wgen"]


def delivery_dir(output_root, product: str) -> Path:
    """Return the folder under ``output_root`` that holds a module's delivery CSVs of
    ``product`` (a key of ``DELIVERY``)."""
    return Path(output_root) / DELIVERY[product]["dir"]


def get_arc_inflows(forcing: str) -> Path:
    """Return the rim-inflow model's monthly arc flows for ``forcing`` (a key of
    ``WEATHER_SETS``): the ``arc_inflow_monthly.csv`` written by
    ``mod_forcing/inflows/_2_run_product.py``."""
    return (get_module_generated_dir("mod_forcing/inflows") / "output" / "_2_run_product"
            / WEATHER_SETS[forcing]["wgen"] / "arc_inflow_monthly.csv")


#: Beside ``arc_inflow_monthly.csv``, and copied into each rim-inflow SV folder: the manifest
#: of the rim-inflow model run the files come from (model, version, forcing, hashes, gates).
INFLOW_PROVENANCE = "run_manifest.json"


def require_chain_model(forcing: str) -> None:
    """Stop if this GENERATED folder holds a rim-inflow run of ``forcing`` (a key of
    ``WEATHER_SETS``) by another model than ``inflow_model``: each model's chain keeps its own
    GENERATED folder (``generated_dir``), so neither its run nor its G2 record is replaced."""
    path = get_arc_inflows(forcing).parent / INFLOW_PROVENANCE
    if path.exists():
        other = json.loads(path.read_text()).get("inflow_model")
        if other != get_inflow_model():
            raise SystemExit(f"{path.parent} holds a run of {other}; the chain of "
                             f"{get_inflow_model()} goes in its own GENERATED folder "
                             "(config: generated_dir)")


def require_pinned_run(folder: Path) -> dict:
    """Return the run manifest of the rim-inflow model outputs in ``folder``, and stop unless
    they come from the configured model (``inflow_model``) at the pinned version
    (``inflow_pin``) with no modified files, in a run that passed every gate, on the inputs G2
    last checked (``forcing_identity.csv`` of ``_1_build_forcing.py``). A run is clean only
    when the version it found is its pin, so the pin it records stands for the version. Outputs
    left over from another model, an earlier pin or an earlier input, or from a step that was
    not re-run after the config or the input changed, fail here."""
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
    run = (manifest.get("inflow_model"), manifest.get("model_pin"))
    pin = (get_inflow_model(), get_inflow_pin())
    if run != pin:
        raise RuntimeError(f"{folder}: built from {run[0]} at {run[1]}, but the config names "
                           f"{pin[0]} at {pin[1]} (inflow_model, inflow_pin); re-run "
                           "mod_forcing/inflows and the rim-inflow builder")
    if manifest.get("model_clean") is not True:
        raise RuntimeError(f"{path}: the run was made with --allow-dirty (off the pin, modified "
                           "files, or an environment that runs another folder), so it is not "
                           "the pinned version's")
    identity = (get_module_generated_dir("mod_forcing/inflows") / "output" / "_1_build_forcing"
                / WEATHER_SETS[manifest["forcing"]]["wgen"] / "forcing_identity.csv")
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
      (CalSim, Matched_inflow, Year, Month, qmap_postAdj), over WY1916-2018, the whole model
      run.
    - ``sv``, ``sv_dir`` (historical, A): the values over ``DELIVERY_WY`` in SV format (Part B,
      Part C, Year, Month, Value), e.g. ``_riminflow_productA_1922_2018.csv``, and the
      delivery folder that holds it, which the compiler scans.
    """
    root = (get_module_generated_dir("mod_hydrology/rim_inflow") / "output"
            / "_1_build_rim_inflow" / WEATHER_SETS[product]["wgen"])
    out = {"dir": root}
    if product in DELIVERY:
        out["ts"] = root / "calsim_qmap_validation_TS.csv"
        out["sv_dir"] = delivery_dir(root, product)
        out["sv"] = out["sv_dir"] / "_riminflow_{}_{}_{}.csv".format(DELIVERY[product]["tag"],
                                                                     *DELIVERY_WY)
    return out


#: The output folder of each module that holds its delivery folder (``delivery_dir``), relative
#: to GENERATED, by the SV compiler's module label; the rim inflows' sits with their run
#: (``get_rim_inflow_outputs``). The compiler reads these folders in this order.
DELIVERY_ROOTS = {
    "calsimhydro": "mod_hydrology/calsimhydro/output/_3_postprocess_single",
    "calsimhydro_ee": "mod_hydrology/calsimhydro_ee/output/_2_postprocess_single",
    "evaporation": "mod_reservoir/evaporation/output/_2_run_reservoir_evap",
    "rim_inflow": None,
    "delta_channel_depletion": "mod_hydrology/delta_channel_depletion/output/_2_postprocess_single",
    "small_watersheds": "mod_hydrology/small_watersheds/output/_2_postprocess_single",
    "storage_curves": "mod_reservoir/storage_curves/output",
    "instream_flows": "mod_other/instream_flows/output",
    "tulare_gw_terms": "mod_hydrology/tulare_gw_terms/output/_1_wyt_monthlyavg",
    "climate": "mod_forcing/climate/output",
    "miscellaneous": "mod_other/miscellaneous/output",
    "upper_watershed": "mod_other/upper_watershed/output",
}


def delivery_dirs(product: str) -> dict:
    """Return every module's delivery folder of ``product`` (a key of ``DELIVERY``), keyed as
    ``DELIVERY_ROOTS``."""
    return {label: get_rim_inflow_outputs(product)["sv_dir"] if rel is None
            else delivery_dir(get_generated_dir() / rel, product)
            for label, rel in DELIVERY_ROOTS.items()}


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
