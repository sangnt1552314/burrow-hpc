"""Cluster-wide GPU and queue status, the data behind Hopper's `gstat`.

Nodes come from `pbsnodes -aSj -F json` (cheap). Queue counts come from the
qstat snapshot the site already collects every few minutes, so HPIT never
runs a cluster-wide `qstat` itself.
"""

import grp
import json
import os
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from hpit.core import config

from hpit.core.command import run_command
from hpit.core.errors import HPITError
from hpit.core.models import (
    ClusterStatus, NodeStat, Placement, QueueInfo, QueueStat, SnapshotJob,
)
from hpit.core.units import human_bytes, parse_pbs_size

QSTAT_SNAPSHOT = "/home/svu/ccepbs/Monitor/log__qstat.txt"
# The latest snapshot block is at the end of the file; this many lines is
# plenty for it (a few hundred jobs) without reading the whole history.
SNAPSHOT_TAIL_LINES = 20000

QUEUES = ["small", "medium", "large", "interactive", "smallx", "mediumx", "largex"]
# Hopper sizes jobs per GPU: 12 CPUs and 225 GB memory each.
CPUS_PER_GPU = 12
MEM_PER_GPU = 225 * 1024**3
# Job sizes to suggest nodes for.
JOB_SIZES = [1, 2, 4, 8]
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

    waiting = {q.name: q.waiting for q in queues}
    try:
        my_queues = get_my_queues()
    except HPITError:
        my_queues = []
    placements = [
        Placement(gpus=g, queue=q, nodes=nodes_with_room(nodes, q, g), waiting=waiting.get(q.name, 0))
        for g in JOB_SIZES
        for q in my_queues
        if q.min_gpus <= g <= q.max_gpus
    ]
    usable = {n.name: n for q in my_queues for n in nodes if _node_serves(n, q)}

    return ClusterStatus(
        queues=queues, nodes=nodes, queues_updated=updated, queues_error=error,
        placements=placements, my_gpus_free=sum(n.gpus_free for n in usable.values()),
    )


def get_nodes() -> List[NodeStat]:
    result = run_command(["pbsnodes", "-a", "-F", "json"])
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
        available = info.get("resources_available", {})
        assigned = info.get("resources_assigned", {})
        gpus = _int(available.get("ngpus"))
        cpus = _int(available.get("ncpus"))
        mem_total = parse_pbs_size(str(available.get("mem", ""))) or 0
        mem_used = parse_pbs_size(str(assigned.get("mem", ""))) or 0
        nodes.append(NodeStat(
            name=name,
            state=info.get("state", ""),
            gpus_free=gpus - _int(assigned.get("ngpus")),
            gpus_total=gpus,
            cpus_free=cpus - _int(assigned.get("ncpus")),
            cpus_total=cpus,
            mem=f"{human_bytes(mem_total - mem_used)} / {human_bytes(mem_total)}",
            jobs=len(set(info.get("jobs", []) or [])),
            pool=_first(available.get("node_pool")),
            dedicated_queue=info.get("queue", "") or "",
            gpu_model=_first(available.get("gpu_model")),
            mem_free_bytes=mem_total - mem_used,
        ))
    nodes.sort(key=lambda n: n.name)
    return nodes


def get_my_queues() -> List[QueueInfo]:
    """Batch queues your jobs can run in: those `auto` routes to, plus
    queues whose enforced user list names you (e.g. `special`)."""
    result = run_command(["qmgr", "-c", "list queue @default"])
    if result.returncode != 0:
        raise ClusterError(result.stderr.strip() or "qmgr failed")
    queues = _parse_qmgr(result.stdout)

    groups = _my_group_names()
    mine = []
    routed = queues.get("auto", {}).get("route_destinations", "").split(",")
    for name, attrs in queues.items():
        if attrs.get("queue_type") != "Execution" or attrs.get("enabled") != "True":
            continue
        if not attrs.get("default_chunk.node_pool"):
            continue
        named = attrs.get("acl_user_enable") == "True" and any(
            entry.split("@")[0] == config.USER for entry in attrs.get("acl_users", "").split(",")
        )
        if name in routed and _allowed(attrs, groups):
            via = "-q " + name if named else "auto"
        elif named:
            via = "-q " + name
        else:
            continue
        mine.append(QueueInfo(
            name=name,
            pool=attrs["default_chunk.node_pool"],
            min_gpus=_int(attrs.get("resources_min.ngpus")) or 1,
            max_gpus=_int(attrs.get("resources_max.ngpus")) or 1,
            max_walltime=attrs.get("resources_max.walltime", "--"),
            max_run=attrs.get("max_run", "").replace("[u:PBS_GENERIC=", "").rstrip("]") or "--",
            via=via,
        ))
    # Routed queues first (normal path), then the extra ones.
    mine.sort(key=lambda q: (q.via != "auto", q.min_gpus))
    return mine


def best_placement(placements: List[Placement], gpus: int):
    """The placement most likely to start soon: room now, fewest waiting."""
    options = [p for p in placements if p.gpus == gpus and p.nodes]
    if not options:
        return None
    return min(options, key=lambda p: (p.waiting, p.queue.via != "auto"))


def submit_hint(placement: Placement) -> str:
    queue = f"-q {placement.queue.name} " if placement.queue.via != "auto" else ""
    return f"qsub {queue}-l select=1:ngpus={placement.gpus} ..."


def nodes_with_room(nodes: List[NodeStat], queue: QueueInfo, gpus: int) -> List[NodeStat]:
    """Nodes where a `gpus`-GPU job of this queue would fit right now."""
    need_mem = gpus * MEM_PER_GPU
    fits = [
        n for n in nodes
        if _node_serves(n, queue)
        and n.gpus_free >= gpus
        and n.cpus_free >= gpus * CPUS_PER_GPU
        and n.mem_free_bytes >= need_mem
    ]
    # Tightest fit first, so big free nodes stay free for big jobs.
    fits.sort(key=lambda n: (n.gpus_free, n.name))
    return fits


def _node_serves(node: NodeStat, queue: QueueInfo) -> bool:
    return (
        node.available
        and node.pool == queue.pool
        and node.dedicated_queue in ("", queue.name)
    )


def _parse_qmgr(text: str) -> Dict[str, Dict[str, str]]:
    queues: Dict[str, Dict[str, str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("Queue "):
            current = queues.setdefault(line.split()[1], {})
        elif current is not None and " = " in line:
            key, _, value = line.strip().partition(" = ")
            current[key] = value.strip()
    return queues


def _allowed(attrs: Dict[str, str], groups: Set[str]) -> bool:
    if attrs.get("acl_group_enable") == "True":
        return bool(groups & set(attrs.get("acl_groups", "").split(",")))
    return True


def _my_group_names() -> Set[str]:
    names = set()
    for gid in os.getgroups():
        try:
            names.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            pass
    return names


def _first(value) -> str:
    # string_array resources may come back as "a,b".
    return str(value or "").split(",")[0]


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _format_stamp(stamp: str) -> str:
    # "20261004_01.30" -> "2026-10-04 01:30"
    try:
        day, hm = stamp.split("_")
        return f"{day[:4]}-{day[4:6]}-{day[6:]} {hm.replace('.', ':')}"
    except ValueError:
        return stamp
