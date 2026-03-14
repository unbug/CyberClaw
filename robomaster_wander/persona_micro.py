import random
from typing import List, Tuple

try:
    from .persona_types import Macro, Step
except ImportError:
    from persona_types import Macro, Step


def _drive(name: str, x: float, y: float, z: float, dur: float, tags: Tuple[str, ...], weight: float = 0.8, cooldown_s: float = 0.6) -> Macro:
    steps = [Step("expression"), Step("drive", (dur, x, y, z)), Step("stop")]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _spin(name: str, deg: float, tags: Tuple[str, ...], weight: float = 0.7, cooldown_s: float = 1.2) -> Macro:
    steps = [Step("expression"), Step("spin", (deg, 140.0)), Step("stop")]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _look(name: str, yaw: float, tags: Tuple[str, ...], weight: float = 0.7, cooldown_s: float = 0.8) -> Macro:
    steps = [Step("expression"), Step("gimbal_to", (0.0, yaw)), Step("sleep", (0.15,)), Step("gimbal_center")]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _scan(name: str, dur: float, yaw: float, tags: Tuple[str, ...], weight: float = 0.8, cooldown_s: float = 1.2) -> Macro:
    steps = [Step("expression"), Step("gimbal_sweep", (dur, -abs(yaw), abs(yaw))), Step("gimbal_center")]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _idle(name: str, dur: float, tags: Tuple[str, ...], weight: float = 0.6, cooldown_s: float = 1.5) -> Macro:
    steps = [Step("expression"), Step("utter"), Step("sleep", (dur,))]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _song(name: str, seq: List[int], tags: Tuple[str, ...], weight: float = 0.55, cooldown_s: float = 14.0) -> Macro:
    steps = [Step("expression"), Step("sound_seq", (seq, 0.45)), Step("utter")]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)

def _audio_pick(name: str, audio_tags: Tuple[str, ...], dur_s, tags: Tuple[str, ...], weight: float = 0.25, cooldown_s: float = 2.0) -> Macro:
    steps = [Step("expression"), Step("audio_pick", (audio_tags, dur_s))]
    return Macro(name=name, steps=steps, tags=tags, weight=weight, cooldown_s=cooldown_s)


def _fire_show(name: str, tags: Tuple[str, ...], weight: float = 0.3, cooldown_s: float = 25.0) -> Macro:
    steps = [
        Step("expression"),
        Step("led", (255, 80, 80, "flash")),
        Step("sound_seq", ([7, 6, 7], 0.55)),
        Step("fire_repeat", (10, 0.18)),
        Step("sleep", (0.4,)),
        Step("led", (255, 255, 255, "on")),
    ]
    return Macro(name=name, steps=steps, tags=tags + ("fire",), weight=weight, cooldown_s=cooldown_s, allow_fire=True)


def build_micro_library(seed: int = 0) -> List[Macro]:
    rng = random.Random(seed)
    macros: List[Macro] = []

    macros += [
        _drive("move_forward", 0.26, 0.0, 0.0, 1.8, ("movement", "explore"), 1.2),
        _drive("move_backward", -0.22, 0.0, 0.0, 1.4, ("movement", "safety"), 0.9),
        _drive("turn_left", 0.0, 0.0, 90.0, 0.7, ("movement",), 0.6),
        _drive("turn_right", 0.0, 0.0, -90.0, 0.7, ("movement",), 0.6),
        _spin("spin", 360.0, ("movement", "emotion"), 0.55, 4.0),
        _spin("small_spin", 120.0, ("movement",), 0.6, 2.0),
        _drive("wiggle", 0.0, 0.0, 80.0, 0.35, ("movement", "emotion"), 0.7, 1.6),
        _drive("approach_target", 0.22, 0.0, 0.0, 1.2, ("explore", "curiosity"), 1.1),
        _drive("retreat", -0.22, 0.0, 0.0, 1.0, ("safety",), 0.8),
        _drive("circle_object", 0.18, 0.0, 24.0, 2.0, ("explore", "curiosity"), 0.9, 2.0),
        _drive("follow_wall", 0.16, 0.0, 14.0, 2.5, ("environment", "explore"), 0.8, 2.0),
        _drive("wander_random", 0.18, 0.0, 26.0, 2.0, ("explore",), 1.0, 1.5),
        _drive("wander_slow", 0.14, 0.0, 0.0, 3.0, ("explore", "idle"), 0.9, 2.0),
        _drive("wander_fast", 0.34, 0.0, 0.0, 1.6, ("explore", "emotion"), 0.8, 2.5),
        _idle("stop", 0.2, ("idle",), 0.4, 0.2),
        _drive("micro_adjust", 0.10, 0.0, 0.0, 0.35, ("movement",), 0.5, 0.8),
        _drive("move_arc", 0.20, 0.0, 18.0, 1.6, ("movement", "explore"), 0.9, 1.4),
        _drive("back_and_turn", -0.18, 0.0, 70.0, 1.2, ("safety",), 0.8, 2.0),
        _drive("escape_obstacle", -0.18, 0.0, 90.0, 1.2, ("safety", "environment"), 0.8, 3.0),
        _drive("patrol_route", 0.22, 0.0, 0.0, 3.5, ("explore",), 0.7, 3.0),
    ]

    macros += [
        _look("look_left", -35, ("look", "curiosity")),
        _look("look_right", 35, ("look", "curiosity")),
        _look("look_up", -5, ("look",)),
        _look("look_down", 5, ("look",)),
        _scan("scan_room", 3.0, 45, ("look", "curiosity"), 1.0, 3.0),
        _scan("double_look", 1.6, 25, ("look",), 0.7, 1.4),
        _scan("slow_scan", 4.0, 35, ("look", "idle"), 0.7, 2.4),
        _scan("quick_scan", 1.2, 55, ("look", "curiosity"), 0.9, 2.0),
        _look("look_back", 90, ("look", "curiosity")),
        _scan("look_at_object", 2.2, 20, ("look", "explore"), 0.8, 2.2),
        _scan("look_at_human", 2.2, 30, ("look", "social"), 0.8, 2.2),
        _look("head_tilt", 15, ("look", "emotion")),
        _scan("confused_look", 2.4, 30, ("look", "emotion"), 0.7, 3.0),
        _scan("focus_target", 1.6, 18, ("look", "curiosity"), 0.8, 2.0),
        _scan("peek", 1.8, 28, ("look", "curiosity", "environment"), 0.8, 2.5),
    ]

    macros += [
        _drive("explore_random", 0.20, 0.0, 16.0, 3.0, ("explore",), 1.1, 1.5),
        _drive("explore_new_area", 0.28, 0.0, 0.0, 4.0, ("explore", "curiosity"), 1.2, 1.8),
        _drive("explore_corner", 0.16, 0.0, 20.0, 2.8, ("explore", "environment"), 0.9, 2.5),
        _drive("explore_wall", 0.14, 0.0, 16.0, 3.0, ("explore", "environment"), 0.9, 2.5),
        _scan("explore_object", 3.0, 35, ("explore", "curiosity"), 0.9, 2.0),
        _song("investigate_sound", [2, 4, 2], ("explore", "curiosity"), 0.7, 8.0),
        _song("investigate_motion", [3, 3, 4], ("explore", "curiosity"), 0.7, 8.0),
        _song("investigate_light", [1, 2, 1], ("explore", "curiosity"), 0.6, 8.0),
        _drive("approach_unknown", 0.20, 0.0, 0.0, 2.0, ("explore", "curiosity"), 1.0, 1.6),
        _drive("circle_unknown", 0.18, 0.0, 26.0, 2.2, ("explore", "curiosity"), 0.9, 2.0),
        _scan("sniff_object", 2.0, 22, ("explore", "curiosity"), 0.7, 2.0),
        _drive("touch_object", 0.16, 0.0, 0.0, 1.0, ("explore", "environment"), 0.6, 3.0),
        _drive("follow_path", 0.24, 0.0, 0.0, 4.0, ("explore",), 1.0, 2.0),
        _scan("peek_around_corner", 2.5, 45, ("explore", "environment"), 0.8, 3.0),
        _drive("check_space", 0.20, 0.0, 0.0, 2.6, ("explore", "curiosity"), 0.8, 2.0),
    ]

    macros += [
        _song("greet_human", [1, 3, 5], ("social", "emotion"), 0.7, 10.0),
        _drive("approach_human", 0.18, 0.0, 0.0, 1.6, ("social",), 0.9, 2.0),
        _drive("follow_human", 0.20, 0.0, 0.0, 2.5, ("social",), 0.8, 2.0),
        _scan("look_at_face", 2.2, 22, ("social", "look"), 0.7, 2.0),
        _spin("happy_spin", 240.0, ("social", "emotion"), 0.6, 6.0),
        _drive("excited_wiggle", 0.0, 0.0, 120.0, 0.6, ("social", "emotion"), 0.7, 4.0),
        _song("call_for_attention", [6, 6, 7], ("social",), 0.7, 12.0),
        _drive("wave_motion", 0.0, 0.0, 80.0, 0.35, ("social",), 0.6, 2.0),
        _song("celebrate", [2, 4, 6, 7], ("social", "emotion"), 0.6, 14.0),
        _song("play_sound_happy", [2, 3, 4], ("social", "emotion"), 0.6, 10.0),
        _song("play_sound_call", [6, 7, 6], ("social",), 0.6, 10.0),
        _scan("show_curiosity", 2.6, 35, ("social", "curiosity"), 0.7, 3.0),
        _scan("peek_human", 1.8, 25, ("social", "curiosity"), 0.7, 3.0),
        _drive("shy_backoff", -0.14, 0.0, 35.0, 1.8, ("social", "emotion"), 0.6, 6.0),
        _drive("slow_approach", 0.12, 0.0, 0.0, 2.8, ("social",), 0.7, 2.0),
        _drive("jump_back", -0.22, 0.0, 0.0, 0.7, ("social", "emotion"), 0.7, 4.0),
        _idle("attention_pose", 0.8, ("social",), 0.5, 4.0),
        _spin("friendly_spin", 180.0, ("social",), 0.6, 6.0),
        _scan("gaze_follow", 2.4, 40, ("social", "look"), 0.7, 3.0),
        _idle("wait_for_response", 1.4, ("social",), 0.4, 4.0),
    ]

    macros += [
        _spin("happy_dance", 240.0, ("emotion", "dance"), 0.5, 10.0),
        _spin("excited_spin", 360.0, ("emotion",), 0.5, 12.0),
        _scan("curious_scan", 3.0, 45, ("emotion", "look"), 0.7, 4.0),
        _drive("bored_wander", 0.12, 0.0, 14.0, 3.5, ("emotion", "explore"), 0.8, 3.0),
        _drive("sleepy_slow_move", 0.10, 0.0, 0.0, 4.0, ("emotion", "idle"), 0.5, 6.0),
        _idle("sad_idle", 2.5, ("emotion", "idle"), 0.4, 6.0),
        _spin("confused_spin", 150.0, ("emotion",), 0.5, 8.0),
        _drive("frustrated_move", 0.0, 0.0, 140.0, 0.8, ("emotion",), 0.5, 8.0),
        _idle("relaxed_idle", 2.0, ("emotion", "idle"), 0.5, 4.0),
        _idle("proud_pose", 1.2, ("emotion",), 0.4, 8.0),
        _drive("surprised_jump", -0.18, 0.0, 80.0, 0.5, ("emotion",), 0.5, 8.0),
        _drive("timid_step_back", -0.12, 0.0, 35.0, 1.2, ("emotion",), 0.5, 8.0),
        _drive("playful_circle", 0.20, 0.0, 28.0, 2.2, ("emotion", "explore"), 0.6, 6.0),
        _drive("lazy_move", 0.10, 0.0, 0.0, 2.5, ("emotion", "idle"), 0.4, 6.0),
        _spin("celebration_spin", 300.0, ("emotion", "social"), 0.5, 10.0),
    ]

    macros += [
        _scan("idle_look_around", 3.0, 35, ("idle", "look"), 0.8, 2.8),
        _spin("idle_spin_small", 90.0, ("idle",), 0.5, 5.0),
        _scan("idle_scan", 2.2, 30, ("idle", "look"), 0.6, 3.0),
        _drive("idle_random_move", 0.11, 0.0, 16.0, 2.0, ("idle", "random"), 0.6, 2.5),
        _look("idle_head_tilt", 12, ("idle", "look"), 0.5, 2.0),
        _idle("idle_stop_and_watch", 2.0, ("idle",), 0.6, 3.0),
        _scan("idle_peek", 1.8, 28, ("idle", "look"), 0.5, 3.0),
        _drive("idle_micro_move", 0.10, 0.0, 0.0, 0.5, ("idle",), 0.5, 1.4),
        _idle("idle_wait", 1.2, ("idle",), 0.5, 2.0),
        _song("idle_listen", [1, 1, 2], ("idle", "look"), 0.45, 10.0),
        _drive("idle_wiggle", 0.0, 0.0, 80.0, 0.35, ("idle",), 0.5, 2.0),
        _drive("idle_slow_circle", 0.12, 0.0, 12.0, 3.0, ("idle", "explore"), 0.5, 4.0),
        _scan("idle_curiosity", 2.4, 35, ("idle", "curiosity"), 0.6, 4.0),
        _idle("idle_fake_sleep", 3.5, ("idle", "sleep"), 0.35, 10.0),
        _song("idle_random_sound", [rng.randint(1, 7) for _ in range(5)], ("idle", "random"), 0.4, 12.0),
    ]

    macros += [
        _drive("avoid_obstacle", -0.16, 0.0, 65.0, 1.0, ("environment", "safety"), 0.6, 3.0),
        _drive("approach_wall", 0.14, 0.0, 0.0, 1.8, ("environment",), 0.5, 4.0),
        _drive("follow_edge", 0.14, 0.0, 12.0, 3.0, ("environment", "explore"), 0.6, 3.0),
        _drive("escape_trap", -0.18, 0.0, 110.0, 1.2, ("environment", "safety"), 0.5, 6.0),
        _drive("find_open_space", 0.26, 0.0, 0.0, 4.0, ("environment", "explore"), 0.8, 3.0),
        _drive("navigate_door", 0.22, 0.0, 0.0, 3.0, ("environment", "explore"), 0.6, 6.0),
        _scan("check_corner", 2.6, 45, ("environment", "look"), 0.6, 4.0),
        _drive("circle_chair", 0.18, 0.0, 22.0, 2.4, ("environment", "explore"), 0.6, 5.0),
        _drive("explore_table", 0.16, 0.0, 16.0, 2.8, ("environment", "explore"), 0.6, 6.0),
        _scan("check_shadow", 2.2, 30, ("environment", "look"), 0.5, 6.0),
    ]

    macros += [
        _spin("random_spin", rng.choice([90, 120, 180, 240]), ("random",), 0.5, 2.0),
        _drive("random_jump", -0.22, 0.0, 80.0, 0.5, ("random", "emotion"), 0.5, 4.0),
        _song("random_sound", [rng.randint(1, 7) for _ in range(3)], ("random",), 0.5, 6.0),
        _idle("random_pause", 0.9, ("random", "idle"), 0.4, 1.5),
        _drive("random_turn", 0.0, 0.0, rng.choice([120, -120]), 0.5, ("random",), 0.5, 2.0),
        _scan("random_scan", 1.6, rng.choice([25, 35, 45]), ("random", "look"), 0.5, 2.0),
        _drive("random_dash", 0.38, 0.0, 0.0, 0.6, ("random", "explore"), 0.4, 6.0),
        _drive("random_shake", 0.0, 0.0, 160.0, 0.4, ("random",), 0.4, 3.0),
        _idle("random_stop", 0.4, ("random",), 0.4, 1.0),
        _drive("random_wiggle", 0.0, 0.0, 120.0, 0.35, ("random",), 0.4, 2.0),
    ]

    macros += [
        _idle("go_charge", 2.0, ("energy",), 0.2, 60.0),
        _idle("seek_dock", 1.5, ("energy",), 0.2, 40.0),
        _drive("low_energy_move", 0.10, 0.0, 0.0, 3.5, ("energy", "idle"), 0.3, 8.0),
        _idle("sleep", 4.0, ("energy", "sleep"), 0.3, 10.0),
        _song("wake_up", [1, 2, 3], ("energy",), 0.3, 10.0),
        _drive("stretch_move", 0.0, 0.0, 120.0, 0.6, ("energy",), 0.3, 10.0),
        _drive("slow_walk", 0.12, 0.0, 0.0, 4.0, ("energy", "idle"), 0.3, 6.0),
        _idle("rest_idle", 2.5, ("energy", "idle"), 0.3, 6.0),
        _idle("power_save_mode", 2.0, ("energy", "context"), 0.2, 20.0),
        _idle("energy_recover", 2.0, ("energy", "idle"), 0.2, 15.0),
    ]

    macros += [
        _idle("night_mode", 2.0, ("context", "idle"), 0.2, 20.0),
        _song("morning_wake", [1, 2, 4, 6], ("context", "energy"), 0.2, 30.0),
        _drive("evening_wander", 0.14, 0.0, 15.0, 4.0, ("context", "explore"), 0.3, 10.0),
        _idle("rainy_day_idle", 3.0, ("context", "idle"), 0.2, 20.0),
        _idle("quiet_mode", 2.0, ("context", "idle"), 0.2, 20.0),
        _song("party_mode", [6, 7, 6, 7, 6], ("context", "show"), 0.2, 30.0),
        _drive("exploration_mode", 0.26, 0.0, 0.0, 5.0, ("context", "explore"), 0.3, 12.0),
        _drive("guard_mode", 0.0, 0.0, 90.0, 1.5, ("context", "look"), 0.2, 15.0),
        _drive("play_mode", 0.22, 0.0, 32.0, 3.0, ("context", "explore"), 0.3, 12.0),
        _idle("study_mode", 2.0, ("context", "idle"), 0.2, 20.0),
    ]

    macros += [
        _fire_show("fire_show", ("show", "emotion"), 0.25, 30.0),
        _fire_show("celebrate_fire", ("show", "social"), 0.22, 35.0),
    ]

    macros += [
        Macro(
            name="unstick_sound",
            steps=[
                Step("expression"),
                Step("audio_pick", (("hurt", "yelp", "grunt"), 0.9)),
            ],
            tags=("emotion", "idle", "show"),
            weight=0.0,
            cooldown_s=1.0,
        ),
        Macro(
            name="frustration_fire",
            steps=[
                Step("expression"),
                Step("led", (255, 40, 40, "flash")),
                Step("audio_pick", (("grunt", "bark", "hurt", "yelp"), 1.0)),
                Step("sleep", (0.1,)),
                Step("fire_repeat", (4, 0.18)),
                Step("sleep", (0.2,)),
                Step("led", (255, 255, 255, "on")),
            ],
            tags=("show", "emotion"),
            weight=0.0,
            cooldown_s=18.0,
            allow_fire=True,
        ),
        _audio_pick("dog_sync_audio", "audio_tags", "audio_target_s", ("emotion", "voice"), 0.28, 0.6),
        _audio_pick("voice_hi", ("bark", "cute"), 1.2, ("talk", "voice", "social"), 0.22, 8.0),
        _audio_pick("voice_huh", ("cute", "ooh"), 0.9, ("talk", "voice", "emotion"), 0.20, 8.0),
        _audio_pick("voice_here", ("bark",), 1.3, ("talk", "voice", "social"), 0.18, 10.0),
        _audio_pick("voice_look", ("sniff", "ooh", "cute"), 1.2, ("talk", "voice", "curiosity"), 0.18, 10.0),
        _audio_pick("voice_good", ("cute",), 1.0, ("talk", "voice", "social"), 0.16, 12.0),
        _audio_pick("voice_follow", ("bark", "grunt"), 1.5, ("talk", "voice", "social"), 0.18, 10.0),
        _audio_pick("voice_sniff", ("sniff",), 1.1, ("talk", "voice", "curiosity"), 0.18, 10.0),
        _audio_pick("voice_pet", ("cute", "breath"), 1.2, ("talk", "voice", "social"), 0.16, 12.0),
        _audio_pick("puppy_yelp", ("hurt", "yelp"), 0.8, ("talk", "voice", "emotion"), 0.12, 10.0),
        _audio_pick("puppy_snore", ("snore",), 2.6, ("talk", "voice", "idle"), 0.08, 18.0),
        _audio_pick("puppy_grumble", ("grunt",), 0.9, ("talk", "voice", "emotion"), 0.10, 10.0),
        _audio_pick("puppy_weird", ("weird", "troll", "misc"), 1.1, ("talk", "voice", "mischief"), 0.08, 14.0),
    ]

    return macros
