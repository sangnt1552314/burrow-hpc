from dataclasses import dataclass, field
from typing import List, Optional


STATE_NAMES = {
    "R": "RUNNING",
    "Q": "QUEUED",
    "H": "HELD",
    "E": "EXITING",
    "F": "FINISHED",
    "S": "SUSPENDED",
    "B": "ARRAY",
    "W": "WAITING",
    "X": "DONE",
}


@dataclass
class Job:
    job_id: str
    name: str
    user: str
    runtime: str
    state: str
    queue: str
    gpus: int = 0
    cpus: int = 0
    memory: str = "--"
    requested_walltime: str = "--"

    @property
    def short_id(self) -> str:
        return self.job_id.split(".")[0]

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self.state, self.state)


@dataclass
class JobDetails:
    job: Job
    node: str = "--"
    project: str = "--"
    script: str = "--"
    workdir: str = "--"
    stdout_path: str = ""
    stderr_path: str = ""
    # Join_Path=oe means stderr is written into the stdout file.
    stderr_joined: bool = False
    submitted: str = "--"
    started: str = "--"
    memory_used: str = "--"
    cpu_time: str = "--"
    cpu_percent: str = "--"
    exit_status: str = "--"
    comment: str = ""


@dataclass
class DiskUsage:
    path: str
    total_bytes: int
    used_bytes: int
    available_bytes: int

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return 100.0 * self.used_bytes / self.total_bytes


@dataclass
class StorageEntry:
    path: str
    name: str
    size_bytes: int
    is_dir: bool = True


@dataclass
class StorageScan:
    path: str
    total_bytes: int
    scanned_at: float
    entries: List[StorageEntry] = field(default_factory=list)
    # du could not read everything (e.g. permission denied).
    incomplete: bool = False


@dataclass
class FileEntry:
    name: str
    path: str
    kind: str  # "d" directory, "f" file, "l" symlink, other find %y letters
    size_bytes: int
    modified: float

    @property
    def is_dir(self) -> bool:
        return self.kind == "d"


@dataclass
class LogTail:
    path: str
    lines: List[str]
    note: Optional[str] = None
