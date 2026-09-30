from dataclasses import dataclass
import subprocess
from typing import List


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


def run_command(args: List[str]) -> CommandResult:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
    )

    return CommandResult(
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
    )