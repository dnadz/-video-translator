"""Phase 21 final QA. No new features. Real local models, network disabled for AI I/O."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LOCALVIDEOAI_SKIP_RECOVERY", "1")

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import ExportRequest, SubtitleSegment, TranslationRequest
from localvideoai.engines import (
    create_export_engine,
    create_ocr_engine,
    create_speech_engine,
    create_translation_engine,
)
from localvideoai.hardware.hardware_manager import HardwareManager
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.store import is_ocr_ready
from localvideoai.speech.store import list_local_models
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.translation.store import list_local_translation_models


def _run(command: list[str], env: dict[str, str] | None = None, timeout: int | None = None) -> dict[str, object]:
    started = time.time()
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        env=env,
        timeout=timeout,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "ok": completed.returncode == 0,
        "stdout": (completed.stdout or "")[-4000:],
        "stderr": (completed.stderr or "")[-4000:],
        "seconds": round(time.time() - started, 2),
    }


@contextmanager
def network_disabled():
    original = socket.socket

    class BlockedSocket(socket.socket):
        def __init__(self, *args, **kwargs):
            raise OSError("Phase 21: network disabled")

    socket.socket = BlockedSocket  # type: ignore[misc,assignment]
    try:
        yield
    finally:
        socket.socket = original  # type: ignore[misc]


def hardware() -> dict[str, object]:
    report = HardwareManager().detect()
    gpu = report.gpus[0] if report.gpus else None
    return {
        "os": report.os_caption,
        "cpu": report.cpu_name,
        "cpu_logical": report.cpu_logical,
        "ram_gb": report.ram_total_gb,
        "ram_available_gb": report.ram_available_gb,
        "gpu": gpu.name if gpu else None,
        "vram_mb": gpu.vram_mb if gpu else None,
        "version": __version__,
    }


def step(name: str, fn) -> dict[str, object]:
    started = time.time()
    try:
        detail = fn()
        return {"name": name, "ok": True, "seconds": round(time.time() - started, 2), "detail": detail}
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "seconds": round(time.time() - started, 2),
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-2500:],
        }


def offline_core(root: Path, out: Path) -> dict[str, object]:
    notes: dict[str, object] = {
        "speech_models": list_local_models(),
        "ocr_ready": is_ocr_ready(),
        "translation_models": list_local_translation_models(),
    }
    if "tiny" not in notes["speech_models"] and "small" not in notes["speech_models"]:
        raise RuntimeError("没有已安装的本地语音模型")
    if not notes["ocr_ready"]:
        raise RuntimeError("没有已安装的本地 OCR 模型")
    if not notes["translation_models"]:
        raise RuntimeError("没有已安装的本地翻译模型")
    video = root / "test_assets" / "videos" / "10秒_测试.mp4"
    wav = root / "test_assets" / "audio" / "phase6" / "zh_normal.wav"
    with network_disabled():
        analysis = MediaAnalyzer().analyze(video)
        notes["duration_ms"] = analysis.duration_ms
        model_id = "tiny" if "tiny" in notes["speech_models"] else "small"
        transcript = create_speech_engine().transcribe_media(
            wav, language="zh", model_id=model_id, save_raw=False, prefer_gpu=True
        )
        notes["asr_segments"] = len(transcript.segments)
        notes["asr_device"] = transcript.device
        notes["asr_text"] = transcript.segments[0].text if transcript.segments else ""
        ocr_video = root / "test_assets" / "videos" / "phase7" / "zh_static.mp4"
        if not ocr_video.is_file():
            ocr_video = video
        ocr = create_ocr_engine().recognize_video(ocr_video, language="zh", save_raw=False)
        notes["ocr_segments"] = len(ocr.cues)
        notes["ocr_device"] = ocr.device
        translated = create_translation_engine().translate(
            TranslationRequest(text="今天天气很好。", source_lang="zh", target_lang="en")
        )
        notes["translation"] = translated.text
        notes["translation_device"] = translated.device
        subtitle = save_subtitle(
            SubtitleDocument(
                segments=[
                    SubtitleSegment(
                        id=1,
                        start_time=0,
                        end_time=1500,
                        source_text="发布验收",
                        translated_text=translated.text,
                    )
                ],
                format_name="srt",
            ),
            out / "offline.srt",
            "srt",
        )
        loaded = load_subtitle(subtitle)
        notes["subtitle_cues"] = len(loaded.segments)
        exported = create_export_engine().export_detailed(
            ExportRequest(
                video_path=video,
                subtitle_path=subtitle,
                output_path=out / "offline_out.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )
        notes["export"] = str(exported.output_path)
        notes["encode_mode"] = exported.encode_mode
        if not Path(exported.output_path).is_file():
            raise RuntimeError("离线导出没有成片")
        if not translated.text or translated.text.strip() == "今天天气很好。":
            raise RuntimeError("离线翻译没有产生译文")
        if not transcript.segments:
            raise RuntimeError("离线语音识别没有结果")
    return notes


def long_videos(root: Path, out: Path) -> dict[str, object]:
    notes = {}
    for name, minimum in (("1小时_性能.mp4", 55 * 60 * 1000), ("2小时_性能.mp4", 110 * 60 * 1000)):
        path = root / "test_assets" / "videos" / "phase19" / name
        analysis = MediaAnalyzer().analyze(path)
        if analysis.duration_ms < minimum:
            raise RuntimeError(f"{name} 时长不足：{analysis.duration_ms}")
        subtitle = save_subtitle(
            SubtitleDocument(
                segments=[SubtitleSegment(id=1, start_time=0, end_time=1000, source_text=name)],
                format_name="srt",
            ),
            out / f"{path.stem}.srt",
            "srt",
        )
        exported = create_export_engine().export_detailed(
            ExportRequest(
                video_path=path,
                subtitle_path=subtitle,
                output_path=out / f"{path.stem}.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
            )
        )
        notes[name] = {
            "duration_ms": analysis.duration_ms,
            "export": str(exported.output_path),
            "encode_mode": exported.encode_mode,
            "size": Path(exported.output_path).stat().st_size,
        }
    return notes


def ten_videos(root: Path) -> dict[str, object]:
    folder = root / "test_assets" / "videos" / "phase15"
    clips = [folder / f"clip_{index:02d}.mp4" for index in range(1, 11)]
    missing = [path.name for path in clips if not path.is_file()]
    if missing:
        raise RuntimeError(f"缺少批量样片：{missing}")
    durations = []
    for path in clips:
        analysis = MediaAnalyzer().analyze(path)
        if analysis.duration_ms <= 0:
            raise RuntimeError(f"无法分析 {path.name}")
        durations.append(analysis.duration_ms)
    return {"count": len(clips), "durations_ms": durations}


def installers(root: Path, python: Path) -> dict[str, object]:
    result = _run([str(python), str(root / "scripts" / "phase20_isolated_test.py")], timeout=400)
    if not result["ok"]:
        raise RuntimeError(result["stderr"] or result["stdout"] or "Setup/Portable 验收失败")
    return {"isolated": True, "seconds": result["seconds"]}


def pytest_suite(python: Path, extra: list[str]) -> dict[str, object]:
    command = [str(python), "-m", "pytest", "tests", "--tb=line", "-q", *extra]
    result = _run(command, timeout=None)
    if not result["ok"]:
        raise RuntimeError(result["stdout"] or result["stderr"] or "pytest 失败")
    return {"stdout": result["stdout"][-1500:], "seconds": result["seconds"]}


def main() -> int:
    root = install_root()
    python = Path(sys.executable)
    out = root / "logs" / "phase21"
    out.mkdir(parents=True, exist_ok=True)
    skip_long = "--skip-long-media" in sys.argv
    skip_installers = "--skip-installers" in sys.argv
    report: dict[str, object] = {
        "version": __version__,
        "environment": hardware(),
        "steps": [],
    }
    report["steps"].append(step("offline_asr_ocr_translate_subtitle_export", lambda: offline_core(root, out)))
    report["steps"].append(step("ten_videos_analyze", lambda: ten_videos(root)))
    report["steps"].append(step("one_and_two_hour_analyze_export", lambda: long_videos(root, out)))
    report["steps"].append(
        step(
            "pytest_default",
            lambda: pytest_suite(python, ["-m", "not long_media"]),
        )
    )
    if not skip_long:
        report["steps"].append(step("pytest_long_media", lambda: pytest_suite(python, ["-m", "long_media"])))
    if not skip_installers:
        report["steps"].append(step("setup_and_portable", lambda: installers(root, python)))
    failed = [item for item in report["steps"] if not item.get("ok")]
    report["failed"] = [item["name"] for item in failed]
    report["core_passed"] = not failed
    dest = root / "logs" / "phase21_results.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"core_passed": report["core_passed"], "failed": report["failed"]}, ensure_ascii=False, indent=2))
    print(dest)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
