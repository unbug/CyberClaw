import random
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    from .persona_runtime import PersonaCtx, Blackboard, apply_expression, bb_get, choose_utterance, safe_stop
except ImportError:
    from persona_runtime import PersonaCtx, Blackboard, apply_expression, bb_get, choose_utterance, safe_stop
try:
    from .persona_types import Macro, Step
except ImportError:
    from persona_types import Macro, Step
try:
    from .persona_micro import build_micro_library
except ImportError:
    from persona_micro import build_micro_library


class MacroPlayer:
    def __init__(self, macro: Macro):
        self.macro = macro
        self.i = 0
        self.t0: Optional[float] = None
        self.state: Dict[str, Any] = {}

    def reset(self) -> None:
        self.i = 0
        self.t0 = None
        self.state = {}

    def _sdk_action_owner(self, kind: str) -> str:
        return f"{self.macro.name}:{kind}:{self.i}"

    def _sdk_action_try_acquire(self, bb: Blackboard, now: float, kind: str, ttl_s: float) -> bool:
        owner = self._sdk_action_owner(kind)
        cur_owner = str(bb.get("sdk_action_owner", "")) if bb.get("sdk_action_owner") is not None else ""
        until = float(bb.get("sdk_action_until", 0.0))
        if now < until and cur_owner and cur_owner != owner:
            return False
        bb["sdk_action_owner"] = owner
        bb["sdk_action_until"] = now + float(ttl_s)
        self.state["sdk_action_owner"] = owner
        return True

    def _sdk_action_release(self, bb: Blackboard) -> None:
        owner = str(self.state.get("sdk_action_owner", ""))
        if not owner:
            return
        if str(bb.get("sdk_action_owner", "")) == owner:
            bb["sdk_action_owner"] = ""
            bb["sdk_action_until"] = 0.0
        self.state.pop("sdk_action_owner", None)

    def tick(self, ctx: PersonaCtx, bb: Blackboard) -> bool:
        if self.i >= len(self.macro.steps):
            return True
        step = self.macro.steps[self.i]
        ok = self._run_step(ctx, bb, step)
        if ok:
            self.i += 1
            self.t0 = None
            self.state = {}
        return self.i >= len(self.macro.steps)

    def _run_step(self, ctx: PersonaCtx, bb: Blackboard, step: Step) -> bool:
        now = float(ctx.now)
        k = step.kind
        if k == "stop":
            safe_stop(ctx)
            return True
        if k == "sleep":
            if self.t0 is None:
                self.t0 = ctx.now
            dur = float(step.args[0])
            if (ctx.now - self.t0) >= dur:
                self.t0 = None
                return True
            safe_stop(ctx)
            return False
        if k == "drive":
            if self.t0 is None:
                self.t0 = ctx.now
                try:
                    rx, ry, _ = ctx.pose
                except Exception:
                    rx, ry = 0.0, 0.0
                self.state["drive_last_pose"] = (float(rx), float(ry))
                self.state["drive_last_progress_t"] = now
            dur, x, y, z = step.args
            if (ctx.now - self.t0) >= float(dur):
                self.t0 = None
                safe_stop(ctx)
                return True
            try:
                rx, ry, _ = ctx.pose
                last_rx, last_ry = self.state.get("drive_last_pose", (float(rx), float(ry)))
                moved = ((float(rx) - float(last_rx)) ** 2 + (float(ry) - float(last_ry)) ** 2) ** 0.5
                if moved > 0.015:
                    self.state["drive_last_pose"] = (float(rx), float(ry))
                    self.state["drive_last_progress_t"] = now
            except Exception:
                pass

            dist = getattr(ctx, "dist", None)
            try:
                dist_v = float(dist) if dist is not None else None
            except Exception:
                dist_v = None

            x_v = float(x)
            if x_v > 0.05 and dist_v is not None:
                if dist_v < float(bb.get("safety_stop_dist_m", 0.3)) + 0.03:
                    safe_stop(ctx)
                    return True
                if dist_v < float(bb.get("danger_dist_m", 0.55)):
                    safe_stop(ctx)
                    return True

            last_progress_t = float(self.state.get("drive_last_progress_t", now))
            if x_v > 0.10 and (now - last_progress_t) > 0.9:
                bb["stat:stuck_breaks"] = int(bb.get("stat:stuck_breaks", 0)) + 1
                bb["stuck_cooldown_until"] = now + 2.5
                safe_stop(ctx)
                ft0 = float(bb.get("frustration_t0", 0.0))
                if (now - ft0) > 25.0:
                    bb["frustration_t0"] = now
                    bb["frustration_count"] = 0
                bb["frustration_count"] = int(bb.get("frustration_count", 0)) + 1
                last_fx = float(bb.get("last_unstick_sound_t", 0.0))
                if (now - last_fx) > 3.0:
                    person_seen = bool(bb.get("person_seen", False))
                    safe_dist = (dist_v is None) or (dist_v > 1.2)
                    can_fire = bool(bb_get(bb, "enable_fire", False)) and (not person_seen) and safe_dist
                    fire_cd = float(bb.get("last_frustration_fire_t", 0.0))
                    if can_fire and int(bb.get("frustration_count", 0)) >= 3 and (now - fire_cd) > 22.0:
                        bb["force_macro:overlay"] = "frustration_fire"
                        bb["force_macro_until:overlay"] = now + 6.0
                        bb["force_macro_uses:overlay"] = 1
                        bb["last_frustration_fire_t"] = now
                    else:
                        bb["force_macro:overlay"] = "unstick_sound"
                        bb["force_macro_until:overlay"] = now + 4.0
                        bb["force_macro_uses:overlay"] = 1
                    bb["last_unstick_sound_t"] = now
                try:
                    ctx.patrol._unstick()
                except Exception:
                    pass
                return True
            ctx.patrol.chassis.drive_speed(x=float(x), y=float(y), z=float(z))
            return False
        if k == "spin":
            deg, z_speed = step.args
            deg = float(deg)
            z_speed = float(z_speed)
            if z_speed <= 1e-6:
                return True
            dur = abs(deg) / abs(z_speed)
            z = z_speed if deg >= 0 else -z_speed
            if self.t0 is None:
                self.t0 = ctx.now
                try:
                    _, _, ryaw = ctx.pose
                except Exception:
                    ryaw = 0.0
                self.state["spin_last_yaw"] = float(ryaw)
                self.state["spin_last_progress_t"] = now
            if (ctx.now - self.t0) >= dur:
                safe_stop(ctx)
                return True
            try:
                _, _, ryaw = ctx.pose
                last_yaw = float(self.state.get("spin_last_yaw", float(ryaw)))
                dy = abs((float(ryaw) - last_yaw + 3.141592653589793) % (2 * 3.141592653589793) - 3.141592653589793)
                if dy > 0.08:
                    self.state["spin_last_yaw"] = float(ryaw)
                    self.state["spin_last_progress_t"] = now
            except Exception:
                pass

            last_progress_t = float(self.state.get("spin_last_progress_t", now))
            if (now - last_progress_t) > 0.9:
                bb["stat:stuck_breaks"] = int(bb.get("stat:stuck_breaks", 0)) + 1
                bb["stuck_cooldown_until"] = now + 2.5
                safe_stop(ctx)
                ft0 = float(bb.get("frustration_t0", 0.0))
                if (now - ft0) > 25.0:
                    bb["frustration_t0"] = now
                    bb["frustration_count"] = 0
                bb["frustration_count"] = int(bb.get("frustration_count", 0)) + 1
                last_fx = float(bb.get("last_unstick_sound_t", 0.0))
                if (now - last_fx) > 3.0:
                    person_seen = bool(bb.get("person_seen", False))
                    dist = bb.get("dist", None)
                    try:
                        dist_v = float(dist) if dist is not None else None
                    except Exception:
                        dist_v = None
                    safe_dist = (dist_v is None) or (dist_v > 1.2)
                    can_fire = bool(bb_get(bb, "enable_fire", False)) and (not person_seen) and safe_dist
                    fire_cd = float(bb.get("last_frustration_fire_t", 0.0))
                    if can_fire and int(bb.get("frustration_count", 0)) >= 3 and (now - fire_cd) > 22.0:
                        bb["force_macro:overlay"] = "frustration_fire"
                        bb["force_macro_until:overlay"] = now + 6.0
                        bb["force_macro_uses:overlay"] = 1
                        bb["last_frustration_fire_t"] = now
                    else:
                        bb["force_macro:overlay"] = "unstick_sound"
                        bb["force_macro_until:overlay"] = now + 4.0
                        bb["force_macro_uses:overlay"] = 1
                    bb["last_unstick_sound_t"] = now
                try:
                    ctx.patrol._unstick()
                except Exception:
                    pass
                return True
            ctx.patrol.chassis.drive_speed(x=0.0, y=0.0, z=z)
            return False
        if k == "cruise":
            if self.t0 is None:
                self.t0 = ctx.now
                try:
                    rx, ry, _ = ctx.pose
                except Exception:
                    rx, ry = 0.0, 0.0
                self.state["cruise_last_pose"] = (float(rx), float(ry))
                self.state["cruise_last_progress_t"] = now
            dur = float(step.args[0])
            if (ctx.now - self.t0) >= dur:
                safe_stop(ctx)
                return True
            dist = ctx.dist
            v = ctx.patrol._cruise_speed(dist) if dist is not None else 0.0
            try:
                rx, ry, _ = ctx.pose
                last_rx, last_ry = self.state.get("cruise_last_pose", (float(rx), float(ry)))
                moved = ((float(rx) - float(last_rx)) ** 2 + (float(ry) - float(last_ry)) ** 2) ** 0.5
                if moved > 0.02:
                    self.state["cruise_last_pose"] = (float(rx), float(ry))
                    self.state["cruise_last_progress_t"] = now
            except Exception:
                pass
            last_progress_t = float(self.state.get("cruise_last_progress_t", now))
            if v > 0.12 and (now - last_progress_t) > 1.1:
                bb["stat:stuck_breaks"] = int(bb.get("stat:stuck_breaks", 0)) + 1
                bb["stuck_cooldown_until"] = now + 2.5
                safe_stop(ctx)
                ft0 = float(bb.get("frustration_t0", 0.0))
                if (now - ft0) > 25.0:
                    bb["frustration_t0"] = now
                    bb["frustration_count"] = 0
                bb["frustration_count"] = int(bb.get("frustration_count", 0)) + 1
                last_fx = float(bb.get("last_unstick_sound_t", 0.0))
                if (now - last_fx) > 3.0:
                    person_seen = bool(bb.get("person_seen", False))
                    dist = bb.get("dist", None)
                    try:
                        dist_v = float(dist) if dist is not None else None
                    except Exception:
                        dist_v = None
                    safe_dist = (dist_v is None) or (dist_v > 1.2)
                    can_fire = bool(bb_get(bb, "enable_fire", False)) and (not person_seen) and safe_dist
                    fire_cd = float(bb.get("last_frustration_fire_t", 0.0))
                    if can_fire and int(bb.get("frustration_count", 0)) >= 3 and (now - fire_cd) > 22.0:
                        bb["force_macro:overlay"] = "frustration_fire"
                        bb["force_macro_until:overlay"] = now + 6.0
                        bb["force_macro_uses:overlay"] = 1
                        bb["last_frustration_fire_t"] = now
                    else:
                        bb["force_macro:overlay"] = "unstick_sound"
                        bb["force_macro_until:overlay"] = now + 4.0
                        bb["force_macro_uses:overlay"] = 1
                    bb["last_unstick_sound_t"] = now
                try:
                    ctx.patrol._unstick()
                except Exception:
                    pass
                return True
            ctx.patrol.chassis.drive_speed(x=float(v), y=0.0, z=0.0)
            return False
        if k == "move":
            x, y, z, xy_speed, z_speed, timeout = step.args
            action = self.state.get("move_action")
            if action is None:
                if not self._sdk_action_try_acquire(bb, now, "move", ttl_s=float(timeout)):
                    return False
                try:
                    action = ctx.patrol.chassis.move(x=float(x), y=float(y), z=float(z), xy_speed=float(xy_speed), z_speed=float(z_speed))
                    self.state["move_action"] = action
                    self.state["move_deadline"] = ctx.now + float(timeout)
                except Exception:
                    self._sdk_action_release(bb)
                    return True
            deadline = float(self.state.get("move_deadline", ctx.now))
            if ctx.now >= deadline:
                self.state.pop("move_action", None)
                self._sdk_action_release(bb)
                return True
            try:
                ok = action.wait_for_completed(timeout=0.01)
                if ok:
                    self.state.pop("move_action", None)
                    self._sdk_action_release(bb)
                    return True
            except Exception:
                self.state.pop("move_action", None)
                self._sdk_action_release(bb)
                return True
            return False
        if k == "gimbal_to":
            pitch, yaw = step.args
            action = self.state.get("gimbal_action")
            if action is None:
                if not self._sdk_action_try_acquire(bb, now, "gimbal", ttl_s=2.5):
                    return False
                try:
                    action = ctx.patrol.gimbal.moveto(pitch=float(pitch), yaw=float(yaw), pitch_speed=30, yaw_speed=80)
                    self.state["gimbal_action"] = action
                    self.state["gimbal_deadline"] = ctx.now + 2.5
                except Exception:
                    self._sdk_action_release(bb)
                    return True
            if ctx.now >= float(self.state.get("gimbal_deadline", ctx.now)):
                self.state.pop("gimbal_action", None)
                self._sdk_action_release(bb)
                return True
            try:
                ok = action.wait_for_completed(timeout=0.01)
                if ok:
                    self.state.pop("gimbal_action", None)
                    self._sdk_action_release(bb)
                    return True
            except Exception:
                self.state.pop("gimbal_action", None)
                self._sdk_action_release(bb)
                return True
            return False
        if k == "gimbal_center":
            action = self.state.get("gimbal_action")
            if action is None:
                if not self._sdk_action_try_acquire(bb, now, "gimbal", ttl_s=2.5):
                    return False
                try:
                    action = ctx.patrol.gimbal.recenter()
                    self.state["gimbal_action"] = action
                    self.state["gimbal_deadline"] = ctx.now + 2.5
                except Exception:
                    self._sdk_action_release(bb)
                    return True
            if ctx.now >= float(self.state.get("gimbal_deadline", ctx.now)):
                self.state.pop("gimbal_action", None)
                self._sdk_action_release(bb)
                return True
            try:
                ok = action.wait_for_completed(timeout=0.01)
                if ok:
                    self.state.pop("gimbal_action", None)
                    self._sdk_action_release(bb)
                    return True
            except Exception:
                self.state.pop("gimbal_action", None)
                self._sdk_action_release(bb)
                return True
            return False
        if k == "gimbal_sweep":
            dur, yaw_left, yaw_right = step.args
            dur = float(dur)
            yaw_left = float(yaw_left)
            yaw_right = float(yaw_right)
            if self.t0 is None:
                self.t0 = ctx.now
                self.state["phase"] = 0
            if (ctx.now - self.t0) >= dur:
                self.t0 = None
                self.state = {}
                self._sdk_action_release(bb)
                return True
            phase = int(self.state.get("phase", 0))
            targets = [yaw_left, yaw_right, 0.0]
            target = targets[phase % len(targets)]
            action = self.state.get("gimbal_action")
            if action is None:
                if not self._sdk_action_try_acquire(bb, now, "gimbal", ttl_s=1.2):
                    return False
                try:
                    action = ctx.patrol.gimbal.moveto(pitch=0.0, yaw=float(target), pitch_speed=30, yaw_speed=80)
                    self.state["gimbal_action"] = action
                except Exception:
                    self.state["phase"] = phase + 1
                    self._sdk_action_release(bb)
                    return False
            try:
                ok = action.wait_for_completed(timeout=0.01)
                if ok:
                    self.state["gimbal_action"] = None
                    self.state["phase"] = phase + 1
                    self._sdk_action_release(bb)
            except Exception:
                self.state["gimbal_action"] = None
                self.state["phase"] = phase + 1
                self._sdk_action_release(bb)
            return False
        if k == "led":
            r, g, b, effect = step.args
            try:
                ctx.patrol.robot.led.set_led(comp="all", r=int(r), g=int(g), b=int(b), effect=str(effect))
            except Exception:
                pass
            return True
        if k == "expression":
            apply_expression(ctx, bb)
            return True
        if k == "sound":
            sound_id = step.args[0]
            if not self._sdk_action_try_acquire(bb, now, "sound", ttl_s=1.0):
                return False
            try:
                ctx.patrol.speaker.play(int(sound_id))
            except Exception:
                pass
            self._sdk_action_release(bb)
            return True
        if k == "sound_seq":
            seq, interval_s = step.args
            if not isinstance(seq, (list, tuple)) or not seq:
                return True
            interval_s = float(interval_s)
            if self.t0 is None:
                self.t0 = ctx.now
                self.state["sound_i"] = 0
                self.state["sound_next_t"] = ctx.now
            i = int(self.state.get("sound_i", 0))
            if i >= len(seq):
                return True
            next_t = float(self.state.get("sound_next_t", ctx.now))
            action = self.state.get("sound_action")
            deadline = float(self.state.get("sound_deadline", 0.0))
            if action is not None:
                if ctx.now >= deadline:
                    self.state["sound_action"] = None
                    self.state["sound_i"] = i + 1
                    self.state["sound_next_t"] = ctx.now + interval_s
                    self._sdk_action_release(bb)
                    return False
                try:
                    ok = action.wait_for_completed(timeout=0.01)
                    if ok:
                        self.state["sound_action"] = None
                        self.state["sound_i"] = i + 1
                        self.state["sound_next_t"] = ctx.now + interval_s
                        self._sdk_action_release(bb)
                except Exception:
                    self.state["sound_action"] = None
                    self.state["sound_i"] = i + 1
                    self.state["sound_next_t"] = ctx.now + interval_s
                    self._sdk_action_release(bb)
                return False
            if ctx.now < next_t:
                return False
            sound_id = seq[i]
            if not self._sdk_action_try_acquire(bb, now, "sound", ttl_s=1.2):
                return False
            try:
                action = ctx.patrol.robot.play_sound(int(sound_id))
                self.state["sound_action"] = action
                self.state["sound_deadline"] = ctx.now + 1.2
                self.state["sound_next_t"] = ctx.now + interval_s
            except Exception:
                self.state["sound_i"] = i + 1
                self.state["sound_next_t"] = ctx.now + interval_s
                self._sdk_action_release(bb)
            return False
        if k == "audio_pick":
            tags = step.args[0] if step.args else ()
            if isinstance(tags, str):
                tags = bb.get(tags, ())
            target = step.args[1] if len(step.args) > 1 else 1.0
            try:
                if isinstance(target, str):
                    dur_s = float(bb.get(target, 1.0))
                else:
                    dur_s = float(target)
            except Exception:
                dur_s = 1.0
            chosen = self.state.get("audio_pick_chosen")
            if not isinstance(chosen, tuple) or len(chosen) != 2:
                seed = bb_get(bb, "rng_seed", None)
                c = int(bb.get("audio_pick_counter", 0))
                bb["audio_pick_counter"] = c + 1
                rng = random.Random(hash((seed, "audio_pick", c, int(ctx.now * 10))))
                try:
                    try:
                        from .audio_catalog import pick_clip
                    except ImportError:
                        from audio_catalog import pick_clip
                    clip = pick_clip(tags=list(tags) if isinstance(tags, (list, tuple)) else [str(tags)], target_s=dur_s, rng=rng)
                except Exception:
                    clip = None
                if clip is None:
                    return True
                self.state["audio_pick_chosen"] = (clip.rel_path, float(clip.dur_s))
                chosen = self.state["audio_pick_chosen"]

            path, chosen_dur = chosen
            try:
                chosen_dur_s = float(chosen_dur)
            except Exception:
                chosen_dur_s = dur_s
            if not isinstance(path, str) or not path:
                self.state.pop("audio_pick_chosen", None)
                return True

            step = type(step)(kind="audio", args=(path, float(chosen_dur_s)))
            k = "audio"
        if k == "audio":
            path = step.args[0] if step.args else ""
            dur_s = float(step.args[1]) if len(step.args) > 1 else 3.0
            if not isinstance(path, str) or not path:
                return True
            bb["last_audio_t"] = now
            import os
            if not os.path.isabs(path):
                path = os.path.abspath(os.path.join(os.path.dirname(__file__), path))
            if not os.path.exists(path):
                return True
            action = self.state.get("audio_action")
            deadline = float(self.state.get("audio_deadline", 0.0))
            if action is not None:
                if ctx.now >= deadline:
                    self.state["audio_action"] = None
                    self._sdk_action_release(bb)
                    return True
                try:
                    ok = action.wait_for_completed(timeout=0.01)
                    if ok:
                        self.state["audio_action"] = None
                        self._sdk_action_release(bb)
                        return True
                except Exception:
                    self.state["audio_action"] = None
                    self._sdk_action_release(bb)
                    return True
                return False
            if not self._sdk_action_try_acquire(bb, now, "audio", ttl_s=max(1.0, dur_s + 2.0)):
                return False
            try:
                self.state["audio_action"] = ctx.patrol.robot.play_audio(path)
                self.state["audio_deadline"] = ctx.now + max(0.2, dur_s + 2.0)
            except Exception:
                self.state["audio_action"] = None
                self._sdk_action_release(bb)
                return True
            return False
        if k == "utter":
            now = ctx.now
            key = "last_utter_t"
            if now - float(bb.get(key, 0.0)) < 3.0:
                return True
            uc = int(bb.get("utter_counter", 0))
            bb["utter_counter"] = uc + 1
            seed = bb_get(bb, "rng_seed", None)
            rng = random.Random(hash((seed, uc, int(now * 10))))
            mood = str(bb_get(bb, "mood", "curious"))
            text = choose_utterance(mood, rng)
            print(f"[persona] {mood}: {text}")
            bb[key] = now
            return True
        if k == "fire":
            if not bool(bb_get(bb, "enable_fire", False)):
                return True
            if not self.macro.allow_fire:
                return True
            count = int(step.args[0]) if step.args else 1
            now = ctx.now
            last = float(bb.get("last_fire_t", 0.0))
            if now - last < 0.45:
                return False
            try:
                ctx.patrol.robot.blaster.fire(fire_type="ir", times=count)
            except Exception:
                pass
            bb["last_fire_t"] = now
            return True
        if k == "fire_burst":
            if not bool(bb_get(bb, "enable_fire", False)):
                return True
            if not self.macro.allow_fire:
                return True
            duration_s, interval_s, times_each = step.args
            duration_s = float(duration_s)
            interval_s = float(interval_s)
            times_each = int(times_each)
            if duration_s <= 0.0:
                return True
            if self.t0 is None:
                self.t0 = ctx.now
                self.state["fire_last_t"] = 0.0
            if (ctx.now - self.t0) >= duration_s:
                return True
            last_t = float(self.state.get("fire_last_t", 0.0))
            if (ctx.now - last_t) < interval_s:
                return False
            try:
                ctx.patrol.robot.blaster.fire(fire_type="ir", times=times_each)
            except Exception:
                pass
            self.state["fire_last_t"] = ctx.now
            return False
        if k == "fire_repeat":
            if not bool(bb_get(bb, "enable_fire", False)):
                return True
            if not self.macro.allow_fire:
                return True
            count, interval_s = step.args
            count = int(count)
            interval_s = float(interval_s)
            if count <= 0:
                return True
            if self.t0 is None:
                self.t0 = ctx.now
                self.state["fire_i"] = 0
                self.state["fire_next_t"] = ctx.now
            i = int(self.state.get("fire_i", 0))
            if i >= count:
                return True
            next_t = float(self.state.get("fire_next_t", ctx.now))
            if ctx.now < next_t:
                return False
            try:
                ctx.patrol.robot.blaster.fire(fire_type="ir", times=1)
            except Exception:
                pass
            self.state["fire_i"] = i + 1
            self.state["fire_next_t"] = ctx.now + max(0.05, interval_s)
            return False
        if k == "unstick":
            try:
                ok = ctx.patrol._unstick()
                return bool(ok)
            except Exception:
                return False
        return True


def _dance_macro(name: str, turns: List[float], wiggle: bool, color: Tuple[int, int, int], sound: Optional[int]) -> Macro:
    r, g, b = color
    steps: List[Step] = [Step("led", (r, g, b, "flash")), Step("expression")]
    if sound is not None:
        steps.append(Step("sound", (sound,)))
    for t in turns:
        steps.append(Step("spin", (float(t), 90.0)))
        if wiggle:
            steps.append(Step("drive", (0.35, 0.0, 0.0, 55)))
            steps.append(Step("drive", (0.35, 0.0, 0.0, -55)))
    steps.append(Step("gimbal_center"))
    steps.append(Step("led", (255, 255, 255, "on")))
    return Macro(name=name, steps=steps, tags=("dance",), weight=0.18, cooldown_s=25.0)


def _prank_macro(name: str, side: float, sound: Optional[int]) -> Macro:
    steps: List[Step] = [Step("expression"), Step("utter")]
    if sound is not None:
        steps.append(Step("sound", (sound,)))
    steps.extend(
        [
            Step("spin", (45 * side, 120.0)),
            Step("drive", (0.45, 0.18, 0.0, 0.0)),
            Step("drive", (0.45, -0.22, 0.0, 0.0)),
            Step("spin", (-70 * side, 120.0)),
        ]
    )
    return Macro(name=name, steps=steps, tags=("prank",), weight=0.8, cooldown_s=14.0)


def _idle_macro(name: str, sec: float, look: bool) -> Macro:
    steps: List[Step] = [Step("stop"), Step("expression"), Step("utter")]
    if look:
        steps.extend([Step("gimbal_sweep", (sec, -28, 28)), Step("gimbal_center")])
    steps.append(Step("sleep", (sec,)))
    return Macro(name=name, steps=steps, tags=("idle",), weight=0.6, cooldown_s=8.0)


def _explore_burst(name: str, v: float, sec: float) -> Macro:
    steps: List[Step] = [Step("expression"), Step("drive", (sec, v, 0.0, 0.0)), Step("gimbal_sweep", (sec, -25, 25)), Step("stop")]
    return Macro(name=name, steps=steps, tags=("explore",), weight=1.4, cooldown_s=2.0)


def _adventure_walk(name: str, sec: float) -> Macro:
    steps: List[Step] = [
        Step("expression"),
        Step("utter"),
        Step("gimbal_sweep", (min(4.0, sec), -35, 35)),
        Step("cruise", (sec,)),
        Step("stop"),
        Step("gimbal_center"),
    ]
    return Macro(name=name, steps=steps, tags=("adventure", "explore"), weight=2.0, cooldown_s=1.5)

def _adventure_long(name: str, sec: float) -> Macro:
    sec = float(sec)
    steps: List[Step] = [
        Step("expression"),
        Step("utter"),
        Step("sound_seq", ([2, 3, 4, 3, 2], 0.45)),
        Step("gimbal_sweep", (min(8.0, sec), -40, 40)),
        Step("cruise", (sec,)),
        Step("gimbal_sweep", (min(6.0, sec), -25, 25)),
        Step("stop"),
        Step("gimbal_center"),
    ]
    return Macro(name=name, steps=steps, tags=("adventure", "explore"), weight=3.0, cooldown_s=2.0)

def _showoff_song(name: str, seq: List[int]) -> Macro:
    steps: List[Step] = [
        Step("expression"),
        Step("sound_seq", (seq, 0.5)),
    ]
    return Macro(name=name, steps=steps, tags=("show", "talk"), weight=0.7, cooldown_s=18.0)

def _showoff_fire(name: str) -> Macro:
    steps: List[Step] = [
        Step("expression"),
        Step("led", (255, 80, 80, "flash")),
        Step("sound_seq", ([7, 6, 7], 0.55)),
        Step("fire_repeat", (10, 0.18)),
        Step("led", (255, 255, 255, "on")),
    ]
    return Macro(name=name, steps=steps, tags=("show", "fire"), weight=0.25, cooldown_s=35.0, allow_fire=True)


def build_catalog() -> List[Macro]:
    macros: List[Macro] = []
    macros.extend(build_micro_library(seed=0))

    colors = [
        (255, 80, 80),
        (80, 255, 120),
        (80, 160, 255),
        (255, 200, 60),
        (255, 80, 220),
        (200, 200, 200),
    ]
    sounds = [1, 2, 3, 4, 5, 6, 7, None]

    dance_turn_sets = [
        [30, -30, 60, -60],
        [45, 45, -90],
        [60, -120, 60],
        [90, -90, 180],
        [120, -60, -60],
    ]
    for ci, c in enumerate(colors):
        for si, s in enumerate(sounds):
            for ti, turns in enumerate(dance_turn_sets):
                macros.append(_dance_macro(f"dance_{ci}_{si}_{ti}_a", turns, True, c, s))
                macros.append(_dance_macro(f"dance_{ci}_{si}_{ti}_b", list(reversed(turns)), False, c, s))

    for side in (-1.0, 1.0):
        for si, s in enumerate(sounds):
            for i in range(10):
                macros.append(_prank_macro(f"prank_{int(side)}_{si}_{i}", side, s))

    for i in range(20):
        sec = 0.6 + 0.12 * (i % 5)
        look = (i % 2) == 0
        macros.append(_idle_macro(f"idle_{i}", sec, look))

    for i in range(30):
        v = 0.12 + 0.01 * (i % 8)
        sec = 1.8 + 0.18 * (i % 8)
        macros.append(_explore_burst(f"explore_{i}", v, sec))

    for i in range(24):
        sec = 4.0 + 0.5 * (i % 9)
        macros.append(_adventure_walk(f"adventure_{i}", sec))

    for i in range(12):
        sec = 10.0 + 1.0 * (i % 9)
        macros.append(_adventure_long(f"adventure_long_{i}", sec))

    song_seqs = [
        [1, 2, 3, 4, 3, 2, 1],
        [2, 2, 5, 5, 6, 6, 5],
        [3, 4, 3, 2, 1, 2, 3],
        [4, 6, 7, 6, 4, 3, 2],
    ]
    for i, seq in enumerate(song_seqs):
        macros.append(_showoff_song(f"song_{i}", seq))

    for i in range(6):
        macros.append(_showoff_fire(f"show_fire_{i}"))

    for i in range(20):
        r = int(40 + (i * 11) % 215)
        g = int(40 + (i * 23) % 215)
        b = int(40 + (i * 37) % 215)
        steps = [
            Step("led", (r, g, b, "breath")),
            Step("sound", (i % 8 + 1,)),
            Step("gimbal_to", (0, -20)),
            Step("gimbal_to", (0, 20)),
            Step("gimbal_center"),
            Step("utter"),
            Step("sleep", (0.5,)),
            Step("led", (255, 255, 255, "on")),
        ]
        macros.append(Macro(name=f"monologue_{i}", steps=steps, tags=("talk", "mood"), weight=0.5, cooldown_s=10.0))

    macros.append(
        Macro(
            name="mischief_shoot_ir",
            steps=[Step("expression"), Step("utter"), Step("sound_seq", ([7, 7, 6, 7], 0.45)), Step("fire_repeat", (10, 0.18)), Step("sleep", (0.8,))],
            tags=("prank", "fire"),
            weight=0.2,
            cooldown_s=30.0,
            allow_fire=True,
        )
    )

    uniq = {m.name: m for m in macros}
    macros = list(uniq.values())
    macros.sort(key=lambda m: m.name)
    return macros


def pick_macro(macros: List[Macro], bb: Blackboard, mood: str) -> Macro:
    now = float(bb_get(bb, "now", time.time()))
    rc = int(bb.get("rng_counter", 0))
    bb["rng_counter"] = rc + 1
    seed = bb_get(bb, "rng_seed", None)
    rng = random.Random(hash((seed, rc, int(now * 10))))

    def category(m: Macro) -> str:
        if "context" in m.tags:
            return "context"
        if "energy" in m.tags or "sleep" in m.tags:
            return "energy"
        if "social" in m.tags:
            return "social"
        if "look" in m.tags or "curiosity" in m.tags:
            return "look"
        if "show" in m.tags:
            return "show"
        if "adventure" in m.tags:
            return "adventure"
        if "explore" in m.tags:
            return "explore"
        if "environment" in m.tags:
            return "environment"
        if "prank" in m.tags:
            return "prank"
        if "dance" in m.tags:
            return "dance"
        if "talk" in m.tags:
            return "talk"
        if "idle" in m.tags:
            return "idle"
        if "random" in m.tags:
            return "random"
        if "emotion" in m.tags:
            return "emotion"
        if "movement" in m.tags:
            return "movement"
        return "explore"

    pools: Dict[str, List[Macro]] = {}
    for m in macros:
        cd_key = f"cd:{m.name}"
        last = float(bb.get(cd_key, 0.0))
        if m.cooldown_s and now - last < m.cooldown_s:
            continue
        pools.setdefault(category(m), []).append(m)

    energy = float(bb_get(bb, "energy", 0.8))
    enable_fire = bool(bb_get(bb, "enable_fire", False))

    override = bb.get("cat_weights_override")
    if isinstance(override, dict) and override:
        base_cat_weights = {k: float(v) for k, v in override.items() if v is not None}
        cfg_by_mood = bb.get("cat_weights_by_mood")
    else:
        base_cat_weights = {
            "adventure": 0.40,
            "explore": 0.18,
            "look": 0.10,
            "social": 0.10,
            "idle": 0.07,
            "emotion": 0.05,
            "random": 0.03,
            "movement": 0.03,
            "environment": 0.03,
            "show": 0.03,
            "prank": 0.03,
            "dance": 0.02,
            "talk": 0.02,
            "energy": 0.01,
            "context": 0.00,
        }
        cfg_by_mood = bb.get("cat_weights_by_mood")
        if isinstance(cfg_by_mood, dict):
            mcfg = cfg_by_mood.get(mood)
            if isinstance(mcfg, dict) and mcfg:
                base_cat_weights = dict(mcfg)

    cat_weights = dict(base_cat_weights)
    if mood == "sleepy" or energy < 0.25:
        sleepy = cfg_by_mood.get("sleepy") if isinstance(cfg_by_mood, dict) else None
        cat_weights = dict(sleepy) if isinstance(sleepy, dict) and sleepy else {"idle": 0.45, "energy": 0.20, "look": 0.12, "talk": 0.10, "adventure": 0.08, "explore": 0.04, "social": 0.01}
    elif mood == "scared":
        scared = cfg_by_mood.get("scared") if isinstance(cfg_by_mood, dict) else None
        cat_weights = dict(scared) if isinstance(scared, dict) and scared else {"adventure": 0.62, "explore": 0.22, "look": 0.10, "idle": 0.06}
    elif mood == "mischief":
        mischief = cfg_by_mood.get("mischief") if isinstance(cfg_by_mood, dict) else None
        if isinstance(mischief, dict) and mischief:
            cat_weights = dict(mischief)
        else:
            cat_weights["prank"] = 0.10
            cat_weights["random"] = 0.06
            cat_weights["show"] = 0.05
            cat_weights["dance"] = 0.04
            cat_weights["idle"] = 0.05
            cat_weights["adventure"] = 0.35
    elif mood == "angry":
        angry = cfg_by_mood.get("angry") if isinstance(cfg_by_mood, dict) else None
        if isinstance(angry, dict) and angry:
            cat_weights = dict(angry)
        else:
            cat_weights["dance"] = 0.01
            cat_weights["prank"] = 0.04
            cat_weights["adventure"] = 0.55
            cat_weights["explore"] = 0.20

    cats = [c for c in cat_weights.keys() if pools.get(c)]
    if not cats:
        cats = list(pools.keys())
    cw = [max(0.0, float(cat_weights.get(c, 0.1))) for c in cats]
    force_cat = bb.get("force_cat")
    if force_cat and now < float(bb.get("force_cat_until", 0.0)) and pools.get(str(force_cat)):
        chosen_cat = str(force_cat)
        uses = int(bb.get("force_cat_uses", 1))
        uses -= 1
        if uses <= 0:
            bb.pop("force_cat", None)
            bb.pop("force_cat_until", None)
            bb.pop("force_cat_uses", None)
        else:
            bb["force_cat_uses"] = uses
    else:
        chosen_cat = rng.choices(cats, weights=cw, k=1)[0]
    bb["stat:last_cat"] = chosen_cat
    bb["stat:last_cat_t"] = now
    bb[f"stat:cat:{chosen_cat}"] = int(bb.get(f"stat:cat:{chosen_cat}", 0)) + 1

    eligible = pools.get(chosen_cat, [])
    if not eligible:
        eligible = [m for ms in pools.values() for m in ms]
    weights: List[float] = []
    person_seen = bool(bb.get("person_seen", False))
    dist = bb.get("dist", None)
    try:
        dist_v = float(dist) if dist is not None else None
    except Exception:
        dist_v = None
    import os
    base_dir = os.path.dirname(__file__)
    for m in eligible:
        w = float(m.weight)
        if not enable_fire and "fire" in m.tags:
            w *= 0.0
        if "fire" in m.tags and (person_seen or (dist_v is not None and dist_v < 1.0)):
            w *= 0.0
        if w > 0.0:
            for s in m.steps:
                if s.kind != "audio" or not s.args:
                    continue
                p = s.args[0]
                if not isinstance(p, str) or not p:
                    w *= 0.0
                    break
                if os.path.isabs(p):
                    ap = p
                else:
                    ap = os.path.abspath(os.path.join(base_dir, p))
                if not os.path.exists(ap):
                    w *= 0.0
                    break
        if mood == "scared" and ("prank" in m.tags or "dance" in m.tags or "fire" in m.tags):
            w *= 0.0
        if mood == "curious" and ("adventure" in m.tags or "explore" in m.tags):
            w *= 1.4
        if mood == "mischief" and "prank" in m.tags:
            w *= 1.6
        if mood == "sleepy" and "idle" in m.tags:
            w *= 2.0

        wide_open = float(bb.get("wide_open_dist_m", 1.6))
        if dist_v is not None and dist_v >= wide_open and not person_seen:
            is_forward_arc = False
            is_forward_straight = False
            for s in m.steps:
                if s.kind == "cruise":
                    is_forward_straight = True
                    break
                if s.kind != "drive" or not s.args:
                    continue
                try:
                    _dur, x, _y, z = s.args
                    x = float(x)
                    z = float(z)
                except Exception:
                    continue
                if x > 0.12:
                    if abs(z) > 1e-6:
                        is_forward_arc = True
                    else:
                        is_forward_straight = True
                    break
            if is_forward_arc:
                w *= 0.35
            elif is_forward_straight:
                w *= 1.15
        weights.append(max(0.0, w))

    chosen = rng.choices(eligible, weights=weights, k=1)[0]
    bb[f"cd:{chosen.name}"] = now
    return chosen
