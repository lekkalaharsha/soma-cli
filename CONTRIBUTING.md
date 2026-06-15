# Contributing to SOMA

Thank you for your interest in contributing to SOMA! We welcome pull requests, bug reports, and suggestions. 

To maintain the quality, security, and local-first architecture of the project, please follow these guidelines.

---

## 🏛️ Project Guidelines & Scope

### In Scope
- Performance improvements to git log parsing, file walks, and caching.
- Context extraction heuristics (better suggested focus clustering, better README prose detectors).
- Ecosystem package integration (parsing dependency structures from other languages/frameworks).
- MCP protocol updates and client integrations.
- Command-line interface usability.

### Out of Scope (Phase 1/2)
- Network calls or API integrations (SOMA is strictly local-first and does not speak to the cloud).
- Background daemons or persistent background file watchers (we run on-demand or on Git hooks).
- Databases (state must remain strictly in filesystem plain TOML files).

---

## 🛠️ Code Conventions

*   **Python Target**: Python 3.12+
*   **Type Safety**: Strictly type hint all function signatures and use `pydantic` models for structured data.
*   **Module Size Limit**: Keep all files strictly **under 300 lines of code**. If a file grows beyond 300 lines, split it into submodules.
*   **Error Handling**: Never print raw tracebacks to the end-user. Catch errors and terminate cleanly using `typer.Exit` combined with formatted `rich` console messages.

---

## 🧪 Testing Requirements

SOMA is highly verified by unit and integration tests. Any contribution must maintain 100% test compatibility:
*   Write unit tests in the `tests/` directory for any new logic or bug fixes.
*   Run the test suite using `pytest` to make sure everything is green before submitting a PR.
*   Use mock/fixture directories (like `fixtures/home`) and monkeypatches rather than writing files into real directories.

To execute the tests:
```bash
pytest
```

---

## 📝 Commit Conventions

We enforce the **Conventional Commits** standard to automate changelog generation. Commits must follow this format:

```text
type(scope): subject
```

### Types
- `feat`: A new user-facing feature.
- `fix`: A bug fix.
- `docs`: Documentation updates.
- `test`: Adding or correcting tests.
- `refactor`: Code restructuring with no behavior changes.
- `chore`: Infrastructure or setup changes.

### Scopes
Use one of the following scopes:
- `cli`
- `config`
- `context`
- `detect`
- `filters`
- `mcp`
- `status`
- `tests`

### Rules
- Subject must be in the imperative mood, start lowercase, have no ending punctuation, and be under 72 characters.
- Never use generic messages like `wip`, `fixes`, or `changes`.
- Never add `Co-Authored-By` trailers. Commits are credited to the author alone.

---

## 🛡️ Security Rules

Zero credentials in any SOMA output is a hard project gate.
*   Never commit API keys, tokens, or credentials of any kind.
*   Any new context output field must be routed through `soma.sanitize.redact` to strip sensitive patterns.
*   Write unit tests for any new sanitization rules in `tests/test_sanitizer.py`.
