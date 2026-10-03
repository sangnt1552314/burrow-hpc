"""Project credits / GPU-hours via `amgr` (Altair Budgets), as `hpc project` uses.

amgr needs a token from `amgr login` (NUS password). The token is cached
in ~/.am/.amtoken and expires, so HPIT can renew it with the password
from the .env file (HPIT_AMGR_PASSWORD), at most once per process.
"""

import csv
import json
import threading
from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from hpit.core import config
from hpit.core.command import CommandResult, run_command
from hpit.core.errors import HPITError
from hpit.core.models import SU_PER_GPU_HOUR, MemberUsage, Project


class AccountingError(HPITError):
    pass


class NotLoggedIn(AccountingError):
    pass


NOT_LOGGED_IN_HELP = (
    "Not logged in to the accounting system (amgr token expired).\n"
    "Run `hpit login` (or `amgr login`), or set HPIT_AMGR_PASSWORD in "
    f"{config.ENV_FILE}."
)

# One automatic login attempt per process: retrying a wrong password
# could lock the NUS account.
_auto_login_tried = False
_login_lock = threading.Lock()


def _amgr(args: List[str]) -> CommandResult:
    result = run_command(["amgr", *args])
    if result.returncode == 127:
        raise AccountingError("amgr is not available on this machine.")

    output = result.stdout + result.stderr
    # amgr reports an expired token as "Code :15006" (sometimes with exit 0).
    if "15006" in output or "token has expired" in output.lower() or "please login" in output.lower():
        raise NotLoggedIn(NOT_LOGGED_IN_HELP)
    if result.returncode != 0:
        raise AccountingError(_clean(output) or f"amgr exited with code {result.returncode}")
    return result


def _clean(output: str) -> str:
    # Drop getpass noise ("Can not control echo...") from amgr's output.
    noise = ("GetPassWarning", "passwd = fallback_getpass", "may be echoed", "Password:")
    lines = [l for l in output.splitlines() if l.strip() and not any(n in l for n in noise)]
    return "\n".join(lines).strip()


def is_logged_in() -> bool:
    try:
        _amgr(["ls", "user", "-n", config.USER])
        return True
    except NotLoggedIn:
        return False


def login(password: str) -> None:
    """Run `amgr login`, passing the password on stdin (never argv,
    where other users could see it with `ps`)."""
    if not password:
        raise AccountingError("No password given.")

    # A new session has no controlling terminal, so amgr's hidden prompt
    # falls back to reading stdin instead of the user's terminal.
    result = run_command(
        ["amgr", "login"], input=password + "\n", new_session=True, timeout=60,
    )
    if result.returncode == 127:
        raise AccountingError("amgr is not available on this machine.")
    if result.returncode != 0 or not is_logged_in():
        message = _clean(result.stdout + result.stderr)
        raise AccountingError(f"amgr login failed. {message}".strip())


def ensure_logged_in() -> None:
    """Make sure a valid token exists, logging in once from .env if needed."""
    global _auto_login_tried

    if is_logged_in():
        return

    password = config.secret("HPIT_AMGR_PASSWORD")
    if not password:
        if config.ENV_FILE_PROBLEM:
            raise NotLoggedIn(f"{NOT_LOGGED_IN_HELP}\nIgnoring the .env password: {config.ENV_FILE_PROBLEM}")
        raise NotLoggedIn(NOT_LOGGED_IN_HELP)

    with _login_lock:
        if is_logged_in():  # Another thread may have just logged in.
            return
        if _auto_login_tried:
            raise NotLoggedIn(
                "Automatic amgr login already failed in this session; "
                "check HPIT_AMGR_PASSWORD, then restart HPIT or run `hpit login`."
            )
        _auto_login_tried = True
        login(password)


def get_projects() -> List[Project]:
    """Projects you belong to, with credits and balance (like `hpc project`)."""
    ensure_logged_in()
    names = _amgr(["ls", "project"]).stdout.split()
    return [get_project(name) for name in names]


def get_project(name: str) -> Project:
    info_list = json.loads(_amgr(["ls", "project", "-n", name, "-j"]).stdout or "[]")
    info = info_list[0] if info_list else {}

    project = Project(
        name=name,
        start_date=info.get("start_date") or "--",
        end_date=info.get("end_date") or "--",
        active=bool(info.get("active", False)),
        users=info.get("users") or [],
    )

    # `hpc project` uses the "su" service unit; 100 SU = 1 GPU-hour.
    for row in _csv(_amgr(["report", "project", "-n", name, "-r"]).stdout):
        if row.get("serviceunit") == "su":
            project.period = row.get("period", "")
            project.credits_su = _float(row.get("total_credits"))
            project.net_su = _float(row.get("net_balance"))
            project.reserved_su = _float(row.get("total_debits_authorized"))
    return project


def get_project_usage(
    name: str, start: str, end: str, members: Optional[List[str]] = None,
    live: bool = True,
) -> List[MemberUsage]:
    """GPU-hours per member between two dates (YYYY-MM-DD), like `hpc project-usage`.

    Jobs reserve their full walltime when they start and are credited back
    for unused time when they finish, so running jobs count in full.

    Every transaction counts, so the total equals the drop in the project
    balance. (`hpc project-usage` keeps only reconciled rows and de-duplicates
    them, which misses jobs that used their full walltime and requeued jobs,
    so it reports less.)
    """
    ensure_logged_in()
    output = _amgr([
        "report", "project", "-n", name, "-l", "-r",
        "-S", f"{start} 00:00:00", "-E", f"{end} 23:59:59",
    ]).stdout

    used: Dict[str, float] = defaultdict(float)
    jobs: Dict[str, set] = defaultdict(set)
    for row in _csv(output):
        if row.get("serviceunit") != "su":
            continue
        user = row.get("transaction_user", "")
        amount = _float(row.get("amount"))
        if row.get("type") == "debit":
            used[user] += amount
            if amount:
                jobs[user].add(row.get("transaction_id"))
        elif row.get("type") == "credit":
            used[user] -= amount

    # List every member (like `hpc project-usage`), even with no usage.
    users = list(dict.fromkeys(list(members or []) + list(used)))
    usage = [
        MemberUsage(user=u, gpu_hours=used[u] / SU_PER_GPU_HOUR, jobs=len(jobs[u]))
        for u in users
    ]
    if live:
        _add_live_activity(name, usage)
    # Busiest right now first, then by usage this period.
    usage.sort(key=lambda m: (m.gpus_here, m.running, m.queued, m.gpu_hours), reverse=True)
    return usage


# Jobs reserve credit when they start; the longest walltime on Hopper is
# 144 h, so any job still running started within this window.
LIVE_WINDOW_DAYS = 7


def _add_live_activity(name: str, usage: List[MemberUsage]) -> None:
    """Fill in members' current jobs.

    PBS hides other users' jobs, so running/queued counts come from the
    site's cluster-wide qstat snapshot. That has no project column, so a
    running job counts for this project only if amgr shows this project
    reserved credit for it.
    """
    from hpit.core.cluster import estimate_gpus, read_snapshot

    try:
        _, snapshot = read_snapshot()
    except HPITError:
        return  # Live columns just stay empty.

    start = (date.today() - timedelta(days=LIVE_WINDOW_DAYS)).isoformat()
    output = _amgr([
        "report", "project", "-n", name, "-l", "-r",
        "-S", f"{start} 00:00:00", "-E", f"{date.today().isoformat()} 23:59:59",
    ]).stdout
    reserved: Dict[str, float] = {}
    for row in _csv(output):
        if row.get("serviceunit") == "su" and row.get("transaction_type") == "acquired":
            reserved[row.get("transaction_id", "")] = _float(row.get("amount"))

    by_user = {m.user: m for m in usage}
    for job in snapshot:
        member = by_user.get(job.user)
        if member is None:
            continue
        if job.state in ("R", "B"):
            member.running += 1
            if job.job_id in reserved:
                member.running_here += 1
                member.gpus_here += estimate_gpus(job)
                member.reserved_gpu_hours += reserved[job.job_id] / SU_PER_GPU_HOUR
        elif job.state in ("Q", "W", "H"):
            member.queued += 1


def shift_month(day: date, months: int) -> date:
    """First day of the month `months` away from `day`'s month."""
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_bounds(day: date) -> Tuple[date, date]:
    """First and last day of `day`'s month (last capped at today)."""
    first = day.replace(day=1)
    last = shift_month(day, 1) - timedelta(days=1)
    return first, min(last, max(date.today(), first))


def month_range() -> Tuple[str, str]:
    """This month so far, as ISO strings."""
    first, last = month_bounds(date.today())
    return first.isoformat(), last.isoformat()


def _csv(text: str) -> List[Dict[str, str]]:
    lines = [line for line in text.splitlines() if "," in line]
    return list(csv.DictReader(lines))


def _float(value: Optional[str]) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0
