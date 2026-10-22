"""OCR → locate → track → region process → repair → new subtitles."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from pathlib import Path

import numpy as np

from localvideoai.core.exceptions import InpaintError, MediaError, OCRError
from localvideoai.core.types import SubtitleSegment
from localvideoai.inpaint.compare import write_comparison
from localvideoai.inpaint.fast import inpaint_fast
from localvideoai.inpaint.io import FrameWriter, copy_video, iter_native_frames
from localvideoai.inpaint.lama import inpaint_lama, lama_available
from localvideoai.inpaint.locate import regions_from_document, regions_from_transcript
from localvideoai.inpaint.mask import mask_for_frame
from localvideoai.inpaint.overlay import cover_and_burn
from localvideoai.inpaint.quality import decide_mode, face_change_score, person_risk, residual_edge_score
from localvideoai.inpaint.temporal import TEMPORAL_RADIUS, temporal_inpaint
from localvideoai.inpaint.track import regions_at, track_regions
from localvideoai.inpaint.types import MODE_KEEP, MODE_OVERLAY, MODE_SMART, InpaintResult, TimedRegion
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.merge import text_similar
from localvideoai.ocr.region import NormalizedRegion
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import save_subtitle

ProgressCallback = Callable[[int, int, str], None]


def process_hard_subtitles(
    video_path: Path,
    destination: Path,
    *,
    mode: str = MODE_SMART,
    document: SubtitleDocument | None = None,
    ocr_engine=None,
    language: str | None = None,
    region: NormalizedRegion | None = None,
    use_ai: bool = True,
    progress: ProgressCallback | None = None,
) -> InpaintResult:
    source = video_path.expanduser().resolve()
    dest = destination.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise InpaintError(f"没有可处理的视频：{source}")
    requested = mode if mode in {MODE_KEEP, MODE_OVERLAY, MODE_SMART} else MODE_SMART
    try:
        analysis = MediaAnalyzer().analyze(source)
    except MediaError as exc:
        raise InpaintError(str(exc)) from exc
    video = analysis.primary_video
    if video is None or not video.width or not video.height:
        raise InpaintError(f"视频没有可处理的画面：{source}")
    width, height = int(video.width), int(video.height)
    fps = float(video.fps or 25.0)
    duration_ms = max(int(analysis.duration_ms), 1)
    tracks, source_document, warnings = _resolve_tracks(
        source, document, ocr_engine, language, region, progress
    )
    subtitle_path = dest.with_suffix(".srt")
    save_subtitle(_document_from_tracks(tracks, source_document), subtitle_path, "srt")
    if requested == MODE_KEEP:
        if progress:
            progress(1, 1, "保留原字幕，复制视频并写出新字幕")
        copy_video(source, dest)
        compare = write_comparison(source, dest, label="保留原字幕")
        return InpaintResult(
            output_path=dest,
            subtitle_path=subtitle_path,
            mode_requested=requested,
            mode_used=MODE_KEEP,
            recommended_mode=MODE_KEEP,
            reason="保留原硬字幕，已生成新的字幕文件",
            quality_score=100.0,
            frames_processed=0,
            used_ai=False,
            used_fast=False,
            person_risk=0.0,
            residual_text=False,
            comparison_path=compare,
            warnings=warnings,
            duration_ms=duration_ms,
            used_temporal=False,
        )
    used_ai = False
    used_fast = False
    used_temporal = False
    risk = 0.0
    residual = 0.0
    face_change = 0.0
    residual_text = False
    if requested == MODE_SMART:
        if progress:
            progress(0, 100, "探测修复质量")
        risk, residual, face_change, residual_text, used_ai, used_fast = _probe(
            source, width, height, fps, duration_ms, tracks, ocr_engine, use_ai
        )
    used_mode, recommended, reason, score = decide_mode(
        requested=requested,
        risk=risk,
        residual=residual,
        face_change=face_change,
        residual_text=residual_text,
    )
    if requested == MODE_OVERLAY:
        used_mode = MODE_OVERLAY
        recommended = MODE_OVERLAY
        reason = "覆盖原字幕并烧录新字幕"
    frames, used_temporal = _encode(
        source,
        dest,
        width,
        height,
        fps,
        duration_ms,
        tracks,
        used_mode,
        use_ai=use_ai and used_mode == MODE_SMART,
        progress=progress,
    )
    if used_mode == MODE_SMART:
        used_fast = True
        used_ai = used_ai or lama_available()
    compare = write_comparison(source, dest, label=used_mode)
    return InpaintResult(
        output_path=dest,
        subtitle_path=subtitle_path,
        mode_requested=requested,
        mode_used=used_mode,
        recommended_mode=recommended,
        reason=reason,
        quality_score=round(score, 1),
        frames_processed=frames,
        used_ai=used_ai,
        used_fast=used_fast or used_mode in {MODE_OVERLAY, MODE_SMART},
        person_risk=round(risk, 3),
        residual_text=residual_text,
        comparison_path=compare,
        warnings=warnings,
        duration_ms=duration_ms,
        used_temporal=used_temporal,
    )


def _resolve_tracks(source, document, ocr_engine, language, region, progress):
    warnings: list[str] = []
    regions: list[TimedRegion] = []
    if document is not None and document.segments:
        regions = regions_from_document(document)
    if not regions:
        if ocr_engine is None:
            raise InpaintError("没有字幕框，也没有可用的 OCR 引擎")
        if progress:
            progress(0, 100, "OCR 识别硬字幕")
        try:
            transcript = ocr_engine.recognize_video(source, language=language, region=region)
        except OCRError as exc:
            raise InpaintError(str(exc)) from exc
        regions = regions_from_transcript(transcript)
    if not regions:
        raise InpaintError("没有定位到硬字幕区域")
    return track_regions(regions), document, warnings


def _document_from_tracks(tracks: list[TimedRegion], document: SubtitleDocument | None) -> SubtitleDocument:
    if document is not None and document.segments:
        return document
    segments = [
        SubtitleSegment(
            id=index,
            start_time=item.start_ms,
            end_time=item.end_ms,
            source_text=item.text,
            extra={"ocr": {"x": item.x, "y": item.y, "w": item.w, "h": item.h}},
        )
        for index, item in enumerate(tracks, start=1)
    ]
    return SubtitleDocument(segments=segments, format_name="srt")


def _probe(source, width, height, fps, duration_ms, tracks, ocr_engine, use_ai):
    times = _probe_times(tracks, duration_ms)
    risks: list[float] = []
    residuals: list[float] = []
    faces: list[float] = []
    residual_text = False
    used_ai = False
    used_fast = False
    for time_ms in times:
        frame = _frame_at(source, width, height, fps, time_ms)
        active = regions_at(tracks, time_ms)
        mask = mask_for_frame(height, width, active)
        if mask.max() == 0:
            continue
        risks.append(person_risk(frame, mask))
        repaired, ai, fast, _temporal = _repair_frame(frame, mask, (), (), use_ai, time_ms, fps)
        used_ai = used_ai or ai
        used_fast = used_fast or fast
        residuals.append(residual_edge_score(frame, repaired, mask))
        faces.append(face_change_score(frame, repaired, mask))
        if ocr_engine is not None and _ocr_still_has_text(ocr_engine, repaired, mask, active):
            residual_text = True
    return (
        max(risks, default=0.0),
        max(residuals, default=0.0),
        max(faces, default=0.0),
        residual_text,
        used_ai,
        used_fast,
    )


def _probe_times(tracks: list[TimedRegion], duration_ms: int) -> list[int]:
    times: list[int] = []
    for item in tracks:
        mid = (item.start_ms + item.end_ms) // 2
        times.extend([item.start_ms + 80, mid, max(item.start_ms, item.end_ms - 80)])
    if not times:
        times = [min(1200, duration_ms // 2)]
    uniq = sorted({max(0, min(duration_ms, t)) for t in times})
    return uniq[:6]


def _frame_at(source: Path, width: int, height: int, fps: float, time_ms: int) -> np.ndarray:
    index = int(round((time_ms / 1000.0) * fps))
    for current, frame in enumerate(iter_native_frames(source, width, height)):
        if current >= index:
            return frame
    raise InpaintError(f"无法读取 {time_ms} ms 处的帧")


def _repair_frame(rgb, mask, past, future, use_ai: bool, time_ms: int, fps: float):
    filled, remain = temporal_inpaint(rgb, mask, past=past or (), future=future or ())
    used_temporal = bool(mask.max()) and int(remain.sum()) < int(mask.sum())
    used_ai = False
    used_fast = False
    if remain.max() == 0:
        return filled, used_ai, used_fast, used_temporal
    if use_ai and lama_available() and _should_run_ai(time_ms, fps):
        filled = inpaint_lama(filled, remain)
        used_ai = True
        return filled, used_ai, used_fast, used_temporal
    filled = inpaint_fast(filled, remain)
    used_fast = True
    return filled, used_ai, used_fast, used_temporal


def _should_run_ai(time_ms: int, fps: float) -> bool:
    step = max(1, int(round(fps / 5.0)))
    frame_index = int(round((time_ms / 1000.0) * fps))
    return frame_index % step == 0


def _ocr_still_has_text(ocr_engine, repaired: np.ndarray, mask: np.ndarray, regions: list[TimedRegion]) -> bool:
    from PIL import Image

    ys, xs = np.where(mask > 0)
    if ys.size == 0:
        return False
    crop = repaired[max(0, ys.min()) : ys.max() + 1, max(0, xs.min()) : xs.max() + 1]
    if crop.size == 0:
        return False
    from localvideoai.core.paths import logs_dir

    path = logs_dir() / "phase14_compare" / "_probe_crop.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop).save(path)
    try:
        boxes = ocr_engine.recognize_image(path)
    except Exception:
        return False
    blob = " ".join(item.text for item in boxes)
    return any(text_similar(item.text, blob) for item in regions if item.text)


def _encode(source, dest, width, height, fps, duration_ms, tracks, mode, use_ai, progress):
    writer = FrameWriter(source, dest, width, height, fps)
    total = max(1, int(round(duration_ms / 1000.0 * fps)))
    history: deque[tuple[np.ndarray, np.ndarray]] = deque(maxlen=TEMPORAL_RADIUS)
    pending: deque[tuple[np.ndarray, np.ndarray, int]] = deque()
    count = 0
    used_temporal = False

    def _emit(frame, mask, time_ms):
        nonlocal used_temporal
        if mode == MODE_OVERLAY:
            return cover_and_burn(frame, regions_at(tracks, time_ms), mask)
        if mask.max() == 0:
            return frame
        future = [(item[0], item[1]) for item in pending]
        out, _ai, _fast, temporal = _repair_frame(frame, mask, list(history), future, use_ai, time_ms, fps)
        used_temporal = used_temporal or temporal
        return out

    def _flush_one() -> None:
        nonlocal count
        frame, mask, time_ms = pending.popleft()
        writer.write(_emit(frame, mask, time_ms))
        history.append((frame, mask))
        count += 1
        if progress and (count == 1 or count % 5 == 0 or count >= total):
            progress(min(count, total), total, f"正在生成视频 {count}/{total}")

    try:
        index = 0
        for frame in iter_native_frames(source, width, height):
            time_ms = int(round(index * 1000 / fps)) if fps else index * 40
            mask = mask_for_frame(height, width, regions_at(tracks, time_ms))
            if mode == MODE_OVERLAY:
                writer.write(cover_and_burn(frame, regions_at(tracks, time_ms), mask))
                count += 1
                if progress and (count == 1 or count % 5 == 0 or count >= total):
                    progress(min(count, total), total, f"正在生成视频 {count}/{total}")
            else:
                pending.append((frame, mask, time_ms))
                while len(pending) > TEMPORAL_RADIUS:
                    _flush_one()
            index += 1
        while pending:
            _flush_one()
    finally:
        writer.close()
    if count == 0:
        raise InpaintError(f"没有写出任何帧：{source}")
    return count, used_temporal
