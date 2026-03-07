# CyberBrick Plugin for OpenClaw

**Giving Life to CyberBrick Devices via AI**

This plugin bridges the gap between [OpenClaw](https://github.com/openclaw) AI agents and [CyberBrick](https://cyberbrick.cn) hardware. It empowers any CyberBrick device (Mini T Tank, robotic arms, etc.) with autonomous capabilities, turning static hardware into intelligent, interactive companions.

## Mission

Our goal is to **animate the physical world** through AI. By connecting CyberBrick's versatile hardware ecosystem with OpenClaw's powerful agent framework, we enable:

- 🤖 **Autonomous Behavior**: Devices that explore, react, and make decisions independently.
- 🎭 **Personality Injection**: Programmable "souls" like the "Hyperactive Kid" persona.
- 🔌 **Universal Control**: A unified driver interface for all standard CyberBrick pinout configurations.

## Core Capabilities

This plugin currently provides the following skills:

1.  **Universal Driver (`cyberbrick_driver/cyberbrick_driver.py`)**:
    -   Precise motor and servo control (1000Hz PWM).
    -   Standardized movement (Forward, Backward, Turn).
    -   Action triggers (Fire, Turret elevation).
    -   Full system diagnostics.

2.  **Autonomous Wander (`cyberbrick_wander/cyberbrick_wander.py`)**:
    -   A "Hyperactive Kid" personality engine.
    -   Self-driven exploration with erratic, playful behaviors.
    -   Complex macro actions (Dance, Panic, Celebrate).

## Usage

Skills are registered in `SKILL.md` files within each subdirectory and can be invoked naturally by OpenClaw agents.

### Example Prompts
- "Start wandering around."
- "Perform a dance routine."
- "Run a hardware self-test."
- "Move forward at full speed for 3 seconds."

## Directory Structure

- `cyberbrick_driver/`: Contains the driver skill and low-level hardware abstraction layer.
- `cyberbrick_wander/`: Contains the wander skill and high-level behavioral logic.
- `README.md`: Project documentation.

---
*Powered by OpenClaw & CyberBrick*
