"""Cluster-wide GPU and queue status, the data behind Hopper's `gstat`.

Nodes come from `pbsnodes -aSj -F json` (cheap). Queue counts come from the
qstat snapshot the site already collects every few minutes, so HPIT never
runs a cluster-wide `qstat` itself.
"""

import json
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from hpit.core.command import run_command
from hpit.core.errors import HPITError
from hpit.core.models import ClusterStatus, NodeStat, QueueStat, SnapshotJob

QSTAT_SNAPSHOT = "/home/svu/ccepbs/Monitor/log__qstat.txt"
# The latest snapshot block is at the end of the file; this many lines is
# plenty for it (a few hundred jobs) without reading the whole history.
SNAPSHOT_TAIL_LINES = 20000

QUEUES = ["small", "medium", "large", "interactive", "smallx", "mediumx", "largex"]
CPUS_PER_GPU = 12
RUNNING = {"R", "B"}
WAITING = {"Q", "W", "H"}


class ClusterError(HPITError):
    pass


def get_cluster_status() -> ClusterStatus:
    nodes = get_nodes()
    try:
        updated, queues = get_queue_stats()
        error = None
    except HPITError as exc:
        updated, queues, error = "", [], str(exc)
    return ClusterStatus(queues=queues, nodes=nodes, queues_updated=updated, queues_error=error)


def get_nodes() -> List[NodeStat]:
    result = run_command(["pbsnodes", "-aSj", "-F", "json"])
    if result.returncode == 127:
        raise ClusterError("PBS tools are not available on this machine.")
    if result.returncode != 0:
        raise ClusterError(result.stderr.strip() or "pbsnodes failed")

    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise ClusterError("pbsnodes returned output that is not valid JSON.")

    nodes = []
    for name, info in data.get("nodes", {}).items():
        gpus_free, gpus_total = _free_total(info.get("ngpus f/t", ""))
        cpus_free, cpus_total = _free_total(info.get("ncpus f/t", ""))
        nodes.append(NodeStat(
            name=name,
            state=info.get("State", ""),
            gpus_free=gpus_free,
            gpus_total=gpus_total,
            cpus_free=cpus_free,
            cpus_total=cpus_total,
            mem=info.get("mem f/t", "--"),
            jobs=len(set(info.get("jobs", []) or [])),
        ))
    nodes.sort(key=lambda n: n.name)
    return nodes


def read_snapshot() -> Tuple[str, List[SnapshotJob]]:
    """All users' jobs from the latest site qstat snapshot (PBS itself
    hides other users' jobs on Hopper: query_other_jobs = False)."""
    result = run_command(["tail", "-n", str(SNAPSHOT_TAIL_LINES), QSTAT_SNAPSHOT])
    if result.returncode != 0:
        raise ClusterError("Queue summary is not available (no site qstat snapshot).")

    lines = result.stdout.splitlines()
    if not lines:
        raise ClusterError("Queue snapshot is empty.")
    stamp = lines[-1].split(":", 1)[0]

    jobs = []
    for line in lines:
        if not line.startswith(stamp + ":"):
            continue
        # "<stamp>: jobid user queue name sessid nds tsk mem time S elap"
        fields = line.split()
        if len(fields) < 11 or not fields[1][0].isdigit():
            continue
        try:
            cpus = int(fields[7])
        except ValueError:
            cpus = 0
        jobs.append(SnapshotJob(
            job_id=fields[1], user=fields[2], queue=fields[3],
            state=fields[10], cpus=cpus, memory=fields[8],
        ))
    return _format_stamp(stamp), jobs


def estimate_gpus(job: SnapshotJob) -> int:
    # Hopper auto-assigns 12 CPUs per GPU in the standard queues, and the
    # snapshot has no GPU column, so derive it from the CPU count.
    return max(1, round(job.cpus / CPUS_PER_GPU))


def get_queue_stats() -> Tuple[str, List[QueueStat]]:
    """Running / waiting jobs per queue, computed like `gstat` does."""
    stamp, jobs = read_snapshot()

    running: Dict[str, int] = defaultdict(int)
    waiting: Dict[str, int] = defaultdict(int)
    run_users: Dict[str, Set[str]] = defaultdict(set)
    wait_users: Dict[str, Set[str]] = defaultdict(set)

    for job in jobs:
        if job.queue.startswith("AISG"):
            continue  # gstat leaves out the AISG partition too.
        for key in (job.queue, "auto"):
            if job.state in RUNNING:
                running[key] += 1
                run_users[key].add(job.user)
            elif job.state in WAITING:
                waiting[key] += 1
                wait_users[key].add(job.user)

    queues = [
        QueueStat(
            name=name,
            running=running[name],
            waiting=waiting[name],
            # Users whose jobs are all still waiting, as gstat counts it.
            users_waiting=len(wait_users[name] - run_users[name]),
        )
        for name in ["auto"] + QUEUES
    ]
    return stamp, queues


def _free_total(value: str) -> Tuple[int, int]:
    try:
        free, total = value.split("/")
        return int(free), int(total)
    except ValueError:
        return 0, 0


def _format_stamp(stamp: str) -> str:
    # "20261004_01.30" -> "2026-10-04 01:30"
    try:
        day, hm = stamp.split("_")
        return f"{day[:4]}-{day[4:6]}-{day[6:]} {hm.replace('.', ':')}"
    except ValueError:
        return stamp
