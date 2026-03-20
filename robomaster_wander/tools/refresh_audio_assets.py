import io
import json
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
    with open(path, "rb") as f:
        buf = f.read()
    if len(buf) < 12 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise RuntimeError(f"not a wav file: {path}")

    fmt = None
    data = None
    off = 12
    while off + 8 <= len(buf):
        cid = buf[off : off + 4]
        size = int.from_bytes(buf[off + 4 : off + 8], "little", signed=False)
        start = off + 8
        end = start + size
        if end > len(buf):
            break
        if cid == b"fmt ":
            fmt = buf[start:end]
        elif cid == b"data":
            data = buf[start:end]
        off = end + (size & 1)

    if fmt is None or len(fmt) < 16:
        raise RuntimeError(f"missing fmt chunk: {path}")
    if data is None:
        raise RuntimeError(f"missing data chunk: {path}")

    w_format = int.from_bytes(fmt[0:2], "little", signed=False)
    n_channels = int.from_bytes(fmt[2:4], "little", signed=False)
    sr = int.from_bytes(fmt[4:8], "little", signed=False)
    bits = int.from_bytes(fmt[14:16], "little", signed=False)

    if w_format == 65534:
        if len(fmt) < 40:
            raise RuntimeError(f"invalid extensible fmt: {path}")
        valid_bits = int.from_bytes(fmt[18:20], "little", signed=False)
        subformat = fmt[24:40]
        pcm_guid = bytes.fromhex("0100000000001000800000aa00389b71")
        if subformat != pcm_guid:
            raise RuntimeError(f"unsupported wav subformat: {path}")
        bits = int(valid_bits)

    if int(n_channels) != 1:
        raise RuntimeError(f"expected mono wav: {path}")
    if int(bits) != 16:
        raise RuntimeError(f"expected 16-bit wav: {path}")
    if len(data) % 2 != 0:
        data = data[: len(data) - 1]
    return int(sr), data


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


def _extract_zip(zip_bytes: bytes, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        zf.extractall(out_dir)


def _iter_audio_files(root_dir: str) -> list[str]:
    out: list[str] = []
    for dp, _dns, fns in os.walk(root_dir):
        if "__MACOSX" in dp:
            continue
        for fn in fns:
            lo = fn.lower()
            if fn.startswith("._"):
                continue
            if lo.endswith((".ogg", ".wav", ".mp3", ".aiff", ".aif", ".m4a")):
                out.append(os.path.join(dp, fn))
    out.sort()
    return out


def _clear_dir(dir_path: str) -> None:
    if not os.path.exists(dir_path):
        return
    for dp, dns, fns in os.walk(dir_path, topdown=False):
        for fn in fns:
            try:
                os.remove(os.path.join(dp, fn))
            except Exception:
                pass
        for dn in dns:
            try:
                os.rmdir(os.path.join(dp, dn))
            except Exception:
                pass


def _download_oga_zip_with_fallbacks(urls: list[str]) -> tuple[str, bytes]:
    last_err = None
    for url in urls:
        try:
            return url, _http_get_bytes(url, timeout_s=120.0)
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err is not None else RuntimeError("all download urls failed")


def _process_pack_zip(
    *,
    tmp_dir: str,
    out_dir: str,
    slug: str,
    zip_urls: list[str],
    out_subdir: str,
) -> dict:
    used_url, zip_bytes = _download_oga_zip_with_fallbacks(zip_urls)
    src_dir = os.path.join(tmp_dir, slug)
    _clear_dir(src_dir)
    os.makedirs(src_dir, exist_ok=True)
    _extract_zip(zip_bytes, src_dir)

    wav_dir = os.path.join(out_dir, out_subdir)
    _clear_dir(wav_dir)
    os.makedirs(wav_dir, exist_ok=True)

    out_durations: dict = {}
    for src in _iter_audio_files(src_dir):
        base = os.path.splitext(os.path.basename(src))[0] + ".wav"
        dst = os.path.join(wav_dir, base)
        d = _process_keep_duration(src, dst)
        out_durations[base] = float(d)
        time.sleep(0.06)

    with open(os.path.join(wav_dir, "_durations.json"), "w", encoding="utf-8") as f:
        json.dump(out_durations, f, ensure_ascii=False, indent=2, sort_keys=True)

    return {"used_url": used_url, "wav_dir": wav_dir, "count": len(out_durations)}


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

    packs = []

    for p in packs:
        info = _process_pack_zip(
            tmp_dir=tmp_dir,
            out_dir=out_dir,
            slug=str(p["slug"]),
            zip_urls=list(p["zip_urls"]),
            out_subdir=str(p["out_subdir"]),
        )
        rel_wav_dir = os.path.relpath(str(info["wav_dir"]), root).replace("\\", "/")
        attrib_lines += [
            f"- 目录：{rel_wav_dir}",
            f"  - 来源：{p['page']}",
            f"  - 许可：{p['license']}",
            f"  - 下载：{info['used_url']}",
            "  - 说明：由原始音频转码为 48kHz/mono/16-bit wav，音量归一化并做淡入淡出",
            f"  - 文件数：{int(info['count'])}",
            "",
            f"- 文件：{rel_wav_dir}/_durations.json",
            "  - 说明：用于行为与音效时长匹配的索引（生成文件）",
            "",
        ]

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
