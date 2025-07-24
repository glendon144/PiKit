#!/bin/bash

# Get the absolute path of the directory this script lives in
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/pikit-env"
PYTHON_BIN="$VENV_DIR/bin/python"
ENTRYPOINT="$PROJECT_DIR/main.py"

# Check that the virtualenv exists
if [ ! -x "$PYTHON_BIN" ]; then
  echo "❌ Virtual environment not found at $PYTHON_BIN"
  echo "Create one with: python3.13 -m venv pikit-env"
  exit 1
fi

# Check that the entrypoint exists
if [ ! -f "$ENTRYPOINT" ]; then
  echo "❌ Could not find entrypoint: $ENTRYPOINT"
  exit 1
fi

# Show which Python is running
echo "✅ Running with: $($PYTHON_BIN --version)"

# Launch the application
"$PYTHON_BIN" "$ENTRYPOINT"

