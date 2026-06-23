"""SOMA v1 CLI entry point. Commands: init, status, history, context."""
from __future__ import annotations

import subprocess
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape

from soma.detect import load_registry
from soma.runtime import registry_path
from soma.status import collect_statuses, humanize_delta

# Expose helper functions and variables for test monkeypatching / lazy imports
from soma.config import load_config, set_config, reset_config
from soma.notes import add_note, load_notes, clear_notes
from soma.cli_helpers import _copy_to_clipboard, _config_path, _parse_since, _status_to_dict, _collect_mtimes

_BASELINES_DIR = Path.home() / ".soma" / "baselines"

# Import command functions to register them
from soma.commands.core import init, status, history, forget, rename
from soma.commands.context_cmd import context, validate
from soma.commands.briefing import note, briefing
from soma.commands.organise import tag, archive, unarchive, export, search, config_app
from soma.commands.power import activity, diff, doctor, tui, drift, predict, verify, why, team
from soma.commands.integrations import hook_app, mcp_app
from soma.commands.agent import agent_app
from soma.commands.integrity_cmd import integrity

app = typer.Typer(
    help="SOMA — System Omniscient Memory Agent (v1)",
    invoke_without_command=True,
)
console = Console()
_VERSION = "0.4.1"


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", is_eager=True),
    update: bool = typer.Option(False, "--update", help="Upgrade soma-cli via pip and exit.", is_eager=True),
    uninstall: bool = typer.Option(False, "--uninstall", help="Uninstall soma-cli and exit.", is_eager=True),
) -> None:
    """Your repos already remember everything. Now they can tell your AI."""
    if version:
        typer.echo(f"soma-cli {_VERSION}")
        raise typer.Exit()
    if update:
        console.print(f"Upgrading [bold]soma-cli[/bold] (current: {_VERSION})...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "soma-cli"],
            capture_output=False,
        )
        if result.returncode != 0:
            console.print("[red]Upgrade failed.[/red] Is soma-cli on PyPI? Try: pip install --upgrade soma-cli")
            raise typer.Exit(code=1)
        raise typer.Exit()
    if uninstall:
        typer.confirm("Uninstall soma-cli?", abort=True)
        purge = typer.confirm("Also delete ~/.soma/ registry data?", default=False)
        if sys.platform == "win32":
            if purge:
                soma_dir = Path.home() / ".soma"
                if soma_dir.exists():
                    shutil.rmtree(soma_dir)
                    console.print(f"[dim]Removed {soma_dir}[/dim]")
            console.print("[green]SOMA registry cleaned. Launching uninstaller window...[/green]")
            cmd = f'cmd.exe /C "title SOMA Uninstaller & echo. & echo Uninstalling SOMA CLI... & ping 127.0.0.1 -n 2 >nul & "{sys.executable}" -m pip uninstall -y soma-cli & echo. & echo SOMA has been successfully uninstalled from your Python environment. & echo You can close this window now. & pause"'
            subprocess.Popen(
                cmd,
                creationflags=0x00000010  # CREATE_NEW_CONSOLE
            )
            raise typer.Exit()
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "soma-cli"])
        if purge:
            soma_dir = Path.home() / ".soma"
            if soma_dir.exists():
                shutil.rmtree(soma_dir)
                console.print(f"[dim]Removed {soma_dir}[/dim]")
        console.print("[green]soma-cli uninstalled.[/green]")
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return
    registry = load_registry(registry_path())
    if not registry:
        console.print("[bold]SOMA[/bold] — no projects registered yet.")
        console.print("  Run [bold cyan]soma init[/bold cyan] to scan your home directory.")
        return
    statuses = collect_statuses(registry)
    active = [s for s in statuses if s.commits_7d > 0][:5]
    console.print(f"[bold]SOMA[/bold] — {len(registry)} project(s) registered\n")
    if active:
        console.print("[bold]Recently active:[/bold]")
        for s in active:
            console.print(
                f"  [cyan]{escape(s.name):<28}[/cyan] "
                f"{humanize_delta(s.last_active):<12} "
                f"[dim]{escape(s.branch)}[/dim]"
            )
    console.print(
        f"\n[dim]soma status[/dim]          all projects"
        f"\n[dim]soma context <project>[/dim]  generate LLM summary"
        f"\n[dim]soma history[/dim]         last 7 days of activity"
    )


# Register top-level commands dynamically
app.command()(init)
app.command()(status)
app.command()(history)
app.command()(context)
app.command()(validate)
app.command()(note)
app.command()(briefing)
app.command()(export)
app.command()(rename)
app.command()(forget)
app.command()(search)
app.command()(tag)
app.command()(archive)
app.command()(unarchive)
app.command()(diff)
app.command()(doctor)
app.command()(activity)
app.command()(tui)
app.command()(drift)
app.command()(predict)
app.command()(verify)
app.command()(why)
app.command()(team)
app.command()(integrity)

# Register sub-typer command groups
app.add_typer(config_app, name="config")
app.add_typer(hook_app, name="hook")
app.add_typer(mcp_app, name="mcp")
app.add_typer(agent_app, name="agent")


if __name__ == "__main__":
    app()
