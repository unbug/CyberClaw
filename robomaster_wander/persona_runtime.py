import math
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


Blackboard = Dict[str, Any]


@dataclass
class PersonaCtx:
    patrol: Any
    now: float
    pose: Tuple[float, float, float]
    dist: Optional[float]
    dist_t: float
    pos_t: float
    gyaw: float
    battery_pct: Optional[int] = None
    battery_t: float = 0.0


def bb_get(bb: Blackboard, key: str, default: Any) -> Any:
    v = bb.get(key, default)
    return default if v is None else v


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def mood_color(mood: str) -> Tuple[int, int, int]:
    if mood == "happy":
        return 255, 220, 80
    if mood == "curious":
        return 80, 200, 255
    if mood == "mischief":
        return 255, 60, 120
    if mood == "sleepy":
        return 80, 80, 255
    if mood == "angry":
        return 255, 40, 40
    if mood == "sad":
        return 80, 120, 255
    if mood == "scared":
        return 255, 140, 0
    return 255, 255, 255


def set_mood(bb: Blackboard, mood: str, intensity: float = 0.6) -> None:
    bb["mood"] = mood
    bb["mood_intensity"] = clamp(float(intensity), 0.0, 1.0)


def update_affect(ctx: PersonaCtx, bb: Blackboard) -> None:
    mood = bb_get(bb, "mood", "curious")
    energy = float(bb_get(bb, "energy", 0.8))
    last_novelty = float(bb_get(bb, "last_novelty_t", ctx.now))
    last_t = float(bb.get("last_affect_t", ctx.now))
    dt = max(0.0, float(ctx.now - last_t))
    bb["last_affect_t"] = ctx.now

    vision = getattr(ctx.patrol, "vision_data", None)
    persons = []
    if isinstance(vision, dict):
        persons = vision.get("person") or []
    person_seen = bool(persons)
    bb["person_seen"] = bool(person_seen)
    if person_seen:
        bb["last_person_t"] = ctx.now

    boredom = float(bb_get(bb, "need_boredom", 0.2))
    curiosity = float(bb_get(bb, "need_curiosity", 0.4))
    social = float(bb_get(bb, "need_social", 0.35))
    play = float(bb_get(bb, "need_play", 0.35))
    boredom_up = float(bb.get("need_boredom_up_per_s", 0.004))
    curiosity_up = float(bb.get("need_curiosity_up_per_s", 0.003))
    social_up = float(bb.get("need_social_up_per_s", 0.0025))
    play_up = float(bb.get("need_play_up_per_s", 0.0018))
    social_boost = float(bb.get("need_social_boost_on_person", 0.18))
    novelty_boost = float(bb.get("need_novelty_boost_on_person", 0.12))

    boredom = clamp(boredom + boredom_up * dt, 0.0, 1.0)
    curiosity = clamp(curiosity + curiosity_up * dt, 0.0, 1.0)
    social = clamp(social + social_up * dt, 0.0, 1.0)
    play = clamp(play + play_up * dt, 0.0, 1.0)
    if person_seen:
        social = clamp(social + social_boost, 0.0, 1.0)
        boredom = clamp(boredom - novelty_boost, 0.0, 1.0)
        play = clamp(play + 0.16, 0.0, 1.0)
        bb["last_novelty_t"] = ctx.now

    bb["need_boredom"] = boredom
    bb["need_curiosity"] = curiosity
    bb["need_social"] = social
    bb["need_play"] = play

    last_cat = bb.get("stat:last_cat")
    last_cat_t = float(bb.get("stat:last_cat_t", 0.0))
    if (ctx.now - last_cat_t) < 7.0:
        if last_cat in ("explore", "environment", "adventure", "movement"):
            boredom = clamp(boredom - 0.14, 0.0, 1.0)
            curiosity = clamp(curiosity - 0.06, 0.0, 1.0)
        elif last_cat in ("social", "look", "talk"):
            social = clamp(social - 0.12, 0.0, 1.0)
            curiosity = clamp(curiosity - 0.04, 0.0, 1.0)
        elif last_cat in ("show", "dance", "prank"):
            play = clamp(play - 0.22, 0.0, 1.0)
            social = clamp(social - 0.10, 0.0, 1.0)
        elif last_cat in ("idle", "energy"):
            boredom = clamp(boredom + 0.06, 0.0, 1.0)
        bb["need_boredom"] = boredom
        bb["need_curiosity"] = curiosity
        bb["need_social"] = social
        bb["need_play"] = play

    if getattr(ctx.patrol, "hit_detected", False):
        set_mood(bb, "angry", 0.9)
        bb["last_novelty_t"] = ctx.now
    elif ctx.dist is not None and ctx.dist < float(bb.get("scared_dist_m", 0.45)):
        if mood != "scared":
            set_mood(bb, "scared", 0.7)
        bb["last_novelty_t"] = ctx.now
    elif person_seen and mood not in ("scared", "angry"):
        last_happy = float(bb.get("last_happy_t", 0.0))
        if (ctx.now - last_happy) > 3.0:
            set_mood(bb, "happy", 0.65)
            bb["last_happy_t"] = ctx.now
    elif (ctx.now - last_novelty) > 90.0:
        if energy < 0.35:
            set_mood(bb, "sleepy", 0.7)
        else:
            set_mood(bb, "mischief", 0.6)
            bb["last_novelty_t"] = ctx.now

    energy = clamp(energy - 0.0025 * dt, 0.0, 1.0)
    bb["energy"] = energy

    dist = bb.get("dist", None)
    try:
        dist_v = float(dist) if dist is not None else None
    except Exception:
        dist_v = None

    base = {
        "adventure": 0.22,
        "explore": 0.18,
        "look": 0.10,
        "social": 0.12,
        "idle": 0.08,
        "emotion": 0.05,
        "random": 0.03,
        "movement": 0.03,
        "environment": 0.03,
        "show": 0.04,
        "prank": 0.02,
        "dance": 0.03,
        "talk": 0.04,
        "energy": 0.01,
        "context": 0.00,
    }
    base["explore"] += 0.18 * boredom
    base["adventure"] += 0.10 * boredom
    base["look"] += 0.14 * curiosity
    base["social"] += 0.18 * social
    base["show"] += 0.10 * play
    base["dance"] += 0.06 * play
    base["idle"] += 0.22 * clamp(1.0 - energy, 0.0, 1.0)
    if person_seen:
        base["social"] += 0.22
        base["look"] += 0.10
        base["talk"] += 0.05
        bb["social_mode_until"] = max(float(bb.get("social_mode_until", 0.0)), ctx.now + 6.0)
    if ctx.now < float(bb.get("social_mode_until", 0.0)):
        base["social"] += 0.18
        base["look"] += 0.08
    if mood == "scared" or (dist_v is not None and dist_v < 0.35):
        base["adventure"] *= 0.55
        base["social"] *= 0.45
        base["show"] *= 0.15
        base["prank"] *= 0.10
        base["dance"] *= 0.10
        base["explore"] += 0.08
        base["environment"] += 0.10

    bb["cat_weights_override"] = base


def choose_utterance(mood: str, rng: random.Random) -> str:
    lines: Dict[str, List[str]] = {
        "happy": ["汪！好开心～", "尾巴摇起来！", "我们去玩！", "耶～我超乖！"],
        "curious": ["汪？那是什么？", "我去闻闻～", "咦…有点意思", "让我看看嘛～"],
        "mischief": ["汪汪！我来啦～", "嘿嘿～偷偷转一圈", "别抓我！我会装乖～", "我要乱跑一下下！"],
        "sleepy": ["呜…我困了", "先趴一会儿…", "呼…", "再睡一下下…"],
        "angry": ["汪！别碰我！", "谁推我！", "我不高兴了！", "哼！保持距离！"],
        "sad": ["呜呜…", "我有点委屈", "要抱抱…", "不想动了…"],
        "scared": ["汪！吓到我了！", "我退后一点…", "别靠太近！", "我躲一下…"],
    }
    pool = lines.get(mood, ["…"])
    return rng.choice(pool)


def apply_expression(ctx: PersonaCtx, bb: Blackboard) -> None:
    mood = bb_get(bb, "mood", "curious")
    r, g, b = mood_color(str(mood))
    last_t = float(bb.get("last_expression_t", 0.0))
    if (ctx.now - last_t) < 1.5:
        return
    bb["last_expression_t"] = ctx.now
    try:
        ctx.patrol.robot.led.set_led(comp="all", r=int(r), g=int(g), b=int(b), effect="on")
    except Exception:
        pass


def safe_stop(ctx: PersonaCtx) -> None:
    try:
        ctx.patrol.chassis.drive_speed(x=0, y=0, z=0)
    except Exception:
        pass


def estimate_forward_obstacle(ctx: PersonaCtx) -> Optional[float]:
    best = None
    try:
        obs = ctx.patrol._visual_obstacles_snapshot()
        for oa, od in obs:
            if od is None:
                continue
            if abs(oa) <= math.radians(15):
                best = od if best is None else min(best, od)
    except Exception:
        pass
    return best
