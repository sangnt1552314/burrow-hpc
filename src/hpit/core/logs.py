import os

from hpit.core import pbs
from hpit.core.command import run_command
from hpit.core.errors import HPITError
from hpit.core.models import JobDetails, LogTail


class LogError(HPITError):
    pass


def tail_file(path: str, lines: int) -> LogTail:
    if not path:
        raise LogError("PBS did not report a path for this log.")

    if not os.path.exists(path):
        raise LogError(f"Log file not found:\n{path}")

    # `tail` reads from the end, so large logs are never loaded whole.
    result = run_command(["tail", "-n", str(lines), "--", path])

    if result.returncode != 0:
        raise LogError(result.stderr.strip())

    return LogTail(path=path, lines=result.stdout.splitlines())


MISSING_HINTS = {
    "Q": "The job has not started yet.",
    "H": "The job has not started yet.",
    "R": "PBS may only copy the log here when the job ends.",
    "E": "PBS is still copying the log; try again shortly.",
    "F": "It may have been moved or deleted, or the job never started.",
}


def tail_job_log(details: JobDetails, stream: str, lines: int) -> LogTail:
    """Tail a job's "stdout" or "stderr" using the paths PBS reports."""
    joined = stream == "stderr" and details.stderr_joined
    path = details.stdout_path if stream == "stdout" or joined else details.stderr_path

    try:
        log = tail_file(path, lines)
    except LogError as exc:
        hint = MISSING_HINTS.get(details.job.state)
        if hint and path and not os.path.exists(path):
            raise LogError(f"{exc}\n\n{hint}")
        raise

    if joined:
        log.note = "stderr is merged into stdout for this job (Join_Path=oe)."
    return log


def tail_job_log_by_id(job_id: str, stream: str, lines: int) -> LogTail:
    return tail_job_log(pbs.get_job_details(job_id), stream, lines)
