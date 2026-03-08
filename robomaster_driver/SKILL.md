---
name: robomaster-driver
description: Universal driver for DJI RoboMaster S1/EP. Control movement, gimbal, LED, blaster, and sensors via SDK.
metadata:
  openclaw:
    emoji: 🎮
    tags: ["robotics", "driver", "cli", "sdk", "robomaster"]
---

# RoboMaster Driver Skill

A universal driver for DJI RoboMaster S1/EP series robots, updated to use the modern `robomaster` SDK for enhanced reliability and feature access.

## Commands

### Move
Controls the chassis movement.
- `python3 robomaster_driver.py move <x> [y] [z]`
  - `x`: Forward/Backward distance (m)
  - `y`: Left/Right distance (m) (Optional)
  - `z`: Rotation angle (deg) (Optional)

#### Move Shortcuts (New!)
Simplified commands for common movements.
- `forward <dist>`: Move forward by `dist` meters.
- `back <dist>`: Move backward by `dist` meters.
- `left <angle>`: Turn left by `angle` degrees.
- `right <angle>`: Turn right by `angle` degrees.
- `turn <angle>`: Turn by `angle` degrees (positive=left, negative=right).
- `uturn`: Perform a 180-degree U-turn.

### Gimbal
Controls the gimbal movement.
- `python3 robomaster_driver.py gimbal <pitch> [yaw]`
  - `pitch`: Up/Down angle (deg)
  - `yaw`: Left/Right angle (deg) (Optional)

### LED (New!)
Controls the robot's LED effects for visual feedback.
- `python3 robomaster_driver.py led [--comp COMP] [-r R] [-g G] [-b B] [--effect EFFECT]`
  - `--comp`: LED component (`all` by default, `top_all`, `bottom_all`, `top_right`, etc.)
  - `-r`, `-g`, `-b`: RGB values (0-255). Default: White (255, 255, 255).
  - `--effect`: `on` (solid), `off`, `flash`, `breath`, `scrolling`.
  - **Example**: `python3 robomaster_driver.py led -r 255 -g 0 -b 0 --effect flash` (Red Flash)

### Sensor
Reads data from onboard sensors.
- `python3 robomaster_driver.py sensor [--dist]`
  - `--dist`: Read the ToF (Time-of-Flight) infrared distance sensor (m).

### Fire
Fires the blaster.
- `python3 robomaster_driver.py fire [type] [count]`
  - `type`: `ir` (infrared/laser, default) or `bead` (water gel)
  - `count`: 
    - For `ir`: Duration in seconds (default 1.0).
    - For `bead`: Number of shots (1-8, default 1).

### Status / Info
Checks robot system information (Battery, SN, Version).
- `python3 robomaster_driver.py info`

## Configuration

- **Connection**: Supports `sta` (Station/Router, default), `ap` (Access Point), and `rndis` (USB).
- **Auto-Discovery**: Automatically finds the robot on the local network via UDP broadcast if no IP is specified.

## Requirements

- **Python 3.6+**
- **RoboMaster SDK**: Included in `../vendor` or install via `pip install robomaster`.
- **OpenCV**: Required for vision-related features (used in Wander skill).
