#!/usr/bin/env python
"""Step 14: Build the 1921-2018 CalSim ET DSS.

Inputs
------
Spline workbook EToDaily sheet and DCR2025 precipitation input.

Outputs
-------
Aligned daily input CSVs, monthly ETc CSV, validated DSS, and report under
GENERATED/mod_forcing/climate/output/_3_refet_cimis_adj/step14.

Dependencies
------------
Python environment from the CUP+ environment.yml, openpyxl, pandas, pyhecdss.

Usage
-----
python Step14_Final_CS3_ET_DSS.py [--overwrite] [--install-package]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from utils.paths import get_module_generated_dir, get_base_dir


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DSS_LINK = REPO_ROOT / "_step14_dss_link"
CUP_LINK = REPO_ROOT / "_step14_cup_link"
CUP_DIR = get_base_dir() / "PyCUP"
WORKBOOK_NAME = "step12b_CS3_Table_9-xx_ETo_Spline2025_Oct1920.xlsm"
START_YEAR = 1921
END_YEAR = 2018
FIRST_WORKBOOK_DATA_ROW = 8
DATE_COLUMN = 2
FIRST_SERIES_COLUMN = 3
EXCLUDED_WBA_HEADERS = {"WBA_91"}


def generated_step14_dir() -> Path:
    return (
        get_module_generated_dir("mod_forcing/climate")
        / "output"
        / "_3_refet_cimis_adj"
        / "step14"
    )


def find_spline_workbook() -> Path:
    path = generated_step14_dir().parent / "step12" / WORKBOOK_NAME
    if not path.is_file():
        raise FileNotFoundError(f"Spline workbook not found: {path}")
    return path


def expected_daily_index(start_year: int, end_year: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", freq="D")


def export_eto(workbook_path: Path, output_path: Path) -> tuple[list[str], pd.DatetimeIndex]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    if "EToDaily" not in workbook.sheetnames:
        workbook.close()
        raise ValueError(f"Workbook has no EToDaily sheet: {workbook_path}")

    sheet = workbook["EToDaily"]
    workbook_headers = [
        str(value).strip()
        for value in next(
            sheet.iter_rows(min_row=2, max_row=2, min_col=FIRST_SERIES_COLUMN,
                            max_col=sheet.max_column, values_only=True)
        )
    ]
    if not workbook_headers or any(not name for name in workbook_headers) or len(workbook_headers) != len(set(workbook_headers)):
        workbook.close()
        raise ValueError("EToDaily row 2 must contain unique, non-empty series headers.")
    headers = [name for name in workbook_headers if name not in EXCLUDED_WBA_HEADERS]
    if not headers:
        workbook.close()
        raise ValueError("EToDaily contains no processable WBA series.")
    selected_positions = [
        index for index, name in enumerate(workbook_headers)
        if name not in EXCLUDED_WBA_HEADERS
    ]

    expected = expected_daily_index(START_YEAR, END_YEAR)
    rows: list[tuple[dt.datetime, tuple[float, ...]]] = []
    for row in sheet.iter_rows(
        min_row=FIRST_WORKBOOK_DATA_ROW,
        max_row=sheet.max_row,
        min_col=DATE_COLUMN,
        max_col=sheet.max_column,
        values_only=True,
    ):
        date_value = row[0]
        if date_value is None:
            continue
        date = pd.Timestamp(date_value).normalize()
        if START_YEAR <= date.year <= END_YEAR:
            values = tuple(
                row[FIRST_SERIES_COLUMN - DATE_COLUMN + index]
                for index in selected_positions
            )
            if len(values) != len(headers) or any(value is None for value in values):
                workbook.close()
                raise ValueError(f"EToDaily has blank series values on {date.date()}.")
            try:
                numeric = tuple(float(value) for value in values)
            except (TypeError, ValueError) as exc:
                workbook.close()
                raise ValueError(f"EToDaily has a nonnumeric value on {date.date()}.") from exc
            rows.append((date.to_pydatetime(), numeric))
    workbook.close()

    dates = pd.DatetimeIndex([row[0] for row in rows])
    if dates.has_duplicates or not dates.equals(expected):
        raise ValueError(
            f"EToDaily dates must exactly cover {expected[0].date()} through "
            f"{expected[-1].date()} once each; got {len(dates)} rows."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Date", *headers])
        for date, values in rows:
            writer.writerow([f"{date.month}/{date.day}/{date.year}", *values])
    return headers, dates


def normalize_precipitation(
    source_path: Path,
    output_path: Path,
    eto_headers: list[str],
) -> pd.DatetimeIndex:
    source = pd.read_csv(source_path, index_col=0)
    source.index = source.index.astype(str).str.strip()
    if source.columns.has_duplicates:
        raise ValueError("Precipitation input contains duplicate WBA headers.")

    # The source date year is two digits and cannot identify the century. Its
    # fixed 1921-2021 row sequence is validated using every month/day before
    # four-digit years are assigned by position.
    source_calendar = expected_daily_index(1921, 2021)
    if len(source) != len(source_calendar):
        raise ValueError(
            f"Precipitation must contain {len(source_calendar)} daily rows for 1921-2021; "
            f"found {len(source)}."
        )
    month_days = []
    for raw_date in source.index:
        match = re.fullmatch(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})", raw_date)
        if not match:
            raise ValueError(f"Unexpected ambiguous precipitation date: {raw_date!r}")
        try:
            parsed = dt.datetime.strptime(raw_date, "%d-%b-%y")
        except ValueError as exc:
            raise ValueError(f"Invalid precipitation date label: {raw_date!r}") from exc
        month_days.append((parsed.month, parsed.day))
    expected_month_days = [(date.month, date.day) for date in source_calendar]
    if month_days != expected_month_days:
        raise ValueError(
            "Precipitation row sequence does not match an unbroken 1921-2021 daily calendar."
        )

    missing_headers = sorted(set(eto_headers) - set(source.columns))
    extra_headers = sorted(
        set(source.columns) - set(eto_headers) - EXCLUDED_WBA_HEADERS
    )
    if missing_headers or extra_headers:
        raise ValueError(
            f"ETo and precipitation WBA headers differ; missing={missing_headers}, "
            f"extra={extra_headers}."
        )

    source = source[eto_headers].apply(pd.to_numeric, errors="coerce")
    if source.isna().any().any():
        raise ValueError("Precipitation contains missing or nonnumeric values.")
    source.index = source_calendar
    source = source.loc[f"{START_YEAR}-01-01":f"{END_YEAR}-12-31", eto_headers]
    expected = expected_daily_index(START_YEAR, END_YEAR)
    if not source.index.equals(expected):
        raise ValueError("Normalized precipitation dates do not match the 1921-2018 ETo dates.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = source.copy()
    output.insert(0, "Date", [date.strftime("%d%b%Y").upper() for date in output.index])
    output.to_csv(output_path, index=False)
    return source.index


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
        "--overwrite",
        action="store_true",
        help="Allow replacement of the Step 14 DSS if it already exists.",
    )
    parser.add_argument(
        "--install-package",
        action="store_true",
        help="Install the local CUP+ package with pip -e before running.",
    )
    args = parser.parse_args()

    if not CUP_DIR.is_dir():
        raise FileNotFoundError(f"CUP+ folder not found: {CUP_DIR}")
    step14_dir = generated_step14_dir()
    step14_dir.mkdir(parents=True, exist_ok=True)
    dss_output = step14_dir / "PythonGenETc_1921_2018.dss"
    if dss_output.exists() and not args.overwrite:
        raise FileExistsError(
            f"Refusing to replace existing Step 14 DSS: {dss_output}. "
            "Pass --overwrite to allow replacement."
        )

    workbook = find_spline_workbook()
    eto_csv = CUP_DIR / "tables" / "eto.csv"
    precip_source = CUP_DIR / "tables" / "DCR2025_precip_adj.csv"
    precip_output = step14_dir / "DCR2025_precip_adj_1921_2018.csv"
    if not precip_source.is_file():
        raise FileNotFoundError(f"Precipitation source not found: {precip_source}")

    eto_headers, eto_dates = export_eto(workbook, eto_csv)
    precip_dates = normalize_precipitation(precip_source, precip_output, eto_headers)
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
        finally:
            input_variables.write_text(original_input_variables, encoding="utf-8")
            remove_directory_junction(DSS_LINK)
    finally:
        remove_directory_junction(CUP_LINK)
    report_path = step14_dir / "DSS_validation.txt"
    report_path.write_text(
        f"DSS: {dss_output}\n"
        f"ETo and precipitation daily coverage: {eto_dates[0].date()} to {eto_dates[-1].date()}\n"
        "WBA_91 excluded from processing.\n"
        f"Monthly 1MON records in catalog: {record_count}\n"
        f"Monthly records verified for 1921-01 through 2018-12: {checked_count}\n",
        encoding="ascii",
    )
    print(f"Created and validated: {dss_output}")
    print(f"Monthly records validated: {checked_count}")
    print(f"Validation report: {report_path}")


if __name__ == "__main__":
    main()
