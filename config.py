"""Loads configuration from the environment (and a .env file if present).

No third-party dependency: we parse .env ourselves so `python config.py` works
even before `pip install`.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_PATH = Path(__file__).with_name(".env")


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=VALUE per line, # comments, no quotes required."""
    if not _ENV_PATH.exists():
        return
    for raw in _ENV_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes if the user added them.
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip())
    except (ValueError, AttributeError):
        return default


DISCORD_TOKEN: str = os.environ.get("DISCORD_TOKEN", "").strip()
OWNER_ID: int = _int("OWNER_ID", 0)

# Safety gates. DRY_RUN defaults to TRUE — going live must be a deliberate choice.
DRY_RUN: bool = _bool("DRY_RUN", True)
MAX_PER_ORDER_CENTS: int = _int("MAX_PER_ORDER_CENTS", 2500)
TIP_CENTS: int = _int("TIP_CENTS", 0)


def summary() -> str:
    """Human-readable config summary (never prints the token)."""
    return (
        f"DRY_RUN={DRY_RUN} | MAX_PER_ORDER=${MAX_PER_ORDER_CENTS/100:.2f} | "
        f"TIP=${TIP_CENTS/100:.2f} | OWNER_ID={'set' if OWNER_ID else 'MISSING'} | "
        f"TOKEN={'set' if DISCORD_TOKEN else 'MISSING'}"
    )


if __name__ == "__main__":
    print(summary())
