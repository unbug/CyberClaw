import json
import os
import random
import wave
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class AudioClip:
    rel_path: str
    dur_s: float
    tags: Tuple[str, ...]


_CACHE: Optional[List[AudioClip]] = None


def _infer_tags(name: str) -> Tuple[str, ...]:
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    folder = os.path.normpath(str(name)).lower().replace("\\", "/")
    if "assets/audio/minionish_goblins_slow_wav/" in folder:
        return ("minion", "goblin", "voice", "idle", "sleepy")
    if "assets/audio/minionish_goblins_wav/" in folder:
        return ("minion", "goblin", "voice", "cute", "mischief")
    if "assets/audio/minionish_robot_voice_pack_wav/" in folder:
        if stem in ("ouch", "thathurt"):
            return ("minion", "robot", "voice", "hurt")
        if stem.endswith("down") or stem in ("one more down", "onemoredown"):
            return ("minion", "robot", "voice", "emotion")
        if "backup" in stem:
            return ("minion", "robot", "voice", "social")
        if stem.startswith("target"):
            return ("minion", "robot", "voice", "look")
        return ("minion", "robot", "voice", "social")
    if "assets/audio/minionish_voiceover_fighter_wav/" in folder:
        if stem in ("game_over", "you_lose", "mission_failed", "wrong"):
            return ("minion", "announcer", "voice", "emotion")
        if stem in ("you_win", "mission_completed", "objective_achieved", "congratulations", "correct"):
            return ("minion", "announcer", "voice", "social")
        if stem.startswith("war_"):
            return ("minion", "announcer", "voice", "mischief")
        return ("minion", "announcer", "voice", "show")
    if stem.startswith("barking_"):
        return ("bark", "voice", "social")
    if stem.startswith("cute_"):
        return ("cute", "voice", "social")
    if stem == "howl":
        return ("howl", "voice", "emotion")
    if stem == "snore" or stem.startswith("snore_"):
        return ("snore", "sleep", "idle")
    if stem == "nose":
        return ("sniff", "curiosity", "explore")
    if stem.startswith("hurt_"):
        return ("yelp", "hurt", "scared")
    if stem.startswith("grunt_"):
        return ("grunt", "emotion")
    if stem == "breath" or stem.startswith("breath_"):
        return ("breath", "idle")
    if stem.startswith("eat_"):
        return ("eat", "idle")
    if stem.startswith("cough_"):
        return ("cough", "weird")
    if stem.startswith("burp_"):
        return ("burp", "weird")
    if stem.startswith("burble_"):
        return ("burble", "weird")
    if stem.startswith("spit_"):
        return ("spit", "weird")
    if stem.startswith("misc_"):
        return ("misc", "weird")
    if stem.startswith("weird_"):
        return ("weird", "mischief")
    if stem.startswith("troll_"):
        return ("troll", "mischief")
    if stem.startswith("monster_") or stem.startswith("roar_") or stem.startswith("scream_"):
        return ("monster", "mischief")
    if stem.startswith("slime_"):
        return ("slime", "mischief")
    if stem.startswith("alien_") or stem.startswith("bug_"):
        return ("alien", "mischief")
    if stem.startswith("attack_"):
        return ("attack", "mischief")
    if stem.startswith("die_"):
        return ("die", "hurt", "scared")
    if stem.startswith("human_"):
        return ("human", "voice", "social")
    if stem.startswith("stomp_"):
        return ("stomp", "movement")
    if stem == "ooh":
        return ("ooh", "curiosity")
    return ("any",)


def _durations_from_json(dir_path: str) -> Dict[str, float]:
    p = os.path.join(dir_path, "_durations.json")
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        out: Dict[str, float] = {}
        if isinstance(data, dict):
            for k, v in data.items():
                try:
                    out[str(k)] = float(v)
                except Exception:
                    continue
        return out
    except Exception:
        return {}


def _wav_duration(path: str) -> float:
    with wave.open(path, "rb") as wf:
        sr = float(wf.getframerate())
        n = float(wf.getnframes())
        if sr <= 0.0:
            return 0.0
        return n / sr


def load_default_catalog() -> List[AudioClip]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    clips: List[AudioClip] = []

    roots: List[Tuple[str, str]] = [
        ("oga_cc0_creature_sfx_wav", os.path.join("assets", "audio", "oga_cc0_creature_sfx_wav")),
        ("minionish_goblins_wav", os.path.join("assets", "audio", "minionish_goblins_wav")),
        ("minionish_goblins_slow_wav", os.path.join("assets", "audio", "minionish_goblins_slow_wav")),
        ("minionish_robot_voice_pack_wav", os.path.join("assets", "audio", "minionish_robot_voice_pack_wav")),
        ("minionish_voiceover_fighter_wav", os.path.join("assets", "audio", "minionish_voiceover_fighter_wav")),
    ]

    for dir_name, rel_prefix in roots:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "audio", dir_name))
        durations = _durations_from_json(base_dir)
        if not os.path.isdir(base_dir):
            continue
        for fn in sorted(os.listdir(base_dir)):
            if not fn.lower().endswith(".wav"):
                continue
            if fn.startswith("_"):
                continue
            rel = os.path.join(rel_prefix, fn)
            abs_path = os.path.join(base_dir, fn)
            dur = durations.get(fn)
            if dur is None:
                try:
                    dur = _wav_duration(abs_path)
                except Exception:
                    continue
            tags = _infer_tags(rel)
            clips.append(AudioClip(rel_path=rel, dur_s=float(dur), tags=tags))
    _CACHE = clips
    return clips


def pick_clip(tags: Sequence[str], target_s: float, rng: random.Random, exclude_rel_paths: Optional[Sequence[str]] = None) -> Optional[AudioClip]:
    want: Set[str] = {str(t).lower() for t in (tags or []) if t}
    clips = load_default_catalog()
    if not clips:
        return None
    exclude: Set[str] = set()
    if exclude_rel_paths:
        for p in exclude_rel_paths:
            if not p:
                continue
            exclude.add(str(p))

    def _matches(c: AudioClip) -> bool:
        if (not want) or ("any" in want):
            return True
        return bool(want.intersection({t.lower() for t in c.tags}))

    strict: List[AudioClip]
    if (not want) or ("any" in want):
        strict = clips
    else:
        strict = [c for c in clips if _matches(c)]
        if not strict:
            strict = clips

    pool = [c for c in strict if c.rel_path not in exclude]
    if not pool:
        pool = strict
    ts = max(0.05, float(target_s))
    scored: List[Tuple[float, AudioClip]] = []
    for c in pool:
        d = abs(float(c.dur_s) - ts)
        scored.append((d, c))
    scored.sort(key=lambda x: x[0])
    top = scored[: min(20, len(scored))]
    return rng.choice([c for _d, c in top])
