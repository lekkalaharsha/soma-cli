"""SOMA user configuration — ~/.soma/config.toml.

Keys and their defaults mirror the constants in context.py. Loading at
call-time (not import-time) means values changed by `soma config set`
are picked up immediately without restarting the process.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w

from soma.detect import SOMA_DIR

CONFIG_FILE = SOMA_DIR / "config.toml"

VALID_KEYS: dict[str, type] = {
    "dormant_days": int,
    "token_ceiling": int,
    "max_files": int,
    "max_commits": int,
}

DEFAULTS: dict[str, int] = {
    "dormant_days": 30,
    "token_ceiling": 600,
    "max_files": 8,
    "max_commits": 5,
}

_BOUNDS: dict[str, tuple[int, int]] = {
    "dormant_days": (1, 365),
    "token_ceiling": (200, 2000),
    "max_files": (1, 20),
    "max_commits": (1, 20),
}


def load_config(path: Path = CONFIG_FILE) -> dict[str, int]:
    """Return merged config: file values override defaults."""
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return cfg
    for key, cast in VALID_KEYS.items():
        raw = data.get("soma", {}).get(key)
        if raw is not None:
            try:
                cfg[key] = cast(raw)
            except (TypeError, ValueError):
                pass
    return cfg


def set_config(key: str, value: int, path: Path = CONFIG_FILE) -> None:
    """Persist a single config key. Raises ValueError for unknown keys or out-of-range values."""
    if key not in VALID_KEYS:
        raise ValueError(f"Unknown key '{key}'. Valid: {', '.join(VALID_KEYS)}")
    lo, hi = _BOUNDS[key]
    if not lo <= value <= hi:
        raise ValueError(f"'{key}' must be between {lo} and {hi}, got {value}")
    data: dict = {}
    if path.exists():
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            data = {}
    data.setdefault("soma", {})[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(data, f)


def reset_config(key: str, path: Path = CONFIG_FILE) -> bool:
    """Remove a key from config (reverts to default). Returns True if key was present."""
    if not path.exists():
        return False
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return False
    soma_section = data.get("soma", {})
    if key not in soma_section:
        return False
    del soma_section[key]
    data["soma"] = soma_section
    with path.open("wb") as f:
        tomli_w.dump(data, f)
    return True
