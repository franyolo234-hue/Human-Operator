#!/usr/bin/env python3
"""
VoiceHaptic — HTTP Command Receiver (Flask API)
=================================================
Drop-in replacement for Human Operator's receiver.py.
Translates HTTP API calls to serial commands for the
vibrotactile controller (replacing EMS relay commands).

This maintains API compatibility with the original receiver
while redirecting to vibrotactile patterns instead of EMS.

Endpoints:
  GET  /health    — System status
  POST /execute   — Execute a vibrotactile command or pattern
  POST /raw       — Direct actuator control (channel, amplitude, duration)
  POST /calibrate — Run calibration sequence
  GET  /patterns  — List available patterns

Usage:
  python receiver.py [--port /dev/ttyUSB0] [--http-port 5001]
"""

from flask import Flask, request, jsonify
import json
import os
import time
import serial
import serial.tools.list_ports

app = Flask(__name__)


# ============================================================
# VIBROTACTILE CONTROLLER CONNECTION
# ============================================================
class VibrotactileController:
    """Serial interface to ESP32 vibrotactile controller."""

    def __init__(self, port=None, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.error = None
        self.connected = False

        if port:
            self.connect(port)

    def connect(self, port):
        try:
            self.ser = serial.Serial(port, self.baudrate, timeout=1)
            time.sleep(2)  # ESP32 boot

            # Drain boot messages
            boot_msgs = []
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    boot_msgs.append(line)

            self.connected = True
            self.error = None
            print(f"[OK] Connected to vibrotactile controller: {port}")
            for msg in boot_msgs:
                print(f"  [BOOT] {msg}")

        except Exception as e:
            self.error = str(e)
            self.connected = False
            print(f"[!] Connection failed: {e}")

    def send(self, command):
        """Send a command to the controller and return response lines."""
        if not (self.ser and self.ser.is_open):
            return {"status": "simulated", "command": command}

        try:
            self.ser.write(f"{command}\n".encode())
            self.ser.flush()

            time.sleep(0.1)
            responses = []
            deadline = time.time() + 0.5
            while time.time() < deadline:
                if self.ser.in_waiting:
                    line = self.ser.readline().decode(errors='ignore').strip()
                    if line:
                        responses.append(line)
                        deadline = time.time() + 0.1
                else:
                    time.sleep(0.01)

            print(f"  >>> {command}")
            for r in responses:
                print(f"  <<< {r}")

            return {"status": "sent", "command": command, "response": responses}

        except Exception as e:
            self.error = str(e)
            return {"status": "error", "error": str(e)}

    def close(self):
        if self.ser:
            self.send("stop")
            self.ser.close()


# ============================================================
# AVAILABLE PATTERNS
# ============================================================
PATTERNS = {
    "close_hand": {
        "description": "Sequential finger closure guidance",
        "duration_ms": 2850,
        "channels": ["thumb", "index", "middle", "ring", "pinky"],
        "clinical_basis": "Proprioceptive motor cueing"
    },
    "open_hand": {
        "description": "Sequential finger extension guidance",
        "duration_ms": 2350,
        "channels": ["pinky", "ring", "middle", "index", "thumb"],
        "clinical_basis": "Extension reflex facilitation"
    },
    "relax": {
        "description": "Low-frequency calming vibration (8-15Hz)",
        "duration_ms": 8400,
        "channels": ["all"],
        "clinical_basis": "Parasympathetic activation",
        "loops": True
    },
    "tremor": {
        "description": "Anti-tremor wrist stimulation",
        "duration_ms": 6050,
        "channels": ["wrist_volar", "wrist_dorsal", "forearm"],
        "clinical_basis": "Proprioceptive tremor disruption (Encora X1 approach)",
        "loops": True
    },
    "grip": {
        "description": "Power grip assist",
        "duration_ms": 2750,
        "channels": ["all_fingers", "wrist_volar"],
        "clinical_basis": "Simultaneous motor unit recruitment"
    },
    "pinch": {
        "description": "Precision pinch (thumb + index)",
        "duration_ms": 1400,
        "channels": ["thumb", "index"],
        "clinical_basis": "Fine motor proprioceptive cueing"
    },
    "wave": {
        "description": "Wrist flexion/extension guidance",
        "duration_ms": 2400,
        "channels": ["wrist_volar", "wrist_dorsal", "forearm"],
        "clinical_basis": "Wrist range of motion facilitation",
        "loops": True
    },
    "stop": {
        "description": "Stop all vibration immediately",
        "duration_ms": 0,
        "channels": [],
        "clinical_basis": "Safety"
    }
}


# ============================================================
# AUTO-DETECT
# ============================================================
def find_controller_port():
    ports = serial.tools.list_ports.comports()
    keywords = ["cp210", "ch340", "usb", "serial", "esp", "arduino"]
    for p in ports:
        desc = f"{p.device} {p.description}".lower()
        if any(kw in desc for kw in keywords):
            return p.device
    return None


# ============================================================
# INITIALIZATION
# ============================================================
env_port = os.environ.get("CONTROLLER_PORT")
port = env_port or find_controller_port()
controller = VibrotactileController(port=port)


# ============================================================
# API ENDPOINTS
# ============================================================
@app.route('/health', methods=['GET'])
def health():
    """System health check — compatible with Human Operator's receiver."""
    return jsonify({
        "status": "ready",
        "system": "VoiceHaptic Vibrotactile Controller",
        "hardware_mode": "vibrotactile",
        "controller_port": controller.port or "SIMULATED",
        "controller_connected": controller.connected,
        "controller_error": controller.error,
        "available_patterns": list(PATTERNS.keys()),
        # Backward compatibility fields
        "stim_port": "N/A (vibrotactile mode)",
        "relay_port": controller.port or "SIMULATED",
        "relay_hardware_connected": controller.connected,
    }), 200


@app.route('/execute', methods=['POST'])
def execute():
    """
    Execute a vibrotactile command.

    Accepts two formats:

    1. Simple command (VoiceHaptic native):
       {"command": "close_hand"}

    2. Timestamped sequence (Human Operator compatible):
       {
         "0.0": [{"type": "VIBRO", "pattern": "close_hand"}],
         "2.0": [{"type": "VIBRO", "pattern": "stop"}]
       }
    """
    data = request.json

    if not data:
        return jsonify({"error": "No JSON body"}), 400

    # Format 1: Simple command
    if "command" in data:
        cmd = data["command"]
        if cmd not in PATTERNS and cmd != "test" and cmd != "status":
            return jsonify({"error": f"Unknown command: {cmd}",
                            "available": list(PATTERNS.keys())}), 400

        result = controller.send(cmd)
        return jsonify({
            "status": "executed",
            "command": cmd,
            "pattern_info": PATTERNS.get(cmd, {}),
            "hardware": result
        }), 200

    # Format 2: Timestamped sequence (backward compatible)
    try:
        sorted_keys = sorted(data.keys(), key=lambda x: float(x))
    except (ValueError, TypeError):
        sorted_keys = list(data.keys())

    start_time = time.monotonic()
    results = []

    for timestamp_key in sorted_keys:
        # Wait for the right moment
        try:
            target_offset = float(timestamp_key)
            elapsed = time.monotonic() - start_time
            wait = target_offset - elapsed
            if wait > 0:
                time.sleep(wait)
        except (ValueError, TypeError):
            pass

        commands = data[timestamp_key]
        for cmd in commands:
            cmd_type = cmd.get("type", "VIBRO").upper()

            if cmd_type == "VIBRO":
                pattern = cmd.get("pattern", "stop")
                result = controller.send(pattern)
                results.append(result)

            elif cmd_type == "RAW":
                ch = cmd.get("channel", 0)
                amp = cmd.get("amplitude", 60)
                dur = cmd.get("duration_ms", 500)
                result = controller.send(f"raw {ch} {amp} {dur}")
                results.append(result)

            elif cmd_type in ("RELAY", "EMS"):
                # Backward compatibility: translate EMS commands to vibrotactile
                finger = cmd.get("finger", "x")
                if finger == "x":
                    result = controller.send("stop")
                else:
                    # Map finger relay to vibrotactile channel activation
                    result = controller.send(f"close_hand")
                results.append(result)

    return jsonify({
        "status": "executed",
        "steps": len(results),
        "results": results,
        "hardware_mode": "vibrotactile"
    }), 200


@app.route('/raw', methods=['POST'])
def raw_control():
    """Direct actuator control for calibration and testing."""
    data = request.json
    channel = data.get("channel", 0)
    amplitude = data.get("amplitude", 60)
    duration_ms = data.get("duration_ms", 500)

    result = controller.send(f"raw {channel} {amplitude} {duration_ms}")

    return jsonify({
        "status": "executed",
        "channel": channel,
        "channel_name": CHANNEL_NAMES[channel] if channel < len(CHANNEL_NAMES) else "unknown",
        "amplitude": amplitude,
        "duration_ms": duration_ms,
        "result": result
    }), 200


CHANNEL_NAMES = [
    "wrist_volar", "wrist_dorsal", "thumb", "index",
    "middle", "ring", "pinky", "forearm"
]


@app.route('/patterns', methods=['GET'])
def list_patterns():
    """List all available vibrotactile patterns."""
    return jsonify(PATTERNS), 200


@app.route('/calibrate', methods=['POST'])
def calibrate():
    """Run auto-calibration sequence across all channels."""
    result = controller.send("test")
    return jsonify({
        "status": "calibration_started",
        "result": result
    }), 200


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    http_port = int(os.environ.get("HTTP_PORT", 5001))

    print(f"╔══════════════════════════════════════════╗")
    print(f"║  VoiceHaptic Receiver — HTTP Gateway     ║")
    print(f"╚══════════════════════════════════════════╝")
    print(f"  Controller: {controller.port or 'SIMULATED'}")
    print(f"  HTTP Port:  {http_port}")
    print(f"  Patterns:   {len(PATTERNS)}")
    print()

    app.run(host='0.0.0.0', port=http_port)
