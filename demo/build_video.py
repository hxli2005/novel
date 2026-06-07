"""Assemble a narrated demo video from the captured screenshots.

For each segment: synthesize Chinese narration with macOS `say`, then build a
clip (the screenshot held for the narration length + a short tail) with ffmpeg.
Finally concat the clips into demo/inkdraft-demo.mp4.

Run with:  uv run --with imageio-ffmpeg python demo/build_video.py
"""

from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = "Tingting"
ROOT = Path(__file__).resolve().parent
SHOTS = ROOT / "shots"
WORK = ROOT / "_clips"
WORK.mkdir(exist_ok=True)
OUT = ROOT / "inkdraft-demo.mp4"
TAIL = 0.8  # seconds of silence after each narration line

SEGMENTS = [
    ("1_upload.png",
     "墨稿，是一款 AI 小说转剧本工具。上传三章以上的小说，选好体裁、节奏和改编引擎，"
     "就能把它变成可编辑、可校验、可导出的结构化剧本初稿。"),
    ("2_running.png",
     "转换过程实时可见。解析章节、提取人物地点、规划分场、组装剧本、逐场扩写、质量校验，"
     "六个阶段逐一完成，并且随时可以取消。"),
    ("3_reader.png",
     "这是接入 DeepSeek 真实模型生成的剧本，以纸墨风格呈现：场景标题、动作描写、"
     "人物对白与潜台词一应俱全，可以泛化到任意题材的小说。"),
    ("4_quality.png",
     "右侧是质量报告。除了确定性的结构检查，还能一键触发 AI 深度复审，"
     "自动发现伏笔是否回收、人物弧光是否连贯、跨场因果是否成立，并跳转到对应场景。"),
    ("5_fdx.png",
     "剧本可以一键导出为 Fountain、Final Draft 和 Word 三种专业格式。"
     "这是生成的 Final Draft 文件，可以直接在 Final Draft、WriterDuet 等行业工具中打开。"),
    ("6_history.png",
     "所有生成过的剧本都保存在历史记录里，随时重看、换章节范围重新生成或重新导出。"
     "墨稿，让小说落定成剧本。"),
]


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def main() -> None:
    clips = []
    for i, (image, text) in enumerate(SEGMENTS, start=1):
        wav = WORK / f"seg{i}.wav"
        subprocess.run(
            ["say", "-v", VOICE, "-o", str(wav), "--data-format=LEI16@22050", text],
            check=True,
        )
        dur = wav_duration(wav) + TAIL
        clip = WORK / f"seg{i}.mp4"
        subprocess.run(
            [
                FFMPEG, "-y", "-loop", "1", "-i", str(SHOTS / image), "-i", str(wav),
                "-t", f"{dur:.2f}", "-r", "30",
                "-vf", "scale=1280:800:force_original_aspect_ratio=decrease,"
                       "pad=1280:800:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-af", "apad",
                "-c:v", "libx264", "-c:a", "aac", "-b:a", "192k",
                str(clip),
            ],
            check=True, capture_output=True,
        )
        print(f"seg{i}: {dur:.1f}s  ({image})")
        clips.append(clip)

    listing = WORK / "list.txt"
    listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    subprocess.run(
        [
            FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(OUT),
        ],
        check=True, capture_output=True,
    )
    total = sum(wav_duration(WORK / f"seg{i}.wav") + TAIL for i in range(1, len(SEGMENTS) + 1))
    print(f"\nDONE -> {OUT}  (~{total:.0f}s)")


if __name__ == "__main__":
    main()
