from dataclasses import dataclass
import subprocess
import threading
from typing import List, Optional, Set


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


# Processes that are still running, so a quitting UI can stop slow
# commands (e.g. a multi-minute `du`) instead of waiting for them.
_running: Set[subprocess.Popen] = set()
_lock = threading.Lock()


def run_command(args: List[str], timeout: Optional[float] = 30) -> CommandResult:
    # Return codes follow shell conventions so callers only need to
    # check returncode: 127 = not found, 126 = cannot run, 124 = timed out.
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
    except FileNotFoundError:
        return CommandResult(
            stdout="",
            stderr=f"{args[0]}: command not found",
            returncode=127,
        )
    except OSError as exc:
        return CommandResult(
            stdout="",
            stderr=f"{args[0]}: {exc.strerror}",
            returncode=126,
        )

    with _lock:
        _running.add(process)

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return CommandResult(
            stdout="",
            stderr=f"{args[0]}: timed out after {timeout:g}s",
            returncode=124,
        )
    finally:
        with _lock:
            _running.discard(process)

    return CommandResult(
        stdout=stdout,
        stderr=stderr,
        returncode=process.returncode,
    )


def kill_running_commands() -> None:
    with _lock:
        processes = list(_running)

    for process in processes:
        process.kill()
