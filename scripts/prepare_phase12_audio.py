"""Build two-speaker / three-speaker / different-timbre fixtures with local SAPI voices."""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.media.ffmpeg_runtime import find_ffmpeg

TWO_PERSON = [
    ("A", "你好，我是甲方，今天来测试说话人分离。"),
    ("B", "Hello, I am speaker B. My voice is different from yours."),
    ("A", "请记住我是第一个说话的人。"),
    ("B", "Please remember that I am the second speaker."),
]

THREE_PERSON = [
    ("A", "我是一号，负责开头说明。"),
    ("B", "I am speaker B, answering in the middle."),
    ("C", "I am speaker C, confirming at the end."),
    ("A", "一号再次发言，确认双人之后还有第三人。"),
    ("B", "Speaker B speaks again with the same English voice."),
    ("C", "Speaker C speaks again with a different English voice."),
]


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
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or "cannot list SAPI voices")
    return [line.strip() for line in completed.stdout.splitlines() if "|" in line]


def _pick_distinct(voices: list[str]) -> list[str]:
    names = [row.split("|", 1)[0] for row in voices]
    if len(names) < 2:
        raise RuntimeError(f"need at least 2 SAPI voices, got {voices}")
    chosen: list[str] = []
    for name in names:
        if name not in chosen:
            chosen.append(name)
        if len(chosen) == 3:
            break
    if len(chosen) == 2:
        chosen.append(chosen[0])
    return chosen[:3]


def _speak(text: str, voice: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    escaped = text.replace("'", "''")
    voice_escaped = voice.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{voice_escaped}'); "
        "$s.Rate = 0; "
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
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size < 2000:
        raise RuntimeError(f"SAPI failed for {dest}: size={dest.stat().st_size if dest.is_file() else 0} {completed.stderr or completed.stdout}")
    if _wav_duration_ms(dest) < 400:
        raise RuntimeError(f"SAPI wrote too little audio for {dest}")


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate() or 16000
    return int(frames * 1000 / rate)


def _silence(ffmpeg: Path, dest: Path, ms: int = 250) -> None:
    _run(
        ffmpeg,
        [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=16000:cl=mono",
            "-t",
            f"{ms / 1000:.3f}",
            "-c:a",
            "pcm_s16le",
            str(dest),
        ],
    )


def _concat(ffmpeg: Path, clips: list[Path], dest: Path) -> None:
    listing = dest.with_suffix(".concat.txt")
    listing.write_text("".join(f"file '{item.resolve().as_posix()}'\n" for item in clips), encoding="utf-8")
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
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(dest),
        ],
    )


def _write_srt(cues: list[dict[str, object]], dest: Path) -> None:
    lines: list[str] = []
    for index, cue in enumerate(cues, start=1):
        start = _clock(int(cue["start_ms"]))
        end = _clock(int(cue["end_ms"]))
        lines.extend([str(index), f"{start} --> {end}", str(cue["text"]), ""])
    dest.write_text("\n".join(lines), encoding="utf-8")


def _clock(ms: int) -> str:
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _build_dialogue(ffmpeg: Path, root: Path, name: str, script: list[tuple[str, str]], voices: dict[str, str]) -> dict:
    clips: list[Path] = []
    cues: list[dict[str, object]] = []
    cursor = 0
    gap = root / f"{name}_gap.wav"
    _silence(ffmpeg, gap, 220)
    gap_ms = _wav_duration_ms(gap)
    for index, (who, text) in enumerate(script, start=1):
        clip = root / f"{name}_{who}_{index}.wav"
        _speak(text, voices[who], clip)
        pcm = root / f"{name}_{who}_{index}_16k.wav"
        _run(ffmpeg, ["-i", str(clip), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(pcm)])
        duration = _wav_duration_ms(pcm)
        cues.append(
            {
                "speaker": who,
                "voice": voices[who],
                "text": text,
                "start_ms": cursor,
                "end_ms": cursor + duration,
            }
        )
        clips.append(pcm)
        clips.append(gap)
        cursor += duration + gap_ms
    audio = root / f"{name}.wav"
    _concat(ffmpeg, clips, audio)
    srt = install_root() / "test_assets" / "subtitles" / "phase12" / f"{name}.srt"
    ensure_directory(srt.parent)
    _write_srt(cues, srt)
    meta = {"audio": str(audio), "srt": str(srt), "voices": voices, "cues": cues}
    (root / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{audio} cues={len(cues)} voices={voices}")
    return meta


def main() -> int:
    ffmpeg = find_ffmpeg()
    root = ensure_directory(install_root() / "test_assets" / "audio" / "phase12")
    installed = _sapi_voices()
    print("SAPI voices:")
    for item in installed:
        print(f"  {item}")
    picked = _pick_distinct(installed)
    two_voices = {"A": picked[0], "B": picked[1]}
    three_voices = {"A": picked[0], "B": picked[1], "C": picked[2]}
    _build_dialogue(ffmpeg, root, "two_person", TWO_PERSON, two_voices)
    _build_dialogue(ffmpeg, root, "three_person", THREE_PERSON, three_voices)
    timbre = root / "different_timbre.wav"
    parts = [root / "two_person_A_1_16k.wav", root / "two_person_B_2_16k.wav"]
    if (root / "three_person_C_3_16k.wav").is_file():
        parts.append(root / "three_person_C_3_16k.wav")
    _concat(ffmpeg, parts, timbre)
    print(timbre)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
