import getpass
from typing import List
import json

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
    job_ids = get_job_ids()

    if not job_ids:
        return []

    jobs = []

    result = run_command(
        ["qstat", "-f", "-F", "json", *job_ids]
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    data = json.loads(result.stdout)

    for job_id, info in data["Jobs"].items():
        resources_used = info.get("resources_used", {})

        job = Job(
            job_id=job_id,
            name=info.get("Job_Name", ""),
            user=info.get("Job_Owner", "").split("@")[0],
            runtime=resources_used.get("walltime", "--"),
            state=info.get("job_state", ""),
            queue=info.get("queue", ""),
        )

        jobs.append(job)

    return jobs


def get_job_ids() -> List[str]:
    username = getpass.getuser()

    result = run_command(
        ["qstat", "-w", "-u", username]
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())

    job_ids = []

    for line in result.stdout.splitlines():
        parts = line.split()

        if not parts:
            continue

        if parts[0].startswith("-"):
            continue

        if parts[0] == "Job":
            continue

        if ".hopper-" not in parts[0]:
            continue

        job_ids.append(parts[0])

    return job_ids