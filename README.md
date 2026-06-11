# soma-cli

**soma is a CLI tool that scans git repos on-demand and generates compact LLM context summaries** — so you never re-explain your project to an AI assistant.

```
soma context myproject
```
```
# myproject — Context Summary (generated 2026-06-11 by SOMA)

**Branch:** main | **Last active:** 2h ago
**Activity (7d):** 8 commits, 15 files changed
**Confidence:** high

**What this is:** A CLI tool that scans git repos and generates LLM context summaries.

## Recent work
- feat: add watch mode (+18/-2) (2h ago)
- fix: correct token budget truncation order (+6/-4) (4h ago)

## Files in motion
- src/context.py (2h ago)
- tests/test_context.py (2h ago)

## Possible blockers
- None detected

## Suggested focus
Continue recent work in `src/` — last commit: "feat: add watch mode"
```

Paste this into any LLM session. Your AI already knows the project.

---

## Install

```bash
pip install soma-cli            # core CLI (no heavy deps)
pip install 'soma-cli[mcp]'     # + MCP server for Claude Desktop / Cursor
pip install 'soma-cli[tui]'     # + textual TUI dashboard
pip install 'soma-cli[all]'     # everything

soma init        # scan ~/ for git repos, register them
soma status      # see all projects sorted by last activity
soma context <project>   # generate context summary
```

The core install stays lean — `fastmcp` and `textual` are optional extras,
pulled in only if you use `soma mcp` or `soma tui`.

---

## Commands

### Core

| Command | What it does |
|---------|-------------|
| `soma init` | Scan home directory for git repos, write `~/.soma/projects.toml` |
| `soma status` | All-projects table sorted by recency (branch, commits, files) |
| `soma status <project>` | Deep view: recent commits, files changed, warnings |
| `soma status --json` | Machine-readable status for scripting |
| `soma history` | Timestamped activity log, last 7 days |
| `soma history --days 30 --markdown` | Export to markdown for standups/notes |
| `soma context <project>` | Generate LLM-ready context summary (with diff stats per commit) |
| `soma context <project> --watch` | Keep CLAUDE.md in the repo up-to-date (3s debounce) |
| `soma context <project> --format json` | Structured output for tool integration |
| `soma context <project> --since 7d` | Limit activity window (`YYYY-MM-DD`, `7d`, `2w`, `yesterday`) |
| `soma context <project> --copy` | Copy summary straight to clipboard |
| `soma briefing` | Morning roll-up: active / quiet / dormant projects + pending notes |
| `soma forget <project>` | Remove a project from the registry (does not delete files) |
| `soma rename <old> <new>` | Rename a project (migrates its notes) |
| `soma note <project> "text"` | Attach a manual note surfaced in context output |
| `soma validate` | Health check: token budget, format, secrets across all projects |
| `soma --version` / `--update` / `--uninstall` | Version, pip upgrade, interactive uninstall |

### Organisation

| Command | What it does |
|---------|-------------|
| `soma tag <project> <tag>` | Tag a project (`--remove` / `--list` too) |
| `soma context --group <tag>` | Combine every tagged project into one context block |
| `soma briefing --group <tag>` | Filter the briefing to one tag |
| `soma archive <project>` | Hide a dormant project from briefing (`soma briefing --all` to show) |
| `soma unarchive <project>` | Restore an archived project |
| `soma export [project]` | Dump context summaries to `<name>_context.md` files |
| `soma search <keyword>` | Grep across all project context summaries |
| `soma config set <key> <value>` | Tune `token_ceiling`, `max_files`, `dormant_days`, `max_commits` |

### Power tools

| Command | What it does |
|---------|-------------|
| `soma activity [--days N]` | ASCII commit heatmap across all projects |
| `soma diff <project>` | What changed since the last saved baseline |
| `soma validate --save-baseline` / `--compare` | Snapshot context, then diff future runs against it |
| `soma doctor` | Diagnose registry, stale roots, config bounds, git availability |
| `soma hook install <project>` | post-commit hook that auto-rewrites CLAUDE.md (`hook remove` too) |
| `soma tui` | Interactive terminal dashboard (textual) |
| `soma mcp start` / `install` | MCP server for Claude Desktop / Cursor (`uninstall` too) |

---

## Integrations

### MCP — let your AI query repos directly

soma ships an MCP (Model Context Protocol) server. Claude Desktop or Cursor call
soma's tools directly — no copy-paste:

```bash
soma mcp install     # writes mcpServers.soma into claude_desktop_config.json
# restart Claude Desktop, then ask: "what are my soma projects?"
```

Tools exposed: `list_projects`, `get_context`, `search_projects`, `get_briefing`.
Still no LLM calls or network on soma's side — the server reads git, the client is the LLM.

### TUI dashboard

```bash
soma tui
```

Left panel: projects (↑↓ to navigate). Right: live context summary + notes.
Keys — `r` refresh · `n` add note · `c` copy context · `q` quit.

### VS Code extension

`vscode-soma/` — sidebar briefing panel with click-to-copy context, auto-refresh on
file save, and a `SOMA: Copy Context` command. Build with `cd vscode-soma && npm install && npm run compile`.

---

## What soma does NOT do

- **No daemon.** Scanning is on-demand only. Nothing runs in the background.
- **No LLM calls.** Output is pure heuristics + templates — no AI, no API key, no cost.
- **No database.** State lives in `~/.soma/projects.toml` (TOML, plain text).
- **No network.** Fully offline. Your code never leaves your machine.
- **No shell capture.** soma never runs your code or reads environment variables.
- **No secrets.** Output is redacted for `api_key=`, `token=`, `sk-*` patterns.

---

## How it works

soma reads two sources:

1. **`git log`** — commits, branches, changed files, diff stats (via gitpython)
2. **File mtimes** — catches uncommitted edits git doesn't see

No event logging, no process watching. The filesystem is the daemon.

---

## Context format

Every `soma context` output follows a fixed schema an LLM can parse reliably:

- **Branch + last active + activity** — orientation line
- **What this is** — extracted from README or pyproject.toml description
- **Recent work** — last 5 commits with `(+insertions/-deletions)` diff stats
- **Files in motion** — up to 8 files sorted by recency (omits files untouched >30d)
- **Possible blockers** — stale branch, TODO/FIXME in active files, fix storms
- **Suggested focus** — derived from most recent activity cluster

Target: 350–600 tokens. Active repos typically land at 340–400.

---

## Configuration

Projects registry: `~/.soma/projects.toml` — auto-written by `soma init`.

soma never writes inside your repos except `CLAUDE.md` when `--watch` is explicitly used.
It will refuse to overwrite a `CLAUDE.md` it didn't generate (your hand-written agent contract is safe).

---

## Requirements

- Python 3.12+
- git

---

## License

MIT
