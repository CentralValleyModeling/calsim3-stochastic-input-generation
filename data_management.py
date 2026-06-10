"""CalSim 3 stochastic data management.

Two subcommands:

  sync     Upload changed local data to Box as module-level zip archives.
           Unchanged files are copied from the existing zip without
           recompressing; only new or modified files are compressed.
           Requires the csstochastic conda env (uses utils.paths).

  acquire  Download and unpack zips from Box shared links (data_links.json).
           No extra dependencies -- stdlib only.

Usage:
    python data_management.py sync [--force] [--dry-run] [--base-only]
                                   [--generated-only] [--box-dir PATH]
                                   [--depth {1,2}] [--compresslevel {0-9}]
                                   [--workers N]

    python data_management.py acquire [--data-dir PATH] [--force] [--dry-run]
                                      [--base-only] [--generated-only]
                                      [KEY ...]
"""

import os
import sys
import json
import zipfile
import shutil
import struct
import tempfile
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent

BOX_DEFAULT = Path(
    r"C:\Users\warnold_la\Box\Wyatt Arnold - User Folder\CalSim-Stochastic-Data"
)

# Explicit zip targets for data/BASE (paths relative to BASE root).
# Mirrors the existing Box structure; order determines zip output order.
BASE_TARGETS = [
    "CalSim3",
    "Historical_Climate",
    "WGEN/Product_A/1",
    "WGEN/Product_B/1",
]

# Per-path depth overrides for GENERATED auto-discovery (relative to GENERATED
# root, forward slashes).  Paths not listed here use the --depth default (2).
GENERATED_DEPTH_OVERRIDES = {
    "mod_forcing/vic": 4,
    "mod_forcing/vic/VIC_Support_4.2.d": 3,  # keep as single zip
}

IGNORE_DIR_NAMES = {"__pycache__", ".ipynb_checkpoints"}
IGNORE_FILE_NAMES = {"Thumbs.db", ".DS_Store"}
IGNORE_SUFFIXES = {".pyc"}

LINKS_FILE = _REPO_ROOT / "data_links.json"
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per download chunk
BOX_TOKEN_ENV = "BOX_TOKEN"  # env var for Box access token
CACHE_ROOT = _REPO_ROOT / ".sync_cache"  # local per-zip manifests for change detection
DEFAULT_COMPRESSLEVEL = 6  # DEFLATE level; lower = faster but larger archives

# ---------------------------------------------------------------------------
# Sync helpers
# ---------------------------------------------------------------------------

def is_ignored_dir(name: str) -> bool:
    if name in IGNORE_DIR_NAMES:
        return True
    if "archive" in name.lower():
        return True
    return False


def should_skip_file(rel_path: Path) -> bool:
    """Return True if rel_path (relative to its source_dir) should be excluded."""
    for part in rel_path.parts[:-1]:
        if is_ignored_dir(part):
            return True
    if rel_path.name in IGNORE_FILE_NAMES:
        return True
    if rel_path.suffix in IGNORE_SUFFIXES:
        return True
    return False


def discover_targets(
    root: Path,
    default_depth: int = 2,
    depth_overrides: dict | None = None,
) -> list:
    """
    Discover directories to zip under root.

    Recurses up to default_depth levels.  When traversal reaches a directory
    whose path (relative to root, forward slashes) appears in depth_overrides,
    that subtree switches to the override depth instead.
    """
    if depth_overrides is None:
        depth_overrides = {}

    def _recurse(directory: Path, depth: int, max_depth: int) -> list:
        rel_str = directory.relative_to(root).as_posix()
        if rel_str in depth_overrides:
            max_depth = depth_overrides[rel_str]

        subdirs = [
            d for d in sorted(directory.iterdir())
            if d.is_dir() and not is_ignored_dir(d.name)
        ]

        if not subdirs or depth >= max_depth:
            return [directory]

        result = []
        for d in subdirs:
            result.extend(_recurse(d, depth + 1, max_depth))
        return result

    if not root.exists():
        return []

    result = []
    for d1 in sorted(root.iterdir()):
        if not d1.is_dir() or is_ignored_dir(d1.name):
            continue
        result.extend(_recurse(d1, 1, default_depth))
    return result


def scan_source(source_dir: Path) -> tuple[set, float]:
    """Return (set of relative posix file paths, max mtime) for all non-skipped
    files under source_dir.  The path set mirrors exactly what create_zip would
    store, so it can be compared against an existing zip's manifest."""
    files = set()
    latest = 0.0
    for path in source_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source_dir)
        if should_skip_file(rel):
            continue
        files.add(rel.as_posix())
        mtime = path.stat().st_mtime
        if mtime > latest:
            latest = mtime
    return files, latest


def read_manifest(manifest_path: Path | None) -> set | None:
    """Return the file set recorded for a zip at its last sync, or None when no
    manifest exists or it cannot be read."""
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return set(data.get("files", []))
    except (OSError, ValueError):
        return None


def write_manifest(manifest_path: Path, source_dir: Path, dest_zip: Path) -> None:
    """Record source_dir's current file set locally so the next sync can detect
    deletions without reading the (possibly cloud-only) zip."""
    files, _ = scan_source(source_dir)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"zip_mtime": dest_zip.stat().st_mtime, "files": sorted(files)}
    tmp = manifest_path.parent / (manifest_path.name + ".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(manifest_path)


def needs_update(
    source_dir: Path, dest_zip: Path, manifest_path: Path | None = None
) -> bool:
    """Return True if dest_zip is missing or out of date relative to source_dir.

    Detection never reads the zip's contents -- important when the destination
    lives on an on-demand cloud mount (e.g. Box Drive), where reading a zip
    forces a full download.  A source file newer than the zip's filesystem mtime
    catches additions and edits (metadata only).  Deletions are caught by
    comparing the current file set against a local manifest written at the last
    sync.  The manifest is seeded automatically the first time a target is seen
    up to date, so deletions are detected from the second sync onward.
    """
    if not dest_zip.exists():
        return True
    current_files, latest_mtime = scan_source(source_dir)
    if latest_mtime > dest_zip.stat().st_mtime:
        return True
    stored = read_manifest(manifest_path)
    return stored is not None and current_files != stored


def create_zip(
    source_dir: Path, dest_zip: Path, compresslevel: int = DEFAULT_COMPRESSLEVEL
) -> int:
    """Create a zip of source_dir at dest_zip. Returns the number of files zipped.

    The archive is built on local disk and moved to dest_zip at the end, so the
    many small writes during compression never go through a cloud-synced folder.
    Files that cannot be read (e.g. OneDrive cloud-only placeholders) are skipped
    with a printed warning so the rest of the zip still completes.
    """
    dest_zip.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".zip.tmp")
    tmp_path = Path(tmp_path_str)
    file_count = 0
    try:
        os.close(tmp_fd)
        with zipfile.ZipFile(
            tmp_path, "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compresslevel,
        ) as zf:
            for path in sorted(source_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(source_dir)
                if should_skip_file(rel):
                    continue
                try:
                    zf.write(str(path), rel.as_posix())
                    file_count += 1
                except OSError as e:
                    print(f"\n    [SKIP] {rel}: {e}", flush=True)
        shutil.move(str(tmp_path), dest_zip)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return file_count


def _copy_member_raw(
    zin: zipfile.ZipFile, zout: zipfile.ZipFile, info: zipfile.ZipInfo
) -> None:
    """Append info's already-compressed bytes from zin into zout without
    decompressing or recompressing.

    Uses ZipFile internals (fp, filelist, NameToInfo, start_dir) that have been
    stable across CPython 3.x.  Any failure is the caller's signal to fall back
    to recompressing the member.
    """
    in_fp = zin.fp
    out_fp = zout.fp
    if in_fp is None or out_fp is None:
        raise zipfile.BadZipFile("zip file object unavailable")

    # Locate the compressed payload: a fixed 30-byte local file header, then
    # variable-length filename and extra fields, then the data itself.
    in_fp.seek(info.header_offset)
    header = in_fp.read(30)
    if header[0:4] != b"PK\x03\x04":
        raise zipfile.BadZipFile(f"bad local header for {info.filename}")
    fname_len, extra_len = struct.unpack("<HH", header[26:30])
    in_fp.seek(info.header_offset + 30 + fname_len + extra_len)
    data = in_fp.read(info.compress_size)
    if len(data) != info.compress_size:
        raise zipfile.BadZipFile(f"short read for {info.filename}")

    # Rebuild a ZipInfo carrying the original compression and metadata, then
    # write the local header + raw bytes and register it in the destination.
    zi = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
    zi.compress_type = info.compress_type
    zi.create_system = info.create_system
    zi.external_attr = info.external_attr
    zi.internal_attr = info.internal_attr
    zi.flag_bits = info.flag_bits & ~0x08  # no trailing data descriptor
    zi.CRC = info.CRC
    zi.compress_size = info.compress_size
    zi.file_size = info.file_size
    zi.header_offset = zout.start_dir

    out_fp.seek(zout.start_dir)
    out_fp.write(zi.FileHeader())
    out_fp.write(data)
    zout.start_dir = out_fp.tell()
    zout.filelist.append(zi)
    zout.NameToInfo[zi.filename] = zi


def _incremental_zip(
    source_dir: Path, dest_zip: Path, compresslevel: int = DEFAULT_COMPRESSLEVEL
) -> int:
    """Rebuild dest_zip, copying unchanged members straight from the existing
    archive and only (re)compressing files that are new or modified since the
    zip was last written.  Deleted files are simply not carried over.

    A file is treated as unchanged when it is present in the existing zip and
    its mtime is not newer than the zip -- the same mtime convention used by
    needs_update.  Raises on any structural problem so update_zip can fall back
    to a full recompress.
    """
    old_mtime = dest_zip.stat().st_mtime
    current, _ = scan_source(source_dir)

    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".zip.tmp")
    tmp_path = Path(tmp_path_str)
    os.close(tmp_fd)
    file_count = 0
    reused = 0
    try:
        with zipfile.ZipFile(dest_zip, "r") as zin, zipfile.ZipFile(
            tmp_path, "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=compresslevel,
        ) as zout:
            stored = {i.filename: i for i in zin.infolist() if not i.is_dir()}
            for rel in sorted(current):
                local_path = source_dir.joinpath(*rel.split("/"))
                info = stored.get(rel)
                if info is not None and local_path.stat().st_mtime <= old_mtime:
                    try:
                        _copy_member_raw(zin, zout, info)
                        reused += 1
                        file_count += 1
                        continue
                    except Exception:
                        pass  # raw copy failed -> recompress this one member
                try:
                    zout.write(str(local_path), rel)
                    file_count += 1
                except OSError as e:
                    print(f"\n    [SKIP] {rel}: {e}", flush=True)

        # Verify the rebuilt archive's manifest before replacing the original.
        with zipfile.ZipFile(tmp_path) as zcheck:
            built = {i.filename for i in zcheck.infolist() if not i.is_dir()}
        if built != current:
            raise zipfile.BadZipFile(
                f"rebuilt manifest mismatch ({len(built)} vs {len(current)} files)"
            )
        shutil.move(str(tmp_path), dest_zip)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    if reused:
        print(
            f"    [reuse] {dest_zip.name}: {reused}/{file_count} members "
            f"copied without recompressing",
            flush=True,
        )
    return file_count


def update_zip(
    source_dir: Path,
    dest_zip: Path,
    manifest_path: Path | None = None,
    compresslevel: int = DEFAULT_COMPRESSLEVEL,
) -> int:
    """Refresh dest_zip from source_dir, reusing already-compressed bytes for
    unchanged files and only (re)compressing new or modified ones; deleted files
    are dropped.  Records a local manifest afterwards so the next sync can detect
    deletions without reading the zip.

    Falls back to a full recompress (create_zip) when dest_zip is missing or the
    incremental path raises for any reason, so correctness never depends on the
    raw-copy fast path succeeding.
    """
    if not dest_zip.exists():
        n = create_zip(source_dir, dest_zip, compresslevel)
    else:
        try:
            n = _incremental_zip(source_dir, dest_zip, compresslevel)
        except Exception as e:
            print(
                f"\n    [rebuild] {dest_zip.name}: incremental update failed "
                f"({e}); recompressing in full",
                flush=True,
            )
            n = create_zip(source_dir, dest_zip, compresslevel)
    if manifest_path is not None:
        try:
            write_manifest(manifest_path, source_dir, dest_zip)
        except OSError as e:
            print(f"\n    [warn] manifest {manifest_path.name}: {e}", flush=True)
    return n


def sync_section(
    source_root: Path,
    box_root: Path,
    *,
    label: str,
    explicit_targets: list | None = None,
    max_depth: int = 2,
    depth_overrides: dict | None = None,
    cache_root: Path | None = None,
    compresslevel: int = DEFAULT_COMPRESSLEVEL,
    workers: int | None = None,
    force: bool,
    dry_run: bool,
) -> tuple[int, int]:
    """
    Sync one data section to its Box subdirectory.

    explicit_targets: list of relative path strings (used for BASE).
      If None, auto-discover directories at max_depth (used for GENERATED).
    workers: number of parallel zip processes (None = cpu count).
    """
    if explicit_targets is not None:
        source_dirs = []
        for t in explicit_targets:
            d = source_root / t
            if d.exists():
                source_dirs.append(d)
            else:
                print(f"  [{label}] WARNING: configured target not found: {t}")
    else:
        source_dirs = discover_targets(source_root, max_depth, depth_overrides)

    if not source_dirs:
        print(f"  [{label}] No targets found under {source_root}")
        return 0, 0

    updated = 0
    skipped = 0
    to_zip = []  # (source_dir, dest_zip, rel, manifest_path)

    for source_dir in source_dirs:
        rel = source_dir.relative_to(source_root)
        dest_zip = box_root / rel.parent / (rel.name + ".zip")
        manifest_path = (
            cache_root / rel.parent / (rel.name + ".json")
            if cache_root is not None else None
        )

        if force or needs_update(source_dir, dest_zip, manifest_path):
            reason = "new" if not dest_zip.exists() else "changed"
            if dry_run:
                print(f"  [would update] {rel}  ({reason})")
            else:
                to_zip.append((source_dir, dest_zip, rel, manifest_path))
            updated += 1
        else:
            print(f"  [up-to-date]   {rel}")
            skipped += 1
            # Seed a missing manifest from the matching source so the next sync
            # can detect deletions -- no re-zip and no zip read required.
            if manifest_path is not None and not dry_run and not manifest_path.exists():
                try:
                    write_manifest(manifest_path, source_dir, dest_zip)
                except OSError:
                    pass

    if dry_run or not to_zip:
        return updated, skipped

    n_workers = workers if workers is not None else (os.cpu_count() or 1)
    n_workers = min(n_workers, len(to_zip))
    print(f"  [{label}] zipping {len(to_zip)} target(s) with {n_workers} worker(s) ...")

    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {
            executor.submit(update_zip, sd, dz, mp, compresslevel): (rel, dz)
            for sd, dz, rel, mp in to_zip
        }
        for future in as_completed(futures):
            rel, dz = futures[future]
            try:
                n = future.result()
                size_mb = dz.stat().st_size / 1_048_576
                print(f"  [done]         {rel}  ({n} files, {size_mb:.1f} MB)")
            except Exception as exc:
                print(f"  [ERROR]        {rel}: {exc}")

    return updated, skipped

# ---------------------------------------------------------------------------
# Acquire helpers
# ---------------------------------------------------------------------------

def _default_data_dir() -> Path:
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from utils.paths import get_data_dir
        return get_data_dir()
    except Exception:
        return _REPO_ROOT / "data"


def load_links(
    keys_filter: set | None,
    base_only: bool,
    generated_only: bool,
) -> dict:
    if not LINKS_FILE.exists():
        print(f"ERROR: {LINKS_FILE} not found.")
        print("Create it from the template in the repo and fill in Box shared links.")
        sys.exit(1)

    with open(LINKS_FILE, encoding="utf-8") as f:
        raw = json.load(f)

    result = {}
    for key, url in raw.items():
        if key.startswith("_"):
            continue
        if base_only and not key.startswith("BASE/"):
            continue
        if generated_only and not key.startswith("GENERATED/"):
            continue
        if keys_filter and key not in keys_filter:
            continue
        if not url:
            print(f"  [no link]      {key}  (skipped -- add URL to data_links.json)")
            continue
        result[key] = url

    return result


def is_populated(directory: Path) -> bool:
    if not directory.exists():
        return False
    return next((True for p in directory.rglob("*") if p.is_file()), False)


def _box_stream(shared_url: str, dest: Path, token: str | None, label: str) -> None:
    """Download a Box shared file to dest via the Box content API.

    Uses the BoxApi header (+ optional Bearer token for enterprise Box).
    Steps:
      1. GET /2.0/shared_items  -> resolve shared link to file ID
      2. GET /2.0/files/{id}/content  -> stream file bytes (follows CDN redirect)
    """
    headers = {"BoxApi": f"shared_link={shared_url}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Step 1: resolve shared link to file ID
    try:
        req = urllib.request.Request(
            "https://api.box.com/2.0/shared_items",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            file_id = json.loads(resp.read())["id"]
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise PermissionError(
                "Box authentication required. Provide a token via --token or "
                f"the {BOX_TOKEN_ENV} environment variable. "
                "Generate a Developer Token at developer.box.com (valid 60 min)."
            ) from e
        raise

    # Step 2: stream file content (Box returns 302 -> CDN; urllib follows)
    req = urllib.request.Request(
        f"https://api.box.com/2.0/files/{file_id}/content",
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while chunk := resp.read(CHUNK_SIZE):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = 100 * downloaded / total
                    print(
                        f"\r  [downloading]  {label}  "
                        f"{downloaded/1_048_576:.0f}/{total/1_048_576:.0f} MB"
                        f" ({pct:.0f}%)",
                        end="", flush=True,
                    )
    print()


def acquire(
    key: str,
    url: str,
    data_root: Path,
    *,
    force: bool,
    dry_run: bool,
    token: str | None = None,
) -> bool:
    target_dir = data_root / Path(*key.split("/"))

    if not force and is_populated(target_dir):
        print(f"  [exists]       {key}")
        return True

    if dry_run:
        status = "re-download" if is_populated(target_dir) else "new"
        print(f"  [would fetch]  {key}  ({status})")
        return True

    target_dir.mkdir(parents=True, exist_ok=True)
    tmp = target_dir.parent / f".{target_dir.name}.zip.tmp"

    try:
        _box_stream(url, tmp, token, key)

        with open(tmp, "rb") as f:
            if f.read(4) != b"PK\x03\x04":
                raise ValueError("Downloaded content is not a valid zip file.")

        print(f"  [extracting]   {key} ...", end="", flush=True)
        with zipfile.ZipFile(tmp) as zf:
            zf.extractall(target_dir)

        n = sum(1 for p in target_dir.rglob("*") if p.is_file())
        size_mb = tmp.stat().st_size / 1_048_576
        print(f"\r  [done]         {key}  ({n} files from {size_mb:.1f} MB zip)")
        return True

    except Exception as e:
        print(f"\n  [ERROR]        {key}: {e}")
        return False

    finally:
        tmp.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Subcommand entry points
# ---------------------------------------------------------------------------

def cmd_sync(args) -> None:
    sys.path.insert(0, str(_REPO_ROOT))
    from utils.paths import get_base_dir, get_generated_dir

    do_base = not args.generated_only
    do_generated = not args.base_only
    total_updated = 0
    total_skipped = 0

    if do_base:
        print("BASE/")
        u, s = sync_section(
            get_base_dir(),
            args.box_dir / "BASE",
            label="BASE",
            explicit_targets=BASE_TARGETS,
            cache_root=CACHE_ROOT / "BASE",
            compresslevel=args.compresslevel,
            workers=args.workers,
            force=args.force,
            dry_run=args.dry_run,
        )
        total_updated += u
        total_skipped += s

    if do_generated:
        print("GENERATED/")
        u, s = sync_section(
            get_generated_dir(),
            args.box_dir / "GENERATED",
            label="GENERATED",
            max_depth=args.depth,
            depth_overrides=GENERATED_DEPTH_OVERRIDES,
            cache_root=CACHE_ROOT / "GENERATED",
            compresslevel=args.compresslevel,
            workers=args.workers,
            force=args.force,
            dry_run=args.dry_run,
        )
        total_updated += u
        total_skipped += s

    action = "would update" if args.dry_run else "updated"
    print(f"\nDone: {total_updated} {action}, {total_skipped} up-to-date")


def cmd_acquire(args) -> None:
    links = load_links(
        keys_filter=set(args.keys) if args.keys else None,
        base_only=args.base_only,
        generated_only=args.generated_only,
    )

    if not links:
        print("Nothing to download.")
        return

    print(f"Data root: {args.data_dir}\n")

    token = args.token or os.environ.get(BOX_TOKEN_ENV)
    if not token and not args.dry_run:
        print(
            f"WARNING: no Box token provided. Set --token or {BOX_TOKEN_ENV} env var.\n"
            "         Generate a Developer Token at developer.box.com (valid 60 min).\n"
        )

    ok = 0
    failed = 0
    for key, url in links.items():
        if acquire(key, url, args.data_dir, force=args.force, dry_run=args.dry_run, token=token):
            ok += 1
        else:
            failed += 1

    verb = "would fetch" if args.dry_run else "fetched"
    print(f"\nDone: {ok} {verb}, {failed} failed")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="data_management.py",
        description="CalSim 3 stochastic data management (sync to Box / acquire from Box).",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # -- sync -----------------------------------------------------------------
    p_sync = sub.add_parser(
        "sync",
        help="Upload changed local data to Box as module-level zip archives.",
        description="Zip and upload data/BASE and data/GENERATED to Box. "
                    "Only modules whose source files changed are re-zipped.",
    )
    p_sync.add_argument("--force", action="store_true",
                        help="Re-zip all modules regardless of mtime")
    p_sync.add_argument("--dry-run", action="store_true",
                        help="Print what would change without writing")
    p_sync.add_argument("--base-only", action="store_true",
                        help="Only sync BASE/")
    p_sync.add_argument("--generated-only", action="store_true",
                        help="Only sync GENERATED/")
    p_sync.add_argument("--box-dir", type=Path, default=BOX_DEFAULT,
                        help=f"Box destination directory (default: {BOX_DEFAULT})")
    p_sync.add_argument("--depth", type=int, choices=[1, 2], default=2,
                        help="Auto-discovery depth for GENERATED/ (default: 2)")
    p_sync.add_argument("--compresslevel", type=int, choices=range(0, 10),
                        default=DEFAULT_COMPRESSLEVEL, metavar="{0-9}",
                        help=f"DEFLATE level 0-9 (default: {DEFAULT_COMPRESSLEVEL}); "
                             "lower is faster but produces larger archives")
    p_sync.add_argument("--workers", type=int, default=None,
                        help="Parallel zip workers (default: cpu count)")
    p_sync.set_defaults(func=cmd_sync)

    # -- acquire --------------------------------------------------------------
    default_dir = _default_data_dir()
    p_acq = sub.add_parser(
        "acquire",
        help="Download and unpack zips from Box shared links (data_links.json).",
        description="Download module zips from Box shared links and extract them "
                    "into the local data directory. Skips entries that are already "
                    "populated unless --force is given.",
    )
    p_acq.add_argument("--data-dir", type=Path, default=default_dir,
                       help=f"Root directory to unpack data into (default: {default_dir})")
    p_acq.add_argument("--force", action="store_true",
                       help="Re-download even if destination already has files")
    p_acq.add_argument("--dry-run", action="store_true",
                       help="Show what would be downloaded without doing it")
    p_acq.add_argument("--base-only", action="store_true",
                       help="Only download BASE/ entries")
    p_acq.add_argument("--generated-only", action="store_true",
                       help="Only download GENERATED/ entries")
    p_acq.add_argument(
        "--token", default=None,
        help=(
            f"Box access token (or set {BOX_TOKEN_ENV} env var). "
            "Generate a Developer Token at developer.box.com (valid 60 min), "
            "or use a long-lived service account token from the Box admin console."
        ),
    )
    p_acq.add_argument("keys", nargs="*",
                       help="Specific keys to download (e.g. BASE/CalSim3). Default: all.")
    p_acq.set_defaults(func=cmd_acquire)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
