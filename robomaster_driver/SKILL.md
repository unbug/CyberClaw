# RoboMaster Driver Skill

A universal driver for DJI RoboMaster S1/EP series robots using the Text SDK protocol.

## Commands

### Move
Controls the chassis movement.
- `python3 robomaster_driver.py move <x> [y] [z]`
  - `x`: Forward/Backward distance (m)
  - `y`: Left/Right distance (m) (Optional)
  - `z`: Rotation angle (deg) (Optional)

### Gimbal
Controls the gimbal movement.
- `python3 robomaster_driver.py gimbal <pitch> [yaw]`
  - `pitch`: Up/Down angle (deg)
  - `yaw`: Left/Right angle (deg) (Optional)

### Fire
Fires the blaster.
- `python3 robomaster_driver.py fire [type] [count]`
  - `type`: `ir` (infrared/laser, default) or `bead` (water gel)
  - `count`: 
    - For `ir`: Duration in seconds (default 1.0). Fires repeatedly.
    - For `bead`: Number of shots (1-8, default 1).

### Status
Checks robot status (e.g., battery).
- `python3 robomaster_driver.py status`

### Raw Command
Sends a raw SDK text command.
- `python3 robomaster_driver.py raw <command>`
  - Example: `python3 robomaster_driver.py raw "led control comp all r 255 g 0 b 0 effect on"`

## Configuration

- **IP Address**: Default is `192.168.1.116`. You can override it with `--host` argument.
- **Port**: Default is `40923`. Override with `--port`.

## Requirements

- Robot must be in "Direct Connection" or "Router" mode.
- PC must be on the same network.
