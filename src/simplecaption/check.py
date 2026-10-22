"""Confirm the simple app can see FFmpeg, a speech model, and a translation model."""

from __future__ import annotations

from simplecaption.runtime import prepare_runtime


def run_check() -> int:
    prepare_runtime()
    problems: list[str] = []
    try:
        from localvideoai.media.ffmpeg_runtime import find_ffmpeg

        ffmpeg = find_ffmpeg()
        print(f"ffmpeg: {ffmpeg}")
    except Exception as exc:
        problems.append(f"ffmpeg: {exc}")
    from localvideoai.speech.store import list_local_models
    from localvideoai.translation.store import list_local_translation_models

    speech = list_local_models()
    translation = list_local_translation_models()
    print("speech models: " + (", ".join(speech) if speech else "(none)"))
    print("translation models: " + (", ".join(translation) if translation else "(none)"))
    if not speech:
        problems.append("没有可用的本地语音模型")
    if not translation:
        problems.append("没有可用的本地翻译模型")
    if problems:
        for item in problems:
            print("FAIL: " + item)
        return 1
    print("OK")
    return 0
