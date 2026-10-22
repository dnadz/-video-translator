from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from localvideoai.audio.chunker import iter_pcm_chunks
from localvideoai.core.paths import install_root
from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine
from localvideoai.hardware.hardware_manager import EnvironmentReport, GpuInfo
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.speech.language import normalize_speech_language
from localvideoai.speech.postprocess import correct_text
from localvideoai.speech.selector import select_speech_model
from localvideoai.speech.store import list_local_models


def _audio(name: str) -> Path:
    return install_root() / "test_assets" / "audio" / "phase6" / name


def _require(*names: str) -> None:
    for name in names:
        path = _audio(name)
        if not path.is_file():
            pytest.fail(f"missing fixture {path}; run scripts/prepare_phase6_audio.py")
    if not list_local_models():
        pytest.fail("no local speech model; run scripts/prepare_phase6_models.py")


_SHARED_ENGINE: FasterWhisperSpeechEngine | None = None


def _engine() -> FasterWhisperSpeechEngine:
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        _SHARED_ENGINE = FasterWhisperSpeechEngine()
    return _SHARED_ENGINE


def _rss_mb() -> float:
    import ctypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return 0.0
    return counters.WorkingSetSize / (1024 * 1024)


def test_language_and_correction_helpers():
    assert normalize_speech_language("zh-CN") == "zh"
    assert normalize_speech_language("jpn") == "ja"
    assert normalize_speech_language("auto") is None
    assert "谢谢" in correct_text("谢谢谢谢谢谢谢谢谢谢 你好")


def test_hardware_selects_local_model():
    report = EnvironmentReport(
        os_caption="Windows 11 Test",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12.13",
        python_executable="python",
        cpu_name="test-cpu",
        cpu_cores=6,
        cpu_logical=12,
        ram_total_gb=32.0,
        ram_available_gb=16.0,
        disks=[{"drive": "E:", "total_gb": 100.0, "free_gb": 50.0}],
        gpus=[],
        tools=[],
        project_root=".",
    )
    cpu = select_speech_model(report, prefer_gpu=False, available={"tiny", "small"})
    assert cpu.device == "cpu"
    assert cpu.model_id == "small"
    assert cpu.compute_type == "int8"
    report.gpus = [
        GpuInfo(
            name="NVIDIA GeForce RTX 3060 Ti",
            vram_mb=8192,
            driver="551.76",
            cuda_driver_version="12.4",
            source="nvidia-smi",
        )
    ]
    gpu = select_speech_model(report, prefer_gpu=True, available={"tiny", "small"})
    assert gpu.device == "cuda"
    assert gpu.model_id == "small"
    assert gpu.compute_type == "float16"
    assert "large-v3-turbo" in gpu.reason


def test_ui_source_does_not_import_model_sdk():
    root = install_root() / "src" / "localvideoai" / "ui"
    banned = ("faster_whisper", "ctranslate2", "huggingface_hub")
    for path in root.rglob("*.py"):
        blob = path.read_text(encoding="utf-8")
        for name in banned:
            assert name not in blob, f"{path} imports {name}"


def test_chunker_does_not_load_whole_file():
    _require("10min.mp3")
    analysis = MediaAnalyzer().analyze(_audio("10min.mp3"))
    sizes: list[int] = []
    count = 0
    for chunk in iter_pcm_chunks(_audio("10min.mp3"), analysis.duration_ms, chunk_ms=30_000, overlap_ms=800):
        sizes.append(len(chunk.pcm_s16le))
        count += 1
        assert len(chunk.pcm_s16le) <= 30_000 * 16 * 2 + 16000
    assert count >= 15
    assert max(sizes) < 2_000_000


def test_transcribe_chinese_normal():
    _require("zh_normal.wav")
    transcript = _engine().transcribe_media(_audio("zh_normal.wav"), language="zh", model_id="small")
    blob = "".join(item.text for item in transcript.segments)
    assert transcript.language in {"zh", "en", "ja"} or transcript.language
    assert any(token in blob for token in ("天气", "本地", "识别", "中文", "测试"))
    assert all(item.end_ms >= item.start_ms for item in transcript.segments)
    assert transcript.segments[0].start_ms >= 0
    assert transcript.raw_path is not None and transcript.raw_path.is_file()


def test_transcribe_english_normal():
    _require("en_normal.wav")
    transcript = _engine().transcribe_media(_audio("en_normal.wav"), language="en", model_id="small")
    blob = " ".join(item.text.lower() for item in transcript.segments)
    assert any(token in blob for token in ("weather", "speech", "recognition", "english", "local", "test"))
    assert transcript.language == "en"


def test_transcribe_japanese_normal():
    _require("ja_normal.wav")
    transcript = _engine().transcribe_media(_audio("ja_normal.wav"), language="ja", model_id="small")
    blob = "".join(item.text for item in transcript.segments)
    assert transcript.segments
    assert transcript.language in {"ja", "zh", "en"}
    assert any(token in blob for token in ("日本語", "音声", "テスト", "晴天", "本日", "ninshiki", "nihongo", "tesuto"))


def test_fast_speech_zh_en():
    _require("zh_fast.wav", "en_fast.wav")
    zh = _engine().transcribe_media(_audio("zh_fast.wav"), language="zh", model_id="small")
    en = _engine().transcribe_media(_audio("en_fast.wav"), language="en", model_id="small")
    assert zh.segments and en.segments
    assert "识别" in "".join(item.text for item in zh.segments) or "测试" in "".join(item.text for item in zh.segments)
    assert "test" in " ".join(item.text.lower() for item in en.segments) or "local" in " ".join(
        item.text.lower() for item in en.segments
    )


def test_multi_speaker_and_noise():
    _require("multi_speaker.wav", "zh_noise.wav")
    multi = _engine().transcribe_media(_audio("multi_speaker.wav"), language="auto", model_id="small")
    noisy = _engine().transcribe_media(_audio("zh_noise.wav"), language="zh", model_id="small")
    multi_text = "".join(item.text for item in multi.segments)
    noisy_text = "".join(item.text for item in noisy.segments)
    assert multi.segments
    assert any(token in multi_text for token in ("天气", "weather", "识别", "speech", "本地", "local"))
    assert any(token in noisy_text for token in ("天气", "本地", "识别", "中文", "测试"))


def test_auto_and_manual_language():
    _require("zh_normal.wav")
    auto = _engine().transcribe_media(_audio("zh_normal.wav"), language=None, model_id="small")
    manual = _engine().transcribe_media(_audio("zh_normal.wav"), language="zh", model_id="small")
    assert auto.language in {"zh", "en", "ja"}
    assert manual.language == "zh"
    assert auto.segments and manual.segments


def test_sentence_and_word_timestamps():
    _require("en_normal.wav")
    transcript = _engine().transcribe_media(_audio("en_normal.wav"), language="en", model_id="small")
    assert transcript.segments
    assert all(item.end_ms > item.start_ms for item in transcript.segments)
    wordy = [item for item in transcript.segments if item.words]
    assert wordy, "faster-whisper should return word timestamps"
    for segment in wordy:
        for word in segment.words:
            assert word.end_ms >= word.start_ms
            assert word.text.strip()


def test_raw_json_saved(isolated_env):
    _require("en_normal.wav")
    dest = isolated_env / "raw.json"
    transcript = _engine().transcribe_media(_audio("en_normal.wav"), language="en", model_id="small", raw_path=dest)
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "segments" in text
    assert "start_ms" in text
    assert transcript.raw_path == dest


def test_ten_minutes_chunked():
    _require("10min.mp3")
    path = _audio("10min.mp3")
    analysis = MediaAnalyzer().analyze(path)
    assert analysis.duration_ms >= 9 * 60 * 1000
    before = _rss_mb()
    transcript = _engine().transcribe_media(path, language="en", model_id="small", save_raw=False)
    after = _rss_mb()
    assert transcript.chunk_count >= 15
    assert transcript.segments[-1].end_ms >= 8 * 60 * 1000
    assert after - before < 1500


def test_cpu_path_works():
    import subprocess
    import sys

    _require("en_normal.wav")
    code = (
        "from localvideoai.core.paths import install_root\n"
        "from localvideoai.engines.faster_whisper_engine import FasterWhisperSpeechEngine\n"
        "path = install_root() / 'test_assets' / 'audio' / 'phase6' / 'en_normal.wav'\n"
        "t = FasterWhisperSpeechEngine().transcribe_media(path, language='en', "
        "device_preference='cpu', prefer_gpu=False, model_id='tiny', save_raw=False)\n"
        "assert t.device == 'cpu' and t.segments\n"
        "print('cpu-ok')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(install_root()),
    )
    assert completed.returncode == 0, completed.stderr[-2000:] + completed.stdout[-2000:]
    assert "cpu-ok" in completed.stdout


def test_gpu_or_documented_cpu_fallback():
    _require("en_normal.wav")
    transcript = _engine().transcribe_media(
        _audio("en_normal.wav"),
        language="en",
        device_preference="auto",
        prefer_gpu=True,
        model_id="small",
    )
    assert transcript.device in {"cuda", "cpu"}
    assert transcript.segments


def test_offline_socket_block(monkeypatch, isolated_env):
    _require("zh_normal.wav")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    def blocked(*_args, **_kwargs):
        raise OSError("network disabled for Phase 6 offline test")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    dest = isolated_env / "offline.json"
    transcript = _engine().transcribe_media(
        _audio("zh_normal.wav"),
        language="zh",
        model_id="small",
        raw_path=dest,
    )
    assert transcript.segments
    assert dest.is_file()


def test_ui_transcribe_button_enabled_and_fills_table(qt_app, main_window):
    _require("zh_normal.mp4")
    assert main_window.side_panel.transcribe_button.isEnabled()
    main_window.add_video_path(_audio("zh_normal.mp4"))
    qt_app.processEvents()
    transcript = main_window.transcribe_current_media()
    qt_app.processEvents()
    assert transcript.segments
    assert main_window.subtitle_page.table.rowCount() >= 1
    assert main_window.subtitle_page.table.item(0, 1).text()
    assert main_window.subtitle_page.table.item(0, 4).text()


def test_version_is_phase6():
    from localvideoai import __version__

    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 7)


@pytest.mark.long_media
def test_one_hour_and_two_hours_support():
    _require("1hour.mp3", "2hour.mp3")
    model = "small"
    hour = MediaAnalyzer().analyze(_audio("1hour.mp3"))
    two = MediaAnalyzer().analyze(_audio("2hour.mp3"))
    assert hour.duration_ms >= 55 * 60 * 1000
    assert two.duration_ms >= 110 * 60 * 1000
    engine = _engine()
    rss_loaded = _rss_mb()
    hour_result = engine.transcribe_media(
        _audio("1hour.mp3"),
        language="en",
        model_id=model,
        word_timestamps=False,
        save_raw=False,
    )
    rss_hour = _rss_mb()
    two_result = engine.transcribe_media(
        _audio("2hour.mp3"),
        language="en",
        model_id=model,
        word_timestamps=False,
        save_raw=False,
    )
    rss_two = _rss_mb()
    assert hour_result.chunk_count >= 100
    assert two_result.chunk_count >= 200
    assert hour_result.segments[-1].end_ms >= 45 * 60 * 1000
    assert two_result.segments[-1].end_ms >= 90 * 60 * 1000
    assert all(item.end_ms >= item.start_ms for item in hour_result.segments)
    assert all(item.end_ms >= item.start_ms for item in two_result.segments)
    # Long files must not add memory roughly proportional to duration.
    assert rss_two - rss_hour < 800
    assert rss_hour - rss_loaded < 800
