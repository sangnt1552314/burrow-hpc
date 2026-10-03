import os
from typing import List

from hpit.core.command import run_command
from hpit.core.errors import HPITError
from hpit.core.models import FileEntry


LARGE_FILES_TIMEOUT = 600


class FilesError(HPITError):
    pass


def list_directory(path: str) -> List[FileEntry]:
    """List one directory level (fast; no recursion)."""
    if not os.path.isdir(path):
        raise FilesError(f"Directory not found: {path}")

    # NUL separators keep odd file names (spaces, newlines) intact.
    result = run_command(
        [
            "find", path, "-mindepth", "1", "-maxdepth", "1",
            "-printf", r"%y\0%s\0%T@\0%f\0",
        ]
    )
    entries = [
        FileEntry(name=name, path=os.path.join(path, name), kind=kind,
                  size_bytes=size, modified=modified)
        for kind, size, modified, name in _records(result.stdout, 4)
    ]

    if result.returncode != 0 and not entries:
        raise FilesError(result.stderr.strip() or f"Cannot list {path}")

    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return entries


def find_large_files(root: str, min_mb: int = 1024, limit: int = 100) -> List[FileEntry]:
    """Recursively find files over `min_mb` MB (slow on big trees)."""
    if not os.path.isdir(root):
        raise FilesError(f"Directory not found: {root}")

    result = run_command(
        [
            "find", root, "-xdev", "-type", "f", "-size", f"+{min_mb}M",
            "-printf", r"%y\0%s\0%T@\0%p\0",
        ],
        timeout=LARGE_FILES_TIMEOUT,
    )

    if result.returncode == 124:
        raise FilesError(f"find timed out after {LARGE_FILES_TIMEOUT}s")

    entries = [
        FileEntry(name=os.path.relpath(path, root), path=path, kind=kind,
                  size_bytes=size, modified=modified)
        for kind, size, modified, path in _records(result.stdout, 4)
    ]
    entries.sort(key=lambda e: e.size_bytes, reverse=True)
    return entries[:limit]


def _records(output: str, width: int):
    fields = output.split("\0")
    for i in range(0, len(fields) - width + 1, width):
        kind, size, modified, name = fields[i:i + width]
        try:
            yield kind, int(size), float(modified), name
        except ValueError:
            continue
