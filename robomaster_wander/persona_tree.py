import random
import time

try:
    from .persona_behaviors import build_catalog
    from .persona_runtime import PersonaCtx, Blackboard, apply_expression, estimate_forward_obstacle, safe_stop, update_affect
    from .persona_tracks import build_default_tracks
    from .persona_optimizer import AutoOptimizer
except ImportError:
    from persona_behaviors import build_catalog
    from persona_runtime import PersonaCtx, Blackboard, apply_expression, estimate_forward_obstacle, safe_stop, update_affect
    from persona_tracks import build_default_tracks
    from persona_optimizer import AutoOptimizer


class PersonaController:
    def __init__(self, enable_fire: bool = False):
        self.enable_fire = bool(enable_fire)
        self.macros = build_catalog()
        self._macro_by_name = {m.name: m for m in self.macros}
        self.bb: Blackboard = {
            "rng_seed": int(time.time()),
            "energy": 0.85,
            "mood": "curious",
            "enable_fire": self.enable_fire,
            "scared_dist_m": 0.45,
            "danger_dist_m": 0.55,
            "danger_visual_m": 0.85,
            "safety_stop_dist_m": 0.3,
            "safety_visual_m": 0.45,
            "autotune": {
                "enabled": True,
                "interval_s": 15.0,
                "target_avoid_per_min": 6.0,
                "target_overlay_per_min": 8.0,
                "persist": False,
            },
            "need_boredom": 0.2,
            "need_curiosity": 0.4,
            "need_social": 0.35,
            "need_boredom_up_per_s": 0.004,
            "need_curiosity_up_per_s": 0.003,
            "need_social_up_per_s": 0.0025,
            "need_social_boost_on_person": 0.18,
            "need_novelty_boost_on_person": 0.12,
            "need_play": 0.35,
            "need_play_up_per_s": 0.0018,
            "social_mode_until": 0.0,
            "next_trick_t": time.time() + 18.0,
            "last_trick_t": 0.0,
            "last_random_sound_t": 0.0,
            "last_voice_t": 0.0,
            "last_puppy_fx_t": 0.0,
            "last_audio_t": 0.0,
            "last_unstick_sound_t": 0.0,
            "frustration_t0": 0.0,
            "frustration_count": 0,
            "last_frustration_fire_t": 0.0,
            "audio_tags": ("any",),
            "audio_target_s": 1.0,
        }
        self._track_loco, self._track_head, self._track_overlay = build_default_tracks(self.macros)
        self._optimizer = AutoOptimizer()

    def behavior_count(self) -> int:
        return len(self.macros)

    def tick(self, ctx: PersonaCtx) -> None:
        self.bb["stat:block_reason"] = ""
        self.bb["now"] = ctx.now
        if getattr(ctx, "battery_pct", None) is not None:
            self.bb["battery_pct"] = int(ctx.battery_pct)
        self.bb["dist"] = ctx.dist
        update_affect(ctx, self.bb)
        apply_expression(ctx, self.bb)
        self._optimizer.tick(ctx, self.bb)

        self._maybe_social_and_trick(ctx)
        enable_fire_now = bool(self.enable_fire) and (not bool(self.bb.get("person_seen", False)))
        self.bb["enable_fire"] = bool(enable_fire_now)
        self._maybe_leave_area(ctx)

        if ctx.now < float(self.bb.get("stuck_cooldown_until", 0.0)):
            self.bb["stat:block_reason"] = "stuck_cooldown"
            safe_stop(ctx)
            mood = str(self.bb.get("mood", "curious"))
            self._track_head.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._track_overlay.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._maybe_print_stats(ctx)
            return

        avoid_active = self._avoid(ctx)
        if avoid_active:
            mood = str(self.bb.get("mood", "curious"))
            self._track_head.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._track_overlay.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._maybe_print_stats(ctx)
            return

        if self._safety_backoff(ctx):
            mood = str(self.bb.get("mood", "curious"))
            self._track_head.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._track_overlay.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
            self._maybe_print_stats(ctx)
            return

        if not self._safety(ctx):
            self._maybe_print_stats(ctx)
            return

        mood = str(self.bb.get("mood", "curious"))
        self._maybe_minion_background(ctx)
        self._track_loco.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
        self._track_head.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
        self._maybe_audio_idle(ctx)
        self._maybe_puppy_fx(ctx)
        self._maybe_sync_random_sound(ctx)
        self._track_overlay.tick(ctx, self.bb, mood=mood, enable_fire=enable_fire_now)
        self._watchdog_no_progress(ctx)
        self._maybe_print_stats(ctx)

    def _maybe_leave_area(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        person_seen = bool(self.bb.get("person_seen", False))
        if person_seen:
            return
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is None:
            return
        wide_open = float(self.bb.get("wide_open_dist_m", 1.4))
        if dist_v < wide_open:
            return
        try:
            rx, ry, _ = ctx.pose
            x = float(rx)
            y = float(ry)
        except Exception:
            return
        anchor = self.bb.get("area_anchor_pose")
        if not (isinstance(anchor, (list, tuple)) and len(anchor) == 2):
            self.bb["area_anchor_pose"] = (x, y)
            self.bb["area_anchor_t"] = now
            self.bb["area_last_leave_t"] = 0.0
            return
        ax, ay = anchor
        try:
            ax = float(ax)
            ay = float(ay)
        except Exception:
            self.bb["area_anchor_pose"] = (x, y)
            self.bb["area_anchor_t"] = now
            return
        drift = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
        if drift > 1.0:
            self.bb["area_anchor_pose"] = (x, y)
            self.bb["area_anchor_t"] = now
            return
        t0 = float(self.bb.get("area_anchor_t", now))
        last_leave = float(self.bb.get("area_last_leave_t", 0.0))
        if (now - t0) < 22.0:
            return
        if (now - last_leave) < 14.0:
            return
        if drift > 0.45:
            return
        self.bb["force_cat:locomotion"] = "adventure"
        self.bb["force_cat_until:locomotion"] = now + 7.0
        self.bb["force_cat_uses:locomotion"] = 2
        self.bb["area_last_leave_t"] = now
        self.bb["area_anchor_pose"] = (x, y)
        self.bb["area_anchor_t"] = now

    def _watchdog_no_progress(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        if bool(self.bb.get("person_seen", False)):
            return
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is not None and dist_v < 0.55:
            return
        try:
            rx, ry, ryaw = ctx.pose
            x = float(rx)
            y = float(ry)
            yaw = float(ryaw)
        except Exception:
            return

        last_pose = self.bb.get("no_prog_pose")
        if not (isinstance(last_pose, (list, tuple)) and len(last_pose) == 3):
            self.bb["no_prog_pose"] = (x, y, yaw)
            self.bb["no_prog_t"] = now
            self.bb["no_prog_unstick_t"] = 0.0
            return
        lx, ly, lyaw = last_pose
        try:
            lx = float(lx)
            ly = float(ly)
            lyaw = float(lyaw)
        except Exception:
            self.bb["no_prog_pose"] = (x, y, yaw)
            self.bb["no_prog_t"] = now
            return
        moved = ((x - lx) ** 2 + (y - ly) ** 2) ** 0.5
        dy = abs((yaw - lyaw + 3.141592653589793) % (2 * 3.141592653589793) - 3.141592653589793)
        if moved > 0.08 or dy > 0.28:
            self.bb["no_prog_pose"] = (x, y, yaw)
            self.bb["no_prog_t"] = now
            return

        t0 = float(self.bb.get("no_prog_t", now))
        if (now - t0) < 14.0:
            return
        last_unstick = float(self.bb.get("no_prog_unstick_t", 0.0))
        if (now - last_unstick) < 10.0:
            return
        try:
            ok = bool(ctx.patrol._unstick())
        except Exception:
            ok = False
        self.bb["no_prog_unstick_t"] = now
        self.bb["no_prog_pose"] = (x, y, yaw)
        self.bb["no_prog_t"] = now
        if ok:
            self.bb["force_cat:locomotion"] = "adventure"
            self.bb["force_cat_until:locomotion"] = now + 6.0
            self.bb["force_cat_uses:locomotion"] = 2

    def _rng(self, key: str, now: float) -> random.Random:
        seed = self.bb.get("rng_seed", None)
        c = int(self.bb.get(key, 0))
        self.bb[key] = c + 1
        return random.Random(hash((seed, key, c, int(now * 10))))

    def _estimate_duration_s(self, macro_name: str) -> float:
        m = self._macro_by_name.get(macro_name)
        if m is None:
            return 0.0
        total = 0.0
        for s in m.steps:
            k = s.kind
            if k == "sleep":
                try:
                    total += float(s.args[0])
                except Exception:
                    pass
            elif k == "drive" or k == "cruise":
                try:
                    total += float(s.args[0])
                except Exception:
                    pass
            elif k == "spin":
                try:
                    deg, z_speed = s.args
                    z_speed = float(z_speed)
                    if abs(z_speed) > 1e-6:
                        total += abs(float(deg)) / abs(z_speed)
                except Exception:
                    pass
            elif k == "gimbal_sweep":
                try:
                    total += float(s.args[0])
                except Exception:
                    pass
        return max(0.0, total)

    def _maybe_sync_random_sound(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        if now - float(self.bb.get("last_random_sound_t", 0.0)) < 0.8:
            return
        if self.bb.get("force_cat:overlay") or self.bb.get("force_macro:overlay"):
            return
        if bool(self.bb.get("person_seen", False)):
            return
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is not None and dist_v < 0.9:
            return

        loco_name = self.bb.get("track_last_macro:locomotion")
        head_name = self.bb.get("track_last_macro:head")
        candidate = None
        for name in (loco_name, head_name):
            if not name:
                continue
            m = self._macro_by_name.get(str(name))
            if m is None:
                continue
            if "random" in (m.tags or ()):
                candidate = m.name
                break
        if not candidate:
            return

        d = self._estimate_duration_s(candidate)
        self.bb["audio_tags"] = ("any",)
        self.bb["audio_target_s"] = float(max(0.2, d))
        self.bb["force_macro:overlay"] = "dog_sync_audio"
        self.bb["force_macro_until:overlay"] = now + max(1.0, float(d) + 1.2)
        self.bb["force_macro_uses:overlay"] = 1
        self.bb["last_random_sound_t"] = now

    def _maybe_puppy_fx(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        if now - float(self.bb.get("last_puppy_fx_t", 0.0)) < 2.4:
            return
        if self.bb.get("force_cat:overlay") or self.bb.get("force_macro:overlay"):
            return

        mood = str(self.bb.get("mood", "curious"))
        person_seen = bool(self.bb.get("person_seen", False))
        tags = ("sniff", "cute", "ooh")
        if person_seen:
            tags = ("bark", "cute")
        elif mood == "sleepy":
            tags = ("snore", "breath")
        elif mood == "scared":
            tags = ("hurt", "yelp")
        elif mood == "mischief":
            tags = ("troll", "weird", "monster", "alien")
        elif mood == "angry":
            tags = ("grunt", "bark")

        last = self.bb.get("track_last_macro:locomotion") or self.bb.get("track_last_macro:head")
        d = 1.0
        if last:
            d = self._estimate_duration_s(str(last))
        d = float(max(0.25, min(3.2, d if d > 0.0 else 1.0)))

        self.bb["audio_tags"] = tuple(tags)
        self.bb["audio_target_s"] = d
        self.bb["force_macro:overlay"] = "dog_sync_audio"
        self.bb["force_macro_until:overlay"] = now + max(1.0, d + 1.1)
        self.bb["force_macro_uses:overlay"] = 1
        self.bb["last_puppy_fx_t"] = now

    def _maybe_audio_idle(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        last = float(self.bb.get("last_audio_t", 0.0))
        if (now - last) < 9.0:
            return
        if self.bb.get("force_cat:overlay") or self.bb.get("force_macro:overlay"):
            return
        person_seen = bool(self.bb.get("person_seen", False))
        if person_seen:
            return
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is not None and dist_v < 0.9:
            return
        self.bb["audio_tags"] = ("cute", "bark", "sniff", "grunt", "breath")
        self.bb["audio_target_s"] = 1.0
        self.bb["force_macro:overlay"] = "dog_sync_audio"
        self.bb["force_macro_until:overlay"] = now + 4.0
        self.bb["force_macro_uses:overlay"] = 1

    def _maybe_social_and_trick(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        person_seen = bool(self.bb.get("person_seen", False))
        last_person_t = float(self.bb.get("last_person_t", 0.0))
        if person_seen or (now - last_person_t) < 5.0:
            self.bb["force_cat:head"] = "look"
            self.bb["force_cat_until:head"] = now + 2.5
            self.bb["force_cat_uses:head"] = 1
            self.bb["force_cat:overlay"] = "social"
            self.bb["force_cat_until:overlay"] = now + 2.5
            self.bb["force_cat_uses:overlay"] = 1
            self.bb["force_cat:locomotion"] = "social"
            self.bb["force_cat_until:locomotion"] = now + 2.5
            self.bb["force_cat_uses:locomotion"] = 1
            if now - float(self.bb.get("last_voice_t", 0.0)) > 9.0:
                rng = self._rng("voice_rng", now)
                voice = rng.choice(["voice_hi", "voice_follow", "voice_here", "voice_look", "voice_pet"])
                self.bb["force_macro:overlay"] = voice
                self.bb["force_macro_until:overlay"] = now + 4.0
                self.bb["force_macro_uses:overlay"] = 1
                self.bb["last_voice_t"] = now

        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        safe_for_trick = (dist_v is None) or (dist_v > 0.55)
        if person_seen and safe_for_trick and now > float(self.bb.get("last_trick_t", 0.0)) + 18.0:
            play = float(self.bb.get("need_play", 0.0))
            if play > 0.45:
                if self._maybe_trigger_minion_show(now):
                    self.bb["last_trick_t"] = now
                    rng = self._rng("trick_rng", now)
                    self.bb["next_trick_t"] = now + rng.uniform(35.0, 65.0)
                    return
                if self._maybe_trigger_combo(now, mood=str(self.bb.get("mood", "curious")), person_seen=True):
                    self.bb["last_trick_t"] = now
                    rng = self._rng("trick_rng", now)
                    self.bb["next_trick_t"] = now + rng.uniform(35.0, 65.0)
                    return
                self.bb["force_cat:overlay"] = "show"
                self.bb["force_cat_until:overlay"] = now + 4.0
                self.bb["force_cat_uses:overlay"] = 1
                self.bb["last_trick_t"] = now
                rng = self._rng("trick_rng", now)
                self.bb["next_trick_t"] = now + rng.uniform(35.0, 65.0)

        if (not person_seen) and safe_for_trick and now >= float(self.bb.get("next_trick_t", 0.0)):
            energy = float(self.bb.get("energy", 0.0))
            mood = str(self.bb.get("mood", "curious"))
            play = float(self.bb.get("need_play", 0.0))
            if energy > 0.35 and mood != "scared" and play > 0.35:
                if self._maybe_trigger_minion_show(now):
                    self.bb["last_trick_t"] = now
                    rng = self._rng("trick_rng", now)
                    self.bb["next_trick_t"] = now + rng.uniform(35.0, 65.0)
                    return
                if self._maybe_trigger_combo(now, mood=mood, person_seen=False):
                    self.bb["last_trick_t"] = now
                    rng = self._rng("trick_rng", now)
                    self.bb["next_trick_t"] = now + rng.uniform(35.0, 65.0)
                    return
                self.bb["force_cat:overlay"] = "show"
                self.bb["force_cat_until:overlay"] = now + 4.0
                self.bb["force_cat_uses:overlay"] = 1
                self.bb["last_trick_t"] = now
            rng = self._rng("trick_rng", now)
            self.bb["next_trick_t"] = now + rng.uniform(40.0, 85.0)

    def _maybe_trigger_combo(self, now: float, mood: str, person_seen: bool) -> bool:
        if self.bb.get("force_macro:overlay") or self.bb.get("force_macro:locomotion") or self.bb.get("force_macro:head"):
            return False
        if self.bb.get("force_cat:overlay") or self.bb.get("force_cat:locomotion") or self.bb.get("force_cat:head"):
            return False
        if now < float(self.bb.get("combo_cd_t", 0.0)):
            return False

        rng = self._rng("combo_rng", now)
        if rng.random() > 0.55:
            return False

        m = str(mood or "curious")
        styles = ["curious_scout", "prank_zoom", "guard_growl", "stomp_march", "celebrate_spin"]
        if m == "sleepy" or float(self.bb.get("energy", 1.0)) < 0.28:
            styles = ["sleepy_shuffle", "curious_scout"]
        elif m == "scared":
            styles = ["guard_growl", "curious_scout"]
        elif m == "mischief":
            styles = ["prank_zoom", "stomp_march", "guard_growl", "celebrate_spin"]
        elif m == "angry":
            styles = ["guard_growl", "stomp_march"]
        if person_seen and "celebrate_spin" not in styles:
            styles.append("celebrate_spin")

        style = rng.choice(styles)
        loco = f"combo_{style}_loco"
        head = f"combo_{style}_head"
        overlay = f"combo_{style}_overlay"
        if (loco not in self._macro_by_name) or (head not in self._macro_by_name) or (overlay not in self._macro_by_name):
            return False

        until = now + 6.5
        self.bb["force_macro:locomotion"] = loco
        self.bb["force_macro_until:locomotion"] = until
        self.bb["force_macro_uses:locomotion"] = 1
        self.bb["force_macro:head"] = head
        self.bb["force_macro_until:head"] = until
        self.bb["force_macro_uses:head"] = 1
        self.bb["force_macro:overlay"] = overlay
        self.bb["force_macro_until:overlay"] = until
        self.bb["force_macro_uses:overlay"] = 1
        self.bb["combo_cd_t"] = now + 16.0
        return True

    def _maybe_trigger_minion_show(self, now: float, force: bool = False) -> bool:
        if self.bb.get("force_macro:overlay") or self.bb.get("force_macro:locomotion") or self.bb.get("force_macro:head"):
            return False
        if self.bb.get("force_cat:overlay") or self.bb.get("force_cat:locomotion") or self.bb.get("force_cat:head"):
            return False
        if now < float(self.bb.get("minion_show_cd_t", 0.0)):
            return False

        rng = self._rng("minion_rng", now)
        if (not force) and (rng.random() > 0.95):
            return False

        pools = [
            "minion_goblin_prank",
            "minion_goblin_slow",
            "minion_robot_order",
            "minion_announcer",
        ]
        i = int(self.bb.get("minion_show_i", 0))
        style = pools[i % len(pools)]
        self.bb["minion_show_i"] = i + 1

        loco = f"combo_{style}_loco"
        head = f"combo_{style}_head"
        overlay = f"combo_{style}_overlay"
        if (loco not in self._macro_by_name) or (head not in self._macro_by_name) or (overlay not in self._macro_by_name):
            return False

        until = now + 7.5
        self.bb["force_macro:locomotion"] = loco
        self.bb["force_macro_until:locomotion"] = until
        self.bb["force_macro_uses:locomotion"] = 1
        self.bb["force_macro:head"] = head
        self.bb["force_macro_until:head"] = until
        self.bb["force_macro_uses:head"] = 1
        self.bb["force_macro:overlay"] = overlay
        self.bb["force_macro_until:overlay"] = until
        self.bb["force_macro_uses:overlay"] = 1
        self.bb["minion_show_cd_t"] = now + 6.5
        return True

    def _maybe_minion_background(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        if now < float(self.bb.get("minion_bg_next_t", 0.0)):
            return
        if self.bb.get("force_macro:overlay") or self.bb.get("force_macro:locomotion") or self.bb.get("force_macro:head"):
            return
        if self.bb.get("force_cat:overlay") or self.bb.get("force_cat:locomotion") or self.bb.get("force_cat:head"):
            return
        if bool(self.bb.get("person_seen", False)):
            return
        energy = float(self.bb.get("energy", 0.0))
        if energy < 0.28:
            return
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is not None and dist_v < 0.65:
            return
        if now < float(self.bb.get("minion_show_cd_t", 0.0)):
            self.bb["minion_bg_next_t"] = now + 2.0
            return

        ok = self._maybe_trigger_minion_show(now, force=True)
        self.bb["minion_bg_next_t"] = now + (12.0 if ok else 5.0)

    def _maybe_print_stats(self, ctx: PersonaCtx) -> None:
        now = float(ctx.now)
        last = float(self.bb.get("stat:last_print_t", 0.0))
        if (now - last) < 6.0:
            return
        self.bb["stat:last_print_t"] = now

        dist = ctx.dist
        dist_str = f"{dist:.2f}m" if dist is not None else "None"
        bat = getattr(ctx, "battery_pct", None)
        bat_str = str(int(bat)) if bat is not None else "None"
        mood = str(self.bb.get("mood", "curious"))
        energy = float(self.bb.get("energy", 0.0))
        nb = float(self.bb.get("need_boredom", 0.0))
        nc = float(self.bb.get("need_curiosity", 0.0))
        ns = float(self.bb.get("need_social", 0.0))
        np = float(self.bb.get("need_play", 0.0))
        avoid_level = int(self.bb.get("avoid_level", 0))
        last_cat = self.bb.get("stat:last_cat")
        loco = self.bb.get("track_last_macro:locomotion")
        head = self.bb.get("track_last_macro:head")
        overlay = self.bb.get("track_last_macro:overlay")
        block = str(self.bb.get("stat:block_reason", ""))
        sdk_owner = str(self.bb.get("sdk_action_owner", ""))
        sdk_until = float(self.bb.get("sdk_action_until", 0.0))
        sdk_rem = max(0.0, sdk_until - now) if sdk_owner else 0.0
        al = str(self.bb.get("stat:track_active:locomotion", ""))
        ah = str(self.bb.get("stat:track_active:head", ""))
        ao = str(self.bb.get("stat:track_active:overlay", ""))
        sl = str(self.bb.get("stat:track_step:locomotion", ""))
        sh = str(self.bb.get("stat:track_step:head", ""))
        so = str(self.bb.get("stat:track_step:overlay", ""))
        next_l = max(0.0, float(self.bb.get("track_next:locomotion", 0.0)) - now)
        next_h = max(0.0, float(self.bb.get("track_next:head", 0.0)) - now)
        next_o = max(0.0, float(self.bb.get("track_next:overlay", 0.0)) - now)

        cats = []
        for c in ("adventure", "explore", "look", "social", "idle", "show", "random", "emotion", "movement", "environment", "prank", "dance", "talk", "energy"):
            cats.append((c, int(self.bb.get(f"stat:cat:{c}", 0))))
        cats.sort(key=lambda x: x[1], reverse=True)
        top = ",".join([f"{k}:{v}" for k, v in cats[:5] if v > 0])
        ps = "1" if bool(self.bb.get("person_seen", False)) else "0"
        print(f"[stat] mood={mood} energy={energy:.2f} bat={bat_str}% dist={dist_str} needs={nb:.2f},{nc:.2f},{ns:.2f},{np:.2f} ps={ps} avoid={avoid_level} block={block} cat={last_cat} loco={loco} head={head} overlay={overlay} top={top}")
        print(f"[health] sdk={sdk_owner} sdk_rem={sdk_rem:.1f}s next={next_l:.1f},{next_h:.1f},{next_o:.1f} active={al},{ah},{ao} step={sl}|{sh}|{so}")

    def _safety(self, ctx: PersonaCtx) -> bool:
        dist = ctx.dist
        if dist is not None and dist < float(self.bb.get("safety_stop_dist_m", 0.3)):
            self.bb["stat:block_reason"] = "safety:tof"
            safe_stop(ctx)
            return False
        od = estimate_forward_obstacle(ctx)
        if od is not None and od < float(self.bb.get("safety_visual_m", 0.45)):
            self.bb["stat:block_reason"] = "safety:visual"
            safe_stop(ctx)
            return False
        return True

    def _safety_backoff(self, ctx: PersonaCtx) -> bool:
        now = float(ctx.now)
        person_seen = bool(self.bb.get("person_seen", False))
        if person_seen:
            return False
        dist = ctx.dist
        try:
            dist_v = float(dist) if dist is not None else None
        except Exception:
            dist_v = None
        if dist_v is None:
            return False
        stop_dist = float(self.bb.get("safety_stop_dist_m", 0.3))
        until = float(self.bb.get("safety_backoff_until", 0.0))
        if now < until:
            side = float(self.bb.get("safety_backoff_side", 1.0))
            try:
                ctx.patrol.chassis.drive_speed(x=-0.16, y=0.0, z=55.0 * side)
            except Exception:
                try:
                    nf = getattr(ctx.patrol, "_note_action_failure", None)
                    if callable(nf):
                        nf()
                except Exception:
                    raise
            self.bb["stat:block_reason"] = "safety:backoff"
            return True
        if dist_v >= stop_dist:
            return False
        rng = self._rng("safety_backoff_rng", now)
        side = 1.0 if rng.random() < 0.5 else -1.0
        self.bb["safety_backoff_side"] = side
        self.bb["safety_backoff_until"] = now + 0.75
        self.bb["stat:block_reason"] = "safety:backoff"
        try:
            ctx.patrol.chassis.drive_speed(x=-0.16, y=0.0, z=55.0 * side)
        except Exception:
            try:
                nf = getattr(ctx.patrol, "_note_action_failure", None)
                if callable(nf):
                    nf()
            except Exception:
                raise
        return True

    def _avoid(self, ctx: PersonaCtx) -> bool:
        grace_until = float(self.bb.get("avoid_grace_until", 0.0))
        if ctx.now < grace_until:
            return False

        seq_until = float(self.bb.get("avoid_seq_until", 0.0))
        if ctx.now < seq_until:
            phase = str(self.bb.get("avoid_phase", "forward"))
            side = float(self.bb.get("avoid_side", 1.0))
            phase_until = float(self.bb.get("avoid_phase_until", 0.0))
            if ctx.now >= phase_until:
                if phase == "back":
                    phase = "turn"
                    self.bb["avoid_phase"] = phase
                    self.bb["avoid_phase_until"] = ctx.now + float(self.bb.get("avoid_turn_dur", 1.0))
                elif phase == "turn":
                    phase = "forward"
                    self.bb["avoid_phase"] = phase
                    self.bb["avoid_phase_until"] = seq_until
            self.bb["stat:block_reason"] = f"avoid:{phase}"

            dist = ctx.dist
            last_log_t = float(self.bb.get("avoid_log_t", 0.0))
            if (ctx.now - last_log_t) > 1.0:
                d_str = f"{dist:.2f}m" if dist is not None else "None"
                print(f"[persona] avoid phase={phase} dist={d_str} side={int(side)}")
                self.bb["avoid_log_t"] = ctx.now

            if phase == "back":
                try:
                    back_x = float(self.bb.get("avoid_back_x", -0.18))
                    back_y = 0.0
                    back_z = float(self.bb.get("avoid_back_z", 70.0)) * side
                    ctx.patrol.chassis.drive_speed(x=back_x, y=back_y, z=back_z)
                except Exception:
                    try:
                        nf = getattr(ctx.patrol, "_note_action_failure", None)
                        if callable(nf):
                            nf()
                    except Exception:
                        raise
                return True
            if phase == "turn":
                try:
                    turn_z = float(self.bb.get("avoid_turn_z", 120.0)) * side
                    ctx.patrol.chassis.drive_speed(x=0.0, y=0.0, z=turn_z)
                except Exception:
                    try:
                        nf = getattr(ctx.patrol, "_note_action_failure", None)
                        if callable(nf):
                            nf()
                    except Exception:
                        raise
                return True
            if dist is not None and dist < 0.12:
                self.bb["avoid_phase"] = "back"
                self.bb["avoid_phase_until"] = ctx.now + 0.9
                return True
            if dist is not None and dist > 1.0:
                self.bb["avoid_seq_until"] = 0.0
                self.bb["avoid_grace_until"] = ctx.now + 2.0
                return False
            try:
                forward_x = float(self.bb.get("avoid_forward_x", 0.28))
                forward_z = float(self.bb.get("avoid_forward_z", 45.0)) * side
                ctx.patrol.chassis.drive_speed(x=forward_x, y=0.0, z=forward_z)
            except Exception:
                try:
                    nf = getattr(ctx.patrol, "_note_action_failure", None)
                    if callable(nf):
                        nf()
                except Exception:
                    raise
            return True

        dist = ctx.dist
        od = estimate_forward_obstacle(ctx)
        danger = (dist is not None and dist < float(self.bb.get("danger_dist_m", 0.55))) or (od is not None and od < float(self.bb.get("danger_visual_m", 0.85)))
        if not danger:
            return False

        self.bb["stat:avoid_events"] = int(self.bb.get("stat:avoid_events", 0)) + 1
        now = float(ctx.now)
        ft0 = float(self.bb.get("frustration_t0", 0.0))
        if (now - ft0) > 25.0:
            self.bb["frustration_t0"] = now
            self.bb["frustration_count"] = 0
        self.bb["frustration_count"] = int(self.bb.get("frustration_count", 0)) + 1
        seed = self.bb.get("rng_seed", None)
        rc = int(self.bb.get("avoid_counter", 0))
        self.bb["avoid_counter"] = rc + 1
        rng = random.Random(hash((seed, rc, int(ctx.now * 10))))
        side = 1.0 if rng.random() < 0.5 else -1.0

        level_t0 = float(self.bb.get("avoid_level_t0", 0.0))
        if (ctx.now - level_t0) > 20.0:
            self.bb["avoid_level_t0"] = ctx.now
            self.bb["avoid_level"] = 0
        level = int(self.bb.get("avoid_level", 0)) + 1
        if level > 3:
            level = 3
        self.bb["avoid_level"] = level

        self.bb["avoid_side"] = side

        if level >= 3:
            self.bb["stat:block_reason"] = "avoid:unstick"
            last_log_t = float(self.bb.get("avoid_log_t", 0.0))
            if (ctx.now - last_log_t) > 1.0:
                d_str = f"{dist:.2f}m" if dist is not None else "None"
                od_str = f"{od:.2f}m" if od is not None else "None"
                print(f"[persona] avoid escalation dist={d_str} od={od_str} -> unstick")
                self.bb["avoid_log_t"] = ctx.now
            last_fx = float(self.bb.get("last_unstick_sound_t", 0.0))
            if (now - last_fx) > 3.0:
                person_seen = bool(self.bb.get("person_seen", False))
                safe_dist = (dist is None) or (float(dist) > 1.2)
                safe_od = (od is None) or (float(od) > 1.2)
                can_fire = bool(self.bb.get("enable_fire", False)) and (not person_seen) and safe_dist and safe_od
                fire_cd = float(self.bb.get("last_frustration_fire_t", 0.0))
                if can_fire and int(self.bb.get("frustration_count", 0)) >= 3 and (now - fire_cd) > 22.0:
                    self.bb["force_macro:overlay"] = "frustration_fire"
                    self.bb["force_macro_until:overlay"] = now + 6.0
                    self.bb["force_macro_uses:overlay"] = 1
                    self.bb["last_frustration_fire_t"] = now
                else:
                    self.bb["force_macro:overlay"] = "unstick_sound"
                    self.bb["force_macro_until:overlay"] = now + 4.0
                    self.bb["force_macro_uses:overlay"] = 1
                self.bb["last_unstick_sound_t"] = now
            try:
                ctx.patrol._unstick()
            except Exception:
                pass
            self.bb["avoid_seq_until"] = 0.0
            self.bb["avoid_grace_until"] = ctx.now + 6.0
            return True

        self.bb["avoid_phase"] = "back"
        self.bb["stat:block_reason"] = "avoid:start"
        back_dur = 0.8 + 0.3 * (level - 1)
        turn_dur = 1.0
        forward_dur = 3.5
        self.bb["avoid_turn_dur"] = turn_dur
        self.bb["avoid_back_x"] = -0.18 - 0.04 * (level - 1)
        self.bb["avoid_back_y"] = 0.0
        self.bb["avoid_back_z"] = 55.0
        self.bb["avoid_turn_z"] = 110.0
        self.bb["avoid_forward_x"] = 0.22 + 0.05 * (level - 1)
        self.bb["avoid_forward_y"] = 0.0
        self.bb["avoid_forward_z"] = 35.0
        self.bb["avoid_phase_until"] = ctx.now + back_dur
        self.bb["avoid_seq_until"] = ctx.now + back_dur + turn_dur + forward_dur
        self.bb["avoid_grace_until"] = ctx.now + back_dur + turn_dur + forward_dur + 1.0

        last_log_t = float(self.bb.get("avoid_log_t", 0.0))
        if (ctx.now - last_log_t) > 1.0:
            d_str = f"{dist:.2f}m" if dist is not None else "None"
            od_str = f"{od:.2f}m" if od is not None else "None"
            print(f"[persona] avoid start dist={d_str} od={od_str} side={int(side)} level={level}")
            self.bb["avoid_log_t"] = ctx.now

        try:
            ctx.patrol.chassis.drive_speed(x=float(self.bb.get("avoid_back_x", -0.18)), y=0.0, z=70.0 * side)
        except Exception:
            try:
                nf = getattr(ctx.patrol, "_note_action_failure", None)
                if callable(nf):
                    nf()
            except Exception:
                raise
        return True
