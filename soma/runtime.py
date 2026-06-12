"""Runtime paths for SOMA user state."""
from __future__ import annotations

import os
from pathlib import Path

SOMA_DIR = Path.home() / ".soma"
DEFAULT_REGISTRY_PATH = SOMA_DIR / "projects.toml"
PROJECTS_FILE_ENV = "SOMA_PROJECTS_FILE"


def registry_path() -> Path:
    """Return the projects registry path, allowing tests to override it."""
    override = os.environ.get(PROJECTS_FILE_ENV)
    if override:
        return Path(override).expanduser()
    return DEFAULT_REGISTRY_PATH
