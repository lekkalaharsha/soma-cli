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
- feat: add watch mode for CLAUDE.md generation (2h ago)
- fix: correct token budget truncation order (4h ago)

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
pip install soma-cli
soma init        # scan ~/ for git repos, register them
soma status      # see all projects sorted by last activity
soma context <project>   # generate context summary
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `soma init` | Scan home directory for git repos, write `~/.soma/projects.toml` |
| `soma status` | All-projects table sorted by recency (branch, commits, files) |
| `soma status <project>` | Deep view: recent commits, files changed, warnings |
| `soma history` | Timestamped activity log, last 7 days |
| `soma history --days 30 --markdown` | Export to markdown for standups/notes |
| `soma context <project>` | Generate LLM-ready context summary |
| `soma context <project> --watch` | Keep CLAUDE.md in the repo up-to-date on file changes |
| `soma forget <project>` | Remove a project from the registry (does not delete files) |
| `soma validate` | Health check: token budget, format, secrets across all projects |

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

1. **`git log`** — commits, branches, changed files (via gitpython)
2. **File mtimes** — catches uncommitted edits git doesn't see

No event logging, no process watching. The filesystem is the daemon.

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
