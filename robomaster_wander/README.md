## RoboMaster Wander (CyberClaw)

`robomaster_wander` is a persona behavior-tree that keeps a RoboMaster EP (or compatible device) exploring, avoiding obstacles, and “acting” continuously. Behaviors run on three parallel tracks:

- locomotion: chassis movement
- head: gimbal behaviors
- overlay: audio / LED / utterances / performance (should not block locomotion)

### Run

From `skills/CyberClaw`:

```bash
python3 robomaster_wander/robomaster_wander.py --conn sta --persona
```

Common flags:

- `--conn sta|ap`: connection mode
- `--persona`: enable the persona behavior tree

### Stop

Use the stop subcommand (stops the robot and terminates the process):

```bash
python3 robomaster_wander/robomaster_wander.py --stop --conn sta
```

### Behavior & Safety

- Obstacle avoidance & safe stop: if ToF is too close (or visual risk is high), it enters safe-stop / backoff / unstick flows.
- “No-progress” recovery: if pose progress stalls for too long, it triggers `_unstick()` and forces a short exploration push to avoid “only head + audio moving”.
- Explicit stop: the process only treats stop signals as “real stop” when `--stop` has been requested, preventing accidental SIGTERM from interrupting wander.

### Audio Assets

The project uses `Robot.play_audio()` to play local wav files, and uses `audio_pick` to choose clips at runtime by tags and target duration, so audio better fits the current motion/animation duration.

Audio format requirements and generation scripts:

- robomaster_wander/assets/audio/README.md
- License/source record: robomaster_wander/assets/audio/ATTRIBUTION.md

Enabled default audio libraries:

- `assets/audio/oga_cc0_creature_sfx_wav`
- `assets/audio/oga_cc0_creature_sfx_2_wav`

To re-download / transcode audio:

```bash
python3 robomaster_wander/tools/refresh_audio_assets.py
```

### Personality Combo Routines (Audio-Orchestrated)

To make “motion + sound” feel cohesive, there are cross-track combo routines: when a “show” window is reached, it may trigger a coordinated set of locomotion/head/overlay macros so the dog performs a more structured routine with matching audio.

Combo macro naming:

- `combo_<style>_loco`
- `combo_<style>_head`
- `combo_<style>_overlay`

### Debug

Two key log lines are printed during runtime:

- `[stat] ... loco=... head=... overlay=...`: current macro selection and block reason
- `[health] ... active=... step=...`: SDK action ownership and current step per track
