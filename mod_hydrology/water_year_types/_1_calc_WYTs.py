"""
Calculate Water Year Types (WYTs)
=================================
Sacramento 40-30-30 Index and San Joaquin 60-20-20 Index calculations based
on rim-inflow aggregations with recursive index formulas. Supports Product A
(historical validation) and Product B (stochastic 1000-year).

Inputs
------
- Rim-inflow QM time series (rim_inflow calsim_qmap_validation_TS.csv)

Outputs
-------
- <generated>/output/_1_calc_WYTs/Product_A/  (Sac + SJ WYT indices)
- <generated>/output/_1_calc_WYTs/Product_B/  (with --product B)

Dependencies
------------
- utils/paths.py  (data-dir resolution)

Usage
-----
# Process both products with default paths:
    cd ./water_year_types && python _1_calc_WYTs.py

# Process Product A only:
    cd ./water_year_types && python _1_calc_WYTs.py --product A

# Process Product B only:
    cd ./water_year_types && python _1_calc_WYTs.py --product B

# Override input/output paths:
    cd ./water_year_types && python _1_calc_WYTs.py \
        --product A \
        --product_a_input path/to/calsim_qmap_validation_TS.csv \
        --product_a_output path/to/output
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir

_rim_gen = get_module_generated_dir("mod_hydrology/rim_inflow")
_wyt_gen = get_module_generated_dir("mod_hydrology/water_year_types")


# Rim inflow component CalSim names (as they appear in the data)
SAC_COMPONENTS = ['UNIMP_SRBB', 'UNIMP_OROV', 'UNIMP_YUBA', 'UNIMP_FOLS']
SJ_COMPONENTS = ['UNIMP_ST', 'UNIMP_TU', 'UNIMP_ME', 'UNIMP_SJ']

# Product B file name mapping (simple CS3 name only, no VIC name appended)
PRODUCT_B_FILES = {
    'UNIMP_SRBB': 'UNIMP_SRBB_qmo_n{:02d}.csv',
    'UNIMP_OROV': 'UNIMP_OROV_qmo_n{:02d}.csv',
    'UNIMP_YUBA': 'UNIMP_YUBA_qmo_n{:02d}.csv',
    'UNIMP_FOLS': 'UNIMP_FOLS_qmo_n{:02d}.csv',
    'UNIMP_ST':   'UNIMP_ST_qmo_n{:02d}.csv',
    'UNIMP_TU':   'UNIMP_TU_qmo_n{:02d}.csv',
    'UNIMP_ME':   'UNIMP_ME_qmo_n{:02d}.csv',
    'UNIMP_SJ':   'UNIMP_SJ_qmo_n{:02d}.csv',
}

# WYT Thresholds (MAF)
THRESHOLDS = {
    'sacramento': {
        'aji': 0.4,
        'omi': 0.3,
        'c': 5.4,    # Critical threshold
        'd': 6.5,    # Dry threshold (starting value)
        'bn': 7.8,   # Below Normal threshold
        'an': 9.2,   # Above Normal threshold
        'w': 9.2     # Wet threshold
    },
    'san_joaquin': {
        'aji': 0.6,
        'omi': 0.2,
        'c': 2.1,    # Critical threshold
        'd': 2.5,    # Dry threshold (starting value)
        'bn': 3.1,   # Below Normal threshold
        'an': 3.8,   # Above Normal threshold
        'w': 3.8     # Wet threshold
    }
}


def aggregate_flows(df, components, months):
    """
    Aggregate rim inflow components over specified months.
    
    Args:
        df: DataFrame with date index and rim inflow columns
        components: List of column names to sum
        months: List of month numbers to include (1=Jan, 10=Oct, etc.)
    
    Returns:
        Series with water year aggregated flows in MAF
    """
    # Filter to specified months
    df_filtered = df[df.index.month.isin(months)].copy()
    
    # Sum across components (flows are in TAF)
    df_filtered['total'] = df_filtered[components].sum(axis=1)
    
    # Group by water year (Oct-Sep, so WY 2022 = Oct 2021 - Sep 2022)
    # Shift months Oct-Dec (10,11,12) to next year
    df_filtered['water_year'] = df_filtered.index.year
    df_filtered.loc[df_filtered.index.month >= 10, 'water_year'] += 1
    
    # Sum by water year and convert TAF to MAF (divide by 1000)
    annual_totals = df_filtered.groupby('water_year')['total'].sum() / 1000.0
    
    return annual_totals


def calculate_sacramento_index(apr_jul, oct_mar, thresholds, initial_index=None):
    """
    Calculate Sacramento Valley 40-30-30 Index.
    
    Year 1: SacIndex1 = 0.4*AprJul1 + 0.3*OctMar1 + 0.3*prev_year_index
    Years 2+: SacIndexi = 0.4*AprJuli + 0.3*OctMari + 0.3*min(SacIndexi-1, 10)
    
    Args:
        apr_jul: Series of Apr-Jul flows by water year
        oct_mar: Series of Oct-Mar flows by water year
        thresholds: Dict of Sacramento thresholds
        initial_index: Previous year index value for first year calculation
                      If None, uses threshold 'd' = 6.5
    
    Returns:
        Series of Sacramento indices
    """
    if initial_index is None:
        initial_index = thresholds['sacramento']['d']
    
    sac_index = pd.Series(index=apr_jul.index, dtype=float)
    
    # Year 1: use actual previous year index (or default to threshold 'd')
    sac_index.iloc[0] = 0.4 * apr_jul.iloc[0] + 0.3 * oct_mar.iloc[0] + 0.3 * min(initial_index, 10.0)
    
    # Years 2+: use previous year's index (capped at 10)
    for i in range(1, len(sac_index)):
        prev_index = min(sac_index.iloc[i-1], 10.0)
        sac_index.iloc[i] = 0.4 * apr_jul.iloc[i] + 0.3 * oct_mar.iloc[i] + 0.3 * prev_index
    
    return sac_index


def calculate_san_joaquin_index(apr_jul, oct_mar, thresholds, initial_index=None):
    """
    Calculate San Joaquin Valley 60-20-20 Index.
    
    Year 1: SJIndex1 = 0.6*AprJul1 + 0.2*OctMar1 + 0.2*prev_year_index
    Years 2+: SJIndexi = 0.6*AprJuli + 0.2*OctMari + 0.2*min(SJIndexi-1, 4.5)
    
    Args:
        apr_jul: Series of Apr-Jul flows by water year
        oct_mar: Series of Oct-Mar flows by water year
        thresholds: Dict of San Joaquin thresholds
        initial_index: Previous year index value for first year calculation
                      If None, uses threshold 'd' = 2.5
    
    Returns:
        Series of San Joaquin indices
    """
    if initial_index is None:
        initial_index = thresholds['san_joaquin']['d']
    
    sj_index = pd.Series(index=apr_jul.index, dtype=float)
    
    # Year 1: use actual previous year index (or default to threshold 'd')
    sj_index.iloc[0] = 0.6 * apr_jul.iloc[0] + 0.2 * oct_mar.iloc[0] + 0.2 * min(initial_index, 4.5)
    
    # Years 2+: use previous year's index (capped at 4.5)
    for i in range(1, len(sj_index)):
        prev_index = min(sj_index.iloc[i-1], 4.5)
        sj_index.iloc[i] = 0.6 * apr_jul.iloc[i] + 0.2 * oct_mar.iloc[i] + 0.2 * prev_index
    
    return sj_index


def classify_wyt(index_series, thresholds, valley):
    """
    Classify water year types based on index values.
    
    Classification thresholds (lower index = drier):
    - index < c -> Critical (C, 5)
    - c <= index < d -> Dry (D, 4)
    - d <= index < bn -> Below Normal (BN, 3)
    - bn <= index < an -> Above Normal (AN, 2)
    - index >= an -> Wet (W, 1)
    
    Args:
        index_series: Series of flow indices
        thresholds: Dict of thresholds for the valley
        valley: 'sacramento' or 'san_joaquin'
    
    Returns:
        Tuple of (numeric_wyt_series, letter_wyt_series)
    """
    t = thresholds[valley]
    
    wyt_num = pd.Series(index=index_series.index, dtype=int)
    wyt_letter = pd.Series(index=index_series.index, dtype=str)
    
    # Critical (driest)
    mask_c = index_series < t['c']
    wyt_num[mask_c] = 5
    wyt_letter[mask_c] = 'C'
    
    # Dry
    mask_d = (index_series >= t['c']) & (index_series < t['d'])
    wyt_num[mask_d] = 4
    wyt_letter[mask_d] = 'D'
    
    # Below Normal
    mask_bn = (index_series >= t['d']) & (index_series < t['bn'])
    wyt_num[mask_bn] = 3
    wyt_letter[mask_bn] = 'BN'
    
    # Above Normal
    mask_an = (index_series >= t['bn']) & (index_series < t['an'])
    wyt_num[mask_an] = 2
    wyt_letter[mask_an] = 'AN'
    
    # Wet (wettest)
    mask_w = index_series >= t['an']
    wyt_num[mask_w] = 1
    wyt_letter[mask_w] = 'W'
    
    return wyt_num, wyt_letter


def calculate_wyts(df, thresholds, sac_initial_index=None, sj_initial_index=None):
    """
    Calculate WYTs from rim inflow DataFrame.
    
    Args:
        df: DataFrame with date index and rim inflow columns
        thresholds: Dict of WYT thresholds
        sac_initial_index: Sacramento previous year index for first calculation
        sj_initial_index: San Joaquin previous year index for first calculation
    
    Returns:
        DataFrame with columns: water_year, sac_index, sac_wyt, sac_wyt_label, sj_index, sj_wyt, sj_wyt_label
    """
    # Sacramento aggregations
    sac_apr_jul = aggregate_flows(df, SAC_COMPONENTS, [4, 5, 6, 7])
    sac_oct_mar = aggregate_flows(df, SAC_COMPONENTS, [10, 11, 12, 1, 2, 3])
    
    # San Joaquin aggregations
    sj_apr_jul = aggregate_flows(df, SJ_COMPONENTS, [4, 5, 6, 7])
    sj_oct_mar = aggregate_flows(df, SJ_COMPONENTS, [10, 11, 12, 1, 2, 3])
    
    # Calculate indices
    sac_index = calculate_sacramento_index(sac_apr_jul, sac_oct_mar, thresholds, sac_initial_index)
    sj_index = calculate_san_joaquin_index(sj_apr_jul, sj_oct_mar, thresholds, sj_initial_index)
    
    # Classify WYTs (returns numeric and letter codes)
    sac_wyt_num, sac_wyt_letter = classify_wyt(sac_index, thresholds, 'sacramento')
    sj_wyt_num, sj_wyt_letter = classify_wyt(sj_index, thresholds, 'san_joaquin')
    
    # Combine into output DataFrame
    result = pd.DataFrame({
        'water_year': sac_index.index,
        'sac_index': sac_index.values,
        'sac_wyt': sac_wyt_num.values,
        'sac_wyt_label': sac_wyt_letter.values,
        'sj_index': sj_index.values,
        'sj_wyt': sj_wyt_num.values,
        'sj_wyt_label': sj_wyt_letter.values
    })
    
    return result


def process_product_a(input_path, output_dir, thresholds):
    """
    Process Product A (historical validation) data.
    
    Args:
        input_path: Path to calsim_qmap_validation_TS.csv
        output_dir: Directory for output CSV files
        thresholds: Dict of WYT thresholds
    """
    print(f"Processing Product A: {input_path}")
    
    # Read data (long format with CalSim column identifying the component)
    df_long = pd.read_csv(input_path)
    
    # Filter to only the 8 rim inflow components we need
    all_components = SAC_COMPONENTS + SJ_COMPONENTS
    df_long = df_long[df_long['CalSim'].isin(all_components)].copy()
    
    # Create date column
    df_long['date'] = pd.to_datetime(df_long[['Year', 'Month']].assign(Day=1))
    
    # Pivot to wide format: columns are rim inflow components, values are qmap_postAdj
    df_wide = df_long.pivot_table(
        index='date',
        columns='CalSim',
        values='qmap_postAdj'
    )
    
    # Verify we have all components
    missing = set(all_components) - set(df_wide.columns)
    if missing:
        print(f"  WARNING: Missing components: {missing}")
    
    # Calculate WYTs with 1971 initial index values (previous year for 1972 start)
    # From CDEC historical WYT data: 1971 Sac Index = 10.37, SJ Index = 2.89
    wyt_df = calculate_wyts(df_wide, thresholds, 
                           sac_initial_index=10.37, 
                           sj_initial_index=2.89)
    
    # Save separate outputs for Sacramento and San Joaquin
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sacramento WYT
    sac_df = wyt_df[['water_year', 'sac_index', 'sac_wyt', 'sac_wyt_label']].copy()
    sac_df.columns = ['water_year', 'index', 'wyt', 'wyt_label']
    sac_output = output_dir / '_SacWYT.csv'
    sac_df.to_csv(sac_output, index=False)
    print(f"  Saved Sacramento: {sac_output}")
    
    # San Joaquin WYT
    sj_df = wyt_df[['water_year', 'sj_index', 'sj_wyt', 'sj_wyt_label']].copy()
    sj_df.columns = ['water_year', 'index', 'wyt', 'wyt_label']
    sj_output = output_dir / '_SJWYT.csv'
    sj_df.to_csv(sj_output, index=False)
    print(f"  Saved San Joaquin: {sj_output}")
    
    print(f"  Water years: {wyt_df['water_year'].min()} - {wyt_df['water_year'].max()}")
    print(f"  Total years: {len(wyt_df)}")


def process_product_b(input_dir, output_dir, thresholds):
    """
    Process Product B (1000-year stochastic) data.
    Processes 10 x 100-year chunks separately.
    
    Args:
        input_dir: Directory containing *_qmo_n01.csv through *_qmo_n10.csv files
        output_dir: Directory for output CSV files
        thresholds: Dict of WYT thresholds
    """
    print(f"Processing Product B: {input_dir}")
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Process each of 10 chunks
    for chunk_num in range(1, 11):
        print(f"  Processing chunk n{chunk_num:02d} (years {(chunk_num-1)*100 + 1}-{chunk_num*100})...")
        
        # Read all rim inflow components for this chunk
        chunk_data = {}
        
        for component, file_pattern in PRODUCT_B_FILES.items():
            file_name = file_pattern.format(chunk_num)
            file_path = input_path / file_name
            
            if not file_path.exists():
                print(f"    WARNING: Missing file {file_path}")
                continue
            
            # Read the component data
            comp_df = pd.read_csv(file_path)
            comp_df['date'] = pd.to_datetime(comp_df[['Year', 'Month']].assign(Day=1))
            comp_df = comp_df.set_index('date')
            chunk_data[component] = comp_df['qmap_postAdj']
        
        # Combine all components into one DataFrame (aligned by date index)
        df_chunk = pd.DataFrame(chunk_data)
        
        # Verify we have all components
        all_components = SAC_COMPONENTS + SJ_COMPONENTS
        missing = set(all_components) - set(df_chunk.columns)
        if missing:
            print(f"    WARNING: Missing components: {missing}")
        
        # Calculate WYTs for this chunk
        # Use 1921 initial index values (previous year for 1922 start) for first chunk only
        # From CDEC historical WYT data: 1921 Sac Index = 9.20, SJ Index = 3.23
        if chunk_num == 1:
            wyt_df = calculate_wyts(df_chunk, thresholds,
                                   sac_initial_index=9.20,
                                   sj_initial_index=3.23)
        else:
            # For subsequent chunks, use default (threshold 'd') since these are synthetic continuations
            wyt_df = calculate_wyts(df_chunk, thresholds)
        
        # Remap water years to CalSim convention (WY 1922-2021)
        wyt_df['water_year'] = list(range(1922, 1922 + len(wyt_df)))
        
        # Save separate outputs for Sacramento and San Joaquin
        # Sacramento WYT
        sac_df = wyt_df[['water_year', 'sac_index', 'sac_wyt', 'sac_wyt_label']].copy()
        sac_df.columns = ['water_year', 'index', 'wyt', 'wyt_label']
        sac_output = output_path / f'_SacWYT_n{chunk_num:02d}.csv'
        sac_df.to_csv(sac_output, index=False)
        
        # San Joaquin WYT
        sj_df = wyt_df[['water_year', 'sj_index', 'sj_wyt', 'sj_wyt_label']].copy()
        sj_df.columns = ['water_year', 'index', 'wyt', 'wyt_label']
        sj_output = output_path / f'_SJWYT_n{chunk_num:02d}.csv'
        sj_df.to_csv(sj_output, index=False)
        
        print(f"    Saved Sacramento: {sac_output.name}")
        print(f"    Saved San Joaquin: {sj_output.name}")
        print(f"    Water years: {wyt_df['water_year'].min()} - {wyt_df['water_year'].max()}")


def main():
    parser = argparse.ArgumentParser(description='Calculate Water Year Types for CalSim')
    parser.add_argument('--product', choices=['A', 'B', 'both'], default='both',
                        help='Which product to process (default: both)')
    parser.add_argument('--product_a_input', 
                        default=str(_rim_gen / 'output' / '_2_qmap_historical_validation' / 'calsim_qmap_validation_TS.csv'),
                        help='Path to Product A input CSV')
    parser.add_argument('--product_a_output',
                        default=str(_wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_A'),
                        help='Directory for Product A output CSVs')
    parser.add_argument('--product_b_input',
                        default=str(_rim_gen / 'output' / '_3_qmap_product_b'),
                        help='Directory containing Product B input CSVs')
    parser.add_argument('--product_b_output',
                        default=str(_wyt_gen / 'output' / '_1_calc_WYTs' / 'Product_B'),
                        help='Directory for Product B output CSVs')
    
    args = parser.parse_args()
    
    # Use hardcoded thresholds
    print("Using WYT thresholds (MAF):")
    print(f"  Sacramento: {THRESHOLDS['sacramento']}")
    print(f"  San Joaquin: {THRESHOLDS['san_joaquin']}")
    print()
    
    # Process Product A
    if args.product in ['A', 'both']:
        process_product_a(args.product_a_input, args.product_a_output, THRESHOLDS)
        print()
    
    # Process Product B
    if args.product in ['B', 'both']:
        process_product_b(args.product_b_input, args.product_b_output, THRESHOLDS)
        print()
    
    print("Done!")


if __name__ == '__main__':
    main()
