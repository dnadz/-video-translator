from __future__ import annotations

import os
from pathlib import Path

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import ExportRequest, SubtitleSegment
from localvideoai.engines import create_export_engine, create_speech_engine
from localvideoai.hardware.hardware_manager import GpuInfo
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.performance.cache import get_media_cache, get_model_cache, reset_performance_caches
from localvideoai.performance.policy import basic_capabilities, policy_from_report
from localvideoai.performance.profiles import classify_profile, simulate_report
from localvideoai.performance.runtime import BackgroundGate, PerformanceRuntime
from localvideoai.performance.throttle import ProgressThrottle
from localvideoai.speech.selector import select_speech_model
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import save_subtitle
from localvideoai.audio.chunker import iter_pcm_chunks
from localvideoai.audio.window import extract_pcm_window

from tests.conftest import make_report


def test_version_is_phase19():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 20)


def test_simulated_profiles_match_spec():
    low = simulate_report("low")
    mid = simulate_report("mid")
    high = simulate_report("high")
    assert classify_profile(low).profile_id == "low"
    assert classify_profile(mid).profile_id == "mid"
    assert classify_profile(high).profile_id == "high"
    assert low.ram_total_gb == 8
    assert not low.gpus
    assert mid.ram_total_gb == 16
    assert mid.gpus[0].vram_mb == 4096
    assert high.ram_total_gb == 32
    assert high.gpus[0].vram_mb == 10240


def test_low_profile_keeps_basic_cpu_functions():
    policy = policy_from_report(simulate_report("low"))
    assert policy.profile_id == "low"
    assert policy.speech_device == "cpu"
    assert policy.speech_model_hint == "tiny"
    assert policy.prefer_gpu is False
    assert policy.max_background_jobs == 1
    assert "transcribe_cpu" in basic_capabilities(policy)
    choice = select_speech_model(simulate_report("low"), prefer_gpu=True, available={"tiny", "small"})
    assert choice.device == "cpu"
    assert choice.model_id == "tiny"


def test_high_profile_uses_gpu_automatically():
    policy = policy_from_report(simulate_report("high"))
    assert policy.auto_uses_gpu
    assert policy.speech_device == "cuda"
    assert policy.translation_device == "cuda"
    choice = select_speech_model(simulate_report("high"), prefer_gpu=True, available={"tiny", "small"})
    assert choice.device == "cuda"


def test_mid_profile_has_gpu_and_16gb():
    report = simulate_report("mid")
    policy = policy_from_report(report)
    assert policy.profile_id == "mid"
    assert report.ram_total_gb == 16
    assert policy.speech_device == "cuda"
    assert policy.chunk_ms >= 20_000


def test_real_report_classification_uses_measured_values():
    report = make_report()
    report.gpus = [
        GpuInfo(
            name="NVIDIA GeForce RTX 3060 Ti",
            vram_mb=8192,
            driver="551.76",
            cuda_driver_version="12.4",
            source="nvidia-smi",
        )
    ]
    report.ram_total_gb = 32.0
    assert classify_profile(report).profile_id == "high"
    assert policy_from_report(report).auto_uses_gpu


def test_media_probe_cache_avoids_repeat_reads(tmp_path):
    reset_performance_caches()
    video = _phase19("10分钟_性能.mp4")
    analyzer = MediaAnalyzer()
    first = analyzer.analyze(video)
    hits_after_first = get_media_cache().stats.hits
    second = analyzer.analyze(video)
    assert second.duration_ms == first.duration_ms
    assert get_media_cache().stats.hits == hits_after_first + 1
    assert get_media_cache().stats.misses >= 1


def test_progress_throttle_drops_bursts():
    seen: list[int] = []
    throttle = ProgressThrottle(10_000, lambda current, total, _message: seen.append(current))
    throttle(0, 100, "start")
    throttle(10, 100, "mid")
    throttle(20, 100, "mid2")
    throttle(100, 100, "end")
    assert seen[0] == 0
    assert seen[-1] == 100
    assert throttle.dropped >= 1
    assert throttle.emitted == 2


def test_background_gate_limits_low_profile():
    gate = BackgroundGate(1)
    assert gate.try_acquire("语音识别")
    assert not gate.try_acquire("硬字幕OCR")
    gate.release("语音识别")
    assert gate.try_acquire("硬字幕OCR")


def test_hardware_is_visible_in_ui(main_window):
    snap = main_window._perf.snapshot()
    text = main_window.hardware_status.text()
    assert "CPU：" in text
    assert "GPU：" in text
    assert "VRAM：" in text
    assert "RAM：" in text
    assert snap.cpu in main_window.side_panel.hardware_label.text()
    assert main_window.settings_page.hardware_cpu.text() == snap.cpu
    assert main_window.settings_page.hardware_gpu.text() == snap.gpu
    assert main_window.settings_page.hardware_vram.text() == snap.vram
    assert main_window.settings_page.hardware_ram.text() == snap.ram


def test_low_runtime_display_and_high_runtime_auto_gpu():
    low = PerformanceRuntime(simulate_report("low"))
    high = PerformanceRuntime(simulate_report("high"))
    assert "无" in low.snapshot().gpu
    assert low.snapshot().vram == "无"
    assert "8.0" in low.snapshot().ram
    assert low.snapshot().auto_gpu is False
    assert high.snapshot().auto_gpu is True
    assert "10240" in high.snapshot().vram


def test_run_10min_1hour_2hour_videos(tmp_path):
    reset_performance_caches()
    clips = {
        "10min": _phase19("10分钟_性能.mp4"),
        "1hour": _phase19("1小时_性能.mp4"),
        "2hour": _phase19("2小时_性能.mp4"),
    }
    analyzer = MediaAnalyzer()
    rss_before = _rss_mb()
    analyses = {name: analyzer.analyze(path) for name, path in clips.items()}
    assert analyses["10min"].duration_ms >= 9 * 60 * 1000
    assert analyses["1hour"].duration_ms >= 55 * 60 * 1000
    assert analyses["2hour"].duration_ms >= 110 * 60 * 1000
    hits_before = get_media_cache().stats.hits
    for path in clips.values():
        analyzer.analyze(path)
    assert get_media_cache().stats.hits >= hits_before + 3
    for name, path in clips.items():
        duration = analyses[name].duration_ms
        head = extract_pcm_window(path, 0, 1500)
        tail = extract_pcm_window(path, max(0, duration - 2000), duration)
        assert head.sample_count > 0
        assert tail.sample_count > 0
        chunks = []
        for chunk in iter_pcm_chunks(path, duration, chunk_ms=20_000, overlap_ms=400):
            chunks.append(chunk)
            if len(chunks) >= 2:
                break
        assert len(chunks) == 2
        assert chunks[0].pcm_s16le != chunks[1].pcm_s16le or chunks[0].start_ms != chunks[1].start_ms
    engine = create_export_engine()
    sub = save_subtitle(_document(), tmp_path / "perf.srt", "srt")
    for name, path in clips.items():
        dest = tmp_path / f"{name}.mp4"
        result = engine.export_detailed(
            ExportRequest(
                video_path=path,
                subtitle_path=sub,
                output_path=dest,
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )
        assert dest.is_file() and dest.stat().st_size > 100
        assert result.encode_mode == "remux"
    rss_after = _rss_mb()
    assert rss_after - rss_before < 800


def test_model_cache_reuses_speech_runtime():
    reset_performance_caches()
    from localvideoai.speech.store import is_model_ready

    if not is_model_ready("tiny"):
        raise AssertionError("本地没有 speech/tiny，无法验证模型缓存")
    first = create_speech_engine(simulate_report("low"))
    first._load_model(select_speech_model(simulate_report("low"), available={"tiny"}))
    puts = get_model_cache().stats.puts
    hits = get_model_cache().stats.hits
    second = create_speech_engine(simulate_report("low"))
    second._load_model(select_speech_model(simulate_report("low"), available={"tiny"}))
    assert get_model_cache().stats.hits >= hits + 1
    assert get_model_cache().stats.puts == puts


def test_ui_low_profile_window_uses_cpu(isolated_env, qt_app):
    from localvideoai.managers.settings_manager import SettingsManager
    from localvideoai.ui.main_window import MainWindow

    window = MainWindow(SettingsManager(), simulate_report("low"))
    window.show()
    qt_app.processEvents()
    try:
        assert window._perf.policy.speech_device == "cpu"
        assert window._perf.policy.max_background_jobs == 1
        assert "低配置" in window.hardware_status.text()
        assert "CPU：" in window.hardware_status.text()
        assert "VRAM：" in window.hardware_status.text()
    finally:
        window.close()
        qt_app.processEvents()


def _phase19(name: str) -> Path:
    path = install_root() / "test_assets" / "videos" / "phase19" / name
    if not path.is_file():
        raise AssertionError(f"缺少 Phase 19 测试视频：{path}。请先运行 scripts/prepare_phase19_videos.py")
    return path


def _document() -> SubtitleDocument:
    return SubtitleDocument(
        segments=[
            SubtitleSegment(id=1, start_time=200, end_time=1600, source_text="性能优化", language="zh")
        ],
        format_name="srt",
        detected_language="zh",
    )


def _rss_mb() -> float:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        return counters.PrivateUsage / (1024 * 1024)
    try:
        return Path("/proc/self/statm").read_text(encoding="utf-8").split()[0]
    except OSError:
        return 0.0
