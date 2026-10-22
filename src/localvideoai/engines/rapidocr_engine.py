from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np

from localvideoai.core.exceptions import MediaError, OCRError
from localvideoai.core.types import OCRBox, OCRTranscript
from localvideoai.engines.ocr_engine import OCREngine
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.managers.log_manager import get_logger
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.language import detect_script_language, normalize_ocr_language
from localvideoai.ocr.merge import boxes_to_cue, merge_cues, text_similar
from localvideoai.ocr.persist import save_ocr_transcript
from localvideoai.ocr.region import DEFAULT_BOTTOM, NormalizedRegion, region_from_boxes
from localvideoai.ocr.sampler import (
    DEFAULT_SAMPLE_FPS,
    band_signature,
    iter_sampled_frames,
    signature_changed,
)
from localvideoai.ocr.store import MODEL_ID, resolve_ocr_models
from localvideoai.performance.cache import get_model_cache
from localvideoai.performance.policy import policy_from_report

ProgressCallback = Callable[[int, int, str], None]
SUBTITLE_CHANGE_THRESHOLD = 2.8
SCENE_CHANGE_THRESHOLD = 12.0


class RapidOCREngine(OCREngine):
    """Local RapidOCR hard-subtitle engine. Samples frames; OCR only when the band changes."""

    def __init__(self, report: EnvironmentReport | None = None) -> None:
        self._logger = get_logger("ocr")
        self._report = report
        self._analyzer = MediaAnalyzer()
        self._runtime = None
        self._device = "cpu"

    @property
    def engine_id(self) -> str:
        return "rapidocr"

    @property
    def display_name(self) -> str:
        return "RapidOCR Hard Subtitle Engine"

    def recognize_image(self, image_path: Path) -> list[OCRBox]:
        source = image_path.expanduser().resolve()
        if not source.is_file():
            raise OCRError(f"没有可识别的图片：{source}")
        from PIL import Image

        array = np.array(Image.open(source).convert("RGB"))
        runtime = self._load_runtime("auto", True)
        return self._ocr_array(runtime, array, 0, array.shape[1], array.shape[0], 0, 0)

    def recognize_video(
        self,
        video_path: Path,
        language: str | None = None,
        *,
        region: NormalizedRegion | tuple[float, float, float, float] | None = None,
        device_preference: str = "auto",
        prefer_gpu: bool = True,
        sample_fps: float = DEFAULT_SAMPLE_FPS,
        save_raw: bool = True,
        raw_path: Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> OCRTranscript:
        source = video_path.expanduser().resolve()
        if not source.is_file():
            raise OCRError(f"没有可识别的视频：{source}")
        try:
            analysis = self._analyzer.analyze(source)
        except MediaError as exc:
            raise OCRError(str(exc)) from exc
        video = analysis.primary_video
        width = video.width if video else None
        height = video.height if video else None
        if not width or not height:
            raise OCRError(f"无法 OCR：没有有效画面：{source}")
        duration_ms = analysis.duration_ms
        requested = normalize_ocr_language(language)
        policy = policy_from_report(self._report)
        if sample_fps == DEFAULT_SAMPLE_FPS:
            sample_fps = policy.ocr_sample_fps
        runtime = self._load_runtime(device_preference, prefer_gpu)
        warnings: list[str] = []
        if self._device == "cpu" and (device_preference == "gpu" or (device_preference == "auto" and prefer_gpu)):
            warnings.append("本机 onnxruntime 没有 CUDA Execution Provider，硬字幕 OCR 使用 CPU。")
        manual = _coerce_region(region)
        chosen = manual or DEFAULT_BOTTOM
        region_source = "manual" if manual is not None else "auto"
        frames_decoded = 0
        frames_ocr = 0
        found_boxes: list[tuple[float, float, float, float]] = []
        last_scene = None
        last_band = None
        open_cue = None
        collected: list = []
        step_ms = int(1000 / sample_fps)
        try:
            for frame in iter_sampled_frames(source, width, height, duration_ms, sample_fps=sample_fps):
                frames_decoded += 1
                scene = band_signature(frame.rgb)
                scene_changed = signature_changed(last_scene, scene, SCENE_CHANGE_THRESHOLD)
                last_scene = scene
                crop = _crop(frame.rgb, chosen, width, height)
                band = band_signature(crop)
                subtitle_changed = signature_changed(last_band, band, SUBTITLE_CHANGE_THRESHOLD)
                hunting = open_cue is None
                should_ocr = last_band is None or subtitle_changed or scene_changed or hunting
                if not should_ocr:
                    if open_cue is not None:
                        open_cue = replace(open_cue, end_ms=max(frame.time_ms + step_ms, open_cue.end_ms))
                    if progress:
                        progress(frame.time_ms, duration_ms, f"跳过未变化帧 {frame.index + 1}")
                    continue
                last_band = band
                frames_ocr += 1
                boxes = self._ocr_region(runtime, frame, chosen)
                found_boxes.extend(_norm_boxes(boxes))
                if region_source == "auto" and found_boxes and frames_ocr <= 4:
                    chosen = region_from_boxes(found_boxes)
                cue = boxes_to_cue(boxes, frame.time_ms, frame.time_ms + step_ms, requested)
                if cue is None:
                    if open_cue is not None:
                        collected.append(open_cue)
                        open_cue = None
                    if progress:
                        progress(frame.time_ms, duration_ms, f"OCR {frame.index + 1}：无字幕")
                    continue
                if open_cue is not None and text_similar(open_cue.text, cue.text):
                    open_cue = replace(
                        open_cue,
                        end_ms=max(open_cue.end_ms, cue.end_ms),
                        confidence=cue.confidence or open_cue.confidence,
                    )
                else:
                    if open_cue is not None:
                        collected.append(open_cue)
                    open_cue = cue
                if progress:
                    progress(frame.time_ms, duration_ms, f"OCR {frame.index + 1}：{cue.text[:24]}")
            if open_cue is not None:
                collected.append(replace(open_cue, end_ms=max(open_cue.end_ms, duration_ms or open_cue.end_ms)))
        except OCRError:
            raise
        except Exception as exc:
            raise OCRError(f"本地硬字幕 OCR 失败：{exc}") from exc
        if region_source == "auto" and found_boxes:
            chosen = region_from_boxes(found_boxes)
        cues = merge_cues(collected)
        blob = "\n".join(item.text for item in cues)
        language_out = requested or detect_script_language(blob)
        if not cues:
            raise OCRError(f"没有识别到硬字幕文字：{source}")
        transcript = OCRTranscript(
            cues=cues,
            language=language_out,
            model_id=MODEL_ID,
            device=self._device,
            source_path=source,
            region=chosen.as_tuple(),
            region_source=region_source,
            duration_ms=duration_ms,
            frames_decoded=frames_decoded,
            frames_ocr=frames_ocr,
            warnings=warnings,
        )
        self._logger.info(
            "OCR %s lang=%s device=%s decoded=%s ocr=%s cues=%s",
            source.name,
            transcript.language,
            transcript.device,
            frames_decoded,
            frames_ocr,
            len(cues),
        )
        if save_raw:
            transcript.raw_path = save_ocr_transcript(transcript, raw_path)
        return transcript

    def _load_runtime(self, device_preference: str, prefer_gpu: bool):
        if self._runtime is not None:
            return self._runtime
        backend = _ocr_backend(device_preference, prefer_gpu)
        cache_key = ("ocr", MODEL_ID, backend)
        cached = get_model_cache().get(cache_key)
        if cached is not None:
            self._runtime = cached
            self._device = backend
            return self._runtime
        paths = resolve_ocr_models()
        try:
            from rapidocr import EngineType, RapidOCR
        except ImportError as exc:
            raise OCRError("未安装 rapidocr。请在项目虚拟环境中安装依赖。") from exc
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        params = {
            "Global.log_level": "error",
            "Det.model_path": str(paths["det"]),
            "Rec.model_path": str(paths["rec"]),
            "Cls.model_path": str(paths["cls"]),
            "Det.engine_type": EngineType.ONNXRUNTIME,
            "Rec.engine_type": EngineType.ONNXRUNTIME,
            "Cls.engine_type": EngineType.ONNXRUNTIME,
            "EngineConfig.onnxruntime.use_cuda": backend == "cuda",
            "EngineConfig.onnxruntime.use_dml": backend == "dml",
        }
        try:
            self._runtime = RapidOCR(params=params)
            self._device = backend
        except Exception as exc:
            if backend != "cpu":
                self._logger.warning("OCR %s 失败，回退 CPU：%s", backend, exc)
                params["EngineConfig.onnxruntime.use_cuda"] = False
                params["EngineConfig.onnxruntime.use_dml"] = False
                cpu_key = ("ocr", MODEL_ID, "cpu")
                cached_cpu = get_model_cache().get(cpu_key)
                if cached_cpu is not None:
                    self._runtime = cached_cpu
                    self._device = "cpu"
                    return self._runtime
                self._runtime = RapidOCR(params=params)
                self._device = "cpu"
                get_model_cache().put(cpu_key, self._runtime)
                return self._runtime
            raise OCRError(f"无法加载本地 OCR 模型：{exc}") from exc
        get_model_cache().put(cache_key, self._runtime)
        return self._runtime

    def _ocr_region(self, runtime, frame, region: NormalizedRegion) -> list[OCRBox]:
        x0, y0, x1, y1 = region.pixel_box(frame.width, frame.height)
        crop = frame.rgb[y0:y1, x0:x1]
        if crop.size == 0:
            return []
        return self._ocr_array(runtime, crop, frame.time_ms, frame.width, frame.height, x0, y0)

    def _ocr_array(
        self,
        runtime,
        array: np.ndarray,
        time_ms: int,
        full_w: int,
        full_h: int,
        offset_x: int,
        offset_y: int,
    ) -> list[OCRBox]:
        try:
            result = runtime(array)
        except Exception as exc:
            raise OCRError(f"RapidOCR 推理失败：{exc}") from exc
        texts = list(getattr(result, "txts", None) or [])
        scores = list(getattr(result, "scores", None) or [])
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return []
        out: list[OCRBox] = []
        for index, text in enumerate(texts):
            cleaned = str(text or "").strip()
            if not cleaned:
                continue
            score = float(scores[index]) if index < len(scores) else 0.0
            raw_box = boxes[index]
            points = []
            for pair in raw_box:
                px = (float(pair[0]) + offset_x) / max(full_w, 1)
                py = (float(pair[1]) + offset_y) / max(full_h, 1)
                points.append((px, py))
            out.append(
                OCRBox(
                    start_ms=time_ms,
                    end_ms=time_ms,
                    text=cleaned,
                    confidence=score,
                    points=tuple(points),
                )
            )
        return out


def _ocr_backend(device_preference: str, prefer_gpu: bool) -> str:
    if device_preference == "cpu":
        return "cpu"
    if device_preference != "gpu" and not (device_preference == "auto" and prefer_gpu):
        return "cpu"
    try:
        import onnxruntime as ort
    except ImportError:
        return "cpu"
    providers = set(ort.get_available_providers())
    if "CUDAExecutionProvider" in providers:
        return "cuda"
    if "DmlExecutionProvider" in providers:
        return "dml"
    return "cpu"


def _coerce_region(region) -> NormalizedRegion | None:
    if region is None:
        return None
    if isinstance(region, NormalizedRegion):
        return region.clamp()
    if len(region) != 4:
        raise OCRError("字幕区域必须是 (x, y, w, h) 归一化矩形")
    return NormalizedRegion(float(region[0]), float(region[1]), float(region[2]), float(region[3])).clamp()


def _crop(rgb: np.ndarray, region: NormalizedRegion, width: int, height: int) -> np.ndarray:
    x0, y0, x1, y1 = region.pixel_box(width, height)
    return rgb[y0:y1, x0:x1]


def _norm_boxes(boxes: list[OCRBox]) -> list[tuple[float, float, float, float]]:
    out = []
    for box in boxes:
        if len(box.points) < 2:
            continue
        xs = [point[0] for point in box.points]
        ys = [point[1] for point in box.points]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out
