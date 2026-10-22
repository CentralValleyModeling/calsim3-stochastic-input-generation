"""
SAC-SMA dPL-CalSim
==================
Adapter of the rim-inflow model SAC-SMA (``inflow_model`` ``sacsma``): its dPL-CalSim model
(run ``8_calsim`` at the current pin) with its share model, which divides each multi-arc
system's flow among its arcs. It runs through the product command of SAC-SMA's CLI, in the
conda environment ``inflow_env`` with ``inflow_repo`` first on PYTHONPATH:

    conda run -n <inflow_env> sacsma dpl calsim product apply --forcing <store> --out <folder>

Without ``--out``, SAC-SMA writes into its own tracked ``artifacts/product/calsim3/``. That
tracked copy is the series G1 compares the run with.

Input. SAC-SMA does not read the WGEN text files during a run. It reads a NetCDF store of the
4,410 grid cells it uses (``prcp``, ``tmin``, ``tmax``, daily). Historical unsplit and Product A
are in its checkout under ``data/inputs/forcing/``: ``historical_livneh_unsplit.nc`` (WGEN
NonDetrend-Unsplit, the model's training forcing) and ``wgen_product_a.nc`` (WGEN Product A
scenario 1). G2 requires each store value to equal the text value to float32 precision, with
two exceptions the stores make on purpose:

- the stores sort an inverted temperature pair (tmin above tmax), so G2 compares it with the
  sorted text pair;
- in the historical store SAC-SMA divides 289 documented x10 precipitation spikes by 10
  (``prcp_x10_artifacts.csv``), so G2 compares those (cell, day) pairs with a tenth of the
  text value.

The G2 table reports per store and variable the days compared, the largest absolute
difference, the values outside tolerance and the x10 pairs among the cells checked.

Product B. One pass cannot hold 1,008 stamp years: SAC-SMA keeps time as datetime64, which
spans 584 years, and dates the days on the Gregorian calendar. The adapter runs Product B in 10
segments, one per chunk (utils.wgen_calendar); segment 1 also takes the 9 months before chunk
1, so it starts on the first day of the record. build_inputs shifts each segment's stamp years
to 1904-2004, which puts the stamp leap days (years 1, 5, 9, ...) on Gregorian ones.
_1_build_forcing.py writes the 10 stores (``wgen_product_b_segNN.nc``) from
BASE/WGEN/Product_B/1, and run() then:

1. runs the segments' passes in order (``product apply --forcing <store> --start --end``):
   segment 1 from SAC-SMA's cycle spin-up, each later one from the model state the one before
   kept on its last day (``--save-state``, ``--init-state``), so the 10 passes give the flow of
   one unbroken run of the record (``sacsma verify learned`` checks this split, bit for bit);
2. checks gate G6: each pass ran the span of its segment, the spans follow each other day by
   day, and each later pass started from the state file the one before wrote (by sha256,
   which the pass records in its ``tier2_run_info.json``);
3. joins the chunks' months of the 10 passes into one pass, labelled with the stamp year plus
   1000 (pandas writes a year below 1000 without its leading zeros, so the months would not
   read back as written);
4. applies the share model once to the joined pass (``product apply --tier2 <joined>
   --centre-wy all``), centred on the whole record, the stationary climate's counterpart of
   the fit years WY1950-2015.

A 30-year lead-in in place of the hand-off left two segments 18.7% apart on I_MFS047's annual
volume 27 years into their overlap: some SAC-SMA stores keep their initial state for decades
(``sacsma/dpl/spinup.py``).

Output. ``rim_inflow_monthly.csv`` (arc, month, taf, dpl_taf, kind) holds the 196 arcs:
``taf`` is the product flow, ``kind`` share, single-arc system or non-anchor.
``tier2/tier2_monthly.csv`` holds the Sacramento valley node I_SRBB_VAL (UNIMP_SRBB is the sum
of its 8 arcs and this node), and ``tier2/tier2_run_info.json`` names the checkpoint and
extension cells the run used.
"""

import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path

import netCDF4
import numpy as np
import pandas as pd

from utils.wgen_calendar import CHUNK_MONTHS, N_CHUNKS, chunk_months, chunk_span, stamp_day_index

LABEL = "SAC-SMA"
FORCINGS = {"historical": "historical_livneh_unsplit", "A": "wgen_product_a",
            "B": "wgen_product_b"}
BUILT = {"B"}

# relative to the SAC-SMA repository; apply uses the default share model
STORE_DIR = Path("data") / "inputs" / "forcing"
X10_CSV = STORE_DIR / "prcp_x10_artifacts.csv"
CELLS_STORE = STORE_DIR / "wgen_product_a.nc"   # the 4,410 cells, in the order every store keeps
PRODUCT_DIR = Path("artifacts") / "product" / "calsim3"
SHARE_MODEL = PRODUCT_DIR / "share_model.pt"
VALLEY_NODE = "I_SRBB_VAL"
N_ARCS = 196
VARIABLES = ("prcp", "tmin", "tmax")
RTOL = ATOL = 1e-6          # G2: float32 holds the text's 2-3 decimals well inside this
G1_RTOL = 1e-5
G1_FLOOR = 1e-3             # TAF; G1 takes relative differences against at least this
GREGORIAN_START = 1904      # a segment's first stamp year (a leap year) becomes 1904, also leap
JOIN_OFFSET = 1000          # joined pass: stamp year + 1000
STATE_FILE = "state_end.npz"   # a segment's model state on its last day
BATCH = 64                 # cells read in parallel at a time
WORKERS = min(8, os.cpu_count() or 1)


def conda() -> str:
    path = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not path:
        raise SystemExit("conda not found (CONDA_EXE unset and conda not on PATH)")
    return path


def _plain(path: Path) -> Path:
    """``path`` without the ``\\\\?\\`` long-path prefix, which the NetCDF library does not read."""
    return Path(str(path).removeprefix("\\\\?\\"))


def _sub_env(repo: Path) -> dict:
    """The environment of a SAC-SMA call: its package imported from ``repo``."""
    return dict(os.environ, PYTHONPATH=str(repo))


def segments() -> list[dict]:
    """Product B's segments: per chunk, the first and last stamp day (y, m, d) of its pass and
    the year offset that shifts it to 1904-2004 with the leap days in place."""
    out = []
    for k in range(1, N_CHUNKS + 1):
        (y0, _), (y1, _) = chunk_span(k)
        start = (1, 1, 1) if k == 1 else (y0, 10, 1)
        offset = GREGORIAN_START - start[0]
        out.append({"segment": k, "start": start, "end": (y1, 9, 30), "offset": offset})
    return out


def _gregorian(day: tuple, offset: int) -> str:
    return date(day[0] + offset, day[1], day[2]).isoformat()


def inputs(repo: Path, forcing: str, build_dir: Path) -> list[Path]:
    """The NetCDF forcing store of ``forcing``; for Product B its 10 segment stores."""
    if forcing in BUILT:
        return [_plain(build_dir) / f"{FORCINGS[forcing]}_seg{s['segment']:02d}.nc"
                for s in segments()]
    return [repo / STORE_DIR / f"{FORCINGS[forcing]}.nc"]


def _cells(repo: Path) -> np.ndarray:
    with netCDF4.Dataset(repo / CELLS_STORE) as ds:
        return np.asarray(ds["key"][:]).astype(str)


def _read_batches(read_base, keys):
    """``(key, WGEN cell)`` in key order, read in worker processes ``BATCH`` cells at a time."""
    with ProcessPoolExecutor(WORKERS) as pool:
        for b in range(0, len(keys), BATCH):
            batch = keys[b:b + BATCH]
            yield from zip(batch, pool.map(read_base, batch))


def _ymd(w: pd.DataFrame) -> np.ndarray:
    return (w["y"].to_numpy(np.int64) * 10000 + w["m"].to_numpy(np.int64) * 100
            + w["d"].to_numpy(np.int64))


def _ymd_of(day: tuple) -> int:
    return day[0] * 10000 + day[1] * 100 + day[2]


def _sorted_pair(w: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    tmin, tmax = w["tmin"].to_numpy(float), w["tmax"].to_numpy(float)
    return np.minimum(tmin, tmax), np.maximum(tmin, tmax)


def build_inputs(repo: Path, forcing: str, read_base, build_dir: Path, source: str) -> list[Path]:
    """Write Product B's 10 segment stores from BASE, each cell read once, in the format of
    SAC-SMA's stores (data/inputs/forcing/build_region_forcing.py)."""
    if forcing not in BUILT:
        raise ValueError(f"{forcing}: SAC-SMA's checkout holds this store")
    keys = _cells(repo)
    files = inputs(repo, forcing, build_dir)
    files[0].parent.mkdir(parents=True, exist_ok=True)
    segs = segments()
    stores, rows, stamp = [], [], None
    try:
        for i, (k, w) in enumerate(_read_batches(read_base, keys)):
            ymd = _ymd(w)
            if stamp is None:
                stamp = ymd
                for s, f in zip(segs, files):
                    r = np.flatnonzero((ymd >= _ymd_of(s["start"])) & (ymd <= _ymd_of(s["end"])))
                    if not len(r) or not (np.diff(r) == 1).all():
                        raise SystemExit(f"cell {k}: segment {s['segment']} has no contiguous days")
                    rows.append(r)
                    stores.append(_create_store(f, keys, w.iloc[r], s, source))
            elif not np.array_equal(ymd, stamp):
                raise SystemExit(f"cell {k}: its days differ from those of cell {keys[0]}")
            tmin, tmax = _sorted_pair(w)
            vals = {"prcp": w["prcp"].to_numpy(np.float32), "tmin": tmin.astype(np.float32),
                    "tmax": tmax.astype(np.float32)}
            for ds, r in zip(stores, rows):
                for v in VARIABLES:
                    ds[v][i, :] = vals[v][r]
            if (i + 1) % 500 == 0:
                print(f"  {i + 1}/{len(keys)} cells written", flush=True)
    finally:
        for ds in stores:
            ds.close()
    return files


def _create_store(path: Path, keys, days: pd.DataFrame, seg: dict, source: str) -> netCDF4.Dataset:
    """An empty segment store: its cells, and its days shifted to 1904-2004."""
    off = seg["offset"]
    greg = pd.to_datetime(pd.DataFrame({"year": days["y"] + off, "month": days["m"],
                                        "day": days["d"]}))
    if not (np.diff(greg.to_numpy()) == np.timedelta64(1, "D")).all():
        raise SystemExit(f"segment {seg['segment']}: the stamp days do not map onto consecutive "
                         f"Gregorian days with offset {off}")
    first = greg.iloc[0]
    (c0, _), (c1, _) = chunk_span(seg["segment"])
    ds = netCDF4.Dataset(path, "w", format="NETCDF4")
    ds.setncatts({
        "title": f"WGEN Product B scenario 1, segment {seg['segment']} of {N_CHUNKS}, "
                 "unified region store",
        "source": source,
        "note": f"chunk {seg['segment']} (stamp Oct {c0} to Sep {c1})"
                f"{', from the record start' if seg['segment'] == 1 else ''}; stamp years "
                f"{seg['start'][0]}-{seg['end'][0]} relabelled by +{off} so the leap days fall "
                "on Gregorian leap years; tmin/tmax pairs sorted; written by csstochastic "
                "mod_forcing/inflows (sacsma adapter)",
        "stamp_offset": np.int32(off),
        "chunk": np.int32(seg["segment"]),
    })
    ds.createDimension("key", len(keys))
    ds.createDimension("time", len(days))
    kv = ds.createVariable("key", str, ("key",))
    kv[:] = np.asarray(keys, dtype=object)
    tv = ds.createVariable("time", "i8", ("time",))
    tv.units = f"days since {first:%Y-%m-%d} 00:00:00"
    tv.calendar = "proleptic_gregorian"
    tv[:] = np.arange(len(days), dtype=np.int64)
    for v in VARIABLES:
        ds.createVariable(v, "f4", ("key", "time"), zlib=True, complevel=4, shuffle=True,
                          chunksizes=(1, len(days)), fill_value=np.float32(np.nan))
    return ds


def _store_days(ds: netCDF4.Dataset) -> np.ndarray:
    """The stamp days (yyyymmdd) of a store: its dates less the segment's offset, if any."""
    t = netCDF4.num2date(ds["time"][:], ds["time"].units, getattr(ds["time"], "calendar",
                         "standard"), only_use_cftime_datetimes=False,
                         only_use_python_datetimes=True)
    off = int(getattr(ds, "stamp_offset", 0))
    return np.array([(d.year - off) * 10000 + d.month * 100 + d.day for d in t], dtype=np.int64)


def check_inputs(repo: Path, forcing: str, files: list[Path], read_base,
                 n_cells: int | None) -> pd.DataFrame:
    """Gate G2: each store against the WGEN text files, on ``n_cells`` seeded cells or all."""
    stores = [netCDF4.Dataset(f) for f in files]
    try:
        keys = np.asarray(stores[0]["key"][:]).astype(str)
        for f, ds in zip(files[1:], stores[1:]):
            if not np.array_equal(np.asarray(ds["key"][:]).astype(str), keys):
                raise SystemExit(f"{f.name}: its cells differ from those of {files[0].name}")
        days = [_store_days(ds) for ds in stores]
        if forcing in BUILT:
            for f, d, s in zip(files, days, segments(), strict=True):
                want = (_ymd_of(s["start"]), _ymd_of(s["end"]),
                        stamp_day_index(*s["end"]) - stamp_day_index(*s["start"]) + 1)
                if (int(d[0]), int(d[-1]), len(d)) != want:
                    raise SystemExit(f"{f.name}: days {d[0]}-{d[-1]} ({len(d)}), but segment "
                                     f"{s['segment']} is {want[0]}-{want[1]} ({want[2]}); "
                                     "rebuild the stores")
        if n_cells is None or n_cells >= len(keys):
            idx = np.arange(len(keys))
        else:
            idx = np.sort(np.random.default_rng(0).choice(len(keys), n_cells, replace=False))
        print(f"{len(keys)} cells in {len(files)} store(s), {sum(map(len, days))} days; "
              f"checking {len(idx)} cells")

        x10 = {}    # cell -> stamp days (yyyymmdd) of its x10 spikes
        if forcing == "historical":
            t = pd.read_csv(repo / X10_CSV, parse_dates=["date"])
            for k, g in t.groupby("key"):
                x10[k] = set((g["date"].dt.year * 10000 + g["date"].dt.month * 100
                              + g["date"].dt.day).tolist())

        rows = {(f, v): dict(variable=v, cells=0, days=0, max_abs_diff=0.0, outside_tol=0,
                             x10_pairs=0) for f in files for v in VARIABLES}
        for n, (k, w) in enumerate(_read_batches(read_base, keys[idx]), 1):
            i = idx[n - 1]
            ymd = _ymd(w)
            lo, hi = _sorted_pair(w)
            text = {"prcp": w["prcp"].to_numpy(float), "tmin": lo, "tmax": hi}
            for f, ds, d in zip(files, stores, days):
                pos = np.searchsorted(ymd, d)
                if (pos >= len(ymd)).any() or not np.array_equal(ymd[pos], d):
                    raise SystemExit(f"cell {k}: the days of {f.name} are not all in BASE")
                if forcing not in BUILT and len(d) != len(ymd):
                    raise SystemExit(f"cell {k}: {len(ymd)} days in BASE, {len(d)} in {f.name}")
                for v, ref in text.items():
                    got = np.asarray(ds[v][i, :], dtype=float)
                    exp = ref[pos].copy()
                    r = rows[(f, v)]
                    if v == "prcp" and k in x10:
                        hits = np.flatnonzero(np.isin(d, list(x10[k])))
                        exp[hits] = exp[hits] / 10.0
                        r["x10_pairs"] += len(hits)
                    diff = np.abs(got - exp)
                    r["cells"] += 1
                    r["days"] += len(diff)
                    r["max_abs_diff"] = max(r["max_abs_diff"], float(diff.max()))
                    r["outside_tol"] += int((~np.isclose(got, exp, rtol=RTOL, atol=ATOL)).sum())
            if n % 500 == 0:
                print(f"  {n}/{len(idx)} cells", flush=True)
    finally:
        for ds in stores:
            ds.close()

    out = pd.DataFrame([{**r, "input": f} for (f, _), r in rows.items()])
    out["pass"] = out["outside_tol"] == 0
    out["input_cells"] = len(keys)
    cols = ["variable", "cells", "days", "max_abs_diff", "outside_tol", "x10_pairs", "pass",
            "input_cells", "input"]
    return out[cols]


def check_environment(repo: Path, env: str) -> dict:
    """The repository the conda environment imports the ``sacsma`` package from."""
    out = subprocess.run([conda(), "run", "-n", env, "python", "-c",
                          "import sacsma; print(sacsma.__file__)"],
                         capture_output=True, text=True, check=True, env=_sub_env(repo)).stdout
    package = Path(out.strip().splitlines()[-1]).resolve().parents[1]
    return {"conda_env": env, "package": str(package), "ok": package == repo.resolve()}


def _apply(repo: Path, env: str, args: list[str]) -> list[str]:
    cmd = [conda(), "run", "-n", env, "--no-capture-output",
           "sacsma", "dpl", "calsim", "product", "apply", *args]
    print("Running:", " ".join(cmd[1:]), flush=True)
    subprocess.run(cmd, cwd=repo, check=True, env=_sub_env(repo))
    return cmd


def run(repo: Path, env: str, forcing: str, files: list[Path], out_dir: Path) -> list[list[str]]:
    """``product apply`` on the forcing; for Product B the 10 segments, each from the state the
    one before kept, G6, the join and one application of the share model (module docstring)."""
    if forcing not in BUILT:
        return [_apply(repo, env, ["--forcing", FORCINGS[forcing], "--out", str(out_dir)])]
    cmds, state = [], None
    # product apply always applies the share model, and its default centre years (WY1950-2015)
    # lie outside 1904-2004, hence --centre-wy all; the segments' own products are not used.
    for s, f in zip(segments(), files):
        seg_dir = out_dir / "segments" / f"seg{s['segment']:02d}"
        seg_dir.mkdir(parents=True)
        cmds.append(_apply(repo, env, [
            "--forcing", str(f), "--start", _gregorian(s["start"], s["offset"]),
            "--end", _gregorian(s["end"], s["offset"]), "--centre-wy", "all",
            *(["--init-state", str(state)] if state else []),
            "--save-state", str(seg_dir / STATE_FILE), "--out", str(seg_dir)]))
        state = seg_dir / STATE_FILE
    if not handoff(out_dir)["pass"]:
        raise SystemExit("G6 failed: " + (out_dir / "g6_handoff.json").read_text())
    join(out_dir, FORCINGS[forcing])
    cmds.append(_apply(repo, env, ["--tier2", str(out_dir / "joined"), "--forcing",
                                   FORCINGS[forcing], "--centre-wy", "all",
                                   "--out", str(out_dir)]))
    return cmds


def _stamp_months(t: pd.DataFrame, offset: int) -> tuple[np.ndarray, np.ndarray]:
    """The stamp (year, month) of a pass table's ``YYYY-MM`` months."""
    ym = t["month"].str.split("-", expand=True).astype(int)
    return ym[0].to_numpy() - offset, ym[1].to_numpy()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def handoff(out_dir: Path) -> dict:
    """Gate G6 (module docstring): per segment its span, the span its pass ran, how it started
    and the sha256 of the state it kept, in ``g6_handoff.json``."""
    rows, prev = [], None
    for s in segments():
        seg_dir = out_dir / "segments" / f"seg{s['segment']:02d}"
        info = json.loads((seg_dir / "tier2" / "tier2_run_info.json").read_text())
        row = {"segment": s["segment"], "start": s["start"], "end": s["end"],
               "envelope": info.get("envelope"), "spinup": info.get("spinup"),
               "init_state_sha256": info.get("init_state_sha256"),
               "state_sha256": _sha256(seg_dir / STATE_FILE)}
        ran = row["envelope"] == [_gregorian(s["start"], s["offset"]),
                                  _gregorian(s["end"], s["offset"])]
        first = stamp_day_index(*s["start"])
        if prev is None:
            row["pass"] = ran and first == 0 and row["spinup"] == "cycle"
        else:
            row["pass"] = (ran and first == stamp_day_index(*prev["end"]) + 1
                           and row["spinup"] == "state"
                           and row["init_state_sha256"] == prev["state_sha256"])
        rows.append(row)
        prev = row
    summary = {"segments": rows, "pass": all(r["pass"] for r in rows)}
    (out_dir / "g6_handoff.json").write_text(json.dumps(summary, indent=1))
    bad = [r["segment"] for r in rows if not r["pass"]]
    print(f"G6: {len(rows)} segments, each from the state the one before kept; "
          + ("PASS" if not bad else f"FAIL at segment(s) {bad}"), flush=True)
    return summary


def join(out_dir: Path, forcing_name: str) -> Path:
    """The chunks' months of the segment passes as one pass in ``out_dir/joined``, labelled
    with the stamp year plus ``JOIN_OFFSET``."""
    dest = out_dir / "joined"
    dest.mkdir()
    segs = segments()
    for name in ("tier2_monthly.csv", "tier2_components_monthly.csv"):
        parts = []
        for s in segs:
            t = pd.read_csv(out_dir / "segments" / f"seg{s['segment']:02d}" / "tier2" / name)
            y, m = _stamp_months(t, s["offset"])
            keep = (chunk_months(y, m)["chunk"] == s["segment"]).to_numpy()
            t = t[keep].copy()
            t["month"] = [f"{a + JOIN_OFFSET:04d}-{b:02d}" for a, b in zip(y[keep], m[keep])]
            parts.append(t)
        arcs = {frozenset(p["arc"]) for p in parts}
        if len(arcs) != 1:
            raise SystemExit(f"{name}: the segments' passes hold different arcs")
        joined = pd.concat(parts, ignore_index=True)
        if "ref_taf" in joined:
            joined["ref_taf"] = np.nan      # CalSim3 has no stamp years
        n = joined.groupby("arc")["month"].nunique()
        if (n != N_CHUNKS * CHUNK_MONTHS).any() or joined.duplicated(["arc", "month"]).any():
            raise SystemExit(f"{name}: the joined pass is not the {N_CHUNKS * CHUNK_MONTHS} "
                             "chunk months once per arc")
        joined.sort_values(["arc", "month"]).to_csv(dest / name, index=False)
    info = json.loads((out_dir / "segments" / "seg01" / "tier2" / "tier2_run_info.json")
                      .read_text())
    first, last = (*chunk_span(1)[0], 1), segs[-1]["end"]
    info.update(forcing=forcing_name,
                envelope=[f"{first[0] + JOIN_OFFSET:04d}-{first[1]:02d}-{first[2]:02d}",
                          f"{last[0] + JOIN_OFFSET:04d}-{last[1]:02d}-{last[2]:02d}"],
                joined=f"the chunks of {len(segs)} segment passes, stamp year + {JOIN_OFFSET}")
    (dest / "tier2_run_info.json").write_text(json.dumps(info, indent=1))
    return dest


def describe(repo: Path, forcing: str, out_dir: Path) -> dict:
    """The checkpoint and extension cells the run used, as its record names them."""
    info = json.loads((out_dir / "tier2" / "tier2_run_info.json").read_text())
    run_info = {"pass_envelope": info.get("envelope")}
    if forcing in BUILT:
        run_info.update(segments=segments(), segment_start="the state the one before kept",
                        centre_wy="all", join_offset=JOIN_OFFSET)
    return {"model": f"SAC-SMA dPL-CalSim (run {Path(info['checkpoint']).parents[1].name}) "
                     "with its share model",
            "files": {"checkpoint": info["checkpoint"],
                      "extension_cells": info["extension_cells"],
                      "share_model": SHARE_MODEL.as_posix()},
            "run": run_info}


def rel_diff(new: pd.Series, old: pd.Series) -> dict:
    """Largest relative difference, and the rows where either side is missing."""
    d = (new - old).abs() / np.maximum(old.abs(), G1_FLOOR)
    return {"max_rel_diff": float(d.max()) if d.notna().any() else 0.0,
            "missing": int(d.isna().sum())}


def valley(run_dir: Path, months) -> pd.DataFrame:
    t = pd.read_csv(run_dir / "tier2" / "tier2_monthly.csv", usecols=["arc", "month", "sim_taf"])
    return t[(t["arc"] == VALLEY_NODE) & t["month"].isin(months)]


def reproduce(repo: Path, forcing: str, out_dir: Path) -> dict:
    """Gate G1: the run against the series SAC-SMA tracks for the same forcing: ``taf`` and
    ``dpl_taf`` of every arc-month to a relative difference of 1e-5, the same ``kind``, and
    I_SRBB_VAL. A missing value on either side fails."""
    tracked_dir = repo / PRODUCT_DIR / FORCINGS[forcing]
    a = pd.read_csv(out_dir / "rim_inflow_monthly.csv")
    b = pd.read_csv(tracked_dir / "rim_inflow_monthly.csv")
    m = a.merge(b, on=["arc", "month"], how="outer", suffixes=("", "_tracked"), indicator=True)
    unmatched = int((m["_merge"] != "both").sum())
    m = m[m["_merge"] == "both"]
    va = valley(out_dir, set(a["month"]))
    vb = valley(tracked_dir, set(a["month"]))
    v = va.merge(vb, on="month", how="outer", suffixes=("", "_tracked"))
    out = {"tracked": str(tracked_dir), "arc_months": int(len(m)), "unmatched_rows": unmatched,
           "kind_mismatches": int((m["kind"] != m["kind_tracked"]).sum()),
           "taf": rel_diff(m["taf"], m["taf_tracked"]),
           "dpl_taf": rel_diff(m["dpl_taf"], m["dpl_taf_tracked"]),
           "valley_months": int(len(v)),
           "valley": rel_diff(v["sim_taf"], v["sim_taf_tracked"])}
    diffs = [out[k] for k in ("taf", "dpl_taf", "valley")]
    out["pass"] = bool(unmatched == 0 and out["kind_mismatches"] == 0
                       and out["valley_months"] == a["month"].nunique()
                       and all(d["missing"] == 0 and d["max_rel_diff"] <= G1_RTOL for d in diffs))
    return out


def gates(repo: Path, forcing: str, out_dir: Path) -> dict:
    """G1 against SAC-SMA's tracked series; for Product B, which SAC-SMA does not track, G6."""
    if forcing in BUILT:
        return {"G6": json.loads((out_dir / "g6_handoff.json").read_text())}
    return {"G1": reproduce(repo, forcing, out_dir)}


def arc_flows(forcing: str, out_dir: Path) -> pd.DataFrame:
    """The 196 arcs and the valley node (``kind`` valley) over the product's months."""
    prod = pd.read_csv(out_dir / "rim_inflow_monthly.csv", usecols=["arc", "month", "taf", "kind"])
    if prod["arc"].nunique() != N_ARCS:
        raise SystemExit(f"{out_dir}: {prod['arc'].nunique()} arcs, expected {N_ARCS}")
    months = set(prod["month"])
    val = valley(out_dir, months)
    if len(val) != len(months):
        raise SystemExit(f"{out_dir}: {VALLEY_NODE} covers {len(val)} of {len(months)} months")
    val = val.rename(columns={"sim_taf": "taf"}).assign(kind="valley")
    out = pd.concat([prod, val[["arc", "month", "taf", "kind"]]], ignore_index=True)
    y, m = _stamp_months(out, JOIN_OFFSET if forcing in BUILT else 0)
    return pd.DataFrame({"arc": out["arc"], "year": y, "month": m, "taf": out["taf"],
                         "kind": out["kind"]})
