"""Tests for soma/context.py — format stability, token budget, heuristics, fallbacks."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import git
import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.context import (
    UnsafeTargetError,
    estimate_tokens,
    generate_context,
    write_context_file,
)

runner = CliRunner()

SECTIONS = ("## Recent work", "## Files in motion", "## Possible blockers", "## Suggested focus")


def rich_repo(tmp_path: Path) -> Path:
    """Realistic project density: long messages, deep paths, a TODO, a fix run."""
    root = tmp_path / "merops-x"
    commits = [
        (
            f"src/radar_pipeline/processing/parameter_sweep_stage_{i}.py",
            f"feat: implement radar parameter sweep stage {i} for the antenna trade study",
            NOW - timedelta(hours=30 - i * 3),
        )
        for i in range(6)
    ]
    commits += [
        (
            "docs/trade_study/antenna_gain_comparison_matrix.md",
            "docs: capture antenna gain comparison matrix results for phase one review",
            NOW - timedelta(hours=8),
        ),
        (
            "src/radar_pipeline/calibration/doppler_offset_correction.py",
            "fix: correct doppler offset sign error in the calibration coefficient table",
            NOW - timedelta(hours=4),
        ),
    ]
    make_repo(root, commits)
    todo_file = root / "src" / "radar_pipeline" / "calibration" / "doppler_offset_correction.py"
    todo_file.write_text(todo_file.read_text() + "# TODO: recalibrate against field data\n")
    return root


def section_lines(output: str, header: str) -> list[str]:
    """Bullet lines belonging to one ## section."""
    lines = output.splitlines()
    start = lines.index(header) + 1
    out = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.startswith("- "):
            out.append(line)
    return out


class TestContextFormat:
    def test_template_schema(self, tmp_path: Path) -> None:
        out = generate_context("merops-x", rich_repo(tmp_path))
        first = out.splitlines()[0]
        assert re.match(
            r"^# merops-x — Context Summary \(generated \d{4}-\d{2}-\d{2} by SOMA\)$", first
        )
        assert re.search(r"^\*\*Branch:\*\* \S+ \| \*\*Last active:\*\* .+$", out, re.M)
        assert re.search(
            r"^\*\*Activity \(7d\):\*\* \d+ commits, \d+ files? (changed|edited \(uncommitted\))$",
            out,
            re.M,
        )

    def test_all_required_sections_present(self, tmp_path: Path) -> None:
        out = generate_context("merops-x", rich_repo(tmp_path))
        for section in SECTIONS:
            assert section in out, f"missing {section}"

    def test_confidence_always_present_and_valid(self, tmp_path: Path) -> None:
        rich = generate_context("merops-x", rich_repo(tmp_path))
        plain_dir = tmp_path / "plain"
        plain_dir.mkdir()
        (plain_dir / "notes.md").write_text("notes\n")
        plain = generate_context("plain", plain_dir)
        for out in (rich, plain):
            assert re.search(r"^\*\*Confidence:\*\* (low|medium|high)$", out, re.M), out

    def test_generated_timestamp_is_today(self, tmp_path: Path) -> None:
        out = generate_context("merops-x", rich_repo(tmp_path))
        assert datetime.now(timezone.utc).strftime("%Y-%m-%d") in out.splitlines()[0]


class TestContextTokenBudget:
    def test_realistic_project_within_band(self, tmp_path: Path) -> None:
        out = generate_context("merops-x", rich_repo(tmp_path))
        tokens = estimate_tokens(out)
        assert 350 <= tokens <= 600, f"{tokens} tokens outside 350-600 band:\n{out}"

    def test_over_budget_truncates_files_first(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        full = generate_context("merops-x", root)
        squeezed = generate_context("merops-x", root, max_tokens=300)
        assert estimate_tokens(squeezed) <= 300
        # Files gave ground; all five commits survived.
        assert len(section_lines(squeezed, "## Files in motion")) < len(
            section_lines(full, "## Files in motion")
        )
        assert len(section_lines(squeezed, "## Recent work")) == len(
            section_lines(full, "## Recent work")
        )

    def test_commits_truncated_only_after_files_exhausted(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        squeezed = generate_context("merops-x", root, max_tokens=200)
        assert estimate_tokens(squeezed) <= 200
        # Files fully gone (placeholder only) before commits started shrinking.
        assert section_lines(squeezed, "## Files in motion") == [
            "- (no recent file changes)"
        ]
        commits = section_lines(squeezed, "## Recent work")
        assert 1 <= len(commits) < 5

    def test_never_truncates_branch_blockers_confidence(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        squeezed = generate_context("merops-x", root, max_tokens=200)
        assert "**Branch:**" in squeezed
        assert "**Confidence:**" in squeezed
        assert "## Possible blockers" in squeezed
        assert "## Suggested focus" in squeezed


class TestContextHeuristics:
    def test_stale_branch_flagged(self, tmp_path: Path) -> None:
        root = tmp_path / "stale"
        # Commit is 12 days old; write_text left file mtimes at "now".
        make_repo(root, [("a.py", "feat: old work", NOW - timedelta(days=12))])
        out = generate_context("stale", root)
        assert "Possible blocker detected:" in out
        assert "stale" in out.lower()

    def test_fix_storm_flagged(self, tmp_path: Path) -> None:
        root = tmp_path / "storm"
        commits = [
            (f"f{i}.py", f"fix: attempt {i} at the radar detection bug", NOW - timedelta(hours=20 - i * 4))
            for i in range(4)
        ]
        make_repo(root, commits)
        out = generate_context("storm", root)
        assert "Possible blocker detected:" in out
        assert "fix" in out.lower()

    def test_long_todo_flagged(self, tmp_path: Path) -> None:
        root = tmp_path / "todoed"
        make_repo(root, [("core.py", "feat: core logic", NOW - timedelta(hours=2))])
        (root / "core.py").write_text("# FIXME: race condition in scheduler\n")
        out = generate_context("todoed", root)
        assert "Possible blocker detected:" in out
        assert "TODO/FIXME" in out

    def test_uncommitted_edits_not_reported_as_zero_files(self, tmp_path: Path) -> None:
        root = tmp_path / "quiet"
        # Commit is 12 days old; write_text left file mtimes at "now" —
        # the activity line must not contradict the files-in-motion list.
        make_repo(root, [("a.py", "feat: old work", NOW - timedelta(days=12))])
        out = generate_context("quiet", root)
        assert "0 commits, 1 file edited (uncommitted)" in out
        assert "0 files changed" not in out

    def test_heuristics_never_assert_fact(self, tmp_path: Path) -> None:
        root = tmp_path / "stale2"
        make_repo(root, [("a.py", "feat: old work", NOW - timedelta(days=12))])
        out = generate_context("stale2", root)
        for line in section_lines(out, "## Possible blockers"):
            assert line == "- None detected" or line.startswith(
                "- Possible blocker detected:"
            ), line


class TestContextFallback:
    def test_no_events_file_falls_back_to_git(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import soma.context

        monkeypatch.setattr(soma.context, "EVENTS_DIR", tmp_path / "no-events-here")
        out = generate_context("merops-x", rich_repo(tmp_path))
        assert "# merops-x — Context Summary" in out

    def test_no_git_repo_no_crash(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        (plain / "notes.md").write_text("just notes\n")
        out = generate_context("plain", plain)
        assert "# plain — Context Summary" in out
        assert "**Confidence:** low" in out

    def test_empty_repo_valid_output(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        git.Repo.init(empty, initial_branch="main")
        out = generate_context("empty", empty)
        for section in SECTIONS:
            assert section in out

    def test_unknown_project_clean_cli_error(self, registry: Path, tmp_path: Path) -> None:
        write_registry(registry, {"alpha": tmp_path / "alpha"})
        result = runner.invoke(app, ["context", "ghost"])
        assert result.exit_code == 1
        assert "ghost" in result.output
        assert "Traceback" not in result.output

    def test_cli_outputs_context(self, registry: Path, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        write_registry(registry, {"merops-x": root})
        result = runner.invoke(app, ["context", "merops-x"])
        assert result.exit_code == 0, result.output
        assert "# merops-x — Context Summary" in result.output


class TestWatchWrite:
    def test_writes_claude_md_into_repo(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        text = generate_context("merops-x", root)
        target = write_context_file(root, text)
        assert target == root / "CLAUDE.md"
        assert "Context Summary" in target.read_text(encoding="utf-8")

    def test_refuses_to_overwrite_foreign_claude_md(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        original = "# My hand-written agent contract\n"
        (root / "CLAUDE.md").write_text(original)
        with pytest.raises(UnsafeTargetError):
            write_context_file(root, "# x — Context Summary (generated by SOMA)\n")
        assert (root / "CLAUDE.md").read_text() == original

    def test_overwrites_its_own_previous_output(self, tmp_path: Path) -> None:
        root = rich_repo(tmp_path)
        first = generate_context("merops-x", root)
        write_context_file(root, first)
        second = first.replace("Context Summary", "Context Summary")  # regenerated
        target = write_context_file(root, second)
        assert "Context Summary" in target.read_text(encoding="utf-8")


class TestContextSecurity:
    def test_credentials_in_commit_messages_redacted(self, tmp_path: Path) -> None:
        root = tmp_path / "leaky"
        make_repo(
            root,
            [("cfg.py", "fix: remove leaked api_key=SUPERSECRETVALUE123 from config", NOW - timedelta(hours=1))],
        )
        out = generate_context("leaky", root)
        assert "SUPERSECRETVALUE123" not in out
        assert "[REDACTED]" in out
