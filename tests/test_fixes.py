from pathlib import Path
import time
from datetime import timedelta
import pytest
from conftest import NOW, make_repo, write_registry
from soma.config import load_config, set_config
from soma.status import get_status_safe, collect_statuses
from soma.context import _todo_blockers

def test_scan_timeout_config(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    cfg = load_config(p)
    assert cfg["scan_timeout"] == 2
    
    set_config("scan_timeout", 10, p)
    cfg_updated = load_config(p)
    assert cfg_updated["scan_timeout"] == 10

def test_scan_timeout_applied_to_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Set up config file path override
    import soma.config as cfg_mod
    config_file = tmp_path / "config.toml"
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)
    
    # Configure tiny timeout to trigger timeout warning on a slow job
    set_config("scan_timeout", 1, config_file)
    
    # Let's assert load_config works as expected here
    cfg = load_config()
    print("LOADED CONFIG IS:", cfg)
    assert cfg["scan_timeout"] == 1
    
    # Verify that get_status_safe respects the 1s timeout
    import soma.status as status_mod
    
    def slow_get_status(name, root, since=None):
        time.sleep(1.5)
        return status_mod.ProjectStatus(name=name, root=str(root))
        
    monkeypatch.setattr(status_mod, "get_status", slow_get_status)
    
    res = get_status_safe("test-slow", tmp_path)
    assert "skipped — scan exceeded 1s" in (res.warning or "")

def test_metadata_description_prioritized(tmp_path: Path) -> None:
    # 1. Create a workspace with a pyproject.toml and a README.md
    root = tmp_path / "metadata_proj"
    root.mkdir()
    
    # pyproject has a description
    pyproject = root / "pyproject.toml"
    pyproject.write_text("[project]\ndescription = 'This is a pyproject description.'\n", encoding="utf-8")
    
    # README has a different description
    readme = root / "README.md"
    readme.write_text("# Project\nThis is a readme paragraph that provides information.", encoding="utf-8")
    
    from soma.context import _project_description
    desc = _project_description(root)
    # pyproject description should win!
    assert desc == "This is a pyproject description."

def test_package_json_description(tmp_path: Path) -> None:
    root = tmp_path / "npm_proj"
    root.mkdir()
    
    package = root / "package.json"
    package.write_text('{"description": "This is a package.json description."}', encoding="utf-8")
    
    readme = root / "README.md"
    readme.write_text("# Project\nThis is a readme paragraph.", encoding="utf-8")
    
    from soma.context import _project_description
    desc = _project_description(root)
    # package.json description should win over README
    assert desc == "This is a package.json description."

def test_readme_badge_scrubbing(tmp_path: Path) -> None:
    root = tmp_path / "badge_proj"
    root.mkdir()
    
    # README contains badges before the description paragraph
    readme = root / "README.md"
    readme.write_text(
        "# Project\n"
        "[![Build Status](https://img.shields.io/travis/user/repo.svg)](https://travis-ci.org/user/repo) "
        "[![Coverage Status](https://coveralls.io/repos/github/user/repo/badge.svg)](https://coveralls.io/github/user/repo)\n\n"
        "SOMA is a CLI tool that provides project context summaries.",
        encoding="utf-8"
    )
    
    from soma.context import _project_description
    desc = _project_description(root)
    # Should skip the line full of badges and successfully extract the real paragraph
    assert desc == "SOMA is a CLI tool that provides project context summaries."

def test_todo_stale_vs_new(tmp_path: Path) -> None:
    root = tmp_path / "todo_proj"
    root.mkdir()
    
    old_time = NOW - timedelta(days=45)
    new_time = NOW - timedelta(hours=2)
    
    commits = [
        ("src/old.py", "TODO: stale task\n", old_time),
        ("src/new.py", "TODO: new task\n", new_time),
    ]
    make_repo(root, commits)
    
    files = [
        ("src/new.py", new_time),
        ("src/old.py", old_time),
    ]
    
    blockers = _todo_blockers(root, files)
    assert len(blockers) == 1
    assert "src/new.py" in blockers[0]

def test_todo_untracked_is_blocker(tmp_path: Path) -> None:
    root = tmp_path / "untracked_todo_proj"
    root.mkdir()
    
    make_repo(root, [("src/init.py", "print('hello')", NOW - timedelta(days=5))])
    
    untracked_file = root / "src" / "untracked.py"
    untracked_file.parent.mkdir(parents=True, exist_ok=True)
    untracked_file.write_text("TODO: fix this untracked file\n", encoding="utf-8")
    
    files = [
        ("src/untracked.py", NOW),
    ]
    
    blockers = _todo_blockers(root, files)
    assert len(blockers) == 1
    assert "src/untracked.py" in blockers[0]

def test_context_out_option(tmp_path: Path, registry: Path) -> None:
    proj_dir = tmp_path / "test_out_proj"
    proj_dir.mkdir()
    make_repo(proj_dir, [("README.md", "# Test Project\nThis is a test project description.\n", NOW)])
    
    write_registry(registry, {"test_out_proj": proj_dir})
    
    from soma.cli import app
    from typer.testing import CliRunner
    runner = CliRunner()
    
    out_file = tmp_path / "global_context.md"
    result = runner.invoke(app, ["context", "test_out_proj", "--out", str(out_file)])
    assert result.exit_code == 0, result.output
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "test_out_proj" in content
    assert "test project description" in content
    
    # Confirm that no CLAUDE.md was generated inside the repository folder itself
    assert not (proj_dir / "CLAUDE.md").exists()

def test_poetry_description_extracted(tmp_path: Path) -> None:
    root = tmp_path / "poetry_proj"
    root.mkdir()
    
    pyproject = root / "pyproject.toml"
    pyproject.write_text("[tool.poetry]\ndescription = 'This is a poetry project description.'\n", encoding="utf-8")
    
    from soma.context import _project_description
    desc = _project_description(root)
    assert desc == "This is a poetry project description."

def test_cargo_description_extracted(tmp_path: Path) -> None:
    root = tmp_path / "cargo_proj"
    root.mkdir()
    
    cargo = root / "Cargo.toml"
    cargo.write_text("[package]\ndescription = 'This is a cargo project description.'\n", encoding="utf-8")
    
    from soma.context import _project_description
    desc = _project_description(root)
    assert desc == "This is a cargo project description."

def test_setup_cfg_description_extracted(tmp_path: Path) -> None:
    root = tmp_path / "setup_proj"
    root.mkdir()
    
    setup = root / "setup.cfg"
    setup.write_text("[metadata]\ndescription = This is a setup.cfg project description.\n", encoding="utf-8")
    
    from soma.context import _project_description
    desc = _project_description(root)
    assert desc == "This is a setup.cfg project description."
