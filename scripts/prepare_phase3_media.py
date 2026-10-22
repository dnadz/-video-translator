"""Create Phase 3 media-analysis fixtures with bundled FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def _run(ffmpeg: Path, args: list[str]) -> None:
    command = [str(ffmpeg), "-y", *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-3000:])


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(path)


def main() -> int:
    ffmpeg = find_ffmpeg()
    root = ensure_directory(install_root() / "test_assets" / "videos" / "phase3")
    chinese = ensure_directory(root / "中文路径")
    source = root / "无字幕.mp4"
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30:duration=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "1",
            "-shortest",
            str(source),
        ],
    )
    print(f"{source} ({source.stat().st_size} bytes)")

    english = root / "english.srt"
    chinese_srt = root / "chinese.srt"
    chinese_ass = root / "chinese.ass"
    _write(
        english,
        "1\n00:00:00,000 --> 00:00:02,000\nHello from English\n",
    )
    _write(
        chinese_srt,
        "1\n00:00:00,000 --> 00:00:02,000\n这是中文字幕\n",
    )
    _write(
        chinese_ass,
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,这是ASS字幕\n",
    )

    single = root / "单字幕.mkv"
    _run(
        ffmpeg,
        [
            "-i",
            str(source),
            "-i",
            str(english),
            "-map",
            "0",
            "-map",
            "1",
            "-c",
            "copy",
            "-c:s",
            "srt",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "title=English",
            str(single),
        ],
    )
    print(f"{single} ({single.stat().st_size} bytes)")

    multi = root / "多字幕.mkv"
    _run(
        ffmpeg,
        [
            "-i",
            str(source),
            "-i",
            str(english),
            "-i",
            str(chinese_ass),
            "-map",
            "0",
            "-map",
            "1",
            "-map",
            "2",
            "-c",
            "copy",
            "-c:s:0",
            "srt",
            "-c:s:1",
            "ass",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "title=English",
            "-metadata:s:s:1",
            "language=chi",
            "-metadata:s:s:1",
            "title=中文",
            str(multi),
        ],
    )
    print(f"{multi} ({multi.stat().st_size} bytes)")

    dual = root / "多音轨.mkv"
    _run(
        ffmpeg,
        [
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000:duration=3",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a:0",
            "copy",
            "-c:a:1",
            "aac",
            "-ac:a:1",
            "2",
            "-metadata:s:a:0",
            "language=eng",
            "-metadata:s:a:0",
            "title=English mono",
            "-metadata:s:a:1",
            "language=jpn",
            "-metadata:s:a:1",
            "title=Japanese stereo",
            str(dual),
        ],
    )
    print(f"{dual} ({dual.stat().st_size} bytes)")

    empty = root / "空文件.mp4"
    empty.write_bytes(b"")
    print(f"{empty} ({empty.stat().st_size} bytes)")

    damaged = root / "损坏.mp4"
    damaged.write_bytes(b"not a video file " + bytes(range(64)))
    print(f"{damaged} ({damaged.stat().st_size} bytes)")

    chinese_copy = chinese / "多字幕.mkv"
    chinese_copy.write_bytes(multi.read_bytes())
    print(chinese_copy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
