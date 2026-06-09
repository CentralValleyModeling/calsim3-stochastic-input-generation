"""Pipeline script-convention gate.

Single source of truth for the numbered-pipeline script convention,
used both for a local pre-commit check and by CI
(.github/workflows/lint.yml). For every script in the Product A and
Product B pipelines it enforces five rules:

Per-file rules (run on every gated script):

  1. ASCII only         -- no byte >= 0x80 anywhere (CLAUDE.md hard rule).
  2. No Jupyter cells   -- no ``# %%`` / ``#%%`` cell markers (scripts are
                           CLI, not notebooks).
  3. Header docstring   -- a module docstring containing the ``===``
                           standardized title underline.
  4. pyflakes-clean     -- no unused imports / undefined names, etc.
  5. No raw HecDss.Open -- route DSS opens through ``utils.dss_io.open_dss``
                           (handles Windows long-path junction + the
                           256-char Fortran CNAME limit). Only
                           ``utils/dss_io.py`` + ``utils/dss_pickle_builder.py``
                           are sanctioned raw callers (neither is gated).
  6. No hard-coded data paths -- resolve data locations via utils.paths
                           helpers, never a literal ``../../data/``.
  7. Reference CSVs exist -- any ``"reference" / "X.csv"`` a script names
                           must exist on disk under the script's reference/.
  8. No deprecated pandas freq aliases -- use the pandas 2.2 forms
                           ('ME','YE','QE','YS-OCT', ...) not 'M'/'A'/'AS-OCT'.
  9. PBIAS sign         -- PBIAS must be 100 * sum(sim - obs) / sum(obs)
                           (positive = overestimation); reject (obs - sim).
 10. No np.random.seed  -- QM determinism comes from the single QMAP_SEED
                           in utils/quantile_mapping.py; do not re-seed.

Plus one cross-cutting check (only run during a full sweep):

 11. Manifest-drift cross-check -- every pipeline-shaped .py file on disk
     (numbered ``_N_*.py`` under mod_*/, all ``*.py`` under postprocessing/)
     must be listed in PRODUCT_A_SCRIPTS, PRODUCT_B_SCRIPTS, or
     EXEMPT_SCRIPTS; conversely, no listed entry may be missing from disk.

Inputs       : the Product A + Product B script lists below
               (or paths given as argv to check a subset; subset runs skip
               the manifest-drift cross-check).
Outputs      : a report on stdout; exit code 0 (clean) or 1 (violations).
Dependencies : pyflakes (see environment.yml pip section).
Usage        : python utils/check_scripts.py            # both lists + drift
               python utils/check_scripts.py path ...   # subset (no drift)
"""
import ast
import re
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
    "mod_reservoir/storage_curves/_2_qmap.py",
    "mod_reservoir/storage_curves/_3_oroville_daily_precip.py",
    "mod_reservoir/storage_curves/_4_oroville_level5.py",
    "mod_other/instream_flows/_1_min_flow_feather.py",
    "mod_other/instream_flows/_2_sjr_rest_req.py",
    "mod_other/miscellaneous/_1_wyt_monthlyavg.py",
    "mod_other/miscellaneous/_2_DeltaAccretionForNDOI.py",
    "mod_other/miscellaneous/_3_hybrid.py",
    "mod_other/miscellaneous/_4_qmap.py",
    "mod_other/upper_watershed/_1_wyt_monthlyavg.py",
    "mod_other/upper_watershed/_2_qmap.py",
    "mod_other/upper_watershed/_3_hybrid.py",
    "mod_other/upper_watershed/_4_pge_wy_allocation.py",
    "mod_other/upper_watershed/_5_dnp_evaporation.py",
    "mod_other/closure_terms/_1_ct_calculation.py",
    "postprocessing/sv_compile/product_a_historical_validation.py",
    "postprocessing/calsim_runs/_productA_pickle_builder.py",
    "postprocessing/calsim_runs/_productA_postproc.py",
    "postprocessing/calsim_runs/_historical_modified_pickle_builder.py",
    "postprocessing/calsim_runs/_historical_modified_postproc.py",
]


# Canonical Product B pipeline (Product_B_Production_Manifest.md section A
# "End-to-end ordering"). Numbered pipeline scripts only -- shared utils/
# library modules are exempt; scripts shared between A and B (compile_precip,
# rim_inflow QM historical validation, water_year_types, the merged
# --product-flagged qmap wrappers in upper_watershed/miscellaneous/
# storage_curves, etc.) live in the Product A list above and are not
# duplicated here.
PRODUCT_B_SCRIPTS = [
    "mod_hydrology/rim_inflow/_3_qmap_productB.py",
    "mod_hydrology/calsimhydro/_4_postprocess_product_b.py",
    "mod_hydrology/calsimhydro_ee/_3_postprocess_product_b.py",
    "mod_hydrology/delta_channel_depletion/_3_postprocess_product_b.py",
    "mod_hydrology/small_watersheds/_3_postprocess_product_b.py",
    "mod_other/day_volume_fractions/_2_generate_product_b.py",
    "postprocessing/sv_compile/product_b_compilation.py",
    "postprocessing/calsim_runs/_productB_pickle_builder.py",
    "postprocessing/calsim_runs/_productB_postproc.py",
]


# Diagnostic / exploration / validation scripts tracked in the repo but NOT
# part of either pipeline. Exempt from the convention checks (rules 1-4) and
# accepted as "known" by the manifest-drift cross-check (rule 5) so they
# don't trip the on-disk-but-unlisted detector.
EXEMPT_SCRIPTS = [
    "mod_forcing/vic/_1_append_wind_wgen_stochastic.py",            # alt stochastic variant; pipeline uses _1_append_wind_wgen_hist
    "mod_hydrology/calsimhydro/_0_compare_et_cshydro_vic.py",       # diagnostic
    "mod_hydrology/rim_inflow/_0_stochastic_inflow_explore.py",     # exploration
    "mod_hydrology/rim_inflow/_0_stochastic_precipitation.py",      # exploration
    "mod_hydrology/rim_inflow/_1_calc_correlations.py",             # diagnostic
    "mod_hydrology/small_watersheds/_1b_check_precip_output.py",    # diagnostic
    "mod_hydrology/water_year_types/_2_compare_wyts.py",            # diagnostic
    "mod_other/day_volume_fractions/_1_vol_fractions_analysis.py",  # diagnostic
    "mod_reservoir/evaporation/_1_excel_to_python_validation.py",   # validation tool
    "postprocessing/calsim_runs/infeasibilities/n09.py",            # chunk-specific infeasibility debug
    "postprocessing/calsim_runs/infeasibilities/n10.py",            # chunk-specific infeasibility debug
    "postprocessing/calsim_runs/infeasibilities/n1_n4_n5_n6.py",    # chunk-specific infeasibility debug
    "postprocessing/calsim_runs/infeasibilities/n3_n7.py",          # chunk-specific infeasibility debug
]


# Pipeline-script naming patterns the drift check uses to discover .py files
# on disk and decide whether they should be in the manifest. Numbered scripts
# under mod_*/ have the canonical ``_N_*.py`` shape (or ``_Nb_*.py`` for the
# rare lettered variant); postprocessing scripts follow ad-hoc names so all
# .py files under postprocessing/ (except __init__.py) are considered
# pipeline-shaped.
_NUMBERED_RE = re.compile(r"^_\d+[a-z]?_.+\.py$")
_MODULE_ROOTS = ("mod_forcing", "mod_hydrology", "mod_reservoir", "mod_other")
_PIPELINE_ROOTS = _MODULE_ROOTS + ("postprocessing",)


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


def check_no_raw_hecdss(rel, text):
    """Forbid raw ``HecDss.Open(`` in pipeline scripts; require ``utils.dss_io``.

    AST-based so comments, docstrings, and string literals are naturally
    ignored. Library modules ``utils/dss_io.py`` and ``utils/dss_pickle_builder.py``
    are not in PRODUCT_A_SCRIPTS / PRODUCT_B_SCRIPTS / EXEMPT_SCRIPTS, so they
    are never checked -- they remain the only sanctioned ``HecDss.Open`` sites.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []  # parse errors are reported by check_header / check_pyflakes
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "Open"
                and isinstance(func.value, ast.Name)
                and func.value.id == "HecDss"):
            bad.append(
                f"{rel}:{func.lineno}: raw HecDss.Open(...) -- "
                f"use utils.dss_io.open_dss() instead"
            )
    return bad


_DATA_PATH_RE = re.compile(r"\.\.[\\/]+(?:\.\.[\\/]+)*data\b")


def check_no_hardcoded_data_paths(rel, text):
    """Forbid hard-coded relative ``../data`` paths; require utils.paths helpers.

    Pipeline scripts must resolve data locations through
    ``utils.paths.get_base_dir`` / ``get_generated_dir`` /
    ``get_module_generated_dir`` (which honor config.json), never a literal
    ``../../data/`` relative to the script. Matches both forward-slash and
    escaped-backslash (``..\\..\\data``) literals. Comment-only lines are
    skipped.
    """
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if _DATA_PATH_RE.search(line):
            bad.append(
                f"{rel}:{i}: hard-coded relative data/ path -- "
                f"use utils.paths.get_base_dir() / get_generated_dir() / "
                f"get_module_generated_dir()"
            )
    return bad


_REF_CSV_RE = re.compile(r"""["']reference["']\s*/\s*["']([^"']+\.csv)["']""")


def check_reference_csvs(rel, text):
    """Verify each ``"reference" / "X.csv"`` a script names exists on disk.

    Catches typos / missing reference files that otherwise only surface when
    the script's pipeline actually runs. Only the ``"reference" / "X.csv"``
    pathlib-join form is matched; scripts that build reference paths another
    way are simply not checked (no false positives).
    """
    bad = []
    ref_dir = (REPO / rel).parent / "reference"
    for m in _REF_CSV_RE.finditer(text):
        name = m.group(1)
        if not (ref_dir / name).is_file():
            bad.append(
                f"{rel}: references reference/{name} which does not exist "
                f"(expected at {ref_dir / name})"
            )
    return bad


# Deprecated pandas offset aliases (pandas 2.2). Compared on the part before
# any '-' anchor, so 'A-OCT' / 'AS-OCT' / 'Q-DEC' are caught via 'A'/'AS'/'Q'.
_DEPRECATED_FREQ = {
    "M", "A", "Q", "Y", "AS", "YS", "BM", "BA", "BAS", "BQ", "BY",
    "H", "T", "S", "L", "U", "N",
}
# Only ``freq=`` and ``.resample(`` are checked. ``.asfreq()`` is deliberately
# excluded: on a PeriodIndex, ``.asfreq('M')`` is a *Period* alias and remains
# valid in pandas 2.2 -- only the *offset* aliases (resample / date_range /
# freq=) were deprecated. We can't tell PeriodIndex from DatetimeIndex
# statically, so checking .asfreq would false-positive on the (common, valid)
# PeriodIndex.asfreq('M') pattern.
_FREQ_CALL_RE = re.compile(
    r"""(?:freq\s*=\s*|\.resample\(\s*)["']([A-Za-z][A-Za-z\-]*)["']"""
)


def check_pandas_freq_aliases(rel, text):
    """Forbid deprecated pandas 2.2 offset aliases in ``freq=`` / ``.resample()``.

    Matches a string alias used as ``freq=`` or as the first positional arg to
    ``.resample(``, and flags it if the part before any '-' anchor is in the
    deprecated set (e.g. 'M' -> 'ME', 'AS-OCT' -> 'YS-OCT'). ``.asfreq()`` is
    intentionally not checked (see _FREQ_CALL_RE note).

    Add ``# period-resample`` at end of line to suppress: pandas period-based
    resample (PeriodIndex) requires 'M' not 'ME', so those sites are correct.
    """
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if "# period-resample" in line:
            continue
        for m in _FREQ_CALL_RE.finditer(line):
            alias = m.group(1)
            if alias.split("-")[0] in _DEPRECATED_FREQ:
                bad.append(
                    f"{rel}:{i}: deprecated pandas freq alias '{alias}' -- "
                    f"use the pandas 2.2 form (e.g. 'ME','YE','QE','YS-OCT')"
                )
    return bad


def check_pbias_sign(rel, text):
    """Flag PBIAS computed with the inverted ``(obs - sim)`` convention.

    The repo standard is ``100 * sum(sim - obs) / sum(obs)`` (positive means
    overestimation). Heuristic: on any line assigning ``pbias`` (joined with
    the next two lines to catch wrapped formulas), if an ``obs - sim`` term
    appears without a ``sim - obs`` term, flag it.
    """
    bad = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if not re.search(r"\bpbias\b\s*=", line, re.IGNORECASE):
            continue
        window = " ".join(lines[i - 1:i + 2])
        has_obs_sim = re.search(r"\bobs\s*-\s*sim\b", window)
        has_sim_obs = re.search(r"\bsim\s*-\s*obs\b", window)
        if has_obs_sim and not has_sim_obs:
            bad.append(
                f"{rel}:{i}: PBIAS appears to use (obs - sim); the convention "
                f"is 100 * sum(sim - obs) / sum(obs)"
            )
    return bad


def check_no_random_seed(rel, text):
    """Forbid ``np.random.seed(`` outside utils/quantile_mapping.py.

    QM determinism is established by the single global ``QMAP_SEED`` in
    utils/quantile_mapping.py; any other module re-seeding the global RNG
    risks silently breaking reproducibility.
    """
    bad = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if "np.random.seed(" in line or "numpy.random.seed(" in line:
            bad.append(
                f"{rel}:{i}: np.random.seed(...) -- QM determinism is via "
                f"utils.quantile_mapping QMAP_SEED; do not re-seed elsewhere"
            )
    return bad


def check_drift():
    """Cross-check on-disk pipeline-shaped .py files vs the manifest.

    Walks ``mod_*/`` for ``_N_*.py`` (or ``_Nb_*.py``) and ``postprocessing/``
    for all ``*.py`` (excluding ``__init__.py``). Reports drift in two
    directions:
      - on disk, not listed in PRODUCT_A_SCRIPTS / PRODUCT_B_SCRIPTS /
        EXEMPT_SCRIPTS (potential missing entry; add to gate or exempt)
      - listed but not on disk (stale gate entry; remove or move)
    """
    on_disk = set()
    for module_root in _MODULE_ROOTS:
        root = REPO / module_root
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _NUMBERED_RE.match(path.name):
                on_disk.add(str(path.relative_to(REPO)).replace("\\", "/"))
    pp_root = REPO / "postprocessing"
    if pp_root.is_dir():
        for path in pp_root.rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "__init__.py":
                continue
            on_disk.add(str(path.relative_to(REPO)).replace("\\", "/"))

    known = {p.replace("\\", "/") for p in
             PRODUCT_A_SCRIPTS + PRODUCT_B_SCRIPTS + EXEMPT_SCRIPTS}

    bad = []
    for rel in sorted(on_disk - known):
        bad.append(
            f"{rel}: on disk but not in PRODUCT_A_SCRIPTS / "
            f"PRODUCT_B_SCRIPTS / EXEMPT_SCRIPTS (drift)"
        )
    for rel in sorted(known - on_disk):
        # Only report stale entries that would have been discovered by the
        # walk above; skip out-of-scope entries.
        if rel.startswith(_PIPELINE_ROOTS) and not rel.endswith("/__init__.py"):
            bad.append(
                f"{rel}: listed in manifest but not on disk (stale entry)"
            )
    return bad


def main(argv):
    rels = argv or (PRODUCT_A_SCRIPTS + PRODUCT_B_SCRIPTS)
    failures = []
    if not argv:
        # Full sweep: also run cross-cutting checks (manifest drift)
        failures.extend(check_drift())
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
        file_fail += check_no_raw_hecdss(rel, text)
        file_fail += check_no_hardcoded_data_paths(rel, text)
        file_fail += check_reference_csvs(rel, text)
        file_fail += check_pandas_freq_aliases(rel, text)
        file_fail += check_pbias_sign(rel, text)
        file_fail += check_no_random_seed(rel, text)
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
          "(see module docstring for the full rule list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
