#!/bin/bash
set -euo pipefail

# Setup Python environment
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
