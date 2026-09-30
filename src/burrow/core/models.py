from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    name: str
    user: str
    runtime: str
    state: str
    queue: str