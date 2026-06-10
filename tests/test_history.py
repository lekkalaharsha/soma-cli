"""Tests for soma/history.py — daily activity log across projects."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.history import collect_history, render_markdown

runner = CliRunner()


def two_project_registry(tmp_path: Path, registry: Path) -> None:
    make_repo(
        tmp_path / "alpha",
        [
            ("c.py", "feat: alpha ancient work", NOW - timedelta(days=30)),
            ("b.py", "fix: alpha bug three days back", NOW - timedelta(days=3)),
            ("a.py", "feat: alpha work today", NOW - timedelta(hours=2)),
        ],
    )
    make_repo(
        tmp_path / "beta",
        [("z.py", "feat: beta work yesterday", NOW - timedelta(days=1))],
    )
    write_registry(registry, {"alpha": tmp_path / "alpha", "beta": tmp_path / "beta"})


class TestCollectHistory:
    def test_events_grouped_by_day(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7)
        all_events = [e for evs in days.values() for e in evs]
        assert {e.project for e in all_events} == {"alpha", "beta"}
        for day, events in days.items():
            for event in events:
                assert event.when.date() == day

    def test_default_window_excludes_old_commits(
        self, tmp_path: Path, registry: Path
    ) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7)
        messages = [e.message for evs in days.values() for e in evs]
        assert "feat: alpha ancient work" not in messages
        assert "feat: alpha work today" in messages

    def test_days_n_widens_window(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=60)
        messages = [e.message for evs in days.values() for e in evs]
        assert "feat: alpha ancient work" in messages

    def test_project_filter(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7, project="beta")
        projects = {e.project for evs in days.values() for e in evs}
        assert projects == {"beta"}

    def test_days_ordered_newest_first(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7)
        keys = list(days.keys())
        assert keys == sorted(keys, reverse=True)

    def test_non_git_project_skipped_quietly(
        self, tmp_path: Path, registry: Path
    ) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "x.md").write_text("notes\n")
        write_registry(registry, {"plain": plain})
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7)
        assert days == {}


class TestHistoryCli:
    def test_default_output(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        result = runner.invoke(app, ["history"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        assert "alpha work today" in result.output
        assert "beta work yesterday" in result.output

    def test_markdown_export(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        result = runner.invoke(app, ["history", "--markdown"], env={"COLUMNS": "200"})
        assert result.exit_code == 0, result.output
        assert "## " in result.output  # day headers
        assert "**alpha**" in result.output
        assert "feat: alpha work today" in result.output

    def test_unknown_project_clean_error(
        self, tmp_path: Path, registry: Path
    ) -> None:
        two_project_registry(tmp_path, registry)
        result = runner.invoke(app, ["history", "ghost"])
        assert result.exit_code == 1
        assert "ghost" in result.output
        assert "Traceback" not in result.output


class TestMarkdownRender:
    def test_render_markdown_structure(self, tmp_path: Path, registry: Path) -> None:
        two_project_registry(tmp_path, registry)
        from soma.detect import load_registry

        days = collect_history(load_registry(registry), days=7)
        md = render_markdown(days)
        lines = md.splitlines()
        assert lines[0].startswith("# Activity")
        day_headers = [l for l in lines if l.startswith("## ")]
        assert day_headers == sorted(day_headers, reverse=True)
        assert any(l.startswith("- ") and "**alpha**" in l for l in lines)
