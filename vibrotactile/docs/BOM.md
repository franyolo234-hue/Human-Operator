# VoiceHaptic — Bill of Materials (BOM)

**Project:** Voice-Controlled Vibrotactile Therapy Wearable for Tremor Management
**Target:** MVP Prototype for Johannesheim Senior Care, Freiburg
**Revision:** 1.0 | November 2026

---

## 1. Core Electronics

| # | Component | Part Number / Description | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|--------------------------|-----|-----------------|-------------|--------|
| 1 | ESP32-S3 DevKitC-1 N16R8 | Main MCU — 16MB Flash, 8MB PSRAM, WiFi/BLE 5.0, I2S, I2C | 1 | 12.00 | 12.00 | AliExpress / Mouser |
| 2 | TCA9548A I2C Multiplexer Breakout | 8-channel I2C mux for addressing DRV2605L drivers | 1 | 6.50 | 6.50 | Adafruit (#2717) |
| 3 | DRV2605L Haptic Driver Breakout | Haptic motor driver with 123-effect library, LRA/ERM support | 8 | 7.50 | 60.00 | Adafruit / SparkFun |
| 4 | INMP441 MEMS Microphone Module | I2S digital output, omnidirectional, ESP32-compatible | 1 | 2.50 | 2.50 | AliExpress / Amazon |

**Subtotal Core Electronics: ~EUR 81.00**

## 2. Actuators — Linear Resonant Actuators (LRAs)

| # | Component | Specification | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|---------------|-----|-----------------|-------------|--------|
| 5 | LRA Coin Vibration Motor (10mm) | 10×3.4mm, Z-axis, 175Hz resonant freq, 1.2Vrms | 8 | 3.00 | 24.00 | DigiKey (Jinlong) |
| 6 | LRA Coin Vibration Motor (8mm) — spare | 8×3.0mm for finger positions if 10mm too large | 4 | 2.80 | 11.20 | Precision Microdrives |

**Subtotal Actuators: ~EUR 35.20**

## 3. Power System

| # | Component | Specification | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|---------------|-----|-----------------|-------------|--------|
| 7 | LiPo Battery 3.7V 500mAh | 503035 cell, JST-PH 2.0 connector, PCM protected | 1 | 5.50 | 5.50 | Adafruit (#1578) |
| 8 | TP4056 USB-C Charging Module | Li-ion charger with protection circuit, USB-C input | 1 | 1.50 | 1.50 | AliExpress |
| 9 | 3.3V LDO Voltage Regulator (AMS1117) | 3.3V output for DRV2605L logic supply | 1 | 0.50 | 0.50 | AliExpress |
| 10 | Slide Switch (SPDT) | Power on/off, panel mount | 1 | 0.30 | 0.30 | Any supplier |

**Subtotal Power: ~EUR 7.80**

## 4. Passive Components & Wiring

| # | Component | Specification | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|---------------|-----|-----------------|-------------|--------|
| 11 | Pull-up Resistors 4.7kΩ | I2C bus pull-ups (SDA, SCL) | 2 | 0.05 | 0.10 | Any supplier |
| 12 | Decoupling Capacitors 100nF | Ceramic, per DRV2605L board | 8 | 0.05 | 0.40 | Any supplier |
| 13 | Decoupling Capacitors 10µF | Electrolytic, power rail | 2 | 0.10 | 0.20 | Any supplier |
| 14 | LED (green, 3mm) | Status indicator | 1 | 0.10 | 0.10 | Any supplier |
| 15 | LED (red, 3mm) | Error/low battery indicator | 1 | 0.10 | 0.10 | Any supplier |
| 16 | Current-limiting Resistors 220Ω | For LEDs | 2 | 0.05 | 0.10 | Any supplier |
| 17 | Tactile Push Button (6mm) | Emergency stop / reset | 1 | 0.20 | 0.20 | Any supplier |
| 18 | Ribbon Cable 8-conductor | Flexible, 28AWG, actuator connections | 1m | 2.00 | 2.00 | Amazon |
| 19 | Silicone-insulated Wire 30AWG | Flexible hookup wire, assorted colors | 5m | 3.00 | 3.00 | Amazon |
| 20 | JST-PH 2.0mm Connectors (2-pin) | For actuator quick-disconnect | 10 | 0.30 | 3.00 | AliExpress |
| 21 | Proto / Perf Board (5×7cm) | For mounting DRV2605L breakouts + mux | 1 | 1.50 | 1.50 | Any supplier |
| 22 | Pin Headers (male + female) | 2.54mm, for stackable connections | 2 strips | 0.50 | 1.00 | Any supplier |

**Subtotal Passives & Wiring: ~EUR 11.70**

## 5. Wearable Enclosure & Mounting

| # | Component | Specification | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|---------------|-----|-----------------|-------------|--------|
| 23 | 3D-Printed Forearm Controller Housing | PLA/PETG, custom OpenSCAD model (see design/) | 1 | 3.00 | 3.00 | Self-printed |
| 24 | 3D-Printed Actuator Pods (finger) | TPU flexible, snap-fit pockets for LRAs | 7 | 0.50 | 3.50 | Self-printed |
| 25 | 3D-Printed Wrist Actuator Band | TPU, holds wrist_volar + wrist_dorsal LRAs | 1 | 1.00 | 1.00 | Self-printed |
| 26 | Elastic Velcro Straps (20mm) | Adjustable, medical-grade, hypoallergenic | 3 | 1.50 | 4.50 | Amazon |
| 27 | Neoprene Comfort Padding | 3mm thick, adhesive-backed, cut-to-fit | 1 sheet | 3.00 | 3.00 | Amazon |
| 28 | Medical-Grade Silicone Adhesive Pads | Reusable, skin-safe, for actuator contact | 10 | 0.50 | 5.00 | Medical supply |
| 29 | Compression Glove (fingerless) | Commercial arthritis glove as actuator substrate | 1 | 8.00 | 8.00 | Pharmacy / Amazon |
| 30 | M2 × 6mm Screws + Nuts | Stainless steel, for enclosure assembly | 10 | 0.10 | 1.00 | Any supplier |
| 31 | Rubber Grommets (5mm) | Cable pass-through strain relief | 4 | 0.20 | 0.80 | Any supplier |

**Subtotal Enclosure: ~EUR 29.80**

## 6. Development & Testing Tools (one-time)

| # | Component | Specification | Qty | Unit Cost (EUR) | Total (EUR) | Source |
|---|-----------|---------------|-----|-----------------|-------------|--------|
| 32 | USB-C Cable (data + power) | For ESP32-S3 programming | 1 | 3.00 | 3.00 | Any |
| 33 | Breadboard (830-point) | For prototyping | 1 | 4.00 | 4.00 | Any |
| 34 | Jumper Wire Set (M-M, M-F, F-F) | 40-pin ribbon, 20cm | 3 sets | 2.00 | 6.00 | Any |
| 35 | Digital Multimeter | Basic DMM for debugging | 1 | 15.00 | 15.00 | Any |
| 36 | Soldering Iron + Solder | 60W adjustable temp | 1 | 20.00 | 20.00 | Any (if not owned) |

**Subtotal Dev Tools: ~EUR 48.00**

---

## Cost Summary

| Category | Cost (EUR) |
|----------|-----------|
| Core Electronics | 81.00 |
| Actuators (LRAs) | 35.20 |
| Power System | 7.80 |
| Passives & Wiring | 11.70 |
| Wearable Enclosure | 29.80 |
| **Prototype Total** | **165.50** |
| Development Tools (one-time) | 48.00 |
| **Grand Total (incl. tools)** | **213.50** |

**Note:** Costs are approximate (Nov 2026). Shipping not included. Significant savings possible with bulk orders from AliExpress (prototype total could drop to ~EUR 100). Per-unit cost at scale (~50 units): estimated EUR 85-110.

---

## Wiring Diagram Summary

```
ESP32-S3 DevKitC-1
├── I2C Bus (GPIO 8 = SDA, GPIO 9 = SCL)
│   └── TCA9548A I2C Multiplexer (addr 0x70)
│       ├── CH0 → DRV2605L #0 → LRA: Wrist Volar
│       ├── CH1 → DRV2605L #1 → LRA: Wrist Dorsal
│       ├── CH2 → DRV2605L #2 → LRA: Thumb
│       ├── CH3 → DRV2605L #3 → LRA: Index
│       ├── CH4 → DRV2605L #4 → LRA: Middle
│       ├── CH5 → DRV2605L #5 → LRA: Ring
│       ├── CH6 → DRV2605L #6 → LRA: Pinky
│       └── CH7 → DRV2605L #7 → LRA: Forearm
│
├── I2S Bus (Voice Input)
│   ├── GPIO 5 = I2S_SCK  → INMP441 SCK
│   ├── GPIO 6 = I2S_WS   → INMP441 WS
│   └── GPIO 7 = I2S_SD   → INMP441 SD
│
├── GPIO 4 → Emergency Stop Button (INPUT_PULLUP)
├── GPIO 15 → Status LED (Green)
├── GPIO 16 → Error LED (Red)
├── GPIO 2 → Battery ADC (via voltage divider)
│
└── Power
    ├── LiPo 3.7V → TP4056 → USB-C Charge
    ├── 3.3V LDO → ESP32 VIN
    └── 3.3V → TCA9548A VCC, DRV2605L VCC, INMP441 VCC
```

---

## Assembly Notes

1. **Start with breadboard prototype** — verify each DRV2605L drives its LRA before soldering.
2. **I2C addresses** — all DRV2605L share address 0x5A; the TCA9548A selects which one responds.
3. **LRA orientation** — Z-axis coin LRAs vibrate perpendicular to the skin surface for maximum proprioceptive feedback.
4. **Cable routing** — run ribbon cable from forearm housing along the back of the hand (dorsal side) to minimize interference with grip.
5. **Actuator attachment** — silicone adhesive pads on LRAs, seated inside TPU flexible pods sewn/glued to compression glove.
6. **Battery safety** — TP4056 module handles over-charge/over-discharge protection. Never short LiPo terminals.
