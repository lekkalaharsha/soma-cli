<div align="center">

# SOMA — System Omniscient Memory Agent

**Your repos already remember everything. Now they can tell your AI.**

[![PyPI version](https://img.shields.io/pypi/v/soma-cli?color=brightgreen&logo=pypi&logoColor=white)](https://pypi.org/project/soma-cli/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?logo=opensourceinitiative&logoColor=white)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-436%20passing-brightgreen?logo=pytest&logoColor=white)](tests/)
[![Build](https://img.shields.io/badge/build-passing-brightgreen?logo=github&logoColor=white)](https://github.com/aranrobotics-prog/soma-cli/actions)
[![Code style](https://img.shields.io/badge/style-ruff-orange)](https://github.com/astral-sh/ruff)

</div>

---

SOMA is a **local-first, on-demand CLI** that scans your git repositories, tracks co-change file coupling, and generates compact (~500 token) structured summaries for AI agents.

Before touching any file, SOMA predicts which other files you'll likely need to edit based on your repo's history:

```bash
soma predict my-project soma/context.py
```

```
soma predict — my-project / soma/context.py
Found 12 commit(s) touching this file.

If you edit this file, history says you'll likely also need:

┌────────────────────────┬────────────┬────────┬─────────────────┐
│ File                   │ Co-changed │ Out of │      Confidence │
├────────────────────────┼────────────┼────────┼─────────────────┤
│ tests/test_context.py  │         10 │     12 │   usually (83%) │
│ soma/status.py         │          9 │     12 │   usually (75%) │
└────────────────────────┴────────────┴────────┴─────────────────┘
```

These coupling rules automatically feed into context blocker heuristics. If you touch a file but forget to edit its co-change partner, SOMA flags the mismatch in your context summary:

```bash
soma context my-project
```

```markdown
# my-project — Context Summary (generated 2026-06-17 by SOMA)

**Branch:** main | **Last active:** 2h ago
**Activity (7d):** 1 commit, 1 file changed
**Confidence:** high

**What this is:** Local-first CLI that scans git repos and generates LLM context summaries.

## Recent work
- feat: optimize scanning logic (+8/-2) (2h ago)

## Files in motion
- soma/context.py (2h ago)

## Possible blockers
- [detected] touched soma/context.py but missed co-change partner tests/test_context.py (83% coupling)

## Suggested focus
Continue recent work in `soma/` — last commit: "feat: optimize scanning logic".
```

Paste that. Your AI now knows exactly what you've done and what you missed.

---

## Why SOMA?

Every time you start a new AI session you re-explain the same project. What branch, what you last did, what's broken, what to focus on next. SOMA reads it from git and says it for you — accurately, every time, in under 500 tokens.

| Without SOMA | With SOMA |
|-------------|-----------|
| Type 3 paragraphs of project context | `soma context my-project` → paste |
| AI guesses what files are relevant | SOMA knows what changed in the last 7 days |
| Context goes stale after 1 commit | Always current — reads live git log |
| Re-explain every new chat session | MCP: Claude fetches context automatically |

---

## ⚡ Key Features

- **Live git context** — branch, commits, files changed, last active — from the actual repo, not a stale note
- **Works without git** — if git is not on PATH, SOMA degrades gracefully using file mtimes (no commits/branches)
- **350–600 token budget** — fits in any model's context without burning your limit
- **Blocker detection** — stale branches, old TODOs, fix-storm commits flagged as heuristics
- **MCP server** — Claude Desktop and Cursor query your repos automatically via `soma mcp install`
- **Git hook** — `soma hook install` regenerates `CLAUDE.md` after every commit automatically
- **Morning briefing** — active / quiet / dormant tier view across all your projects
- **100% offline** — no network calls, no API keys, no background daemons, no telemetry
- **Credential redaction** — API keys, bearer tokens, and `sk-` prefixes are stripped from all output

---

## 📥 Installation

### Recommended — pipx (isolated, stays out of your global environment)

```bash
pipx install soma-cli              # core
pipx install 'soma-cli[mcp]'       # + Claude Desktop / Cursor integration
pipx install 'soma-cli[tui]'       # + terminal UI dashboard
pipx install 'soma-cli[all]'       # everything
```

> **Why pipx?** It installs CLI tools in isolated virtualenvs and puts the binary on your PATH automatically. No virtualenv activation. No dependency conflicts. `pipx upgrade soma-cli` keeps it fresh.
> 
> Install pipx: `pip install pipx` or `brew install pipx`

---

### Modern — uv (fastest install, 10-100× faster than pip)

```bash
uv tool install soma-cli
uv tool install 'soma-cli[all]'

# upgrade later
uv tool upgrade soma-cli
```

> **Why uv?** Same isolated-install behaviour as pipx, but dramatically faster. Becoming the Python community standard.
> 
> Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

### Standard — pip

```bash
pip install soma-cli
pip install 'soma-cli[mcp]'        # FastMCP server support
pip install 'soma-cli[tui]'        # Textual TUI dashboard
pip install 'soma-cli[all]'        # MCP + TUI
```

> Recommended inside a virtual environment. Avoid installing globally with pip directly.

---

### From Source (contributors)

```bash
git clone https://github.com/aranrobotics-prog/soma-cli
cd soma-cli

# Windows
python -m venv .venv && .venv\Scripts\activate

# macOS / Linux
python -m venv .venv && source .venv/bin/activate

pip install -e ".[all]"
pytest                              # 436 tests — must be green
```

---

### Verify Installation

```bash
soma --version                      # soma-cli 0.4.0
soma doctor                         # health check: git, config, registry
```

---

## 🚀 60-Second Quick Start

```bash
# 1. Scan your home directory for git repos (depth ≤ 4)
soma init

# 2. See all your projects — branch, last active, commits this week
soma status

# 3. Generate a context summary for your AI
soma context my-project

# 4. Copy straight to clipboard
soma context my-project --copy

# 5. What should I work on this morning?
soma briefing
```

---

## 📋 Output Format

SOMA's context follows a **strict, stable format** designed to be maximally useful to any LLM:

```
# {project} — Context Summary (generated {date} by SOMA)

**Branch:** {branch} | **Last active:** {humanized time}
**Activity (7d):** {n} commits, {n} files changed
**Confidence:** low | medium | high
**What this is:** {description from pyproject.toml / Cargo.toml / README}

## Notes              ← your manual annotations (soma note)
## Recent work        ← last 5 commits with +/- diff stats
## Files in motion    ← last 8 touched files by mtime
## Possible blockers  ← heuristic: stale branch / old TODO / fix-storm
## Suggested focus    ← single derived line from most recent activity
```

**Token budget:** 350–600 tokens enforced. Files truncate first, then commits. The ceiling is a hard limit — the floor is a target.

---

## 🛠️ All Commands

### Core

| Command | Description |
|---------|-------------|
| `soma init [--base PATH]` | Scan for git repos → register to `~/.soma/projects.toml` |
| `soma status [project] [--json]` | All-projects dashboard or deep single-project view |
| `soma history [--days N] [--markdown]` | Timestamped commit log per day — Obsidian/standup ready |
| `soma context <project> [--watch] [--out PATH]` | Generate LLM context summary ← **the product** |
| `soma validate [project] [--save-baseline]` | Check token budget, format, and secrets |
| `soma briefing [--all]` | Morning view: active / quiet / dormant tiers |

### Annotations & Organisation

| Command | Description |
|---------|-------------|
| `soma note <project> "text"` | Add a manual note surfaced in context output |
| `soma tag <project> <tag>` | Add/remove/list tags for grouping |
| `soma archive <project>` | Hide from briefing (still accessible) |
| `soma unarchive <project>` | Restore to active tier |
| `soma rename <old> <new>` | Rename in registry + migrate notes |
| `soma forget <project>` | Remove from registry (files untouched) |
| `soma export [project] [--dir PATH]` | Write context summaries to `.md` files |
| `soma search <keyword>` | Grep across all project context summaries |

### Power Tools

| Command | Description |
|---------|-------------|
| `soma activity [--days N]` | ASCII heatmap of commit frequency |
| `soma diff <project>` | Unified diff vs saved baseline |
| `soma drift <project> [--since TS]` | View changes since last session or timestamp |
| `soma predict <project> <file>` | Co-change coupling analysis for a file |
| `soma verify <project> <claim>` | Fact-check a natural language claim against git history |
| `soma why <project> <file>` | Explain a file's history and evolution from commits |
| `soma team <project>` | Local author activity summary table |
| `soma agent init <project> [--print]` | Generate AI agent ruleset (`AGENTS.md`) from project structure |
| `soma agent sync <project>` | Update AI agent ruleset context |
| `soma doctor` | Registry integrity, stale roots, config bounds |
| `soma tui` | Textual interactive dashboard |

### Configuration

| Command | Description |
|---------|-------------|
| `soma config list` | Show all config keys with current and default values |
| `soma config get <key>` | Print one value |
| `soma config set <key> <value>` | Set a value (bounds-validated) |
| `soma config reset <key>` | Reset to default |

**Config keys:** `dormant_days` (30) · `token_ceiling` (600) · `max_files` (8) · `max_commits` (5) · `scan_timeout` (5)

---

## 💾 Data Storage

SOMA stores everything in `~/.soma/`:

| File | Purpose |
|------|---------|
| `~/.soma/projects.toml` | Project registry — names, root paths, tags, notes |
| `~/.soma/baselines/` | Saved diff baselines per project |
| `~/.soma/sessions.toml` | Last-seen timestamps per project (for `soma drift`) |

No database. No network calls. No cloud. Plain TOML — readable, portable, versionable.

---

## 🔌 Integrations

### MCP — Claude Desktop & Cursor (automatic context, no paste needed)

```bash
pip install 'soma-cli[mcp]'        # install FastMCP dependency
soma mcp install                   # register with Claude Desktop
# restart Claude Desktop
```

Claude now calls `get_context("my-project")` automatically before answering questions about your repos. No copy-paste. Always current.

**MCP tools exposed:**

| Tool | What Claude uses it for |
|------|------------------------|
| `list_projects()` | "What projects do you have?" |
| `get_context(project)` | Any project-specific question |
| `search_projects(keyword)` | "Which project uses Influx?" |
| `get_briefing()` | "What should I work on today?" |
| `get_history(project, ...)` | "Show me the commit history for this project" |
| `get_diff(project, ...)` | "What lines of code changed in this project?" |
| `get_drift(project, ...)` | "What changed since my last question/session?" |
| `get_predict(project, file, ...)` | "Predict what files might change alongside this one" |

Also works with: **Cursor · Windsurf · Zed · Open WebUI · Continue.dev · AnythingLLM**

---

### Git Hook — auto-regenerate CLAUDE.md on every commit

```bash
soma hook install my-project
# → .git/hooks/post-commit writes CLAUDE.md after every git commit
```

Perfect for **Antigravity, Codex CLI, and file-reading agents** that watch `AGENTS.md` / `CLAUDE.md` automatically.

---

### 👥 Team Sync — Serverless & Off-Grid

SOMA implements a decentralized, daemonless team synchronization model. It requires no central database, cloud server, or background processes:
- **Git as the Source of Truth**: By installing SOMA's git hooks (`soma hook install`), every team member's local commit automatically updates `CLAUDE.md` (or `AGENTS.md`) within the repository.
- **Off-Grid Syncing**: When developers push their changes and others pull, the updated context files are shared via standard Git. Your AI agents read the latest context directly from the repository state.
- **Zero Configuration**: No API keys, no network traffic to external servers, and zero setup for new team members beyond cloning the repo.

---

### 🧠 Agent Rulesets vs. Graphify

SOMA's `soma agent init <project>` command generates a comprehensive `AGENT.md` profile mapping your project's shape. Here is how SOMA's approach differs from **Graphify**:
- **Directory & Commit Coupling**: Unlike Graphify, which performs deep AST (Abstract Syntax Tree) parsing of source code to build strict dependency graphs, SOMA is lightweight and language-agnostic. It analyzes your project's actual directory layout and git logs to find social co-change coupling.
- **No AST Parsing Overhead**: SOMA does not need language-specific parsers or compilers. It is extremely fast and runs in milliseconds on any type of codebase.
- **Focus on AI Rulesets**: SOMA produces high-level, human-readable rulesets summarizing the actual developer activity and implicit coupling patterns, designed specifically for LLM context injection.

---

### Other AI Tools

| Tool | Best method |
|------|------------|
| Claude Desktop / Cursor | `soma mcp install` |
| Codex CLI | `soma context <project> --out AGENTS.md` |
| Antigravity | `soma hook install <project>` |
| ChatGPT / Gemini | `soma context <project> --copy` → paste |
| Ollama + Open WebUI | `soma mcp install` |
| Ollama raw | `soma context <project> \| ollama run llama3` |

---

### TUI Dashboard

```bash
pip install 'soma-cli[tui]'
soma tui
```

Navigate with `↑↓`, press `n` to add a note, `c` to copy context, `r` to refresh.

---

## 🛡️ What SOMA Does NOT Do

These are design decisions, not limitations:

| Never | Why |
|-------|-----|
| **No background daemon** | On-demand only — zero idle resource usage |
| **No LLM calls** | Pure heuristics + templates — no API key, no cost, no network |
| **No network requests** | Local-first is a product promise, not a preference |
| **No database** | Filesystem + TOML — readable, portable, versionable |
| **No credential storage** | SOMA reads git data; never stores tokens or keys |
| **No completion percentages** | Uses recency + blocker counts — percentages lie |

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

You are free to use, fork, modify, and distribute SOMA in personal and commercial projects.
See [`LICENSE`](LICENSE) for the full text.

---

## 🤝 Contributing

Contributions are welcome — bug reports, heuristic improvements, new language support, MCP tool additions.
Read [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full guide.

### Quick PR Checklist

- [ ] `pytest` passes — zero failures (436+ tests)
- [ ] New behaviour has tests in `tests/`
- [ ] Commit follows Conventional Commits (`feat(scope): subject`)
- [ ] No secrets, tokens, or API keys in the diff
- [ ] Module size < 300 lines — split if larger
- [ ] New output fields routed through `soma.sanitize.redact()`

### Commit Format

```
type(scope): subject

Types:  feat · fix · docs · test · refactor · chore
Scopes: cli · config · context · detect · filters · mcp · status · tests
Rules:  imperative, lowercase, no period, max 72 chars
        tests ship in the SAME commit as the feature — never separate
```

### What We Welcome vs. Won't Accept

| Welcome | Won't Accept |
|---------|-------------|
| Faster git log parsing | Network calls or cloud sync |
| Better README extraction | Background daemons |
| New language support (`go.mod`, `pom.xml`) | Any database |
| New MCP tools | LLM calls inside SOMA |
| Shell completions | Completion percentages |

### Setting Up

```bash
git clone https://github.com/aranrobotics-prog/soma-cli
cd soma-cli
python -m venv .venv

.venv\Scripts\activate         # Windows
source .venv/bin/activate       # macOS / Linux

pip install -e ".[all]"
pytest                          # must be green before writing any code
```

### Reporting Bugs

Open a [GitHub Issue](https://github.com/aranrobotics-prog/soma-cli/issues) with:
- OS + Python version (`python --version`)
- Exact command you ran
- Full output (sanitised — remove any credentials)
- What you expected

### Security

Zero credentials in SOMA output is a **hard gate, not a guideline**.
If you find a credential-leakage or path-traversal bug — do not open a public issue. Contact the maintainer directly.

---

<div align="center">

Built for developers who talk to AI every day.

[GitHub](https://github.com/aranrobotics-prog/soma-cli) · [PyPI](https://pypi.org/project/soma-cli/) · [Issues](https://github.com/aranrobotics-prog/soma-cli/issues) · [MIT License](LICENSE)

</div>
