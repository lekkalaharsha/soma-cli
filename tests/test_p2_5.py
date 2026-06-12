"""Tests for P2.5 — soma activity heatmap, status --json, context --watch debounce."""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.activity import (
    _cell,
    build_activity_data,
    fetch_daily_commits,
    render_heatmap,
)
from soma.cli import app

runner = CliRunner()

TODAY = NOW.date()


# ---------------------------------------------------------------------------
# activity module unit tests
# ---------------------------------------------------------------------------
class TestCell:
    def test_zero(self) -> None:
        assert _cell(0) == "·"

    def test_one(self) -> None:
        assert _cell(1) == "░"

    def test_two(self) -> None:
        assert _cell(2) == "░"

    def test_three(self) -> None:
        assert _cell(3) == "▒"

    def test_six(self) -> None:
        assert _cell(6) == "█"

    def test_high(self) -> None:
        assert _cell(99) == "█"


class TestFetchDailyCommits:
    def test_returns_dict(self, tmp_path: Path) -> None:
        make_repo(tmp_path, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        result = fetch_daily_commits(tmp_path, 7, TODAY)
        assert isinstance(result, dict)

    def test_commit_counted(self, tmp_path: Path) -> None:
        make_repo(tmp_path, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        result = fetch_daily_commits(tmp_path, 7, TODAY)
        assert result.get(TODAY, 0) >= 1

    def test_non_git_dir_returns_empty(self, tmp_path: Path) -> None:
        bare = tmp_path / "bare"
        bare.mkdir()
        assert fetch_daily_commits(bare, 7, TODAY) == {}

    def test_old_commit_outside_window_not_counted(self, tmp_path: Path) -> None:
        make_repo(tmp_path, [("a.py", "feat: old", NOW - timedelta(days=90))])
        result = fetch_daily_commits(tmp_path, 7, TODAY)
        assert sum(result.values()) == 0

    def test_multiple_commits_same_day(self, tmp_path: Path) -> None:
        make_repo(tmp_path, [
            ("a.py", "feat: one", NOW - timedelta(hours=3)),
            ("b.py", "feat: two", NOW - timedelta(hours=2)),
        ])
        result = fetch_daily_commits(tmp_path, 7, TODAY)
        assert result.get(TODAY, 0) >= 2


class TestBuildActivityData:
    def test_returns_rows_and_dates(self, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        registry = {"alpha": {"root": str(alpha)}}
        rows, date_range = build_activity_data(registry, days=7, today=TODAY)
        assert len(rows) == 1
        assert len(date_range) == 7

    def test_date_range_correct_length(self, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        registry = {"alpha": {"root": str(alpha)}}
        _, date_range = build_activity_data(registry, days=30, today=TODAY)
        assert len(date_range) == 30

    def test_active_project_first(self, tmp_path: Path) -> None:
        active = tmp_path / "active"
        quiet = tmp_path / "quiet"
        make_repo(active, [("a.py", "feat: active", NOW - timedelta(hours=1))])
        make_repo(quiet, [("b.py", "feat: old", NOW - timedelta(days=60))])
        registry = {"active": {"root": str(active)}, "quiet": {"root": str(quiet)}}
        rows, _ = build_activity_data(registry, days=7, today=TODAY)
        assert rows[0][0] == "active"

    def test_parallel_fetch_completes(self, tmp_path: Path) -> None:
        # Create 5 repos; verify all 5 returned
        registry = {}
        for i in range(5):
            p = tmp_path / f"repo{i}"
            make_repo(p, [("f.py", f"feat: r{i}", NOW - timedelta(hours=i + 1))])
            registry[f"repo{i}"] = {"root": str(p)}
        rows, _ = build_activity_data(registry, days=7, today=TODAY)
        assert len(rows) == 5


class TestRenderHeatmap:
    def _make_rows(self, tmp_path: Path) -> tuple:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        registry = {"alpha": {"root": str(alpha)}}
        return build_activity_data(registry, days=7, today=TODAY)

    def test_renders_without_error(self, tmp_path: Path) -> None:
        rows, date_range = self._make_rows(tmp_path)
        out = render_heatmap(rows, date_range)
        assert isinstance(out, str)
        assert len(out) > 0

    def test_project_name_in_output(self, tmp_path: Path) -> None:
        rows, date_range = self._make_rows(tmp_path)
        out = render_heatmap(rows, date_range)
        assert "alpha" in out

    def test_legend_present(self, tmp_path: Path) -> None:
        rows, date_range = self._make_rows(tmp_path)
        out = render_heatmap(rows, date_range)
        assert "Legend" in out

    def test_commit_count_in_output(self, tmp_path: Path) -> None:
        rows, date_range = self._make_rows(tmp_path)
        out = render_heatmap(rows, date_range)
        assert "commits" in out

    def test_empty_rows(self) -> None:
        out = render_heatmap([], [TODAY])
        assert "(no projects)" in out

    def test_cells_correct_length(self, tmp_path: Path) -> None:
        rows, date_range = self._make_rows(tmp_path)
        out = render_heatmap(rows, date_range)
        # project row should contain 7 cells (one per day)
        for line in out.splitlines():
            if "alpha" in line:
                # strip name prefix, find cell block
                parts = line.split("  ", 1)
                cells_part = parts[1].rstrip() if len(parts) > 1 else ""
                # cells are 7 chars (one per day), possibly followed by suffix
                cell_block = cells_part.split("  ")[0] if "  " in cells_part else cells_part
                assert len(cell_block) == 7, f"expected 7 cells, got {len(cell_block)!r} from {cells_part!r}"


# ---------------------------------------------------------------------------
# soma activity CLI
# ---------------------------------------------------------------------------
class TestActivityCLI:
    def test_activity_renders(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["activity"])
        assert result.exit_code == 0, result.output
        assert "alpha" in result.output
        assert "Traceback" not in result.output

    def test_activity_days_flag(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["activity", "--days", "7"])
        assert result.exit_code == 0, result.output
        assert "7d window" in result.output

    def test_activity_invalid_days(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["activity", "--days", "400"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_activity_empty_registry(self, registry: Path, tmp_path: Path) -> None:
        # registry file doesn't exist (empty registry fixture)
        result = runner.invoke(app, ["activity"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_activity_hides_archived(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.cli as cli_mod
        import soma.detect as det
        monkeypatch.setenv("SOMA_PROJECTS_FILE", str(registry))
        active = tmp_path / "active"
        archived = tmp_path / "archived"
        make_repo(active, [("a.py", "feat: a", NOW - timedelta(hours=1))])
        make_repo(archived, [("b.py", "feat: b", NOW - timedelta(hours=1))])
        write_registry(registry, {"active": active, "archived": archived})
        from soma.detect import set_archived
        set_archived("archived", True, registry)
        result = runner.invoke(app, ["activity"])
        assert result.exit_code == 0, result.output
        assert "active" in result.output
        assert "archived" not in result.output


# ---------------------------------------------------------------------------
# status --json
# ---------------------------------------------------------------------------
class TestStatusJson:
    def test_status_json_single(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["status", "alpha", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["name"] == "alpha"
        assert "branch" in data
        assert "commits_7d" in data

    def test_status_json_all(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        beta = tmp_path / "beta"
        make_repo(alpha, [("a.py", "feat: a", NOW - timedelta(hours=1))])
        make_repo(beta, [("b.py", "feat: b", NOW - timedelta(hours=2))])
        write_registry(registry, {"alpha": alpha, "beta": beta})
        result = runner.invoke(app, ["status", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        names = {d["name"] for d in data}
        assert names == {"alpha", "beta"}

    def test_status_json_keys(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["status", "alpha", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        for key in ("name", "branch", "last_active", "commits_7d", "files_changed_7d", "recent_commits"):
            assert key in data, f"missing key: {key}"

    def test_status_json_serialisable(self, registry: Path, tmp_path: Path) -> None:
        alpha = tmp_path / "alpha"
        make_repo(alpha, [("a.py", "feat: init", NOW - timedelta(hours=1))])
        write_registry(registry, {"alpha": alpha})
        result = runner.invoke(app, ["status", "alpha", "--json"])
        assert result.exit_code == 0, result.output
        # no exception
        data = json.loads(result.output)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# _collect_mtimes helper
# ---------------------------------------------------------------------------
class TestCollectMtimes:
    def test_finds_watched_files(self, tmp_path: Path) -> None:
        from soma.cli import _collect_mtimes
        (tmp_path / "a.py").write_text("x")
        result = _collect_mtimes(tmp_path)
        assert any("a.py" in k for k in result)

    def test_ignores_hidden_dirs(self, tmp_path: Path) -> None:
        from soma.cli import _collect_mtimes
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x")
        result = _collect_mtimes(tmp_path)
        assert not any(".hidden" in k for k in result)

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        from soma.cli import _collect_mtimes
        empty = tmp_path / "empty"
        empty.mkdir()
        result = _collect_mtimes(empty)
        assert result == {}
