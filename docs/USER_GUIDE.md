# SOMA — End-User Guide (v1.0)

Welcome to SOMA (System Omniscient Memory Agent). SOMA scans your local repositories and active changes to construct high-density, structured markdown summaries for your AI coding assistants.

This guide provides a comprehensive manual covering SOMA installation, configuration, standard workflow commands, and integrations.

---

## 1. Installation

Install SOMA from PyPI. Choose the installation tier that matches your workflow:

```bash
# Core CLI (no heavy dependencies)
pip install soma-cli

# Core CLI + Model Context Protocol (MCP) server
pip install 'soma-cli[mcp]'

# Core CLI + Interactive Textual TUI
pip install 'soma-cli[tui]'

# Full Installation (TUI + MCP)
pip install 'soma-cli[all]'
```

---

## 2. Core Workflows & Commands

### Initialization (`soma init`)
Scans your system directory for git roots (up to a depth of 4 levels) and registers them:
```bash
soma init
```
*   *Note: SOMA does not modify your local repository settings or directories during initialization. The registry is written to `~/.soma/projects.toml`.*

### Repository Dashboard (`soma status`)
Lists registered projects sorted by their last active timestamp:
```bash
soma status
```
For a detailed deep-dive into a single project:
```bash
soma status my-project
```

### Context Generation (`soma context`)
Generates a compact markdown summary of your project:
```bash
soma context my-project
```
*   **Copy directly to clipboard**:
    ```bash
    soma context my-project --copy
    ```
*   **Limit time window**:
    ```bash
    soma context my-project --since 14d
    ```
*   **Custom output path** (prevents repository pollution):
    ```bash
    soma context my-project --out ~/.soma/contexts/my-project.md
    ```

---

## 3. Integrations

### Model Context Protocol (MCP)
Integrate SOMA directly into Claude Desktop or Cursor so your AI can query your repositories natively without copy-pasting:

1.  Install the SOMA MCP server configuration:
    ```bash
    soma mcp install
    ```
2.  Restart your Claude Desktop client.
3.  Ask Claude: `List my SOMA projects` or `Get the context of project X`.

### Terminal UI (TUI) Dashboard
Interact with SOMA graphically in the terminal:
```bash
soma tui
```
*   Use `↑` and `↓` arrow keys to navigate projects.
*   Press `c` to copy the selected project's context.
*   Press `n` to append a manual annotation note.
*   Press `r` to refresh the dashboard.

---

## 4. Configuration Options

SOMA settings live globally in `~/.soma/config.toml`. Manage settings via the CLI:

### List Config Keys
```bash
soma config list
```

### Set Config Parameters
```bash
soma config set scan_timeout 5
soma config set dormant_days 14
soma config set token_ceiling 500
```

*   **`scan_timeout`** (default: `2`): Hard timeout limit in seconds to scan a repository's git logs and active files.
*   **`dormant_days`** (default: `30`): Cutoff threshold for file walk mtimes. Files untouched longer than this limit are excluded.
*   **`token_ceiling`** (default: `600`): Maximum token budget for context summaries. SOMA automatically truncates files first, then commits to respect this ceiling.
