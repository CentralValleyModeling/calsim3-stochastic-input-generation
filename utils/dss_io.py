"""
Shared HEC-DSS I/O helpers
==========================
Centralizes the DSS-access boilerplate that was copy-pasted across the
pipeline: the Windows long-path directory-junction lifecycle, the
``HecDss.Open(..., catalog_flag=True)`` coupling, the start-of-period to
end-of-month timestamp shift, the ``<= -900`` missing-value sentinel, and the
``\\?\`` long-path-aware ``makedirs``.

pydsstools version coupling
---------------------------
This module passes ``catalog_flag=True`` to ``HecDss.Open`` and uses
``getPathnameList``.  Both require **pydsstools < 3** (pinned in
``environment.yml``): pydsstools 3.0 made ``HecDss.Open`` reject
``catalog_flag`` and removed ``getPathnameList``.  Keep the pin; do not
"upgrade" this module to the 3.x API without migrating every call site.

Behavior-preservation note
--------------------------
``read_monthly_series`` and ``read_monthly_frame`` are *faithful copies* of two
pre-existing, deliberately different read loops:

- ``read_monthly_series`` reproduces
  ``utils/qmap_product_a_from_pairs.read_calsim_monthly_pairs`` exactly
  (tuple ``(B_upper, C_upper)`` keys, pattern ``/*/*/*/*/1MON/*``, master
  series reindexed onto a fixed month-end range, sort by D-part then path).
- ``read_monthly_frame`` reproduces
  ``mod_hydrology/calsimhydro/_3_postprocess_product_a._read_dss`` exactly
  (string ``"B/C"`` keys with C-part case preserved, pattern
  ``/*/*/*/*/1MON/*/`` with trailing slash, inventory filter with all-paths
  fallback, sort by D-part only, wide DataFrame output).

They are intentionally NOT unified -- the differences are semantic and there
are no tests to catch a regression.  Each caller keeps its exact prior
contract.
"""
from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

# -- Windows long-path junction ------------------------------------------------
# The Fortran HEC-DSS library inside pydsstools limits path names to 256 chars.
# The data directory lives on OneDrive with a very long path, so for long paths
# we create a temporary Windows directory junction under the repo root to
# shorten it.  _DSS_LINK and _PATH_LIMIT are kept identical to the values that
# were duplicated in the postprocessors and the sv_compile compiler.

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DSS_LINK = _REPO_ROOT / "_dss_link"
_PATH_LIMIT = 200  # conservative limit vs Fortran's 256-char CNAME


def needs_junction(dss_path) -> bool:
    """Return True if the path is long enough to require a shortening junction."""
    return len(str(dss_path)) > _PATH_LIMIT


def create_junction(target_dir):
    """Create (or re-create) a directory junction at _DSS_LINK -> target_dir."""
    target_str = str(target_dir)
    if target_str.startswith("\\\\?\\"):
        target_str = target_str[4:]  # mklink /J requires a plain path, not \\?\ prefix
    # Use os.path.lexists so we also catch broken junctions (Path.exists follows
    # the reparse point and returns False if the target is gone, which would
    # leak a stale link and break the next mklink).
    if os.path.lexists(str(_DSS_LINK)):
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(_DSS_LINK), target_str],
        check=True, capture_output=True,
    )


def remove_junction():
    """Remove the _DSS_LINK junction (does not affect target directory)."""
    if os.path.lexists(str(_DSS_LINK)):
        subprocess.run(["cmd", "/c", "rmdir", str(_DSS_LINK)], capture_output=True)


@contextmanager
def open_dss(dss_path, *, version=6, catalog_flag=True, use_junction=None):
    """Open a DSS file, transparently handling the long-path junction.

    Parameters
    ----------
    dss_path : str or Path
        Path to the DSS file.
    version : int
        DSS file version passed to ``HecDss.Open`` (default 6).
    catalog_flag : bool
        Passed straight through to ``HecDss.Open``.  Default ``True`` matches
        the qmap engine and the sv_compile compiler.  Callers that previously
        opened *without* ``catalog_flag`` (e.g. the calsimhydro ``_read_dss``)
        must pass ``catalog_flag=False`` to preserve their exact prior call.
    use_junction : bool or None
        ``None`` (default) decides automatically via :func:`needs_junction`.
        Pass ``False`` to force a direct open (preserves the qmap engine's
        historical behavior of opening the ``\\?\``-prefixed path directly),
        or ``True`` to force a junction.

    Yields
    ------
    The open ``HecDss`` handle.  The junction (if created) is always removed
    on exit, including on error.
    """
    dss_path = Path(dss_path)
    if use_junction is None:
        use_junction = needs_junction(dss_path)

    if use_junction:
        create_junction(dss_path.parent)
        work_path = str(_DSS_LINK / dss_path.name)
    else:
        work_path = str(dss_path)

    try:
        with HecDss.Open(work_path, version=version,
                         catalog_flag=catalog_flag) as dss:
            yield dss
    finally:
        if use_junction:
            remove_junction()


# -- Timestamp / sentinel helpers ---------------------------------------------

def eom_index(pytimes) -> pd.DatetimeIndex:
    """Shift pydsstools start-of-period timestamps to end-of-month.

    pydsstools reports monthly timestamps at the start of the period; both the
    qmap engine and the postprocessors normalize them to month-end with this
    exact expression.
    """
    return (pd.to_datetime(pytimes).to_period("M") - 1).to_timestamp("M")


def apply_sentinel(values, sentinel: float = -900):
    """Return a float array with ``values <= sentinel`` replaced by NaN."""
    vals = np.asarray(values, dtype=float)
    return np.where(vals <= sentinel, np.nan, vals)


def _date_range_me(start, end=None, **kwargs) -> pd.DatetimeIndex:
    """Month-end DatetimeIndex (pandas 2.2+ ``freq="ME"``)."""
    return pd.date_range(start, end, freq="ME", **kwargs)


# -- Filesystem helper --------------------------------------------------------

def safe_makedirs(path):
    """Create directories, stripping the ``\\?\`` long-path prefix first.

    On Python 3.8 + Windows, ``os.makedirs`` cannot resolve the root of a
    ``\\?\X:\`` path, causing infinite recursion.  Stripping the prefix
    before the call avoids the issue without modifying ``utils/paths.py``.
    """
    s = str(path)
    if s.startswith("\\\\?\\"):
        s = s[4:]
    os.makedirs(s, exist_ok=True)


# -- Catalog helper -----------------------------------------------------------

def list_monthly_paths(dss, pattern="/*/*/*/*/1MON/*"):
    """Return the monthly pathname list for an open DSS handle.

    The default pattern matches the qmap engine.  Pass the trailing-slash
    variant ``/*/*/*/*/1MON/*/`` to match the calsimhydro postprocessor.
    """
    return dss.getPathnameList(pattern)


# -- Reader variant A: qmap engine (dict of month-end Series) -----------------

def read_monthly_series(dss, requested, dss_read_start, dss_read_end):
    """Faithful copy of ``read_calsim_monthly_pairs``'s read loop.

    Parameters
    ----------
    dss
        An open ``HecDss`` handle (see :func:`open_dss`).
    requested : set[tuple[str, str]]
        Set of ``(B_upper, C_upper)`` keys to extract.
    dss_read_start, dss_read_end
        Bounds of the fixed month-end master index each series is built onto.

    Returns
    -------
    dict[(B_upper, C_upper)] -> pd.Series
        Month-end indexed series; only keys with at least one non-NaN value.
    """
    if not requested:
        return {}

    full_idx = _date_range_me(dss_read_start, dss_read_end)
    out = {}

    paths = dss.getPathnameList("/*/*/*/*/1MON/*")
    bucket = {}
    for path in paths:
        parts = path.strip("/").split("/")
        if len(parts) != 6:
            continue
        key = (parts[1].strip().upper(), parts[2].strip().upper())
        if key in requested:
            bucket.setdefault(key, []).append(path)

    for key in sorted(requested):
        if key not in bucket:
            continue
        master = pd.Series(index=full_idx, dtype=float)
        for path in sorted(bucket[key],
                           key=lambda x: (x.strip("/").split("/")[3], x)):
            ts = dss.read_ts(path, trim_missing=True)
            vals = apply_sentinel(ts.values)
            idx = eom_index(ts.pytimes)
            master.update(pd.Series(vals, index=idx))
        if master.notna().any():
            out[key] = master

    return out


# -- Reader variant B: calsimhydro postprocessor (wide DataFrame) -------------

def read_monthly_frame(dss, excel_partcs):
    """Faithful copy of ``_3_postprocess_product_a._read_dss``'s read loop.

    Parameters
    ----------
    dss
        An open ``HecDss`` handle (see :func:`open_dss`).
    excel_partcs : dict
        Maps ``"B/C"`` (B upper-cased, C as-is) -> output column name.  Used
        to filter the catalog; if no path matches, all paths are read.

    Returns
    -------
    pd.DataFrame
        Wide, date-sorted; one column per matched Part B/C series.
    """
    data_dict = {}
    all_paths = dss.getPathnameList("/*/*/*/*/1MON/*/")
    print(f"    Catalog: {len(all_paths)} monthly paths found")

    # Group pathnames by Part B / Part C
    buckets = {}
    for p in all_paths:
        parts = p.strip("/").split("/")
        key = parts[1].upper() + "/" + parts[2]
        buckets.setdefault(key, []).append(p)

    # Filter to inventory SVs; fall back to all if none match
    wanted = {k: v for k, v in buckets.items() if k in excel_partcs}
    if not wanted:
        print("    No inventory match -- reading all paths")
        wanted = buckets
    else:
        print(f"    Matched {len(wanted)} of {len(excel_partcs)} inventory SVs")

    for part_BC, plist in wanted.items():
        master = {}
        for p in sorted(plist, key=lambda x: x.strip("/").split("/")[3]):
            ts = dss.read_ts(p, trim_missing=True)
            vals = np.asarray(ts.values, dtype=float)
            vals[vals <= -900] = np.nan
            idx = eom_index(ts.pytimes)
            s = pd.Series(vals, index=idx)
            master.update(s.to_dict())
        if master:
            series = pd.Series(master).sort_index()
            series.name = excel_partcs.get(part_BC, part_BC)
            data_dict[series.name] = series

    df = pd.DataFrame(data_dict).sort_index()
    print(f"    Result: {df.shape[1]} variables, {len(df)} timesteps")
    return df
