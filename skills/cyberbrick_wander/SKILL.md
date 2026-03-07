---
name: "cyberbrick-wander"
description: "Starts the 'Hyperactive Kid' random wander mode. The tank will move erratically, explore, wiggle, and act playfully until stopped (Ctrl+C). Invoke when user wants the tank to roam freely."
---

# CyberBrick Wander

This skill enables the "Hyperactive Kid" personality for CyberBrick devices.

## Usage

- **Start Wander**: `python3 cyberbrick_wander.py start`
  - Starts the "Hyperactive Kid" random wander mode.
  - Creates a lock file to maintain the loop.
  - The tank will move erratically, explore, wiggle, and act playfully.

- **Stop Wander**: `python3 cyberbrick_wander.py stop`
  - Safely stops the wandering process by removing the lock file.
  - Ensures motors are halted.
  - Invoke this command when the user wants to stop the wandering behavior.

## Personality Features

- **Restless**: Short pauses, quick movements.
- **Playful**: Dances, wiggles, and shakes head.
- **Unpredictable**: Randomly switches between exploring and performing tricks.
