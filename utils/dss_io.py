"""
HEC-DSS Access Helpers
======================
The pipeline's route to DSS files: ``open_dss`` and two monthly readers that turn a DSS catalog
into pandas series.

- ``open_dss(dss_path, version=6, catalog_flag=True, use_junction=None, **open_kwargs)``:
  context manager over ``HecDss.Open``. A path longer than 200 characters (``needs_junction``;
  the HEC-DSS Fortran library takes 256) opens through a directory junction
  ``_dss_link_<pid>_<n>`` under the repo root, removed on exit; ``create_junction`` also removes
  the junctions of processes no longer running. ``create_junction`` and ``remove_junction``
  serve callers that keep one junction over many opens.
- ``read_monthly_series(dss, requested, dss_read_start, dss_read_end)``: a dict of month-end
  Series keyed by upper-cased (Part B, Part C), each on a fixed month-end index over the read
  window; catalog ``/*/*/*/*/1MON/*``, records in D-part then path order; only keys with a value.
  ``utils.qmap_single_from_pairs``, ``utils.wyt_monthlyavg_framework`` and the rim-inflow
  builder read through it.
- ``read_monthly_frame(dss, excel_partcs)``: a wide frame, one column per ``"B/C"`` key (Part C
  case kept) of ``excel_partcs``, or of every monthly record when none matches; catalog
  ``/*/*/*/*/1MON/*/``, records in D-part order. The CalSimHydro and CalSimHydroEE
  postprocessors read through it.
- ``eom_index`` (pydsstools start-of-period times to month ends), ``apply_sentinel`` (values
  <= -900 to NaN), ``list_monthly_paths``, ``safe_makedirs`` (``os.makedirs`` with the Windows long-path
  prefix stripped).

The two readers differ in key form, catalog pattern and record order, and each caller depends on
its own form, so they stay separate.

``catalog_flag`` and ``getPathnameList`` exist only in pydsstools 2.x; ``environment.yml`` pins
``pydsstools<3``.

Usage
-----
    from utils import dss_io
    with dss_io.open_dss(dss_path) as dss:
        series = dss_io.read_monthly_series(dss, {("I_SHSTA", "FLOW-INFLOW")},
                                            "1921-10-31", "2021-09-30")
"""
from __future__ import annotations

import ctypes
import itertools
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

# -- Windows long-path junction ------------------------------------------------
# The Fortran HEC-DSS library inside pydsstools limits path names to 256 chars,
# and the data directory lives on OneDrive with a very long path, so a long path
# is opened through a temporary directory junction under the repo root. Every
# junction has its own name, _dss_link_<pid>_<n>, so runs in parallel and nested
# opens in one run never re-point each other's link. create_junction removes the
# junctions of processes that are no longer running (a killed run leaves its own).

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LINK_PREFIX = "_dss_link_"
_PATH_LIMIT = 200  # conservative limit vs Fortran's 256-char CNAME
_link_numbers = itertools.count(1)


def needs_junction(dss_path) -> bool:
    """Return True if the path is long enough to require a shortening junction."""
    return len(str(dss_path)) > _PATH_LIMIT


def _process_running(pid: int) -> bool:
    """True if process ``pid`` exists (a running process may refuse the query)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 5             # ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259                        # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _unlink(link) -> None:
    """Remove a junction; rmdir leaves the target's contents alone."""
    subprocess.run(["cmd", "/c", "rmdir", str(link)], capture_output=True)


def _remove_orphan_junctions() -> None:
    """Remove the junctions of processes that are no longer running."""
    for link in _REPO_ROOT.glob(f"{_LINK_PREFIX}*"):
        pid = link.name[len(_LINK_PREFIX):].split("_")[0]
        if pid.isdigit() and int(pid) != os.getpid() and not _process_running(int(pid)):
            _unlink(link)


def create_junction(target_dir) -> Path:
    """Create a new directory junction under the repo root to ``target_dir`` and return
    its path; remove it with :func:`remove_junction`."""
    target_str = str(target_dir)
    if target_str.startswith("\\\\?\\"):
        target_str = target_str[4:]  # mklink /J requires a plain path, not \\?\ prefix
    _remove_orphan_junctions()
    link = _REPO_ROOT / f"{_LINK_PREFIX}{os.getpid()}_{next(_link_numbers)}"
    # A dead process with this pid may have left the name behind, possibly broken:
    # os.path.lexists sees a broken junction, Path.exists does not.
    if os.path.lexists(str(link)):
        _unlink(link)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), target_str],
        check=True, capture_output=True,
    )
    return link


def remove_junction(link) -> None:
    """Remove a junction made by :func:`create_junction` (its target is untouched)."""
    if os.path.lexists(str(link)):
        _unlink(link)


@contextmanager
def open_dss(dss_path, *, version=6, catalog_flag=True, use_junction=None,
             **open_kwargs):
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
        Pass ``False`` to open the path directly, or ``True`` to force a
        junction.
    **open_kwargs
        Any additional keyword arguments are forwarded verbatim to
        ``HecDss.Open`` (e.g. ``window=(start, end)`` to pre-restrict a read
        to a time window).

    Yields
    ------
    The open ``HecDss`` handle.  The junction (if created) is always removed
    on exit, including on error.
    """
    dss_path = Path(dss_path)
    if use_junction is None:
        use_junction = needs_junction(dss_path)

    if use_junction:
        link = create_junction(dss_path.parent)
        work_path = str(link / dss_path.name)
    else:
        work_path = str(dss_path)

    try:
        with HecDss.Open(work_path, version=version,
                         catalog_flag=catalog_flag, **open_kwargs) as dss:
            yield dss
    finally:
        if use_junction:
            remove_junction(link)


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
    r"""Create directories, stripping the ``\\?\`` long-path prefix first.

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
    """Monthly series of the requested (Part B, Part C) keys, matched upper-cased.

    Every ``1MON`` record of a key is read in D-part, then pathname order onto one month-end
    index, a later record overwriting the months it holds; values <= -900 become NaN. Callers:
    ``utils.qmap_product_b_from_pairs.read_calsim_monthly_pairs``, ``utils.qmap_single_from_pairs``,
    ``utils.wyt_monthlyavg_framework`` and the rim-inflow builder.

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
    """Monthly series of an open DSS as a wide DataFrame (one column per inventory SV).

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
