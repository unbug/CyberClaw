import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from robomaster_wander.tools.refresh_audio_assets import _fade, _normalize_i16, _read_wav_mono_i16, _write_wav_mono_i16


def _resample_linear_i16(frames: bytes, speed: float) -> bytes:
    speed = float(speed)
    if speed <= 0.01:
        raise ValueError("speed must be > 0")
    n = len(frames) // 2
    if n <= 2:
        return frames
    inp = memoryview(frames).cast("h")
    out_n = max(1, int(round(n / speed)))
    out = bytearray(out_n * 2)
    outv = memoryview(out).cast("h")
    for i in range(out_n):
        pos = i * speed
        j = int(pos)
        frac = pos - j
        if j >= n - 1:
            outv[i] = int(inp[n - 1])
            continue
        a = int(inp[j])
        b = int(inp[j + 1])
        outv[i] = int(round(a + (b - a) * frac))
    return bytes(out)


def _build_variant(src_dir: str, dst_dir: str, speed: float) -> None:
    os.makedirs(dst_dir, exist_ok=True)
    durations: dict = {}
    for fn in sorted(os.listdir(src_dir)):
        if not fn.lower().endswith(".wav"):
            continue
        if fn.startswith("_"):
            continue
        src = os.path.join(src_dir, fn)
        sr, frames = _read_wav_mono_i16(src)
        frames = _resample_linear_i16(frames, speed=speed)
        frames = _normalize_i16(frames, peak=0.92)
        frames = _fade(frames, sr=sr, fade_s=0.01)
        dst = os.path.join(dst_dir, fn)
        _write_wav_mono_i16(dst, sr=sr, frames=frames)
        durations[fn] = (len(frames) / 2) / float(sr)

    with open(os.path.join(dst_dir, "_durations.json"), "w", encoding="utf-8") as f:
        import json

        json.dump(durations, f, ensure_ascii=False, indent=2, sort_keys=True)


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cand = os.path.join(root, "assets", "audio", "_candidates")
    src_dir = os.path.join(cand, "minionish_goblins_wav")
    if not os.path.isdir(src_dir):
        raise RuntimeError(f"missing: {src_dir}")

    _build_variant(src_dir, os.path.join(cand, "minionish_goblins_fast_wav"), speed=1.25)
    _build_variant(src_dir, os.path.join(cand, "minionish_goblins_chip_wav"), speed=1.45)
    _build_variant(src_dir, os.path.join(cand, "minionish_goblins_slow_wav"), speed=0.85)
    print("ok")


if __name__ == "__main__":
    main()

