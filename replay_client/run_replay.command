#!/bin/zsh

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ -x "$PROJECT_DIR/client/.venv/bin/python" ]]; then
  exec "$PROJECT_DIR/client/.venv/bin/python" "$PROJECT_DIR/replay_client/main.py"
fi

exec python3 "$PROJECT_DIR/replay_client/main.py"
