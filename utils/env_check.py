"""
Pipeline Environment Sanity Check
=================================
Fast preflight that catches the most common foot-gun: running a pipeline
script in the wrong shell / wrong Python where the project's dependencies
aren't installed. Without this, scripts fail dozens of frames deep with a
generic ``ModuleNotFoundError: No module named 'pandas'`` (or similar)
instead of a clear "wrong env" message.

How it triggers
---------------
``utils/paths.py`` calls ``require_env()`` once at module load, and every
numbered pipeline script imports from ``utils.paths``. So just opening any
pipeline script in the wrong env produces the clear error -- no per-script
``require_env()`` call is needed.

Library modules (``utils/dss_io.py``, ``utils/csv_io.py``,
``utils/quantile_mapping.py``, ``utils/qmap_product_*_from_pairs.py``,
``utils/wyt_monthlyavg_framework.py``, ``utils/dss_pickle_builder.py``,
``utils/check_scripts.py``) do not import ``utils.paths``, so they do not
trigger the check -- intentional: the CI lint workflow (which only has
pyflakes installed, not pydsstools) runs ``python utils/check_scripts.py``
and would otherwise spuriously fail this check.

Invariants enforced
-------------------
- Python interpreter version >= ``MIN_PYTHON`` (matches ``environment.yml``).
- ``pydsstools`` is importable. This is the project's canary dep: if it
  imports, the conda env (or equivalent) is essentially correct. We do
  not check the conda env name itself because that is brittle (users may
  use venv, may rename the env, may run without ``conda activate`` from
  a Python they know is correct).

On failure
----------
Prints a multi-line diagnostic naming each failing invariant, suggests
``conda activate csstochastic``, prints ``sys.executable`` so the user
can see which interpreter is running, and ``sys.exit(...)`` with a
non-zero status.
"""
from __future__ import annotations

import importlib.util
import sys

MIN_PYTHON: tuple[int, int] = (3, 11)
EXPECTED_CONDA_ENV: str = "csstochastic"


def require_env() -> None:
    """Fail fast if the running interpreter is missing pipeline dependencies."""
    issues: list[str] = []

    py = sys.version_info
    if (py.major, py.minor) < MIN_PYTHON:
        issues.append(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required, "
            f"got {py.major}.{py.minor}.{py.micro}"
        )

    if importlib.util.find_spec("pydsstools") is None:
        issues.append("pydsstools not importable (not installed in this Python)")

    if not issues:
        return

    lines = ["", "ERROR: wrong Python environment for this pipeline."]
    for i in issues:
        lines.append(f"  - {i}")
    lines.append("")
    lines.append(
        f"Fix: activate the '{EXPECTED_CONDA_ENV}' conda env in your shell:"
    )
    lines.append(f"  conda activate {EXPECTED_CONDA_ENV}")
    lines.append("")
    lines.append(f"Current interpreter: {sys.executable}")
    sys.exit("\n".join(lines))
