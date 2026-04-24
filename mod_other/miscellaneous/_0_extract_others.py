import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pydsstools.heclib.dss import HecDss

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_base_dir, get_module_generated_dir, get_inventory_dir


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
_GEN_DIR = get_module_generated_dir("mod_other/miscellaneous")

DEFAULT_DSS        = get_base_dir() / "CalSim3" / "__calsim_sv_default__.dss"
script_name = Path(__file__).stem
DEFAULT_OUTDIR     = _GEN_DIR / "output" / script_name
DEFAULT_MASTER_XLS = get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx"

# Output file names
OUT_XLSX = DEFAULT_OUTDIR / "other_monthly_from_dss.xlsx"


def excel_to_part_b(name: str) -> str:
    """Map an Excel name to DSS Part B convention."""
    return str(name).upper().replace(" ", "_")


def extract_other_monthlies_from_dss(dss_path: Path, master_xls_path: Path) -> pd.DataFrame:
    """
    - Reads the MASTER Excel, selects rows where 9th column starts with 'Other' 
    - Finds matching DSS monthly series (Part B) and extracts ALL available months.
    - Returns a DataFrame of all assembled series.
    """
    # --- Load MASTER inventory and filter to rows tagged "Other..." in the module column (col 9)
    sheet_name = "MASTER"
    print(f"Reading master inventory: {master_xls_path.name}")
    df_master = pd.read_excel(master_xls_path, sheet_name=sheet_name)

    mask_other = (
        df_master.iloc[:, 8]  # 9th column, 0-based index 8
        .astype(str).str.strip().str.lower().str.startswith("other", na=False)
    )
    other_rows  = df_master[mask_other]
    other_names = [str(name).strip() for name in other_rows.iloc[:, 2].tolist()]
    print(f"  Found {len(other_names)} 'Other' entries in MASTER inventory")

    # Map Excel SV names -> DSS Part B (uppercase, spaces to underscores)
    excel_partbs = {excel_to_part_b(n): n for n in other_names}

    # --- Open the baseline DSS and organize monthly paths by Part B
    dss_monthly = {}
    print(f"Opening DSS: {dss_path.name}")
    with HecDss.Open(str(dss_path), version=6) as dss:
        # Filter catalog to monthly records only
        all_paths = dss.getPathnameList("/*/*/*/*/1MON/*/")
        print(f"  {len(all_paths)} monthly paths found in DSS catalog")

        # Group DSS paths by Part B so we can merge multi-record series
        buckets = {}
        for p in all_paths:
            parts  = p.strip("/").split("/")
            if len(parts) < 6:
                continue
            part_b = parts[1].upper()
            buckets.setdefault(part_b, []).append(p)

        # Intersect DSS Part Bs with the wanted "Other" list
        wanted_keys = sorted(set(excel_partbs).intersection(buckets))
        if not wanted_keys:
            print("Warning: No 'Other...' entries from MASTER matched DSS Part B paths.")
        else:
            print(f"  {len(wanted_keys)} matching Part B keys to extract")

        for part_b in wanted_keys:
            plist = buckets[part_b]

            # Merge all date-range slices for this Part B into one continuous series;
            # later Part D ranges take precedence via combine_first
            master = pd.Series(dtype="float64")

            # Sort by Part D so precedence is deterministic (earliest range first)
            for p in sorted(plist, key=lambda x: x.strip("/").split("/")[3]):
                ts = dss.read_ts(p, trim_missing=True)
                vals = np.asarray(ts.values, dtype=float)
                vals[vals <= -900] = np.nan  # replace DSS missing-value sentinel with NaN

                # Normalize dates to end-of-month
                idx = (pd.to_datetime(ts.pytimes).to_period("M") - 1).to_timestamp("M")

                s = pd.Series(vals, index=idx)
                master = s.combine_first(master)

            if master.notna().any():
                series_name = excel_partbs.get(part_b, part_b)
                master.name = series_name
                dss_monthly[series_name] = master
                print(f"    Extracted: {series_name}  ({master.notna().sum()} months)")

    # Assemble all series into a single DataFrame, aligned on a common date index
    df = pd.DataFrame(dss_monthly).sort_index()
    print(f"Extraction complete: {df.shape[1]} series, {df.shape[0]} months")
    return df


def main():
    # Ensure output directory exists
    DEFAULT_OUTDIR.mkdir(parents=True, exist_ok=True)

    # Extract "Other" monthly series from the baseline DSS
    df_other = extract_other_monthlies_from_dss(
        dss_path=DEFAULT_DSS,
        master_xls_path=DEFAULT_MASTER_XLS,
    )

    # Write CSV
    #df_other.to_csv(OUT_CSV, index_label="date", date_format="%Y-%m-%d")

    # Write results to Excel
    print(f"Writing output: {OUT_XLSX}")
    with pd.ExcelWriter(OUT_XLSX) as xw:
        df_other.to_excel(xw, sheet_name="OtherMonthly", index_label="date")
    print("Done.")


if __name__ == "__main__":
    main()
