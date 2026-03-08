# RoboMaster Autonomous Wander Skill

A skill that enables the RoboMaster robot to wander autonomously for a set duration, avoiding obstacles using IR sensors and performing random actions.

## Usage

```bash
python3 robomaster_wander.py --duration <seconds>
```

### Options
- `--duration`: How long to wander in seconds (default: 300s / 5min).
- `--host`: Robot IP address (default: 192.168.1.116).
- `--port`: Robot SDK port (default: 40923).
- `--mock`: Run in simulation mode without hardware.

## Logic
1.  **Sensing**: Continuously checks IR distance sensor (ID 1).
2.  **Navigation**:
    -   If distance < 50cm: Stops, backs up, and turns randomly.
    -   If path clear: Moves forward.
3.  **Action**:
    -   Randomly fires IR laser.
    -   Randomly moves gimbal.
    -   Randomly "wiggles" chassis.
