import json
import os
import time
from typing import Optional

from hpit.core import config
from hpit.core.command import run_command
from hpit.core.errors import HPITError
from hpit.core.models import DiskUsage, StorageEntry, StorageScan


# `du` on a large scratch can take minutes (about 4 on Hopper).
SCAN_TIMEOUT = 900

_CACHE_FILE = os.path.join(config.CACHE_DIR, "storage.json")


class StorageError(HPITError):
    pass


def get_disk_usage(path: str) -> DiskUsage:
    if not os.path.isdir(path):
        raise StorageError(f"Scratch directory not found: {path}")

    # `df` asks the filesystem directly, so it is instant. On Hopper the
    # NFS scratch mount reports the per-user quota as its size.
    result = run_command(["df", "-P", "-k", path])
    if result.returncode != 0:
        raise StorageError(result.stderr.strip())

    lines = result.stdout.strip().splitlines()
    try:
        fields = lines[-1].split()
        total, used, available = (int(fields[i]) * 1024 for i in (1, 2, 3))
    except (IndexError, ValueError):
        raise StorageError("Could not parse df output.")

    return DiskUsage(path, total, used, available)


def scan_directory(path: str) -> StorageScan:
    """Size every direct child of `path` with one `du` call (slow)."""
    if not os.path.isdir(path):
        raise StorageError(f"Directory not found: {path}")

    result = run_command(
        ["du", "-k", "--max-depth=1", "--", path],
        timeout=SCAN_TIMEOUT,
    )

    if result.returncode == 124:
        raise StorageError(f"du timed out after {SCAN_TIMEOUT}s on {path}")

    # du exits 1 when some folders are unreadable but still prints the
    # rest, so only fail when it printed nothing at all.
    sizes = {}
    for line in result.stdout.splitlines():
        size, _, entry_path = line.partition("\t")
        if size.isdigit():
            sizes[entry_path] = int(size) * 1024

    root = os.path.normpath(path)
    if root not in sizes:
        raise StorageError(result.stderr.strip() or f"du failed on {path}")

    total = sizes.pop(root)
    entries = [
        StorageEntry(path=p, name=os.path.basename(p), size_bytes=s)
        for p, s in sizes.items()
    ]

    # du only lists folders; whatever is left over is loose files.
    loose = total - sum(e.size_bytes for e in entries)
    if loose > 0:
        entries.append(
            StorageEntry(path=root, name="(files)", size_bytes=loose, is_dir=False)
        )

    entries.sort(key=lambda e: e.size_bytes, reverse=True)

    scan = StorageScan(
        path=root,
        total_bytes=total,
        scanned_at=time.time(),
        entries=entries,
        incomplete=result.returncode != 0,
    )
    _save_scan(scan)
    return scan


def load_cached_scan(path: str) -> Optional[StorageScan]:
    data = _read_cache().get(os.path.normpath(path))
    if not data:
        return None

    try:
        return StorageScan(
            path=data["path"],
            total_bytes=data["total_bytes"],
            scanned_at=data["scanned_at"],
            entries=[StorageEntry(**entry) for entry in data["entries"]],
            incomplete=data.get("incomplete", False),
        )
    except (KeyError, TypeError):
        return None


def _read_cache() -> dict:
    try:
        with open(_CACHE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_scan(scan: StorageScan) -> None:
    cache = _read_cache()
    cache[scan.path] = {
        "path": scan.path,
        "total_bytes": scan.total_bytes,
        "scanned_at": scan.scanned_at,
        "incomplete": scan.incomplete,
        "entries": [entry.__dict__ for entry in scan.entries],
    }

    try:
        os.makedirs(config.CACHE_DIR, exist_ok=True)
        with open(_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except OSError:
        pass  # The cache is only a convenience.
