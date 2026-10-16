"""
Rim-Inflow Skill Evaluation (Gates G3 and G3r)
==============================================
Scores the rim-inflow model (SAC-SMA dPL-CalSim) against CalSim3 next to the VIC model it
replaces, and measures how both respond to the Product A detrending.

G3, skill. The model's historical-unsplit SVs (direct, no bias correction; built by
_1_build_rim_inflow.py) and the raw VIC historical-unsplit run of the v1.0 archive (routed,
before quantile mapping and the anchor mass balance; see VIC's historical run below), each
against CalSim3, monthly, on three windows of water years:

- 1976-1985: held out of the dPL training, the only out-of-sample test
- 1950-2018 less 1976-1985: in-sample
- 1922-1949: diagnostic only; the pre-1950 forcing is too uncertain to judge a model on

G3r, response. Product A scenario 1 minus historical unsplit, by period, for both models:
the change in annual volume (%) and in April-July share (percentage points), for the
Sacramento and San Joaquin four-river groups, the anchors and the arcs. The two forcings share
their precipitation, so the difference is the detrending's temperature signal.

Also the Sacramento four-river annual bias by year class, for the dry-year evidence.

VIC's historical run. The historical WGEN weather has precipitation 10 times too high on 289
grid-cell days (reference/prcp_x10_artifacts.csv; 259 of them in July 1974). Products A and B
and SAC-SMA's historical forcing carry a tenth of those values; v1.0's VIC run on the
historical weather used them as they were. The script reads that run redone with the values
divided by 10 (routed/Historical_Unsplit_x10fix in the v1.0 archive, made by
mod_forcing/vic/x10fix/vic_x10fix.py there), so every month is scored.

For the qmap SVs (aliases and gap arcs) no window is out of sample, since their maps are fitted
on CalSim3 over WY1950-2018, and VIC's series is the arc v1.0 matched to them.

Inputs
------
- the model's historical SVs: utils.paths.get_rim_inflow_outputs("historical")
- the model's arc flows: utils.paths.get_arc_inflows("historical"), get_arc_inflows("A")
- reference/CalSim3_inflow_mapping.csv (anchor sums)
- reference/CalSim3_VIC_name_mapping.csv (CalSim3 SV -> VIC routed series)
- v1.0 archive: mod_forcing/vic/output/routed/{Historical_Unsplit_x10fix, Product_A/1}/CS3_<VIC>_qmo.csv
- CalSim3 baseline DSS: CalSim3/__calsim_sv_default__.dss
- master inventory (Part C)

Outputs
-------
- <generated>/mod_hydrology/rim_inflow/output/_2_skill_evaluation/
  - skill_summary_monthly.csv   per SV and window: KGE, NSE, R2 and PBIAS of SAC and of VIC
  - arc_skill_by_kind.csv       per window and kind of arc: median KGE and median |PBIAS|
  - detrending_response.csv     per series, model and period: volume and Apr-Jul share change
  - sacramento_four_annual.csv  per WY: CalSim3, SAC and VIC volumes, training status, class
  - dry_year_bias.csv           Sacramento four bias by training status and year class

Usage
-----
    python mod_hydrology/rim_inflow/_2_skill_evaluation.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import (get_archive_dir, get_arc_inflows, get_base_dir, get_inventory_dir,
                         get_module_generated_dir, get_rim_inflow_outputs)
from utils.validation_plots import nse, pbias, r2

_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
OUT_DIR = _gen / "output" / "_2_skill_evaluation"
INFLOW_MAP = _SCRIPT_DIR / "reference" / "CalSim3_inflow_mapping.csv"
VIC_MAP = _SCRIPT_DIR / "reference" / "CalSim3_VIC_name_mapping.csv"
VIC_ROUTED = get_archive_dir() / "mod_forcing" / "vic" / "output" / "routed"
VIC_HIST = "Historical_Unsplit_x10fix"     # v1.0's historical run, x10 precipitation corrected
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
INVENTORY_XLSX = get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx"


def wys(a: int, b: int) -> set:
    return set(range(a, b + 1))


HELD_OUT = wys(1976, 1985)
WINDOWS = {
    "WY1976-1985 held out": HELD_OUT,
    "WY1950-2018 less 1976-1985 in-sample": wys(1950, 2018) - HELD_OUT,
    "WY1922-1949 diagnostic": wys(1922, 1949),
}
TRAINED = wys(1950, 2018) - HELD_OUT          # the years dPL-CalSim trains on
NOT_TRAINED = wys(1922, 1949) | HELD_OUT
PERIODS = [(1922, 1935), (1936, 1950), (1951, 1970), (1971, 1990), (1991, 2018)]
GROUPS = {
    "Sacramento four": ["UNIMP_SRBB", "UNIMP_OROV", "UNIMP_YUBA", "UNIMP_FOLS"],
    "San Joaquin four": ["UNIMP_ST", "UNIMP_TU", "UNIMP_ME", "UNIMP_SJ"],
}
APR_JUL = (4, 5, 6, 7)


def kge(obs, sim) -> float:
    """Kling-Gupta efficiency (Gupta et al. 2009), as SAC-SMA computes it."""
    obs, sim = np.asarray(obs, float), np.asarray(sim, float)
    m = np.isfinite(obs) & np.isfinite(sim)
    obs, sim = obs[m], sim[m]
    if obs.size < 2 or obs.mean() == 0 or obs.std() == 0 or sim.std() == 0:
        return np.nan
    r = np.mean((sim - sim.mean()) * (obs - obs.mean())) / (sim.std() * obs.std())
    return 1.0 - np.sqrt((r - 1) ** 2 + (sim.std() / obs.std() - 1) ** 2 + (sim.mean() / obs.mean() - 1) ** 2)


def water_years(index: pd.DatetimeIndex) -> np.ndarray:
    return index.year + (index.month >= 10).astype(int)


def wide_arcs(forcing: str) -> pd.DataFrame:
    d = pd.read_csv(get_arc_inflows(forcing), usecols=["date", "arc", "taf"], parse_dates=["date"])
    return d.pivot(index="date", columns="arc", values="taf")


def anchor_sum(wide: pd.DataFrame, mapping: pd.DataFrame, name: str) -> pd.Series:
    """A sum SV of the mapping, built from the arc table (zero rows count as 0)."""
    method = mapping.at[name, "Method"] if name in mapping.index else "arc"
    if method == "sum":
        parts = [anchor_sum(wide, mapping, x) for x in mapping.at[name, "Source"].split("+")]
        return sum(p for p in parts if p is not None)
    if method == "zero":
        return None
    return wide[name]


def read_vic(sub: str, vic_names) -> pd.DataFrame:
    """Raw VIC routed series of the v1.0 archive, month-end indexed, by VIC name."""
    if not (VIC_ROUTED / sub).is_dir():
        raise SystemExit(f"{VIC_ROUTED / sub} is missing")
    out = {}
    for v in sorted(set(vic_names)):
        f = VIC_ROUTED / sub / f"CS3_{v}_qmo.csv"
        if f.exists():
            d = pd.read_csv(f, header=None, names=["date", "value"], parse_dates=["date"])
            out[v] = pd.Series(d["value"].to_numpy(float),
                               index=d["date"] + pd.offsets.MonthEnd(0))
    return pd.DataFrame(out)


def read_calsim3(names) -> pd.DataFrame:
    inv = pd.read_excel(INVENTORY_XLSX, sheet_name="MASTER")
    b, c = inv.columns[2], inv.columns[3]
    part_c = {str(x).strip().upper(): str(y).strip().upper() for x, y in zip(inv[b], inv[c])}
    keys = {(n, part_c[n]) for n in names if n in part_c}
    with dss_io.open_dss(str(DSS_FILE), version=6, catalog_flag=True) as dss:
        got = dss_io.read_monthly_series(dss, keys, "1921-10-31", "2018-09-30")
    return pd.DataFrame({k[0]: s for k, s in got.items()})


def skill_rows(name, method, obs, sac, vic):
    rows = []
    wy = water_years(obs.index)
    for label, years in WINDOWS.items():
        m = np.isin(wy, list(years))
        o = obs[m]
        row = {"CalSim": name, "Method": method, "window": label, "n_months": int(o.notna().sum())}
        for tag, sim in (("SAC", sac), ("VIC", vic)):
            s = sim.reindex(o.index) if sim is not None else pd.Series(np.nan, index=o.index)
            row[f"{tag}_KGE"] = kge(o, s)
            row[f"{tag}_NSE"] = nse(o, s)
            row[f"{tag}_R2"] = r2(o, s)
            row[f"{tag}_PBIAS"] = pbias(o, s)
        rows.append(row)
    return rows


def response(hist: pd.Series, prod: pd.Series) -> list:
    """Product A minus historical, per period: volume change (%) and Apr-Jul share change (pp)."""
    out = []
    for a, b in PERIODS:
        vals = {}
        for tag, s in (("H", hist), ("A", prod)):
            s = s[np.isin(water_years(s.index), list(wys(a, b)))]
            vals[tag] = (s.sum(), s[s.index.month.isin(APR_JUL)].sum())
        (vh, ajh), (va, aja) = vals["H"], vals["A"]
        out.append({"period": f"WY{a}-{b}", "volume_change_pct": 100 * (va / vh - 1),
                    "apr_jul_share_change_pp": 100 * (aja / va - ajh / vh)})
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping = pd.read_csv(INFLOW_MAP, keep_default_na=False).set_index("CS3_Inflow")
    vic_map = pd.read_csv(VIC_MAP).dropna().set_index("CS3_Inflow")["VIC_Inflow"]

    ts = pd.read_csv(get_rim_inflow_outputs("historical")["ts"])
    ts["date"] = pd.to_datetime(dict(year=ts["Year"], month=ts["Month"], day=1)) + pd.offsets.MonthEnd(0)
    sac = ts.pivot(index="date", columns="CalSim", values="qmap_postAdj")
    names = list(sac.columns)
    cs3 = read_calsim3(names)
    vic_h = read_vic(VIC_HIST, vic_map.reindex(names).dropna())
    print(f"{len(names)} SVs; CalSim3 {cs3.shape[1]}; VIC raw {vic_h.shape[1]} series ({VIC_HIST})")

    # ---- G3: skill per SV and window ----------------------------------------
    rows = []
    for n in names:
        if n not in cs3:
            continue
        v = vic_h[vic_map[n]] if n in vic_map.index and vic_map[n] in vic_h else None
        rows += skill_rows(n, mapping.at[n, "Method"], cs3[n], sac[n], v)
    skill = pd.DataFrame(rows)
    skill.to_csv(OUT_DIR / "skill_summary_monthly.csv", index=False, float_format="%.4f")

    kinds = (pd.read_csv(get_arc_inflows("historical"), usecols=["arc", "kind"])
             .drop_duplicates("arc").set_index("arc")["kind"])
    arcs = skill[skill["Method"] == "arc"].assign(kind=lambda d: d["CalSim"].map(kinds))
    summary = []
    for (window, kind), g in pd.concat([arcs, arcs.assign(kind="all rim arcs")]).groupby(["window", "kind"]):
        summary.append({"window": window, "kind": kind, "n": len(g),
                        "SAC_median_KGE": g["SAC_KGE"].median(), "VIC_median_KGE": g["VIC_KGE"].median(),
                        "SAC_median_abs_PBIAS": g["SAC_PBIAS"].abs().median(),
                        "VIC_median_abs_PBIAS": g["VIC_PBIAS"].abs().median()})
    by_kind = pd.DataFrame(summary)
    by_kind.to_csv(OUT_DIR / "arc_skill_by_kind.csv", index=False, float_format="%.4f")

    # ---- G3r: detrending response ---------------------------------------------
    arcs_h, arcs_a = wide_arcs("historical"), wide_arcs("A")
    anchors = [n for n in mapping.index if mapping.at[n, "Method"] == "sum"
               and n.startswith("UNIMP_") and not n.endswith("_UHH")]
    vic_a = read_vic("Product_A/1", vic_map.reindex(names).dropna())
    series = {}
    for n in anchors + list(kinds.index):
        sac_pair = (anchor_sum(arcs_h, mapping, n), anchor_sum(arcs_a, mapping, n))
        vn = vic_map.get(n)
        vic_pair = (vic_h[vn], vic_a[vn]) if vn in vic_h and vn in vic_a else None
        kind = "anchor" if n in anchors else ("valley" if kinds[n] == "valley" else "arc")
        series[n] = (kind, sac_pair, vic_pair)
    for g, members in GROUPS.items():
        sac_pair = tuple(sum(series[m][1][i] for m in members) for i in (0, 1))
        vic_pair = tuple(sum(series[m][2][i] for m in members) for i in (0, 1))
        series[g] = ("group", sac_pair, vic_pair)
    rows = []
    for n, (kind, sac_pair, vic_pair) in series.items():
        for model, pair in (("SAC", sac_pair), ("VIC", vic_pair)):
            if pair is not None:
                rows += [{"series": n, "kind": kind, "model": model, **r} for r in response(*pair)]
    resp = pd.DataFrame(rows)
    resp.to_csv(OUT_DIR / "detrending_response.csv", index=False, float_format="%.3f")

    # ---- Sacramento four by year class --------------------------------------
    four = GROUPS["Sacramento four"]
    ann = pd.DataFrame({
        "CalSim3": cs3[four].sum(axis=1, min_count=4),
        "SAC": sac[four].sum(axis=1),
        "VIC_raw": series["Sacramento four"][2][0],
    }).dropna()
    ann = ann.groupby(water_years(ann.index)).sum()
    ann.index.name = "WY"
    ann = ann.loc[1922:2018]
    ann["status"] = np.where(ann.index.isin(list(TRAINED)), "dPL training years",
                             np.where(ann.index.isin(list(NOT_TRAINED)), "not trained on", "other"))
    ann["class"] = "middle"
    for _, g in ann.groupby("status"):
        lo, hi = g["CalSim3"].quantile([0.2, 0.8])
        ann.loc[g.index[g["CalSim3"] <= lo], "class"] = "driest 20%"
        ann.loc[g.index[g["CalSim3"] >= hi], "class"] = "wettest 20%"
    ann.to_csv(OUT_DIR / "sacramento_four_annual.csv", float_format="%.1f")
    dry = (ann[ann["status"] != "other"].groupby(["status", "class"])[["CalSim3", "SAC", "VIC_raw"]].sum())
    dry["SAC_bias_pct"] = 100 * (dry["SAC"] / dry["CalSim3"] - 1)
    dry["VIC_raw_bias_pct"] = 100 * (dry["VIC_raw"] / dry["CalSim3"] - 1)
    dry.to_csv(OUT_DIR / "dry_year_bias.csv", float_format="%.2f")

    # ---- report ---------------------------------------------------------------
    pd.set_option("display.width", 160)
    anc = skill[skill["CalSim"].isin(anchors)].pivot(index="CalSim", columns="window",
                                                     values=["SAC_KGE", "VIC_KGE", "SAC_PBIAS", "VIC_PBIAS"])
    print("\nAnchors (KGE, PBIAS %), SAC vs raw VIC against CalSim3:")
    print(anc.round(2).to_string())
    print("\nArcs, median by window and kind:")
    print(by_kind.round(3).to_string(index=False))
    print("\nDetrending response, groups:")
    print(resp[resp["kind"] == "group"].round(2).to_string(index=False))
    print("\nSacramento four, bias by year class:")
    print(dry[["SAC_bias_pct", "VIC_raw_bias_pct"]].round(1).to_string())
    print(f"\nWrote {OUT_DIR}")


if __name__ == "__main__":
    main()
