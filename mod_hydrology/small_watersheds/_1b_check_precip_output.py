"""
Interactive comparison of original vs. regenerated CVprecip .dat files.

Computes per-watershed statistics (mean difference, RMSE, correlation) and
generates diagnostic scatter, histogram, and CDF plots.
Can be run cell-by-cell in VS Code IPython or as a complete script.

Usage
-----
    python _1b_check_precip_output.py
"""
# %%
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# Add repo root to path for utils imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

# %%
# Configuration
_SCRIPT_DIR = Path(__file__).resolve().parent
_GEN_DIR = get_module_generated_dir("mod_hydrology/small_watersheds")

ORIGINAL_FILE = str(_SCRIPT_DIR / 'reference' / 'CVprecipWY1921_2021.dat')
NEW_FILE = str(_GEN_DIR / 'output' / '_1_compile_precip_sws' / 'Product_A' / 'CVprecipWY1921_2021.dat')
OUTPUT_DIR = str(_GEN_DIR / 'output' / '_1_compile_precip_sws' / 'Product_A')
SUMMARY_CSV = os.path.join(OUTPUT_DIR, "comparison_summary.csv")

# Modified columns start at index 1393 (1-indexed column 1394)
START_COL = 1393
HEADER_ROWS = 104

# %%
def load_cvprecip_data(filepath: str, skiprows: int = HEADER_ROWS) -> pd.DataFrame:
    """Load CVprecip data file."""
    print(f"Loading: {filepath}")
    df = pd.read_csv(filepath, delimiter='\t', header=None, skiprows=skiprows)
    print(f"  Shape: {df.shape}")
    return df

# %%
def compare_columns(orig_df: pd.DataFrame, 
                   new_df: pd.DataFrame, 
                   start_col: int = START_COL) -> pd.DataFrame:
    """
    Compare original and new CVprecip files for modified columns.
    
    Returns DataFrame with statistics for each watershed.
    """
    end_col = min(orig_df.shape[1], new_df.shape[1])
    n_watersheds = end_col - start_col
    
    print(f"\nComparing {n_watersheds} watersheds (columns {start_col+1} to {end_col})")
    
    stats_list = []
    
    for col_idx in range(start_col, end_col):
        watershed_id = col_idx - start_col + 1  # Watershed numbering starts at 1
        
        orig_vals = orig_df.iloc[:, col_idx].dropna()
        new_vals = new_df.iloc[:, col_idx].dropna()
        
        # Ensure same length
        min_len = min(len(orig_vals), len(new_vals))
        orig_vals = orig_vals.iloc[:min_len]
        new_vals = new_vals.iloc[:min_len]
        
        # Calculate differences
        diff = new_vals - orig_vals
        
        # Compute statistics
        stats = {
            'Watershed_ID': watershed_id,
            'Column_Index': col_idx + 1,  # 1-indexed
            'N_Values': len(orig_vals),
            'Original_Mean': orig_vals.mean(),
            'New_Mean': new_vals.mean(),
            'Mean_Difference': diff.mean(),
            'Mean_Pct_Change': (diff.mean() / orig_vals.mean() * 100) if orig_vals.mean() != 0 else np.nan,
            'Original_Sum': orig_vals.sum(),
            'New_Sum': new_vals.sum(),
            'Sum_Difference': new_vals.sum() - orig_vals.sum(),
            'Sum_Pct_Change': ((new_vals.sum() - orig_vals.sum()) / orig_vals.sum() * 100) if orig_vals.sum() != 0 else np.nan,
            'Original_Std': orig_vals.std(),
            'New_Std': new_vals.std(),
            'Std_Difference': new_vals.std() - orig_vals.std(),
            'Max_Abs_Diff': diff.abs().max(),
            'RMSE': np.sqrt((diff ** 2).mean()),
            'Correlation': orig_vals.corr(new_vals)
        }
        stats_list.append(stats)
    
    return pd.DataFrame(stats_list)

# %%
def print_summary_statistics(summary_df: pd.DataFrame):
    """Print formatted summary statistics."""
    print("\n" + "="*80)
    print("COMPARISON SUMMARY - Modified Columns")
    print("="*80)
    print(f"\nNumber of watersheds compared: {len(summary_df)}")
    
    print(f"\n{'Overall Statistics:':<40}")
    print(f"{'  Average Mean Difference:':<40} {summary_df['Mean_Difference'].mean():>10.4f} inches/month")
    print(f"{'  Std Dev of Mean Differences:':<40} {summary_df['Mean_Difference'].std():>10.4f} inches/month")
    print(f"{'  Average Mean % Change:':<40} {summary_df['Mean_Pct_Change'].mean():>10.2f}%")
    print(f"{'  Max Absolute Mean Difference:':<40} {summary_df['Mean_Difference'].abs().max():>10.4f} inches/month")
    print(f"{'  Max Single-Cell Difference:':<40} {summary_df['Max_Abs_Diff'].max():>10.4f} inches/month")
    print(f"{'  Average RMSE:':<40} {summary_df['RMSE'].mean():>10.4f} inches/month")
    print(f"{'  Average Correlation:':<40} {summary_df['Correlation'].mean():>10.4f}")
    
    print("\n" + "-"*80)
    print("Top 10 Watersheds by LARGEST INCREASE in Mean:")
    print("-"*80)
    top_increases = summary_df.nlargest(10, 'Mean_Difference')[
        ['Watershed_ID', 'Original_Mean', 'New_Mean', 'Mean_Difference', 'Mean_Pct_Change']
    ]
    print(top_increases.to_string(index=False, float_format=lambda x: f'{x:.4f}'))
    
    print("\n" + "-"*80)
    print("Top 10 Watersheds by LARGEST DECREASE in Mean:")
    print("-"*80)
    top_decreases = summary_df.nsmallest(10, 'Mean_Difference')[
        ['Watershed_ID', 'Original_Mean', 'New_Mean', 'Mean_Difference', 'Mean_Pct_Change']
    ]
    print(top_decreases.to_string(index=False, float_format=lambda x: f'{x:.4f}'))
    
    print("\n" + "-"*80)
    print("Top 10 Watersheds by Largest Absolute Difference:")
    print("-"*80)
    top_abs = summary_df.nlargest(10, 'Max_Abs_Diff')[
        ['Watershed_ID', 'Original_Mean', 'New_Mean', 'Mean_Difference', 'Max_Abs_Diff']
    ]
    print(top_abs.to_string(index=False, float_format=lambda x: f'{x:.4f}'))

# %%
def create_diagnostic_plots(summary_df: pd.DataFrame, output_dir: str):
    """Create diagnostic plots for comparison."""
    
    # Set style
    sns.set_style("whitegrid")
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    fig.suptitle('CVprecip Comparison Diagnostics', fontsize=16, fontweight='bold')
    
    # 1. Mean difference distribution
    ax = axes[0, 0]
    summary_df['Mean_Difference'].hist(bins=50, ax=ax, edgecolor='black')
    ax.axvline(0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Mean Difference (inches/month)')
    ax.set_ylabel('Frequency')
    ax.set_title('Distribution of Mean Differences')
    ax.grid(alpha=0.3)
    
    # 2. Percent change distribution
    ax = axes[0, 1]
    summary_df['Mean_Pct_Change'].hist(bins=50, ax=ax, edgecolor='black')
    ax.axvline(0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Mean % Change')
    ax.set_ylabel('Frequency')
    ax.set_title('Distribution of % Changes')
    ax.grid(alpha=0.3)
    
    # 3. Scatter: Original vs New means
    ax = axes[0, 2]
    ax.scatter(summary_df['Original_Mean'], summary_df['New_Mean'], alpha=0.5)
    lims = [
        min(summary_df['Original_Mean'].min(), summary_df['New_Mean'].min()),
        max(summary_df['Original_Mean'].max(), summary_df['New_Mean'].max())
    ]
    ax.plot(lims, lims, 'r--', linewidth=2, label='1:1 Line')
    ax.set_xlabel('Original Mean (inches/month)')
    ax.set_ylabel('New Mean (inches/month)')
    ax.set_title('Original vs New Means')
    ax.legend()
    ax.grid(alpha=0.3)
    
    # 4. Mean difference by watershed ID
    ax = axes[1, 0]
    ax.scatter(summary_df['Watershed_ID'], summary_df['Mean_Difference'], alpha=0.5)
    ax.axhline(0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Watershed ID')
    ax.set_ylabel('Mean Difference (inches/month)')
    ax.set_title('Mean Difference by Watershed')
    ax.grid(alpha=0.3)
    
    # 5. RMSE by watershed ID
    ax = axes[1, 1]
    ax.scatter(summary_df['Watershed_ID'], summary_df['RMSE'], alpha=0.5, color='orange')
    ax.set_xlabel('Watershed ID')
    ax.set_ylabel('RMSE (inches/month)')
    ax.set_title('RMSE by Watershed')
    ax.grid(alpha=0.3)
    
    # 6. Correlation by watershed ID
    ax = axes[1, 2]
    ax.scatter(summary_df['Watershed_ID'], summary_df['Correlation'], alpha=0.5, color='green')
    ax.axhline(1.0, color='red', linestyle='--', linewidth=2)
    ax.set_xlabel('Watershed ID')
    ax.set_ylabel('Correlation')
    ax.set_title('Correlation by Watershed')
    ax.set_ylim([0.9, 1.01])
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    
    # Save figure
    plot_path = os.path.join(output_dir, 'comparison_diagnostics.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"\nDiagnostic plots saved to: {plot_path}")
    plt.show()

# %%
def create_cdf_plots(summary_df: pd.DataFrame, output_dir: str):
    """Create CDF plots for raw and percentage differences."""
    
    # Set style
    sns.set_style("whitegrid")
    
    # Create figure with two subplots
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle('Cumulative Distribution Functions of Differences', fontsize=16, fontweight='bold')
    
    # 1. CDF of Raw Mean Differences
    ax = axes[0]
    raw_diff = summary_df['Mean_Difference'].sort_values()
    cdf_raw = np.arange(1, len(raw_diff) + 1) / len(raw_diff)
    
    ax.plot(raw_diff.values, cdf_raw, linewidth=2, color='blue', label='Raw Difference CDF')
    ax.axvline(raw_diff.median(), color='red', linestyle='--', linewidth=2, 
               label=f'Median: {raw_diff.median():.4f}')
    ax.axvline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
    ax.axhline(0.5, color='gray', linestyle=':', alpha=0.5)
    
    ax.set_xlabel('Mean Difference (inches/month)', fontsize=12)
    ax.set_ylabel('Cumulative Probability', fontsize=12)
    ax.set_title('CDF of Raw Mean Differences', fontsize=13)
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 1])
    
    # Add percentile annotations
    percentiles = [0.10, 0.25, 0.50, 0.75, 0.90]
    for p in percentiles:
        val = raw_diff.quantile(p)
        ax.plot(val, p, 'ro', markersize=6)
        ax.annotate(f'{p*100:.0f}%: {val:.3f}', 
                   xy=(val, p), 
                   xytext=(10, 0), 
                   textcoords='offset points',
                   fontsize=9,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.3))
    
    # 2. CDF of Percentage Changes
    ax = axes[1]
    pct_change = summary_df['Mean_Pct_Change'].dropna().sort_values()
    cdf_pct = np.arange(1, len(pct_change) + 1) / len(pct_change)
    
    ax.plot(pct_change.values, cdf_pct, linewidth=2, color='green', label='% Change CDF')
    ax.axvline(pct_change.median(), color='red', linestyle='--', linewidth=2,
               label=f'Median: {pct_change.median():.2f}%')
    ax.axvline(0, color='black', linestyle='-', linewidth=1, alpha=0.5)
    ax.axhline(0.5, color='gray', linestyle=':', alpha=0.5)
    
    ax.set_xlabel('Mean % Change', fontsize=12)
    ax.set_ylabel('Cumulative Probability', fontsize=12)
    ax.set_title('CDF of % Changes', fontsize=13)
    ax.legend(loc='lower right')
    ax.grid(alpha=0.3)
    ax.set_ylim([0, 1])
    
    # Add percentile annotations
    for p in percentiles:
        val = pct_change.quantile(p)
        ax.plot(val, p, 'ro', markersize=6)
        ax.annotate(f'{p*100:.0f}%: {val:.2f}%', 
                   xy=(val, p), 
                   xytext=(10, 0), 
                   textcoords='offset points',
                   fontsize=9,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.3))
    
    plt.tight_layout()
    
    # Save figure
    plot_path = os.path.join(output_dir, 'comparison_cdf.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"\nCDF plots saved to: {plot_path}")
    plt.show()
    
    # Print CDF statistics
    print("\n" + "="*80)
    print("CDF STATISTICS")
    print("="*80)
    print("\nRaw Mean Difference (inches/month):")
    for p in [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]:
        print(f"  {p*100:5.1f}th percentile: {raw_diff.quantile(p):>8.4f}")
    
    print("\nMean % Change:")
    for p in [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]:
        print(f"  {p*100:5.1f}th percentile: {pct_change.quantile(p):>8.2f}%")

# %%
# Main execution
if __name__ == "__main__" or True:  # Allow running in interactive mode
    
    # Load data
    print("="*80)
    print("Loading CVprecip files...")
    print("="*80)
    orig_df = load_cvprecip_data(ORIGINAL_FILE)
    new_df = load_cvprecip_data(NEW_FILE)
    
    # %%
    # Compare
    print("\n" + "="*80)
    print("Performing comparison...")
    print("="*80)
    summary_df = compare_columns(orig_df, new_df)
    
    # %%
    # Print statistics
    print_summary_statistics(summary_df)
    
    # %%
    # Save summary
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_df.to_csv(SUMMARY_CSV, index=False, float_format='%.6f')
    print(f"\n{'='*80}")
    print(f"Detailed comparison saved to: {SUMMARY_CSV}")
    print(f"{'='*80}")
    
    # %%
    # Create diagnostic plots
    print("\nGenerating diagnostic plots...")
    create_diagnostic_plots(summary_df, OUTPUT_DIR)
    
    # %%
    # Create CDF plots
    print("\nGenerating CDF plots...")
    create_cdf_plots(summary_df, OUTPUT_DIR)
    
    # %%
    # Additional interactive exploration
    print("\n" + "="*80)
    print("Summary DataFrame available as 'summary_df'")
    print("Original data available as 'orig_df'")
    print("New data available as 'new_df'")
    print("="*80)

# %%
# Example: Filter watersheds with large changes
# large_changes = summary_df[summary_df['Mean_Pct_Change'].abs() > 5]
# print(f"\nWatersheds with >5% change: {len(large_changes)}")

# %%
# Example: Get specific watershed details
# watershed_id = 1
# ws_stats = summary_df[summary_df['Watershed_ID'] == watershed_id].iloc[0]
# print(f"\nWatershed {watershed_id} statistics:")
# print(ws_stats)