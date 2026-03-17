# %% Quantile-mapping: train on Product A (1921-10–2018-12) and
# %% apply to Product B VIC routed flows
#
# 
#   1) Read all Product-B time series (01..10 / n01..n10)
#   2) Concatenate them in numeric order into one long simulation time series
#   3) Run qmap_single() ONCE on that combined simulation timeseries
#   4) Split mapped values back to each time series
#   5) Write one output per time series, keeping the original suffix
#      e.g. *_qmo_n01.csv -> <CalSim>_*_qmo_n01.csv

import os
import re
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from pydsstools.heclib.dss import HecDss
from pandas.tseries.offsets import MonthEnd

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_inventory_dir, get_module_generated_dir
from utils.quantile_mapping import qmap_single

_SCRIPT_DIR = Path(__file__).resolve().parent
_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_vic_gen = get_module_generated_dir("mod_hydrology/vic")

# ==== CONFIG =================================================================
# Historical training data (Product A)
master_xlsx   = str(get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx")
dss_file      = str(get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss")
vic_hist_dir  = str(_vic_gen / "output" / "routed" / "Product_A" / "1")
vic_end_year  = 2018

# Simulated to be adjusted (Product B)
vic_sim_dir   = str(_vic_gen / "output" / "routed" / "Product_B" / "1")

BASE_OUT_DIR  = str(_gen / "_3_qmap_product_b")
OUT_TS_DIR    = BASE_OUT_DIR
os.makedirs(OUT_TS_DIR, exist_ok=True)

ANCHOR_XLSX  = str(_SCRIPT_DIR / "reference" / "RimInflowAnchor.xlsx")

# ==== BASIC HELPERS ==========================================================
def ser_to_df(s: pd.Series) -> pd.DataFrame:
    """Convert monthly Series (month-end index) to DataFrame(year,month,value)."""
    return pd.DataFrame(
        {
            "year":  s.index.year.astype(int),
            "month": s.index.month.astype(int),
            "value": s.values,
        }
    )


def read_master_pairs():
    df_master  = pd.read_excel(master_xlsx, sheet_name="MASTER")
    col_C, col_I = df_master.columns[2], df_master.columns[8]

    # Filter for "Rim Inflow"
    df_inflow    = df_master[df_master[col_I].astype(str).str.strip().str.lower() == "rim inflow"]
    calsim_inflows = df_inflow[col_C].dropna().unique().tolist()

    # CalSim ↔ VIC matched pairs (from correlation CSV)
    r2_csv_path = str(_gen / "_1_calc_correlations" / "r2_calsim_vs_vic.csv")
    df_r2 = pd.read_csv(r2_csv_path)
    df_pairs = df_r2[["DSS Inflow", "VIC Inflow"]].copy()
    df_pairs = df_pairs.rename(columns={"DSS Inflow": "CalSim_Inflow", "VIC Inflow": "VIC_Inflow"})
    df_pairs = df_pairs.dropna()

    # Preserve CSV order of CalSim inflows for outputs
    master_order = df_pairs["CalSim_Inflow"].tolist()
    return df_pairs, calsim_inflows, master_order


def excel_to_partB(name: str) -> str:
    return name.upper().replace(" ", "_")


def read_calsim_monthly_multi(dssfile, strList):
    """Read CalSim monthly inflows from DSS into wide DataFrame."""
    full_idx = pd.date_range("1915-01-31", f"{vic_end_year}-12-31", freq="M")
    with HecDss.Open(dssfile, version=6, catalog_flag=True) as dss:
        paths   = dss.getPathnameList("/*/*/*/*/1MON/*")
        bucket  = {}
        for p in paths:
            b = p.strip("/").split("/")[1].upper()
            bucket.setdefault(b, []).append(p)

        data = {}
        for inflow in strList:
            b = excel_to_partB(inflow)
            if b not in bucket:
                continue
            master = pd.Series(index=full_idx, dtype=float)
            for p in sorted(bucket[b], key=lambda x: x.split("/")[3]):
                ts   = dss.read_ts(p, trim_missing=True)
                vals = np.where(ts.values <= -900, np.nan, ts.values)
                idx  = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")
                master.update(pd.Series(vals, index=idx))
            if master.notna().any():
                data[inflow] = master
    df = pd.DataFrame(data)
    df.index.name = "date"
    return df


def load_vic_hist_dir(vic_path: str) -> pd.DataFrame:
    """
    Load historical VIC (Product A) CSVs:
    CS3_<VIC>_qmo.csv with [date,value].
    """
    data = {}
    for file in os.listdir(vic_path):
        if not (file.startswith("CS3_") and file.endswith("_qmo.csv")):
            continue
        name  = file[len("CS3_"):-len("_qmo.csv")]
        fpath = os.path.join(vic_path, file)
        df    = pd.read_csv(fpath, header=None)
        df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        ser = pd.Series(df.iloc[:, 1].values, index=df.iloc[:, 0].values, name=name)

        # normalize to month-end
        ser.index = pd.to_datetime(
            pd.to_datetime(ser.index).to_period("M").to_timestamp("M")
        )
        data[name] = ser

    out = pd.DataFrame(data)
    out.index.name = "date"
    return out


def timeseries_sort_key(label: str):
    """
    Numeric ordering for time series labels like:
      01, 02, ..., 10
      n01, n02, ..., n10
    Falls back to string ordering if no digits are present.
    """
    s = str(label)
    m = re.search(r"(\d+)", s)
    if m:
        return (int(m.group(1)), s)
    return (10**9, s)


def find_timeseries_in_dir(sim_dir: str):
    """
    Detect time series labels from filenames like:
      CS3_<VIC>_qmo_n01.csv -> time series 'n01'
      CS3_<VIC>_qmo_01.csv  -> time series '01'
    """
    timeseries_list = set()
    for file in os.listdir(sim_dir):
        if not (file.startswith("CS3_") and file.endswith(".csv")):
            continue
        if "_qmo_" not in file:
            continue
        _, tail = file.split("_qmo_", 1)
        ts = os.path.splitext(tail)[0]  # drop .csv
        timeseries_list.add(ts)
    return sorted(timeseries_list, key=timeseries_sort_key)


def load_vic_sim_series(vic_name: str, sim_dir: str, ts: str):
    """
    Load a VIC series (Product B) for a VIC inflow.
    Expects files like: CS3_<VIC>_qmo_<ts>.csv with columns [Year, Month, Value].
    Returns (Series, filename) or (None, None) if not found.
    """
    fname = f"CS3_{vic_name}_qmo_{ts}.csv"
    fpath = os.path.join(sim_dir, fname)
    if not os.path.exists(fpath):
        return None, None

    df = pd.read_csv(fpath, header=None)

    years  = df.iloc[:, 0].astype(int)
    months = df.iloc[:, 1].astype(int)
    vals   = df.iloc[:, 2].astype(float).values

    # First day of month, then shift to month-end
    dt  = pd.to_datetime(years.astype(str) + "-" + months.astype(str) + "-01", errors="coerce")
    idx = dt + MonthEnd(0)

    ser = pd.Series(vals, index=idx, name=vic_name)
    return ser, fname


def load_vic_sim_all_timeseries(vic_name: str, sim_dir: str, timeseries_list: list[str]) -> pd.DataFrame:
    """
    Load ALL Product-B time series files for one VIC inflow, concatenate them in the
    supplied time series order, and keep enough metadata to split them back out later.

    Returns columns:
      timeseries, input_filename, year, month, vic_val
    """
    blocks = []
    for ts in timeseries_list:
        sim_ser, sim_fname = load_vic_sim_series(vic_name, sim_dir, ts)
        if sim_ser is None:
            continue

        block = ser_to_df(sim_ser).rename(columns={"value": "vic_val"})
        block["timeseries"] = ts
        block["input_filename"] = sim_fname
        blocks.append(block)

    if not blocks:
        return pd.DataFrame(columns=["timeseries", "input_filename", "year", "month", "vic_val"])

    out = pd.concat(blocks, ignore_index=True)
    out["timeseries"] = pd.Categorical(out["timeseries"], categories=timeseries_list, ordered=True)
    out = out.sort_values(["timeseries", "year", "month"]).reset_index(drop=True)
    return out


def build_output_filename(calsim_name: str, input_filename: str) -> str:
    """
    Replace the leading 'CS3' in the Product B filename with the CalSim inflow name.
    CS3_8RI_DPR_I_qmo_n01.csv -> <CalSim>_8RI_DPR_I_qmo_n01.csv
    """
    if not input_filename:
        return f"{calsim_name}.csv"
    if "_" in input_filename:
        _, rest = input_filename.split("_", 1)
        return f"{calsim_name}_{rest}"
    return f"{calsim_name}_{input_filename}"


# ==== ANCHOR / MASS BALANCE HELPERS ==========================================
def build_anchor_map(all_calsim_inflows):
    """
    Build full anchor/tributary map once (for all CalSim inflows).
    We'll filter per time series later.
    """
    w = pd.read_excel(ANCHOR_XLSX)
    a = w.columns[0]
    anchor_map = (
        w.melt(id_vars=[a], value_vars=w.columns[1:], var_name="_", value_name="Trib_CalSim")
         .drop(columns="_")
         .rename(columns={a: "Anchor_CalSim"})
         .dropna(subset=["Trib_CalSim"])
    )
    anchor_map["Anchor_CalSim"] = anchor_map["Anchor_CalSim"].astype(str).str.strip()
    anchor_map["Trib_CalSim"]   = anchor_map["Trib_CalSim"].astype(str).str.strip()
    anchor_map = anchor_map.loc[
        (anchor_map["Trib_CalSim"] != "") &
        (anchor_map["Anchor_CalSim"].isin(all_calsim_inflows)) &
        (anchor_map["Trib_CalSim"].isin(all_calsim_inflows)),
        ["Anchor_CalSim", "Trib_CalSim"],
    ].drop_duplicates()
    return anchor_map


def enforce_anchor_mass_balance(qdf: pd.DataFrame, mapping_cal: pd.DataFrame):
    """
    Mass-balance adjustment for tributaries under each anchor, per WY-month.
    qdf columns: Series, Year, Month, WY, Flow_QM
    """
    if mapping_cal.empty or qdf.empty:
        qdf = qdf.copy()
        qdf["Flow_QM_Adj"] = qdf["Flow_QM"]
        return qdf

    df = qdf.copy()
    anchors = set(mapping_cal["Anchor_CalSim"].unique())

    anc = (
        df[df["Series"].isin(anchors)]
        [["Series", "WY", "Month", "Flow_QM"]]
        .rename(columns={"Series": "Anchor_CalSim", "Flow_QM": "Anchor_QM"})
    )

    trib = df.merge(mapping_cal, left_on="Series", right_on="Trib_CalSim", how="inner")

    tsum = (
        trib.groupby(["Anchor_CalSim", "WY", "Month"], as_index=False)["Flow_QM"]
        .sum()
        .rename(columns={"Flow_QM": "Sum_Trib_QM"})
    )

    mb = (
        trib.merge(tsum, on=["Anchor_CalSim", "WY", "Month"], how="left")
            .merge(anc,  on=["Anchor_CalSim", "WY", "Month"], how="left")
    )

    delta = (mb["Anchor_QM"] - mb["Sum_Trib_QM"]).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        share = mb["Flow_QM"] / mb["Sum_Trib_QM"]
        mb["Flow_QM_Adj"] = np.where(
            mb["Sum_Trib_QM"].abs() > 0,
            mb["Flow_QM"] + delta * share,
            mb["Flow_QM"],
        )

    adj_tbl = (
        mb[["Trib_CalSim", "Year", "Month", "Flow_QM_Adj"]]
        .rename(columns={"Trib_CalSim": "Series"})
    )

    out = df.merge(adj_tbl, on=["Series", "Year", "Month"], how="left")
    out["Flow_QM_Adj"] = out["Flow_QM_Adj"].fillna(out["Flow_QM"])
    return out


# ==== MAIN WORKFLOW ==========================================================
def main():
    # --- 1. Static data (done once) -----------------------------------------
    df_pairs, calsim_inflows, master_order = read_master_pairs()

    df_vic_hist   = load_vic_hist_dir(vic_hist_dir)
    df_calsim_all = read_calsim_monthly_multi(dss_file, calsim_inflows)

    # Optional: Save df_calsim_all for inspection
    df_calsim_all.to_csv(os.path.join(BASE_OUT_DIR, "df_calsim_all.csv"))

    # Precompute training data per (CalSim, VIC) pair, once
    training = {}  # key: (cal, vic) -> (b_train_df, t_train_df)
    for _, row in df_pairs.iterrows():
        cal = row["CalSim_Inflow"]
        vic = row["VIC_Inflow"]

        if cal not in df_calsim_all.columns or vic not in df_vic_hist.columns:
            continue

        joined = pd.concat(
            [df_vic_hist[vic], df_calsim_all[cal]],
            axis=1,
            join="inner",
        ).dropna()
        if joined.empty:
            continue

        joined.columns = ["basis", "target"]

        # Full Product A period for training
        train = joined.loc["1921-10-01":"2018-12-31"]
        b_train = train["basis"]
        t_train = train["target"]
        if b_train.empty or t_train.empty:
            continue

        training[(cal, vic)] = (ser_to_df(b_train), ser_to_df(t_train))

    if not training:
        print("No CalSim/VIC training pairs available.")
        return

    # Build full anchor map once
    anchor_map_full = build_anchor_map(calsim_inflows)

    # Detect Product B time series files (e.g. 01..10 or n01..n10)
    timeseries_list = find_timeseries_in_dir(vic_sim_dir)
    if not timeseries_list:
        print("No Product B time series files found – check vic_sim_dir.")
        return

    print("Found Product B time series:", ", ".join(timeseries_list))

    # --- 2. Precompute qmap on COMBINED time series -----------------------------
    # For each (CalSim, VIC) pair:
    #   - read all Product-B time series in order
    #   - concatenate into one long simulation serie
    #   - run qmap_single ONCE
    #   - store mapped values with time series labels so we can split later
    qmap_cache = {}  # key: (cal, vic) -> combined mapped DataFrame

    for (cal, vic), (b_train_df, t_train_df) in training.items():
        sim_all = load_vic_sim_all_timeseries(vic, vic_sim_dir, timeseries_list)
        if sim_all.empty:
            continue

        simulation_df = sim_all[["year", "month", "vic_val"]].rename(columns={"vic_val": "value"})

        qmap = qmap_single(
            simulation_df,      # combined Product B VIC series (all time series stacked)
            b_train_df,   # train basis: Product A VIC
            t_train_df,   # train target: CalSim
        ).copy()

        if "quantile_mapped_value" not in qmap.columns:
            raise KeyError(
                "qmap_single output is missing 'quantile_mapped_value'. "
                f"Available columns: {list(qmap.columns)}"
            )
        if len(qmap) != len(sim_all):
            raise ValueError(
                f"qmap_single returned {len(qmap)} rows, but combined simulation series has {len(sim_all)} rows "
                f"for pair (CalSim={cal}, VIC={vic})."
            )

        sim_all = sim_all.copy()
        sim_all["qmap_preAdj"] = qmap["quantile_mapped_value"].to_numpy(float)
        qmap_cache[(cal, vic)] = sim_all

    if not qmap_cache:
        print("No Product B time series were available for quantile mapping.")
        return

    # --- 3. Split mapped results back to each time series and write outputs ------
    for ts in timeseries_list:
        print(f"\n=== Processing time series {ts} ===")

        per_pair_dfs = []
        input_fname_by_cal = {}

        for (cal, vic), sim_all in qmap_cache.items():
            block = sim_all[sim_all["timeseries"] == ts].copy()
            if block.empty:
                continue

            input_fname_by_cal[cal] = block["input_filename"].iloc[0]

            pair_df = pd.DataFrame(
                {
                    "CalSim":         cal,
                    "Matched_inflow": vic,
                    "Year":           block["year"].astype(int).to_numpy(),
                    "Month":          block["month"].astype(int).to_numpy(),
                    "vic_val":        block["vic_val"].astype(float).to_numpy(),
                    "qmap_preAdj":    block["qmap_preAdj"].astype(float).to_numpy(),
                }
            )
            per_pair_dfs.append(pair_df)

        if not per_pair_dfs:
            print(f"No CalSim/VIC pairs processed for time series {ts}.")
            continue

        detail_df = pd.concat(per_pair_dfs, ignore_index=True)
        detail_df["CalSim"] = pd.Categorical(
            detail_df["CalSim"], categories=master_order, ordered=True
        )
        detail_df = detail_df.sort_values(["CalSim", "Year", "Month"])

        # ==== MASS BALANCE ADJUSTMENT (anchors/tributaries) ==================
        qmap_cal = (
            detail_df[["CalSim", "Year", "Month", "qmap_preAdj"]]
            .rename(columns={"CalSim": "Series", "qmap_preAdj": "Flow_QM"})
            .copy()
        )
        qmap_cal["Series"] = qmap_cal["Series"].astype(str).str.strip()
        qmap_cal["Year"]   = qmap_cal["Year"].astype(int)
        qmap_cal["Month"]  = qmap_cal["Month"].astype(int)
        qmap_cal["WY"]     = np.where(
            qmap_cal["Month"] >= 10, qmap_cal["Year"] + 1, qmap_cal["Year"]
        )

        present_calsim = set(qmap_cal["Series"].unique())
        anchor_map_cal = anchor_map_full[
            anchor_map_full["Anchor_CalSim"].isin(present_calsim)
            & anchor_map_full["Trib_CalSim"].isin(present_calsim)
        ].copy()

        adjusted_cal = enforce_anchor_mass_balance(qmap_cal, anchor_map_cal)

        # Merge adjusted flows back to detail_df
        detail_df = detail_df.merge(
            adjusted_cal[["Series", "Year", "Month", "Flow_QM_Adj"]]
                .rename(columns={"Series": "CalSim"}),
            on=["CalSim", "Year", "Month"],
            how="left",
        )
        detail_df["qmap_postAdj"] = np.where(
            detail_df["Flow_QM_Adj"].notna(),
            detail_df["Flow_QM_Adj"],
            detail_df["qmap_preAdj"],
        )
        detail_df.drop(columns=["Flow_QM_Adj"], inplace=True)

        # ==== WRITE PER-INFLOW CSVs (ONE PER TIME SERIES) ========================
        base_cols = [
            "CalSim",
            "Matched_inflow",
            "Year",
            "Month",
            "vic_val",
            "qmap_preAdj",
            "qmap_postAdj",
        ]

        for cal_name, grp in detail_df.groupby("CalSim", observed=True):
            cal_name = str(cal_name)
            in_fname = input_fname_by_cal.get(cal_name, f"{cal_name}_{ts}.csv")
            out_fname = build_output_filename(cal_name, in_fname)
            out_path = os.path.join(OUT_TS_DIR, out_fname)
            grp[base_cols].to_csv(out_path, index=False)
            print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
