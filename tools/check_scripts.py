"""Pipeline script-convention gate.

Single source of truth for the numbered-pipeline script convention,
used both for a local pre-commit check and by CI
(.github/workflows/lint.yml). For every script in the Product A and
Product B pipelines it enforces four rules:

  1. ASCII only        -- no byte >= 0x80 anywhere (CLAUDE.md hard rule).
  2. No Jupyter cells  -- no ``# %%`` / ``#%%`` cell markers (scripts are
                          CLI, not notebooks).
  3. Header docstring  -- a module docstring containing the ``===``
                          standardized title underline.
  4. pyflakes-clean    -- no unused imports / undefined names, etc.

Inputs       : the Product A + Product B script lists below
               (or paths given as argv to check a subset).
Outputs      : a report on stdout; exit code 0 (clean) or 1 (violations).
Dependencies : pyflakes (see environment.yml pip section).
Usage        : python tools/check_scripts.py            # both lists
               python tools/check_scripts.py path ...   # subset
"""
import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Canonical Product A pipeline (Product_A_Validation_Manifest.md
# section A "End-to-end ordering"). Numbered pipeline scripts only -- shared
# utils/ library modules are not CLI scripts and are exempt from rules 2-3.
PRODUCT_A_SCRIPTS = [
    "mod_reservoir/evaporation/_0_extract_reservoir_database.py",
    "mod_other/miscellaneous/_0_extract_others.py",
    "mod_other/upper_watershed/_0_load_sv.py",
    "mod_forcing/vic/_1_append_wind_wgen_hist.py",
    "mod_forcing/vic/_2_compile_rim_inflows.py",
    "mod_forcing/climate/_1_pp_point_locations.py",
    "mod_forcing/climate/_2_uhh_basin_averages.py",
    "mod_hydrology/calsimhydro/_1_compile_precip.py",
    "mod_hydrology/calsimhydro/_2_compile_et.py",
    "mod_hydrology/calsimhydro_ee/_1_compile_precip_EE.py",
    "mod_hydrology/delta_channel_depletion/_1_compile_precip_DETAW.py",
    "mod_hydrology/small_watersheds/_1_compile_precip_sws.py",
    "mod_hydrology/rim_inflow/_2_qmap_historical_validation.py",
    "mod_hydrology/water_year_types/_1_calc_WYTs.py",
    "mod_hydrology/calsimhydro/_3_postprocess_product_a.py",
    "mod_hydrology/calsimhydro_ee/_2_postprocess_product_a.py",
    "mod_hydrology/delta_channel_depletion/_2_postprocess_product_a.py",
    "mod_hydrology/small_watersheds/_2_postprocess_product_a.py",
    "mod_hydrology/tulare_gw_terms/_1_wyt_monthlyavg.py",
    "mod_reservoir/evaporation/_2_run_reservoir_evap.py",
    "mod_reservoir/storage_curves/_1_wyt_index_curves.py",
    "mod_reservoir/storage_curves/_2_qmap_product_a.py",
    "mod_reservoir/storage_curves/_3_oroville_daily_precip.py",
    "mod_reservoir/storage_curves/_4_oroville_level5.py",
    "mod_other/instream_flows/_1_min_flow_feather.py",
    "mod_other/instream_flows/_2_sjr_rest_req.py",
    "mod_other/miscellaneous/_1_wyt_monthlyavg.py",
    "mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py",
    "mod_other/miscellaneous/_3_hybrid_product_a.py",
    "mod_other/miscellaneous/_4_qmap_product_a.py",
    "mod_other/upper_watershed/_1_wyt_monthlyavg.py",
    "mod_other/upper_watershed/_2_qmap_product_a.py",
    "mod_other/upper_watershed/_3_hybrid_product_a.py",
    "mod_other/upper_watershed/_4_pge_wy_allocation.py",
    "mod_other/upper_watershed/_5_dnp_evaporation.py",
    "mod_other/closure_terms/_1_ct_calculation.py",
    "postprocessing/sv_compile/product_a_historical_validation.py",
]


# Canonical Product B pipeline (Product_B_Production_Manifest.md section A
# "End-to-end ordering"). Numbered pipeline scripts only -- shared utils/
# library modules are exempt; scripts shared between A and B (compile_precip,
# rim_inflow QM historical validation, water_year_types, etc.) live in the
# Product A list above and are not duplicated here.
PRODUCT_B_SCRIPTS = [
    "mod_hydrology/rim_inflow/_3_qmap_productB.py",
    "mod_hydrology/calsimhydro/_4_postprocess_product_b.py",
    "mod_hydrology/calsimhydro_ee/_3_postprocess_product_b.py",
    "mod_hydrology/delta_channel_depletion/_3_postprocess_product_b.py",
    "mod_hydrology/small_watersheds/_3_postprocess_product_b.py",
    "mod_reservoir/storage_curves/_2_qmap_product_b.py",
    "mod_other/upper_watershed/_2_qmap_product_b.py",
    "mod_other/upper_watershed/_3_hybrid_product_b.py",
    "mod_other/miscellaneous/_3_hybrid_product_b.py",
    "mod_other/miscellaneous/_4_qmap_product_b.py",
    "mod_other/day_volume_fractions/_2_generate_product_b.py",
    "postprocessing/sv_compile/product_b_compilation.py",
    "postprocessing/calsim_runs/_productB_pickle_builder.py",
]


def check_ascii(rel, text):
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        for j, ch in enumerate(line, 1):
            if ord(ch) > 127:
                bad.append(f"{rel}:{i}:{j}: non-ASCII U+{ord(ch):04X} {ch!r}")
                break
    return bad


def check_no_cells(rel, text):
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.lstrip()
        if s.startswith("# %%") or s.startswith("#%%"):
            bad.append(f"{rel}:{i}: Jupyter cell marker '{line.strip()}'")
    return bad


def check_header(rel, text):
    try:
        doc = ast.get_docstring(ast.parse(text))
    except SyntaxError as exc:
        return [f"{rel}: SyntaxError parsing for docstring: {exc}"]
    if not doc:
        return [f"{rel}: missing module docstring"]
    if "===" not in doc:
        return [f"{rel}: module docstring lacks the '===' title underline"]
    return []


def check_pyflakes(path):
    proc = subprocess.run([sys.executable, "-m", "pyflakes", str(path)],
                           capture_output=True, text=True)
    if proc.returncode == 0:
        return []
    out = (proc.stdout + proc.stderr).strip().splitlines()
    return [f"  pyflakes: {ln}" for ln in out] or ["  pyflakes: failed"]


def main(argv):
    rels = argv or (PRODUCT_A_SCRIPTS + PRODUCT_B_SCRIPTS)
    failures = []
    checked = 0
    for rel in rels:
        rel = rel.replace("\\", "/")
        path = REPO / rel
        if not path.is_file():
            failures.append(f"{rel}: MISSING (stale list entry or moved)")
            continue
        checked += 1
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
        file_fail = []
        file_fail += check_ascii(rel, text)
        file_fail += check_no_cells(rel, text)
        file_fail += check_header(rel, text)
        file_fail += check_pyflakes(path)
        if file_fail:
            failures.extend(file_fail)

    print(f"check_scripts: {checked} script(s) checked, "
          f"{len(rels)} listed")
    if failures:
        print("RESULT: FAIL")
        for f in failures:
            print("  - " + f)
        return 1
    print("RESULT: PASS - all pipeline scripts conform "
          "(ASCII / no-# %% / === header / pyflakes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
