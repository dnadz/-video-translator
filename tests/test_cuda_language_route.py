from __future__ import annotations

from pathlib import Path

from localvideoai.core.types import SubtitleSegment, TranslationRequest
from localvideoai.engines import create_translation_engine
from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine
from localvideoai.speech.cuda_runtime import is_cuda_runtime_error, prepare_cuda_dlls
from localvideoai.speech.selector import ModelChoice
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.store import list_local_translation_models

from tests.conftest import make_report


def test_cuda_runtime_error_detects_missing_cublas():
    assert is_cuda_runtime_error(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
    assert not is_cuda_runtime_error(RuntimeError("没有可识别的媒体文件"))


def test_prepare_cuda_dlls_exposes_cublas():
    directories = [Path(item) for item in prepare_cuda_dlls()]
    assert any(dll.is_file() for folder in directories for dll in folder.glob("cublas64_*.dll"))


def test_prepare_cuda_dlls_does_not_grow_path_again():
    import os

    prepare_cuda_dlls()
    length = len(os.environ.get("PATH", ""))
    prepare_cuda_dlls()
    assert len(os.environ.get("PATH", "")) == length


def test_cuda_inference_failure_falls_back_to_same_model_on_cpu():
    engine = FasterWhisperSpeechEngine()
    choice = ModelChoice("large-v3-turbo", "cuda", "float16", "test")
    engine._model = object()
    engine._loaded_choice = choice
    fallback = engine._cpu_fallback_choice(
        choice,
        RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"),
    )
    assert fallback is not None
    assert fallback.model_id == "large-v3-turbo"
    assert fallback.device == "cpu"
    assert fallback.compute_type == "int8"
    assert engine._model is None
    assert engine._cpu_fallback_choice(fallback, RuntimeError("cublas")) is None


def test_auto_recognized_chinese_translates_to_english():
    names = set(list_local_translation_models())
    if "argos-zh-en" not in names:
        raise AssertionError("missing argos-zh-en")
    engine = create_translation_engine(make_report())
    source = "妈妈开车回家的 那是第一次 转天早上我下楼"
    document = SubtitleDocument(
        segments=[SubtitleSegment(id=1, start_time=0, end_time=2500, source_text=source, language="zh")],
        format_name="srt",
        detected_language="zh",
    )
    results = engine.translate_document(
        document,
        "auto",
        ["en"],
        quality="standard",
        device_preference="cpu",
        use_context=False,
    )
    translated = document.segments[0].translated_text.strip()
    assert results
    assert results[0].source_lang == "zh"
    assert results[0].target_lang == "en"
    assert translated
    assert translated != source
    assert any(char.isascii() and char.isalpha() for char in translated)
    direct = engine.translate(TranslationRequest(source, "auto", "en", device_preference="cpu"))
    assert direct.source_lang == "zh"
    assert direct.target_lang == "en"
    assert direct.text.strip() != source


def test_translate_many_handles_several_lines_together():
    names = set(list_local_translation_models())
    if "argos-en-ja" not in names:
        raise AssertionError("missing argos-en-ja")
    engine = create_translation_engine(make_report())
    requests = [
        TranslationRequest("Hello.", "en", "ja", device_preference="cpu"),
        TranslationRequest("They are ready for you now.", "en", "ja", device_preference="cpu"),
        TranslationRequest("Go again from the top.", "en", "ja", device_preference="cpu"),
    ]
    results = engine.translate_many(requests)
    assert len(results) == 3
    assert all(item.text.strip() for item in results)
    assert all(item.target_lang == "ja" for item in results)
