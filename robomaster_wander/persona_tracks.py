import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    from .persona_types import Macro
except ImportError:
    from persona_types import Macro

try:
    from .persona_behaviors import MacroPlayer, pick_macro
except ImportError:
    from persona_behaviors import MacroPlayer, pick_macro


Blackboard = Dict[str, Any]


def _macro_uses_only_kinds(m: Macro, allowed: Set[str]) -> bool:
    return all(s.kind in allowed for s in m.steps)


def _filter_macros(macros: Sequence[Macro], required_tags: Set[str], forbidden_tags: Set[str], allowed_kinds: Set[str]) -> List[Macro]:
    out: List[Macro] = []
    for m in macros:
        mtags = set(m.tags)
        if required_tags and not (mtags & required_tags):
            continue
        if forbidden_tags and (mtags & forbidden_tags):
            continue
        if not _macro_uses_only_kinds(m, allowed_kinds):
            continue
        out.append(m)
    return out


@dataclass
class Track:
    name: str
    allowed_kinds: Set[str]
    required_tags: Set[str]
    forbidden_tags: Set[str]
    min_gap_s: float
    pick_mood: Optional[str]
    overlay_probability: float = 1.0


class TrackRunner:
    def __init__(self, track: Track, all_macros: Sequence[Macro]):
        self.track = track
        self.all_macros = list(all_macros)
        self.macros = _filter_macros(all_macros, track.required_tags, track.forbidden_tags, track.allowed_kinds)
        self.active: Optional[MacroPlayer] = None

    def _step_summary(self) -> str:
        if self.active is None:
            return ""
        try:
            step = self.active.macro.steps[self.active.i]
        except Exception:
            return ""
        k = getattr(step, "kind", "")
        args = getattr(step, "args", ())
        try:
            if k == "audio" and args:
                import os
                return f"audio:{os.path.basename(str(args[0]))}"
            if k == "audio_pick":
                return "audio_pick"
            if k == "move" and len(args) >= 3:
                return f"move:{float(args[0]):.2f},{float(args[1]):.2f},{float(args[2]):.1f}"
            if k == "drive" and len(args) >= 4:
                return f"drive:{float(args[0]):.2f}s v={float(args[1]):.2f} z={float(args[3]):.0f}"
            if k == "cruise" and args:
                return f"cruise:{float(args[0]):.2f}s"
            if k == "spin" and len(args) >= 2:
                return f"spin:{float(args[0]):.0f}@{float(args[1]):.0f}"
            if k == "gimbal_sweep" and args:
                return f"gimbal_sweep:{float(args[0]):.2f}s"
            if k == "gimbal_to" and len(args) >= 2:
                return f"gimbal_to:{float(args[0]):.0f},{float(args[1]):.0f}"
            if k == "sound" and args:
                return f"sound:{int(args[0])}"
            if k == "sound_seq" and args:
                seq = args[0]
                n = len(seq) if isinstance(seq, (list, tuple)) else 0
                return f"sound_seq:{n}"
            if k.startswith("fire"):
                return k
        except Exception:
            return str(k)
        return str(k)

    def _rng(self, bb: Blackboard, key: str, now: float) -> random.Random:
        seed = bb.get("rng_seed", None)
        c = int(bb.get(key, 0))
        bb[key] = c + 1
        return random.Random(hash((seed, key, c, int(now * 10))))

    def _allowed_to_start(self, bb: Blackboard, now: float) -> bool:
        next_t = float(bb.get(f"track_next:{self.track.name}", 0.0))
        return now >= next_t

    def _schedule_next(self, bb: Blackboard, now: float) -> None:
        bb[f"track_next:{self.track.name}"] = now + float(self.track.min_gap_s)

    def tick(self, ctx: Any, bb: Blackboard, mood: str, enable_fire: bool) -> None:
        now = float(getattr(ctx, "now", time.time()))
        cfg_all = bb.get("track_cfg")
        if isinstance(cfg_all, dict):
            cfg = cfg_all.get(self.track.name)
            if isinstance(cfg, dict):
                if "min_gap_s" in cfg:
                    self.track.min_gap_s = float(cfg["min_gap_s"])
                if "overlay_probability" in cfg:
                    self.track.overlay_probability = float(cfg["overlay_probability"])
        if self.active is not None:
            bb[f"stat:track_active:{self.track.name}"] = getattr(self.active.macro, "name", "")
            try:
                bb[f"stat:track_step:{self.track.name}"] = f"{int(self.active.i) + 1}/{len(self.active.macro.steps)}:{self._step_summary()}"
            except Exception:
                bb[f"stat:track_step:{self.track.name}"] = self._step_summary()
        else:
            bb[f"stat:track_active:{self.track.name}"] = ""
            bb[f"stat:track_step:{self.track.name}"] = ""
        if self.active is not None:
            fm = bb.get(f"force_macro:{self.track.name}")
            if fm and now < float(bb.get(f"force_macro_until:{self.track.name}", 0.0)) and self.track.name == "overlay":
                forced = str(fm)
                if forced and forced != getattr(self.active.macro, "name", None):
                    step_kind = None
                    try:
                        step_kind = self.active.macro.steps[self.active.i].kind
                    except Exception:
                        step_kind = None
                    if step_kind in ("sleep", "utter", "led", "expression", "stop"):
                        try:
                            self.active.abort(bb)
                        except Exception:
                            pass
                        self.active = None
            if self.active is not None:
                done = self.active.tick(ctx, bb)
                if done:
                    self.active = None
                    self._schedule_next(bb, now)
                return

        if not self._allowed_to_start(bb, now):
            return
        if not self.macros:
            self._schedule_next(bb, now)
            return

        fm = bb.get(f"force_macro:{self.track.name}")
        if fm and now < float(bb.get(f"force_macro_until:{self.track.name}", 0.0)):
            name = str(fm)
            chosen = None
            for m in self.macros:
                if m.name == name:
                    chosen = m
                    break
            if chosen is not None:
                cd_until = float(bb.get(f"cd:{chosen.name}", 0.0))
                if now >= cd_until:
                    uses = int(bb.get(f"force_macro_uses:{self.track.name}", 1))
                    uses -= 1
                    if uses <= 0:
                        bb.pop(f"force_macro:{self.track.name}", None)
                        bb.pop(f"force_macro_until:{self.track.name}", None)
                        bb.pop(f"force_macro_uses:{self.track.name}", None)
                    else:
                        bb[f"force_macro_uses:{self.track.name}"] = uses
                    bb[f"track_last_macro:{self.track.name}"] = chosen.name
                    bb[f"stat:track:{self.track.name}"] = int(bb.get(f"stat:track:{self.track.name}", 0)) + 1
                    print(f"[persona] track={self.track.name} macro={chosen.name} tags={','.join(chosen.tags)}")
                    self.active = MacroPlayer(chosen)
                    return
            else:
                bb.pop(f"force_macro:{self.track.name}", None)
                bb.pop(f"force_macro_until:{self.track.name}", None)
                bb.pop(f"force_macro_uses:{self.track.name}", None)

        rng = self._rng(bb, f"track_rng:{self.track.name}", now)
        if rng.random() > float(self.track.overlay_probability):
            self._schedule_next(bb, now)
            return

        local_bb = dict(bb)
        local_bb["track_name"] = str(self.track.name)
        local_bb["enable_fire"] = bool(enable_fire)
        fc = bb.get(f"force_cat:{self.track.name}")
        if fc:
            local_bb["force_cat"] = fc
            local_bb["force_cat_until"] = bb.get(f"force_cat_until:{self.track.name}", 0.0)
            local_bb["force_cat_uses"] = bb.get(f"force_cat_uses:{self.track.name}", 1)

        mood_to_use = self.track.pick_mood if self.track.pick_mood else mood
        chosen = pick_macro(self.macros, local_bb, mood=mood_to_use)
        for k, v in local_bb.items():
            if k.startswith("cd:") or k.endswith("_counter") or k.endswith("_t") or k.startswith("rng_"):
                bb[k] = v
            if k.startswith("stat:"):
                bb[k] = v
            if k.startswith("intent_") or k.startswith("recent_"):
                bb[k] = v
        if "force_cat" in local_bb or f"force_cat:{self.track.name}" in bb:
            if local_bb.get("force_cat"):
                bb[f"force_cat:{self.track.name}"] = local_bb.get("force_cat")
                bb[f"force_cat_until:{self.track.name}"] = float(local_bb.get("force_cat_until", 0.0))
                bb[f"force_cat_uses:{self.track.name}"] = int(local_bb.get("force_cat_uses", 1))
            else:
                bb.pop(f"force_cat:{self.track.name}", None)
                bb.pop(f"force_cat_until:{self.track.name}", None)
                bb.pop(f"force_cat_uses:{self.track.name}", None)

        bb[f"track_last_macro:{self.track.name}"] = chosen.name
        bb[f"stat:track:{self.track.name}"] = int(bb.get(f"stat:track:{self.track.name}", 0)) + 1
        print(f"[persona] track={self.track.name} macro={chosen.name} tags={','.join(chosen.tags)}")
        self.active = MacroPlayer(chosen)
        bb[f"stat:track_active:{self.track.name}"] = chosen.name
        bb[f"stat:track_step:{self.track.name}"] = f"1/{len(chosen.steps)}:{chosen.steps[0].kind}" if chosen.steps else ""


def build_default_tracks(all_macros: Sequence[Macro]) -> Tuple[TrackRunner, TrackRunner, TrackRunner]:
    locomotion = Track(
        name="locomotion",
        allowed_kinds={"expression", "drive", "cruise", "spin", "move", "stop", "sleep", "unstick"},
        required_tags={"adventure", "explore", "movement", "environment", "social", "random"},
        forbidden_tags={"fire"},
        min_gap_s=0.2,
        pick_mood=None,
        overlay_probability=1.0,
    )
    head = Track(
        name="head",
        allowed_kinds={"expression", "gimbal_to", "gimbal_center", "gimbal_sweep", "sleep"},
        required_tags={"look", "curiosity", "social", "environment"},
        forbidden_tags=set(),
        min_gap_s=0.3,
        pick_mood=None,
        overlay_probability=0.85,
    )
    overlay = Track(
        name="overlay",
        allowed_kinds={"expression", "led", "sound", "sound_seq", "utter", "sleep", "fire", "fire_burst", "fire_repeat", "audio", "audio_pick"},
        required_tags={"emotion", "idle", "talk", "show", "random", "social"},
        forbidden_tags=set(),
        min_gap_s=1.2,
        pick_mood=None,
        overlay_probability=0.55,
    )
    return TrackRunner(locomotion, all_macros), TrackRunner(head, all_macros), TrackRunner(overlay, all_macros)
