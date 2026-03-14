音频资源约定

本目录用于存放 RoboMaster 自定义音频（Robot.play_audio）使用的 wav 文件。

格式要求（SDK 限制）
- 单声道（mono）
- 48kHz 采样率
- wav

默认音效包（小狗音效）
- 运行：python3 robomaster_wander/tools/refresh_audio_assets.py
- 生成目录：assets/audio/oga_cc0_creature_sfx_wav
- 说明：会下载 OpenGameArt 的 CC0 音效包并转码为 48kHz/mono wav

声音资源来源建议
- Freesound（多为 CC BY/CC0，需要按页面要求署名/标注许可）
- Wikimedia Commons（有大量 Public Domain / CC 许可音频，注意逐文件许可）
- OpenGameArt（游戏音效集合，注意许可）
- Pixabay Sound Effects（注意许可条款）

下载后请将来源、作者、许可、链接写入本目录的 ATTRIBUTION.md
