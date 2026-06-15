# SOMA
### System Omniscient Memory Agent

> Your repos already remember everything. Now they can tell your AI.

---

## The Problem

You open a project you haven't touched in three days.
You spend time reconstructing where you left off.
You open Claude Code or Cursor.
You spend more time re-explaining what the project even is.

Every AI session starts from zero. Every time.

SOMA fixes that with one command.

---

## What SOMA Does

```bash
soma context merops-x
```

```
# SOMA Context — merops-x
Generated: 2026-06-10 14:32

## Active Branch
phase1-trade-study

## Recent Activity
fix: radar param matrix update (3 days ago)

## Files in Motion (7d)
- docs/trade_study.md
- requirements/matrix.xlsx
- soma/filters.py

## Possible Blockers
Possible blocker detected: branch has no commit in 7 days despite file activity
Possible blocker detected: fix-storm pattern (4 fix commits in 24h on 2026-06-07)

## Suggested Focus
docs/trade_study.md (most recently modified)

---
*Confidence: medium*
*SOMA cannot see: external blockers, verbal decisions, whiteboard work.*
*Correct with: soma note merops-x "waiting on PX4 vendor response"*
```

Paste that into any LLM session. Claude already knows your project.
No re-explaining. No manual notes. No MEMORY.md to maintain.

---

## Install

```bash
pip install soma-cli
soma init
```

That's it. SOMA scans your home directory, finds all git repos, and registers them.
No config. No API keys. No cloud. Everything stays on your machine.

---

## Commands

```bash
# Detect and register all projects
soma init

# See all projects at a glance
soma status

# Deep view of one project
soma status <project>

# Generate LLM context summary (THE PRODUCT)
soma context <project>

# Keep CLAUDE.md updated automatically as you work
soma context <project> --watch

# Start MCP server (for Claude Code / Cursor integration)
soma mcp start
```

---

## MCP Integration — Claude Code

SOMA exposes a local MCP server so Claude Code queries your project state
automatically before generating code. No manual paste required.

Add to `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "soma": {
      "command": "soma",
      "args": ["mcp", "start"],
      "env": {}
    }
  }
}
```

Add to Cursor MCP settings:

```json
{
  "soma": {
    "url": "http://localhost:6123",
    "name": "SOMA Project Memory"
  }
}
```

Verify it's running:
```bash
soma mcp start
curl http://localhost:6123/health
```

Once connected, Claude Code calls `get_project_state` before every response.
Your project context loads automatically. You explain nothing.

---

## How It Works

SOMA reads what's already on your machine:

- Git log — commits, branches, timestamps
- File mtimes — what you actually touched and when
- Heuristics — stale branches, fix-storm patterns, TODO/FIXME markers

No daemon. No background process. No file watcher running 24/7.
SOMA scans on demand when you run a command. Fast and silent.

Output is always honest about what it knows vs. what it inferred:

```
*Confidence: medium*
*SOMA cannot see: external blockers, verbal decisions, whiteboard work.*
```

When SOMA is wrong, correct it in one line:

```bash
soma note merops-x "PX4 SITL resolved — new blocker is ROS2 bridge latency"
```

---

## soma status

```
$ soma status

SOMA — Project Awareness
────────────────────────────────────────────────────────────
Project        Last Active    Branch                Files (7d)
────────────────────────────────────────────────────────────
aran-isr       2h ago         mpc-refactor          12
merops-x       3d ago         phase1-trade-study     4
auraos         5d ago         main                   1
gate-2027      8d ago         —                      0
────────────────────────────────────────────────────────────
```

---

## What v1 Does NOT Do

Be clear on what you're installing:

- **No daemon.** SOMA does not run in the background watching your files.
  It scans on demand. If you want always-fresh context, use `--watch`.

- **No LLM summarization.** v1 is pure heuristics — git log, file mtimes,
  pattern matching. No AI inference, no API calls, no Ollama required.

- **No shell command logging.** SOMA does not capture your terminal history.
  It reads git and files only.

- **No completion percentages.** Engineering completion is not measurable
  from file artifacts. SOMA never pretends otherwise.

- **No cloud.** Your work history never leaves your machine. No telemetry.
  No usage analytics. No account required.

- **No magic.** SOMA cannot see a 2-hour debug session that produced one
  commit. It cannot see the email you're waiting on. It cannot see the
  architecture decision you made on a whiteboard. It tells you what it
  knows and flags what it cannot see.

---

## Accuracy

SOMA's accuracy depends on your git hygiene.

Projects with frequent, descriptive commits → high confidence output.
Projects with rare commits and many editor auto-saves → medium/low confidence.

Gate 4 threshold (validated on real projects):
- Recency ranking: > 90% correct
- File attribution: > 85% match to actual work
- False event rate: < 10% noise past filter

If SOMA's output is wrong for a project, use `soma note` to correct it.
Corrections surface in the next `soma context` run.

---

## Supported File Types

SOMA tracks changes to:

```
.py .ts .js .rs .go .cpp .c .h .hpp
.md .yaml .yml .toml .json .env.example
Dockerfile CMakeLists.txt Makefile
.sh .bash .zsh
```

SOMA ignores:

```
__pycache__/ node_modules/ .git/objects/
dist/ build/ *.pyc *.log *.lock
```

Filter rules live in `soma/filters.py` — single source of truth.

---

## Requirements

- Python 3.12+
- Git installed and on PATH
- Projects must have at least one git commit for full output
  (non-git directories show file mtime only)

---

## Privacy

SOMA runs entirely on your machine.

- No network calls from any SOMA process
- No telemetry, crash reporting, or usage analytics
- User data stored in `~/.soma/` — never in the repo
- MCP server runs on localhost only — never exposed externally
- Full data export: `soma export` → JSON

---

## Roadmap

**v1 (current)** — on-demand scanning, git + mtime, heuristic context, MCP stub

**Phase 1** — LLM summarization (local Ollama), knowledge graph, natural language queries,
MCP with real data

**Phase 2** — Agent coordination, code reviewer, TUI dashboard

**Phase 3** — AuraOS bridge, multi-machine sync (local network), proactive insights

---

## Contributing

SOMA is open-core. CLI and MCP server are open source.

```bash
git clone https://github.com/harsha/soma-cli
cd soma-cli
pip install -e .
pytest  # must be green before any PR
```

Conventional commits enforced. See CLAUDE.md for full dev contract.

Issues and PRs welcome. Feature requests → checked against v1 scope first.

---

## License

MIT

---

*SOMA v0.1.0 — Built by Harsha / Aran Technologies*
*Local-first. No cloud. No excuses.*
