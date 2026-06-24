"""Five-way precipitation comparison at the UHH basins.

Compares annual (water-year) precipitation from five sources, area-weighted to
each UHH location, with Trinity (TR_UHH) highlighted for GitHub issue #78:

  1. PRISM_AN        PRISM all-networks, 4km      (independent reference)
  2. PRISM_LT        PRISM long-term/stable, 800m (independent reference)
  3. Hist_CalSim     CalSim historical SV precip  (__calsim_sv_default__.dss)
  4. LIVNEH_UNSPLIT  Livneh "unsplit" forcing     (WGEN/Historical_Unsplit, col 3)
  5. LIVNEH_SPLIT    Livneh "split" forcing       (Historical_Climate_LTO/1_Historical, col 0)

The four gridded per-cell sources (all named data_<lat>_<lon>) are area-weighted
to each UHH location using the GridInfo weights (mod_forcing/vic/reference/
GridInfo); Hist_CalSim is read per location from the default CalSim SV DSS. All
series are annual WY totals in inches.

Repo data is resolved through utils.paths (so it follows config.json). The DSS
reader and GridInfo/location helpers are reused from _2_uhh_basin_averages.

Outputs (GENERATED/mod_forcing/climate/output/precip_5way_comparison/):
  precip_5way_annual_stats.csv     tidy: location, source, period, mean/min/max (in/yr), n_WY
  precip_5way_panel_<LOC>.png      per basin: time-series overlay + full/pre-1950/post-1950 bars
  precip_5way_fullmean_bar.png     full-period mean per source, grouped by location
"""
import os
import re
import sys
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Resolve repo data through utils.paths (the sanctioned resolver).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir

# Reuse the DSS historical reader and GridInfo/location helpers from the sibling
# UHH module (module name starts with a digit-friendly underscore, so import by name).
sys.path.insert(0, str(Path(__file__).resolve().parent))
uhh = importlib.import_module("_2_uhh_basin_averages")

BASE = get_base_dir()
# Plain strings for os.listdir (the long-path prefix get_base_dir adds is harmless
# here and these dirs are well under MAX_PATH).
PRISM_AN_DIR = os.path.normpath(str(BASE / "PRISM" / "an"))
PRISM_LT_DIR = os.path.normpath(str(BASE / "PRISM" / "lt"))
SPLIT_DIR    = os.path.normpath(str(BASE / "Historical_Climate_LTO" / "1_Historical"))  # col 0 = prcp
UNSPLIT_DIR  = os.path.normpath(str(BASE / "WGEN" / "Historical_Unsplit"))          # col 3 = prcp

REPO_ROOT = Path(__file__).resolve().parents[2]
GRIDINFO_DIR = REPO_ROOT / "mod_forcing" / "vic" / "reference" / "GridInfo"
LOCS_CSV = Path(__file__).resolve().parent / "reference" / "uhh_locations.csv"

MM_PER_IN = 25.4
TRINITY = "TR_UHH"

# Common-overlap water-year windows for the period-mean table:
#   Hist_CalSim 1922-2021, Split/Unsplit 1916-2018, PRISM 1916-2025 -> common 1922-2018.
PERIODS = [("full", 1922, 2018), ("pre1950", 1922, 1949), ("post1950", 1950, 2018)]

SOURCES = ["PRISM_AN", "PRISM_LT", "Hist_CalSim", "LIVNEH_SPLIT", "LIVNEH_UNSPLIT"]
COLORS = {
    "PRISM_AN": "#1f77b4",        # blue
    "PRISM_LT": "#17becf",        # teal
    "Hist_CalSim": "#222222",     # near-black: the CalSim reference
    "LIVNEH_SPLIT": "#ff7f0e",    # orange
    "LIVNEH_UNSPLIT": "#d62728",  # red
}
DIR_OF = {"PRISM_AN": PRISM_AN_DIR, "PRISM_LT": PRISM_LT_DIR,
          "LIVNEH_SPLIT": SPLIT_DIR, "LIVNEH_UNSPLIT": UNSPLIT_DIR}


def index_dir(d):
    """Map (round(lat,5), round(lon,5)) -> file path for a data_<lat>_<lon>[.txt] dir."""
    idx = {}
    if not os.path.isdir(d):
        return idx
    for fn in os.listdir(d):
        m = re.match(r"data_(-?\d+\.\d+)_(-?\d+\.\d+)(?:\.txt)?$", fn)
        if m:
            idx[(round(float(m.group(1)), 5), round(float(m.group(2)), 5))] = os.path.join(d, fn)
    return idx


def _prism_cell_wy(path):
    """PRISM monthly txt (header Year Month ppt tmin tmax) -> Series WY -> inches/yr.
    Keeps only complete (12-month) water years."""
    df = pd.read_csv(path, sep="\t")
    df = df.dropna(subset=["ppt"])
    df["WY"] = df["Year"] + (df["Month"] >= 10).astype(int)
    g = df.groupby("WY")["ppt"]
    tot, cnt = g.sum(), g.count()
    return (tot[cnt == 12]) / MM_PER_IN


def _daily_cell_wy(path, usecol):
    """Daily per-cell file (no dates; row i = 1915-01-01 + i days) -> Series WY -> inches/yr.
    usecol selects the precip column (Split col 0, Unsplit col 3). Keeps complete WYs (>=365 days)."""
    v = np.loadtxt(path, usecols=usecol)
    dates = pd.date_range("1915-01-01", periods=len(v), freq="D")
    df = pd.DataFrame({"p": v, "WY": dates.year + (dates.month >= 10).astype(int)})
    g = df.groupby("WY")["p"]
    tot, cnt = g.sum(), g.count()
    return (tot[cnt >= 365]) / MM_PER_IN


_CACHE = {}


def _cell_wy(source, path):
    key = (source, path)
    if key not in _CACHE:
        if source in ("PRISM_AN", "PRISM_LT"):
            _CACHE[key] = _prism_cell_wy(path)
        elif source == "LIVNEH_SPLIT":
            _CACHE[key] = _daily_cell_wy(path, 0)
        elif source == "LIVNEH_UNSPLIT":
            _CACHE[key] = _daily_cell_wy(path, 3)
    return _CACHE[key]


def location_series(gi_df, source, idx):
    """Area-weight a gridded source over a basin's GridInfo cells -> Series WY -> inches/yr.
    Renormalizes weights over the cells actually present in the source; inner-joins on WY."""
    cols, weights = [], []
    for _, r in gi_df.iterrows():
        key = (round(float(r["lat"]), 5), round(float(r["lon"]), 5))
        p = idx.get(key)
        if p is None:
            continue
        s = _cell_wy(source, p)
        if s is None or s.empty:
            continue
        cols.append(s.rename(len(cols)))
        weights.append(float(r["weight1"]))
    if not cols:
        return None, 0, len(gi_df)
    df = pd.concat(cols, axis=1, join="inner")
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    loc = pd.Series((df.values * w).sum(axis=1), index=df.index)
    return loc, len(cols), len(gi_df) - len(cols)


def period_stats(s, lo, hi):
    if s is None:
        return {"mean": np.nan, "min": np.nan, "max": np.nan, "n": 0}
    v = s[(s.index >= lo) & (s.index <= hi)]
    if len(v) == 0:
        return {"mean": np.nan, "min": np.nan, "max": np.nan, "n": 0}
    return {"mean": float(v.mean()), "min": float(v.min()),
            "max": float(v.max()), "n": int(len(v))}


# Sources other than the CalSim historical reference (which is the 0 baseline in
# the period-mean bar charts).
OTHER_SOURCES = [s for s in SOURCES if s != "Hist_CalSim"]


def _pct_vs_hist(mean_src, mean_hist):
    """Percent difference of a source from CalSim historical (the zero point)."""
    if (mean_hist is None or mean_src is None or np.isnan(mean_hist)
            or np.isnan(mean_src) or mean_hist == 0):
        return np.nan
    return 100.0 * (mean_src - mean_hist) / mean_hist


def plot_panel(loc, series_by_source, stats_by_period, out_png, highlight=False):
    """Two-panel figure for one basin: annual WY time-series overlay (left) +
    period-mean bars full/pre-1950/post-1950 (right), all 5 sources."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5.2),
                                   gridspec_kw={"width_ratios": [2.0, 1.0]})
    # left: time series
    for src in SOURCES:
        s = series_by_source.get(src)
        if s is None or s.empty:
            continue
        lw = 2.4 if (highlight and src in ("PRISM_AN", "PRISM_LT")) else 1.6
        ax1.plot(s.index, s.values, color=COLORS[src], lw=lw, marker="o", ms=2.5,
                 label=src, alpha=0.9)
    ax1.axvline(1950, color="#999999", ls="--", lw=0.8)
    ax1.set_xlabel("Water Year", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Annual WY Precipitation (inches)", fontsize=11, fontweight="bold")
    ax1.set_title(f"{loc} - annual precipitation by source", fontsize=12, fontweight="bold")
    ax1.grid(True, axis="y", lw=0.3, alpha=0.5)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.legend(fontsize=9, ncol=3, loc="upper center", framealpha=0.9)
    # right: period-mean bars as % change vs CalSim historical (the 0 reference)
    period_names = [p[0] for p in PERIODS]
    x = np.arange(len(period_names))
    nsrc = len(OTHER_SOURCES)
    width = 0.8 / nsrc
    for j, src in enumerate(OTHER_SOURCES):
        vals = [_pct_vs_hist(stats_by_period[pn][src]["mean"],
                             stats_by_period[pn]["Hist_CalSim"]["mean"]) for pn in period_names]
        ax2.bar(x + (j - (nsrc - 1) / 2) * width, vals, width,
                color=COLORS[src], label=src, edgecolor="black", linewidth=0.3)
    href = ax2.axhline(0, color=COLORS["Hist_CalSim"], lw=1.4, ls="--")
    ax2.set_xticks(x)
    ax2.set_xticklabels(["full\n1922-2018", "pre-1950\n1922-1949", "post-1950\n1950-2018"], fontsize=9)
    ax2.set_ylabel("% difference from CalSim historical", fontsize=11, fontweight="bold")
    ax2.set_title(f"{loc} period means vs CalSim historical", fontsize=12, fontweight="bold")
    ax2.grid(True, axis="y", lw=0.3, alpha=0.5)
    ax2.set_axisbelow(True)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.legend([href], ["CalSim historical (0)"], fontsize=8, loc="best", framealpha=0.9)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_fullmean_bar(locations, full_means, out_png):
    """Grouped bar: full-period mean precip as % change vs CalSim historical (0), per location."""
    fig, ax = plt.subplots(figsize=(13, 5.5))
    x = np.arange(len(locations))
    nsrc = len(OTHER_SOURCES)
    width = 0.8 / nsrc
    for j, src in enumerate(OTHER_SOURCES):
        vals = [_pct_vs_hist(full_means[loc].get(src, np.nan),
                             full_means[loc].get("Hist_CalSim", np.nan)) for loc in locations]
        ax.bar(x + (j - (nsrc - 1) / 2) * width, vals, width,
               color=COLORS[src], label=src, edgecolor="black", linewidth=0.3)
    ax.axhline(0, color=COLORS["Hist_CalSim"], lw=1.4, ls="--", label="CalSim historical (0)")
    ax.set_xticks(x)
    ax.set_xticklabels(locations, fontsize=10, rotation=0)
    ax.set_ylabel("% difference from CalSim historical", fontsize=11, fontweight="bold")
    ax.set_title("Five-way precipitation comparison - full-period mean vs CalSim historical (WY 1922-2018)",
                 fontsize=13, fontweight="bold")
    ax.grid(True, axis="y", lw=0.3, alpha=0.5)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=9, ncol=5, loc="upper right", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_png, dpi=250, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    print("Indexing gridded source directories...", flush=True)
    idx_of = {src: index_dir(DIR_OF[src]) for src in DIR_OF}
    for src, idx in idx_of.items():
        print(f"  {src:11s}: {len(idx)} cells", flush=True)

    locations_df = uhh.read_uhh_locations(LOCS_CSV)
    out_dir = get_module_generated_dir("mod_forcing/climate") / "output" / "precip_5way_comparison"
    out_dir.mkdir(parents=True, exist_ok=True)

    series_by_loc = {}   # loc -> {source -> Series(WY->inches)}
    full_means = {}      # loc -> {source -> full-period mean}
    panel_stats = {}     # loc -> {period -> {source -> stats dict}}
    stats_rows = []
    locations = []

    for _, row in locations_df.iterrows():
        loc = row["location"]
        gi_path = GRIDINFO_DIR / row["grid_info_file"]
        if not gi_path.exists():
            print(f"  WARNING: GridInfo missing for {loc}: {gi_path.name}; skipping")
            continue
        gi_df = uhh.parse_grid_info_file(gi_path)
        print(f"\n{loc} ({row['grid_info_file']}, {len(gi_df)} cells)", flush=True)

        sbs = {}
        # gridded sources
        for src in ("PRISM_AN", "PRISM_LT", "LIVNEH_SPLIT", "LIVNEH_UNSPLIT"):
            s, nc, miss = location_series(gi_df, src, idx_of[src])
            sbs[src] = s
            print(f"  {src:16s}: {nc} cells matched, {miss} missing"
                  + ("" if s is None else f", {len(s)} WYs"), flush=True)
        # historical CalSim from DSS
        try:
            stem = uhh._ppt_filename_stem(loc)
            hist = uhh._historical_wy_totals_from_dss(stem, start_wy=1922, end_wy=2021)
            sbs["Hist_CalSim"] = pd.Series(hist["precip_inches"].values, index=hist["WY"].values)
            print(f"  {'Hist_CalSim':16s}: {len(sbs['Hist_CalSim'])} WYs (DSS Part B={stem})", flush=True)
        except Exception as e:
            sbs["Hist_CalSim"] = None
            print(f"  Hist_CalSim: FAILED ({e})", flush=True)

        series_by_loc[loc] = sbs
        locations.append(loc)

        # per-location period stats (feeds both the table and the figure)
        stats_by_period = {pname: {src: period_stats(sbs.get(src), lo, hi)
                                   for src in SOURCES}
                           for pname, lo, hi in PERIODS}
        panel_stats[loc] = stats_by_period
        full_means[loc] = {src: stats_by_period["full"][src]["mean"] for src in SOURCES}
        for src in SOURCES:
            for pname, _lo, _hi in PERIODS:
                st = stats_by_period[pname][src]
                stats_rows.append({
                    "location": loc, "source": src, "period": pname,
                    "mean_in": round(st["mean"], 2) if not np.isnan(st["mean"]) else np.nan,
                    "min_in": round(st["min"], 2) if not np.isnan(st["min"]) else np.nan,
                    "max_in": round(st["max"], 2) if not np.isnan(st["max"]) else np.nan,
                    "n_WY": st["n"],
                })

        # per-location two-panel figure (time series + period means)
        plot_panel(loc, sbs, stats_by_period, out_dir / f"precip_5way_panel_{loc}.png",
                   highlight=(loc == TRINITY))

    # stats CSV
    stats_df = pd.DataFrame(stats_rows)
    stats_csv = out_dir / "precip_5way_annual_stats.csv"
    stats_df.to_csv(stats_csv, index=False)
    print(f"\n-> {stats_csv}")

    # full-mean grouped bar across all locations
    plot_fullmean_bar(locations, full_means, out_dir / "precip_5way_fullmean_bar.png")
    print(f"-> {out_dir / 'precip_5way_fullmean_bar.png'}")

    # console highlight for Trinity (the issue #78 focus)
    if TRINITY in panel_stats:
        tr = panel_stats[TRINITY]
        print("\n=== Trinity (TR_UHH) mean annual WY precip (inches) ===")
        print(f"  {'source':16s} {'full':>8s} {'pre1950':>8s} {'post1950':>9s}")
        for src in SOURCES:
            print(f"  {src:16s} {tr['full'][src]['mean']:8.2f} "
                  f"{tr['pre1950'][src]['mean']:8.2f} {tr['post1950'][src]['mean']:9.2f}")

    print(f"\nPer-location two-panel figures + table written to:\n  {out_dir}")


if __name__ == "__main__":
    main()
