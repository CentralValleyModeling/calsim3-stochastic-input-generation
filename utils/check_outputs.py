"""
Delivery-file check of the single series
========================================
Lists every module's delivery CSVs of Historical_Unsplit and Product A
(utils.paths.delivery_dirs, the folders the SV compiler reads) and checks them
before a compile:

1. Name   -- each CSV is ``<stem>_<tag>_<first WY>_<last WY>.csv`` with the set's
             tag (utils.csv_io.delivery_name). A file left behind under an older
             name fails here.
2. Span   -- every series has a value for every month of the water years its
             name gives (the compiler drops a NaN and keeps the baseline).
3. Once   -- no Part B / Part C has two rows for a month within a folder, and no
             Part B / Part C comes from two modules' folders.
4. Twins  -- when both sets have delivery files, each file of one set has a file
             of the same stem and span in the other.

Inputs       : the delivery folders under GENERATED.
Outputs      : a report on stdout (files per module and set, then each failure);
               exit code 0 (clean) or 1.
Usage        : python utils/check_outputs.py                  # both sets
               python utils/check_outputs.py --product A      # one set
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import DELIVERY, WEATHER_SETS, delivery_dirs, get_generated_dir

KEY = ["Part B", "Part C", "Year", "Month"]


def rel(path: Path) -> str:
    """``path`` relative to GENERATED, for the report."""
    try:
        return Path(path).relative_to(get_generated_dir()).as_posix()
    except ValueError:
        return str(path)


def norm(s: pd.Series) -> pd.Series:
    """Part B / Part C as the compiler matches them: upper case, spaces to underscores."""
    return s.astype(str).str.upper().str.replace(" ", "_")


def check_file(path: Path, tag: str, problems: list) -> tuple | None:
    """Check the name and span of one delivery CSV; return (stem, span, frame) or None."""
    m = re.fullmatch(rf"(.+)_{tag}_(\d{{4}})_(\d{{4}})\.csv", path.name)
    if not m:
        problems.append(f"{rel(path)}: not named <stem>_{tag}_<first WY>_<last WY>.csv")
        return None
    stem, wy0, wy1 = m.group(1), int(m.group(2)), int(m.group(3))
    df = pd.read_csv(path)
    missing = set(KEY + ["Value"]) - set(df.columns)
    if missing:
        problems.append(f"{rel(path)}: no column {sorted(missing)}")
        return None
    df["Part B"], df["Part C"] = norm(df["Part B"]), norm(df["Part C"])
    wy = df["Year"].astype(int) + (df["Month"].astype(int) >= 10)
    if wy.min() != wy0 or wy.max() != wy1:
        problems.append(f"{rel(path)}: rows cover WY{wy.min()}-{wy.max()}, the name WY{wy0}-{wy1}")
    n_months = 12 * (wy1 - wy0 + 1)
    series = pd.MultiIndex.from_frame(df[["Part B", "Part C"]].drop_duplicates())
    counts = (df[df["Value"].notna()].drop_duplicates(KEY).groupby(["Part B", "Part C"]).size()
              .reindex(series, fill_value=0))
    short = counts[counts < n_months]
    if len(short):
        (b, c), n = next(iter(short.items()))
        problems.append(f"{rel(path)}: {len(short)} series lack a value for months of "
                        f"WY{wy0}-{wy1}, e.g. {b}/{c} has {n} of {n_months}")
    return stem, (wy0, wy1), df


def check_set(product: str, problems: list) -> dict:
    """Check one set's delivery folders; return {module: {(stem, span): file name}}."""
    tag = DELIVERY[product]["tag"]
    found, source_of = {}, {}
    print(f"\n{WEATHER_SETS[product]['name']} ({DELIVERY[product]['dir']})")
    for module, folder in delivery_dirs(product).items():
        files = sorted(folder.glob("*.csv")) if folder.is_dir() else []
        print(f"  {module:26s} {len(files):3d} CSV(s)  {rel(folder)}")
        found[module] = {}
        frames = []
        for f in files:
            checked = check_file(f, tag, problems)
            if checked is None:
                continue
            stem, span, df = checked
            found[module][(stem, span)] = f.name
            frames.append(df.assign(_file=f.name))
        if not frames:
            continue
        rows = pd.concat(frames, ignore_index=True)
        dup = rows[rows.duplicated(KEY, keep=False)]
        if len(dup):
            (b, c), fs = next(iter(dup.groupby(["Part B", "Part C"])["_file"].unique().items()))
            problems.append(f"{rel(folder)}: {dup.groupby(['Part B', 'Part C']).ngroups} series have two "
                            f"rows for a month, e.g. {b}/{c} in {sorted(fs)}")
        for key in rows[["Part B", "Part C"]].drop_duplicates().itertuples(index=False):
            if key in source_of and source_of[key] != module:
                problems.append(f"{key[0]}/{key[1]}: in {source_of[key]} and {module}")
            source_of.setdefault(key, module)
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the delivery CSVs of the single series.")
    ap.add_argument("--product", choices=list(DELIVERY), help="one set (default: both)")
    args = ap.parse_args(argv)
    products = [args.product] if args.product else list(DELIVERY)
    problems: list = []
    found = {p: check_set(p, problems) for p in products}
    if len(products) == 2 and all(any(m.values()) for m in found.values()):
        a, b = products
        for module in found[a]:
            for x, y in ((a, b), (b, a)):
                for key, name in sorted(found[x][module].items()):
                    if key not in found[y][module]:
                        problems.append(f"{module}: {name} has no {WEATHER_SETS[y]['name']} twin")
    if problems:
        print(f"\nRESULT: FAIL ({len(problems)})")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
