#!/usr/bin/env python
"""Step 14: Build the 1920-2018 CalSim ET DSS.

Inputs
------
Step 12 daily ETo CSV and Step 13 daily precipitation. Only the WBA series
(WBA_02 ... WBA_91, WBA_DETAW) are run through CUP+; SR and SW series are skipped.

Outputs
-------
Aligned daily input CSVs, monthly ETc CSV, validated DSS, and report under
GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step14.
CalSimHydro-named CS3_ET.dss (Part B renamed WBA_02_... -> WBA02_...) is under
GENERATED/mod_hydrology/calsimhydro/output/_2_compile_et/Product_A.
Output filenames containing 1921_2018 are retained for compatibility despite
the extended period.
CS3_ET.dss contains CUP+ records plus 44 legacy CropET terms copied from the
historical input DSS: 42 SL climatologies and two RI terms. Each RI term has
11 decade-block DSS records, so 64 DSS records are copied in total.

Dependencies
------------
Python environment from the CUP+ environment.yml, pandas, pyhecdss.

Usage
-----
python step14_final_cs3_et_dss.py [--install-package]
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir, get_base_dir


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DSS_LINK = REPO_ROOT / "_step14_dss_link"
CALSIMHYDRO_DSS_LINK = REPO_ROOT / "_step14_calsimhydro_dss_link"
REFERENCE_CROPET_DSS_LINK = REPO_ROOT / "_step14_reference_cropet_dss_link"
CUP_LINK = REPO_ROOT / "_step14_cup_link"
CUP_DIR = get_base_dir() / "PyCUP"
# Historical reference DSS containing legacy SL climatologies and RI records.
REFERENCE_CROPET_DSS = (
    get_base_dir()
    / "CalSim3" / "CSHydro_Existing" / "inputDSS" / "CS3_ET.dss"
)
DAILY_ETO_NAME = "Product_A_EToDaily_1921_2018.csv"
PRECIP_NAME = "Product_A_precip_daily_1921_2018.csv"
START_YEAR = 1920
END_YEAR = 2018
STATIC_CROP_ET_WBAS = {
    "WBA02", "WBA03", "WBA04", "WBA05", "WBA06", "WBA07N", "WBA07S",
    "WBA08N", "WBA08S", "WBA09", "WBA10", "WBA11", "WBA12", "WBA13",
    "WBA14", "WBA15N", "WBA15S", "WBA16", "WBA17N", "WBA17S", "WBA18",
    "WBA19", "WBA20", "WBA21", "WBA22", "WBA23", "WBA24", "WBA25",
    "WBA26N", "WBA26S", "WBA50", "WBA60N", "WBA60S", "WBA61", "WBA62",
    "WBA63", "WBA64", "WBA71", "WBA72", "WBA73", "WBA90", "WBA91",
}
STATIC_RI_CROP_ET_PART_B = {"WBA02_RI_ET", "WBA03_RI_ET"}
STATIC_RI_CROP_ET_D_PARTS = {
    f"01JAN{year}" for year in range(1920, 2030, 10)
}


def generated_step14_dir() -> Path:
    return (
        get_module_generated_dir("mod_forcing/climate")
        / "output"
        / "_3_refet_cimis_adj"
        / "step14"
    )


def find_daily_eto() -> Path:
    path = generated_step14_dir().parent / "step12" / DAILY_ETO_NAME
    if not path.is_file():
        raise FileNotFoundError(f"Step 12 daily ETo file not found: {path}")
    return path


def find_step13_precipitation() -> Path:
    path = generated_step14_dir().parent / "step13" / PRECIP_NAME
    if not path.is_file():
        raise FileNotFoundError(f"Step 13 precipitation not found: {path}")
    return path


def expected_daily_index(start_year: int, end_year: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", freq="D")


def export_eto(daily_eto_path: Path, output_path: Path) -> tuple[list[str], pd.DatetimeIndex]:
    source = pd.read_csv(daily_eto_path)
    if source.columns.size == 0 or source.columns[0] != "Date":
        raise ValueError(f"Step 12 daily ETo must start with a Date column: {daily_eto_path}")
    file_headers = [str(name).strip() for name in source.columns[1:]]
    if (not file_headers or any(not name for name in file_headers)
            or len(file_headers) != len(set(file_headers))):
        raise ValueError("Step 12 daily ETo must contain unique, non-empty series headers.")
    # CUP+ runs every column of eto.csv, so carry only the WBA series (not SR or SW)
    headers = [name for name in file_headers
               if not name.startswith(("WBA_SR_", "WBA_SW_"))]
    if not headers:
        raise ValueError("Step 12 daily ETo contains no processable WBA series.")

    try:
        dates = pd.DatetimeIndex([
            dt.datetime.strptime(str(value).strip(), "%m/%d/%Y") for value in source["Date"]
        ])
    except ValueError as exc:
        raise ValueError("Step 12 daily ETo dates must be m/d/yyyy.") from exc
    in_range = (dates.year >= START_YEAR) & (dates.year <= END_YEAR)
    dates = dates[in_range]
    expected = expected_daily_index(START_YEAR, END_YEAR)
    if dates.has_duplicates or not dates.equals(expected):
        raise ValueError(
            f"Step 12 daily ETo dates must exactly cover {expected[0].date()} through "
            f"{expected[-1].date()} once each; got {len(dates)} rows."
        )
    values = source.loc[in_range, headers].apply(pd.to_numeric, errors="coerce")
    if not all(math.isfinite(value) for value in values.to_numpy(dtype=float).flat):
        raise ValueError("Step 12 daily ETo contains missing or nonnumeric values.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = values.reset_index(drop=True)
    output.insert(0, "Date", [f"{date.month}/{date.day}/{date.year}" for date in dates])
    output.to_csv(output_path, index=False)
    return headers, dates


def select_precipitation(
    source_path: Path,
    output_path: Path,
    eto_headers: list[str],
) -> pd.DatetimeIndex:
    """Write the Step 13 precipitation columns that match the ETo headers, in ETo order."""
    source = pd.read_csv(source_path)
    missing_headers = sorted(set(eto_headers) - set(source.columns))
    if missing_headers:
        raise ValueError(f"Step 13 precipitation lacks ETo headers: {missing_headers}")
    if source[eto_headers].isna().any().any():
        raise ValueError("Step 13 precipitation contains missing values.")
    dates = pd.DatetimeIndex(pd.to_datetime(source["Date"], format="%d%b%Y"))
    if not dates.equals(expected_daily_index(START_YEAR, END_YEAR)):
        raise ValueError(
            f"Step 13 precipitation dates must cover {START_YEAR}-01-01 through "
            f"{END_YEAR}-12-31 once each."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    source[["Date", *eto_headers]].to_csv(output_path, index=False)
    return dates


def validate_crop_inputs(wba_headers: list[str]) -> None:
    tables_dir = CUP_LINK / "tables"
    required = [
        tables_dir / "ccTable.csv",
        tables_dir / "WBATable.csv",
    ]
    for wba in wba_headers:
        required.extend([
            tables_dir / "CropRef" / f"CropRef_{wba}.csv",
            tables_dir / "csh_CropTable" / f"csh_CropTable_{wba}.csv",
        ])
    unavailable = [path for path in required if not path.is_file()]
    if unavailable:
        examples = "\n".join(f"  {path}" for path in unavailable[:10])
        more = f"\n  ... and {len(unavailable) - 10} more" if len(unavailable) > 10 else ""
        raise FileNotFoundError(
            f"CUP+ input files are missing or not available locally ({len(unavailable)}):\n"
            f"{examples}{more}\n"
            "Hydrate these files from OneDrive, then rerun Step 14."
        )


def update_input_variables(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    seen = set()
    updated = []
    for line in lines:
        if "=" in line:
            key, _ = line.split("=", 1)
            key = key.strip()
            if key in values:
                updated.append(f"{key}={values[key]}")
                seen.add(key)
                continue
        updated.append(line)
    missing = set(values) - seen
    if missing:
        raise ValueError(f"InputVariables.txt is missing keys: {sorted(missing)}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def validate_dss(dss_path: Path) -> tuple[int, int]:
    import pyhecdss

    dss = pyhecdss.DSSFile(str(dss_path))
    try:
        catalog = dss.read_catalog()
        if catalog is None or catalog.empty:
            raise ValueError("Output DSS catalog is empty.")
        paths = dss.get_pathnames(catalog)
        monthly_paths = [
            path for path in paths
            if len(path.strip("/").split("/")) == 6
            and path.strip("/").split("/")[4].upper() == "1MON"
        ]
        if not monthly_paths:
            raise ValueError("Output DSS catalog contains no 1MON records.")

        checked = 0
        expected_start = pd.Period(f"{START_YEAR}-01", freq="M")
        expected_end = pd.Period(f"{END_YEAR}-12", freq="M")
        for pathname in monthly_paths:
            record = dss.read_rts(pathname)
            if record.data.empty:
                raise ValueError(f"DSS record has no values: {pathname}")
            periods = record.data.index
            if not isinstance(periods, pd.PeriodIndex):
                periods = pd.DatetimeIndex(periods).to_period("M")
            if periods.min() != expected_start or periods.max() != expected_end:
                raise ValueError(
                    f"DSS record does not cover {expected_start} through {expected_end}: "
                    f"{pathname} ({periods.min()} through {periods.max()})"
                )
            checked += 1
        return len(monthly_paths), checked
    finally:
        dss.close()


def calsimhydro_part_b(part_b: str) -> str:
    """CalSimHydro names WBA records WBA02_AL_ET; CUP+ writes WBA_02_AL_ET."""
    return part_b.replace("WBA_", "WBA", 1) if part_b.startswith("WBA_") else part_b


def copy_legacy_crop_et_records(target_dss_path: Path, reference_dss_path: Path) -> int:
    """Copy and verify 42 SL climatologies and 22 RI decade-block records."""
    from pydsstools.heclib.dss import HecDss

    if not reference_dss_path.is_file():
        raise FileNotFoundError(f"Reference CropET DSS not found: {reference_dss_path}")
    if not target_dss_path.is_file():
        raise FileNotFoundError(f"Target CalSimHydro DSS not found: {target_dss_path}")

    with (
        HecDss.Open(str(reference_dss_path), version=6, catalog_flag=False) as source,
        HecDss.Open(str(target_dss_path), version=6, catalog_flag=False) as target,
    ):
        source_paths = source.getPathnameList("/*/*/*/*/*/*/") or []
        existing_paths = {
            path.upper()
            for path in target.getPathnameList("/*/*/*/*/*/*/") or []
        }
        required_paths = []
        found_sl_wbas = set()
        found_ri_blocks = {part_b: set() for part_b in STATIC_RI_CROP_ET_PART_B}
        for path in source_paths:
            parts = path.strip("/").split("/")
            if len(parts) != 6:
                continue
            _, part_b, part_c, part_d, _, part_f = parts
            part_b = part_b.upper()
            if part_c.upper() != "RATE_INCH" or part_f.upper() != "EVAPOTRANSPIRATION":
                continue
            if part_b.endswith("_SL_ET") and part_d.upper() == "01JAN4000":
                wba = part_b.removesuffix("_SL_ET")
                if wba in STATIC_CROP_ET_WBAS:
                    found_sl_wbas.add(wba)
                    required_paths.append(path)
            elif part_b in STATIC_RI_CROP_ET_PART_B:
                part_d = part_d.upper()
                found_ri_blocks[part_b].add(part_d)
                if part_d in STATIC_RI_CROP_ET_D_PARTS:
                    required_paths.append(path)

        missing_sl_wbas = STATIC_CROP_ET_WBAS - found_sl_wbas
        missing_ri_blocks = {
            part_b: sorted(STATIC_RI_CROP_ET_D_PARTS - d_parts)
            for part_b, d_parts in found_ri_blocks.items()
            if STATIC_RI_CROP_ET_D_PARTS - d_parts
        }
        if missing_sl_wbas or missing_ri_blocks:
            raise ValueError(
                "Reference DSS is missing required legacy CropET records: "
                f"SL={sorted(missing_sl_wbas)}, RI blocks={missing_ri_blocks}."
            )
        expected_path_count = (
            len(STATIC_CROP_ET_WBAS)
            + len(STATIC_RI_CROP_ET_PART_B) * len(STATIC_RI_CROP_ET_D_PARTS)
        )
        if len(required_paths) != expected_path_count:
            raise ValueError(
                "Reference DSS has duplicate required legacy CropET pathnames; "
                f"found {len(required_paths)}, expected {expected_path_count}."
            )

        records_to_copy = [
            path for path in required_paths if path.upper() not in existing_paths
        ]
        print(
            f"  Copying {len(records_to_copy)} missing legacy CropET records "
            f"to {target_dss_path.name}"
        )
        for path in records_to_copy:
            target.copyRecordsFrom(source, path, path)

        final_paths = {
            path.upper()
            for path in target.getPathnameList("/*/*/*/*/*/*/") or []
        }
        missing_paths = [
            path for path in required_paths if path.upper() not in final_paths
        ]
        if missing_paths:
            raise ValueError(
                "Target DSS is missing legacy CropET records after copying: "
                f"{missing_paths}."
            )

    return len(records_to_copy)

def write_calsimhydro_dss(cup_dss_path: Path, output_path: Path) -> int:
    """Copy every CUP+ record to a new DSS with CalSimHydro Part B names."""
    import pyhecdss

    print(f"\n  write_calsimhydro_dss called:")
    print(f"    Input DSS: {cup_dss_path}")
    print(f"    Output DSS: {output_path}")

    if output_path.exists():
        output_path.unlink()
    source = pyhecdss.DSSFile(str(cup_dss_path))
    try:
        paths = source.get_pathnames(source.read_catalog())
        print(f"  Found {len(paths)} CUP+ records to write")
        with pyhecdss.DSSFile(str(output_path), create_new=True) as target:
            for pathname in paths:
                record = source.read_rts(pathname)
                parts = pathname.strip("/").split("/")
                parts[1] = calsimhydro_part_b(parts[1])
                parts[3] = ""
                new_path = "/" + "/".join(parts) + "/"
                target.write_rts(new_path, record.data, record.units, record.period_type)
    finally:
        source.close()

    record_count = len(paths)
    print(f"  CUP+ records written: {record_count}")

    # Verify file exists before returning
    if not output_path.is_file():
        print(f"  ERROR: Output DSS was not created: {output_path}")

    return record_count


def create_directory_junction(link_path: Path, target_dir: Path) -> None:
    if os.path.lexists(str(link_path)):
        raise FileExistsError(
            f"Temporary directory junction already exists; remove it after verifying its target: {link_path}"
        )
    target = str(target_dir).removeprefix("\\\\?\\")
    subprocess.run(["cmd", "/c", "mklink", "/J", str(link_path), target], check=True)


def remove_directory_junction(link_path: Path) -> None:
    if os.path.lexists(str(link_path)):
        subprocess.run(["cmd", "/c", "rmdir", str(link_path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install-package",
        action="store_true",
        help="Install the local CUP+ package with pip -e before running.",
    )
    args = parser.parse_args()

    calsimhydro_dir = (
        get_module_generated_dir("mod_hydrology/calsimhydro")
        / "output" / "_2_compile_et" / "Product_A"
    )
    calsimhydro_output = calsimhydro_dir / "CS3_ET.dss"

    if not CUP_DIR.is_dir():
        raise FileNotFoundError(f"CUP+ folder not found: {CUP_DIR}")
    step14_dir = generated_step14_dir()
    step14_dir.mkdir(parents=True, exist_ok=True)
    dss_output = step14_dir / "PythonGenETc_1921_2018.dss"
    if not REFERENCE_CROPET_DSS.is_file():
        raise FileNotFoundError(
            f"Reference CropET DSS not found: {REFERENCE_CROPET_DSS}. "
            "Hydrate the historical inputDSS folder and rerun Step 14."
        )
    for output_path in (dss_output, calsimhydro_output):
        for stale in (output_path, *(output_path.with_suffix(s) for s in (".dsc", ".dsd", ".dsk"))):
            if stale.exists():
                print(f"Deleting previous output: {stale}")
                stale.unlink()

    daily_eto = find_daily_eto()
    eto_csv = CUP_DIR / "tables" / "eto.csv"
    precip_source = find_step13_precipitation()
    precip_output = step14_dir / "precip_1921_2018.csv"

    eto_headers, eto_dates = export_eto(daily_eto, eto_csv)
    precip_dates = select_precipitation(precip_source, precip_output, eto_headers)
    if not eto_dates.equals(precip_dates):
        raise ValueError("ETo and precipitation dates are not identical after preparation.")

    input_variables = CUP_DIR / "InputVariables.txt"
    monthly_output = step14_dir / "MonthlyETc_1921_2018.csv"
    original_input_variables = input_variables.read_text(encoding="utf-8")
    create_directory_junction(CUP_LINK, CUP_DIR)
    try:
        validate_crop_inputs(eto_headers)
        create_directory_junction(DSS_LINK, step14_dir)
        try:
            update_input_variables(
                input_variables,
                {
                    "eto_fn": str(eto_csv.resolve()),
                    "precip_fn": str(precip_output.resolve()),
                    "dss_out_fn": str(DSS_LINK / dss_output.name),
                    "month_out_fn": str(monthly_output.resolve()),
                },
            )

            if args.install_package:
                subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=CUP_LINK, check=True)

            subprocess.run([sys.executable, "08_AbvCUPmodel_parrallel.py"], cwd=CUP_LINK, check=True)
            if not dss_output.is_file():
                raise FileNotFoundError(f"CUP+ did not create its configured DSS: {dss_output}")
            record_count, checked_count = validate_dss(DSS_LINK / dss_output.name)
            calsimhydro_dir.mkdir(parents=True, exist_ok=True)
            create_directory_junction(CALSIMHYDRO_DSS_LINK, calsimhydro_dir)
            try:
                calsimhydro_dss_link = CALSIMHYDRO_DSS_LINK / calsimhydro_output.name
                calsimhydro_count = write_calsimhydro_dss(
                    DSS_LINK / dss_output.name, calsimhydro_dss_link
                )
                create_directory_junction(
                    REFERENCE_CROPET_DSS_LINK, REFERENCE_CROPET_DSS.parent
                )
                try:
                    legacy_records_copied = copy_legacy_crop_et_records(
                        calsimhydro_dss_link,
                        REFERENCE_CROPET_DSS_LINK / REFERENCE_CROPET_DSS.name,
                    )
                finally:
                    remove_directory_junction(REFERENCE_CROPET_DSS_LINK)
            finally:
                remove_directory_junction(CALSIMHYDRO_DSS_LINK)
        finally:
            input_variables.write_text(original_input_variables, encoding="utf-8")
            remove_directory_junction(DSS_LINK)
    finally:
        remove_directory_junction(CUP_LINK)
    report_path = step14_dir / "DSS_validation.txt"
    report_path.write_text(
        f"DSS: {dss_output}\n"
        f"ETo and precipitation daily coverage: {eto_dates[0].date()} to {eto_dates[-1].date()}\n"
        "WBA_91 processed using WBA 90 grid cells.\n"
        f"Monthly 1MON records in catalog: {record_count}\n"
        f"Monthly records verified for {START_YEAR}-01 through {END_YEAR}-12: {checked_count}\n"
        f"CalSimHydro DSS (WBA_xx renamed to WBAxx): {calsimhydro_output} "
        f"({calsimhydro_count} CUP+ records + 44 legacy terms across "
        f"64 DSS records; {legacy_records_copied} records copied)\n"
        "Legacy CropET terms include 42 SL climatologies and 2 RI terms "
        "with 11 decade blocks each.\n",
        encoding="ascii",
    )
    print(f"Created and validated: {dss_output}")
    print(f"CalSimHydro-named DSS: {calsimhydro_output}")
    print(
        "Legacy CropET terms verified: 42 SL climatologies and 2 RI terms "
        f"across 64 DSS records ({legacy_records_copied} copied)."
    )
    print(f"Monthly records validated: {checked_count}")
    print(f"Validation report: {report_path}")


if __name__ == "__main__":
    main()
