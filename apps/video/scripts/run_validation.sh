#!/usr/bin/env bash
# Run video pipeline environment validation
# Usage: bash apps/video/scripts/run_validation.sh [--skip-sadtalker] [--skip-whisper]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

export PYTORCH_ENABLE_MPS_FALLBACK=1

echo "Running video pipeline environment validation..."
echo ""

python3 "$SCRIPT_DIR/validate_environment.py" "$@"
