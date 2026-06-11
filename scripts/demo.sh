#!/usr/bin/env bash
# SOMA demo script — run this while recording with asciinema or ScreenToGif.
#
# Prerequisites (WSL2):
#   pip install soma-cli   OR   pip install -e /path/to/soma-v1-setup
#
# Record:
#   asciinema rec soma_demo.cast --overwrite
#   bash scripts/demo.sh
#   exit
#
# Convert to GIF:
#   agg soma_demo.cast soma_demo.gif --theme monokai --font-size 14

set -euo pipefail

PAUSE=1.2   # seconds between commands — adjust for recording pace

_banner() {
  echo ""
  echo "──────────────────────────────────────────"
  echo "  $1"
  echo "──────────────────────────────────────────"
  sleep 0.4
}

_run() {
  echo ""
  echo "$ $*"
  sleep 0.6
  "$@"
  sleep "$PAUSE"
}

clear
echo ""
echo "  ███████╗ ██████╗ ███╗   ███╗ █████╗"
echo "  ██╔════╝██╔═══██╗████╗ ████║██╔══██╗"
echo "  ███████╗██║   ██║██╔████╔██║███████║"
echo "  ╚════██║██║   ██║██║╚██╔╝██║██╔══██║"
echo "  ███████║╚██████╔╝██║ ╚═╝ ██║██║  ██║"
echo "  ╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝"
echo ""
echo "  Your repos already remember everything."
echo "  Now they can tell your AI."
echo ""
sleep 2

# ── 1. Register projects ─────────────────────────────────────────────────────
_banner "1 / 5  soma init — discover git repos"
_run soma init

# ── 2. Status overview ───────────────────────────────────────────────────────
_banner "2 / 5  soma status — see all projects at a glance"
_run soma status

# ── 3. Morning briefing ──────────────────────────────────────────────────────
_banner "3 / 5  soma briefing — active / quiet / dormant"
_run soma briefing

# ── 4. Context summary ───────────────────────────────────────────────────────
_banner "4 / 5  soma context — paste-ready LLM summary"
# Use whichever project name is most recognisable in your registry.
# Default: soma-v1-setup.  Override: DEMO_PROJECT=my-repo bash scripts/demo.sh
DEMO_PROJECT="${DEMO_PROJECT:-soma-v1-setup}"
_run soma context "$DEMO_PROJECT"

# ── 5. Copy to clipboard + search ────────────────────────────────────────────
_banner "5 / 5  --copy   soma search   soma config"
_run soma context "$DEMO_PROJECT" --copy
sleep 0.4
_run soma search "feat"
sleep 0.4
_run soma config list

echo ""
echo "  Done.  pip install soma-cli"
echo ""
sleep 1.5
