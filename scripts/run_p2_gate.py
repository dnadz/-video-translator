"""P2 overall gate: unit tests + live large-v3-turbo ASR + en→zh + embed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

LOG = ROOT / "logs" / "p2_gate.txt"
REPORT = ROOT / "docs" / "p2_quality_test_report.md"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True)


def _pytest() -> tuple[bool, str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_p2_quality.py",
        "tests/test_p0_quality.py",
        "tests/test_p1_quality.py",
        "tests/test_config.py",
        "tests/test_inpaint_phase14.py",
        "tests/test_export_phase18.py",
        "tests/test_translation_phase8.py",
        "-q",
        "--tb=short",
    ]
    completed = _run(command)
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    return completed.returncode == 0, output


def _live_turbo() -> tuple[bool, list[str]]:
    from localvideoai.core.types import ExportRequest, TranslationRequest
    from localvideoai.engines import create_speech_engine, create_translation_engine
    from localvideoai.export.subtitles import build_tracks
    from localvideoai.hardware.hardware_manager import HardwareManager
    from localvideoai.speech.selector import select_speech_model
    from localvideoai.speech.store import is_model_ready, list_local_models
    from localvideoai.subtitles.document import SubtitleDocument
    from localvideoai.core.types import SubtitleSegment

    lines: list[str] = []
    ok = True
    available = set(list_local_models())
    lines.append(f"local_models={sorted(available)}")
    lines.append(f"turbo_ready={is_model_ready('large-v3-turbo')}")
    if not is_model_ready("large-v3-turbo"):
        return False, lines + ["FAIL: large-v3-turbo 未安装"]
    report = HardwareManager().detect()
    choice = select_speech_model(report, prefer_gpu=True, available=available)
    lines.append(f"choice={choice.model_id} device={choice.device} compute={choice.compute_type}")
    lines.append(f"reason={choice.reason}")
    if choice.model_id != "large-v3-turbo":
        ok = False
        lines.append("FAIL: 选择器没有选用 large-v3-turbo")
    clip = ROOT / "test_assets" / "audio" / "phase6" / "zh_normal.mp4"
    if not clip.is_file():
        return False, lines + [f"FAIL: 缺少测试片 {clip}"]
    engine = create_speech_engine(report)
    result = engine.transcribe_media(clip, language="zh", model_id="large-v3-turbo")
    text = " ".join(seg.text for seg in result.segments)
    lines.append(f"asr_model={result.model_id} device={result.device}")
    lines.append(f"asr_text={text}")
    if result.model_id != "large-v3-turbo":
        ok = False
        lines.append("FAIL: 实识别没有用 large-v3-turbo")
    if not any(token in text for token in ("天气", "本地", "识别", "中文")):
        ok = False
        lines.append("FAIL: 识别文本未命中预期中文")
    translator = create_translation_engine(report)
    translated = translator.translate(TranslationRequest("It's a nice day.", "en", "zh", device_preference="cpu"))
    lines.append(f"en_zh={translated.text}")
    if any(bad in translated.text for bad in ("今时善财", "优婆塞")):
        ok = False
        lines.append("FAIL: 英译中仍是幻觉")
    if not any(token in translated.text for token in ("天气", "今天", "好", "晴")):
        ok = False
        lines.append("FAIL: 英译中未命中合理中文")
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=1000,
                source_text="It's a nice day.",
                translated_text=translated.text,
                language="en",
            )
        ],
        format_name="srt",
        detected_language="en",
    )
    tracks = build_tracks(
        ExportRequest(video_path=clip, subtitle_path=None, output_path=clip.with_name("gate.mp4"), mode="embed"),
        document,
    )
    role = tracks[0][0].text_role
    lines.append(f"embed_role={role}")
    if role != "translated":
        ok = False
        lines.append("FAIL: embed 没有优先中文轨")
    return ok, lines


def _write(ok: bool, pytest_ok: bool, pytest_out: str, live_ok: bool, live_lines: list[str]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    body = [
        f"gate={'PASS' if ok else 'FAIL'}",
        f"pytest={'PASS' if pytest_ok else 'FAIL'}",
        f"live_turbo={'PASS' if live_ok else 'FAIL'}",
        *live_lines,
        "",
        "----- pytest -----",
        pytest_out,
    ]
    LOG.write_text("\n".join(body), encoding="utf-8")
    REPORT.write_text(
        "\n".join(
            [
                "# P2 整体测试报告",
                "",
                f"结果：**{'通过' if ok else '未通过'}**",
                "",
                "## 实时 large-v3-turbo",
                "",
                *[f"- {line}" for line in live_lines],
                "",
                "## pytest",
                "",
                "```",
                pytest_out.strip()[-4000:],
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    pytest_ok, pytest_out = _pytest()
    try:
        live_ok, live_lines = _live_turbo()
    except Exception as exc:  # noqa: BLE001 — gate must record the real failure
        live_ok, live_lines = False, [f"FAIL: live turbo 异常 {exc}"]
    ok = pytest_ok and live_ok
    _write(ok, pytest_ok, pytest_out, live_ok, live_lines)
    print(LOG)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
