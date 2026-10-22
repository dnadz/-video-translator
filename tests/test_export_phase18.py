import inspect
from pathlib import Path

from localvideoai import __version__
from localvideoai.core.types import ExportLanguageTrack, ExportRequest, SubtitleSegment
from localvideoai.engines import create_export_engine
from localvideoai.engines.export_engine import ExportEngine
from localvideoai.engines.ffmpeg_export_engine import FFmpegExportEngine
from localvideoai.export.planner import plan_export
from localvideoai.media.ffmpeg_runtime import find_ffmpeg
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle
import subprocess


def test_version_is_phase18():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 19)


def test_export_engine_stays_abstract_and_ffmpeg_is_concrete():
    assert inspect.isabstract(ExportEngine)
    engine = create_export_engine()
    assert isinstance(engine, ExportEngine)
    assert isinstance(engine, FFmpegExportEngine)
    assert not inspect.isabstract(FFmpegExportEngine)


def test_export_subtitle_formats(tmp_path):
    document = _document()
    for fmt in ("srt", "ass", "ssa", "vtt"):
        path = save_subtitle(document, tmp_path / f"cue.{fmt}", fmt)
        loaded = load_subtitle(path)
        assert loaded.segments
        assert "你好" in loaded.segments[0].display_text()


def test_sidecar_video_plus_srt_remux(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    sub = save_subtitle(_document(), tmp_path / "src.srt", "srt")
    dest = tmp_path / "out_sidecar.mp4"
    result = create_export_engine().export_detailed(
        ExportRequest(video_path=video, subtitle_path=sub, output_path=dest, mode="sidecar", container="mp4", video_codec="copy")
    )
    assert dest.is_file() and dest.stat().st_size > 100
    assert any(path.suffix == ".srt" and path.is_file() for path in result.sidecar_paths)
    assert result.encode_mode == "remux"
    analysis = MediaAnalyzer().analyze(dest)
    assert (analysis.primary_video.codec or "").lower() in {"h264", "avc"}


def test_mp4_h264_embed_remux(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    sub = save_subtitle(_document(), tmp_path / "zh.srt", "srt")
    dest = tmp_path / "embed.h264.mp4"
    result = create_export_engine().export_detailed(
        ExportRequest(video_path=video, subtitle_path=sub, output_path=dest, mode="embed", container="mp4", video_codec="copy")
    )
    assert result.encode_mode == "remux"
    analysis = MediaAnalyzer().analyze(dest)
    assert (analysis.primary_video.codec or "").lower() in {"h264", "avc"}
    assert analysis.subtitle_tracks
    assert result.compatibility["decoded"]
    assert result.compatibility["windows_movies"]


def test_mp4_h265_encodes(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    sub = save_subtitle(_document(), tmp_path / "zh.srt", "srt")
    dest = tmp_path / "encode.hevc.mp4"
    result = create_export_engine().export_detailed(
        ExportRequest(video_path=video, subtitle_path=sub, output_path=dest, mode="embed", container="mp4", video_codec="h265")
    )
    assert result.encode_mode == "encode"
    analysis = MediaAnalyzer().analyze(dest)
    assert (analysis.primary_video.codec or "").lower() in {"hevc", "h265"}
    assert analysis.subtitle_tracks
    assert result.compatibility["decoded"]


def test_mkv_multilingual_and_burn_in(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    document = _document(translated=True)
    zh = save_subtitle(document, tmp_path / "zh.srt", "srt")
    dest = tmp_path / "multi.mkv"
    result = create_export_engine().export_detailed(
        ExportRequest(
            video_path=video,
            subtitle_path=zh,
            output_path=dest,
            mode="multilingual",
            container="mkv",
            video_codec="copy",
            tracks=(
                ExportLanguageTrack("chi", "中文", zh, "display"),
                ExportLanguageTrack("eng", "English", zh, "translated"),
            ),
        )
    )
    assert result.encode_mode == "remux"
    analysis = MediaAnalyzer().analyze(dest)
    assert len(analysis.subtitle_tracks) >= 2
    burned = tmp_path / "burned.mp4"
    burn = create_export_engine().export_detailed(
        ExportRequest(video_path=video, subtitle_path=zh, output_path=burned, mode="burn_in", container="mp4", video_codec="h264", burn_in=True)
    )
    assert burn.encode_mode == "encode"
    burned_analysis = MediaAnalyzer().analyze(burned)
    assert burned_analysis.primary_video is not None
    assert burn.compatibility["decoded"]


def test_full_project_export(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    sub = save_subtitle(_document(), tmp_path / "zh.srt", "srt")
    folder = tmp_path / "bundle"
    result = create_export_engine().export_detailed(
        ExportRequest(
            video_path=video,
            subtitle_path=sub,
            output_path=folder,
            mode="project",
            container="mp4",
            video_codec="copy",
            project_payload={"name": "导出包", "videos": [str(video)]},
        )
    )
    assert result.output_path.is_file()
    assert (folder / "manifest.json").is_file()
    assert any(path.suffix == ".vtproj" and path.is_file() for path in result.sidecar_paths)
    assert (folder / "subtitles").is_dir()
    formats = {path.suffix.lstrip(".") for path in (folder / "subtitles").iterdir()}
    assert {"srt", "ass", "ssa", "vtt"} <= formats


def test_planner_prefers_remux_unless_picture_or_codec_changes():
    from localvideoai.core.types import AudioTrackInfo, MediaAnalysis, VideoTrackInfo

    analysis = MediaAnalysis(
        path=Path("src.mp4"),
        size_bytes=1000,
        duration_ms=2000,
        format_name="mp4",
        video_tracks=[VideoTrackInfo(index=0, codec="h264", width=320, height=180, fps=25)],
        audio_tracks=[AudioTrackInfo(index=1, codec="aac", sample_rate=16000, channels=1)],
    )
    remux = plan_export(
        ExportRequest(video_path=Path("src.mp4"), subtitle_path=None, output_path=Path("out.mp4"), mode="embed", video_codec="copy"),
        analysis,
    )
    assert remux.encode_mode == "remux"
    burn = plan_export(
        ExportRequest(video_path=Path("src.mp4"), subtitle_path=None, output_path=Path("out.mp4"), mode="burn_in", burn_in=True),
        analysis,
    )
    assert burn.encode_mode == "encode"
    hevc = plan_export(
        ExportRequest(video_path=Path("src.mp4"), subtitle_path=None, output_path=Path("out.mp4"), mode="embed", video_codec="h265"),
        analysis,
    )
    assert hevc.encode_mode == "encode"


def test_webm_export(tmp_path):
    video = _make_clip(tmp_path / "src.mp4")
    sub = save_subtitle(_document(), tmp_path / "zh.srt", "srt")
    dest = tmp_path / "out.webm"
    result = create_export_engine().export_detailed(
        ExportRequest(video_path=video, subtitle_path=sub, output_path=dest, mode="embed", container="webm", video_codec="copy")
    )
    assert dest.is_file()
    assert result.encode_mode == "encode"
    analysis = MediaAnalyzer().analyze(dest)
    assert (analysis.primary_video.codec or "").lower() in {"vp8", "vp9"}
    assert result.compatibility["decoded"]


def test_ui_export_action_enabled(main_window):
    from PySide6.QtGui import QAction

    action = main_window.findChild(QAction, "action_exportMedia")
    assert action is not None and action.isEnabled()
    assert main_window.settings_page.export_format.findData("ssa") >= 0
    assert main_window.settings_page.export_container.findData("mkv") >= 0
    assert main_window.export_engine.engine_id == "ffmpeg-export"


def _document(translated: bool = False) -> SubtitleDocument:
    return SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=200,
                end_time=1600,
                source_text="你好，世界",
                translated_text="Hello, world" if translated else "",
                language="zh",
            )
        ],
        format_name="srt",
        detected_language="zh",
    )


def _make_clip(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(find_ffmpeg()),
        "-y",
        "-hide_banner",
        "-f",
        "lavfi",
        "-i",
        "color=c=blue:s=320x180:d=2",
        "-f",
        "lavfi",
        "-i",
        "sine=f=440:d=2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not destination.is_file():
        raise AssertionError(completed.stderr[-2000:])
    return destination
