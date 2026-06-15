# SOMA — System Omniscient Memory Agent (v1)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/aranrobotics-prog/soma-cli/actions)

> **"Your repositories already remember everything. Now they can tell your AI."**

SOMA is an on-demand, local-first CLI utility and Model Context Protocol (MCP) server that scans git repositories and active file modifications to generate high-density, structured markdown context summaries. 

Simply feed SOMA's output into any LLM session (Claude, ChatGPT, Gemini, Copilot) to orient your coding assistant instantly without copy-pasting codebases or wasting token limits.

---

## ⚡ Key Features

*   **Zero-Knowledge Orientation**: Automatically extracts functional descriptions from standard project files (`pyproject.toml`, `Cargo.toml`, `package.json`, `setup.cfg`, or `README.md`), removing badge/link noise.
*   **Active Context Modeling**: Captures recent commits, active branch names, and uncommitted edits sorted by modification recency.
*   **Stale TODO Exclusions**: Analyzes recently modified files containing `TODO` or `FIXME` comments using `git blame`. Ignores legacy comments committed >30 days ago, flagging only active/new blockers.
*   **Model Context Protocol (MCP)**: Exposes workspace metadata as tools, enabling Claude Desktop, Cursor, or other MCP clients to query repository contexts natively.
*   **Privacy & Security Guaranteed**: 100% offline, zero network telemetry, no background daemons, and automatic sanitization of credentials/API keys.
*   **Custom Watch Outputs**: Supports `--watch` with `--out` parameters to continuously compile summaries into a global cache, preventing local repository pollution.

---

## 📥 Installation

Install core SOMA or pull in optional integration modules:

```bash
pip install soma-cli            # Core CLI (no heavy dependencies)
pip install 'soma-cli[mcp]'     # Adds FastMCP server support
pip install 'soma-cli[tui]'     # Adds Textual Terminal UI Dashboard
pip install 'soma-cli[all]'     # Full installation (TUI + MCP)
```

Verify the installation:
```bash
soma --version
```

---

## 🚀 Quick Start

1.  **Initialize Registry**: Scan your directories (up to depth 4) to detect git repositories and write them to `~/.soma/projects.toml`:
    ```bash
    soma init
    ```
2.  **View Status Dashboard**: Inspect recent branch activity, commit counts, and file changes across all registered projects:
    ```bash
    soma status
    ```
3.  **Generate LLM Context**: Produce a dense, structured summary for your coding assistant:
    ```bash
    soma context my-project
    ```
4.  **Copy Directly to Clipboard**:
    ```bash
    soma context my-project --copy
    ```

---

## 📋 Context Format Output Example

```markdown
# my-project — Context Summary (generated 2026-06-15 by SOMA)

**Branch:** main | **Last active:** 2h ago
**Activity (7d):** 8 commits, 15 files changed
**Confidence:** high

**What this is:** A local-first CLI tool that scans git repos and generates LLM context summaries.

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

---

## 🛠️ CLI Commands & Sub-typers

### Core Workflow Commands

| Command | Usage | Description |
| :--- | :--- | :--- |
| `init` | `soma init [--base <path>]` | Scans workspace for git repositories and registers them (never overwrites). |
| `status` | `soma status [project]` | Displays activity dashboard. If project specified, opens deep detailed view. |
| `history` | `soma history [--days N] [--markdown]` | Outputs a timestamped activity event log per day per project. |
| `context` | `soma context <project>` | Generates the high-density markdown context summary. |
| `validate` | `soma validate [project]` | Runs verification checks (token budget, sections, secrets check). |

### Project & Config Management

| Command | Usage | Description |
| :--- | :--- | :--- |
| `note` | `soma note <project> "<text>"` | Attaches manual annotations that are surfaced in context outputs. |
| `rename` | `soma rename <old> <new>` | Renames registered project and safely migrates its notes. |
| `forget` | `soma forget <project>` | Removes project from registry without deleting local files. |
| `tag` | `soma tag <project> <tag>` | Attaches search/group tags to projects (`--list` and `--remove` supported). |
| `archive` | `soma archive <project>` | Marks project as dormant, hiding it from daily briefings. |
| `config` | `soma config set <key> <value>` | Manages parameters (`dormant_days`, `token_ceiling`, `scan_timeout`, etc.). |

---

## 🔌 Integrations

### 1. Model Context Protocol (MCP)
Let your AI query your local repositories natively. Register SOMA as an MCP server with Claude Desktop:

```bash
soma mcp install
```
*Restart Claude Desktop, and your AI can directly list projects and read contexts using exposed tools (`list_projects`, `get_context`, `search_projects`, `get_briefing`).*

### 2. Interactive TUI Dashboard
Launch a rich terminal-based dashboard built on `textual`:
```bash
soma tui
```
*Use `↑↓` keys to navigate projects, `n` to append a note, `c` to copy context, and `r` to refresh the dashboard.*

### 3. Git post-commit Hook Automation
Automatically regenerate your agent documentation files (e.g. `CLAUDE.md`) on every commit:
```bash
soma hook install my-project
```

### 4. VS Code Sidebar Extension
Compile and package the sidebar webview panel inside `vscode-soma/`:
```bash
cd vscode-soma
npm install
npm run compile
```

---

## 🛡️ SOMA Guarantees (What it does NOT do)

*   **No Resident Daemons**: Runs strictly on-demand. Zero background resource utilization.
*   **No External API Keys**: Fully heuristic templates. No LLM calls are made on SOMA's side.
*   **No Network Activity**: Strictly local-first. Your code never leaves your workstation.
*   **Credential Sanitizer**: Automatically redacts API keys, bearer tokens, or `sk-` credentials from commits and focus suggestions.

---

## 📄 License

SOMA is open-source software licensed under the [MIT License](LICENSE).
