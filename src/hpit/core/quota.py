"""Home and scratch quotas from the reports Hopper's `hpc space` reads.

Both files are refreshed by site cron jobs, so reading them is instant
(unlike measuring usage ourselves).
"""

import os
import re
from typing import List, Optional

from hpit.core import config
from hpit.core.models import Quota

HOME_REPORT = f"/hpctmp/Hopper/Home_Quota/logs/_{config.USER}.txt"
SCRATCH_REPORT = "/home/svu/ccepbs/nushpc/quota_hw_report/hpfs_quota_raw.txt"

_UNITS = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}


def get_quotas() -> List[Quota]:
    quotas = [q for q in (_home_quota(), _scratch_quota()) if q]
    return quotas


def _home_quota() -> Optional[Quota]:
    text = _read(HOME_REPORT)
    if text is None:
        return None

    used = _size(_field(text, r"AppLogical\(ApparentSize\):\s*(\S+)"))
    limit = _size(_field(text, r"Hard Threshold:\s*(\S+)"))
    files = _field(text, r"Files:\s*(\d+)")
    if used is None or limit is None:
        return None

    return Quota(
        name="Home", path=os.path.expanduser("~"), used_bytes=used, limit_bytes=limit,
        files=int(files) if files else None, reported_at=_mtime(HOME_REPORT),
    )


def _scratch_quota() -> Optional[Quota]:
    text = _read(SCRATCH_REPORT)
    if text is None:
        return None

    # Columns: id quota_type account_id path space_used space_hard ... file_used ...
    # (the owner column is empty, so the path is the 4th field).
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[3] == f"/{config.USER}":
            try:
                used, limit, files = int(fields[4]), int(fields[5]), int(fields[7])
            except ValueError:
                return None
            return Quota(
                name="Scratch", path=f"/scratch/{config.USER}", used_bytes=used,
                limit_bytes=limit, files=files, reported_at=_mtime(SCRATCH_REPORT),
            )
    return None


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
    """Parse sizes like '14.73G' or '132.05M'."""
    match = re.fullmatch(r"([\d.]+)([kKmMgGtT]?)", value or "")
    if not match:
        return None
    return int(float(match.group(1)) * _UNITS[match.group(2).lower()])


def _mtime(path: str) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
