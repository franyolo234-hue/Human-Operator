#!/usr/bin/env python3
"""
VoiceHaptic — Integration Test Suite
======================================
Tests the full pipeline: voice recognition → command matching → serial → firmware.
Can run in simulation mode (no hardware required).

Usage:
  python -m pytest tests/test_integration.py -v
  python tests/test_integration.py          # standalone
"""

import sys
import os
import json
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock
from io import BytesIO

# Add software directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'software'))

# Mock audio libraries that require hardware
sys.modules['sounddevice'] = MagicMock()
sys.modules['vosk'] = MagicMock()


class TestCommandMatcher(unittest.TestCase):
    """Test the keyword matching engine."""

    def setUp(self):
        from voice_bridge import CommandMatcher, COMMAND_MAP
        self.matcher = CommandMatcher(COMMAND_MAP)

    def test_exact_match_english(self):
        phrase, cmd = self.matcher.match("close hand")
        self.assertEqual(cmd, "close_hand")

    def test_exact_match_german(self):
        phrase, cmd = self.matcher.match("hand schließen")
        self.assertEqual(cmd, "close_hand")

    def test_substring_match(self):
        phrase, cmd = self.matcher.match("please close hand now")
        self.assertEqual(cmd, "close_hand")

    def test_fuzzy_match(self):
        phrase, cmd = self.matcher.match("closing hand")
        # Should fuzzy-match "close" or "close hand"
        self.assertIsNotNone(cmd)

    def test_stop_commands(self):
        for word in ["stop", "off", "halt", "stopp", "aus"]:
            phrase, cmd = self.matcher.match(word)
            self.assertEqual(cmd, "stop", f"'{word}' should map to 'stop'")

    def test_all_patterns_reachable(self):
        """Every firmware command should be reachable by at least one phrase."""
        reachable = set()
        from voice_bridge import COMMAND_MAP
        for phrase, cmd in COMMAND_MAP.items():
            reachable.add(cmd)

        expected = {"close_hand", "open_hand", "relax", "tremor",
                    "grip", "pinch", "wave", "stop"}
        self.assertEqual(reachable, expected)

    def test_no_match_returns_none(self):
        phrase, cmd = self.matcher.match("completely unrelated sentence")
        self.assertIsNone(cmd)

    def test_longer_phrase_priority(self):
        """'close hand' should match before just 'close'."""
        phrase, cmd = self.matcher.match("close hand")
        self.assertEqual(phrase, "close hand")

    def test_german_tremor_commands(self):
        for word in ["zittern", "stabilisieren", "ruhig"]:
            phrase, cmd = self.matcher.match(word)
            self.assertEqual(cmd, "tremor", f"'{word}' should map to 'tremor'")


class TestReceiverAPI(unittest.TestCase):
    """Test the Flask HTTP API."""

    def setUp(self):
        # Patch serial before importing receiver
        with patch('serial.Serial'), \
             patch('serial.tools.list_ports.comports', return_value=[]):
            from receiver import app
            self.app = app
            self.client = app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get('/health')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'ready')
        self.assertIn('available_patterns', data)

    def test_patterns_endpoint(self):
        resp = self.client.get('/patterns')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('close_hand', data)
        self.assertIn('tremor', data)
        self.assertIn('stop', data)

    def test_execute_simple_command(self):
        resp = self.client.post('/execute',
                                json={"command": "close_hand"},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'executed')

    def test_execute_invalid_command(self):
        resp = self.client.post('/execute',
                                json={"command": "nonexistent"},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_execute_timestamped_sequence(self):
        payload = {
            "0.0": [{"type": "VIBRO", "pattern": "close_hand"}],
            "0.5": [{"type": "VIBRO", "pattern": "stop"}]
        }
        resp = self.client.post('/execute',
                                json=payload,
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['status'], 'executed')
        self.assertEqual(data['steps'], 2)

    def test_execute_backward_compat_ems(self):
        """Legacy EMS commands should be translated to vibrotactile."""
        payload = {
            "0.0": [{"type": "EMS", "finger": "thumb"}]
        }
        resp = self.client.post('/execute',
                                json=payload,
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_raw_endpoint(self):
        resp = self.client.post('/raw',
                                json={"channel": 0, "amplitude": 50, "duration_ms": 300},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)

    def test_calibrate_endpoint(self):
        resp = self.client.post('/calibrate')
        self.assertEqual(resp.status_code, 200)


class TestPatternDefinitions(unittest.TestCase):
    """Validate pattern metadata consistency."""

    def setUp(self):
        with patch('serial.Serial'), \
             patch('serial.tools.list_ports.comports', return_value=[]):
            from receiver import PATTERNS
            self.patterns = PATTERNS

    def test_all_patterns_have_required_fields(self):
        required = {"description", "duration_ms", "channels", "clinical_basis"}
        for name, pattern in self.patterns.items():
            for field in required:
                self.assertIn(field, pattern,
                              f"Pattern '{name}' missing field '{field}'")

    def test_stop_pattern_zero_duration(self):
        self.assertEqual(self.patterns["stop"]["duration_ms"], 0)

    def test_tremor_pattern_loops(self):
        self.assertTrue(self.patterns["tremor"].get("loops", False))

    def test_relax_pattern_loops(self):
        self.assertTrue(self.patterns["relax"].get("loops", False))


class TestESP32Connection(unittest.TestCase):
    """Test serial communication layer."""

    def test_simulation_mode(self):
        from voice_bridge import ESP32Connection
        esp = ESP32Connection(port=None)
        # Should not crash without hardware
        result = esp.send_command("test")
        self.assertTrue(result)

    def test_auto_detect_no_ports(self):
        from voice_bridge import ESP32Connection
        with patch('serial.tools.list_ports.comports', return_value=[]):
            esp = ESP32Connection()
            port = esp.auto_detect()
            self.assertIsNone(port)


class TestVoiceStateMachine(unittest.TestCase):
    """Test the voice listener state machine logic."""

    def setUp(self):
        self.esp = MagicMock()
        self.esp.send_command = MagicMock(return_value=True)

    @patch('voice_bridge.os.path.exists', return_value=True)
    @patch('voice_bridge.Model')
    @patch('voice_bridge.KaldiRecognizer')
    def test_wake_word_triggers_listening(self, mock_rec, mock_model, mock_exists):
        from voice_bridge import VoiceCommandListener
        listener = VoiceCommandListener(self.esp, "fake_model", "en")

        listener.process_text("operator close hand", is_partial=False)
        self.esp.send_command.assert_called_with("close_hand")

    @patch('voice_bridge.os.path.exists', return_value=True)
    @patch('voice_bridge.Model')
    @patch('voice_bridge.KaldiRecognizer')
    def test_no_wake_word_no_action(self, mock_rec, mock_model, mock_exists):
        from voice_bridge import VoiceCommandListener
        listener = VoiceCommandListener(self.esp, "fake_model", "en")

        listener.process_text("close hand", is_partial=False)
        self.esp.send_command.assert_not_called()

    @patch('voice_bridge.os.path.exists', return_value=True)
    @patch('voice_bridge.Model')
    @patch('voice_bridge.KaldiRecognizer')
    def test_wake_word_then_command(self, mock_rec, mock_model, mock_exists):
        from voice_bridge import VoiceCommandListener
        listener = VoiceCommandListener(self.esp, "fake_model", "en")

        # First: wake word alone
        listener.process_text("operator", is_partial=False)
        self.assertEqual(listener.state, "triggered")

        # Then: command
        listener.process_text("relax", is_partial=False)
        self.esp.send_command.assert_called_with("relax")
        self.assertEqual(listener.state, "idle")


if __name__ == '__main__':
    unittest.main(verbosity=2)
