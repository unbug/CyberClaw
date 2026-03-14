import json
import os
import random
import wave
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass(frozen=True)
class AudioClip:
    rel_path: str
    dur_s: float
    tags: Tuple[str, ...]


_CACHE: Optional[List[AudioClip]] = None


def _infer_tags(name: str) -> Tuple[str, ...]:
    stem = os.path.splitext(os.path.basename(name))[0].lower()
    if stem.startswith("barking_"):
        return ("bark", "voice", "social")
    if stem.startswith("cute_"):
        return ("cute", "voice", "social")
    if stem == "howl":
        return ("howl", "voice", "emotion")
    if stem == "snore":
        return ("snore", "sleep", "idle")
    if stem == "nose":
        return ("sniff", "curiosity", "explore")
    if stem.startswith("hurt_"):
        return ("yelp", "hurt", "scared")
    if stem.startswith("grunt_"):
        return ("grunt", "emotion")
    if stem == "breath":
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
    if stem.startswith("alien_") or stem.startswith("bug_"):
        return ("alien", "mischief")
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
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets", "audio", "oga_cc0_creature_sfx_wav"))
    durations = _durations_from_json(base_dir)
    clips: List[AudioClip] = []
    if os.path.isdir(base_dir):
        for fn in sorted(os.listdir(base_dir)):
            if not fn.lower().endswith(".wav"):
                continue
            if fn.startswith("_"):
                continue
            rel = os.path.join("assets", "audio", "oga_cc0_creature_sfx_wav", fn)
            abs_path = os.path.join(base_dir, fn)
            dur = durations.get(fn)
            if dur is None:
                try:
                    dur = _wav_duration(abs_path)
                except Exception:
                    continue
            tags = _infer_tags(fn)
            clips.append(AudioClip(rel_path=rel, dur_s=float(dur), tags=tags))
    _CACHE = clips
    return clips


def pick_clip(tags: Sequence[str], target_s: float, rng: random.Random) -> Optional[AudioClip]:
    want: Set[str] = {str(t).lower() for t in (tags or []) if t}
    clips = load_default_catalog()
    if not clips:
        return None
    if not want or "any" in want:
        pool = clips
    else:
        pool = [c for c in clips if want.intersection({t.lower() for t in c.tags})]
        if not pool:
            pool = clips
    ts = max(0.05, float(target_s))
    scored: List[Tuple[float, AudioClip]] = []
    for c in pool:
        d = abs(float(c.dur_s) - ts)
        scored.append((d, c))
    scored.sort(key=lambda x: x[0])
    top = scored[: min(8, len(scored))]
    return rng.choice([c for _d, c in top])
