import os
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from robomaster_wander.tools.refresh_audio_assets import _process_pack_zip



def main() -> None:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "assets", "audio")
    tmp_dir = os.path.join(out_dir, "_tmp_candidates")
    cand_dir = os.path.join(out_dir, "_candidates")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(cand_dir, exist_ok=True)

    packs = [
        {
            "slug": "oga_cc0_robot_voice_pack",
            "name": "Robot Voice Pack",
            "page": "https://opengameart.org/content/robot-voice-pack",
            "license": "CC0",
            "zip_urls": ["https://opengameart.org/sites/default/files/Voices.zip"],
            "out_subdir": os.path.join("_candidates", "minionish_robot_voice_pack_wav"),
        },
        {
            "slug": "oga_cc0_voiceover_pack_fighter",
            "name": "Voiceover Pack: Fighter (40+ taunts)",
            "page": "https://opengameart.org/content/voiceover-pack-fighter-40-taunts",
            "license": "CC0 (Kenney)",
            "zip_urls": ["https://opengameart.org/sites/default/files/Voiceover%20Pack.zip"],
            "out_subdir": os.path.join("_candidates", "minionish_voiceover_fighter_wav"),
        },
        {
            "slug": "oga_cc0_goblins_sound_pack",
            "name": "Goblins Sound Pack",
            "page": "https://opengameart.org/content/goblins-sound-pack",
            "license": "CC0",
            "zip_urls": ["https://opengameart.org/sites/default/files/goblins_0.zip"],
            "out_subdir": os.path.join("_candidates", "minionish_goblins_wav"),
        },
        {
            "slug": "oga_cc0_creature_sfx",
            "name": "80 CC0 creature SFX",
            "page": "https://opengameart.org/content/80-cc0-creature-sfx",
            "license": "CC0",
            "zip_urls": [
                "https://opengameart.org/sites/default/files/80-CC0-creature-SFX_0.zip",
                "https://opengameart.org/sites/default/files/80-CC0-creature-SFX.zip",
            ],
            "out_subdir": os.path.join("_candidates", "minionish_cc0_creature_sfx_wav"),
        },
    ]

    lines = ["Candidate voice packs (minion-ish, NOT copyrighted Minions audio)", ""]
    for p in packs:
        info = _process_pack_zip(
            tmp_dir=tmp_dir,
            out_dir=out_dir,
            slug=str(p["slug"]),
            zip_urls=list(p["zip_urls"]),
            out_subdir=str(p["out_subdir"]),
        )
        rel = os.path.relpath(str(info["wav_dir"]), root).replace("\\", "/")
        lines += [
            f"- dir: {rel}",
            f"  - source: {p['page']}",
            f"  - license: {p['license']}",
            f"  - download: {info['used_url']}",
            f"  - files: {int(info['count'])}",
            "",
        ]

    with open(os.path.join(cand_dir, "ATTRIBUTION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    print("ok")


if __name__ == "__main__":
    main()
