#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$DIR/.venv/bin/python"
if [[ -f "$DIR/.python-cmd" ]]; then
  PY="$(head -n 1 "$DIR/.python-cmd")"
fi
if [[ "$PY" == */* && ! -x "$PY" ]]; then
  echo "On the Steam Deck, run this first: bash install.sh" >&2
  exit 1
fi
exec "$PY" "$DIR/deck_keyboard.py" "$@"
