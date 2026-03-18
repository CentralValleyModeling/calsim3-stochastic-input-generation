"""
Reservoir Evaporation Processing Script (Product A & B)

Processes WGEN gridded climate data to calculate evaporation time series
for CalSim 3.0 reservoirs using the Hargreaves-Samani method.
Automatically finds the nearest weather file for each reservoir.

Usage:
    python _2_run_reservoir_evap.py                         # Product A, all reservoirs
    python _2_run_reservoir_evap.py FOLSM                   # Product A, single reservoir
    python _2_run_reservoir_evap.py FOLSM SHSTA OROVL       # Product A, specific reservoirs
    python _2_run_reservoir_evap.py --Product_B             # Product B, all reservoirs
    python _2_run_reservoir_evap.py --Product_B FOLSM       # Product B, single reservoir

Output (Product A):
    - Individual CSV files: output/_2_run_reservoir_evap/Product_A/individual_reservoirs/{Region}/{CODE}.csv
    - Combined CSV file:    output/_2_run_reservoir_evap/Product_A/combined_evaporation.csv
    - Summary statistics:   output/_2_run_reservoir_evap/Product_A/summary_statistics.csv

Output (Product B):
    - Chunk CSVs: output/_2_run_reservoir_evap/Product_B/reservoir_evaporation_productB_n01.csv ... n10.csv
    - Format: Part B, Part C, Year, Month, Value (long format)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
import time
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.paths import get_module_generated_dir, get_base_dir

_gen = get_module_generated_dir("mod_reservoir/evaporation")

from evaporation import (
    EvaporationCalculator,
    load_climate_data,
    find_nearest_weather_file,
    get_all_reservoir_codes,
    get_reservoir_info
)


def _load_climate_data_product_b(file_path: str) -> pd.DataFrame:
    """
    Load Product B WGEN climate data using a PeriodIndex — consistent with all
    other project scripts that handle the 1000-year stochastic sequence.

    Product B WGEN files use years 1–1008 (below pandas Timestamp min ~1677),
    so date construction into a DatetimeIndex fails.  A daily PeriodIndex
    anchored at 2025-01-01 (368,172 periods) spans the full 1000-year sequence
    and is compatible with pandas resample() for monthly aggregation.
    """
    data = np.loadtxt(file_path)
    dates = pd.period_range(start='2025-01-01', periods=len(data), freq='D')
    return pd.DataFrame({
        'precip_mm': data[:, 3],
        'tmax_c':    data[:, 4],
        'tmin_c':    data[:, 5],
    }, index=dates)


def process_reservoir(
    reservoir_code: str,
    start_date: str = '1921-10-01',
    end_date: str = '2018-09-30',
    output_dir: str = 'output/_2_run_reservoir_evap/Product_A',
    weather_dir: str = '../_00_Data/WGEN/Product_A/1',
    product_b: bool = False,
) -> pd.DataFrame:
    """
    Process one reservoir and save results.

    Parameters:
    -----------
    reservoir_code : str
        Reservoir code
    start_date : str
        Start date for Product A clipping (default: 1921-10-01)
    end_date : str
        End date for Product A clipping (default: 2018-09-30)
    output_dir : str
        Output directory
    weather_dir : str
        Directory containing WGEN met files
    product_b : bool
        If True, skip date clipping and individual file output

    Returns:
    --------
    pd.DataFrame
        Monthly evaporation time series
    """
    try:
        # Find weather file
        weather_file = find_nearest_weather_file(reservoir_code, weather_dir=weather_dir)
        if weather_file is None:
            print("    No weather file found")
            return None

        # Load daily data
        if product_b:
            daily_data = _load_climate_data_product_b(weather_file)
        else:
            daily_data = load_climate_data(weather_file)
            daily_data = daily_data.loc[start_date:end_date]

        # Calculate evaporation
        calc = EvaporationCalculator(reservoir_code)
        evap_df = calc.process_daily_to_monthly(daily_data)

        # Product A only: save individual reservoir CSV
        if not product_b:
            params = get_reservoir_info(reservoir_code)
            region = params['region']
            region_folder = region.replace(' ', '_').replace('/', '_')
            output_path = Path(output_dir) / 'individual_reservoirs' / region_folder
            output_path.mkdir(parents=True, exist_ok=True)
            output_file = output_path / f'{reservoir_code}.csv'
            evap_df.to_csv(output_file)

        return evap_df

    except Exception as e:
        print(f"    Error: {e}")
        return None


def process_reservoirs(
    reservoir_codes: list = None,
    start_date: str = '1921-10-01',
    end_date: str = '2018-09-30',
    output_dir: str = 'output/_2_run_reservoir_evap/Product_A',
    weather_dir: str = '../_00_Data/WGEN/Product_A/1',
    product_b: bool = False,
) -> dict:
    """
    Process multiple reservoirs.

    Parameters:
    -----------
    reservoir_codes : list, optional
        List of reservoir codes. If None, processes all.
    start_date : str
        Start date (Product A clipping)
    end_date : str
        End date (Product A clipping)
    output_dir : str
        Output directory
    weather_dir : str
        Directory containing WGEN met files
    product_b : bool
        If True, use Product B weather data; skip individual files

    Returns:
    --------
    dict
        Dictionary of evaporation DataFrames by reservoir code
    """
    if reservoir_codes is None:
        reservoir_codes = get_all_reservoir_codes()

    product_label = "Product B" if product_b else "Product A"
    print("="*80)
    print(f"{product_label} Reservoir Evaporation Processing")
    print("="*80)
    if not product_b:
        print(f"Period: {start_date} to {end_date}")
    print(f"Reservoirs: {len(reservoir_codes)}")
    print(f"Weather:  {weather_dir}")
    print(f"Output:   {output_dir}")
    print("="*80)

    results = {}
    start_time = time.time()

    for i, code in enumerate(reservoir_codes, 1):
        print(f"[{i:3d}/{len(reservoir_codes)}] {code:6s}: ", end='', flush=True)

        evap_df = process_reservoir(
            code, start_date, end_date, output_dir,
            weather_dir=weather_dir, product_b=product_b
        )

        if evap_df is not None:
            results[code] = evap_df
            annual_avg = evap_df['evaporation_in'].mean() * 12
            print(f"OK {len(evap_df):4d} months | {annual_avg:5.1f} in/yr")
        else:
            print(f"FAILED")

    elapsed = time.time() - start_time

    print("\n" + "="*80)
    print(f"Completed: {len(results)}/{len(reservoir_codes)} reservoirs")
    print(f"Time: {elapsed:.1f} seconds ({elapsed/len(reservoir_codes):.2f} s/reservoir)")
    print("="*80)

    return results


def create_combined_output(
    results: dict,
    output_file: str = 'output/_2_run_reservoir_evap/Product_A/combined_evaporation.csv'
):
    """
    Combine all reservoir results into a single wide-format file.

    Parameters:
    -----------
    results : dict
        Dictionary of evaporation DataFrames
    output_file : str
        Output CSV file path
    """
    if len(results) == 0:
        return

    # Create wide format DataFrame
    all_data = []
    for code, df in results.items():
        df_copy = df[['evaporation_in']].copy()
        df_copy.columns = [code]
        all_data.append(df_copy)

    combined = pd.concat(all_data, axis=1)

    # Save
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output_file)

    print(f"\nCombined output: {output_file}")
    print(f"  {combined.shape[0]} months × {combined.shape[1]} reservoirs")


def create_summary_statistics(
    results: dict,
    output_file: str = 'output/_2_run_reservoir_evap/Product_A/summary_statistics.csv'
):
    """
    Create summary statistics for all reservoirs.

    Parameters:
    -----------
    results : dict
        Dictionary of evaporation DataFrames
    output_file : str
        Output CSV file path
    """
    if len(results) == 0:
        return

    summary_data = []

    for code, df in results.items():
        params = get_reservoir_info(code)

        summary_data.append({
            'reservoir': code,
            'latitude': params['latitude'],
            'longitude': params['longitude'],
            'elevation_ft': params['elevation_ft'],
            'mean_monthly_in': df['evaporation_in'].mean(),
            'annual_total_in': df['evaporation_in'].mean() * 12,
            'min_monthly_in': df['evaporation_in'].min(),
            'max_monthly_in': df['evaporation_in'].max()
        })

    summary_df = pd.DataFrame(summary_data)
    summary_df = summary_df.sort_values('reservoir')

    # Save
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_file, index=False)

    print(f"\nSummary statistics: {output_file}")

    # Print summary
    print(f"\nStatistics:")
    print(f"  Mean annual evaporation: {summary_df['annual_total_in'].mean():.2f} in/yr")
    print(f"  Range: {summary_df['annual_total_in'].min():.2f} - {summary_df['annual_total_in'].max():.2f} in/yr")


def create_product_b_chunk_outputs(
    results: dict,
    output_dir: str = 'output/_2_run_reservoir_evap/Product_B'
):
    """
    Write Product B evaporation into 10 long-format chunk CSVs (100 WYs each).
    Skips first 9 months (Jan-Sep of synthetic year 1) to align to Oct WY start.
    Template dates: Oct 1921 - Sep 2021 (WY1922-WY2021).
    Output format columns: Part B, Part C, Year, Month, Value
    """
    if not results:
        return
    months_per_chunk = 1200   # 100 WYs × 12 months
    skip_months = 9            # Jan-Sep of synthetic year 1
    total_chunks = 10
    total_needed = skip_months + months_per_chunk * total_chunks

    date_template = pd.date_range('1921-10-31', periods=months_per_chunk, freq='M')
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"\nWriting Product B chunk files ({total_chunks} chunks × {months_per_chunk} months)...")
    for i in range(total_chunks):
        rows = []
        for code, df in results.items():
            vals = df['evaporation_in'].values
            if len(vals) < total_needed:
                raise ValueError(f"{code}: need {total_needed} months, got {len(vals)}")
            chunk_vals = vals[skip_months + i * months_per_chunk:
                              skip_months + (i + 1) * months_per_chunk]
            part_b = f"ER_{code}"
            for j, val in enumerate(chunk_vals):
                rows.append({
                    'Part B': part_b,
                    'Part C': 'EVAPORATION-RATE',
                    'Year':  int(date_template[j].year),
                    'Month': int(date_template[j].month),
                    'Value': val,
                })
        chunk_df = pd.DataFrame(rows, columns=['Part B', 'Part C', 'Year', 'Month', 'Value'])
        out_file = output_path / f"reservoir_evaporation_productB_n{i+1:02d}.csv"
        chunk_df.to_csv(out_file, index=False)
        print(f"  Chunk {i+1:02d}/10: {out_file.name} ({len(results)} reservoirs)")
    print(f"Product B output: {output_dir}")


def create_temperature_range_boxplot(
    output_dir: str = 'output/_2_run_reservoir_evap/Product_A'
):
    """
    Create boxplot comparing average daily temperature range (tmax - tmin)
    between Original (Excel/validation) and Product A data, by region.

    For Original: uses monthly-averaged tmax/tmin from validation detail CSVs.
    For Product A: loads daily WGEN data, computes daily DTR, then monthly average.

    Parameters:
    -----------
    output_dir : str
        Output directory for the figure
    """
    output_path = Path(output_dir)

    # Load validation results for region mapping
    val_file = _gen / 'output' / '_1_excel_to_python_validation' / 'validation_results.csv'
    if not val_file.exists():
        print("\nWarning: Validation results not found. Run 1_run_validation.py first.")
        return

    val_df = pd.read_csv(val_file)
    reservoir_details_dir = _gen / 'output' / '_1_excel_to_python_validation' / 'reservoir_details'

    print("\n" + "="*80)
    print("Creating Monthly Temperature Range Comparison Figure")
    print("="*80)

    # Store mean DTR per reservoir: {source: {region: [values]}}
    dtr_data = {
        'Original': {'Sacramento Valley': [], 'San Joaquin Valley': [], 'Other': []},
        'Product A': {'Sacramento Valley': [], 'San Joaquin Valley': [], 'Other': []}
    }

    for _, row in val_df.iterrows():
        res_code = row['reservoir_code']
        region = row['region']

        # --- Original (validation detail CSV) ---
        detail_file = reservoir_details_dir / f"{res_code}.csv"
        if detail_file.exists():
            detail_df = pd.read_csv(detail_file)
            detail_df['date'] = pd.to_datetime(detail_df['date'])
            filtered = detail_df[
                (detail_df['date'] >= '1921-10-01') &
                (detail_df['date'] <= '2018-09-30')
            ]
            if len(filtered) > 0 and 'tmax_c' in filtered.columns and 'tmin_c' in filtered.columns:
                orig_dtr = (filtered['tmax_c'] - filtered['tmin_c']).mean()
                dtr_data['Original'][region].append(orig_dtr)

        # --- Product A (daily WGEN data) ---
        try:
            weather_file = find_nearest_weather_file(res_code)
            if weather_file is not None:
                daily = load_climate_data(weather_file)
                daily = daily.loc['1921-10-01':'2018-09-30']
                if len(daily) > 0:
                    # Aggregate to monthly means first, then compute range
                    try:
                        monthly = daily.resample('ME').mean()
                    except ValueError:
                        monthly = daily.resample('M').mean()
                    monthly_dtr = monthly['tmax_c'] - monthly['tmin_c']
                    pa_dtr_mean = monthly_dtr.mean()
                    dtr_data['Product A'][region].append(pa_dtr_mean)
        except Exception as e:
            print(f"    {res_code} Product A DTR error: {e}")

    n_orig = sum(len(v) for v in dtr_data['Original'].values())
    n_pa = sum(len(v) for v in dtr_data['Product A'].values())
    print(f"Original reservoirs loaded: {n_orig}")
    print(f"Product A reservoirs loaded: {n_pa}")

    if n_orig == 0 or n_pa == 0:
        print("Insufficient data for temperature range comparison.")
        return

    # --- Create figure ---
    fig, ax = plt.subplots(figsize=(6.5, 4))

    regions = ['Sacramento Valley', 'San Joaquin Valley', 'Other']
    region_colors = ['#1f77b4', '#ff7f0e', '#2ca02c']

    positions_list = []
    labels = []

    for i, (region, color) in enumerate(zip(regions, region_colors)):
        orig_vals = dtr_data['Original'][region]
        pa_vals = dtr_data['Product A'][region]

        if len(orig_vals) == 0 and len(pa_vals) == 0:
            continue

        pos_orig = i * 3
        pos_pa = i * 3 + 1

        if len(orig_vals) > 0:
            ax.boxplot(
                [orig_vals], positions=[pos_orig], widths=0.7,
                patch_artist=True, showfliers=False,
                boxprops=dict(facecolor=color, alpha=0.4, edgecolor=color, linewidth=1),
                medianprops=dict(color='darkred', linewidth=1.5),
                whiskerprops=dict(color=color, linewidth=1),
                capprops=dict(color=color, linewidth=1)
            )

        if len(pa_vals) > 0:
            ax.boxplot(
                [pa_vals], positions=[pos_pa], widths=0.7,
                patch_artist=True, showfliers=False,
                boxprops=dict(facecolor=color, alpha=0.9, edgecolor=color, linewidth=1),
                medianprops=dict(color='darkred', linewidth=1.5),
                whiskerprops=dict(color=color, linewidth=1),
                capprops=dict(color=color, linewidth=1)
            )

        positions_list.append((pos_orig + pos_pa) / 2)
        n_res = max(len(orig_vals), len(pa_vals))
        labels.append(f"{region}\n(n={n_res} reservoirs)")

    # Legend
    legend_elements = [
        Patch(facecolor='gray', alpha=0.4, edgecolor='black', linewidth=1, label='Original (Excel)'),
        Patch(facecolor='gray', alpha=0.9, edgecolor='black', linewidth=1, label='Product A (WGEN)')
    ]
    ax.legend(handles=legend_elements, fontsize=7, loc='upper left', framealpha=0.9)

    ax.set_xticks(positions_list)
    ax.set_xticklabels(labels, fontsize=7)
    ax.tick_params(axis='y', labelsize=7)
    ax.set_ylabel('Mean Monthly Temperature Range (°C)', fontsize=7, fontweight='bold')
    ax.set_title(
        'Monthly Temperature Range (Tmax − Tmin) by Region\n'
        'Average per Reservoir for Oct 1921 – Sep 2018',
        fontsize=7, fontweight='bold', pad=10
    )
    ax.grid(True, alpha=0.3, axis='y')

    # Summary statistics annotation
    all_orig = [v for vals in dtr_data['Original'].values() for v in vals]
    all_pa = [v for vals in dtr_data['Product A'].values() for v in vals]

    stats_text = (
        f"Original:   {np.min(all_orig):.1f} – {np.max(all_orig):.1f} °C  "
        f"(mean: {np.mean(all_orig):.1f})\n"
        f"Product A:  {np.min(all_pa):.1f} – {np.max(all_pa):.1f} °C  "
        f"(mean: {np.mean(all_pa):.1f})"
    )
    ax.text(
        0.98, 0.98, stats_text, transform=ax.transAxes,
        bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.85),
        fontsize=7, verticalalignment='top', horizontalalignment='right',
        family='monospace'
    )

    plt.tight_layout()

    fig_dir = output_path / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)
    output_file = fig_dir / 'temperature_range_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved: {output_file}")
    plt.close()


def create_climate_boxplots(
    output_dir: str = 'output/_2_run_reservoir_evap/Product_A'
):
    """
    Create boxplots of average monthly precipitation, tmin, and tmax
    comparing Original (Excel/validation) and Product A (WGEN) by region.

    Original tmin/tmax from validation detail CSVs (monthly averages).
    Product A from WGEN daily files aggregated to monthly.
    Precipitation only available from Product A WGEN data.

    Parameters:
    -----------
    output_dir : str
        Output directory for the figure
    """
    output_path = Path(output_dir)

    val_file = _gen / 'output' / '_1_excel_to_python_validation' / 'validation_results.csv'
    if not val_file.exists():
        print("\nWarning: Validation results not found. Run 1_run_validation.py first.")
        return

    val_df = pd.read_csv(val_file)
    reservoir_details_dir = _gen / 'output' / '_1_excel_to_python_validation' / 'reservoir_details'

    print("\n" + "="*80)
    print("Creating Climate Variable Comparison Figures")
    print("="*80)

    # Data structure: {variable: {source: {region: [mean_values]}}}
    regions = ['Sacramento Valley', 'San Joaquin Valley', 'Other']
    variables = {
        'tmin_c':    {'label': 'Avg Monthly Tmin (\u00b0C)',  'has_original': True},
        'tmax_c':    {'label': 'Avg Monthly Tmax (\u00b0C)',  'has_original': True},
    }
    climate_data = {}
    for var in variables:
        climate_data[var] = {
            'Original':  {r: [] for r in regions},
            'Product A': {r: [] for r in regions}
        }

    for _, row in val_df.iterrows():
        res_code = row['reservoir_code']
        region = row['region']

        # --- Original (validation detail CSV): tmin, tmax only ---
        detail_file = reservoir_details_dir / f"{res_code}.csv"
        if detail_file.exists():
            detail_df = pd.read_csv(detail_file)
            detail_df['date'] = pd.to_datetime(detail_df['date'])
            filtered = detail_df[
                (detail_df['date'] >= '1921-10-01') &
                (detail_df['date'] <= '2018-09-30')
            ]
            if len(filtered) > 0:
                if 'tmin_c' in filtered.columns:
                    climate_data['tmin_c']['Original'][region].append(
                        filtered['tmin_c'].mean()
                    )
                if 'tmax_c' in filtered.columns:
                    climate_data['tmax_c']['Original'][region].append(
                        filtered['tmax_c'].mean()
                    )

        # --- Product A (daily WGEN data): precip, tmin, tmax ---
        try:
            weather_file = find_nearest_weather_file(res_code)
            if weather_file is not None:
                daily = load_climate_data(weather_file)
                daily = daily.loc['1921-10-01':'2018-09-30']
                if len(daily) > 0:
                    try:
                        monthly = daily.resample('ME').mean()
                    except ValueError:
                        monthly = daily.resample('M').mean()
                    for var in variables:
                        if var in monthly.columns:
                            climate_data[var]['Product A'][region].append(
                                monthly[var].mean()
                            )
        except Exception as e:
            print(f"    {res_code} climate load error: {e}")

    # --- Create 1×2 figure ---
    fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.5))
    region_colors = ['#1f77b4', '#ff7f0e', '#2ca02c']

    for ax, (var, var_info) in zip(axes, variables.items()):
        positions_list = []
        labels = []
        has_orig = var_info['has_original']
        spacing = 3 if has_orig else 2

        for i, (region, color) in enumerate(zip(regions, region_colors)):
            pa_vals = climate_data[var]['Product A'][region]
            orig_vals = climate_data[var]['Original'][region] if has_orig else []

            if len(pa_vals) == 0 and len(orig_vals) == 0:
                continue

            if has_orig:
                pos_orig = i * spacing
                pos_pa = i * spacing + 1

                if len(orig_vals) > 0:
                    ax.boxplot(
                        [orig_vals], positions=[pos_orig], widths=0.7,
                        patch_artist=True, showfliers=False,
                        boxprops=dict(facecolor=color, alpha=0.4, edgecolor=color, linewidth=1),
                        medianprops=dict(color='darkred', linewidth=1.5),
                        whiskerprops=dict(color=color, linewidth=1),
                        capprops=dict(color=color, linewidth=1)
                    )
                if len(pa_vals) > 0:
                    ax.boxplot(
                        [pa_vals], positions=[pos_pa], widths=0.7,
                        patch_artist=True, showfliers=False,
                        boxprops=dict(facecolor=color, alpha=0.9, edgecolor=color, linewidth=1),
                        medianprops=dict(color='darkred', linewidth=1.5),
                        whiskerprops=dict(color=color, linewidth=1),
                        capprops=dict(color=color, linewidth=1)
                    )
                positions_list.append((pos_orig + pos_pa) / 2)
            else:
                pos = i * spacing
                if len(pa_vals) > 0:
                    ax.boxplot(
                        [pa_vals], positions=[pos], widths=0.7,
                        patch_artist=True, showfliers=False,
                        boxprops=dict(facecolor=color, alpha=0.9, edgecolor=color, linewidth=1),
                        medianprops=dict(color='darkred', linewidth=1.5),
                        whiskerprops=dict(color=color, linewidth=1),
                        capprops=dict(color=color, linewidth=1)
                    )
                positions_list.append(pos)

            n_res = max(len(pa_vals), len(orig_vals))
            labels.append(f"{region}\n(n={n_res})")

        ax.set_xticks(positions_list)
        ax.set_xticklabels(labels, fontsize=7)
        ax.tick_params(axis='y', labelsize=7)
        ax.set_ylabel(var_info['label'], fontsize=7, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='y')

    # Shared title
    fig.suptitle(
        'Climate Variable Comparison by Region (Oct 1921 \u2013 Sep 2018)',
        fontsize=7, fontweight='bold', y=1.02
    )

    # Legend on first axis
    legend_elements = [
        Patch(facecolor='gray', alpha=0.4, edgecolor='black', linewidth=1, label='Original (Excel)'),
        Patch(facecolor='gray', alpha=0.9, edgecolor='black', linewidth=1, label='Product A (WGEN)')
    ]
    axes[0].legend(handles=legend_elements, fontsize=7, loc='upper left', framealpha=0.9)

    plt.tight_layout()

    fig_dir = output_path / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)
    output_file = fig_dir / 'climate_variable_comparison.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved: {output_file}")
    plt.close()


def create_annual_boxplot(
    output_dir: str = 'output/_2_run_reservoir_evap/Product_A'
):
    """
    Create annual evaporation distribution boxplot comparing Excel, Validation, and Product A.
    
    Parameters:
    -----------
    output_dir : str
        Output directory containing product_a and validation data
    """
    output_path = Path(output_dir)
    
    # Load validation results
    val_file = _gen / 'output' / '_1_excel_to_python_validation' / 'validation_results.csv'
    if not val_file.exists():
        print("\nWarning: Validation results not found. Run 1_run_validation.py first.")
        return
    
    val_df = pd.read_csv(val_file)
    
    print("\n" + "="*80)
    print("Creating Annual Evaporation Distribution Figure")
    print("="*80)
    
    reservoir_details_dir = _gen / 'output' / '_1_excel_to_python_validation' / 'reservoir_details'
    product_a_dir = output_path / 'individual_reservoirs'
    
    # Store annual average per reservoir
    annual_avg_data = {
        'Excel': {'Sacramento Valley': [], 'San Joaquin Valley': [], 'Other': []},
        'Validation': {'Sacramento Valley': [], 'San Joaquin Valley': [], 'Other': []},
        'Product A': {'Sacramento Valley': [], 'San Joaquin Valley': [], 'Other': []}
    }
    
    # Load validation data (Excel and Python validation)
    for idx, row in val_df.iterrows():
        res_code = row['reservoir_code']
        region = row['region']
        detail_file = reservoir_details_dir / f"{res_code}.csv"
        
        if detail_file.exists():
            detail_df = pd.read_csv(detail_file)
            detail_df['date'] = pd.to_datetime(detail_df['date'])
            
            # Filter to Oct 1921 - Sep 2018
            filtered = detail_df[(detail_df['date'] >= '1921-10-01') & 
                                (detail_df['date'] <= '2018-09-30')]
            
            if len(filtered) > 0:
                # Calculate annual totals (water years)
                filtered = filtered.copy()
                filtered['water_year'] = filtered['date'].apply(
                    lambda x: x.year if x.month < 10 else x.year + 1
                )
                
                # Calculate mean annual evaporation for this reservoir
                excel_annual_avg = filtered.groupby('water_year')['excel_evap_in'].sum().mean()
                python_annual_avg = filtered.groupby('water_year')['python_evap_in'].sum().mean()
                
                annual_avg_data['Excel'][region].append(excel_annual_avg)
                annual_avg_data['Validation'][region].append(python_annual_avg)
    
    # Load Product A data
    for region_name in ['Sacramento_Valley', 'San_Joaquin_Valley', 'Other']:
        region_display = region_name.replace('_', ' ')
        region_dir = product_a_dir / region_name
        
        if region_dir.exists():
            for res_file in region_dir.glob('*.csv'):
                res_code = res_file.stem
                
                # Check if this reservoir is in our validation set
                if res_code in val_df['reservoir_code'].values:
                    pa_df = pd.read_csv(res_file)
                    
                    # Handle date column (might be 'Unnamed: 0' or 'date')
                    if 'Unnamed: 0' in pa_df.columns:
                        pa_df['date'] = pd.to_datetime(pa_df['Unnamed: 0'])
                    else:
                        pa_df['date'] = pd.to_datetime(pa_df['date'])
                    
                    # Filter to Oct 1921 - Sep 2018
                    pa_filtered = pa_df[(pa_df['date'] >= '1921-10-01') & 
                                       (pa_df['date'] <= '2018-09-30')]
                    
                    if len(pa_filtered) > 0:
                        # Calculate annual totals
                        pa_filtered = pa_filtered.copy()
                        pa_filtered['water_year'] = pa_filtered['date'].apply(
                            lambda x: x.year if x.month < 10 else x.year + 1
                        )
                        pa_annual_avg = pa_filtered.groupby('water_year')['evaporation_in'].sum().mean()
                        annual_avg_data['Product A'][region_display].append(pa_annual_avg)
    
    print(f"Excel data loaded: {sum(len(v) for v in annual_avg_data['Excel'].values())} reservoirs")
    print(f"Validation data loaded: {sum(len(v) for v in annual_avg_data['Validation'].values())} reservoirs")
    print(f"Product A data loaded: {sum(len(v) for v in annual_avg_data['Product A'].values())} reservoirs")
    
    # Create figure with three boxplots per region
    fig, ax = plt.subplots(figsize=(6.5, 4))
    
    regions = ['Sacramento Valley', 'San Joaquin Valley', 'Other']
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']
    positions_list = []
    labels = []
    
    # Create three side-by-side boxplots for each region
    for i, (region, color) in enumerate(zip(regions, colors)):
        excel_data = annual_avg_data['Excel'][region]
        validation_data = annual_avg_data['Validation'][region]
        product_a_data = annual_avg_data['Product A'][region]
        
        if len(excel_data) > 0:
            pos_excel = i * 4
            pos_validation = i * 4 + 0.7
            pos_product_a = i * 4 + 1.4
            
            # Excel boxplot (lightest)
            bp1 = ax.boxplot([excel_data], positions=[pos_excel], widths=0.6,
                             patch_artist=True, showfliers=False,
                             boxprops=dict(facecolor=color, alpha=0.3, edgecolor=color, linewidth=1),
                             medianprops=dict(color='darkred', linewidth=1.5),
                             whiskerprops=dict(color=color, linewidth=1),
                             capprops=dict(color=color, linewidth=1))
            
            # Validation Python boxplot (medium)
            bp2 = ax.boxplot([validation_data], positions=[pos_validation], widths=0.6,
                             patch_artist=True, showfliers=False,
                             boxprops=dict(facecolor=color, alpha=0.6, edgecolor=color, linewidth=1),
                             medianprops=dict(color='darkred', linewidth=1.5),
                             whiskerprops=dict(color=color, linewidth=1),
                             capprops=dict(color=color, linewidth=1))
            
            # Product A boxplot (darkest)
            bp3 = ax.boxplot([product_a_data], positions=[pos_product_a], widths=0.6,
                             patch_artist=True, showfliers=False,
                             boxprops=dict(facecolor=color, alpha=0.95, edgecolor=color, linewidth=1),
                             medianprops=dict(color='darkred', linewidth=1.5),
                             whiskerprops=dict(color=color, linewidth=1),
                             capprops=dict(color=color, linewidth=1))
            
            positions_list.append((pos_excel + pos_product_a) / 2)
            labels.append(f"{region}\n(n={len(excel_data)} reservoirs)")
    
    # Add legend
    legend_elements = [
        Patch(facecolor='gray', alpha=0.3, edgecolor='black', linewidth=1, label='Original Excel'),
        Patch(facecolor='gray', alpha=0.6, edgecolor='black', linewidth=1, label='Validation (Python)'),
        Patch(facecolor='gray', alpha=0.95, edgecolor='black', linewidth=1, label='Product A')
    ]
    ax.legend(handles=legend_elements, fontsize=7, loc='upper left', framealpha=0.9)
    
    ax.set_xticks(positions_list)
    ax.set_xticklabels(labels, fontsize=7)
    ax.tick_params(axis='y', labelsize=7)
    ax.set_ylabel('Annual Average Evaporation (inches/year)', fontsize=7, fontweight='bold')
    ax.set_title('Annual Reservoir Evaporation Distribution by Region\nAverage per Reservoir for Oct 1921 - Sep 2018 (97 Water Years)', 
                fontsize=7, fontweight='bold', pad=10)
    ax.grid(True, alpha=0.3, axis='y')
    
    # Add statistics
    all_excel = [v for vals in annual_avg_data['Excel'].values() for v in vals]
    all_validation = [v for vals in annual_avg_data['Validation'].values() for v in vals]
    all_product_a = [v for vals in annual_avg_data['Product A'].values() for v in vals]
    
    stats_text = f"Excel:      {np.min(all_excel):.1f} - {np.max(all_excel):.1f} in/yr (mean: {np.mean(all_excel):.1f})\n"
    stats_text += f"Validation: {np.min(all_validation):.1f} - {np.max(all_validation):.1f} in/yr (mean: {np.mean(all_validation):.1f})\n"
    stats_text += f"Product A:  {np.min(all_product_a):.1f} - {np.max(all_product_a):.1f} in/yr (mean: {np.mean(all_product_a):.1f})"
    ax.text(0.98, 0.98, stats_text, transform=ax.transAxes,
           bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.85),
           fontsize=7, verticalalignment='top', horizontalalignment='right',
           family='monospace')
    
    plt.tight_layout()
    
    # Save figure
    fig_dir = output_path / 'figures'
    fig_dir.mkdir(parents=True, exist_ok=True)
    output_file = fig_dir / 'annual_evaporation_distribution.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\nFigure saved: {output_file}")
    plt.close()


def main():
    """Main entry point."""
    product_b = '--Product_B' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if product_b:
        output_dir = str(_gen / 'output' / '_2_run_reservoir_evap' / 'Product_B')
        weather_dir = str(get_base_dir() / 'WGEN' / 'Product_B' / '1')
    else:
        output_dir = str(_gen / 'output' / '_2_run_reservoir_evap' / 'Product_A')
        weather_dir = str(get_base_dir() / 'WGEN' / 'Product_A' / '1')

    product_label = "Product B (stochastic)" if product_b else "Product A (1921-2018)"
    print(f"\n_2_run_reservoir_evap.py  |  {product_label}")
    print(f"  weather : {weather_dir}")
    print(f"  output  : {output_dir}\n")

    if args:
        codes = [code.upper() for code in args]
        print(f"\nProcessing {len(codes)} reservoir(s): {', '.join(codes)}\n")
        results = process_reservoirs(
            reservoir_codes=codes,
            output_dir=output_dir,
            weather_dir=weather_dir,
            product_b=product_b,
        )
    else:
        print("\nProcessing all reservoirs...\n")
        results = process_reservoirs(
            output_dir=output_dir,
            weather_dir=weather_dir,
            product_b=product_b,
        )

    if len(results) > 0:
        if product_b:
            create_product_b_chunk_outputs(results, output_dir=output_dir)
        else:
            create_combined_output(
                results,
                output_file=str(Path(output_dir) / 'combined_evaporation.csv')
            )
            create_summary_statistics(
                results,
                output_file=str(Path(output_dir) / 'summary_statistics.csv')
            )
            create_annual_boxplot(output_dir=output_dir)
            create_temperature_range_boxplot(output_dir=output_dir)
            create_climate_boxplots(output_dir=output_dir)

        print("\n" + "="*80)
        print("Processing complete!")
        print("="*80)


if __name__ == '__main__':
    main()
