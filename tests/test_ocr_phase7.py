from __future__ import annotations

from pathlib import Path

import pytest

from localvideoai import __version__
from localvideoai.core.exceptions import OCRError
from localvideoai.core.paths import install_root
from localvideoai.engines.rapidocr_engine import RapidOCREngine
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.language import detect_script_language
from localvideoai.ocr.merge import merge_cues, text_similar
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.ocr.store import is_ocr_ready
from localvideoai.core.types import OCRCue


def _video(name: str) -> Path:
    return install_root() / "test_assets" / "videos" / "phase7" / name


def _require(*names: str) -> None:
    for name in names:
        path = _video(name)
        if not path.is_file():
            pytest.fail(f"missing fixture {path}; run scripts/prepare_phase7_videos.py")
    if not is_ocr_ready():
        pytest.fail("no local OCR model; run scripts/prepare_phase7_models.py")


_SHARED: RapidOCREngine | None = None


def _engine() -> RapidOCREngine:
    global _SHARED
    if _SHARED is None:
        _SHARED = RapidOCREngine()
    return _SHARED


def test_version_is_phase7():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 8)


def test_script_language_helper():
    assert detect_script_language("本日は晴天なり") == "ja"
    assert detect_script_language("这是中文") == "zh"
    assert detect_script_language("Hello world") == "en"


def test_merge_consecutive_cues():
    first = OCRCue(start_ms=1000, end_ms=2000, text="这是硬字幕测试", x=0.1, y=0.8, w=0.8, h=0.1)
    second = OCRCue(start_ms=2100, end_ms=4000, text="这是硬字幕测试", x=0.1, y=0.8, w=0.8, h=0.1)
    merged = merge_cues([first, second])
    assert len(merged) == 1
    assert merged[0].start_ms == 1000
    assert merged[0].end_ms == 4000
    assert text_similar("Hard subtitle test", "Hard subtitle test")


def test_ocr_chinese_static():
    _require("zh_static.mp4")
    transcript = _engine().recognize_video(_video("zh_static.mp4"), language="zh")
    blob = "".join(item.text for item in transcript.cues)
    assert "硬字幕" in blob or "测试" in blob
    assert transcript.language == "zh"
    assert all(item.end_ms >= item.start_ms for item in transcript.cues)
    assert transcript.cues[0].w > 0 and transcript.cues[0].h > 0
    assert transcript.raw_path is not None and transcript.raw_path.is_file()
    payload = transcript.raw_path.read_text(encoding="utf-8")
    assert "start_ms" in payload and "text" in payload
    assert '"x"' in payload and '"y"' in payload


def test_ocr_english_static():
    _require("en_static.mp4")
    transcript = _engine().recognize_video(_video("en_static.mp4"), language="en")
    blob = " ".join(item.text.lower() for item in transcript.cues)
    assert "hard" in blob and "subtitle" in blob
    assert transcript.language == "en"


def test_ocr_japanese_static():
    _require("ja_static.mp4")
    transcript = _engine().recognize_video(_video("ja_static.mp4"), language="ja")
    blob = "".join(item.text for item in transcript.cues)
    assert any(token in blob for token in ("本日", "晴天", "なり", "日本語"))
    assert transcript.language in {"ja", "zh"}


def test_ocr_dynamic_changes():
    _require("zh_dynamic.mp4")
    transcript = _engine().recognize_video(_video("zh_dynamic.mp4"), language="zh")
    texts = [item.text.replace(" ", "") for item in transcript.cues]
    joined = "".join(texts)
    assert "第一" in joined and "第二" in joined
    assert len(transcript.cues) >= 2
    assert transcript.cues[0].end_ms <= transcript.cues[-1].start_ms + 1500


def test_ocr_two_line():
    _require("zh_twoline.mp4")
    transcript = _engine().recognize_video(_video("zh_twoline.mp4"), language="zh")
    blob = "\n".join(item.text for item in transcript.cues)
    assert "第一行" in blob and "第二行" in blob
    assert any("\n" in item.text or ("第一行" in item.text and "第二行" in item.text) for item in transcript.cues)


def test_ocr_english_dynamic():
    _require("en_dynamic.mp4")
    transcript = _engine().recognize_video(_video("en_dynamic.mp4"), language="en")
    blob = " ".join(item.text.lower() for item in transcript.cues)
    assert "first" in blob and "second" in blob
    assert len(transcript.cues) >= 2


def test_auto_region_is_lower_frame():
    _require("zh_static.mp4")
    transcript = _engine().recognize_video(_video("zh_static.mp4"), language="zh")
    assert transcript.region_source == "auto"
    _x, y, _w, h = transcript.region
    assert y >= 0.45
    assert y + h > 0.7


def test_manual_region_top_misses_bottom_text():
    _require("zh_static.mp4")
    with pytest.raises(OCRError):
        _engine().recognize_video(
            _video("zh_static.mp4"),
            language="zh",
            region=NormalizedRegion(0.05, 0.02, 0.9, 0.18),
            save_raw=False,
        )


def test_manual_region_bottom_hits():
    _require("en_static.mp4")
    transcript = _engine().recognize_video(
        _video("en_static.mp4"),
        language="en",
        region=(0.05, 0.72, 0.9, 0.24),
        save_raw=False,
    )
    assert transcript.region_source == "manual"
    assert "subtitle" in " ".join(item.text.lower() for item in transcript.cues)


def test_does_not_ocr_every_frame():
    _require("zh_static.mp4")
    analysis = MediaAnalyzer().analyze(_video("zh_static.mp4"))
    fps = analysis.primary_video.fps or 25
    source_frames = max(1, int((analysis.duration_ms / 1000) * fps))
    transcript = _engine().recognize_video(_video("zh_static.mp4"), language="zh", save_raw=False)
    assert transcript.frames_decoded < source_frames
    assert transcript.frames_ocr < transcript.frames_decoded
    assert transcript.frames_ocr <= 12


def test_blank_video_has_no_fake_text():
    _require("blank.mp4")
    with pytest.raises(OCRError):
        _engine().recognize_video(_video("blank.mp4"), save_raw=False)


def test_scene_change_still_reads_text():
    _require("zh_scene.mp4")
    transcript = _engine().recognize_video(_video("zh_scene.mp4"), language="zh", save_raw=False)
    blob = "".join(item.text for item in transcript.cues)
    assert "字幕" in blob or "场景" in blob


def test_cpu_device():
    _require("en_static.mp4")
    transcript = _engine().recognize_video(
        _video("en_static.mp4"),
        language="en",
        device_preference="cpu",
        prefer_gpu=False,
        save_raw=False,
    )
    assert transcript.device == "cpu"
    assert transcript.cues


def test_ui_source_has_no_rapidocr_sdk():
    root = install_root() / "src" / "localvideoai" / "ui"
    for path in root.rglob("*.py"):
        blob = path.read_text(encoding="utf-8")
        assert "rapidocr" not in blob
        assert "onnxruntime" not in blob


def test_ui_ocr_fills_table(qt_app, main_window):
    _require("zh_static.mp4")
    assert main_window.side_panel.ocr_button.isEnabled()
    main_window.add_video_path(_video("zh_static.mp4"))
    qt_app.processEvents()
    transcript = main_window.ocr_current_media()
    qt_app.processEvents()
    assert transcript.cues
    assert main_window.subtitle_page.table.rowCount() >= 1
    assert main_window.subtitle_page.table.item(0, 4).text()
