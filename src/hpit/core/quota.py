"""Storage locations and quotas from the reports Hopper's `hpc space` reads.

All report files are refreshed by site cron jobs, so reading them is
instant (unlike measuring usage ourselves with du).

Locations: home, scratch, and the project folders you can access
(/scratch/Projects/CFP-*/<project> and /Project_Storage/CFP-*/<project>,
owned by one of your HPC_Users_* groups), like `hpc space --project`.
"""

import glob
import os
import re
from typing import List, Optional

from hpit.core import config
from hpit.core.models import Quota

HOME_REPORT = f"/hpctmp/Hopper/Home_Quota/logs/_{config.USER}.txt"
PROJECT_STORAGE_REPORTS = "/hpctmp/Hopper/Home_Quota/logs_projects"
# /scratch (home and project folders) quota table, one row per path.
SCRATCH_REPORT = "/home/svu/ccepbs/nushpc/quota_hw_report/hpfs_quota_raw.txt"

PROJECT_SCRATCH_GLOB = "/scratch/Projects/*/*"
PROJECT_STORAGE_GLOB = "/Project_Storage/*/*"

_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


def get_quotas() -> List[Quota]:
    """Every storage location with its quota (limit 0 = quota unknown)."""
    scratch_table = _read(SCRATCH_REPORT) or ""
    scratch_time = _mtime(SCRATCH_REPORT)

    quotas = [
        _report_quota("Home", os.path.expanduser("~"), HOME_REPORT),
        _scratch_quota("Scratch", config.SCRATCH, f"/{config.USER}", scratch_table, scratch_time),
    ]

    for path in _project_folders(PROJECT_SCRATCH_GLOB):
        name = os.path.basename(path)
        key = path[len("/scratch"):]  # Report paths omit the /scratch prefix.
        quotas.append(_scratch_quota(f"{name} scratch", path, key, scratch_table, scratch_time))

    for path in _project_folders(PROJECT_STORAGE_GLOB):
        name = os.path.basename(path)
        report = os.path.join(PROJECT_STORAGE_REPORTS, f"_{name}.txt")
        quotas.append(_report_quota(f"{name} storage", path, report))

    return [q for q in quotas if q is not None]


def _project_folders(pattern: str) -> List[str]:
    """Project folders owned by one of your groups (as `hpc space` checks)."""
    my_groups = set(os.getgroups())
    folders = []
    for path in sorted(glob.glob(pattern)):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if os.path.isdir(path) and st.st_gid in my_groups and st.st_gid != os.getgid():
            folders.append(path)
    return folders


def _report_quota(name: str, path: str, report: str) -> Optional[Quota]:
    """Home / Project_Storage reports ("AppLogical(ApparentSize): 14.73G" ...)."""
    if not os.path.isdir(path):
        return None

    text = _read(report)
    used = _size(_field(text or "", r"AppLogical\(ApparentSize\):\s*(\S+)"))
    limit = _size(_field(text or "", r"Hard Threshold:\s*(\S+)"))
    files = _field(text or "", r"Files:\s*(\d+)")
    if used is None or limit is None:
        return Quota(name=name, path=path, used_bytes=0, limit_bytes=0)

    return Quota(
        name=name, path=path, used_bytes=used, limit_bytes=limit,
        files=int(files) if files else None, reported_at=_mtime(report),
    )


def _scratch_quota(name: str, path: str, key: str, table: str, reported_at: Optional[float]) -> Optional[Quota]:
    if not os.path.isdir(path):
        return None

    # Columns: id quota_type account_id path space_used space_hard ... file_used ...
    # (the owner column is empty, so the path is the 4th field).
    for line in table.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[3] == key:
            try:
                used, limit, files = int(fields[4]), int(fields[5]), int(fields[7])
            except ValueError:
                break
            return Quota(
                name=name, path=path, used_bytes=used, limit_bytes=limit,
                files=files, reported_at=reported_at,
            )
    return Quota(name=name, path=path, used_bytes=0, limit_bytes=0)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return None


def _field(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text)
    return match.group(1) if match else None


def _size(value: Optional[str]) -> Optional[int]:
    """Parse sizes like '14.73G' or '25.60T'."""
    match = re.fullmatch(r"([\d.]+)([kKmMgGtT]?)", value or "")
    if not match:
        return None
    return int(float(match.group(1)) * _UNITS[match.group(2).lower()])


def _mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
