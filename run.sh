#!/usr/bin/env bash
# Run the Internship Personnel Tracker
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV="/tmp/tracker-venv"

if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment at $VENV ..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q flask
fi

echo "Starting server at http://localhost:5000"
"$VENV/bin/python" app.py
