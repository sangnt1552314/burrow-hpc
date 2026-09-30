import getpass
from typing import List

from burrow.core.command import run_command
from burrow.core.models import Job


def get_jobs_raw() -> str:
    username = getpass.getuser()

    result = run_command(
        ["qstat", "-u", username]
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    return result.stdout


def get_jobs() -> List[Job]:
    output = get_jobs_raw()

    jobs = []

    lines = output.splitlines()

    for line in lines:
        print(repr(line))

    return jobs