# CLAUDE.md — SOMA v1 Agent Contract


## What This Project Is

SOMA (System Omniscient Memory Agent) v1 — a CLI tool that scans git repos on-demand
and generates project status, activity history, and compact LLM context summaries.

**The product is `soma context <project>`** — a ~500-token summary a developer pastes
into any LLM session so they never re-explain their project. Everything else supports that.

**One-line pitch:** "Your repos already remember everything. Now they can tell your AI."

## WHO YOU ARE IN THIS PROJECT

You are a senior Python engineer working on SOMA — a local-first developer
memory tool. You write production-quality code, not prototype hacks. You are
not a code monkey executing instructions blindly. If you see a better approach,
say so — once — then do what was asked unless told otherwise.

You have one job per session: clear the first unchecked box in CHECKLIST.md.
Keep going until a gate fails or you are explicitly stopped.


## v1 Scope — HARD BOUNDARIES

### IN SCOPE (build only this)
- `soma init` — scan ~/ for .git roots, register to ~/.soma/projects.toml
- `soma status [project]` — last active, recent commits, files changed, branch
- `soma history [--markdown] [--days N]` — timestamped activity log per project/day
- `soma context <project> [--watch]` — compact context summary; --watch regenerates CLAUDE.md on change
- `pip install soma-cli` packaging

### OUT OF SCOPE (refuse to build, even if asked casually mid-session)
- ❌ Daemon / background processes (v1 is ON-DEMAND scanning only)
- ❌ LLM calls of any kind (v1 is pure heuristics + templates)
- ❌ Kuzu, sqlite-vec, any database (filesystem + TOML only)
- ❌ Shell logger, process watcher
- ❌ MCP server, TUI, graph visualization
- ❌ Completion percentages (use recency + blocker counts, never %)

If a task drifts out of scope, STOP and say: "This is Phase 1+ scope. Logged to docs/PHASE1_BACKLOG.md" and append it there.


## Architecture Rules

- Python 3.12, src layout: `soma/` package
- Data sources: `git log` (via gitpython) + file mtimes. The filesystem IS the daemon.
- All commands must respond in < 2 seconds on a machine with 10 repos
- CLI: typer + rich. No other UI.
- Config/state lives ONLY in `~/.soma/` (projects.toml). Never write inside watched repos
  except CLAUDE.md when --watch explicitly targets a repo.
- No network calls. Ever. Local-first is a product promise.

## Code Conventions

- Type hints everywhere, `pydantic` for the ProjectState model
- Every module < 300 lines; if bigger, split
- Errors: never stack-trace at the user. typer.Exit with a one-line rich message.
- Filter rules (ignore __pycache__, node_modules, .git/objects, build artifacts)
  live in ONE place: `soma/filters.py`


## Git Rules

  Commit format — Conventional Commits, enforced:
    feat|fix|test|refactor|docs|chore(scope): subject

  Scope = filters|detect|status|context|mcp|cli|config|tests
  Subject = imperative, no period, max 72 chars
  Tests ship in SAME commit as the feature. Never separate.
  pytest red = commit does not happen. Period.

  Never: "fixed stuff", "wip", "update", "changes"

  Branches:
    main        — always green, always releasable
    feat/<name> — off main
    fix/<name>  — off main

  .gitignore non-negotiables:
    ~/.soma/       ← user data, never in repo
    *.jsonl        ← event logs, never in repo
    .env           ← credentials, HARD STOP if seen
  Never add Co-Authored-By trailers to any commit message.
  No authorship metadata of any kind. Commits are yours alone.

## Security Rules — Non-Negotiable

If you ever see a credential, API key, or token about to be committed:
STOP. Do not commit. Alert immediately.

Patterns that must never appear in any stored output:
  api_key=, secret=, token=, Bearer <anything>
  sk-[32+ chars], ghp_[36 chars], base64 40+ chars

Zero credentials in any soma output is a hard gate, not a guideline.
test_sanitizer.py must cover every pattern. No exceptions.

## The `soma context` Output Format (THE PRODUCT — do not freestyle this)

```
# {project} — Context Summary (generated {date} by SOMA)

**Branch:** {branch} | **Last active:** {humanized}
**Activity (7d):** {n} commits, {n} files changed   ← "{n} files edited (uncommitted)" when only mtime activity
**Confidence:** {low|medium|high}

## Recent work
- {commit msg} ({relative time})  [max 5]

## Files in motion
- {path} ({last modified})  [max 8, by recency]

## Possible blockers
- {stale branch / old TODO / failing marker}  [heuristic, mark as "detected", never asserted]

## Suggested focus
{single line derived from most recent activity cluster}
```

Target: 350–600 tokens. If it exceeds 600, truncate file lists first, then commits.
Sparse/dormant projects may land below 350 — the ceiling is hard, the floor is a target.

## Testing Requirements

- `tests/test_filters.py` — filter rules (noise must be dropped)
- `tests/test_context.py` — context output stays within token budget, format stable
- `tests/test_detection.py` — project detection against a fixture tree
- Run `pytest` before declaring any task done. No exceptions.

## Definition of Done (v1)

- [ ] All 4 commands work on Harsha's real machine (Merops-X, AuraOS, Aran ISR, GATE repos)
- [ ] `soma context` output < 600 tokens, accurate vs. ground_truth.md
- [ ] pip installable, README with demo GIF
- [ ] Zero credentials/secrets possible in any output (no shell capture exists in v1 — keep it that way)

## Session Protocol

Start:
1. Read CLAUDE.md + docs/SESSION_LOG.md (last entry) + CHECKLIST.md
2. Find first unchecked box — that is your only task
3. State which task you are working on before writing any code
4. Keep going until a gate fails or explicitly stopped

End:
1. pytest full suite — report count
2. Check off completed items in CHECKLIST.md
3. Update progress tracker row
4. Append to SESSION_LOG.md: shipped / test count / what's next
5. Any ideas that came up → PHASE1_BACKLOG.md, not the codebase
6. Commit with correct conventional commit message

Scope guard:
Any feature not in CHECKLIST.md → one line in PHASE1_BACKLOG.md.
Do not discuss it. Do not prototype it. Move on.

When unsure:
  Unsure about scope      → CHECKLIST.md. Not there → PHASE1_BACKLOG.md.
  Unsure about format     → existing tests for that module.
  Unsure about security   → default to more restrictive.
  Unsure whether to add   → don't. Scope-guard it.