"""Shared exceptions. Callers must log or re-raise; never swallow these."""


class LocalVideoAIError(Exception):
    """Base error for the application."""


class ConfigurationError(LocalVideoAIError):
    """Settings could not be loaded or saved."""


class DatabaseError(LocalVideoAIError):
    """SQLite connection or schema failure."""


class PathError(LocalVideoAIError):
    """A required path could not be resolved."""


class ModelError(LocalVideoAIError):
    """Local model catalog, install, import, or directory management failed."""


class EngineNotAvailableError(LocalVideoAIError):
    """An engine interface has no implementation in the current phase."""


class MediaError(LocalVideoAIError):
    """Local media probe or playback failed."""


class SubtitleError(LocalVideoAIError):
    """External subtitle import, parse, or save failed."""


class SpeechError(LocalVideoAIError):
    """Local speech recognition failed."""


class OCRError(LocalVideoAIError):
    """Local hard-subtitle OCR failed."""


class TranslationError(LocalVideoAIError):
    """Local machine translation failed."""


class SpeakerError(LocalVideoAIError):
    """Local speaker diarization failed."""


class QualityError(LocalVideoAIError):
    """Subtitle quality inspection failed."""


class InpaintError(LocalVideoAIError):
    """Hard-subtitle removal or overlay failed."""


class ExportError(LocalVideoAIError):
    """Local subtitle or video export failed."""


class TaskError(LocalVideoAIError):
    """Batch task queue or persistence failed."""


class HardwareDetectionError(LocalVideoAIError):
    """Hardware probing failed in a way that blocks startup."""
