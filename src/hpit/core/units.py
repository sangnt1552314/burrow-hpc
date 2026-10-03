from typing import Optional


def human_bytes(n: Optional[float]) -> str:
    if n is None:
        return "--"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024

    return "--"


def parse_pbs_size(value: str) -> Optional[int]:
    """Convert PBS sizes like '225gb' or '34408184kb' to bytes."""
    value = value.strip().lower()
    if not value:
        return None

    multipliers = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}

    for suffix in ("tb", "gb", "mb", "kb", "b"):
        if value.endswith(suffix):
            number = value[: -len(suffix)]
            try:
                return int(float(number) * multipliers[suffix])
            except ValueError:
                return None

    try:
        return int(value)
    except ValueError:
        return None
