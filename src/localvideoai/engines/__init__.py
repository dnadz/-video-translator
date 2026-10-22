from localvideoai.engines.audio_engine import AudioEngine
from localvideoai.engines.base import BaseEngine
from localvideoai.engines.export_engine import ExportEngine
from localvideoai.engines.inpainting_engine import InpaintingEngine
from localvideoai.engines.ocr_engine import OCREngine
from localvideoai.engines.quality_engine import QualityEngine
from localvideoai.engines.speaker_engine import SpeakerEngine
from localvideoai.engines.speech_engine import SpeechEngine
from localvideoai.engines.subtitle_engine import SubtitleEngine
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine
from localvideoai.engines.ffmpeg_audio_engine import FFmpegAudioEngine
from localvideoai.engines.ffmpeg_video_engine import FFmpegVideoEngine
from localvideoai.engines.file_subtitle_engine import FileSubtitleEngine
from localvideoai.engines.video_engine import VideoEngine

ENGINE_TYPES = (
    VideoEngine,
    AudioEngine,
    SubtitleEngine,
    SpeechEngine,
    OCREngine,
    TranslationEngine,
    SpeakerEngine,
    QualityEngine,
    InpaintingEngine,
    ExportEngine,
)


def create_speech_engine(report=None) -> SpeechEngine:
    """UI and tests construct speech engines through this factory, not the model SDK."""
    return FasterWhisperSpeechEngine(report)


def create_ocr_engine(report=None) -> OCREngine:
    from localvideoai.engines.rapidocr_engine import RapidOCREngine

    return RapidOCREngine(report)


def create_speaker_engine(report=None) -> SpeakerEngine:
    """UI and tests construct speaker engines through this factory, not onnxruntime."""
    from localvideoai.engines.local_speaker_engine import LocalSpeakerEngine

    return LocalSpeakerEngine()


def create_inpainting_engine(report=None, ocr_engine=None) -> InpaintingEngine:
    """UI and tests construct inpainting engines through this factory, not a model SDK."""
    from localvideoai.engines.local_inpainting_engine import LocalInpaintingEngine

    return LocalInpaintingEngine(ocr_engine)


def create_quality_engine(report=None) -> QualityEngine:
    """UI and tests construct quality engines through this factory, not a model SDK."""
    from localvideoai.engines.local_quality_engine import LocalQualityEngine

    return LocalQualityEngine()


def create_export_engine() -> ExportEngine:
    """UI and tests construct exporters through this factory, not an FFmpeg SDK."""
    from localvideoai.engines.ffmpeg_export_engine import FFmpegExportEngine

    return FFmpegExportEngine()


def create_translation_engine(report=None) -> TranslationEngine:
    """UI and tests construct translation engines through this factory, not a model SDK."""
    from localvideoai.core.exceptions import TranslationError
    from localvideoai.translation.catalog import load_catalog

    engine_name = (load_catalog().engine or "ctranslate2").strip().lower()
    if engine_name in {"ctranslate2", "ctranslate2-catalog"}:
        from localvideoai.engines.ctranslate2_translation_engine import CTranslate2TranslationEngine

        return CTranslate2TranslationEngine(report)
    raise TranslationError(
        f"翻译目录指定了未知引擎 {engine_name}。请在 config/translation_catalog.json 中改回 ctranslate2，或实现对应引擎后在 create_translation_engine 注册。"
    )


__all__ = [
    "AudioEngine",
    "BaseEngine",
    "ENGINE_TYPES",
    "ExportEngine",
    "FFmpegAudioEngine",
    "FasterWhisperSpeechEngine",
    "FFmpegVideoEngine",
    "FileSubtitleEngine",
    "InpaintingEngine",
    "OCREngine",
    "QualityEngine",
    "SpeakerEngine",
    "SpeechEngine",
    "SubtitleEngine",
    "TranslationEngine",
    "VideoEngine",
    "create_speech_engine",
    "create_ocr_engine",
    "create_speaker_engine",
    "create_quality_engine",
    "create_inpainting_engine",
    "create_translation_engine",
    "create_export_engine",
]
