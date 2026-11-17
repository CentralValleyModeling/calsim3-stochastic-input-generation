"""
Pipeline Environment Check
==========================
``require_env`` stops a run whose interpreter lacks the pipeline's environment with one clear
message, before an import fails deep inside a script.

Checks:

- Python at least ``MIN_PYTHON`` (3.11, as in ``environment.yml``).
- ``pydsstools`` importable, which stands for the whole conda env. The env's name is not
  checked, so an env under another name or a venv with the same packages passes.

On failure it exits with a non-zero status and a message listing each failed check, the fix
``conda activate csstochastic`` (``EXPECTED_CONDA_ENV``) and ``sys.executable``.

``utils/paths.py`` calls ``require_env()`` on import, so every script and module that imports
``utils.paths`` runs the check. ``utils/check_scripts.py`` imports no project module, so the CI
lint job (``.github/workflows/lint.yml``, pyflakes only) runs it without pydsstools.

Usage
-----
    from utils.env_check import require_env
    require_env()
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
