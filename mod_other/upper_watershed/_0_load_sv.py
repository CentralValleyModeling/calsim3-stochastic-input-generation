"""
Load Upper-Watershed SV Variables and Match to Master Inventory
===============================================================
Load all *_SV and *_init DSS variables from upper-watershed modules and match
them against the Master Inventory Spreadsheet on DSS parts C+D concatenation.

Usage
-----
    python mod_other/upper_watershed/_0_load_sv.py
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils import dss_io
from utils.paths import get_inventory_dir, get_module_generated_dir


def main():
    # --- Configuration ---
    _GEN_DIR = get_module_generated_dir("mod_other/upper_watershed")
    modules_dir = Path(__file__).parent / "Modules"
    excel_path = get_inventory_dir() / "_MASTER_INVENTORY_FOR_STOCHASTIC_INPUT_GENERATION_.xlsx"
    sheet_name = "MASTER"
    output_dir = _GEN_DIR / "output" / "_0_load_sv"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Load Master Inventory Spreadsheet ---
    print("Loading Master Inventory Spreadsheet...")
    # Data starts on row 3, so skip first 2 rows
    df_master = pd.read_excel(excel_path, sheet_name=sheet_name, header=1)
    print(f"Master inventory loaded: {len(df_master)} rows")

    # --- Discover all module DSS files ---
    module_folders = [f for f in modules_dir.iterdir() if f.is_dir()]
    print(f"\nFound {len(module_folders)} module folders:")
    for mf in module_folders:
        print(f"  - {mf.name}")

    # --- Scan each module for *_SV.dss files only ---
    dss_files = []
    for module_folder in module_folders:
        dss_folder = module_folder / "CALSIM" / "DSS"
        if not dss_folder.exists():
            print(f"Warning: DSS folder not found for {module_folder.name}")
            continue

        # Look only for SV files that match the module folder name
        module_name = module_folder.name
        expected_sv_file = f"{module_name}_SV.dss"

        for dss_file in dss_folder.glob("*.dss"):
            file_name = dss_file.name
            # Only include SV files
            if file_name == expected_sv_file:
                dss_files.append({
                    "module": module_name,
                    "file_name": file_name,
                    "file_path": dss_file
                })

    print(f"\nFound {len(dss_files)} SV DSS files to process:")
    for df in dss_files:
        print(f"  - {df['module']}: {df['file_name']}")

    # --- Extract all DSS paths from each file ---
    all_dss_records = []

    for dss_info in dss_files:
        print(f"\nProcessing: {dss_info['module']} / {dss_info['file_name']}")

        try:
            with dss_io.open_dss(dss_info['file_path'], version=6, catalog_flag=True) as dss:
                all_paths = dss.getPathnameList("/*/*/*/*/*")

                print(f"  Found {len(all_paths)} pathnames")

                for idx, path in enumerate(all_paths):
                    # Parse DSS path: /A/B/C/D/E/F/
                    parts = path.strip("/").split("/")
                    if len(parts) >= 4:
                        part_a = parts[0] if len(parts) > 0 else ""
                        part_b = parts[1] if len(parts) > 1 else ""
                        part_c = parts[2] if len(parts) > 2 else ""
                        part_d = parts[3] if len(parts) > 3 else ""
                        part_e = parts[4] if len(parts) > 4 else ""
                        part_f = parts[5] if len(parts) > 5 else ""

                        # Concatenate parts B and C for matching
                        b_c_concat = f"{part_b}_{part_c}"

                        # Read time series and calculate metrics
                        avg_monthly_value = np.nan
                        is_constant = False
                        is_monthly_repeating = False

                        try:
                            ts = dss.read_ts(path, trim_missing=True)
                            vals = np.asarray(ts.values, dtype=float)
                            # Filter out missing values
                            valid_vals = vals[(vals > -900) & np.isfinite(vals)]

                            if len(valid_vals) > 0:
                                avg_monthly_value = np.mean(valid_vals)

                                # Check if constant (all values the same)
                                if len(valid_vals) > 1:
                                    is_constant = np.allclose(valid_vals, valid_vals[0], rtol=1e-2, atol=1e-2)

                                # Check if monthly repeating (pattern repeats every 12 months)
                                if len(valid_vals) >= 24 and not is_constant:
                                    # Compare first 12 with subsequent 12-month blocks
                                    pattern = valid_vals[:12]
                                    is_repeating = True
                                    for i in range(12, len(valid_vals) - 11, 12):
                                        block = valid_vals[i:i+12]
                                        if len(block) == 12:
                                            if not np.allclose(pattern, block, rtol=1e-2, atol=1e-2):
                                                is_repeating = False
                                                break
                                    is_monthly_repeating = is_repeating

                        except Exception as e:
                            print(f"    Error reading time series for path: {path} - {e}")
                            pass

                        all_dss_records.append({
                            "Module": dss_info['module'],
                            "Full_Path": path,
                            "Part_A": part_a,
                            "Part_B": part_b,
                            "Part_C": part_c,
                            "Part_D": part_d,
                            "Part_E": part_e,
                            "Part_F": part_f,
                            "B_C_Concat": b_c_concat,
                            "Avg_Monthly_Value": avg_monthly_value,
                            "Is_Constant": is_constant,
                            "Is_Monthly_Repeating": is_monthly_repeating
                        })

        except Exception as e:
            print(f"  Error reading DSS file: {e}")

    # --- Create DataFrame of all DSS records ---
    df_dss = pd.DataFrame(all_dss_records)
    print(f"\n\nTotal DSS records extracted: {len(df_dss)}")

    # --- Simplify to unique Part B and Part C combinations ---
    print("\nGrouping by unique Part B and Part C combinations...")

    # Group by Part B, Part C, and Module, calculate average monthly value and aggregate flags
    df_simplified = df_dss.groupby(['Part_B', 'Part_C', 'Module']).agg({
        'Avg_Monthly_Value': 'mean',  # Average across all variations
        'Is_Constant': 'any',  # True if any path is constant
        'Is_Monthly_Repeating': 'any',  # True if any path is monthly repeating
        'Full_Path': 'count'  # Count how many paths share this B+C+Module
    }).reset_index()

    # Rename columns for clarity
    df_simplified.rename(columns={'Full_Path': 'Num_Paths'}, inplace=True)

    # Create B_C_Concat for matching
    df_simplified['B_C_Concat'] = df_simplified['Part_B'] + "_" + df_simplified['Part_C']

    # Reorder columns
    df_simplified = df_simplified[['Part_B', 'Part_C', 'B_C_Concat', 'Module', 'Avg_Monthly_Value', 'Is_Constant', 'Is_Monthly_Repeating', 'Num_Paths']]

    print(f"Simplified to {len(df_simplified)} unique B+C+Module combinations (from {len(df_dss)} original paths)")

    # Save simplified DSS records
    dss_output_file = output_dir / "all_dss_paths.csv"
    df_simplified.to_csv(dss_output_file, index=False)
    print(f"Saved simplified DSS data to: {dss_output_file}")

    # Also save the detailed (full) version for reference
    dss_detailed_file = output_dir / "all_dss_paths_detailed.csv"
    df_dss.to_csv(dss_detailed_file, index=False)
    print(f"Saved detailed DSS paths to: {dss_detailed_file}")

    # --- Attempt to match against Master Inventory ---
    # Master Inventory has DSS Part B in column C and DSS Part C in column D (starting row 3)
    print("\n\nMaster Inventory column names:")
    for i, col in enumerate(df_master.columns):
        print(f"  Column {i}: {col}")

    # Filter master inventory to only include Upper Watershed Modules
    df_master_filtered = df_master.loc[df_master["Input_Category"]!='Upper Watershed Modules'].copy()

    print("\n\nAttempting to match DSS paths with Master Inventory...")
    print("Using columns C (Part B) and D (Part C) from Master Inventory...")

    # Get column C (index 2) and column D (index 3) - these should be Part B and Part C
    # The columns are accessed by their position since header starts at row 3
    col_names = list(df_master_filtered.columns)
    if len(col_names) >= 4:
        # Columns C and D are at indices 2 and 3 (0-indexed)
        part_b_col = col_names[2]  # Column C
        part_c_col = col_names[3]  # Column D

        print(f"Using column '{part_b_col}' as DSS Part B")
        print(f"Using column '{part_c_col}' as DSS Part C")

        # Create concatenated key in master inventory
        df_master_filtered['B_C_Concat'] = df_master_filtered[part_b_col].astype(str).str.strip() + "_" + df_master_filtered[part_c_col].astype(str).str.strip()

        # Check which B_C_Concat values exist in the master inventory
        master_bc_set = set(df_master_filtered['B_C_Concat'].dropna())

        # Add matched flag to simplified data
        df_simplified['Matched_In_Inventory'] = df_simplified['B_C_Concat'].isin(master_bc_set)

        # Save matched results (only simplified data + match flag)
        matched_output_file = output_dir / "matched_dss_to_inventory.csv"
        df_simplified.to_csv(matched_output_file, index=False)
        print(f"\nMatched results saved to: {matched_output_file}")

        # Summary statistics
        matched_count = df_simplified['Matched_In_Inventory'].sum()
        unmatched_count = len(df_simplified) - matched_count
        print("\nMatching statistics:")
        print(f"Matched: {matched_count} / {len(df_simplified)} ({100*matched_count/len(df_simplified):.1f}%)")
        print(f"Unmatched: {unmatched_count} / {len(df_simplified)} ({100*unmatched_count/len(df_simplified):.1f}%)")

    else:
        print("\nCould not automatically identify DSS part columns in Master Inventory.")
        print("Manual inspection required. Here are the first few rows of the Master Inventory:")
        print(df_master.head())

        # Still save the DSS records for manual matching
        print(f"\nDSS paths have been saved to: {dss_output_file}")
        print("You can manually match these against the Master Inventory.")

        # Save summary statistics
        summary_stats = {
            "Total DSS Records (original)": len(df_dss),
            "Total DSS Records (simplified)": len(df_simplified),
            "Unique B_C Combinations": df_simplified['B_C_Concat'].nunique()
        }

        summary_file = output_dir / "summary_statistics.txt"
        with open(summary_file, 'w') as f:
            for key, value in summary_stats.items():
                f.write(f"{key}: {value}\n")

        print(f"\nSummary statistics saved to: {summary_file}")


if __name__ == "__main__":
    main()
