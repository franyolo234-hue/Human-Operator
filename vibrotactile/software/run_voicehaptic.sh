#!/usr/bin/env bash
# VoiceHaptic — Quick Start Script
# Usage: ./run_voicehaptic.sh [mode]
#   modes: voice (default), receiver, calibrate, sim

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-voice}"
LANG="${2:-en}"
PORT="${CONTROLLER_PORT:-}"

# Download Vosk model if needed
download_model() {
    local lang="$1"
    local model_dir="models"
    mkdir -p "$model_dir"

    if [ "$lang" = "de" ]; then
        local model_name="vosk-model-small-de-0.15"
        local url="https://alphacephei.com/vosk/models/$model_name.zip"
    else
        local model_name="vosk-model-small-en-us-0.15"
        local url="https://alphacephei.com/vosk/models/$model_name.zip"
    fi

    if [ ! -d "$model_dir/$model_name" ]; then
        echo "[Setup] Downloading Vosk model: $model_name"
        wget -q --show-progress -O "/tmp/$model_name.zip" "$url"
        unzip -q "/tmp/$model_name.zip" -d "$model_dir/"
        rm "/tmp/$model_name.zip"
        echo "[Setup] Model ready: $model_dir/$model_name"
    else
        echo "[Setup] Model found: $model_dir/$model_name"
    fi
}

case "$MODE" in
    voice)
        echo "=== VoiceHaptic: Voice Command Mode ==="
        download_model "$LANG"
        python3 voice_bridge.py --lang "$LANG" ${PORT:+--port "$PORT"}
        ;;
    receiver)
        echo "=== VoiceHaptic: HTTP Receiver Mode ==="
        python3 receiver.py ${PORT:+--port "$PORT"}
        ;;
    calibrate)
        echo "=== VoiceHaptic: Calibration GUI ==="
        python3 pattern_designer.py
        ;;
    sim)
        echo "=== VoiceHaptic: Simulation Mode (no hardware) ==="
        download_model "$LANG"
        python3 voice_bridge.py --sim --lang "$LANG"
        ;;
    *)
        echo "Usage: $0 [voice|receiver|calibrate|sim] [en|de]"
        exit 1
        ;;
esac
