"""Tests for soma.detect — project detection against the fixture home tree.

Fixture tree (see conftest.fixture_home):
  repo_a, repo_b, nested/repo_c, l1/l2/l3/repo_deep4   -> real repos
  plain_dir                                            -> no .git
  node_modules/trap_repo                               -> must be skipped
  .hidden_cache/repo_d                                 -> hidden dir, skipped
  l1/l2/l3/l4/l5_too_deep                              -> beyond max depth 4
"""
from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path

import tomli_w

from soma.detect import Project, find_git_roots, register_projects


def _names(roots: list[Path]) -> set[str]:
    return {r.name for r in roots}


class TestFindGitRoots:
    def test_finds_all_real_repos(self, fixture_home: Path) -> None:
        found = _names(find_git_roots(fixture_home))
        assert {"repo_a", "repo_b", "repo_c", "repo_deep4"} <= found

    def test_skips_non_git_dir(self, fixture_home: Path) -> None:
        assert "plain_dir" not in _names(find_git_roots(fixture_home))

    def test_skips_node_modules_trap(self, fixture_home: Path) -> None:
        assert "trap_repo" not in _names(find_git_roots(fixture_home))

    def test_skips_hidden_dirs(self, fixture_home: Path) -> None:
        assert "repo_d" not in _names(find_git_roots(fixture_home))

    def test_respects_max_depth(self, fixture_home: Path) -> None:
        found = _names(find_git_roots(fixture_home, max_depth=4))
        assert "repo_deep4" in found  # exactly at the limit
        assert "l5_too_deep" not in found  # one level past it

    def test_exact_repo_set(self, fixture_home: Path) -> None:
        assert _names(find_git_roots(fixture_home)) == {
            "repo_a",
            "repo_b",
            "repo_c",
            "repo_deep4",
        }


class TestRegisterProjects:
    def test_writes_schema(self, fixture_home: Path, tmp_path: Path) -> None:
        registry_path = tmp_path / "soma_home" / "projects.toml"
        roots = find_git_roots(fixture_home)
        new, existing = register_projects(roots, path=registry_path)

        assert len(new) == 4
        assert existing == []
        with registry_path.open("rb") as f:
            data = tomllib.load(f)
        entry = data["projects"]["repo_a"]
        assert entry["root"] == str(fixture_home.resolve() / "repo_a")
        assert entry["git"] is True
        # registered_at must be parseable ISO 8601
        datetime.fromisoformat(entry["registered_at"])

    def test_merge_preserves_existing_entries(
        self, fixture_home: Path, tmp_path: Path
    ) -> None:
        registry_path = tmp_path / "soma_home" / "projects.toml"
        registry_path.parent.mkdir(parents=True)
        legacy = {
            "projects": {
                "legacy_proj": {
                    "root": "C:/somewhere/legacy_proj",
                    "git": True,
                    "registered_at": "2026-01-01T00:00:00+00:00",
                }
            }
        }
        with registry_path.open("wb") as f:
            tomli_w.dump(legacy, f)

        register_projects(find_git_roots(fixture_home), path=registry_path)

        with registry_path.open("rb") as f:
            data = tomllib.load(f)
        assert "legacy_proj" in data["projects"]  # never wiped
        assert "repo_a" in data["projects"]

    def test_rerun_is_idempotent(self, fixture_home: Path, tmp_path: Path) -> None:
        registry_path = tmp_path / "soma_home" / "projects.toml"
        roots = find_git_roots(fixture_home)

        first_new, _ = register_projects(roots, path=registry_path)
        with registry_path.open("rb") as f:
            first_data = tomllib.load(f)

        second_new, second_existing = register_projects(roots, path=registry_path)
        with registry_path.open("rb") as f:
            second_data = tomllib.load(f)

        assert len(first_new) == 4
        assert second_new == []
        assert len(second_existing) == 4
        # timestamps untouched on re-run
        assert second_data == first_data

    def test_name_collision_gets_suffix(self, tmp_path: Path) -> None:
        registry_path = tmp_path / "projects.toml"
        for parent in ("work", "personal"):
            git_dir = tmp_path / parent / "app" / ".git"
            git_dir.mkdir(parents=True)
            (git_dir / "HEAD").write_text("ref: refs/heads/main\n")

        new, _ = register_projects(find_git_roots(tmp_path), path=registry_path)

        assert {p.name for p in new} == {"app", "app-2"}
        roots = {p.root for p in new}
        assert len(roots) == 2  # both distinct roots registered

    def test_project_model_roundtrip(self) -> None:
        p = Project(
            name="x",
            root="C:/x",
            git=True,
            registered_at="2026-06-10T00:00:00+00:00",
        )
        dumped = p.model_dump(exclude={"name"})
        assert set(dumped) == {"root", "git", "registered_at"}
