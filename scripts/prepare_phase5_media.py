"""Create Phase 5 embedded-subtitle fixtures with bundled FFmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg


def _run(ffmpeg: Path, args: list[str]) -> None:
    command = [str(ffmpeg), "-y", *args]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-4000:])


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    print(path)


def _ensure_base_video(ffmpeg: Path, dest: Path) -> Path:
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
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
            str(dest),
        ],
    )
    return dest


def main() -> int:
    ffmpeg = find_ffmpeg()
    root = ensure_directory(install_root() / "test_assets" / "videos" / "phase5")
    chinese_dir = ensure_directory(root / "中文路径")
    phase3 = install_root() / "test_assets" / "videos" / "phase3" / "无字幕.mp4"
    base = _ensure_base_video(ffmpeg, phase3 if phase3.parent.is_dir() else root / "无字幕.mp4")
    if base != root / "无字幕.mp4":
        shutil.copy2(base, root / "无字幕.mp4")
        base = root / "无字幕.mp4"
    print(f"{base} ({base.stat().st_size} bytes)")

    english = root / "english.srt"
    chinese = root / "chinese.srt"
    japanese = root / "japanese.srt"
    chinese_ass = root / "chinese.ass"
    empty_ass = root / "empty.ass"
    _write(english, "1\n00:00:00,000 --> 00:00:02,000\nHello from English\n")
    _write(chinese, "1\n00:00:00,000 --> 00:00:02,000\n这是中文字幕\n")
    _write(japanese, "1\n00:00:00,000 --> 00:00:02,000\nこんにちは、世界。字幕テスト。\n")
    _write(
        chinese_ass,
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,这是ASS中文字幕\n",
    )
    _write(
        empty_ass,
        "[Script Info]\nScriptType: v4.00+\n\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
    )

    single_en = root / "单字幕_英文.mkv"
    _mux_one(ffmpeg, base, english, single_en, "srt", "eng", "English")
    single_zh = root / "单字幕_中文.mkv"
    _mux_one(ffmpeg, base, chinese, single_zh, "srt", "chi", "中文")
    single_ja = root / "单字幕_日文.mkv"
    _mux_one(ffmpeg, base, japanese, single_ja, "srt", "jpn", "日本語")

    multi = root / "多字幕.mkv"
    _run(
        ffmpeg,
        [
            "-i",
            str(base),
            "-i",
            str(english),
            "-i",
            str(chinese_ass),
            "-i",
            str(japanese),
            "-map",
            "0",
            "-map",
            "1",
            "-map",
            "2",
            "-map",
            "3",
            "-c",
            "copy",
            "-c:s:0",
            "srt",
            "-c:s:1",
            "ass",
            "-c:s:2",
            "srt",
            "-metadata:s:s:0",
            "language=eng",
            "-metadata:s:s:0",
            "title=English",
            "-metadata:s:s:1",
            "language=chi",
            "-metadata:s:s:1",
            "title=中文",
            "-metadata:s:s:2",
            "language=jpn",
            "-metadata:s:s:2",
            "title=日本語",
            str(multi),
        ],
    )
    print(f"{multi} ({multi.stat().st_size} bytes)")

    unmarked = root / "无语言标记.mkv"
    _mux_one(ffmpeg, base, chinese, unmarked, "srt", "und", "")

    empty_track = root / "空字幕轨道.mkv"
    _mux_one(ffmpeg, base, empty_ass, empty_track, "ass", "eng", "Empty")

    bitmap = root / "图像字幕.mkv"
    try:
        _run(
            ffmpeg,
            [
                "-i",
                str(base),
                "-i",
                str(english),
                "-map",
                "0",
                "-map",
                "1",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-c:s",
                "dvdsub",
                "-metadata:s:s:0",
                "language=eng",
                "-metadata:s:s:0",
                "title=Bitmap",
                str(bitmap),
            ],
        )
        print(f"{bitmap} ({bitmap.stat().st_size} bytes)")
    except RuntimeError as exc:
        print(f"skip bitmap mux: {exc}")

    chinese_copy = chinese_dir / "多字幕.mkv"
    shutil.copy2(multi, chinese_copy)
    print(chinese_copy)
    return 0


def _mux_one(ffmpeg: Path, video: Path, subtitle: Path, dest: Path, codec: str, language: str, title: str) -> None:
    args = [
        "-i",
        str(video),
        "-i",
        str(subtitle),
        "-map",
        "0",
        "-map",
        "1",
        "-c",
        "copy",
        "-c:s",
        codec,
        "-metadata:s:s:0",
        f"language={language}",
    ]
    if title:
        args.extend(["-metadata:s:s:0", f"title={title}"])
    args.append(str(dest))
    _run(ffmpeg, args)
    print(f"{dest} ({dest.stat().st_size} bytes)")


if __name__ == "__main__":
    raise SystemExit(main())
