"""Cross-project ASCII activity heatmap — soma activity [--days N]."""
from __future__ import annotations

import concurrent.futures
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_LEVELS = ((0, "·"), (1, "░"), (3, "▒"), (6, "█"))
_MAX_WORKERS = 8
_NAME_WIDTH = 24


def _cell(n: int) -> str:
    c = "·"
    for threshold, char in _LEVELS:
        if n >= threshold:
            c = char
    return c


def fetch_daily_commits(root: Path, days: int, today: date | None = None) -> dict[date, int]:
    """Return {date: commit_count} for each day in the last `days` days."""
    today = today or datetime.now(timezone.utc).date()
    since = today - timedelta(days=days - 1)
    try:
        from git import Repo  # noqa: PLC0415
        from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError  # noqa: PLC0415
        repo = Repo(root)
        out = repo.git.log(
            f"--after={since.isoformat()}T00:00:00",
            "--format=%ad",
            "--date=format:%Y-%m-%d",
        )
    except (GitCommandError, InvalidGitRepositoryError, NoSuchPathError, OSError):
        return {}
    counts: dict[date, int] = defaultdict(int)
    for line in out.splitlines():
        line = line.strip()
        if line:
            try:
                counts[date.fromisoformat(line)] += 1
            except ValueError:
                pass
    return dict(counts)


def build_activity_data(
    registry: dict[str, dict],
    days: int = 30,
    today: date | None = None,
) -> tuple[list[tuple[str, dict[date, int]]], list[date]]:
    """Fetch per-project daily commit counts in parallel.

    Returns (rows, date_range) where rows are sorted by total commits desc.
    """
    today = today or datetime.now(timezone.utc).date()
    date_range = [today - timedelta(days=days - 1 - i) for i in range(days)]

    def _fetch(item: tuple[str, dict]) -> tuple[str, dict[date, int]]:
        name, entry = item
        return name, fetch_daily_commits(Path(entry["root"]), days, today)

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        # Skip entries whose root path no longer exists — doctor already flags them.
        live_items = [(n, e) for n, e in registry.items() if Path(e["root"]).exists()]
        results = list(pool.map(_fetch, live_items))

    results.sort(key=lambda r: (-sum(r[1].values()), r[0]))
    return results, date_range


def render_heatmap(
    rows: list[tuple[str, dict[date, int]]],
    date_range: list[date],
) -> str:
    """Render heatmap as plain-text string ready for terminal output."""
    if not rows:
        return "(no projects)"

    n = len(date_range)
    name_w = min(max(len(name) for name, _ in rows), _NAME_WIDTH)

    # Sparse date header: mm/dd label every 7 positions, chars placed inline
    header_chars = [" "] * n
    for i, d in enumerate(date_range):
        if i % 7 == 0:
            label = d.strftime("%m/%d")
            for j, ch in enumerate(label):
                if i + j < n:
                    header_chars[i + j] = ch

    pad = " " * (name_w + 2)
    lines = [pad + "".join(header_chars)]

    for name, counts in rows:
        cells = "".join(_cell(counts.get(d, 0)) for d in date_range)
        total = sum(counts.values())
        suffix = f"  {total}c" if total else ""
        lines.append(f"{name[:name_w]:<{name_w}}  {cells}{suffix}")

    total_commits = sum(sum(c.values()) for _, c in rows)
    active = sum(1 for _, c in rows if sum(c.values()) > 0)
    lines += [
        "",
        "Legend: · 0  ░ 1-2  ▒ 3-5  █ 6+",
        f"{total_commits} commits · {active}/{len(rows)} projects active · {n}d window",
    ]
    return "\n".join(lines)
