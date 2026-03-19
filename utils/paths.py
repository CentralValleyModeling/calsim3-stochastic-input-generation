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

import json
import sys
from pathlib import Path

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
# Load user config → fall back to default
# ---------------------------------------------------------------------------
_USER_CFG = REPO_ROOT / "config.json"
_DEFAULT_CFG = REPO_ROOT / "config_default.json"


def _load_config() -> dict:
    cfg_path = _USER_CFG if _USER_CFG.exists() else _DEFAULT_CFG
    with open(cfg_path, "r") as f:
        return json.load(f)


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
    """Return ``<data_dir>/BASE`` — original reference and modeling files."""
    return DATA_DIR / "BASE"


def get_generated_dir() -> Path:
    """Return ``<data_dir>/GENERATED`` — all module input/output."""
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


def get_inventory_dir() -> Path:
    """Return the repo-level inventory directory."""
    return REPO_ROOT / "inventory"
