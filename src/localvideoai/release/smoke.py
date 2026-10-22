"""Frozen-app smoke: start, import a local video, analyze, export remux. No upload."""

from __future__ import annotations

from pathlib import Path

from localvideoai.core.types import ExportRequest
from localvideoai.engines import create_export_engine
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import save_subtitle
from localvideoai.core.types import SubtitleSegment


def find_smoke_video(root: Path) -> Path:
    candidates = [
        root / "test_assets" / "videos" / "10秒_测试.mp4",
        root / "samples" / "sample.mp4",
        root / "sample.mp4",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("没有可用于发布冒烟的本地视频")


def run_release_smoke(output_dir: Path, video: Path | None = None) -> dict[str, str]:
    source = video or find_smoke_video(output_dir)
    analysis = MediaAnalyzer().analyze(source)
    if analysis.duration_ms <= 0 or analysis.primary_video is None:
        raise RuntimeError(f"视频分析失败：{source}")
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=min(1500, analysis.duration_ms or 1500),
                source_text="发布冒烟",
                language="zh",
            )
        ],
        format_name="srt",
        detected_language="zh",
    )
    work = output_dir / "release_smoke"
    work.mkdir(parents=True, exist_ok=True)
    subtitle = save_subtitle(document, work / "smoke.srt", "srt")
    dest = work / "smoke_out.mp4"
    result = create_export_engine().export_detailed(
        ExportRequest(
            video_path=source,
            subtitle_path=subtitle,
            output_path=dest,
            mode="sidecar",
            container="mp4",
            video_codec="copy",
        )
    )
    if not dest.is_file() or dest.stat().st_size < 32:
        raise RuntimeError("导出没有写出成片")
    return {
        "video": str(source),
        "duration_ms": str(analysis.duration_ms),
        "export": str(result.output_path),
        "encode_mode": result.encode_mode,
    }
