#!/usr/bin/env bash
# Setup full video pipeline environment
# Run from project root: bash apps/video/scripts/setup_environment.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "=== Video Pipeline Environment Setup ==="

# Step 1: Python dependencies
echo "[1/5] Installing Python dependencies..."
pip install openai-whisper 2>/dev/null && echo "  openai-whisper: OK" || echo "  [WARN] openai-whisper failed"
pip install mediapipe 2>/dev/null && echo "  mediapipe: OK" || echo "  [WARN] mediapipe failed"
pip install psutil 2>/dev/null && echo "  psutil: OK" || echo "  [WARN] psutil failed"

# Step 2: Check FFmpeg
echo "[2/5] Checking FFmpeg..."
if command -v ffmpeg >/dev/null 2>&1; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1)
    echo "  $FFMPEG_VERSION"

    if ffmpeg -codecs 2>/dev/null | grep -q "libvpx-vp9\|vp9"; then
        echo "  VP9 codec: OK"
    else
        echo "  [WARN] VP9 codec not found. Install: brew install ffmpeg"
    fi

    if ffmpeg -codecs 2>/dev/null | grep -q "libx264\|h264"; then
        echo "  H.264 codec: OK"
    else
        echo "  [WARN] H.264 codec not found"
    fi
else
    echo "  [FAIL] FFmpeg not installed. Install: brew install ffmpeg"
fi

# Step 3: Check ffprobe
echo "[3/5] Checking ffprobe..."
if command -v ffprobe >/dev/null 2>&1; then
    echo "  ffprobe: OK"
else
    echo "  [WARN] ffprobe not found (usually bundled with ffmpeg)"
fi

# Step 4: Node.js + Puppeteer
echo "[4/5] Setting up Puppeteer..."
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version)
    echo "  Node.js: $NODE_VERSION"

    (
        cd "$SCRIPT_DIR"
        if [ -f "node_modules/puppeteer/package.json" ]; then
            echo "  [SKIP] Puppeteer already installed"
        else
            echo "  Installing puppeteer..."
            npm init -y 2>/dev/null || true
            npm install puppeteer && echo "  puppeteer: OK" || echo "  [WARN] puppeteer install failed"
        fi
    )
else
    echo "  [FAIL] Node.js not installed"
fi

# Step 5: Create output directories
echo "[5/5] Creating output directories..."
mkdir -p "$PROJECT_ROOT/output/studio/video"
echo "  output/studio/video/: OK"

echo ""
echo "=== Environment Setup Complete ==="
echo "Run validation: bash apps/video/scripts/run_validation.sh"
