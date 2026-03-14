import time
from typing import Any, Dict


Blackboard = Dict[str, Any]


class AutoOptimizer:
    def __init__(self):
        self._last_t = 0.0
        self._last_avoid = 0
        self._last_overlay = 0
        self._last_loco = 0
        self._last_head = 0

    def tick(self, ctx: Any, bb: Blackboard) -> None:
        cfg = bb.get("autotune")
        if not isinstance(cfg, dict) or not bool(cfg.get("enabled", False)):
            return

        now = float(getattr(ctx, "now", time.time()))
        interval_s = float(cfg.get("interval_s", 15.0))
        if (now - self._last_t) < interval_s:
            return
        self._last_t = now

        avoid = int(bb.get("stat:avoid_events", 0))
        overlay = int(bb.get("stat:track:overlay", 0))
        loco = int(bb.get("stat:track:locomotion", 0))
        head = int(bb.get("stat:track:head", 0))
        d_avoid = avoid - self._last_avoid
        d_overlay = overlay - self._last_overlay
        d_loco = loco - self._last_loco
        d_head = head - self._last_head
        self._last_avoid = avoid
        self._last_overlay = overlay
        self._last_loco = loco
        self._last_head = head

        per_min = 60.0 / max(1e-6, interval_s)
        avoid_per_min = d_avoid * per_min
        overlay_per_min = d_overlay * per_min

        target_avoid = float(cfg.get("target_avoid_per_min", 6.0))
        target_overlay = float(cfg.get("target_overlay_per_min", 8.0))

        if avoid_per_min > target_avoid:
            danger_dist = float(bb.get("danger_dist_m", 0.55))
            danger_visual = float(bb.get("danger_visual_m", 0.85))
            scared_dist = float(bb.get("scared_dist_m", 0.45))
            danger_dist = max(0.40, danger_dist - 0.03)
            danger_visual = max(0.55, danger_visual - 0.05)
            scared_dist = max(0.30, scared_dist - 0.02)
            bb["danger_dist_m"] = danger_dist
            bb["danger_visual_m"] = danger_visual
            bb["scared_dist_m"] = scared_dist

        if overlay_per_min < target_overlay and d_loco > 0:
            track_cfg = bb.get("track_cfg")
            if not isinstance(track_cfg, dict):
                track_cfg = {}
            overlay_cfg = track_cfg.get("overlay")
            if not isinstance(overlay_cfg, dict):
                overlay_cfg = {}
            p = float(overlay_cfg.get("overlay_probability", bb.get("overlay_probability_default", 0.35)))
            p = min(0.75, p + 0.05)
            overlay_cfg["overlay_probability"] = p
            track_cfg["overlay"] = overlay_cfg
            bb["track_cfg"] = track_cfg

        bb["stat:autotune_last"] = {
            "t": now,
            "interval_s": interval_s,
            "d": {"avoid": d_avoid, "overlay": d_overlay, "loco": d_loco, "head": d_head},
            "per_min": {"avoid": avoid_per_min, "overlay": overlay_per_min},
            "thresholds": {"danger_dist_m": bb.get("danger_dist_m"), "danger_visual_m": bb.get("danger_visual_m"), "scared_dist_m": bb.get("scared_dist_m")},
            "overlay_probability": bb.get("track_cfg", {}).get("overlay", {}).get("overlay_probability") if isinstance(bb.get("track_cfg"), dict) else None,
        }
        danger_dist_v = float(bb.get("danger_dist_m", 0.55))
        danger_visual_v = float(bb.get("danger_visual_m", 0.85))
        scared_dist_v = float(bb.get("scared_dist_m", 0.45))
        print(f"[auto] avoid/m={avoid_per_min:.1f} overlay/m={overlay_per_min:.1f} danger={danger_dist_v:.2f}/{danger_visual_v:.2f} scared={scared_dist_v:.2f}")
