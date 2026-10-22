from __future__ import annotations

from pathlib import Path

from localvideoai.batch.pipeline import BatchPipeline
from localvideoai.core.types import SubtitleSegment
from localvideoai.export.subtitles import build_tracks
from localvideoai.core.types import ExportRequest
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.catalog import load_catalog
from localvideoai.translation.store import find_translation_model_dir


def test_ja_zh_prefers_direct_route_when_ready():
    catalog = load_catalog()
    ids = {item.id for item in catalog.models.values()}
    assert "opus-mt-ja-zh" in ids
    routes = [route for route in catalog.routes if route.source_lang == "ja" and route.target_lang == "zh"]
    assert routes[0].hop_ids == ("opus-mt-ja-zh",)
    resolved = catalog.resolve_route("ja", "zh")
    if find_translation_model_dir("opus-mt-ja-zh") is not None:
        assert resolved.hop_ids == ("opus-mt-ja-zh",)
    else:
        assert resolved.hop_ids == ("argos-ja-en", "argos-en-zh")


def test_batch_export_writes_translated_srt_and_mp4(tmp_path):
    video = _tiny_clip(tmp_path / "clip.mp4")
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=1000,
                source_text="本日は晴天なり。",
                translated_text="今天是晴天。",
                language="ja",
            )
        ],
        format_name="srt",
        detected_language="ja",
    )
    pipeline = BatchPipeline(
        analyzer=None,
        speech_engine=None,
        ocr_engine=None,
        translation_engine=None,
        quality_engine=None,
    )
    exported = pipeline._export_stage(video, document)
    srt = Path(exported["export_path"])
    assert srt.is_file()
    text = srt.read_text(encoding="utf-8")
    assert "今天是晴天" in text
    video_path = Path(exported.get("export_video_path") or "")
    assert video_path.is_file()
    assert video_path.suffix.lower() == ".mp4"
    assert video_path.stat().st_size > 100


def test_embed_tracks_use_chinese_for_batch_document():
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=800,
                source_text="Hello.",
                translated_text="你好。",
                language="en",
            )
        ],
        format_name="srt",
        detected_language="en",
    )
    tracks = build_tracks(ExportRequest(video_path=Path("a.mp4"), subtitle_path=None, output_path=Path("b.mp4"), mode="embed"), document)
    assert tracks[0][0].text_role == "translated"
    assert "你好" in tracks[0][1].segments[0].source_text


def _tiny_clip(path: Path) -> Path:
    from localvideoai.media.ffmpeg_runtime import find_ffmpeg
    import subprocess

    ffmpeg = find_ffmpeg()
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path
