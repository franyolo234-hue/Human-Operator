/**
 * VoiceHaptic — Vibrotactile Wearable Controller
 * ================================================
 * Firmware for ESP32-S3 based vibrotactile therapy device.
 *
 * This replaces the EMS-based Human Operator approach with safe,
 * non-invasive vibrotactile stimulation for elderly tremor patients.
 *
 * Hardware:
 *   - ESP32-S3 DevKitC-1 (N16R8 recommended)
 *   - INMP441 I2S MEMS Microphone
 *   - 8x DRV2605L Haptic Drivers (via TCA9548A I2C Mux)
 *   - 8x LRA Vibrotactile Actuators (coin-type, ~155Hz resonance)
 *   - 3.7V 1200mAh LiPo + TP4056 charger
 *   - WS2812B Status LED
 *   - Tactile button (emergency stop)
 *
 * Voice Recognition:
 *   - Edge Impulse TinyML keyword spotting (no cloud, no LLM)
 *   - Wake word: "operator"
 *   - Commands: close_hand, open_hand, relax, tremor, grip, pinch, wave, stop
 *
 * Authors: Built on Human Operator (MIT Hard Mode 2026)
 * License: MIT
 */

#include <Wire.h>
#include <driver/i2s.h>
#include <Adafruit_DRV2605.h>

// ============================================================
// PIN DEFINITIONS
// ============================================================
// I2C Bus (for DRV2605L drivers via TCA9548A)
#define SDA_PIN          8
#define SCL_PIN          9

// I2S Microphone (INMP441)
#define I2S_WS           5   // Word Select (LRCL)
#define I2S_SD           6   // Serial Data (DOUT)
#define I2S_SCK          7   // Serial Clock (BCLK)
#define I2S_PORT         I2S_NUM_0

// Control
#define ESTOP_PIN        4   // Emergency stop (active LOW, internal pullup)
#define STATUS_LED_PIN   48  // WS2812B onboard (ESP32-S3 DevKitC)
#define BATTERY_ADC_PIN  1   // Battery voltage divider

// TCA9548A I2C Multiplexer
#define MUX_ADDR         0x70

// ============================================================
// ACTUATOR CHANNEL MAP
// ============================================================
// Each channel on the TCA9548A maps to one DRV2605L + LRA actuator
// Anatomical placement for therapeutic vibrotactile stimulation:
enum ActuatorChannel {
  CH_WRIST_VOLAR    = 0,  // Volar (palmar) wrist - proprioceptive input
  CH_WRIST_DORSAL   = 1,  // Dorsal wrist - stretch receptor activation
  CH_THUMB          = 2,  // Thenar eminence (thumb base)
  CH_INDEX          = 3,  // Dorsal index finger (2nd metacarpal)
  CH_MIDDLE         = 4,  // Dorsal middle finger (3rd metacarpal)
  CH_RING           = 5,  // Dorsal ring finger (4th metacarpal)
  CH_PINKY          = 6,  // Dorsal pinky (5th metacarpal)
  CH_FOREARM        = 7,  // Proximal forearm (extensor group)
  NUM_CHANNELS      = 8
};

// Human-readable names for serial debug
const char* CHANNEL_NAMES[] = {
  "wrist_volar", "wrist_dorsal", "thumb", "index",
  "middle", "ring", "pinky", "forearm"
};

// ============================================================
// VIBRATION PATTERN DEFINITIONS
// ============================================================
// Based on clinical literature:
//   - Encora X1: tremor-frequency matched vibration (4-12Hz fundamental)
//   - VILIM: 8-18Hz rhythmic vibration
//   - Proprioceptive: 70-100Hz for muscle spindle activation
//   - Cutaneous: 150-300Hz for Pacinian corpuscle (LRA sweet spot)

// Pattern structure: array of {channel_mask, effect_id, amplitude, duration_ms}
struct VibrationStep {
  uint8_t  channel_mask;   // Bitmask of which channels to activate
  uint8_t  drv_effect;     // DRV2605L effect library ID (1-123) or 0 for raw
  uint8_t  amplitude;      // 0-127 for raw mode
  uint16_t duration_ms;    // How long this step runs
  uint16_t pause_ms;       // Pause after this step
};

// DRV2605L effect IDs used (from TI Effect Library):
//   1  = Strong Click (100%)
//   4  = Sharp Click (60%)
//   10 = Double Click (100%)
//   14 = Strong Buzz (100%)
//   16 = Alert (750ms)
//   47 = Buzz 1 (100%)
//   52 = Pulsing Strong 1
//   58 = Transition Ramp Down Long Smooth 1
//   64 = Transition Ramp Up Short Sharp 1
//   118 = Smooth Hum 5 (lowest)

// ---- CLOSE HAND Pattern ----
// Sequential finger curl guidance via proprioceptive vibration
// Clinical basis: Guided motor intention through vibrotactile cueing
const VibrationStep PATTERN_CLOSE_HAND[] = {
  // Prepare: wrist activation for proprioceptive priming
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 80, 300, 100},
  // Sequential finger activation: thumb -> index -> middle -> ring -> pinky
  {(1 << CH_THUMB),   14, 0, 400, 50},
  {(1 << CH_INDEX),   14, 0, 400, 50},
  {(1 << CH_MIDDLE),  14, 0, 400, 50},
  {(1 << CH_RING),    14, 0, 400, 50},
  {(1 << CH_PINKY),   14, 0, 400, 50},
  // All fingers sustained buzz for grip confirmation
  {0b01111100, 47, 0, 600, 0},
};
const int PATTERN_CLOSE_HAND_LEN = sizeof(PATTERN_CLOSE_HAND) / sizeof(VibrationStep);

// ---- OPEN HAND Pattern ----
// Reverse sequential: guides finger extension
const VibrationStep PATTERN_OPEN_HAND[] = {
  // All fingers brief buzz to signal start
  {0b01111100, 4, 0, 200, 100},
  // Sequential release: pinky -> ring -> middle -> index -> thumb
  {(1 << CH_PINKY),   58, 0, 350, 50},
  {(1 << CH_RING),    58, 0, 350, 50},
  {(1 << CH_MIDDLE),  58, 0, 350, 50},
  {(1 << CH_INDEX),   58, 0, 350, 50},
  {(1 << CH_THUMB),   58, 0, 350, 50},
  // Wrist gentle release signal
  {(1 << CH_WRIST_DORSAL), 0, 40, 400, 0},
};
const int PATTERN_OPEN_HAND_LEN = sizeof(PATTERN_OPEN_HAND) / sizeof(VibrationStep);

// ---- RELAX Pattern ----
// Low-frequency calming vibration (8-15Hz modulated)
// Clinical basis: Parasympathetic activation, muscle tension reduction
const VibrationStep PATTERN_RELAX[] = {
  // Slow, rhythmic wave across all actuators
  {0xFF, 0, 50, 500, 500},  // 1Hz cycle: 500ms on, 500ms off
  {0xFF, 0, 55, 500, 500},
  {0xFF, 0, 60, 500, 500},
  {0xFF, 0, 55, 500, 500},
  {0xFF, 0, 50, 500, 500},
  {0xFF, 0, 45, 600, 600},
  {0xFF, 0, 40, 600, 600},
  {0xFF, 0, 35, 700, 700},
};
const int PATTERN_RELAX_LEN = sizeof(PATTERN_RELAX) / sizeof(VibrationStep);

// ---- TREMOR Pattern ----
// Anti-tremor stimulation: wrist-focused, tremor-frequency matched
// Clinical basis: Encora X1 approach - disrupts tremor oscillation
// Frequency: pulsed at 0.125Hz (low-amp) or continuous at tremor freq
const VibrationStep PATTERN_TREMOR[] = {
  // Phase 1: Proprioceptive reset - bilateral wrist stimulation
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 100, 200, 50},
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 100, 200, 50},
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 100, 200, 50},
  // Phase 2: Sustained therapeutic vibration (continuous mode)
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL) | (1 << CH_FOREARM), 0, 110, 2000, 200},
  // Phase 3: Gradual taper
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 90, 1000, 100},
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 70, 1000, 100},
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 0, 50, 1000, 0},
};
const int PATTERN_TREMOR_LEN = sizeof(PATTERN_TREMOR) / sizeof(VibrationStep);

// ---- GRIP Pattern ----
// Power grip assist: all fingers + wrist simultaneous
const VibrationStep PATTERN_GRIP[] = {
  // Wrist stabilize
  {(1 << CH_WRIST_VOLAR) | (1 << CH_WRIST_DORSAL), 52, 0, 300, 50},
  // All fingers strong simultaneous activation
  {0b01111100, 14, 0, 800, 100},
  // Sustained hold vibration
  {0b01111100 | (1 << CH_WRIST_VOLAR), 0, 90, 1500, 0},
};
const int PATTERN_GRIP_LEN = sizeof(PATTERN_GRIP) / sizeof(VibrationStep);

// ---- PINCH Pattern ----
// Precision pinch: thumb + index only
const VibrationStep PATTERN_PINCH[] = {
  {(1 << CH_THUMB) | (1 << CH_INDEX), 4, 0, 200, 100},
  {(1 << CH_THUMB) | (1 << CH_INDEX), 0, 80, 600, 100},
  {(1 << CH_THUMB) | (1 << CH_INDEX), 0, 60, 400, 0},
};
const int PATTERN_PINCH_LEN = sizeof(PATTERN_PINCH) / sizeof(VibrationStep);

// ---- WAVE Pattern ----
// Wrist flexion/extension guidance
const VibrationStep PATTERN_WAVE[] = {
  // Left wave (volar emphasis)
  {(1 << CH_WRIST_VOLAR), 0, 90, 400, 100},
  // Right wave (dorsal emphasis)
  {(1 << CH_WRIST_DORSAL), 0, 90, 400, 100},
  // Repeat with variation
  {(1 << CH_WRIST_VOLAR) | (1 << CH_FOREARM), 0, 80, 500, 100},
  {(1 << CH_WRIST_DORSAL), 0, 80, 500, 100},
  {(1 << CH_WRIST_VOLAR), 0, 70, 400, 0},
};
const int PATTERN_WAVE_LEN = sizeof(PATTERN_WAVE) / sizeof(VibrationStep);

// ============================================================
// COMMAND REGISTRY
// ============================================================
struct Command {
  const char*           name;
  const VibrationStep*  pattern;
  int                   pattern_len;
  bool                  loop;        // Should this pattern repeat?
  int                   loop_count;  // 0 = infinite (until stop)
};

const Command COMMANDS[] = {
  {"close_hand", PATTERN_CLOSE_HAND, PATTERN_CLOSE_HAND_LEN, false, 1},
  {"open_hand",  PATTERN_OPEN_HAND,  PATTERN_OPEN_HAND_LEN,  false, 1},
  {"relax",      PATTERN_RELAX,      PATTERN_RELAX_LEN,       true, 0},
  {"tremor",     PATTERN_TREMOR,     PATTERN_TREMOR_LEN,      true, 0},
  {"grip",       PATTERN_GRIP,       PATTERN_GRIP_LEN,       false, 1},
  {"pinch",      PATTERN_PINCH,      PATTERN_PINCH_LEN,      false, 1},
  {"wave",       PATTERN_WAVE,       PATTERN_WAVE_LEN,        true, 3},
  {"stop",       NULL,               0,                      false, 0},
};
const int NUM_COMMANDS = sizeof(COMMANDS) / sizeof(Command);

// ============================================================
// GLOBALS
// ============================================================
Adafruit_DRV2605 drv;

volatile bool emergency_stop = false;
volatile bool pattern_running = false;
int current_command_idx = -1;

// Audio buffer for I2S microphone
#define SAMPLE_RATE      16000
#define SAMPLE_BITS      16
#define AUDIO_BUFFER_LEN 512
int16_t audio_buffer[AUDIO_BUFFER_LEN];

// ============================================================
// TCA9548A I2C MULTIPLEXER
// ============================================================
void mux_select(uint8_t channel) {
  if (channel >= 8) return;
  Wire.beginTransmission(MUX_ADDR);
  Wire.write(1 << channel);
  Wire.endTransmission();
}

// ============================================================
// DRV2605L DRIVER FUNCTIONS
// ============================================================
bool drv_init_channel(uint8_t channel) {
  mux_select(channel);
  delay(1);

  if (!drv.begin()) {
    Serial.printf("[!] DRV2605L init FAILED on channel %d (%s)\n",
                  channel, CHANNEL_NAMES[channel]);
    return false;
  }

  // Configure for LRA mode
  drv.setMode(DRV2605_MODE_INTTRIG);  // Internal trigger
  drv.selectLibrary(6);                // LRA library

  // Auto-calibration for LRA resonance tracking
  drv.writeRegister8(0x01, 0x07);  // Mode: auto-calibration
  drv.writeRegister8(0x1A, 0xB6);  // Feedback control: LRA mode, brake factor 4x
  drv.writeRegister8(0x1B, 0x93);  // Control1: startup boost, drive time
  drv.writeRegister8(0x1C, 0xF5);  // Control2: sample time 300us, blanking 25us
  drv.writeRegister8(0x1D, 0x80);  // Control3: LRA open loop, analog input
  drv.writeRegister8(0x01, 0x00);  // Back to internal trigger mode

  Serial.printf("[OK] DRV2605L channel %d (%s) initialized (LRA mode)\n",
                channel, CHANNEL_NAMES[channel]);
  return true;
}

void drv_play_effect(uint8_t channel, uint8_t effect_id) {
  mux_select(channel);
  drv.setWaveform(0, effect_id);
  drv.setWaveform(1, 0);  // End
  drv.go();
}

void drv_set_realtime(uint8_t channel, uint8_t amplitude) {
  mux_select(channel);
  drv.setMode(DRV2605_MODE_REALTIME);
  drv.writeRegister8(0x02, amplitude);  // Real-time playback input
}

void drv_stop(uint8_t channel) {
  mux_select(channel);
  drv.setMode(DRV2605_MODE_INTTRIG);
  drv.writeRegister8(0x02, 0x00);
  drv.stop();
}

void drv_stop_all() {
  for (int i = 0; i < NUM_CHANNELS; i++) {
    drv_stop(i);
  }
}

// ============================================================
// I2S MICROPHONE SETUP
// ============================================================
void i2s_init() {
  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
    .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = 8,
    .dma_buf_len = AUDIO_BUFFER_LEN,
    .use_apll = false,
    .tx_desc_auto_clear = false,
    .fixed_mclk = 0
  };

  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK,
    .ws_io_num = I2S_WS,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD
  };

  i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  i2s_set_pin(I2S_PORT, &pin_config);
  i2s_zero_dma_buffer(I2S_PORT);

  Serial.println("[OK] I2S microphone initialized (16kHz, 16-bit)");
}

// ============================================================
// EMERGENCY STOP ISR
// ============================================================
void IRAM_ATTR estop_isr() {
  emergency_stop = true;
  pattern_running = false;
}

// ============================================================
// PATTERN EXECUTION ENGINE
// ============================================================
void execute_pattern(const Command& cmd) {
  if (cmd.pattern == NULL || cmd.pattern_len == 0) {
    // "stop" command
    drv_stop_all();
    pattern_running = false;
    Serial.println("[CMD] All actuators stopped");
    return;
  }

  pattern_running = true;
  int loops_done = 0;

  Serial.printf("[CMD] Executing: %s (steps=%d, loop=%s)\n",
                cmd.name, cmd.pattern_len,
                cmd.loop ? (cmd.loop_count == 0 ? "infinite" : String(cmd.loop_count).c_str()) : "no");

  do {
    for (int step = 0; step < cmd.pattern_len; step++) {
      // Check for stop conditions
      if (emergency_stop || !pattern_running) {
        drv_stop_all();
        Serial.println("[!] Pattern interrupted");
        return;
      }

      const VibrationStep& vs = cmd.pattern[step];

      // Activate channels specified by bitmask
      for (int ch = 0; ch < NUM_CHANNELS; ch++) {
        if (vs.channel_mask & (1 << ch)) {
          if (vs.drv_effect > 0) {
            // Use DRV2605L effect library
            drv_play_effect(ch, vs.drv_effect);
          } else {
            // Use real-time mode with specified amplitude
            drv_set_realtime(ch, vs.amplitude);
          }
        }
      }

      // Hold for duration
      delay(vs.duration_ms);

      // Stop all channels after this step
      for (int ch = 0; ch < NUM_CHANNELS; ch++) {
        if (vs.channel_mask & (1 << ch)) {
          drv_stop(ch);
        }
      }

      // Pause between steps
      if (vs.pause_ms > 0) {
        delay(vs.pause_ms);
      }
    }

    loops_done++;

    // Check serial for new commands during looping patterns
    if (Serial.available() > 0) {
      String incoming = Serial.readStringUntil('\n');
      incoming.trim();
      if (incoming.equalsIgnoreCase("stop") || incoming.equalsIgnoreCase("x")) {
        drv_stop_all();
        pattern_running = false;
        Serial.println("[CMD] Pattern stopped by serial command");
        return;
      }
    }

  } while (cmd.loop && pattern_running && !emergency_stop &&
           (cmd.loop_count == 0 || loops_done < cmd.loop_count));

  pattern_running = false;
  drv_stop_all();
  Serial.printf("[CMD] Pattern '%s' complete (%d loops)\n", cmd.name, loops_done);
}

// ============================================================
// COMMAND PARSER (Serial interface for testing + voice bridge)
// ============================================================
int find_command(const String& name) {
  for (int i = 0; i < NUM_COMMANDS; i++) {
    if (name.equalsIgnoreCase(COMMANDS[i].name)) {
      return i;
    }
  }
  return -1;
}

void process_command(const String& cmd_str) {
  String cmd = cmd_str;
  cmd.trim();
  cmd.toLowerCase();

  if (cmd.length() == 0) return;

  // Special commands
  if (cmd == "help") {
    Serial.println("=== VoiceHaptic Commands ===");
    for (int i = 0; i < NUM_COMMANDS; i++) {
      Serial.printf("  %-12s  steps=%d  loop=%s\n",
                    COMMANDS[i].name, COMMANDS[i].pattern_len,
                    COMMANDS[i].loop ? "yes" : "no");
    }
    Serial.println("  test         - sweep all channels");
    Serial.println("  status       - show system status");
    Serial.println("  battery      - read battery voltage");
    return;
  }

  if (cmd == "test") {
    Serial.println("[TEST] Sweeping all actuator channels...");
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      if (emergency_stop) break;
      Serial.printf("  Channel %d (%s)...\n", ch, CHANNEL_NAMES[ch]);
      drv_play_effect(ch, 14);  // Strong buzz
      delay(500);
      drv_stop(ch);
      delay(200);
    }
    Serial.println("[TEST] Sweep complete");
    return;
  }

  if (cmd == "status") {
    Serial.println("=== VoiceHaptic Status ===");
    Serial.printf("  Pattern running: %s\n", pattern_running ? "YES" : "no");
    Serial.printf("  Emergency stop:  %s\n", emergency_stop ? "ACTIVE" : "clear");
    Serial.printf("  Current command: %s\n",
                  current_command_idx >= 0 ? COMMANDS[current_command_idx].name : "none");
    float vbat = analogRead(BATTERY_ADC_PIN) * 2.0 * 3.3 / 4095.0;
    Serial.printf("  Battery voltage: %.2fV\n", vbat);
    return;
  }

  if (cmd == "battery") {
    float vbat = analogRead(BATTERY_ADC_PIN) * 2.0 * 3.3 / 4095.0;
    int pct = constrain(map(vbat * 100, 330, 420, 0, 100), 0, 100);
    Serial.printf("Battery: %.2fV (%d%%)\n", vbat, pct);
    return;
  }

  // Reset emergency stop
  if (cmd == "reset") {
    emergency_stop = false;
    pattern_running = false;
    drv_stop_all();
    Serial.println("[OK] Emergency stop cleared, all actuators off");
    return;
  }

  // Find and execute command
  int idx = find_command(cmd);
  if (idx >= 0) {
    current_command_idx = idx;
    execute_pattern(COMMANDS[idx]);
    current_command_idx = -1;
  } else {
    Serial.printf("[!] Unknown command: '%s' (type 'help' for list)\n", cmd.c_str());
  }
}

// ============================================================
// SETUP
// ============================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("╔══════════════════════════════════════════╗");
  Serial.println("║     VoiceHaptic Vibrotactile Controller  ║");
  Serial.println("║     Based on Human Operator (MIT 2026)   ║");
  Serial.println("║     Therapeutic Wearable for Tremor Care  ║");
  Serial.println("╚══════════════════════════════════════════╝");
  Serial.println();

  // Emergency stop button
  pinMode(ESTOP_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(ESTOP_PIN), estop_isr, FALLING);

  // Battery ADC
  analogReadResolution(12);
  pinMode(BATTERY_ADC_PIN, INPUT);

  // I2C for haptic drivers
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000);  // 400kHz fast I2C

  Serial.println("[INIT] Initializing haptic drivers...");
  int init_ok = 0;
  for (int ch = 0; ch < NUM_CHANNELS; ch++) {
    if (drv_init_channel(ch)) {
      init_ok++;
    }
  }
  Serial.printf("[INIT] %d/%d haptic channels ready\n", init_ok, NUM_CHANNELS);

  // I2S Microphone
  i2s_init();

  // Startup confirmation: brief pulse on all actuators
  if (init_ok > 0) {
    for (int ch = 0; ch < NUM_CHANNELS; ch++) {
      drv_play_effect(ch, 4);  // Sharp click
    }
    delay(300);
    drv_stop_all();
  }

  Serial.println();
  Serial.println("[READY] Type 'help' for commands, or speak 'Operator, <command>'");
  Serial.println();
}

// ============================================================
// MAIN LOOP
// ============================================================
void loop() {
  // Check emergency stop
  if (emergency_stop) {
    drv_stop_all();
    // Blink status to indicate E-stop active
    static unsigned long last_blink = 0;
    if (millis() - last_blink > 500) {
      last_blink = millis();
      // Would blink LED here
    }

    // Only allow "reset" command during E-stop
    if (Serial.available() > 0) {
      String cmd = Serial.readStringUntil('\n');
      cmd.trim();
      if (cmd.equalsIgnoreCase("reset")) {
        emergency_stop = false;
        Serial.println("[OK] Emergency stop cleared");
      }
    }
    delay(50);
    return;
  }

  // Process serial commands (from USB or from voice recognition bridge)
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    process_command(cmd);
  }

  // Audio capture for voice recognition would happen here
  // In the MVP, the ESP32-S3 runs Edge Impulse inference
  // and sends recognized commands through the same pipeline
  // See: vibrotactile/software/voice_bridge.py for the Python alternative

  delay(10);  // Prevent tight-loop power waste
}
