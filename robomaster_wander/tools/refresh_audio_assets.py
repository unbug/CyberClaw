import io
import json
import math
import os
import struct
import subprocess
import time
import urllib.parse
import urllib.request
import wave
import zipfile


def _http_get_bytes(url: str, timeout_s: float = 30.0, retries: int = 6) -> bytes:
    headers = {"User-Agent": "robomaster_wander (audio-fetch; +https://github.com/)"}
    last_err = None
    for i in range(max(1, int(retries))):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if int(getattr(e, "code", 0)) in (429, 503):
                ra = None
                try:
                    ra = e.headers.get("Retry-After")
                except Exception:
                    ra = None
                try:
                    wait_s = float(ra) if ra is not None else (1.0 + (i * 1.5))
                except Exception:
                    wait_s = 1.0 + (i * 1.5)
                wait_s = min(20.0, max(0.8, wait_s))
                time.sleep(wait_s)
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(min(10.0, 0.6 + i * 0.8))
    raise last_err if last_err is not None else RuntimeError("http get failed")


def _commons_api(params: dict) -> dict:
    base = "https://commons.wikimedia.org/w/api.php"
    qs = urllib.parse.urlencode(params)
    raw = _http_get_bytes(base + "?" + qs, timeout_s=30.0)
    return json.loads(raw.decode("utf-8"))


def _commons_file_url_and_meta(title: str) -> tuple[str, dict]:
    data = _commons_api(
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
        }
    )
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    iis = page.get("imageinfo") or []
    if not iis:
        raise RuntimeError(f"missing imageinfo for {title}")
    ii = iis[0]
    url = ii.get("url")
    meta = ii.get("extmetadata") or {}
    if not url:
        raise RuntimeError(f"missing url for {title}")
    return str(url), meta


def _afconvert_to_wav48k_mono(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@48000", "-c", "1", src, dst],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _read_wav_mono_i16(path: str) -> tuple[int, bytes]:
    with wave.open(path, "rb") as wf:
        if wf.getnchannels() != 1:
            raise RuntimeError(f"expected mono wav: {path}")
        if wf.getsampwidth() != 2:
            raise RuntimeError(f"expected 16-bit wav: {path}")
        sr = int(wf.getframerate())
        frames = wf.readframes(wf.getnframes())
        return sr, frames


def _write_wav_mono_i16(path: str, sr: int, frames: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(sr))
        wf.writeframes(frames)


def _normalize_i16(frames: bytes, peak: float = 0.92) -> bytes:
    if not frames:
        return frames
    n = len(frames) // 2
    vals = struct.unpack("<" + "h" * n, frames)
    mx = 1
    for v in vals:
        av = abs(int(v))
        if av > mx:
            mx = av
    target = int(max(1, min(32767, int(float(peak) * 32767))))
    if mx <= 1:
        return frames
    gain = target / float(mx)
    out = []
    for v in vals:
        vv = int(round(float(v) * gain))
        if vv > 32767:
            vv = 32767
        elif vv < -32768:
            vv = -32768
        out.append(vv)
    return struct.pack("<" + "h" * n, *out)


def _trim_or_pad(frames: bytes, sr: int, target_s: float) -> bytes:
    target_n = int(round(float(target_s) * float(sr)))
    cur_n = len(frames) // 2
    if cur_n == target_n:
        return frames
    if cur_n > target_n:
        return frames[: target_n * 2]
    return frames + (b"\x00\x00" * (target_n - cur_n))


def _fade(frames: bytes, sr: int, fade_s: float = 0.01) -> bytes:
    n = len(frames) // 2
    if n <= 2:
        return frames
    fade_n = int(round(float(fade_s) * float(sr)))
    fade_n = max(1, min(fade_n, n // 2))
    vals = list(struct.unpack("<" + "h" * n, frames))
    for i in range(fade_n):
        k = i / float(fade_n)
        vals[i] = int(round(vals[i] * k))
        vals[n - 1 - i] = int(round(vals[n - 1 - i] * k))
    return struct.pack("<" + "h" * n, *vals)


def _process_to_target(src_any: str, dst_wav: str, target_s: float) -> None:
    tmp_wav = dst_wav + ".tmp.wav"
    _afconvert_to_wav48k_mono(src_any, tmp_wav)
    sr, frames = _read_wav_mono_i16(tmp_wav)
    frames = _normalize_i16(frames, peak=0.92)
    frames = _trim_or_pad(frames, sr=sr, target_s=target_s)
    frames = _fade(frames, sr=sr, fade_s=0.01)
    _write_wav_mono_i16(dst_wav, sr=sr, frames=frames)
    try:
        os.remove(tmp_wav)
    except Exception:
        pass


def _process_keep_duration(src_any: str, dst_wav: str) -> float:
    tmp_wav = dst_wav + ".tmp.wav"
    _afconvert_to_wav48k_mono(src_any, tmp_wav)
    sr, frames = _read_wav_mono_i16(tmp_wav)
    frames = _normalize_i16(frames, peak=0.92)
    frames = _fade(frames, sr=sr, fade_s=0.01)
    _write_wav_mono_i16(dst_wav, sr=sr, frames=frames)
    try:
        os.remove(tmp_wav)
    except Exception:
        pass
    return (len(frames) / 2) / float(sr)


def _download_to_tmp(url: str, tmp_dir: str, filename: str) -> str:
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, filename)
    data = _http_get_bytes(url, timeout_s=60.0)
    with open(path, "wb") as f:
        f.write(data)
    return path


def _extract_zip(zip_bytes: bytes, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(out_dir)


def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "assets", "audio")
    tmp_dir = os.path.join(root, "assets", "audio", "_tmp")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    attrib_lines = ["音频来源与许可记录", ""]

    dog_zip_url = "https://opengameart.org/sites/default/files/80-CC0-creature-SFX_0.zip"
    dog_zip = _http_get_bytes(dog_zip_url, timeout_s=120.0)
    dog_src_dir = os.path.join(tmp_dir, "oga_cc0_creature_sfx")
    if os.path.exists(dog_src_dir):
        for fn in os.listdir(dog_src_dir):
            if fn.endswith(".ogg"):
                continue
            try:
                os.remove(os.path.join(dog_src_dir, fn))
            except Exception:
                pass
    _extract_zip(dog_zip, dog_src_dir)

    dog_wav_dir = os.path.join(out_dir, "oga_cc0_creature_sfx_wav")
    os.makedirs(dog_wav_dir, exist_ok=True)
    out_durations = {}
    for fn in sorted(os.listdir(dog_src_dir)):
        if not fn.lower().endswith(".ogg"):
            continue
        src = os.path.join(dog_src_dir, fn)
        out_name = os.path.splitext(fn)[0] + ".wav"
        dst = os.path.join(dog_wav_dir, out_name)
        d = _process_keep_duration(src, dst)
        out_durations[out_name] = float(d)
        time.sleep(0.08)

    attrib_lines += [
        "- 目录：assets/audio/oga_cc0_creature_sfx_wav",
        "  - 来源：https://opengameart.org/content/80-cc0-creature-sfx",
        "  - 作者：rubberduck（OpenGameArt 用户）",
        "  - 许可：CC0",
        f"  - 下载：{dog_zip_url}",
        "  - 说明：由原始 .ogg 转码为 48kHz/mono/16-bit wav，音量归一化并做淡入淡出",
        "",
        "- 文件：assets/audio/oga_cc0_creature_sfx_wav/_durations.json",
        "  - 说明：用于行为与音效时长匹配的索引（生成文件）",
    ]

    with open(os.path.join(dog_wav_dir, "_durations.json"), "w", encoding="utf-8") as f:
        json.dump(out_durations, f, ensure_ascii=False, indent=2, sort_keys=True)

    with open(os.path.join(out_dir, "ATTRIBUTION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(attrib_lines).rstrip() + "\n")

    for fn in os.listdir(tmp_dir):
        if fn.endswith(".mp3") or fn.endswith(".wav") or fn.endswith(".aiff") or fn.endswith(".zip"):
            try:
                os.remove(os.path.join(tmp_dir, fn))
            except Exception:
                pass

    print("ok")


if __name__ == "__main__":
    main()
