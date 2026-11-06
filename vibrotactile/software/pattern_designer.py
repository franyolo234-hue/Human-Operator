#!/usr/bin/env python3
"""
VoiceHaptic — Vibrotactile Pattern Designer & Calibration Tool
================================================================
Desktop GUI for designing, testing, and calibrating vibrotactile
stimulation patterns for the therapeutic wearable.

This replaces Human Operator's manual_control_app.py (EMS-focused)
with a vibrotactile-specific calibration tool designed for
clinical/research use at Johannesheim.

Features:
  - Visual pattern editor with timeline
  - Real-time actuator testing per channel
  - Patient-specific calibration (perception threshold, comfort level)
  - Pattern library management (save/load therapeutic patterns)
  - Session logging for research data collection
  - Waveform visualization

Usage:
  python pattern_designer.py [--port /dev/ttyUSB0]
"""

import sys
import os
import json
import time
import csv
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QSlider, QLineEdit, QHBoxLayout, QGridLayout, QGroupBox,
    QComboBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QTabWidget, QTextEdit, QCheckBox,
    QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

import serial
import serial.tools.list_ports


# ============================================================
# CONSTANTS
# ============================================================
CHANNEL_NAMES = [
    "Wrist (Volar)", "Wrist (Dorsal)", "Thumb",
    "Index", "Middle", "Ring", "Pinky", "Forearm"
]

CHANNEL_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F"
]

# DRV2605L Effect Library (subset of most useful for therapy)
DRV_EFFECTS = {
    0:   "Raw Amplitude (Manual)",
    1:   "Strong Click (100%)",
    4:   "Sharp Click (60%)",
    10:  "Double Click",
    14:  "Strong Buzz",
    16:  "Alert (750ms)",
    47:  "Buzz 1",
    52:  "Pulsing Strong",
    58:  "Ramp Down Smooth",
    64:  "Ramp Up Sharp",
    118: "Smooth Hum (low)",
}

# Clinical frequency reference ranges
FREQ_RANGES = {
    "Tremor Suppression (4-12 Hz)": (4, 12),
    "Relaxation (8-15 Hz)": (8, 15),
    "Proprioceptive (70-100 Hz)": (70, 100),
    "LRA Resonance (~155 Hz)": (140, 170),
    "Cutaneous (150-300 Hz)": (150, 300),
}


# ============================================================
# DARK THEME STYLESHEET
# ============================================================
DARK_STYLE = """
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    margin-top: 1.5ex;
    font-weight: bold;
    color: #4ECDC4;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #4ECDC4;
}
QPushButton {
    background-color: #2d2d4a;
    color: #e0e0e0;
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3d3d5a;
    border-color: #4ECDC4;
}
QPushButton:pressed {
    background-color: #4ECDC4;
    color: #1a1a2e;
}
QSlider::groove:horizontal {
    border: 1px solid #3a3a5c;
    height: 6px;
    background: #2d2d4a;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #4ECDC4;
    border: none;
    width: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QLineEdit, QComboBox, QSpinBox {
    background-color: #2d2d4a;
    color: #e0e0e0;
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    padding: 4px;
}
QTableWidget {
    background-color: #1a1a2e;
    gridline-color: #3a3a5c;
    selection-background-color: #4ECDC4;
    selection-color: #1a1a2e;
}
QTableWidget::item {
    padding: 4px;
}
QHeaderView::section {
    background-color: #2d2d4a;
    color: #4ECDC4;
    border: 1px solid #3a3a5c;
    padding: 4px;
    font-weight: bold;
}
QTabWidget::pane {
    border: 1px solid #3a3a5c;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #2d2d4a;
    color: #e0e0e0;
    padding: 8px 16px;
    border: 1px solid #3a3a5c;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background-color: #4ECDC4;
    color: #1a1a2e;
}
QProgressBar {
    border: 1px solid #3a3a5c;
    border-radius: 4px;
    text-align: center;
    color: #e0e0e0;
}
QProgressBar::chunk {
    background-color: #4ECDC4;
    border-radius: 3px;
}
QTextEdit {
    background-color: #0d0d1a;
    color: #98D8C8;
    border: 1px solid #3a3a5c;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
}
"""


# ============================================================
# SERIAL MANAGER
# ============================================================
class SerialManager:
    def __init__(self):
        self.ser = None
        self.port = None

    def scan_ports(self):
        ports = serial.tools.list_ports.comports()
        return [f"{p.device} - {p.description}" for p in ports]

    def connect(self, port_string, baud=115200):
        port = port_string.split(" - ")[0].strip()
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(port, baud, timeout=1)
            time.sleep(2)
            self.port = port
            # Drain boot messages
            while self.ser.in_waiting:
                self.ser.readline()
            return True, f"Connected to {port}"
        except Exception as e:
            return False, str(e)

    def send(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.write(f"{cmd}\n".encode())
            self.ser.flush()
            time.sleep(0.05)
            response = []
            while self.ser.in_waiting:
                line = self.ser.readline().decode(errors='ignore').strip()
                if line:
                    response.append(line)
            return response
        return ["[SIM] " + cmd]

    def close(self):
        if self.ser:
            self.ser.close()


# ============================================================
# CALIBRATION TAB
# ============================================================
class CalibrationTab(QWidget):
    """Per-patient actuator calibration."""

    def __init__(self, serial_mgr):
        super().__init__()
        self.serial_mgr = serial_mgr
        self.thresholds = {}  # {channel: {perception: val, comfort: val, max: val}}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Instructions
        info = QLabel(
            "Calibrate each actuator for the patient.\n"
            "Gradually increase amplitude until they report:\n"
            "  1. Perception Threshold — first feeling of vibration\n"
            "  2. Comfort Level — pleasant, clear vibration\n"
            "  3. Maximum Tolerable — upper limit before discomfort"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #98D8C8; padding: 8px;")
        layout.addWidget(info)

        # Channel selector
        ch_layout = QHBoxLayout()
        ch_layout.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        for i, name in enumerate(CHANNEL_NAMES):
            self.channel_combo.addItem(f"{i}: {name}")
        ch_layout.addWidget(self.channel_combo)
        layout.addLayout(ch_layout)

        # Amplitude slider
        amp_group = QGroupBox("Amplitude (0-127)")
        amp_layout = QVBoxLayout()
        self.amp_slider = QSlider(Qt.Horizontal)
        self.amp_slider.setRange(0, 127)
        self.amp_slider.setValue(0)
        self.amp_label = QLabel("0")
        self.amp_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #4ECDC4;")
        self.amp_slider.valueChanged.connect(lambda v: self.amp_label.setText(str(v)))
        amp_layout.addWidget(self.amp_slider)
        amp_layout.addWidget(self.amp_label, alignment=Qt.AlignCenter)
        amp_group.setLayout(amp_layout)
        layout.addWidget(amp_group)

        # Test buttons
        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Vibration (1s)")
        self.test_btn.clicked.connect(self.test_vibration)
        btn_layout.addWidget(self.test_btn)

        self.continuous_btn = QPushButton("Continuous ON")
        self.continuous_btn.setCheckable(True)
        self.continuous_btn.clicked.connect(self.toggle_continuous)
        btn_layout.addWidget(self.continuous_btn)

        self.stop_btn = QPushButton("STOP ALL")
        self.stop_btn.setStyleSheet("background-color: #FF6B6B; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.stop_all)
        btn_layout.addWidget(self.stop_btn)
        layout.addLayout(btn_layout)

        # Record thresholds
        record_group = QGroupBox("Record Thresholds")
        record_layout = QGridLayout()

        self.perception_btn = QPushButton("Mark Perception")
        self.perception_btn.clicked.connect(lambda: self.record_threshold("perception"))
        record_layout.addWidget(self.perception_btn, 0, 0)
        self.perception_val = QLabel("—")
        record_layout.addWidget(self.perception_val, 0, 1)

        self.comfort_btn = QPushButton("Mark Comfort")
        self.comfort_btn.clicked.connect(lambda: self.record_threshold("comfort"))
        record_layout.addWidget(self.comfort_btn, 1, 0)
        self.comfort_val = QLabel("—")
        record_layout.addWidget(self.comfort_val, 1, 1)

        self.max_btn = QPushButton("Mark Maximum")
        self.max_btn.clicked.connect(lambda: self.record_threshold("maximum"))
        record_layout.addWidget(self.max_btn, 2, 0)
        self.max_val = QLabel("—")
        record_layout.addWidget(self.max_val, 2, 1)

        record_group.setLayout(record_layout)
        layout.addWidget(record_group)

        # Save calibration
        save_layout = QHBoxLayout()
        self.patient_id = QLineEdit()
        self.patient_id.setPlaceholderText("Patient ID (e.g., JH-001)")
        save_layout.addWidget(self.patient_id)
        self.save_cal_btn = QPushButton("Save Calibration")
        self.save_cal_btn.clicked.connect(self.save_calibration)
        save_layout.addWidget(self.save_cal_btn)
        layout.addLayout(save_layout)

        layout.addStretch()
        self.setLayout(layout)

    def get_channel(self):
        return self.channel_combo.currentIndex()

    def test_vibration(self):
        ch = self.get_channel()
        amp = self.amp_slider.value()
        # In real hardware: send raw amplitude to specific channel
        # For now, use closest firmware command
        self.serial_mgr.send(f"raw {ch} {amp} 1000")

    def toggle_continuous(self, checked):
        ch = self.get_channel()
        amp = self.amp_slider.value()
        if checked:
            self.serial_mgr.send(f"raw {ch} {amp} 0")  # 0 = indefinite
            self.continuous_btn.setText("Continuous OFF")
            self.continuous_btn.setStyleSheet("background-color: #FF6B6B;")
        else:
            self.serial_mgr.send("stop")
            self.continuous_btn.setText("Continuous ON")
            self.continuous_btn.setStyleSheet("")

    def stop_all(self):
        self.serial_mgr.send("stop")
        self.continuous_btn.setChecked(False)
        self.continuous_btn.setText("Continuous ON")
        self.continuous_btn.setStyleSheet("")

    def record_threshold(self, level):
        ch = self.get_channel()
        val = self.amp_slider.value()

        if ch not in self.thresholds:
            self.thresholds[ch] = {}
        self.thresholds[ch][level] = val

        labels = {
            "perception": self.perception_val,
            "comfort": self.comfort_val,
            "maximum": self.max_val,
        }
        labels[level].setText(f"{val}")
        labels[level].setStyleSheet("font-weight: bold; color: #4ECDC4;")

    def save_calibration(self):
        patient = self.patient_id.text().strip()
        if not patient:
            QMessageBox.warning(self, "Error", "Enter a Patient ID")
            return

        cal_dir = os.path.join(os.path.dirname(__file__), "..", "config", "calibrations")
        os.makedirs(cal_dir, exist_ok=True)

        filename = os.path.join(cal_dir, f"{patient}_{datetime.now():%Y%m%d_%H%M%S}.json")

        data = {
            "patient_id": patient,
            "timestamp": datetime.now().isoformat(),
            "device": "VoiceHaptic v1.0",
            "thresholds": {
                CHANNEL_NAMES[ch]: vals
                for ch, vals in self.thresholds.items()
            }
        }

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        QMessageBox.information(self, "Saved", f"Calibration saved:\n{filename}")


# ============================================================
# SESSION LOGGER TAB
# ============================================================
class SessionLogTab(QWidget):
    """Research session logging for clinical data collection."""

    def __init__(self, serial_mgr):
        super().__init__()
        self.serial_mgr = serial_mgr
        self.session_active = False
        self.log_entries = []
        self.start_time = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Session info
        info_layout = QGridLayout()
        info_layout.addWidget(QLabel("Patient ID:"), 0, 0)
        self.patient_input = QLineEdit()
        self.patient_input.setPlaceholderText("JH-001")
        info_layout.addWidget(self.patient_input, 0, 1)

        info_layout.addWidget(QLabel("Session Notes:"), 1, 0)
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("First calibration session, right hand")
        info_layout.addWidget(self.notes_input, 1, 1)

        layout.addLayout(info_layout)

        # Session controls
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Session")
        self.start_btn.setStyleSheet("background-color: #4ECDC4; color: #1a1a2e;")
        self.start_btn.clicked.connect(self.toggle_session)
        btn_layout.addWidget(self.start_btn)

        self.elapsed_label = QLabel("00:00:00")
        self.elapsed_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #4ECDC4;")
        btn_layout.addWidget(self.elapsed_label)
        layout.addLayout(btn_layout)

        # Log display
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)

        # Event buttons
        event_layout = QHBoxLayout()
        events = [
            ("Tremor Observed", "tremor_observed"),
            ("Patient Feedback+", "feedback_positive"),
            ("Patient Feedback-", "feedback_negative"),
            ("Pattern Changed", "pattern_changed"),
        ]
        for label, event_type in events:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, et=event_type: self.log_event(et))
            event_layout.addWidget(btn)
        layout.addLayout(event_layout)

        # Export
        self.export_btn = QPushButton("Export Session (CSV)")
        self.export_btn.clicked.connect(self.export_session)
        layout.addWidget(self.export_btn)

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_elapsed)

        self.setLayout(layout)

    def toggle_session(self):
        if self.session_active:
            self.session_active = False
            self.timer.stop()
            self.start_btn.setText("Start Session")
            self.start_btn.setStyleSheet("background-color: #4ECDC4; color: #1a1a2e;")
            self.log_event("session_end")
        else:
            self.session_active = True
            self.start_time = time.time()
            self.log_entries = []
            self.timer.start(1000)
            self.start_btn.setText("End Session")
            self.start_btn.setStyleSheet("background-color: #FF6B6B; color: white;")
            self.log_event("session_start")

    def update_elapsed(self):
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self.elapsed_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def log_event(self, event_type, details=""):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(time.time() - self.start_time, 1) if self.start_time else 0,
            "event": event_type,
            "details": details,
        }
        self.log_entries.append(entry)
        self.log_display.append(
            f"[{entry['elapsed_s']:>7.1f}s] {event_type}"
            + (f" — {details}" if details else "")
        )

    def export_session(self):
        patient = self.patient_input.text().strip() or "unknown"
        log_dir = os.path.join(os.path.dirname(__file__), "..", "config", "sessions")
        os.makedirs(log_dir, exist_ok=True)

        filename = os.path.join(log_dir, f"{patient}_{datetime.now():%Y%m%d_%H%M%S}.csv")

        with open(filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "elapsed_s", "event", "details"])
            writer.writeheader()
            writer.writerows(self.log_entries)

        QMessageBox.information(self, "Exported", f"Session log saved:\n{filename}")


# ============================================================
# MAIN WINDOW
# ============================================================
class PatternDesigner(QWidget):
    def __init__(self, port=None):
        super().__init__()
        self.serial_mgr = SerialManager()
        self.setWindowTitle("VoiceHaptic — Pattern Designer & Calibration")
        self.setGeometry(50, 50, 1200, 800)
        self.init_ui()

        if port:
            success, msg = self.serial_mgr.connect(port)
            if success:
                self.status_label.setText(f"Connected: {port}")

    def init_ui(self):
        layout = QVBoxLayout()

        # Header
        header = QLabel("VoiceHaptic — Vibrotactile Pattern Designer")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #4ECDC4; padding: 10px;")
        layout.addWidget(header)

        # Serial connection bar
        serial_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.port_combo.addItems(self.serial_mgr.scan_ports())
        serial_layout.addWidget(self.port_combo)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_ports)
        serial_layout.addWidget(refresh_btn)

        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.connect_device)
        serial_layout.addWidget(connect_btn)

        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet("color: #FF6B6B;")
        serial_layout.addWidget(self.status_label)

        layout.addLayout(serial_layout)

        # Tab widget
        tabs = QTabWidget()
        tabs.addTab(CalibrationTab(self.serial_mgr), "Calibration")
        tabs.addTab(SessionLogTab(self.serial_mgr), "Session Log")
        layout.addWidget(tabs)

        self.setLayout(layout)

    def refresh_ports(self):
        self.port_combo.clear()
        self.port_combo.addItems(self.serial_mgr.scan_ports())

    def connect_device(self):
        port = self.port_combo.currentText()
        if port:
            success, msg = self.serial_mgr.connect(port)
            if success:
                self.status_label.setText(msg)
                self.status_label.setStyleSheet("color: #4ECDC4;")
            else:
                self.status_label.setText(f"Error: {msg}")
                self.status_label.setStyleSheet("color: #FF6B6B;")

    def closeEvent(self, event):
        self.serial_mgr.send("stop")
        self.serial_mgr.close()
        event.accept()


# ============================================================
# MAIN
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="Serial port for ESP32")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLE)

    window = PatternDesigner(port=args.port)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
