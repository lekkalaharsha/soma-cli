"""Tests for soma/config.py — load, set, get, reset, validation, context integration."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import NOW, make_repo, write_registry
from soma.cli import app
from soma.config import DEFAULTS, VALID_KEYS, load_config, reset_config, set_config
from soma.context import generate_context

runner = CliRunner()


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg == DEFAULTS

    def test_set_value_overrides_default(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("dormant_days", 14, p)
        cfg = load_config(p)
        assert cfg["dormant_days"] == 14
        assert cfg["token_ceiling"] == DEFAULTS["token_ceiling"]

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        p.write_text("not valid toml ][[[")
        cfg = load_config(p)
        assert cfg == DEFAULTS


class TestSetConfig:
    def test_set_valid_key(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("max_files", 5, p)
        assert load_config(p)["max_files"] == 5

    def test_set_unknown_key_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Unknown key"):
            set_config("invalid_key", 42, tmp_path / "c.toml")

    def test_set_out_of_range_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="must be between"):
            set_config("dormant_days", 0, tmp_path / "c.toml")
        with pytest.raises(ValueError, match="must be between"):
            set_config("dormant_days", 999, tmp_path / "c.toml")

    def test_set_multiple_keys_independent(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("dormant_days", 14, p)
        set_config("max_commits", 3, p)
        cfg = load_config(p)
        assert cfg["dormant_days"] == 14
        assert cfg["max_commits"] == 3

    def test_overwrites_previous_value(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("max_files", 5, p)
        set_config("max_files", 10, p)
        assert load_config(p)["max_files"] == 10


class TestResetConfig:
    def test_reset_removes_override(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("dormant_days", 7, p)
        assert reset_config("dormant_days", p) is True
        assert load_config(p)["dormant_days"] == DEFAULTS["dormant_days"]

    def test_reset_nonexistent_returns_false(self, tmp_path: Path) -> None:
        assert reset_config("dormant_days", tmp_path / "none.toml") is False

    def test_reset_key_not_set_returns_false(self, tmp_path: Path) -> None:
        p = tmp_path / "config.toml"
        set_config("max_files", 4, p)
        assert reset_config("dormant_days", p) is False


class TestConfigInContext:
    def test_max_files_config_limits_files_section(self, tmp_path: Path, monkeypatch) -> None:
        import soma.config as cfg_mod
        config_file = tmp_path / "config.toml"
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)
        import soma.context as ctx
        monkeypatch.setattr(ctx, "load_config", lambda: cfg_mod.load_config(config_file))

        set_config("max_files", 2, config_file)
        root = tmp_path / "proj"
        commits = [
            (f"src/file{i}.py", f"feat: file {i}", NOW - timedelta(hours=i + 1))
            for i in range(6)
        ]
        make_repo(root, commits)
        out = generate_context("proj", root)
        file_lines = [l for l in out.splitlines() if l.startswith("- ") and ".py" in l]
        assert len(file_lines) <= 2

    def test_token_ceiling_config_respected(self, tmp_path: Path, monkeypatch) -> None:
        import soma.config as cfg_mod
        config_file = tmp_path / "config.toml"
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)
        import soma.context as ctx
        monkeypatch.setattr(ctx, "load_config", lambda: cfg_mod.load_config(config_file))

        set_config("token_ceiling", 300, config_file)
        root = tmp_path / "proj2"
        commits = [
            (f"src/module_{i}.py", f"feat: implement module {i} with a long descriptive message", NOW - timedelta(hours=i + 1))
            for i in range(8)
        ]
        make_repo(root, commits)
        from soma.context import estimate_tokens
        out = generate_context("proj2", root)
        assert estimate_tokens(out) <= 300


class TestConfigCLI:
    def test_config_list_shows_all_keys(self, registry: Path) -> None:
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0, result.output
        for key in VALID_KEYS:
            assert key in result.output

    def test_config_get_known_key(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.config as cfg_mod
        import soma.cli as cli_mod
        config_file = tmp_path / "config.toml"
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)
        monkeypatch.setattr(cli_mod, "load_config", lambda: cfg_mod.load_config(config_file))
        result = runner.invoke(app, ["config", "get", "dormant_days"])
        assert result.exit_code == 0, result.output
        assert str(DEFAULTS["dormant_days"]) in result.output

    def test_config_set_and_get(self, registry: Path, tmp_path: Path, monkeypatch) -> None:
        import soma.config as cfg_mod
        import soma.cli as cli_mod
        config_file = tmp_path / "config.toml"
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)
        monkeypatch.setattr(cli_mod, "set_config", lambda k, v: cfg_mod.set_config(k, v, config_file))
        monkeypatch.setattr(cli_mod, "load_config", lambda: cfg_mod.load_config(config_file))
        result = runner.invoke(app, ["config", "set", "dormant_days", "14"])
        assert result.exit_code == 0, result.output
        assert "14" in result.output

    def test_config_set_unknown_key_fails(self, registry: Path) -> None:
        result = runner.invoke(app, ["config", "set", "bad_key", "5"])
        assert result.exit_code == 1
        assert "Unknown key" in result.output
        assert "Traceback" not in result.output

    def test_config_set_bad_value_fails(self, registry: Path) -> None:
        result = runner.invoke(app, ["config", "set", "dormant_days", "notanint"])
        assert result.exit_code == 1
        assert "integer" in result.output.lower()
        assert "Traceback" not in result.output

    def test_config_get_unknown_key_fails(self, registry: Path) -> None:
        result = runner.invoke(app, ["config", "get", "nonexistent"])
        assert result.exit_code == 1
        assert "Unknown key" in result.output
        assert "Traceback" not in result.output

    def test_config_reset_unknown_key_fails(self, registry: Path) -> None:
        result = runner.invoke(app, ["config", "reset", "bad_key"])
        assert result.exit_code == 1
        assert "Traceback" not in result.output
