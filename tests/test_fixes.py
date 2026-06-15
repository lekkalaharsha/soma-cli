from pathlib import Path
import time
import pytest
from soma.config import load_config, set_config
from soma.status import get_status_safe, collect_statuses

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
