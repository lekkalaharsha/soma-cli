"""SOMA integrations commands: hook (git hooks), mcp (model context protocol)."""
from __future__ import annotations

import json
import shlex
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from soma.runtime import registry_path
from soma.detect import load_registry

console = Console()

_HOOK_CONTENT = """\
#!/bin/sh
# soma post-commit hook — auto-regenerates CLAUDE.md
soma context {project}
"""

hook_app = typer.Typer(help="Manage soma git hooks.")


@hook_app.command("install")
def hook_install(
    project: str = typer.Argument(..., help="Project to install hook for."),
) -> None:
    """Write a post-commit hook that regenerates context after every commit."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    hook_dir = Path(entry["root"]) / ".git" / "hooks"
    if not hook_dir.exists():
        console.print(f"[red]No .git/hooks directory in {escape(entry['root'])}[/red]")
        raise typer.Exit(code=1)

    hook_path = hook_dir / "post-commit"
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if "soma context" not in existing:
            console.print(
                f"[yellow]Existing post-commit hook not from soma.[/yellow] "
                f"Edit {escape(str(hook_path))} manually to add: soma context {escape(project)}"
            )
            raise typer.Exit(code=1)

    # Security fix: Use shlex.quote to prevent command injection in hook script.
    hook_path.write_text(_HOOK_CONTENT.format(project=shlex.quote(project)), encoding="utf-8", newline="\n")
    try:
        hook_path.chmod(0o755)
    except OSError:
        pass  # Windows — chmod no-op, git will still run it
    console.print(
        f"[green]Hook installed[/green] → {escape(str(hook_path))}\n"
        f"  After every [bold]git commit[/bold] in [bold]{escape(project)}[/bold], "
        f"CLAUDE.md regenerates automatically."
    )


@hook_app.command("remove")
def hook_remove(
    project: str = typer.Argument(..., help="Project to remove hook from."),
) -> None:
    """Remove the soma post-commit hook from a project."""
    registry = load_registry(registry_path())
    if not registry:
        console.print("No projects registered yet. Run [bold]soma init[/bold] first.")
        raise typer.Exit(code=1)
    entry = registry.get(project)
    if entry is None:
        console.print(f"[red]Unknown project:[/red] {escape(project)}.")
        raise typer.Exit(code=1)

    hook_path = Path(entry["root"]) / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        console.print(f"[dim]No post-commit hook at {escape(str(hook_path))}.[/dim]")
        return

    existing = hook_path.read_text(encoding="utf-8")
    if "soma context" not in existing:
        console.print(
            f"[yellow]Hook at {escape(str(hook_path))} was not installed by soma — leaving it.[/yellow]"
        )
        raise typer.Exit(code=1)

    hook_path.unlink()
    console.print(f"[green]Removed[/green] soma hook from [bold]{escape(project)}[/bold].")


mcp_app = typer.Typer(help="Manage the SOMA MCP server for Claude Desktop / Cursor.")


@mcp_app.command("start")
def mcp_start() -> None:
    """Start the SOMA MCP server (stdio transport — Claude Desktop spawns this)."""
    try:
        from soma.mcp import mcp as _mcp  # noqa: PLC0415
    except ImportError:
        console.print("[red]fastmcp not installed.[/red] Run: pip install 'soma-cli[mcp]'")
        raise typer.Exit(code=1)
    if sys.stdin.isatty():
        console.print(
            "[yellow]soma mcp start[/yellow] is designed to be spawned by Claude Desktop, not run directly.\n"
            "To connect SOMA to Claude Desktop, run:\n"
            "  [bold cyan]soma mcp install[/bold cyan]\n"
            "Then restart Claude Desktop."
        )
        raise typer.Exit()
    _mcp.run()


@mcp_app.command("install")
def mcp_install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print config change without writing."),
) -> None:
    """Register soma MCP server in Claude Desktop config."""
    from soma.cli import _config_path

    soma_bin = shutil.which("soma") or sys.executable.replace("python", "soma")
    server_entry = {
        "command": soma_bin,
        "args": ["mcp", "start"],
    }

    cfg_path = _config_path()
    if dry_run:
        console.print(f"[dim]Config path:[/dim] {escape(str(cfg_path))}")
        console.print("[dim]Would add:[/dim]")
        console.print(json.dumps({"mcpServers": {"soma": server_entry}}, indent=2))
        return

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    config: dict = {}
    if cfg_path.exists():
        try:
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}

    config.setdefault("mcpServers", {})["soma"] = server_entry
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"[green]Installed[/green] soma MCP server → {escape(str(cfg_path))}")
    console.print("Restart Claude Desktop to activate.")


@mcp_app.command("uninstall")
def mcp_uninstall() -> None:
    """Remove soma from Claude Desktop MCP config."""
    from soma.cli import _config_path

    cfg_path = _config_path()
    if not cfg_path.exists():
        console.print("[dim]Claude Desktop config not found — nothing to remove.[/dim]")
        return

    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        console.print("[red]Could not parse config file.[/red]")
        raise typer.Exit(code=1)

    servers = config.get("mcpServers", {})
    if "soma" not in servers:
        console.print("[dim]soma not found in MCP config.[/dim]")
        return

    del servers["soma"]
    config["mcpServers"] = servers
    cfg_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    console.print(f"[green]Removed[/green] soma from {escape(str(cfg_path))}")
