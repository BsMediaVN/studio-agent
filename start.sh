#!/bin/bash
set -euo pipefail

# Make a freshly-installed uv visible to this shell
export PATH="$HOME/.local/bin:$PATH"

# First run on a clean machine: install uv + system prereqs + deps + frames engine
if ! command -v uv >/dev/null 2>&1; then
  echo ">> uv not found — running one-time environment bootstrap (setup_env.py)..."
  python3 setup_env.py
  export PATH="$HOME/.local/bin:$PATH"
fi

# Setup Python environment (idempotent)
echo ">> Setting up Python environment..."
make setup

# Build FE static files (skip if already built)
if [ ! -d "client/out" ]; then
  echo ">> Building Frontend..."
  cd client && npm install && npm run build && cd ..
else
  echo ">> Frontend already built (client/out exists). Skipping build."
  echo "   To rebuild: cd client && npm run build"
fi

# Start BE (serves API + static FE)
echo ""
echo ">> Starting Studio Voice API..."
echo "   http://localhost:8001"
echo ""
uv run python -m apps.studio_api
