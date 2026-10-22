from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtGui import QAction

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.engines import create_inpainting_engine, create_ocr_engine
from localvideoai.engines.inpainting_engine import InpaintingEngine
from localvideoai.inpaint.compare import region_delta
from localvideoai.inpaint.io import iter_native_frames
from localvideoai.inpaint.store import is_lama_ready, lama_model_path
from localvideoai.inpaint.types import MODE_KEEP, MODE_OVERLAY, MODE_SMART
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.sampler import extract_still
from localvideoai.ocr.store import is_ocr_ready

VIDEOS = install_root() / "test_assets" / "videos" / "phase14"


def _require_videos(*names: str) -> None:
    missing = [name for name in names if not (VIDEOS / name).is_file()]
    if missing:
        pytest.fail(f"missing {missing}; run scripts/prepare_phase14_videos.py")
    if not is_ocr_ready():
        pytest.fail("no local OCR model; run scripts/prepare_phase7_models.py")


def _require_lama() -> None:
    if not is_lama_ready():
        pytest.fail(f"missing LaMa model {lama_model_path()}; run scripts/prepare_phase14_models.py")


def _mid_frame(path: Path) -> np.ndarray:
    analysis = MediaAnalyzer().analyze(path)
    video = analysis.primary_video
    assert video and video.width and video.height
    index = max(0, int(round((1.2) * float(video.fps or 25))))
    for current, frame in enumerate(iter_native_frames(path, int(video.width), int(video.height))):
        if current >= index:
            return frame
    pytest.fail(f"no frame from {path}")


def test_version_is_phase14():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 15)


def test_inpainting_engine_stays_abstract_and_factory_is_concrete():
    assert inspect.isabstract(InpaintingEngine)
    engine = create_inpainting_engine(ocr_engine=create_ocr_engine())
    assert isinstance(engine, InpaintingEngine)
    assert engine.engine_id
    assert hasattr(engine, "process_video")
    assert hasattr(engine, "remove_hard_subs")


def test_keep_mode_writes_real_video_and_srt(tmp_path):
    _require_videos("solid.mp4")
    dest = tmp_path / "solid_keep.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "solid.mp4", dest, mode=MODE_KEEP
    )
    assert dest.is_file() and dest.stat().st_size > 1000
    assert result.subtitle_path is not None and result.subtitle_path.is_file()
    assert "硬字幕" in result.subtitle_path.read_text(encoding="utf-8")
    assert result.mode_used == MODE_KEEP
    assert result.comparison_path is not None and result.comparison_path.is_file()
    assert MediaAnalyzer().analyze(dest).duration_ms >= 1500


def test_overlay_mode_changes_subtitle_band(tmp_path):
    _require_videos("solid.mp4")
    dest = tmp_path / "solid_overlay.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "solid.mp4", dest, mode=MODE_OVERLAY
    )
    assert dest.is_file() and dest.stat().st_size > 1000
    assert result.frames_processed > 10
    original = _mid_frame(VIDEOS / "solid.mp4")
    processed = _mid_frame(dest)
    h, w = original.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[int(h * 0.78) : h, int(w * 0.15) : int(w * 0.85)] = 255
    inside, outside = region_delta(original, processed, mask)
    assert inside > 8
    assert outside < inside


def test_smart_solid_background_writes_video(tmp_path):
    _require_videos("solid.mp4")
    dest = tmp_path / "solid_smart.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "solid.mp4", dest, mode=MODE_SMART
    )
    assert dest.is_file()
    assert result.frames_processed > 10
    assert result.mode_used in {MODE_SMART, MODE_OVERLAY}
    assert result.comparison_path is not None and Path(result.comparison_path).is_file()
    original = _mid_frame(VIDEOS / "solid.mp4")
    processed = _mid_frame(dest)
    assert original.shape == processed.shape
    assert float(np.mean(np.abs(original.astype(np.int16) - processed.astype(np.int16)))) > 0.5


def test_smart_complex_and_dynamic(tmp_path):
    _require_videos("complex.mp4", "dynamic.mp4")
    engine = create_inpainting_engine(ocr_engine=create_ocr_engine())
    for name in ("complex.mp4", "dynamic.mp4"):
        dest = tmp_path / f"{Path(name).stem}_smart.mp4"
        result = engine.process_video(VIDEOS / name, dest, mode=MODE_SMART)
        assert dest.is_file() and dest.stat().st_size > 1000
        assert result.frames_processed > 10
        assert result.subtitle_path is not None and result.subtitle_path.is_file()


def test_person_behind_recommends_overlay_and_keeps_head(tmp_path):
    _require_videos("person.mp4")
    dest = tmp_path / "person_smart.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "person.mp4", dest, mode=MODE_SMART
    )
    assert dest.is_file()
    assert result.recommended_mode == MODE_OVERLAY
    assert result.mode_used == MODE_OVERLAY
    assert "覆盖" in (result.reason or "")
    original = _mid_frame(VIDEOS / "person.mp4")
    processed = _mid_frame(dest)
    head = (
        np.abs(
            original[330:450, 575:705].astype(np.int16) - processed[330:450, 575:705].astype(np.int16)
        ).mean()
    )
    assert head < 18, f"head destroyed: {head}"


def test_local_ai_used_when_model_ready(tmp_path):
    _require_lama()
    _require_videos("solid.mp4")
    dest = tmp_path / "solid_ai.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "solid.mp4", dest, mode=MODE_SMART, use_ai=True
    )
    assert dest.is_file()
    if result.mode_used == MODE_SMART:
        assert result.used_ai is True


def test_ui_source_has_no_model_sdk():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"onnxruntime", "faster_whisper", "ctranslate2", "sentencepiece", "torch", "cv2"}
    offenders: list[str] = []
    for path in ui_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in forbidden:
                    offenders.append(f"{path.name} imports {name}")
    assert offenders == []


def test_side_panel_has_hardsub_controls(main_window):
    panel = main_window.side_panel
    assert panel.hardsub_button.isEnabled()
    assert panel.hardsub_button.text() == "处理硬字幕"
    assert panel.hardsub_mode_combo.findData("keep") >= 0
    assert panel.hardsub_mode_combo.findData("overlay") >= 0
    assert panel.hardsub_mode_combo.findData("smart") >= 0
    assert main_window.findChild(QAction, "action_menuHardSub") is not None


def test_comparison_stills_exist_after_process(tmp_path):
    _require_videos("solid.mp4")
    dest = tmp_path / "compare_overlay.mp4"
    result = create_inpainting_engine(ocr_engine=create_ocr_engine()).process_video(
        VIDEOS / "solid.mp4", dest, mode=MODE_OVERLAY
    )
    still = tmp_path / "orig.jpg"
    extract_still(VIDEOS / "solid.mp4", still, time_ms=1200)
    assert still.is_file()
    assert Image.open(still).size[0] >= 320
    assert result.comparison_path is not None
    assert Image.open(result.comparison_path).size[0] >= 320
