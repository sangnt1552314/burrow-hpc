import json
from typing import Any, Dict, List

from hpit.core import config
from hpit.core.command import CommandResult, run_command
from hpit.core.errors import HPITError
from hpit.core.models import Job, JobDetails
from hpit.core.units import human_bytes, parse_pbs_size


# Finished jobs kept in PBS history can be many; show only the newest.
HISTORY_LIMIT = 30


class PBSError(HPITError):
    """A PBS command failed; the message is safe to show to the user."""


def _pbs(args: List[str]) -> CommandResult:
    result = run_command(args)

    if result.returncode == 127:
        raise PBSError("PBS tools are not available on this machine.")

    return result


def _check(result: CommandResult) -> None:
    if result.returncode != 0:
        message = result.stderr.strip() or f"exited with code {result.returncode}"
        raise PBSError(message)


def _qstat_json(args: List[str]) -> Dict[str, Any]:
    result = _pbs(["qstat", "-f", "-F", "json", *args])

    # A job can finish between two qstat calls. qstat then exits
    # non-zero ("Unknown Job Id") but still prints JSON for the rest,
    # so only treat it as a failure when there is no usable output.
    try:
        data = json.loads(result.stdout)
    except ValueError:
        _check(result)
        raise PBSError("qstat returned output that is not valid JSON.")

    return data.get("Jobs", {})


def get_jobs_raw() -> str:
    result = _pbs(["qstat", "-u", config.USER])
    _check(result)
    return result.stdout


def get_job_ids(include_finished: bool = False) -> List[str]:
    args = ["qstat", "-w", "-u", config.USER]
    if include_finished:
        args.insert(1, "-x")

    result = _pbs(args)
    _check(result)

    job_ids = []

    for line in result.stdout.splitlines():
        parts = line.split()

        # Job rows start with the numeric job ID; headers and the
        # "server:" line do not.
        if parts and parts[0][0].isdigit():
            job_ids.append(parts[0])

    if include_finished:
        job_ids = job_ids[-HISTORY_LIMIT:]

    return job_ids


def get_jobs(include_finished: bool = False) -> List[Job]:
    job_ids = get_job_ids(include_finished)

    if not job_ids:
        return []

    args = ["-x", *job_ids] if include_finished else job_ids
    data = _qstat_json(args)

    return [_parse_job(job_id, info) for job_id, info in data.items()]


def get_job_details(job_id: str) -> JobDetails:
    # -x also finds finished jobs that are still in PBS history.
    data = _qstat_json(["-x", job_id])

    if not data:
        raise PBSError(f"Job {job_id} not found.")

    full_id, info = next(iter(data.items()))
    resources_used = info.get("resources_used", {})
    variables = info.get("Variable_List", {})

    return JobDetails(
        job=_parse_job(full_id, info),
        node=_nodes(info.get("exec_host", "")),
        project=info.get("project", "--"),
        script=info.get("Submit_arguments", "--"),
        workdir=variables.get("PBS_O_WORKDIR", "--"),
        stdout_path=_strip_host(info.get("Output_Path", "")),
        stderr_path=_strip_host(info.get("Error_Path", "")),
        stderr_joined=info.get("Join_Path", "n") == "oe",
        submitted=info.get("qtime", "--"),
        started=info.get("stime", "--"),
        memory_used=_memory(resources_used.get("mem", "")),
        cpu_time=resources_used.get("cput", "--"),
        cpu_percent=_text(resources_used.get("cpupercent"), suffix="%"),
        exit_status=_text(info.get("Exit_status")),
        comment=info.get("comment", ""),
    )


def cancel_job(job_id: str) -> None:
    result = _pbs(["qdel", job_id])
    _check(result)


def get_pbs_version() -> str:
    result = _pbs(["qstat", "--version"])
    _check(result)
    # Output looks like "pbs_version = 2024.1.0.20240130071604".
    return result.stdout.strip().split("=")[-1].strip()


def _parse_job(job_id: str, info: Dict[str, Any]) -> Job:
    resources_used = info.get("resources_used", {})
    requested = info.get("Resource_List", {})

    return Job(
        job_id=job_id,
        name=info.get("Job_Name", ""),
        user=info.get("Job_Owner", "").split("@")[0],
        runtime=resources_used.get("walltime", "--"),
        state=info.get("job_state", ""),
        queue=info.get("queue", ""),
        gpus=_int(requested.get("ngpus")),
        cpus=_int(requested.get("ncpus")),
        memory=_memory(requested.get("mem", "")),
        requested_walltime=requested.get("walltime", "--"),
        project=info.get("project", ""),
    )


def _strip_host(path: str) -> str:
    # PBS paths look like "hopper-l-01.cm.cluster:/scratch/...".
    return path.split(":", 1)[1] if ":" in path else path


def _nodes(exec_host: str) -> str:
    # exec_host looks like "hopper-26/4*12+hopper-27/0*12".
    nodes = []
    for chunk in exec_host.split("+"):
        node = chunk.split("/")[0]
        if node and node not in nodes:
            nodes.append(node)
    return ", ".join(nodes) or "--"


def _memory(value: str) -> str:
    size = parse_pbs_size(str(value))
    return human_bytes(size) if size is not None else "--"


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any, suffix: str = "") -> str:
    return "--" if value is None else f"{value}{suffix}"
