"""
Build the Docs of Every Version
===============================
Builds the Sphinx docs of every release tag (``v*``) and of the checked-out commit into one
site with a version menu, the layout the GitHub Pages workflow deploys:

    <out>/v1.0/ ...        one folder per tag
    <out>/main/            the checked-out commit
    <out>/switcher.json    the versions of the menu
    <out>/index.html       opens the newest tag (main while no tag exists)

The menu is pydata-sphinx-theme's version switcher, which sphinx-book-theme inherits; it sits
in the sidebar under the title. The newest tag is the preferred version, and every other
version shows the theme's version warning banner. The checked-out commit is labelled as the next
minor version after the newest tag, marked in progress: "v1.1 (in progress)" while v1.0 is the
newest.

Each version builds from its own docs/ folder, extracted with ``git archive`` into the work
folder, so no tag is moved or rewritten. The switcher settings are appended to that copy of
conf.py, since a tag's conf.py does not have them.

Inputs
------
- the git tags matching v<number>[.<number>...] and the docs/ folder of each
- the docs/ folder of HEAD, or of the working tree with ``--worktree``
- the origin remote, for the site URL (``--base-url`` overrides it)

Outputs
-------
- <out>/, as above; <work>/<version>/docs/, the sources each build read

Dependencies
------------
Standard library; git; the packages of docs/requirements.txt

Usage
-----
    python docs/build_versions.py --out docs/_build/site
    python docs/build_versions.py --out docs/_build/site --worktree --base-url http://localhost:8000/
"""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEV = "main"
MARKER = ".build_versions"
SIDEBAR = ["navbar-logo.html", "version-switcher.html", "icon-links.html",
           "search-button-field.html", "sbt-sidebar-nav.html"]
REDIRECT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url={target}/">
<link rel="canonical" href="{target}/">
<title>CalSim Stochastic Hydroclimate</title>
</head>
<body><p>The documentation is at <a href="{target}/">{target}/</a>.</p></body>
</html>
"""


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True).stdout


def release_tags() -> list:
    """The tags v<number>[.<number>...], oldest first."""
    tags = [t for t in git("tag", "--list", "v*").decode().split()
            if re.fullmatch(r"v\d+(\.\d+)*", t)]
    return sorted(tags, key=numbers)


def numbers(tag: str) -> tuple:
    return tuple(int(n) for n in tag[1:].split("."))


def next_minor(tag: str) -> str:
    """The minor version after ``tag``: v1.0 -> 1.1; with no tag, 0.1."""
    major, minor = (numbers(tag) + (0,))[:2] if tag else (0, 0)
    return f"{major}.{minor + 1}"


def pages_url() -> str:
    """The GitHub Pages URL of the origin remote: https://<owner>.github.io/<repo>/."""
    remote = git("remote", "get-url", "origin").decode().strip()
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(\.git)?$", remote)
    if not m:
        raise SystemExit(f"origin is not a GitHub remote ({remote}); pass --base-url")
    return f"https://{m.group(1).lower()}.github.io/{m.group(2)}/"


def extract_docs(ref: str, dest: Path) -> None:
    """The docs/ folder of a commit, into ``dest``/docs."""
    with tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", ref, "docs"))) as tar:
        tar.extractall(dest, filter="data")


def fresh(folder: Path) -> None:
    """Empty ``folder``, or create it. Refuses a folder with files that an earlier run of this
    script did not make, so a mistyped ``--out`` deletes nothing."""
    if folder.exists() and any(folder.iterdir()):
        if not (folder / MARKER).exists():
            raise SystemExit(f"{folder} is not empty and was not made by this script")
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARKER).write_text("made by docs/build_versions.py\n", encoding="utf-8")


def switcher_conf(base_url: str, release: str) -> str:
    """The lines appended to a version's conf.py."""
    switcher = {"json_url": base_url + "switcher.json", "version_match": release}
    return ("\n\n# -- Version menu (added by docs/build_versions.py) "
            "------------------------------------\n"
            f"release = version = {release!r}\n"
            "html_theme_options = dict(globals().get('html_theme_options', {}))\n"
            f"html_theme_options['switcher'] = {switcher!r}\n"
            "html_theme_options['check_switcher'] = False     # this script writes the file\n"
            "html_theme_options['show_version_warning_banner'] = True\n"
            f"html_sidebars = {{'**': {SIDEBAR!r}}}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the docs of every tag and of HEAD.")
    parser.add_argument("--out", required=True, type=Path,
                        help="site folder; an earlier run's output there is replaced")
    parser.add_argument("--work", type=Path, help="work folder (default: <out>/../versions_src)")
    parser.add_argument("--base-url", help="site URL (default: the GitHub Pages URL of origin)")
    parser.add_argument("--worktree", action="store_true",
                        help=f"build {DEV} from the working tree's docs/, not from HEAD")
    args = parser.parse_args()

    out = args.out.resolve()
    work = (args.work or out.parent / "versions_src").resolve()
    base_url = (args.base_url or pages_url()).rstrip("/") + "/"
    tags = release_tags()
    newest = tags[-1] if tags else None
    dev = next_minor(newest)

    # name, git ref, release, menu label; the menu lists them newest first
    versions = [(DEV, "HEAD", f"{dev}.dev0", f"v{dev} (in progress)")]
    versions += [(t, t, t[1:], t) for t in reversed(tags)]

    for folder in (out, work):
        fresh(folder)

    for name, ref, release, _ in versions:
        src = work / name
        if name == DEV and args.worktree:
            shutil.copytree(REPO / "docs", src / "docs", ignore=shutil.ignore_patterns("_build"))
        else:
            extract_docs(ref, src)
        with open(src / "docs" / "conf.py", "a", encoding="utf-8") as conf:
            conf.write(switcher_conf(base_url, release))
        print(f"== {name}: release {release}", flush=True)
        subprocess.run([sys.executable, "-m", "sphinx", "-b", "html", "-q",
                        str(src / "docs"), str(out / name)], check=True)

    entries = [{"name": label, "version": release, "url": f"{base_url}{name}/"}
               for name, _, release, label in versions]
    for entry, (name, *_) in zip(entries, versions):
        if name == newest:
            entry["preferred"] = True
    (out / "switcher.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    (out / "index.html").write_text(REDIRECT.format(target=newest or DEV), encoding="utf-8")
    print(f"wrote {out}: {', '.join(name for name, *_ in versions)}; root opens {newest or DEV}")


if __name__ == "__main__":
    main()
