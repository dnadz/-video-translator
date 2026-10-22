"""Create legal Phase 6 speech fixtures with Windows SAPI + bundled FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

TEXTS = {
    "zh": "今天天气很好，我们在本地计算机上测试语音识别。这是中文普通语速。",
    "en": "Today the weather is clear. We are testing local speech recognition in English.",
    "ja": "本日は晴天なり。これは日本語の音声認識テストです。",
    "zh_fast": "请尽快完成本地识别测试并核对时间轴。",
    "en_fast": "Please finish this local recognition test quickly and check the timestamps.",
}


def _run(ffmpeg: Path, args: list[str]) -> None:
    completed = subprocess.run(
        [str(ffmpeg), "-y", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "")[-4000:])


def _sapi_voices() -> list[str]:
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
    )
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or "cannot list SAPI voices")
    return [line.strip() for line in completed.stdout.splitlines() if "|" in line]


def _pick_voice(voices: list[str], language: str) -> str:
    wanted = {"zh": ("zh", "chinese", "huihui", "yaoyao", "kangkang"), "en": ("en", "zira", "david", "mark"), "ja": ("ja", "jp", "haruka", "ayumi", "ichiro")}
    keys = wanted[language]
    for row in voices:
        name, culture = row.split("|", 1)
        blob = f"{name} {culture}".lower()
        if any(key in blob for key in keys):
            return name
    if language == "en" and voices:
        return voices[0].split("|", 1)[0]
    raise RuntimeError(f"no SAPI voice for {language}. installed={voices}")


def _speak_japanese_fallback(ffmpeg: Path, text: str, dest: Path, en_voice: str) -> bool:
    raw = dest.with_name("ja_normal.edge.tmp")
    try:
        import asyncio

        import edge_tts

        asyncio.run(edge_tts.Communicate(text, "ja-JP-NanamiNeural").save(str(raw)))
        if raw.is_file() and raw.stat().st_size > 44:
            _run(ffmpeg, ["-i", str(raw), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dest)])
            raw.unlink(missing_ok=True)
            return dest.is_file() and dest.stat().st_size > 44
    except Exception as exc:
        print(f"edge-tts Japanese failed: {exc}")
        raw.unlink(missing_ok=True)
    _speak(
        "Kyou wa seiten nari. Kore wa nihongo no onsei ninshiki tesuto desu.",
        en_voice,
        dest,
        rate=-1,
    )
    return dest.is_file()


def _speak(text: str, voice: str, dest: Path, rate: int = 0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    escaped = text.replace("'", "''")
    voice_escaped = voice.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{voice_escaped}'); "
        f"$s.Rate = {rate}; "
        f"$s.SetOutputToWaveFile('{str(dest)}'); "
        f"$s.Speak('{escaped}'); "
        "$s.Dispose()"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size <= 44:
        raise RuntimeError(f"SAPI failed for {dest}: {completed.stderr or completed.stdout}")


def _concat_loop(ffmpeg: Path, clip: Path, dest: Path, copies: int) -> None:
    listing = dest.with_suffix(".concat.txt")
    lines = "".join(f"file '{clip.resolve().as_posix()}'\n" for _ in range(copies))
    listing.write_text(lines, encoding="utf-8")
    _run(
        ffmpeg,
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dest),
        ],
    )


def _mix_noise(ffmpeg: Path, speech: Path, dest: Path) -> None:
    _run(
        ffmpeg,
        [
            "-i",
            str(speech),
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=white:amplitude=0.04:sample_rate=16000",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0,volume=1.4",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ],
    )


def _make_video(ffmpeg: Path, audio: Path, dest: Path) -> None:
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            "color=c=0x203040:s=640x360:r=15",
            "-i",
            str(audio),
            "-shortest",
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
            str(dest),
        ],
    )


def main() -> int:
    ffmpeg = find_ffmpeg()
    root = ensure_directory(install_root() / "test_assets" / "audio" / "phase6")
    voices = _sapi_voices()
    print("SAPI voices:")
    for item in voices:
        print(f"  {item}")
    zh_voice = _pick_voice(voices, "zh")
    en_voice = _pick_voice(voices, "en")
    try:
        ja_voice = _pick_voice(voices, "ja")
    except RuntimeError:
        ja_voice = None
        print("No Japanese SAPI voice. Will try edge-tts, then romaji fallback.")

    clips: dict[str, Path] = {}
    mapping = [
        ("zh_normal.wav", TEXTS["zh"], zh_voice, 0),
        ("en_normal.wav", TEXTS["en"], en_voice, 0),
        ("zh_fast.wav", TEXTS["zh_fast"], zh_voice, 6),
        ("en_fast.wav", TEXTS["en_fast"], en_voice, 6),
    ]
    if ja_voice:
        mapping.append(("ja_normal.wav", TEXTS["ja"], ja_voice, 0))
    for name, text, voice, rate in mapping:
        dest = root / name
        _speak(text, voice, dest, rate=rate)
        clips[name] = dest
        print(f"{dest} ({dest.stat().st_size} bytes)")

    ja_path = root / "ja_normal.wav"
    if ja_voice is None:
        if not _speak_japanese_fallback(ffmpeg, TEXTS["ja"], ja_path, en_voice):
            raise RuntimeError("cannot create Japanese fixture")
        clips["ja_normal.wav"] = ja_path
        print(f"{ja_path} ({ja_path.stat().st_size} bytes)")

    multi = root / "multi_speaker.wav"
    _run(
        ffmpeg,
        [
            "-i",
            str(clips["zh_normal.wav"]),
            "-i",
            str(clips["en_normal.wav"]),
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1",
            "-c:a",
            "pcm_s16le",
            str(multi),
        ],
    )
    print(multi)

    noisy = root / "zh_noise.wav"
    _mix_noise(ffmpeg, clips["zh_normal.wav"], noisy)
    print(noisy)

    video = root / "zh_normal.mp4"
    _make_video(ffmpeg, clips["zh_normal.wav"], video)
    print(video)

    # 10s-ish clip looped to 10 min / 1 hour / 2 hours without Python holding PCM.
    base = clips["en_normal.wav"]
    probe = subprocess.run(
        [str(ffmpeg), "-hide_banner", "-i", str(base)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    duration = 8.0
    for line in (probe.stderr or "").splitlines():
        if "Duration:" in line:
            stamp = line.split("Duration:")[1].split(",")[0].strip()
            hours, minutes, seconds = stamp.split(":")
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            break
    if duration <= 0:
        duration = 8.0
    targets = {
        "10min.mp3": 600,
        "1hour.mp3": 3600,
        "2hour.mp3": 7200,
    }
    for name, seconds in targets.items():
        copies = max(1, int(seconds / duration) + 1)
        dest = root / name
        print(f"loop {base.name} x {copies} -> {dest}")
        _concat_loop(ffmpeg, base, dest, copies)
        print(f"{dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
