---
name: "cyberbrick-driver"
description: "Universal driver for CyberBrick devices (Mini T Tank, etc.). Invoke when user wants to control movement, fire, turret, or run hardware tests."
---

# CyberBrick Driver

This skill provides comprehensive control for CyberBrick hardware devices, specifically optimized for the Mini T Tank but compatible with other configurations using the standard pinout.

## Usage

The driver script `cyberbrick_driver.py` is located in this directory. You can invoke it using `python3` with various subcommands.

### Commands

#### 1. Movement

- **Forward**: `python3 cyberbrick_driver.py forward <speed> <duration>`
  - `speed`: 0-100 (Default: 0)
  - `duration`: Seconds (Default: 2.0)
  
- **Backward**: `python3 cyberbrick_driver.py backward <speed> <duration>`
  - `speed`: 0-100
  - `duration`: Seconds (Default: 2.0)

- **Turn Left**: `python3 cyberbrick_driver.py left <speed> <duration>`
  - `speed`: 0-100
  - `duration`: Seconds (Default: 2.0)

- **Turn Right**: `python3 cyberbrick_driver.py right <speed> <duration>`
  - `speed`: 0-100
  - `duration`: Seconds (Default: 2.0)

#### 2. Actions

- **Fire**: `python3 cyberbrick_driver.py fire`
  - Triggers the firing mechanism (push-pull action).

- **Turret**: `python3 cyberbrick_driver.py turret <elevation>`
  - `elevation`: Angle 0-180 (90 is neutral).

#### 3. System

- **Test**: `python3 cyberbrick_driver.py test`
  - Runs a full self-test sequence of all hardware functions.

- **Dance**: `python3 cyberbrick_driver.py dance`
  - Performs a dance sequence (Turn Left/Right, Turret Shake, Move Back/Forth).

- **Stop**: `python3 cyberbrick_driver.py stop`
  - Immediately stops all motors.

- **Reset**: `python3 cyberbrick_driver.py reset`
  - Soft-resets the remote controller to manual mode.

## Hardware Mapping (Standard)

- **Left Track (Motor A)**: Pin 2 (1000Hz PWM)
  - Forward: Duty 0
  - Backward: Duty 1023
- **Right Track (Motor B)**: Pin 4, 5 (1000Hz PWM)
  - Forward: Pin 4 High
  - Backward: Pin 5 High
- **Turret (Servo C)**: Pin 3 (50Hz PWM)
- **Fire (Motor D)**: Pin 6, 7 (1000Hz PWM)
