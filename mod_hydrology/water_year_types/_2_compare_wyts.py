"""
Compare Water Year Type indices across products.

Provides:
1. Basic comparison statistics (Product A vs Historical/CDEC)
2. Detailed mismatch analysis with index values
3. Visual plots comparing indices over time
4. CDF comparison of Sac/SJ indices: Historical, Product A, Product B (10 chunks)

Inputs (auto-resolved via utils.paths):
- reference/cdec_wyt.txt              -- Historical CDEC WYT index file
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_A/_SacWYT.csv
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_A/_SJWYT.csv
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_B/_SacWYT_n01..n10.csv
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_B/_SJWYT_n01..n10.csv

Outputs:
- data/GENERATED/.../water_year_types/output/_2_compare_WYTs/wyt_index_comparison.png
- data/GENERATED/.../water_year_types/output/_2_compare_WYTs/wyt_index_difference.png
- data/GENERATED/.../water_year_types/output/_2_compare_WYTs/wyt_index_cdf_comparison.png

Examples
--------
# Run all comparisons (default):
    cd mod_hydrology/water_year_types && python _2_compare_wyts.py

# Only Product A vs Historical comparison:
    cd mod_hydrology/water_year_types && python _2_compare_wyts.py --compare-a

# Only CDF distribution comparison (Hist + Product A + Product B):
    cd mod_hydrology/water_year_types && python _2_compare_wyts.py --compare-cdf

# Both:
    cd mod_hydrology/water_year_types && python _2_compare_wyts.py --compare-a --compare-cdf
"""

import sys
from pathlib import Path
import argparse

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

matplotlib.rcParams['font.size'] = 8

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_SCRIPT_DIR = Path(__file__).resolve().parent
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# Directories
INPUT_DIR = _SCRIPT_DIR / 'reference'
OUTPUT_DIR = _wyt_gen / 'output' / '_2_compare_WYTs'
PRODUCT_A_DIR = _wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_A'
PRODUCT_B_DIR = _wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_B'
N_CHUNKS = 10

# WYT Thresholds (MAF)
SAC_THRESH = {'c': 5.4, 'd': 6.5, 'bn': 7.8, 'an': 9.2}
SJ_THRESH = {'c': 2.1, 'd': 2.5, 'bn': 3.1, 'an': 3.8}


def parse_cdec_wyt(filepath):
    """Parse the CDEC WYT text file to extract index values."""
    data = []
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    # Find the data section (starts after the header with dashes)
    data_start = None
    for i, line in enumerate(lines):
        if '---' in line:
            data_start = i + 1
            break
    
    if data_start is None:
        raise ValueError("Could not find data section in CDEC file")
    
    # Parse data lines from the main table only (11 columns per row).
    # The CDEC file contains additional tables below the main one; stop at
    # the first blank line after we have parsed at least one data row.
    found_data = False
    for line in lines[data_start:]:
        stripped = line.strip()

        if not stripped:
            if found_data:
                break          # end of main table
            continue

        if stripped.startswith('*') or 'Footnote' in stripped:
            continue

        # Format: WY  Oct-Mar Apr-Jul WYsum Index Yr-type Oct-Mar Apr-Jul WYsum Index Yr-type
        parts = stripped.split()

        if len(parts) < 2:
            continue

        try:
            wy = int(parts[0])
        except ValueError:
            if found_data:
                break          # non-numeric first token = summary row (min/mean/max)
            continue

        # Sacramento data (if available)
        sac_index = None
        sac_wyt = None
        if len(parts) >= 5:
            try:
                sac_index = float(parts[4])
                sac_wyt = parts[5] if len(parts) > 5 else None
            except (ValueError, IndexError):
                pass

        # San Joaquin data (if available)
        sj_index = None
        sj_wyt = None
        if len(parts) >= 10:
            try:
                sj_index = float(parts[9])
                sj_wyt = parts[10] if len(parts) > 10 else None
            except (ValueError, IndexError):
                pass

        data.append({
            'water_year': wy,
            'sac_index_hist': sac_index,
            'sac_wyt_hist': sac_wyt,
            'sj_index_hist': sj_index,
            'sj_wyt_hist': sj_wyt
        })
        found_data = True
    
    return pd.DataFrame(data)


def load_data():
    """Load historical and Product A WYT data."""
    print("Loading data...")
    
    # Load historical from CDEC file
    cdec_df = parse_cdec_wyt(INPUT_DIR / 'cdec_wyt.txt')
    
    # Load Product A outputs
    prod_a_sac = pd.read_csv(PRODUCT_A_DIR / '_SacWYT.csv')
    prod_a_sj = pd.read_csv(PRODUCT_A_DIR / '_SJWYT.csv')
    
    # Merge Product A with historical
    comparison = cdec_df.copy()
    comparison = comparison.merge(
        prod_a_sac[['water_year', 'index', 'wyt_label']],
        on='water_year',
        how='left'
    )
    comparison = comparison.rename(columns={'index': 'sac_index_prod_a', 'wyt_label': 'sac_wyt_prod_a'})
    
    comparison = comparison.merge(
        prod_a_sj[['water_year', 'index', 'wyt_label']],
        on='water_year',
        how='left'
    )
    comparison = comparison.rename(columns={'index': 'sj_index_prod_a', 'wyt_label': 'sj_wyt_prod_a'})
    
    # Filter to overlapping period (must have both historical and Product A data)
    comparison = comparison[
        comparison['sac_index_prod_a'].notna() & 
        comparison['sj_index_prod_a'].notna() &
        comparison['sac_index_hist'].notna() &
        comparison['sj_index_hist'].notna()
    ].copy()
    
    return comparison


def print_basic_comparison(comparison):
    """Print basic comparison statistics."""
    print("\n" + "="*80)
    print("DATA RANGES")
    print("="*80)
    print(f"Overlapping period: {comparison['water_year'].min()}-{comparison['water_year'].max()} ({len(comparison)} years)")
    print()
    
    # Sacramento comparison
    comparison['sac_match'] = comparison['sac_wyt_hist'] == comparison['sac_wyt_prod_a']
    comparison['sj_match'] = comparison['sj_wyt_hist'] == comparison['sj_wyt_prod_a']
    
    print("="*80)
    print("SACRAMENTO VALLEY WYT COMPARISON")
    print("="*80)
    print(f"Total overlapping years: {len(comparison)}")
    print(f"Matching WYTs: {comparison['sac_match'].sum()} ({comparison['sac_match'].sum()/len(comparison)*100:.1f}%)")
    print(f"Mismatches: {(~comparison['sac_match']).sum()}")
    print()
    
    print("="*80)
    print("SAN JOAQUIN VALLEY WYT COMPARISON")
    print("="*80)
    print(f"Total overlapping years: {len(comparison)}")
    print(f"Matching WYTs: {comparison['sj_match'].sum()} ({comparison['sj_match'].sum()/len(comparison)*100:.1f}%)")
    print(f"Mismatches: {(~comparison['sj_match']).sum()}")
    print()
    
    print("="*80)
    print("OVERALL STATISTICS")
    print("="*80)
    overall_matches = comparison['sac_match'].sum() + comparison['sj_match'].sum()
    overall_total = len(comparison) * 2
    print(f"Overall match rate: {overall_matches}/{overall_total} ({overall_matches/overall_total*100:.1f}%)")
    print()


def print_detailed_mismatches(comparison):
    """Print detailed mismatch analysis with index values."""
    print("="*90)
    print("SACRAMENTO VALLEY - MISMATCHED YEARS (showing index values)")
    print("="*90)
    print(f"\nThresholds (MAF): C<{SAC_THRESH['c']} | D<{SAC_THRESH['d']} | BN<{SAC_THRESH['bn']} | AN<{SAC_THRESH['an']} | W>={SAC_THRESH['an']}\n")
    
    sac_mismatch = comparison[~comparison['sac_match']].copy()
    if len(sac_mismatch) > 0:
        sac_mismatch_display = sac_mismatch[['water_year', 'sac_index_prod_a', 'sac_wyt_hist', 'sac_wyt_prod_a']].copy()
        sac_mismatch_display.columns = ['Year', 'Index (MAF)', 'Historical WYT', 'Product A WYT']
        print(sac_mismatch_display.to_string(index=False))
        
        print("\nAnalysis of mismatches:")
        for _, row in sac_mismatch_display.iterrows():
            idx = row['Index (MAF)']
            distances = {f"{thresh}({val})": abs(idx - val) for thresh, val in SAC_THRESH.items()}
            nearest = min(distances, key=distances.get)
            print(f"  {int(row['Year'])}: Index={idx:.2f} MAF, nearest threshold is {nearest} (distance={distances[nearest]:.2f})")
    else:
        print("No mismatches!")
    
    print("\n" + "="*90)
    print("SAN JOAQUIN VALLEY - MISMATCHED YEARS (showing index values)")
    print("="*90)
    print(f"\nThresholds (MAF): C<{SJ_THRESH['c']} | D<{SJ_THRESH['d']} | BN<{SJ_THRESH['bn']} | AN<{SJ_THRESH['an']} | W>={SJ_THRESH['an']}\n")
    
    sj_mismatch = comparison[~comparison['sj_match']].copy()
    if len(sj_mismatch) > 0:
        sj_mismatch_display = sj_mismatch[['water_year', 'sj_index_prod_a', 'sj_wyt_hist', 'sj_wyt_prod_a']].copy()
        sj_mismatch_display.columns = ['Year', 'Index (MAF)', 'Historical WYT', 'Product A WYT']
        print(sj_mismatch_display.to_string(index=False))
        
        print("\nAnalysis of mismatches:")
        for _, row in sj_mismatch_display.iterrows():
            idx = row['Index (MAF)']
            distances = {f"{thresh}({val})": abs(idx - val) for thresh, val in SJ_THRESH.items()}
            nearest = min(distances, key=distances.get)
            print(f"  {int(row['Year'])}: Index={idx:.2f} MAF, nearest threshold is {nearest} (distance={distances[nearest]:.2f})")
    else:
        print("No mismatches!")
    print()


def create_index_plots(comparison):
    """Create plots comparing indices between Product A and Historical."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Creating index comparison plots...")
    
    # Create figure with two subplots - Index comparison over time
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(6.5, 4.6), sharex=True)
    
    # Sacramento plot
    ax1.plot(comparison['water_year'], comparison['sac_index_hist'], 
             'o-', label='Historical (CDEC)', color='#1f77b4', linewidth=2, markersize=4)
    ax1.plot(comparison['water_year'], comparison['sac_index_prod_a'], 
             's-', label='Product A', color='#ff7f0e', linewidth=2, markersize=4, alpha=0.7)
    
    # Add threshold lines
    for label, value in SAC_THRESH.items():
        ax1.axhline(y=value, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax1.text(comparison['water_year'].max() + 0.5, value, label.upper(), 
                 fontsize=8, va='center', color='gray')
    
    ax1.set_ylabel('Sacramento Valley Index (MAF)', fontsize=8, fontweight='bold')
    ax1.set_title('Sacramento Valley 40-30-30 Index: Product A vs Historical (CDEC)', 
                  fontsize=8, fontweight='bold', pad=8)
    ax1.legend(loc='upper left', fontsize=7)
    ax1.grid(True, alpha=0.3)
    
    # San Joaquin plot
    ax2.plot(comparison['water_year'], comparison['sj_index_hist'], 
             'o-', label='Historical (CDEC)', color='#1f77b4', linewidth=2, markersize=4)
    ax2.plot(comparison['water_year'], comparison['sj_index_prod_a'], 
             's-', label='Product A', color='#ff7f0e', linewidth=2, markersize=4, alpha=0.7)
    
    # Add threshold lines
    for label, value in SJ_THRESH.items():
        ax2.axhline(y=value, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax2.text(comparison['water_year'].max() + 0.5, value, label.upper(), 
                 fontsize=8, va='center', color='gray')
    
    ax2.set_xlabel('Water Year', fontsize=8, fontweight='bold')
    ax2.set_ylabel('San Joaquin Valley Index (MAF)', fontsize=8, fontweight='bold')
    ax2.set_title('San Joaquin Valley 60-20-20 Index: Product A vs Historical (CDEC)', 
                  fontsize=8, fontweight='bold', pad=8)
    ax2.legend(loc='upper left', fontsize=7)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file = OUTPUT_DIR / 'wyt_index_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"  Saved: {output_file}")
    plt.close()
    
    # Create difference plot
    fig2, (ax3, ax4) = plt.subplots(2, 1, figsize=(6.5, 4.6), sharex=True)
    
    # Calculate differences
    comparison['sac_diff'] = comparison['sac_index_prod_a'] - comparison['sac_index_hist']
    comparison['sj_diff'] = comparison['sj_index_prod_a'] - comparison['sj_index_hist']
    
    # Sacramento difference
    colors_sac = ['red' if x < 0 else 'green' for x in comparison['sac_diff']]
    ax3.bar(comparison['water_year'], comparison['sac_diff'], color=colors_sac, alpha=0.6)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax3.set_ylabel('Difference (Product A - Historical) MAF', fontsize=8, fontweight='bold')
    ax3.set_title('Sacramento Valley Index Difference', fontsize=8, fontweight='bold', pad=8)
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Add statistics text
    sac_rmse = np.sqrt(np.mean(comparison['sac_diff']**2))
    sac_mean_diff = comparison['sac_diff'].mean()
    ax3.text(0.02, 0.98, f'Mean Diff: {sac_mean_diff:.3f} MAF\nRMSE: {sac_rmse:.3f} MAF', 
             transform=ax3.transAxes, fontsize=8, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # San Joaquin difference
    colors_sj = ['red' if x < 0 else 'green' for x in comparison['sj_diff']]
    ax4.bar(comparison['water_year'], comparison['sj_diff'], color=colors_sj, alpha=0.6)
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax4.set_xlabel('Water Year', fontsize=8, fontweight='bold')
    ax4.set_ylabel('Difference (Product A - Historical) MAF', fontsize=8, fontweight='bold')
    ax4.set_title('San Joaquin Valley Index Difference', fontsize=8, fontweight='bold', pad=8)
    ax4.grid(True, alpha=0.3, axis='y')
    
    # Add statistics text
    sj_rmse = np.sqrt(np.mean(comparison['sj_diff']**2))
    sj_mean_diff = comparison['sj_diff'].mean()
    ax4.text(0.02, 0.98, f'Mean Diff: {sj_mean_diff:.3f} MAF\nRMSE: {sj_rmse:.3f} MAF', 
             transform=ax4.transAxes, fontsize=8, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    output_file = OUTPUT_DIR / 'wyt_index_difference.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"  Saved: {output_file}")
    plt.close()
    
    # Print statistics
    print("\n" + "="*80)
    print("INDEX COMPARISON STATISTICS")
    print("="*80)
    print(f"\nSacramento Valley:")
    print(f"  Mean difference (Product A - Historical): {sac_mean_diff:.4f} MAF")
    print(f"  RMSE: {sac_rmse:.4f} MAF")
    print(f"  Max difference: {comparison['sac_diff'].max():.4f} MAF (WY {comparison.loc[comparison['sac_diff'].idxmax(), 'water_year']:.0f})")
    print(f"  Min difference: {comparison['sac_diff'].min():.4f} MAF (WY {comparison.loc[comparison['sac_diff'].idxmin(), 'water_year']:.0f})")
    
    print(f"\nSan Joaquin Valley:")
    print(f"  Mean difference (Product A - Historical): {sj_mean_diff:.4f} MAF")
    print(f"  RMSE: {sj_rmse:.4f} MAF")
    print(f"  Max difference: {comparison['sj_diff'].max():.4f} MAF (WY {comparison.loc[comparison['sj_diff'].idxmax(), 'water_year']:.0f})")
    print(f"  Min difference: {comparison['sj_diff'].min():.4f} MAF (WY {comparison.loc[comparison['sj_diff'].idxmin(), 'water_year']:.0f})")
    print()


def create_cdf_comparison(comparison):
    """Two-panel CDF of Sac/SJ index: Historical, Product A, 10 Product B chunks."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Creating CDF comparison plot...")

    # Gather data --------------------------------------------------------
    # Historical (CDEC) -- WY 1922-2021 (100 water years; Oct 1921 - Sep 2021)
    cdec_full = parse_cdec_wyt(INPUT_DIR / 'cdec_wyt.txt')
    cdec_100 = cdec_full[(cdec_full['water_year'] >= 1922) & (cdec_full['water_year'] <= 2021)]
    hist_sac = cdec_100['sac_index_hist'].dropna().values
    hist_sj = cdec_100['sj_index_hist'].dropna().values

    # Product A (1972-2018)
    prod_a_sac_df = pd.read_csv(PRODUCT_A_DIR / '_SacWYT.csv')
    prod_a_sj_df = pd.read_csv(PRODUCT_A_DIR / '_SJWYT.csv')
    pa_mask_sac = (prod_a_sac_df['water_year'] >= 1972) & (prod_a_sac_df['water_year'] <= 2018)
    pa_mask_sj = (prod_a_sj_df['water_year'] >= 1972) & (prod_a_sj_df['water_year'] <= 2018)
    prod_a_sac_vals = prod_a_sac_df.loc[pa_mask_sac, 'index'].dropna().values
    prod_a_sj_vals = prod_a_sj_df.loc[pa_mask_sj, 'index'].dropna().values
    pa_n = len(prod_a_sac_vals)

    # Product B (10 chunks)
    pb_sac_chunks = []
    pb_sj_chunks = []
    for chunk in range(1, N_CHUNKS + 1):
        tag = f"n{chunk:02d}"
        sac_path = PRODUCT_B_DIR / f'_SacWYT_{tag}.csv'
        sj_path = PRODUCT_B_DIR / f'_SJWYT_{tag}.csv'
        if sac_path.exists() and sj_path.exists():
            pb_sac_chunks.append(pd.read_csv(sac_path)['index'].dropna().values)
            pb_sj_chunks.append(pd.read_csv(sj_path)['index'].dropna().values)
        else:
            print(f"  WARNING: Product B chunk {tag} not found, skipping")

    if not pb_sac_chunks:
        print("  No Product B data found -- skipping CDF plot")
        return

    # Helper: empirical CDF
    def ecdf(data):
        x = np.sort(data)
        y = np.arange(1, len(x) + 1) / len(x)
        return x, y

    # Plot ---------------------------------------------------------------
    fig, (ax_sac, ax_sj) = plt.subplots(1, 2, figsize=(6.5, 3.2))

    for ax, hist_vals, pa_vals, pb_chunks, title, thresholds in [
        (ax_sac, hist_sac, prod_a_sac_vals, pb_sac_chunks,
         "Sacramento 40-30-30 Index", SAC_THRESH),
        (ax_sj, hist_sj, prod_a_sj_vals, pb_sj_chunks,
         "San Joaquin 60-20-20 Index", SJ_THRESH),
    ]:
        # Product B chunks (thin gray)
        for i, chunk_vals in enumerate(pb_chunks):
            x, y = ecdf(chunk_vals)
            label = "Product B (100-Yr)" if i == 0 else None
            ax.step(x, y, where="post", color="#888888", linewidth=0.7,
                    alpha=0.5, label=label)

        # Historical
        x, y = ecdf(hist_vals)
        ax.step(x, y, where="post", color="#1f77b4", linewidth=1.5,
                label=f"Historical CDEC (1922-2021)")

        # Product A
        x, y = ecdf(pa_vals)
        ax.step(x, y, where="post", color="#ff7f0e", linewidth=1.5,
                label=f"Product A (1972-2018)")

        # Threshold lines with labels inside plot at top-left of each line
        for label_t, val in thresholds.items():
            ax.axvline(val, color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
            ax.text(val - 0.05, 0.97, label_t.upper(), fontsize=7, ha="right",
                    va="top", color="gray", transform=ax.get_xaxis_transform())

        ax.set_xlabel("Index (MAF)")
        ax.set_ylabel("Cumulative Probability")
        ax.set_title(title, fontsize=8, fontweight="bold", pad=4)
        ax.set_ylim(0, 1.0)
        ax.legend(loc="lower right", fontsize=7)
        ax.grid(True, alpha=0.3)

    fig.suptitle("WYT Index CDF Comparison: Historical vs Product A vs Product B",
                 fontsize=8, fontweight="bold", y=0.99)
    fig.tight_layout()

    output_file = OUTPUT_DIR / "wyt_index_cdf_comparison.png"
    fig.savefig(output_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_file}")

    # Print summary stats
    print("\n" + "=" * 80)
    print("CDF COMPARISON SUMMARY")
    print("=" * 80)
    pb_sac_all = np.concatenate(pb_sac_chunks)
    pb_sj_all = np.concatenate(pb_sj_chunks)
    print(f"  {'':15s}  {'Sac mean':>10s}  {'Sac med':>10s}  {'SJ mean':>10s}  {'SJ med':>10s}")
    print(f"  {'Historical':15s}  {np.mean(hist_sac):10.3f}  {np.median(hist_sac):10.3f}  "
          f"{np.mean(hist_sj):10.3f}  {np.median(hist_sj):10.3f}")
    print(f"  {'Product A':15s}  {np.mean(prod_a_sac_vals):10.3f}  {np.median(prod_a_sac_vals):10.3f}  "
          f"{np.mean(prod_a_sj_vals):10.3f}  {np.median(prod_a_sj_vals):10.3f}")
    print(f"  {'Product B (all)':15s}  {np.mean(pb_sac_all):10.3f}  {np.median(pb_sac_all):10.3f}  "
          f"{np.mean(pb_sj_all):10.3f}  {np.median(pb_sj_all):10.3f}")
    print()


def main():
    """Main comparison workflow."""
    parser = argparse.ArgumentParser(
        description="Compare WYT indices across Historical, Product A, and Product B."
    )
    parser.add_argument("--compare-a", action="store_true",
                        help="Run Product A vs Historical comparison (stats + plots)")
    parser.add_argument("--compare-cdf", action="store_true",
                        help="Run CDF distribution comparison (Hist + A + B)")
    args = parser.parse_args()

    # If no flags given, run everything
    run_all = not args.compare_a and not args.compare_cdf

    # Load Product A vs Historical data (needed by both modes)
    comparison = load_data()

    if run_all or args.compare_a:
        print_basic_comparison(comparison)
        print_detailed_mismatches(comparison)
        create_index_plots(comparison)

    if run_all or args.compare_cdf:
        create_cdf_comparison(comparison)

    print("Done!")


if __name__ == '__main__':
    main()
