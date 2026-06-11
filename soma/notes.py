"""Manual project annotations — `soma note <project> "text"`.

Notes are stored in ~/.soma/notes.toml separate from projects.toml
so the registry stays clean. Each project gets a list of timestamped
entries; soma context surfaces the newest MAX_NOTES.
"""
from __future__ import annotations

import tomllib
from datetime import datetime, timezone
from pathlib import Path

import tomli_w
from pydantic import BaseModel

from soma.detect import SOMA_DIR

NOTES_FILE = SOMA_DIR / "notes.toml"
MAX_NOTES = 3


class Note(BaseModel):
    text: str
    when: str  # ISO 8601


def load_notes(project: str, path: Path = NOTES_FILE) -> list[Note]:
    """Return all notes for a project, newest first."""
    if not path.exists():
        return []
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return []
    raw = data.get(project, {}).get("notes", [])
    notes = [Note(**n) for n in raw if isinstance(n, dict)]
    notes.sort(key=lambda n: n.when, reverse=True)
    return notes


def add_note(project: str, text: str, path: Path = NOTES_FILE) -> Note:
    """Append a timestamped note for project. Returns the new note."""
    data = _load_raw(path)
    entry = data.setdefault(project, {})
    notes: list[dict] = entry.setdefault("notes", [])
    note = Note(text=text, when=datetime.now(timezone.utc).isoformat(timespec="microseconds"))
    notes.append(note.model_dump())
    _save_raw(data, path)
    return note


def clear_notes(project: str, path: Path = NOTES_FILE) -> int:
    """Remove all notes for project. Returns count removed."""
    data = _load_raw(path)
    count = len(data.get(project, {}).get("notes", []))
    if project in data:
        data[project]["notes"] = []
        _save_raw(data, path)
    return count


def rename_notes(old: str, new: str, path: Path = NOTES_FILE) -> None:
    """Move all notes from old project key to new key."""
    data = _load_raw(path)
    if old not in data:
        return
    data[new] = data.pop(old)
    _save_raw(data, path)


def _load_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _save_raw(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        tomli_w.dump(data, f)
