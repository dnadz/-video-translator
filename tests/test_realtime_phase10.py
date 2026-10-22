from __future__ import annotations

import ast
import os
import socket
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QAction

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.engines import create_speech_engine, create_translation_engine
from localvideoai.realtime.extract import extract_pcm_window
from localvideoai.realtime.pipeline import process_realtime_window
from localvideoai.realtime.policy import DELAY_OPTIONS_MS, adjust_window_ms, normalize_delay_ms, profile_settings
from localvideoai.speech.store import list_local_models
from localvideoai.translation.store import list_local_translation_models
from tests.conftest import make_report


def _audio(name: str) -> Path:
    return install_root() / "test_assets" / "audio" / "phase6" / name


def _chinese_video() -> Path:
    return install_root() / "test_assets" / "videos" / "中文路径" / "10秒_测试.mp4"


def _require_speech(*names: str) -> None:
    for name in names:
        path = _audio(name)
        if not path.is_file():
            pytest.fail(f"missing fixture {path}")
    if not list_local_models():
        pytest.fail("no local speech model; run scripts/prepare_phase6_models.py")


def _require_translation() -> None:
    names = set(list_local_translation_models())
    if "argos-zh-en" not in names and "argos-en-zh" not in names:
        pytest.fail("missing translation models; run scripts/prepare_phase8_models.py")


def _wait(app, predicate, timeout_ms: int = 45000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(80)
    timer.timeout.connect(lambda: predicate() and loop.quit())
    fail = QTimer()
    fail.setSingleShot(True)
    fail.timeout.connect(loop.quit)
    timer.start()
    fail.start(timeout_ms)
    loop.exec()
    timer.stop()
    return bool(predicate())


def test_version_is_phase10():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 11)


def test_delay_options_and_auto_adjust():
    assert DELAY_OPTIONS_MS == (1000, 3000, 5000, 10000, 30000)
    assert normalize_delay_ms(2900) == 3000
    assert adjust_window_ms(1000, "accurate") == 3000
    assert adjust_window_ms(30000, "low") == 5000
    assert adjust_window_ms(3000, "balanced") == 3000
    grown = adjust_window_ms(3000, "balanced", 8000)
    assert grown >= 8000
    assert grown <= profile_settings("balanced").max_ms
    shrunk = adjust_window_ms(3000, "balanced", 400)
    assert shrunk == 3000


def test_extract_window_chinese_path():
    video = _chinese_video()
    if not video.is_file():
        pytest.fail(f"missing {video}")
    chunk = extract_pcm_window(video, 0, 1000)
    assert "中文路径" in str(video)
    assert chunk.end_ms > chunk.start_ms
    assert len(chunk.pcm_s16le) > 1000


def test_pipeline_cpu_produces_subtitle(isolated_env):
    _require_speech("zh_normal.wav")
    _require_translation()
    engine = create_speech_engine(make_report())
    translator = create_translation_engine(make_report())
    cue = process_realtime_window(
        _audio("zh_normal.wav"),
        0,
        3000,
        speech_engine=engine,
        translation_engine=translator,
        source_lang="zh",
        target_lang="en",
        profile="fast",
        device_preference="cpu",
        prefer_gpu=False,
    )
    assert cue.window_ms >= 2000
    assert cue.process_ms >= 0
    assert cue.source_text.strip()
    assert cue.translated_text.strip()
    assert cue.translated_text.strip() != cue.source_text.strip()
    assert cue.speech_device == "cpu"
    assert any(token in cue.source_text for token in ("天气", "本地", "识别", "中文", "测试", "今天"))


def test_offline_socket_block(monkeypatch, isolated_env):
    _require_speech("zh_normal.wav")
    _require_translation()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def blocked(*_args, **_kwargs):
        raise OSError("network disabled for Phase 10 offline test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    cue = process_realtime_window(
        _audio("zh_normal.wav"),
        0,
        3000,
        speech_engine=create_speech_engine(make_report()),
        translation_engine=create_translation_engine(make_report()),
        source_lang="zh",
        target_lang="en",
        profile="fast",
        device_preference="cpu",
        prefer_gpu=False,
    )
    assert cue.source_text.strip()
    assert cue.translated_text.strip()


def test_gpu_or_documented_cpu_fallback(isolated_env):
    _require_speech("zh_normal.wav")
    _require_translation()
    from localvideoai.hardware.hardware_manager import HardwareManager

    report = HardwareManager().detect()
    cue = process_realtime_window(
        _audio("zh_normal.wav"),
        0,
        3000,
        speech_engine=create_speech_engine(report),
        translation_engine=create_translation_engine(report),
        source_lang="zh",
        target_lang="en",
        profile="fast",
        device_preference="auto",
        prefer_gpu=True,
    )
    assert cue.source_text.strip()
    assert cue.translated_text.strip()
    if cue.speech_device == "cpu":
        assert cue.model_id


def test_ui_source_has_no_model_sdk():
    root = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"faster_whisper", "ctranslate2", "sentencepiece", "rapidocr", "onnxruntime"}
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            assert forbidden.isdisjoint(names)


def test_ui_realtime_plays_and_shows_caption(qt_app, main_window):
    _require_speech("zh_normal.wav")
    _require_translation()
    media = _audio("zh_normal.mp4")
    if not media.is_file():
        media = _audio("zh_normal.wav")
    action = main_window.findChild(QAction, "action_menuRealtime")
    assert action is not None and action.isEnabled()
    assert main_window.side_panel.realtime_button.isEnabled()
    assert [main_window.side_panel.realtime_delay_combo.itemData(i) for i in range(5)] == [
        1000,
        3000,
        5000,
        10000,
        30000,
    ]
    main_window.side_panel.realtime_profile_combo.setCurrentIndex(1)
    main_window.side_panel.realtime_delay_combo.setCurrentIndex(1)
    main_window.side_panel.source_language_combo.setCurrentIndex(
        main_window.side_panel.source_language_combo.findData("zh")
    )
    main_window.side_panel.language_combo.setCurrentIndex(main_window.side_panel.language_combo.findData("en"))
    main_window.side_panel.device_combo.setCurrentIndex(main_window.side_panel.device_combo.findData("cpu"))
    main_window.add_video_path(media)
    qt_app.processEvents()
    started_pos = main_window.playback.position_ms()
    main_window.start_realtime()
    qt_app.processEvents()
    assert main_window._realtime_active
    assert main_window.side_panel.realtime_button.text() == "停止实时翻译"
    appeared = _wait(
        qt_app,
        lambda: bool(main_window._realtime_cues and any(item.display_text() for item in main_window._realtime_cues)),
        70000,
    )
    later_pos = main_window.playback.position_ms()
    state = main_window.playback.state_name()
    caption = main_window.video_stage.caption_bar.text()
    overlay = main_window.video_stage.caption_overlay.text()
    main_window.stop_realtime()
    qt_app.processEvents()
    assert appeared
    assert later_pos >= started_pos
    assert state in {"playing", "paused"} or later_pos > started_pos
    assert caption or overlay
    assert "实时翻译进行中" in caption or any(item.source_text for item in main_window._realtime_cues)
