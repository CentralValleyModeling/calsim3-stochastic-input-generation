"""
Build the Rim-Inflow SVs from the Rim-Inflow Model
==================================================
Builds every CalSim3 rim-inflow SV from the monthly arc flows of the rim-inflow model
(mod_forcing/inflows, the model the config names), with no bias correction. Each SV has a
method in reference/CalSim3_inflow_mapping.csv (CS3_Inflow, Source, Method):

- arc  : the 196 arcs the model simulates, as they are.
- sum  : the UNIMP anchors, as the sum of their arcs (UNIMP_SRBB adds the Sacramento valley
         node I_SRBB_VAL), and their _UHH twins, equal to the anchor as in CalSim3. The
         anchor arcs are those of RimInflowAnchor.xlsx; a single-arc system sums one arc.
         The alias I422 equals I_LOSVQ in every month of CalSim3, so it copies the model's
         I_LOSVQ; a quantile map would bend that identity in its tails.
- qmap : the other aliases and the gap arcs, by pass-through quantile mapping. The map is
         fitted from the CalSim3 source series to the CalSim3 series over WY1950-2018 and
         applied to the model's source series, so the SV carries the model's error like the
         arcs it comes from. A source that is a sum is fitted on the CalSim3 sum of the same
         arcs (the series the model is trained to), not on CalSim3's UNIMP series.
- zero : I_RUB002, zero in CalSim3.
- wyt  : I_JBP006, a San Joaquin year-type average; mod_other/miscellaneous builds it once
         the year types exist.
- none : no series (the inventory marks these Missing).

Products
--------
- A          : Product A (WGEN scenario 1), WY1972-2018, the compiler window
- historical : the historical-unsplit run, WY1916-2018, for evaluation; not delivered

Product B arrives in phase P3.

Inputs
------
- the model's arc flows (utils.paths.get_arc_inflows), only from a run of the configured
  model at the pinned commit (its run_manifest.json; utils.paths.require_pinned_run)
- reference/CalSim3_inflow_mapping.csv
- CalSim3 baseline DSS: CalSim3/__calsim_sv_default__.dss (qmap fits)
- master inventory: the rim-inflow SVs and their Part C

Outputs
-------
- <generated>/mod_hydrology/rim_inflow/output/_1_build_rim_inflow/<Product_A/1|Historical_Unsplit>/
  (utils.paths.get_rim_inflow_outputs; the folder is deleted first)
  - calsim_qmap_validation_TS.csv  (CalSim, Matched_inflow, Year, Month, qmap_postAdj);
                                   Matched_inflow is the source series, or the method for a
                                   sum of several series and for zero
  - qmap_fits.csv                  per qmap SV: source, fit window, mean annual volumes of the
                                   SV and its source in CalSim3 (fit window) and in the product,
                                   and their ratios
  - _product_a_validation/_riminflow_productA_1972_2018.csv  (A only; Part B, Part C, Year,
                                   Month, Value, for the SV compiler)
  - run_manifest.json              the manifest of the model run the SVs come from, copied
                                   from the arc flows; the absorb fits check it (utils.qmap_fit)

Usage
-----
    python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product A
    python mod_hydrology/rim_inflow/_1_build_rim_inflow.py --product historical
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import (INFLOW_PROVENANCE, get_arc_inflows, get_base_dir, get_inventory_dir,
                         get_rim_inflow_outputs, remove_tree, require_pinned_run)
from utils.quantile_mapping import qmap_single

_SCRIPT_DIR = Path(__file__).resolve().parent
MAPPING_CSV = _SCRIPT_DIR / "reference" / "CalSim3_inflow_mapping.csv"
DSS_FILE = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
INVENTORY_XLSX = get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx"

METHODS = ("arc", "sum", "qmap", "zero", "wyt", "none")
FIT_WY = (1950, 2018)
PRODUCT_WY = {"A": (1972, 2018), "historical": (1916, 2018)}


def wy_index(wy: tuple[int, int]) -> pd.DatetimeIndex:
    """Month-end dates of water years wy[0]..wy[1]."""
    return pd.date_range(f"{wy[0] - 1}-10-31", f"{wy[1]}-09-30", freq="ME")


def sources(expr: str) -> list[str]:
    return [s for s in str(expr).split("+") if s]


def read_mapping() -> pd.DataFrame:
    m = pd.read_csv(MAPPING_CSV, keep_default_na=False)
    bad = sorted(set(m["Method"]) - set(METHODS))
    if bad:
        raise SystemExit(f"{MAPPING_CSV.name}: unknown methods {bad}")
    dup = m.loc[m["CS3_Inflow"].duplicated(), "CS3_Inflow"].tolist()
    if dup:
        raise SystemExit(f"{MAPPING_CSV.name}: duplicated SVs {dup}")
    return m.set_index("CS3_Inflow")


def read_inventory_part_c() -> dict:
    """Rim-inflow SV (Part B) -> Part C, from the master inventory."""
    inv = pd.read_excel(INVENTORY_XLSX, sheet_name="MASTER")
    b, c, cat = inv.columns[2], inv.columns[3], inv.columns[8]
    rim = inv[inv[cat].astype(str).str.strip().str.lower() == "rim inflow"]
    return {str(pb).strip().upper().replace(" ", "_"): str(pc).strip().upper().replace(" ", "_")
            for pb, pc in zip(rim[b], rim[c])}


class Resolver:
    """Builds a named series from the mapping on one side (the model or CalSim3): a sum adds
    its sources, a zero row is 0, and any other name is a leaf read by ``leaf``."""

    def __init__(self, mapping: pd.DataFrame, index: pd.DatetimeIndex, leaf):
        self.mapping, self.index, self.leaf, self.cache = mapping, index, leaf, {}

    def __call__(self, name: str) -> pd.Series:
        if name not in self.cache:
            method = self.mapping.at[name, "Method"] if name in self.mapping.index else "arc"
            if method == "arc":
                s = self.leaf(name).reindex(self.index)
            elif method == "sum":
                s = sum(self(x) for x in sources(self.mapping.at[name, "Source"]))
            elif method == "zero":
                s = pd.Series(0.0, index=self.index)
            else:
                raise SystemExit(f"{name}: a {method} SV cannot be built here or used as a source")
            if s.isna().any():
                raise SystemExit(f"{name}: missing values in {s[s.isna()].index[[0, -1]].tolist()}")
            self.cache[name] = s.rename(name)
        return self.cache[name]

    def leaves(self, name: str) -> set:
        method = self.mapping.at[name, "Method"] if name in self.mapping.index else "arc"
        if method == "sum":
            return set().union(*(self.leaves(x) for x in sources(self.mapping.at[name, "Source"])))
        return set() if method == "zero" else {name}


def read_calsim3(names: set, part_c: dict) -> dict:
    """CalSim3 series by Part B (Part C from the inventory), month-end indexed."""
    missing_c = sorted(n for n in names if n not in part_c)
    if missing_c:
        raise SystemExit(f"not rim-inflow SVs in the inventory: {missing_c}")
    keys = {(n, part_c[n]) for n in names}
    with dss_io.open_dss(str(DSS_FILE), version=6, catalog_flag=True) as dss:
        got = dss_io.read_monthly_series(dss, keys, "1921-10-31", "2021-09-30")
    absent = sorted(k for k in keys if k not in got)
    if absent:
        raise SystemExit(f"not in {DSS_FILE.name}: {absent}")
    return {b: s for (b, _), s in got.items()}


def to_frame(values: pd.Series) -> pd.DataFrame:
    """Month-end series -> the year, month, value frame qmap_single takes."""
    return pd.DataFrame({"year": values.index.year, "month": values.index.month,
                         "value": values.to_numpy(float)})


def build(product: str, mapping: pd.DataFrame, part_c: dict):
    arcs = pd.read_csv(get_arc_inflows(product), usecols=["date", "arc", "taf"], parse_dates=["date"])
    wide = arcs.pivot(index="date", columns="arc", values="taf")
    out_index = wy_index(PRODUCT_WY[product])

    def model_leaf(name):
        if name not in wide.columns:
            raise SystemExit(f"{name}: not an arc of the rim-inflow model")
        return wide[name]

    model = Resolver(mapping, out_index, model_leaf)
    built = {name: model(name) for name in mapping.index
             if mapping.at[name, "Method"] in ("arc", "sum", "zero")}

    qrows = mapping[mapping["Method"] == "qmap"]
    fit_index = wy_index(FIT_WY)
    cs3_names = set(qrows.index)
    for src in qrows["Source"]:
        cs3_names |= model.leaves(src)
    cs3 = read_calsim3(cs3_names, part_c)
    calsim = Resolver(mapping, fit_index, lambda n: cs3[n])
    fits = []
    for name, row in qrows.iterrows():
        src = row["Source"]
        basis_hist, target = calsim(src), cs3[name].reindex(fit_index)
        if target.isna().any():
            raise SystemExit(f"{name}: CalSim3 series has gaps in WY{FIT_WY[0]}-{FIT_WY[1]}")
        basis_sim = model(src)
        q = qmap_single(to_frame(basis_sim), to_frame(basis_hist), to_frame(target))
        built[name] = pd.Series(q["quantile_mapped_value"].to_numpy(float), index=out_index, name=name)
        n_fit, n_out = len(fit_index) / 12, len(out_index) / 12
        fits.append({
            "CalSim": name, "Source": src, "fit_wy": f"{FIT_WY[0]}-{FIT_WY[1]}",
            "cs3_taf_yr": target.sum() / n_fit, "cs3_source_taf_yr": basis_hist.sum() / n_fit,
            "cs3_ratio": target.sum() / basis_hist.sum(),
            "product_taf_yr": built[name].sum() / n_out,
            "product_source_taf_yr": basis_sim.sum() / n_out,
            "product_ratio": built[name].sum() / basis_sim.sum(),
        })
    return built, pd.DataFrame(fits)


def main():
    ap = argparse.ArgumentParser(description="Build the rim-inflow SVs from the rim-inflow model.")
    ap.add_argument("--product", choices=list(PRODUCT_WY), required=True)   # B: phase P3
    args = ap.parse_args()

    mapping = read_mapping()
    part_c = read_inventory_part_c()
    extra, absent = sorted(set(mapping.index) - set(part_c)), sorted(set(part_c) - set(mapping.index))
    if extra or absent:
        raise SystemExit(f"{MAPPING_CSV.name} vs the inventory's rim-inflow SVs: "
                         f"not in the inventory {extra}; not in the mapping {absent}")

    manifest = require_pinned_run(get_arc_inflows(args.product).parent)
    built, fits = build(args.product, mapping, part_c)

    paths = get_rim_inflow_outputs(args.product)
    remove_tree(paths["dir"])
    paths["dir"].mkdir(parents=True)
    (paths["dir"] / INFLOW_PROVENANCE).write_text(json.dumps(manifest, indent=1))

    rows = []
    for name in mapping.index:          # mapping order
        if name not in built:
            continue
        method, src = mapping.at[name, "Method"], mapping.at[name, "Source"]
        s = built[name]
        single = method in ("arc", "qmap") or (method == "sum" and "+" not in src)
        rows.append(pd.DataFrame({
            "CalSim": name, "Matched_inflow": src if single else method,
            "Year": s.index.year, "Month": s.index.month, "qmap_postAdj": s.to_numpy(float)}))
    ts = pd.concat(rows, ignore_index=True)
    ts.to_csv(paths["ts"], index=False)
    fits.to_csv(paths["dir"] / "qmap_fits.csv", index=False, float_format="%.4f")
    print(f"{ts['CalSim'].nunique()} SVs, WY{PRODUCT_WY[args.product][0]}-{PRODUCT_WY[args.product][1]}: {paths['ts']}")
    print(fits[["CalSim", "Source", "cs3_ratio", "product_ratio"]].to_string(index=False))

    if args.product == "A":
        sv = pd.DataFrame({"Part B": ts["CalSim"], "Part C": ts["CalSim"].map(part_c),
                           "Year": ts["Year"], "Month": ts["Month"], "Value": ts["qmap_postAdj"]})
        paths["sv_dir"].mkdir(parents=True)
        sv.sort_values(["Part B", "Year", "Month"]).to_csv(paths["sv"], index=False)
        print(f"SV format: {paths['sv']}")

    skipped = mapping[~mapping.index.isin(built)]
    print(f"Not built here: {skipped['Method'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
