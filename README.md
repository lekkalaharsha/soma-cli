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

## 📄 License — MIT

```
MIT License

Copyright (c) 2026 SOMA CLI Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

You are free to use, fork, modify, and distribute SOMA in personal or commercial projects.
The full license text is also available in the [`LICENSE`](LICENSE) file in the root of the repository.

---

## 🤝 Contributing

Contributions are welcome — bug reports, performance improvements, heuristic refinements, and MCP client integrations. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide.

### Quick Contribution Checklist

Before opening a Pull Request, make sure:

- [ ] `pytest` passes with zero failures (`341+` tests in the suite)
- [ ] New behaviour has accompanying tests in `tests/`
- [ ] Commit follows **Conventional Commits** format (see below)
- [ ] No API keys, tokens, or secrets appear anywhere in the diff
- [ ] Module size stays under 300 lines — split if needed
- [ ] Any new context output field is routed through `soma.sanitize.redact()`

### What We Welcome

| Area | Examples |
|------|---------|
| **Performance** | Faster git log parsing, smarter file-walk budgets |
| **Heuristics** | Better README description extraction, smarter blocker detection |
| **Language support** | Cargo.toml, `package.json`, `go.mod`, CMakeLists parsing |
| **MCP** | New tools, Cursor/Windsurf client support |
| **CLI UX** | Better error messages, shell completions |
| **Tests** | Edge cases, fixture repos, platform-specific paths |

### What We Will Not Accept (v1 Hard Boundaries)

| Request | Why |
|---------|-----|
| Network calls / cloud sync | SOMA is strictly local-first — no exceptions |
| Background daemons | On-demand scanning only |
| Databases | Filesystem + TOML is sufficient |
| LLM calls inside SOMA | Pure heuristics — no API keys, no cost |
| Completion percentages | Use recency + blocker counts instead |

### Commit Format

```
type(scope): subject
```

**Types:** `feat` · `fix` · `docs` · `test` · `refactor` · `chore`

**Scopes:** `cli` · `config` · `context` · `detect` · `filters` · `mcp` · `status` · `tests`

**Rules:**
- Imperative mood, lowercase start, no ending punctuation, max 72 chars
- Tests ship in the **same commit** as the feature — never separate
- Never: `wip`, `fixes`, `update`, `changes`
- Never add `Co-Authored-By` trailers

**Examples:**
```bash
feat(context): add hot-files list to suggested focus line
fix(status): skip stale registry roots before parallel scan
test(filters): add node_modules nested path edge case
docs(cli): update mcp install instructions for Cursor
```

### Setting Up Locally

```bash
git clone https://github.com/aranrobotics-prog/soma-cli
cd soma-cli
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -e ".[all]"
pytest                           # must be green before you start
```

### Reporting Bugs

Open an issue on [GitHub Issues](https://github.com/aranrobotics-prog/soma-cli/issues) with:
- Your OS and Python version (`python --version`)
- The exact command you ran
- The full error output (or a sanitised version with no credentials)
- What you expected to happen

### Security Disclosures

If you discover a credential-leakage or path-traversal vulnerability, **do not open a public issue**. Email the maintainer directly. We treat zero-credential output as a hard project gate — any bypass is a critical bug.

---

<p align="center">
  Built with ❤️ for developers who talk to AI every day.<br>
  <a href="https://github.com/aranrobotics-prog/soma-cli">GitHub</a> ·
  <a href="https://pypi.org/project/soma-cli/">PyPI</a> ·
  <a href="LICENSE">MIT License</a>
</p>
