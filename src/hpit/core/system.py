import os
import platform
import shutil
from typing import List, Tuple

from hpit import __version__
from hpit.core import config
from hpit.core.errors import HPITError


def get_doctor() -> List[Tuple[str, str]]:
    """Cheap local diagnostics; never runs cluster-wide queries."""
    from hpit.core.pbs import get_pbs_version

    try:
        pbs_version = get_pbs_version()
    except HPITError as exc:
        pbs_version = f"unavailable ({exc})"

    try:
        import textual
        textual_version = textual.__version__
    except (ImportError, AttributeError):
        textual_version = "not installed"

    scratch = config.SCRATCH
    scratch_state = "ok" if os.path.isdir(scratch) else "not found"

    return [
        ("HPIT version", __version__),
        ("Current user", config.USER),
        ("Hostname", platform.node()),
        ("Cluster name", config.CLUSTER_NAME),
        ("Python", f"{platform.python_version()} ({shutil.which('python3') or '?'})"),
        ("Textual", textual_version),
        ("PBS version", pbs_version),
        ("qstat", shutil.which("qstat") or "not found"),
        ("Scratch directory", f"{scratch} ({scratch_state})"),
        ("Cache directory", config.CACHE_DIR),
    ] + [(name, value) for name, value in config.settings().items()]
