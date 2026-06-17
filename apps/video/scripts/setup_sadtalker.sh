#!/usr/bin/env bash
# Setup SadTalker+pirender for Mac Apple Silicon
# This script clones the repo, checks out pirender branch, and installs deps.
# Run from project root: bash apps/video/scripts/setup_sadtalker.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VIDEO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SADTALKER_DIR="$VIDEO_DIR/models/sadtalker"

echo "=== SadTalker+pirender Setup ==="
echo "Target: $SADTALKER_DIR"

# Step 1: Clone repo (skip if exists)
if [ -d "$SADTALKER_DIR/.git" ]; then
    echo "[SKIP] SadTalker repo already cloned"
else
    echo "[1/5] Cloning SadTalker..."
    git clone https://github.com/OpenTalker/SadTalker.git "$SADTALKER_DIR"
fi

# Step 2: Checkout pirender branch (critical for Mac performance)
cd "$SADTALKER_DIR"
CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
if [ "$CURRENT_BRANCH" = "pirender" ]; then
    echo "[SKIP] Already on pirender branch"
else
    echo "[2/5] Checking out pirender branch..."
    if ! git fetch origin pull/458/head:pirender; then
        echo "[ERROR] Failed to fetch pirender branch from PR #458."
        echo "  The PR may have been merged or deleted."
        echo "  Try: git branch -a | grep pirender"
        echo "  Or check: https://github.com/OpenTalker/SadTalker/pull/458"
        exit 1
    fi
    git checkout pirender
fi

# Step 3: Install Python requirements
echo "[3/5] Installing Python requirements..."
uv pip install -r requirements.txt || {
    echo "[WARN] Bulk install failed. Trying individually..."
    while IFS= read -r pkg; do
        [ -z "$pkg" ] || [ "${pkg:0:1}" = "#" ] && continue
        uv pip install "$pkg" || echo "  [WARN] Failed: $pkg"
    done < requirements.txt
}

# Step 4: Install dlib (builds from source on macOS — needs cmake)
echo "[4/5] Installing dlib..."
if python -c "import dlib" 2>/dev/null; then
    echo "[SKIP] dlib already installed"
else
    echo "  dlib requires cmake. Installing cmake if needed..."
    command -v cmake >/dev/null 2>&1 || brew install cmake
    uv pip install dlib
fi

# Step 5: Download pretrained weights
echo "[5/5] Downloading pretrained weights..."
CHECKPOINTS_DIR="$SADTALKER_DIR/checkpoints"
if [ -d "$CHECKPOINTS_DIR" ] && [ "$(ls -A "$CHECKPOINTS_DIR" 2>/dev/null)" ]; then
    echo "[SKIP] Checkpoints already exist at $CHECKPOINTS_DIR"
else
    echo "  Downloading via SadTalker's download script..."
    if [ -f "$SADTALKER_DIR/scripts/download_models.sh" ]; then
        bash "$SADTALKER_DIR/scripts/download_models.sh"
    else
        echo "  [WARN] Download script not found. Please download weights manually."
        echo "  See: https://github.com/OpenTalker/SadTalker#2-download-trained-models"
        echo ""
        echo "  Expected locations:"
        echo "    $CHECKPOINTS_DIR/mapping_00109-model.pth.tar"
        echo "    $CHECKPOINTS_DIR/mapping_00229-model.pth.tar"
        echo "    $CHECKPOINTS_DIR/SadTalker_V0.0.2_256.safetensors"
        echo "    $CHECKPOINTS_DIR/SadTalker_V0.0.2_512.safetensors"
    fi
fi

echo ""
echo "=== Setup Complete ==="
echo "To test: PYTORCH_ENABLE_MPS_FALLBACK=1 python inference.py --facerender pirender --source_image <face.png> --driven_audio <audio.wav>"
