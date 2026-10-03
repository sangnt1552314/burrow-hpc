"""Settings read once from environment variables, with Hopper defaults."""

import getpass
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() not in ("", "0", "false", "no")


USER = getpass.getuser()
CLUSTER_NAME = os.environ.get("HPIT_CLUSTER_NAME", "Hopper")
SCRATCH = os.environ.get("HPIT_SCRATCH", f"/scratch/{USER}")

# Seconds between automatic job refreshes; 0 disables auto-refresh.
REFRESH_INTERVAL = _int("HPIT_REFRESH_INTERVAL", 60)
LOG_LINES = _int("HPIT_LOG_LINES", 200)

MOCK = _flag("HPIT_MOCK")
DEBUG = _flag("HPIT_DEBUG")

CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "hpit",
)


def settings() -> dict:
    return {
        "HPIT_CLUSTER_NAME": CLUSTER_NAME,
        "HPIT_SCRATCH": SCRATCH,
        "HPIT_REFRESH_INTERVAL": str(REFRESH_INTERVAL),
        "HPIT_LOG_LINES": str(LOG_LINES),
        "HPIT_MOCK": "on" if MOCK else "off",
        "HPIT_DEBUG": "on" if DEBUG else "off",
    }
