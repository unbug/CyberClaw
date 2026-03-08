---
name: robomaster-wander
description: Advanced autonomous patrol for RoboMaster EP/S1. Features hybrid motion engine, visual obstacle guard, and LED feedback.
metadata:
  openclaw:
    emoji: 🤖
    tags: ["robotics", "autonomous", "python", "sdk", "robomaster"]
---

# RoboMaster Autonomous Patrol (SDK Version)

This skill transforms the RoboMaster EP/S1 robot into an advanced autonomous sentry, capable of navigating complex home environments, avoiding obstacles (even those invisible to IR), and interacting via LED feedback.

It leverages the official DJI RoboMaster SDK for robust communication and integrates a multi-sensor fusion approach (IR + Vision).

## Key Features

### 🧠 Intelligent Navigation
- **Hybrid Motion Engine**:
  - **Cruise Mode**: Uses `CHASSIS_LEAD` for stable, tank-like movement.
  - **Efficient Scan**: Uses `FREE` mode for quick head-turning checks. Skips full scans if the front is clear (>1.5m).
  - **Precision Turn**: Executes smooth, controlled chassis rotations (45°/s) to avoid jerkiness.
  - **U-Turn**: Automatically performs a 180° turn when trapped in dead ends.

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
- **Silent Operation**: Only emits sound when actively scanning for a path, remaining quiet during normal patrol.

### 🛡️ Robustness
- **Auto-Reconnect**: Automatically detects Wi-Fi disconnection and attempts to reconnect without user intervention.
- **Self-Calibration**: Forces gimbal pitch calibration on startup to prevent sensor misalignment.

## Usage

```bash
# Run in default mode (Silent, Console Logging)
python3 robomaster_wander.py

# Run with verbose debug logs (See sensor data & decisions)
python3 robomaster_wander.py -v

# Stop the robot immediately
python3 robomaster_wander.py --stop
```

### Arguments
- `--conn`: Connection type (`sta` by default, `ap`, `rndis`).
- `-v`, `--verbose`: Enable detailed SDK and logic logs.
- `--stop`: Send a stop command to a running instance.

## Logic Flow
1. **Initialize**: Connect, calibrate gimbal, start camera stream.
2. **Cruise**: Drive forward at 0.2m/s. Monitor IR distance and Visual edges.
3. **Obstacle Event**:
   - If IR < 0.5m OR Visual Edge Density > 5%:
   - **Emergency Brake** (Red LED).
4. **Scan Decision**:
   - Check front distance. If > 1.5m, resume Cruise immediately (Efficient Scan).
   - If blocked, start **Full Scan** (Blue LED + Sound).
5. **Full Scan**:
   - Turn chassis Left 60°, Right 60°.
   - Record distances at 5 angles.
   - Select **Furthest** direction.
   - If all blocked (< 0.6m), select 180° (Back).
6. **Execute Turn**:
   - Turn chassis to target angle (Yellow LED).
   - Resume Cruise.
