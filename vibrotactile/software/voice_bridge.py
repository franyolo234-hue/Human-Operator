#!/usr/bin/env python3
"""
VoiceHaptic — Offline Voice Command Bridge
============================================
Replaces the LLM-based command pipeline from Human Operator with
an offline keyword spotting system. No cloud. No API keys. No latency.

Architecture:
  Microphone → Vosk (offline STT) → Keyword Matcher → Serial → ESP32

The system uses a compact Vosk model (~50MB) for real-time speech-to-text,
then matches recognized words against a preset command dictionary.
This is fundamentally different from Human Operator's approach of sending
voice + camera to Claude for action planning — here, the mapping from
voice to motor command is deterministic and instant.

Why this matters for elderly users at Johannesheim:
  1. Works without internet (critical for device reliability)
  2. Sub-100ms response time (immediate feedback builds trust)
  3. No ongoing API costs (sustainable for humanitarian deployment)
  4. Simple command vocabulary (cognitive accessibility)
  5. Works in German and English (configurable)

Dependencies:
  pip install vosk pyaudio pyserial sounddevice numpy

Vosk models:
  English: vosk-model-small-en-us-0.15 (~40MB)
  German:  vosk-model-small-de-0.15 (~45MB)
  Download from: https://alphacephei.com/vosk/models
"""

import json
import os
import sys
import time
import threading
import queue
import struct
import numpy as np
import serial
import serial.tools.list_ports

# Vosk for offline speech recognition
try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    print("[!] Vosk not installed. Run: pip install vosk")

# Sounddevice for cross-platform audio capture
try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    print("[!] sounddevice not installed. Run: pip install sounddevice")


# ============================================================
# CONFIGURATION
# ============================================================
SAMPLE_RATE = 16000
BLOCK_SIZE = 8000  # 0.5 second blocks
CHANNELS = 1

# Wake word — activates command listening
WAKE_WORD = "operator"

# Command vocabulary — maps spoken phrases to firmware commands
# Each entry: { recognized_phrase: firmware_command }
# The matcher uses fuzzy substring matching to handle speech recognition errors
COMMAND_MAP = {
    # English commands
    "close hand":    "close_hand",
    "close":         "close_hand",
    "fist":          "close_hand",
    "grab":          "grip",

    "open hand":     "open_hand",
    "open":          "open_hand",
    "release":       "open_hand",
    "let go":        "open_hand",

    "relax":         "relax",
    "calm":          "relax",
    "rest":          "relax",
    "soothing":      "relax",

    "tremor":        "tremor",
    "shake":         "tremor",
    "steady":        "tremor",
    "stabilize":     "tremor",

    "grip":          "grip",
    "hold":          "grip",
    "squeeze":       "grip",

    "pinch":         "pinch",
    "pick":          "pinch",
    "precise":       "pinch",

    "wave":          "wave",
    "wrist":         "wave",

    "stop":          "stop",
    "off":           "stop",
    "quit":          "stop",
    "enough":        "stop",
    "halt":          "stop",

    # German commands (for Johannesheim residents)
    "hand schließen": "close_hand",
    "schließen":      "close_hand",
    "faust":          "close_hand",
    "greifen":        "grip",

    "hand öffnen":    "open_hand",
    "öffnen":         "open_hand",
    "loslassen":      "open_hand",

    "entspannen":     "relax",
    "ruhe":           "relax",
    "beruhigen":      "relax",

    "zittern":        "tremor",
    "stabilisieren":  "tremor",
    "ruhig":          "tremor",

    "halten":         "grip",
    "festhalten":     "grip",

    "kneifen":        "pinch",

    "winken":         "wave",

    "stopp":          "stop",
    "aus":            "stop",
    "aufhören":       "stop",
}

# Vosk model paths (download and extract to these locations)
MODEL_PATHS = {
    "en": "models/vosk-model-small-en-us-0.15",
    "de": "models/vosk-model-small-de-0.15",
}

# Serial configuration for ESP32
ESP32_BAUD = 115200


# ============================================================
# SERIAL CONNECTION
# ============================================================
class ESP32Connection:
    """Manages serial communication with the VoiceHaptic ESP32 controller."""

    def __init__(self, port=None, baud=ESP32_BAUD):
        self.port = port
        self.baud = baud
        self.ser = None
        self.lock = threading.Lock()

    def auto_detect(self):
        """Auto-detect ESP32 on serial ports."""
        ports = serial.tools.list_ports.comports()
        esp32_keywords = ["cp210", "ch340", "usb", "serial", "esp"]

        for p in ports:
            desc = f"{p.device} {p.description} {p.manufacturer or ''}".lower()
            if any(kw in desc for kw in esp32_keywords):
                print(f"[Serial] Found candidate: {p.device} ({p.description})")
                return p.device
        return None

    def connect(self):
        """Connect to ESP32."""
        if not self.port:
            self.port = self.auto_detect()

        if not self.port:
            print("[!] No ESP32 found. Use --port to specify.")
            return False

        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            time.sleep(2)  # Wait for ESP32 boot

            # Read boot messages
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    print(f"  [ESP32] {line}")

            print(f"[Serial] Connected to {self.port} @ {self.baud}")
            return True

        except Exception as e:
            print(f"[!] Serial connection failed: {e}")
            return False

    def send_command(self, cmd):
        """Send a command to the ESP32 controller."""
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(f"{cmd}\n".encode())
                    self.ser.flush()
                    print(f"  >>> {cmd}")

                    # Read response
                    time.sleep(0.05)
                    while self.ser.in_waiting:
                        line = self.ser.readline().decode(errors='ignore').strip()
                        if line:
                            print(f"  <<< {line}")
                    return True
                except Exception as e:
                    print(f"[!] Serial send error: {e}")
                    return False
            else:
                print(f"  [SIM] Would send: {cmd}")
                return True

    def close(self):
        if self.ser:
            self.ser.close()


# ============================================================
# KEYWORD MATCHER
# ============================================================
class CommandMatcher:
    """Matches recognized speech to preset commands using fuzzy matching."""

    def __init__(self, command_map):
        self.command_map = command_map
        # Pre-sort by phrase length (longer = more specific = higher priority)
        self.sorted_phrases = sorted(
            command_map.keys(),
            key=len,
            reverse=True
        )

    def match(self, text):
        """
        Find the best matching command for recognized text.
        Returns (matched_phrase, firmware_command) or (None, None).
        """
        text_lower = text.lower().strip()

        # Exact substring match (longest match wins)
        for phrase in self.sorted_phrases:
            if phrase in text_lower:
                return phrase, self.command_map[phrase]

        # Fuzzy match: check if words overlap significantly
        text_words = set(text_lower.split())
        best_match = None
        best_score = 0

        for phrase in self.sorted_phrases:
            phrase_words = set(phrase.split())
            overlap = len(text_words & phrase_words)
            score = overlap / max(len(phrase_words), 1)

            if score > best_score and score >= 0.5:
                best_score = score
                best_match = phrase

        if best_match:
            return best_match, self.command_map[best_match]

        return None, None


# ============================================================
# VOICE COMMAND LISTENER
# ============================================================
class VoiceCommandListener:
    """
    Offline voice command recognition using Vosk.

    Flow:
      1. Continuously transcribe audio
      2. Listen for wake word ("operator")
      3. Capture the command that follows
      4. Match to preset command dictionary
      5. Send to ESP32 via serial
    """

    def __init__(self, esp32, model_path, language="en"):
        self.esp32 = esp32
        self.matcher = CommandMatcher(COMMAND_MAP)
        self.language = language

        # State machine
        self.state = "idle"  # idle -> triggered -> listening -> processing
        self.command_buffer = []
        self.trigger_time = 0
        self.command_timeout = 3.0  # seconds to wait for command after wake word

        # Audio queue
        self.audio_queue = queue.Queue()

        # Initialize Vosk
        if not os.path.exists(model_path):
            print(f"[!] Vosk model not found at: {model_path}")
            print(f"    Download from: https://alphacephei.com/vosk/models")
            sys.exit(1)

        print(f"[Voice] Loading Vosk model: {model_path}")
        self.model = Model(model_path)
        self.recognizer = KaldiRecognizer(self.model, SAMPLE_RATE)
        self.recognizer.SetWords(True)
        print(f"[Voice] Model loaded ({language})")

    def audio_callback(self, indata, frames, time_info, status):
        """Callback for sounddevice audio stream."""
        if status:
            print(f"[Audio] {status}")
        self.audio_queue.put(bytes(indata))

    def process_text(self, text, is_partial=False):
        """Process recognized text through the state machine."""
        text_lower = text.lower().strip()
        if not text_lower:
            return

        prefix = "~" if is_partial else ">"

        if self.state == "idle":
            # Look for wake word
            if WAKE_WORD in text_lower:
                self.state = "triggered"
                self.trigger_time = time.time()
                self.command_buffer = []

                # Extract text after wake word
                idx = text_lower.find(WAKE_WORD)
                after = text_lower[idx + len(WAKE_WORD):].strip().lstrip(',.!?;:- ')

                print(f"\n  [WAKE] Detected '{WAKE_WORD}'!")

                if after:
                    self._try_match(after)
                else:
                    print(f"  [LISTEN] Waiting for command...")
            else:
                if not is_partial:
                    pass  # Suppress idle chatter in production

        elif self.state == "triggered":
            # Accumulate command words
            if not is_partial:
                self.command_buffer.append(text_lower)
                full_text = " ".join(self.command_buffer)
                self._try_match(full_text)

            # Check timeout
            if time.time() - self.trigger_time > self.command_timeout:
                if self.command_buffer:
                    full_text = " ".join(self.command_buffer)
                    self._try_match(full_text, force=True)
                else:
                    print("  [TIMEOUT] No command detected")
                self.state = "idle"

    def _try_match(self, text, force=False):
        """Try to match text to a command."""
        phrase, command = self.matcher.match(text)

        if command:
            print(f"  [MATCH] '{phrase}' → {command}")
            self.esp32.send_command(command)
            self.state = "idle"
            self.command_buffer = []
        elif force:
            print(f"  [NO MATCH] Could not match: '{text}'")
            self.state = "idle"
            self.command_buffer = []

    def run(self):
        """Main recognition loop."""
        print(f"\n{'='*50}")
        print(f"  VoiceHaptic — Listening")
        print(f"  Wake word: '{WAKE_WORD}'")
        print(f"  Language: {self.language}")
        print(f"  Say '{WAKE_WORD}, <command>' to activate")
        print(f"{'='*50}\n")

        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_SIZE,
            dtype='int16',
            channels=CHANNELS,
            callback=self.audio_callback
        ):
            while True:
                data = self.audio_queue.get()

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")
                    if text:
                        self.process_text(text, is_partial=False)
                else:
                    partial = json.loads(self.recognizer.PartialResult())
                    text = partial.get("partial", "")
                    if text:
                        self.process_text(text, is_partial=True)


# ============================================================
# ALTERNATIVE: Edge Impulse TinyML on ESP32-S3
# ============================================================
class EdgeImpulseListener:
    """
    For production deployment, voice recognition runs directly on the
    ESP32-S3 using Edge Impulse's keyword spotting model.

    This class provides the training data collection and model
    deployment pipeline.

    Training workflow:
      1. Record samples of each command (50+ per command)
      2. Upload to Edge Impulse Studio
      3. Train keyword spotting model (MFCC + CNN)
      4. Deploy as Arduino library
      5. Flash to ESP32-S3

    This eliminates the need for the Python bridge entirely —
    the ESP32-S3 handles voice recognition + haptic control in one chip.
    """

    TRAINING_COMMANDS = [
        "operator",      # Wake word
        "close_hand",
        "open_hand",
        "relax",
        "tremor",
        "grip",
        "pinch",
        "wave",
        "stop",
        "_noise",        # Background noise class
        "_unknown",      # Unknown speech class
    ]

    @staticmethod
    def collect_training_data(output_dir="training_data", duration=1.5):
        """Record training samples for Edge Impulse."""
        os.makedirs(output_dir, exist_ok=True)

        print("=== Edge Impulse Training Data Collection ===")
        print(f"Recording {duration}s samples at {SAMPLE_RATE}Hz")
        print()

        for command in EdgeImpulseListener.TRAINING_COMMANDS:
            cmd_dir = os.path.join(output_dir, command)
            os.makedirs(cmd_dir, exist_ok=True)

            print(f"\nCommand: '{command}'")
            print(f"Say the command when prompted. Press Enter to start, 'q' to skip.")

            sample_count = 0
            while True:
                user_input = input(f"  Sample {sample_count + 1} (Enter/q): ").strip()
                if user_input.lower() == 'q':
                    break

                print(f"  Recording in 1s...", end='', flush=True)
                time.sleep(1)
                print(f" GO!", flush=True)

                # Record
                recording = sd.rec(
                    int(duration * SAMPLE_RATE),
                    samplerate=SAMPLE_RATE,
                    channels=1,
                    dtype='int16'
                )
                sd.wait()

                # Save as WAV
                import wave
                filename = os.path.join(cmd_dir, f"{command}_{sample_count:03d}.wav")
                with wave.open(filename, 'w') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(recording.tobytes())

                sample_count += 1
                print(f"  Saved: {filename}")

            print(f"  Collected {sample_count} samples for '{command}'")


# ============================================================
# MAIN
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="VoiceHaptic: Offline voice-controlled vibrotactile therapy"
    )
    parser.add_argument("--port", help="ESP32 serial port (auto-detect if omitted)")
    parser.add_argument("--lang", default="en", choices=["en", "de"],
                        help="Voice recognition language (default: en)")
    parser.add_argument("--model", help="Path to Vosk model directory")
    parser.add_argument("--sim", action="store_true",
                        help="Simulation mode (no serial connection)")
    parser.add_argument("--collect", action="store_true",
                        help="Collect Edge Impulse training data instead")

    args = parser.parse_args()

    # Training data collection mode
    if args.collect:
        EdgeImpulseListener.collect_training_data()
        return

    # Check dependencies
    if not VOSK_AVAILABLE:
        print("[FATAL] Vosk is required. Install: pip install vosk")
        sys.exit(1)
    if not SD_AVAILABLE:
        print("[FATAL] sounddevice is required. Install: pip install sounddevice")
        sys.exit(1)

    # Model path
    model_path = args.model or MODEL_PATHS.get(args.lang)
    if not model_path:
        print(f"[!] No model path for language '{args.lang}'")
        sys.exit(1)

    # Connect to ESP32
    esp32 = ESP32Connection(port=args.port)
    if not args.sim:
        if not esp32.connect():
            print("[WARN] Running in simulation mode (no ESP32)")

    # Start voice listener
    try:
        listener = VoiceCommandListener(esp32, model_path, args.lang)
        listener.run()
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
    finally:
        esp32.close()


if __name__ == "__main__":
    main()
