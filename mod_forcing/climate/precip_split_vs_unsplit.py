"""Quantify Livneh **Unsplit vs Split** total precipitation per 11obs & 9unimp basin,
full period and two sub-periods, and write the comparison artifacts.

Lives in the calsim3-stochastic-input-generation repo at ``mod_forcing/climate/``.
Repo data (BASE inputs, GENERATED outputs) is resolved through ``utils.paths`` per
the repo convention, so it follows ``config.json`` wherever the data dir lives.

Inputs (resolved via ``utils.paths.get_base_dir``):
  BASE/Historical_Climate/1_Historical/data_<lat>_<lon>   SPLIT:   prcp tmax tmin wind (no dates)
  BASE/WGEN/Historical_Unsplit/data_<lat>_<lon>           UNSPLIT: yr mo dy prcp tmax tmin

Basin cell sets + area_weight come from the **SAC-SMA repo** (``SACSMA_REPO`` below):
``data/hru/hruinfo_<domain>.csv`` (per-basin dedup; cells may be shared across nested
basins, e.g. BND nests SHA).  Outputs go to this repo's GENERATED tree
(via ``utils.paths.get_module_generated_dir``):
  GENERATED/mod_forcing/climate/output/precip_split_vs_unsplit/vic_precip_split_vs_unsplit.csv
  GENERATED/mod_forcing/climate/output/precip_split_vs_unsplit/vic_precip_split_vs_unsplit.png
  GENERATED/.../precip_split_vs_unsplit/vic_precip_split_vs_unsplit_bycell.csv  per-cell full-period split/unsplit + diff%
  GENERATED/.../precip_split_vs_unsplit/vic_precip_split_vs_unsplit_map.png     per-cell full-period diff% map
"""
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Resolve repo data through utils.paths (the sanctioned resolver) instead of
# hard-coded relative hops, so BASE inputs and GENERATED outputs follow config.json.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

BASE = get_base_dir()
# Normalize to a plain string (forward slashes -> backslashes; the long-path
# prefix get_base_dir adds is harmless here and these dirs are well under MAX_PATH)
# so os.listdir in index_dir is happy on Windows.
SP = os.path.normpath(str(BASE / "Historical_Climate" / "1_Historical"))  # split   (col 0 = prcp)
UN = os.path.normpath(str(BASE / "WGEN" / "Historical_Unsplit"))          # unsplit (col 3 = prcp)

# external SAC-SMA repo: supplies the basin->cell definitions (hruinfo) read below.
# Input only -- the comparison artifacts now go to this repo's GENERATED tree.
# Override via the SACSMA_REPO env var if the checkout moves.
SACSMA_REPO = os.environ.get("SACSMA_REPO", r"C:/Users/warnold_la/Local/repos/SAC-SMA")

N = 37986                                                 # 1915-01-01 .. 2018-12-31
YR = pd.date_range("1915-01-01", "2018-12-31", freq="D").year.to_numpy()
MASK = {"full": np.ones(N, bool), "P1": YR < 1950, "P2": YR >= 1950}
NYR = {"full": 104, "P1": 35, "P2": 69}
BASIN_LABEL = {
    "TNL": "Trinity", "SHA": "Shasta", "BND": "Bend Bridge", "FTO": "Feather", "YRS": "Yuba",
    "AMF": "American", "SNS": "Stanislaus", "TLG": "Tuolumne", "MRC": "Merced", "SJF": "San Joaquin",
}


def index_dir(d):
    idx = {}
    for fn in os.listdir(d):
        m = re.match(r"data_(-?\d+\.\d+)_(-?\d+\.\d+)$", fn)
        if m:
            idx[(round(float(m.group(1)), 5), round(float(m.group(2)), 5))] = os.path.join(d, fn)
    return idx


def main():
    print("indexing climate dirs...", flush=True)
    spx, unx = index_dir(SP), index_dir(UN)
    print(f"  split={len(spx)}  unsplit={len(unx)} cells", flush=True)
    cache = {}

    def cell(lat, lon):
        k = (round(lat, 5), round(lon, 5))
        if k in cache:
            return cache[k]
        fs, fu = spx.get(k), unx.get(k)
        if fs is None or fu is None:
            cache[k] = None
            return None
        s = np.loadtxt(fs, usecols=0, max_rows=N)
        u = np.loadtxt(fu, usecols=3, max_rows=N)
        r = {f"s_{p}": float(s[m].sum()) for p, m in MASK.items()}
        r.update({f"u_{p}": float(u[m].sum()) for p, m in MASK.items()})
        cache[k] = r
        return r

    rows = []
    for dom in ["11obs", "9unimp"]:
        h = pd.read_csv(os.path.join(SACSMA_REPO, "data", "hru", f"hruinfo_{dom}.csv"))
        for basin, gall in h.groupby("basin"):
            g = gall.drop_duplicates(["lat", "lon"])
            w = g["area_weight"].to_numpy(float)
            tot = [cell(la, lo) for la, lo in zip(g["lat"], g["lon"])]
            ok = [i for i, t in enumerate(tot) if t is not None]
            wok = w[ok] / w[ok].sum()
            rec = {"domain": dom, "basin": basin, "label": BASIN_LABEL.get(basin, basin),
                   "cells": len(g), "miss": len(tot) - len(ok),
                   "lat": float(np.average(g["lat"].to_numpy(float), weights=w))}
            for p in ("full", "P1", "P2"):
                s = float((wok * np.array([tot[i][f"s_{p}"] for i in ok])).sum()) / NYR[p]
                u = float((wok * np.array([tot[i][f"u_{p}"] for i in ok])).sum()) / NYR[p]
                rec[f"{p}_split"] = round(s, 1)
                rec[f"{p}_unsplit"] = round(u, 1)
                rec[f"{p}_diff_pct"] = round(100 * (u - s) / s, 2)
            rows.append(rec)

    res = pd.DataFrame(rows)
    out_dir = get_module_generated_dir("mod_forcing/climate") / "output" / "precip_split_vs_unsplit"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "vic_precip_split_vs_unsplit.csv"
    res.to_csv(out_csv, index=False)
    print("->", out_csv)

    # ---- figure: diff% by basin, full / P1 / P2, faceted by domain --------------
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 5.2), dpi=400)
    for ax, dom in zip(axes, ["11obs", "9unimp"]):
        # north -> south: ascending latitude puts south at the bottom, north at the top (barh)
        sub = res[res.domain == dom].sort_values("lat").reset_index(drop=True)
        y = np.arange(len(sub))
        ax.barh(y + 0.25, sub["P1_diff_pct"], height=0.25, color="#c1666b", label="1915–49")
        ax.barh(y, sub["full_diff_pct"], height=0.25, color="#4d4d4d", label="full")
        ax.barh(y - 0.25, sub["P2_diff_pct"], height=0.25, color="#48a9a6", label="1950–2018")
        ax.axvline(0, color="k", lw=0.6)
        ax.set_yticks(y)
        ax.set_yticklabels([f"{b} ({l})" if l != b else b for b, l in zip(sub["basin"], sub["label"])],
                           fontsize=7)
        ax.set_title(dom, fontsize=10)
        ax.set_xlabel("unsplit − split precip (% of split)", fontsize=8)
        ax.tick_params(axis="x", labelsize=7)
        ax.grid(axis="x", lw=0.3, alpha=0.5)
    axes[0].legend(fontsize=7, loc="lower right", framealpha=0.9)
    fig.suptitle("Livneh Unsplit vs Split - total precipitation, by basin and period", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out_png = out_dir / "vic_precip_split_vs_unsplit.png"
    fig.savefig(out_png)
    plt.close(fig)
    print("->", out_png)

    # ---- per-cell map: full-period diff% at each grid cell ----------------------
    # Reuse the cells already loaded for the basin averages: cache holds the
    # full-period split/unsplit totals per cell, so this adds no extra file I/O.
    cpts = [(la, lo, r["s_full"], r["u_full"])
            for (la, lo), r in cache.items() if r is not None and r["s_full"] > 0]
    cdf = pd.DataFrame(cpts, columns=["lat", "lon", "s_full", "u_full"])
    cdf["full_split"] = (cdf["s_full"] / NYR["full"]).round(1)    # mm/yr
    cdf["full_unsplit"] = (cdf["u_full"] / NYR["full"]).round(1)  # mm/yr
    cdf["full_diff_pct"] = (100 * (cdf["u_full"] - cdf["s_full"]) / cdf["s_full"]).round(2)
    out_cells = out_dir / "vic_precip_split_vs_unsplit_bycell.csv"
    cdf[["lat", "lon", "full_split", "full_unsplit", "full_diff_pct"]].to_csv(out_cells, index=False)
    print("->", out_cells)

    fig, ax = plt.subplots(figsize=(6.2, 7.6), dpi=400)
    vmax = max(1.0, float(np.nanpercentile(cdf["full_diff_pct"].abs(), 98)))  # clip outliers
    sc = ax.scatter(cdf["lon"], cdf["lat"], c=cdf["full_diff_pct"], cmap="RdBu",
                    vmin=-vmax, vmax=vmax, s=12, marker="s", linewidths=0)
    # geographic aspect: stretch latitude by 1/cos(lat) so the 1/16-deg cells read square
    ax.set_aspect(1.0 / np.cos(np.deg2rad(float(cdf["lat"].mean()))))
    ax.set_xlabel("longitude", fontsize=8)
    ax.set_ylabel("latitude", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(lw=0.3, alpha=0.4)
    ax.set_title("Livneh Unsplit - Split: full-period precip by cell\n"
                 f"(% of split; blue = unsplit wetter, red = drier; {len(cdf)} basin cells)",
                 fontsize=10)
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("unsplit - split precip (% of split)", fontsize=8)
    cb.ax.tick_params(labelsize=7)
    fig.tight_layout()
    out_map = out_dir / "vic_precip_split_vs_unsplit_map.png"
    fig.savefig(out_map)
    plt.close(fig)
    print("->", out_map)


if __name__ == "__main__":
    main()
