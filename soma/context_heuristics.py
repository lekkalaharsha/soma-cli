"""Context generation heuristics: blockers, suggested focus, and descriptions."""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from soma.config import load_config
from soma.filters import is_watched, should_ignore
from soma.notes import MAX_NOTES, load_notes
from soma.status import ProjectStatus, humanize_delta

DORMANT_DAYS = 30
STALE_DAYS = 7
FIX_STORM_WINDOW = timedelta(hours=24)
FIX_STORM_THRESHOLD = 3
TODO_READ_CAP = 200_000
README_READ_CAP = 4_000
README_DESC_MAX = 350
MAX_BLOCKERS = 3
MAX_FILES = 8


def _confidence(status: ProjectStatus) -> str:
    if status.commits_7d > 0:
        return "high"
    if status.recent_commits:
        return "medium"
    return "low"


def _project_description(root: Path) -> str:
    """Extract a short functional description from configuration files (pyproject.toml, Cargo.toml,
    package.json, setup.cfg) or README.md. Strips markdown noise; prefers sentences over taglines."""
    # 1. Try pyproject.toml first
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib  # type: ignore[import]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import,no-redef]
            except ImportError:
                tomllib = None
        if tomllib is not None:
            try:
                with open(pyproject, "rb") as f:
                    data = tomllib.load(f)
                desc = data.get("project", {}).get("description", "")
                if not desc:
                    desc = data.get("tool", {}).get("poetry", {}).get("description", "")
                if desc:
                    return str(desc)[:README_DESC_MAX]
            except (OSError, tomllib.TOMLDecodeError):
                pass

    # 2. Try Cargo.toml next
    cargo_toml = root / "Cargo.toml"
    if cargo_toml.exists():
        try:
            import tomllib  # type: ignore[import]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import,no-redef]
            except ImportError:
                tomllib = None
        if tomllib is not None:
            try:
                with open(cargo_toml, "rb") as f:
                    data = tomllib.load(f)
                desc = data.get("package", {}).get("description", "")
                if desc:
                    return str(desc)[:README_DESC_MAX]
            except (OSError, tomllib.TOMLDecodeError):
                pass

    # 3. Try package.json next
    package_json = root / "package.json"
    if package_json.exists():
        try:
            import json
            with package_json.open("r", encoding="utf-8") as f:
                data = json.load(f)
            desc = data.get("description", "")
            if desc:
                return str(desc)[:README_DESC_MAX]
        except Exception:
            pass

    # 4. Try setup.cfg next
    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists():
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(setup_cfg, encoding="utf-8")
            desc = config.get("metadata", "description", fallback="")
            if desc:
                return str(desc)[:README_DESC_MAX]
        except Exception:
            pass

    # 5. Fall back to README files
    for readme in ("README.md", "README.rst", "README.txt", "readme.md"):
        path = root / readme
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:README_READ_CAP]
            except OSError:
                continue
            desc = _extract_readme_paragraph(_readme_preamble(text))
            if desc:
                return desc
    return ""


def _readme_preamble(text: str) -> str:
    """Return README text up to (not including) the first subsection header (##).

    The project description lives in the preamble before any ## sections.
    Dev notes, changelogs, usage guides etc. all live under ## headers —
    stopping there avoids pulling them in as the description.
    """
    lines: list[str] = []
    for line in text.splitlines():
        if re.match(r"^#{2,}", line.strip()):
            break
        lines.append(line)
    return "\n".join(lines)


def _extract_readme_paragraph(text: str) -> str:
    """Return the first real prose paragraph from README text.

    Prefers paragraphs that read as functional descriptions (contain a verb-like
    word: is/does/builds/provides/helps/lets/runs/generates/scans/manages).
    Falls back to any paragraph with a complete sentence (contains a period/colon).
    Finally falls back to first non-trivial line.
    """
    SKIP_PREFIXES = ("#", "!", "<", "`", "[", "|", "---", "===", "~~~")
    VERB_WORDS = re.compile(
        r"\b(is|are|does|builds|provides|helps|lets|runs|generates|scans|manages"
        r"|creates|tracks|allows|enables|installs|parses|reads|writes|converts"
        r"|a proof|a cli|a tool|a library|a framework)\b",
        re.I,
    )

    def clean_line(line: str) -> str:
        line = line.strip()
        if line.startswith(">"):
            line = line.lstrip("> ").strip()
        # Remove badges: [![alt](image)](url)
        line = re.sub(r"\[\!\[[^\]]*\]\([^)]+\)\]\([^)]+\)", "", line)
        # Remove markdown images: ![alt](url)
        line = re.sub(r"\!\[[^\]]*\]\([^)]+\)", "", line)
        # Remove HTML images/badges: <img ...>
        line = re.sub(r"<img\b[^>]*>", "", line)
        # Remove markdown links: [text](url) -> text
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        # Remove HTML links: <a ...>text</a> -> text
        line = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", line)
        # Strip markdown bold/italic (* and _)
        line = re.sub(r"[*_]{1,3}(.+?)[*_]{1,3}", r"\1", line)
        return line.strip()

    paragraphs: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        raw_stripped = raw.strip()
        if not raw_stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if any(raw_stripped.startswith(p) for p in SKIP_PREFIXES):
            continue
        cleaned = clean_line(raw)
        if cleaned:
            current.append(cleaned)
    if current:
        paragraphs.append(" ".join(current))

    # 1. Search for paragraph with functional descriptors
    for p in paragraphs:
        if VERB_WORDS.search(p):
            return p[:README_DESC_MAX]

    # 2. Fall back to any paragraph containing a complete sentence
    for p in paragraphs:
        if "." in p or ":" in p:
            return p[:README_DESC_MAX]

    # 3. Fall back to first non-empty line in README
    for raw in text.splitlines():
        raw_stripped = raw.strip()
        if raw_stripped and not any(raw_stripped.startswith(p) for p in SKIP_PREFIXES):
            cleaned = clean_line(raw)
            if cleaned:
                return cleaned[:README_DESC_MAX]
    return ""


def _is_todo_stale(root: Path, rel: str, line_no: int) -> bool:
    """True if the TODO line was committed more than 30 days ago."""
    try:
        from git import Repo
        repo = Repo(root)
        if rel in repo.untracked_files:
            return False
        blame_info = repo.git.blame("-L", f"{line_no},{line_no}", "--", rel)
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", blame_info)
        if match:
            date_str = match.group(0)
            commit_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - commit_date).days > 30:
                return True
        return False
    except Exception:
        return False


def _todo_blockers(root: Path, files: list[tuple[str, datetime]]) -> list[str]:
    out: list[str] = []
    for rel, _ in files[:MAX_FILES]:
        try:
            with open(root / rel, encoding="utf-8", errors="ignore") as f:
                text = f.read(TODO_READ_CAP)
        except OSError:
            continue
        matches = list(re.finditer(r"(?:^|[\s#/\*])(TODO|FIXME)\s*[:\(]", text, re.MULTILINE))
        if matches:
            line_starts = [0]
            for m in re.finditer(r"\n", text):
                line_starts.append(m.end())

            has_active_todo = False
            for match in matches:
                offset = match.start()
                import bisect
                line_no = bisect.bisect_right(line_starts, offset)
                if not _is_todo_stale(root, rel, line_no):
                    has_active_todo = True
                    break
            if has_active_todo:
                out.append(
                    f"Possible blocker detected: TODO/FIXME in recently modified {rel}"
                )
        if len(out) >= 2:
            break
    return out


def _cochange_blockers(root: Path, files_in_motion: list[tuple[str, datetime]]) -> list[str]:
    """Flag files in motion where a high-confidence co-change partner was skipped."""
    from git import Repo  # noqa: PLC0415
    from git.exc import GitCommandError  # noqa: PLC0415

    if not files_in_motion:
        return []

    try:
        repo = Repo(root)
        # Limit history walk to last 1000 commits for performance SLA
        raw_log = repo.git.log("-n", "1000", "--name-only", "--pretty=format:---COMMIT---")
    except Exception:
        return []

    # Group files per commit
    commits: list[set[str]] = []
    current: set[str] = set()
    for line in raw_log.splitlines():
        line = line.strip()
        if line == "---COMMIT---":
            if current:
                commits.append(current)
            current = set()
        elif line and not should_ignore(line):
            current.add(line)
    if current:
        commits.append(current)

    # Build co-occurrence counts
    model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    touch_count: Counter = Counter()
    for commit in commits:
        files = list(commit)
        for f in files:
            touch_count[f] += 1
        for i, a in enumerate(files):
            for b in files[i + 1:]:
                model[a][b] += 1
                model[b][a] += 1

    modified_set = {f for f, _ in files_in_motion}
    blockers = []
    seen_blockers = set()

    for f in modified_set:
        partners = model.get(f, {})
        total_f = touch_count.get(f, 1)
        # We need a minimum count of 3 co-occurrences to avoid fluke 100% matches on 1 commit
        for partner, co_count in partners.items():
            if co_count >= 3:
                confidence = co_count / total_f
                if confidence >= 0.75 and partner not in modified_set:
                    pct = int(confidence * 100)
                    msg = f"edited `{f}` but not `{partner}` (historically co-changed in {pct}% of commits)"
                    if msg not in seen_blockers:
                        seen_blockers.add(msg)
                        blockers.append(f"Possible blocker detected: {msg}")

    return blockers[:2]  # Cap to avoid spamming the blocker list


def _detect_blockers(
    status: ProjectStatus,
    root: Path,
    files: list[tuple[str, datetime]],
    now: datetime,
) -> list[str]:
    blockers: list[str] = []
    last_commit = status.recent_commits[0].when if status.recent_commits else None
    if last_commit is not None and now - last_commit > timedelta(days=STALE_DAYS):
        if status.last_active is not None and status.last_active > last_commit:
            blockers.append(
                "Possible blocker detected: stale branch — no commit since "
                f"{humanize_delta(last_commit, now)}; file edits "
                f"{humanize_delta(status.last_active, now)} postdate last commit"
            )
    fixes = [
        c
        for c in status.recent_commits
        if "fix" in c.message.lower() and now - c.when <= FIX_STORM_WINDOW
    ]
    if len(fixes) > FIX_STORM_THRESHOLD:
        blockers.append(
            f"Possible blocker detected: fix storm — {len(fixes)} fix commits in the last 24h"
        )
    blockers.extend(_todo_blockers(root, files))

    # Co-change coupling blocker heuristic
    blockers.extend(_cochange_blockers(root, files))

    # Integrity signals — co-change pattern violations (warn-level only, cap at 2)
    try:
        from soma.signals import check_integrity  # noqa: PLC0415
        sigs = [s for s in check_integrity(root, days=3) if s.severity == "warn"]
        for s in sigs[:2]:
            blockers.append(f"Integrity signal detected: {s.message}")
    except Exception:
        pass  # signals are best-effort; never block context generation
    return blockers[:MAX_BLOCKERS]


def _top_dir(files: list[tuple[str, datetime]]) -> str | None:
    """Determine the most active project directory.

    Omit auxiliary dirs doc, tests, dist, build, etc. to get the actual source folder.
    """
    SKIP_DIRS = {"tests", "test", "docs", "doc", "dist", "build", ".github", "scripts", "spec"}
    dirs = []
    for rel, _ in files:
        parts = Path(rel).parts
        if len(parts) > 1 and parts[0] not in SKIP_DIRS:
            dirs.append(parts[0])
    if not dirs:
        return None
    return Counter(dirs).most_common(1)[0][0]


def _suggested_focus(
    status: ProjectStatus,
    files: list[tuple[str, datetime]],
    now: datetime,
    dormant_days: int = DORMANT_DAYS,
) -> str:
    """Return a single line summarizing focus: active, quiet, or dormant."""
    # 1. Dormant case
    if status.last_active is None or (now - status.last_active).days >= dormant_days:
        return f"Dormant project (no changes in {dormant_days}+ days)."

    # 2. Quiet case
    if status.commits_7d == 0 and len(files) == 0:
        delta_str = humanize_delta(status.last_active, now)
        return f"Quiet (last activity {delta_str})."

    # 3. Active case
    active_dir = _top_dir(files)
    if active_dir:
        # e.g., "Active work in src/"
        return f"Active work in {active_dir}/."

    # fallback to files if they are in root
    if files:
        base = Path(files[0][0]).name
        return f"Active work on {base}."

    # fallback to latest commit message
    if status.recent_commits:
        msg = status.recent_commits[0].message.lower()
        # strip conventional prefix
        msg = re.sub(r"^(feat|fix|refactor|chore|test|docs|style|perf)\s*:\s*", "", msg)
        return f"Active work: {msg}."

    return "Active development."
