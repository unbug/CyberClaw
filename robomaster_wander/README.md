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
- `assets/audio/minionish_goblins_wav`
- `assets/audio/minionish_goblins_slow_wav`
- `assets/audio/minionish_robot_voice_pack_wav`
- `assets/audio/minionish_voiceover_fighter_wav`

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

### System Design (Complete)

This project supports two runtime controllers:

- BT mode (default): `robomaster_wander/wander_bt.py`
- Persona mode (recommended): `robomaster_wander/persona_tree.py` + 3-track executor `robomaster_wander/persona_tracks.py`

Both are driven by the same system loop in `robomaster_wander/robomaster_wander.py` and prioritize safety (ToF / visual obstacle risk).

#### Runtime Loop (System Layer)

The `SlamPatrol` loop runs at ~20Hz (sleep 0.05s) and does:

- Read sensor + telemetry snapshot: `pose(x,y,yaw)`, ToF `dist`, gimbal yaw `gyaw`, battery %
- Update the occupancy/grid map: `GridMapper.update(...)`
- Build a Context object and tick the chosen controller:
  - BT: `WanderCtx` -> `root.tick(ctx, bb)`
  - Persona: `PersonaCtx` -> `PersonaController.tick(ctx)`

Entry points:

- BT mode: `SlamPatrol.run()`
- Persona mode: `SlamPatrol.run_persona()`

#### BT Mode (wander_bt.py)

BT mode is a classical Condition/Action behavior tree designed as a compact “patrol + obstacle avoidance” controller.

Key concepts:

- Telemetry health gate: `telemetry_ok`
- Danger detection: `danger` (ToF threshold + visual obstacle checks)
- Turn decision: `ScanChooseTurn` measures multiple headings and picks the best
- Turn execution: `TurnToTarget`
- Motion primitives: `TimedDrive`, `Wiggle`, `LookAround`

Use BT mode when you want a simpler, deterministic-ish patrol behavior without the richer persona layer.

#### Persona Mode (persona_tree.py)

Persona mode is implemented as a deterministic per-tick decision pipeline (think “behavior tree unrolled into explicit stages”). Priority order is fixed and safety always wins.

Stage 1) Affect, needs, expression

- `update_affect(ctx, bb)` computes:
  - perception flags (`person_seen`, `last_person_t`)
  - internal state (`mood`, `energy`)
  - needs (`need_boredom/curiosity/social/play`)
  - base category biases (used later by macro selection)
- `apply_expression(ctx, bb)` maps mood -> LED color (ambient “face”)
- `AutoOptimizer.tick(ctx, bb)` can auto-tune target rates (overlay cadence, avoidance rate, etc.)

Files:

- `robomaster_wander/persona_runtime.py`
- `robomaster_wander/persona_optimizer.py`

Stage 2) Social + show window (intent forcing)

`_maybe_social_and_trick(ctx)` applies short-lived intent overrides:

- When a person is seen (or recently seen): force `look/social` on head + locomotion + overlay
- Periodically inject “voice” overlay macros (e.g. `voice_hi`, `voice_follow`, ...)
- When play-need is high and it’s safe, enter a “show window” that can trigger combo routines

File: `robomaster_wander/persona_tree.py`

Stage 3) Safety & obstacle handling (hard priority)

This stage can fully suppress locomotion or override it with backoff/avoid/unstick.

- `stuck_cooldown_until`: temporary stop where only head/overlay keep running
- `_avoid(ctx)`: multi-phase avoidance sequence (back -> turn -> forward) that can escalate to unstick
- `_safety_backoff(ctx)`: immediate short backoff when ToF is below stop threshold
- `_safety(ctx)`: hard stop when ToF or estimated forward visual obstacle is below threshold

File: `robomaster_wander/persona_tree.py`

Stage 4) Normal execution (three parallel tracks) + injectors

When safe, Persona ticks three tracks in parallel:

- locomotion: chassis movement
- head: gimbal movement
- overlay: audio / LED / utterances / performance (should not block locomotion)

Additionally, Persona injects extra behaviors:

- `_maybe_audio_idle(ctx)`: if quiet for too long, force a short “sync audio” overlay
- `_maybe_puppy_fx(ctx)`: match audio tags + target duration to recent motion and current mood
- `_maybe_sync_random_sound(ctx)`: if a “random” macro just ran, sync audio length to that macro
- `_watchdog_no_progress(ctx)`: if pose stagnates too long, call `_unstick()` and force locomotion toward “adventure”
- `_maybe_leave_area(ctx)`: if staying too long in a wide-open region, force leaving (reduces local loops)

File: `robomaster_wander/persona_tree.py`

#### Motion System (Macro + Step)

The smallest selectable unit is a `Macro` (a short “script” composed of `Step`s):

- `Macro`: name + ordered steps + tags + weight + cooldown + allow_fire
- `Step`: (kind, args) where kind is one of: `drive`, `spin`, `gimbal_*`, `led`, `audio_*`, ...

Files:

- `robomaster_wander/persona_types.py`
- `robomaster_wander/persona_behaviors.py` (the step executor is `MacroPlayer`)

#### Three-Track Executor (TrackRunner)

Tracks are a strict separation-of-concerns design:

- Locomotion only allows chassis kinds (`drive/spin/cruise/unstick/stop/...`)
- Head only allows gimbal kinds (`gimbal_to/gimbal_sweep/gimbal_center/...`)
- Overlay only allows “performance kinds” (`led/utter/sound/audio/...`)

Each track:

- filters eligible macros via `required_tags`, `forbidden_tags`, and `allowed_kinds`
- uses `min_gap_s` and `overlay_probability` to shape cadence
- supports temporary forcing:
  - `force_cat:<track>`: force a category for N uses
  - `force_macro:<track>`: force a specific macro for N uses

File: `robomaster_wander/persona_tracks.py`

#### Macro Selection (Categories + weights + cooldown + recency)

Macro selection happens inside `pick_macro(macros, bb, mood)`:

1) Partition all macros into categories based on tags: `adventure/explore/look/social/show/idle/...`
2) Derive category weights from mood/energy, with locomotion-specific boosts:
   - locomotion strongly boosts `adventure/explore/environment/movement`
   - locomotion suppresses `idle/random/look/social/talk/...`
3) Apply constraints:
   - cooldown (`cd:<macro>`)
   - recent macro down-weighting (`recent_macros:<track>`)
   - safety constraints (e.g. suppress fire when person seen or too close)
   - path validity for `audio` steps (drop weight if file missing)
4) Pick one macro via weighted sampling and start it on the track

File: `robomaster_wander/persona_behaviors.py`

#### Audio System (Catalog + selection + playback)

Catalog:

- `robomaster_wander/audio_catalog.py` loads wav clips, reads `_durations.json`, infers tags, and exposes `pick_clip(...)`.
- Default library directories (all under `assets/audio/`):
  - `oga_cc0_creature_sfx_wav`
  - `oga_cc0_creature_sfx_2_wav`
  - `minionish_goblins_wav`
  - `minionish_goblins_slow_wav`
  - `minionish_robot_voice_pack_wav`
  - `minionish_voiceover_fighter_wav`

Playback steps (executed by `MacroPlayer` in `persona_behaviors.py`):

- `audio_pick(tags, target_s)`
  - filters clips by tags (falls back if none match)
  - avoids recent/bad clips
  - prefers durations closest to `target_s`
  - rewrites itself into `audio(path, dur)`
- `audio(path, dur)`
  - resolves relative path
  - calls `Robot.play_audio(path)`
  - updates `audio_recent` to reduce immediate repetition
- `audio_cycle(prefix)`
  - builds a pool of all clips under `prefix`
  - round-robins through the pool, shuffling between full passes
  - this is used to guarantee coverage when “every file must be used”

#### Combo Routines (Cross-Track Orchestration)

A combo is a coordinated 3-track routine:

- locomotion macro: `combo_<style>_loco`
- head macro: `combo_<style>_head`
- overlay macro: `combo_<style>_overlay`

Triggering is done by writing `force_macro:*` keys for all three tracks with a shared time window.

There are two combo families:

- Base persona combos (curious/prank/guard/sleepy/stomp/celebrate): defined in `persona_micro.py` and triggered by `_maybe_trigger_combo(...)`.
- Minion combos (goblin prank / goblin slow / robot order / announcer): defined in `persona_micro.py` and triggered by `_maybe_trigger_minion_show(...)` and `_maybe_minion_background(...)`.

Files:

- `robomaster_wander/persona_micro.py`
- `robomaster_wander/persona_tree.py`
