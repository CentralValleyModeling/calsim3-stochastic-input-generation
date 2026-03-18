"""
Compare Product A WYTs with Historical (CDEC) WYTs.

Provides:
1. Basic comparison statistics
2. Detailed mismatch analysis with index values
3. Visual plots comparing indices over time

Inputs (auto-resolved via utils.paths):
- reference/cdec_wyt.txt              — Historical CDEC WYT index file
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_A/_SacWYT.csv
- data/GENERATED/.../water_year_types/output/_1_calc_WYTs/Product_A/_SJWYT.csv

Outputs:
- data/GENERATED/.../water_year_types/output/_2_compare_WYTs/wyt_index_comparison.png
- data/GENERATED/.../water_year_types/output/_2_compare_WYTs/wyt_index_difference.png

Examples
--------
# Run from repo root (requires _1_calc_WYTs.py to have been run first):
    cd mod_hydrology/water_year_types && python _2_compare_wyts.py
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_SCRIPT_DIR = Path(__file__).resolve().parent
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")

# Directories
INPUT_DIR = _SCRIPT_DIR / 'reference'
OUTPUT_DIR = _wyt_gen / 'output' / '_2_compare_WYTs'

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
    
    # Parse data lines
    for line in lines[data_start:]:
        # Skip empty lines and footnotes
        if not line.strip() or line.strip().startswith('*') or 'Footnote' in line:
            continue
        
        # Try to parse the line
        # Format: WY  Oct-Mar Apr-Jul WYsum Index Yr-type Oct-Mar Apr-Jul WYsum Index Yr-type
        parts = line.split()
        
        if len(parts) < 2:
            continue
        
        try:
            wy = int(parts[0])
            
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
        except (ValueError, IndexError):
            continue
    
    return pd.DataFrame(data)


def load_data():
    """Load historical and Product A WYT data."""
    print("Loading data...")
    
    # Load historical from CDEC file
    cdec_df = parse_cdec_wyt(INPUT_DIR / 'cdec_wyt.txt')
    
    # Load Product A outputs
    prod_a_sac = pd.read_csv(_wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_A' / '_SacWYT.csv')
    prod_a_sj = pd.read_csv(_wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_A' / '_SJWYT.csv')
    
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
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # Sacramento plot
    ax1.plot(comparison['water_year'], comparison['sac_index_hist'], 
             'o-', label='Historical (CDEC)', color='#1f77b4', linewidth=2, markersize=4)
    ax1.plot(comparison['water_year'], comparison['sac_index_prod_a'], 
             's-', label='Product A', color='#ff7f0e', linewidth=2, markersize=4, alpha=0.7)
    
    # Add threshold lines
    for label, value in SAC_THRESH.items():
        ax1.axhline(y=value, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax1.text(comparison['water_year'].max() + 0.5, value, label.upper(), 
                 fontsize=9, va='center', color='gray')
    
    ax1.set_ylabel('Sacramento Valley Index (MAF)', fontsize=12, fontweight='bold')
    ax1.set_title('Sacramento Valley 40-30-30 Index: Product A vs Historical (CDEC)', 
                  fontsize=14, fontweight='bold', pad=15)
    ax1.legend(loc='upper left', fontsize=10)
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
                 fontsize=9, va='center', color='gray')
    
    ax2.set_xlabel('Water Year', fontsize=12, fontweight='bold')
    ax2.set_ylabel('San Joaquin Valley Index (MAF)', fontsize=12, fontweight='bold')
    ax2.set_title('San Joaquin Valley 60-20-20 Index: Product A vs Historical (CDEC)', 
                  fontsize=14, fontweight='bold', pad=15)
    ax2.legend(loc='upper left', fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file = OUTPUT_DIR / 'wyt_index_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"  Saved: {output_file}")
    plt.close()
    
    # Create difference plot
    fig2, (ax3, ax4) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # Calculate differences
    comparison['sac_diff'] = comparison['sac_index_prod_a'] - comparison['sac_index_hist']
    comparison['sj_diff'] = comparison['sj_index_prod_a'] - comparison['sj_index_hist']
    
    # Sacramento difference
    colors_sac = ['red' if x < 0 else 'green' for x in comparison['sac_diff']]
    ax3.bar(comparison['water_year'], comparison['sac_diff'], color=colors_sac, alpha=0.6)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax3.set_ylabel('Difference (Product A - Historical) MAF', fontsize=12, fontweight='bold')
    ax3.set_title('Sacramento Valley Index Difference', fontsize=14, fontweight='bold', pad=15)
    ax3.grid(True, alpha=0.3, axis='y')
    
    # Add statistics text
    sac_rmse = np.sqrt(np.mean(comparison['sac_diff']**2))
    sac_mean_diff = comparison['sac_diff'].mean()
    ax3.text(0.02, 0.98, f'Mean Diff: {sac_mean_diff:.3f} MAF\nRMSE: {sac_rmse:.3f} MAF', 
             transform=ax3.transAxes, fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # San Joaquin difference
    colors_sj = ['red' if x < 0 else 'green' for x in comparison['sj_diff']]
    ax4.bar(comparison['water_year'], comparison['sj_diff'], color=colors_sj, alpha=0.6)
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax4.set_xlabel('Water Year', fontsize=12, fontweight='bold')
    ax4.set_ylabel('Difference (Product A - Historical) MAF', fontsize=12, fontweight='bold')
    ax4.set_title('San Joaquin Valley Index Difference', fontsize=14, fontweight='bold', pad=15)
    ax4.grid(True, alpha=0.3, axis='y')
    
    # Add statistics text
    sj_rmse = np.sqrt(np.mean(comparison['sj_diff']**2))
    sj_mean_diff = comparison['sj_diff'].mean()
    ax4.text(0.02, 0.98, f'Mean Diff: {sj_mean_diff:.3f} MAF\nRMSE: {sj_rmse:.3f} MAF', 
             transform=ax4.transAxes, fontsize=10, verticalalignment='top',
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


def main():
    """Main comparison workflow."""
    # Load data
    comparison = load_data()
    
    # Basic comparison statistics
    print_basic_comparison(comparison)
    
    # Detailed mismatch analysis
    print_detailed_mismatches(comparison)
    
    # Create plots
    create_index_plots(comparison)
    
    print("Done!")


if __name__ == '__main__':
    main()
