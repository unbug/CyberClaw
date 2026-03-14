---
name: robomaster-wander
description: Advanced autonomous patrol for RoboMaster EP/S1. Features hybrid motion engine, visual obstacle guard, and LED feedback.
metadata:
  openclaw:
    emoji: 🤖
    tags: ["robotics", "autonomous", "python", "sdk", "robomaster"]
---

# RoboMaster Wander (SDK Version)

This skill turns RoboMaster EP/S1 into a dog-like autonomous wanderer: it explores, avoids obstacles, occasionally plays audio, and uses LEDs for state feedback.

By default it runs the **persona** controller (multi-track behavior: locomotion / head / overlay), built on top of the DJI RoboMaster SDK (IR + Vision).

## Key Features

### 🧠 Intelligent Navigation
- **Persona Locomotion**: Uses arc-like motion for a more natural feel, but prefers straight motion when the path ahead is wide open.
- **Unstick**: When stuck, performs a combined arc-reverse / arc-forward / turn sequence.
- **Scan Sound Rate Limit**: Scanning sound is rate-limited to avoid spamming.

### 👁️ Advanced Perception
- **Visual Obstacle Guard**: Uses onboard camera and edge detection to identify "thin" obstacles (like table legs) that the IR sensor might miss.
- **Anti-Lag System**: Synchronizes sensor readings with motion timestamps to ensure decisions are based on fresh data.
- **Blind-Spot Protection**: Automatically stops if sensor data is lost or stale.

### 💡 Interactive Feedback
- **LED Communication**:
  - 🟢 **Green (Solid/Breath)**: Cruising normally.
  - 🔵 **Blue (Flash)**: Scanning for a path.
  - 🟡 **Yellow (Solid)**: Turning to new direction.
  - 🔴 **Red (Flash)**: Emergency brake / Obstacle detected.
  - 🟣 **Purple (Flash)**: Armor hit detected (Panic mode).
- **Heartbeat Refresh**: Ensures LED state remains consistent even with packet loss.
- **Audio/Voice Overlay**: Plays system sounds and custom wav (e.g. the dog SFX pack), and emits a short “bark/yelp” style cue during unstick.

### 🛡️ Robustness
- **Auto-Reconnect**: Automatically detects Wi-Fi disconnection and attempts to reconnect without user intervention.
- **Self-Calibration**: Forces gimbal pitch calibration on startup to prevent sensor misalignment.

## Usage

```bash
# Run persona mode (default)
python3 robomaster_wander/robomaster_wander.py --conn sta

# Run with verbose debug logs (See sensor data & decisions)
python3 robomaster_wander/robomaster_wander.py --conn sta -v

# Disable blaster usage in persona mode
python3 robomaster_wander/robomaster_wander.py --conn sta --disable-fire

# Run legacy state machine controller
python3 robomaster_wander/robomaster_wander.py --conn sta --legacy

# Run minimal behavior tree controller
python3 robomaster_wander/robomaster_wander.py --conn sta --bt

# Stop the robot immediately
python3 robomaster_wander/robomaster_wander.py --stop --conn sta

# Upload and play a wav file (mono 48kHz). If no path, plays a generated beep.
python3 robomaster_wander/robomaster_wander.py --audio-test
```

### Arguments
- `--conn`: Connection type (`sta` by default, `ap`, `rndis`).
- `-v`, `--verbose`: Enable detailed SDK and logic logs.
- `--stop`: Send a stop command to a running instance.
- `--enable-fire` / `--disable-fire`: Enable/disable blaster usage in persona mode.
- `--legacy`: Run the legacy controller.
- `--bt`: Run the minimal behavior tree controller.
- `--persona`: Run persona controller (default).
- `--audio-test [path]`: Upload and play a wav file; if no path, plays a generated beep.
- `--viz`: Enable matplotlib visualization.
- `--camera-stream` / `--no-camera-stream`: Force enable/disable camera stream.

## Audio Assets

- Custom audio uses RoboMaster `play_audio` (uploads to the robot then plays).
- Format requirements: mono / 48kHz / wav
- Default dog SFX pack directory: `robomaster_wander/assets/audio/oga_cc0_creature_sfx_wav`
  - Refresh / generate via: `python3 robomaster_wander/tools/refresh_audio_assets.py`
