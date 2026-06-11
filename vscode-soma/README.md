# SOMA — Project Memory (VS Code)

Live git project context in your sidebar. Click any project to copy a compact,
LLM-ready summary straight into Copilot Chat, Claude, or any AI assistant.

Powered by the [`soma-cli`](https://github.com/aranrobotics-prog/soma-cli) tool —
no LLM calls, no network, pure local git heuristics.

## Features

- **Sidebar briefing** — active / quiet / dormant projects, refreshed (debounced)
  on every file save.
- **One-click copy** — each project has a copy button; the full context summary
  lands on your clipboard.
- **Command palette** — `SOMA: Copy Context`, `SOMA: Open Briefing`,
  `SOMA: Refresh Briefing`.

## Requirements

- `soma-cli` installed and on your PATH (`pip install soma-cli`).
- Run `soma init` once to register your repositories.

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `soma.executablePath` | `soma` | Path to the soma CLI executable. |

## Build from source

```bash
cd vscode-soma
npm install
npm run compile
# F5 in VS Code to launch an Extension Development Host
```

## License

MIT
