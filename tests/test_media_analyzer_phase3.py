from __future__ import annotations

import pytest

from localvideoai.core.exceptions import MediaError
from localvideoai.core.paths import install_root
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.media.media_format import format_subtitle_section, format_video_section


def _phase3(name: str):
    return install_root() / "test_assets" / "videos" / "phase3" / name


def test_plain_mp4_has_no_embedded_subtitles():
    path = _phase3("无字幕.mp4")
    analysis = MediaAnalyzer().analyze(path)
    assert analysis.size_bytes == path.stat().st_size
    assert analysis.duration_ms >= 2900
    video = analysis.primary_video
    assert video is not None
    assert video.width == 1280
    assert video.height == 720
    assert video.fps is not None and abs(video.fps - 30) < 0.05
    assert video.codec.lower().startswith("h264") or video.codec.lower() == "h264"
    assert len(analysis.audio_tracks) == 1
    audio = analysis.audio_tracks[0]
    assert audio.codec.lower() == "aac"
    assert audio.sample_rate == 44100
    assert audio.channels == 1
    assert analysis.has_embedded_subtitles is False
    assert analysis.subtitle_tracks == []
    text = format_subtitle_section(analysis)
    assert "是否存在内嵌字幕：否" in text


def test_single_subtitle_mkv():
    analysis = MediaAnalyzer().analyze(_phase3("单字幕.mkv"))
    assert analysis.has_embedded_subtitles is True
    assert len(analysis.subtitle_tracks) == 1
    track = analysis.subtitle_tracks[0]
    assert track.index >= 0
    assert (track.language or "").lower() in {"eng", "en"}
    assert track.format_name in {"SRT", "SUBRIP"}
    assert "编号" in format_subtitle_section(analysis)
    assert "SRT" in format_subtitle_section(analysis) or "SUBRIP" in format_subtitle_section(analysis)


def test_multiple_subtitle_mkv():
    analysis = MediaAnalyzer().analyze(_phase3("多字幕.mkv"))
    assert analysis.has_embedded_subtitles is True
    assert len(analysis.subtitle_tracks) == 2
    languages = {(track.language or "").lower() for track in analysis.subtitle_tracks}
    formats = {track.format_name for track in analysis.subtitle_tracks}
    indexes = [track.index for track in analysis.subtitle_tracks]
    assert "eng" in languages or "en" in languages
    assert "chi" in languages or "zho" in languages or "zh" in languages
    assert "SRT" in formats or "SUBRIP" in formats
    assert "ASS" in formats
    assert indexes == sorted(indexes)
    assert len(set(indexes)) == 2
    section = format_subtitle_section(analysis)
    assert "字幕轨道数：2" in section
    assert "编号" in section
    assert "语言" in section
    assert "格式" in section


def test_multiple_audio_tracks():
    analysis = MediaAnalyzer().analyze(_phase3("多音轨.mkv"))
    assert len(analysis.audio_tracks) == 2
    codecs = {track.codec.lower() for track in analysis.audio_tracks}
    rates = {track.sample_rate for track in analysis.audio_tracks}
    languages = {(track.language or "").lower() for track in analysis.audio_tracks}
    assert "aac" in codecs
    assert 44100 in rates
    assert 48000 in rates
    assert "eng" in languages or "en" in languages
    assert "jpn" in languages or "ja" in languages
    channels = {track.channels for track in analysis.audio_tracks}
    assert 1 in channels
    assert 2 in channels


def test_chinese_path_analysis():
    path = install_root() / "test_assets" / "videos" / "phase3" / "中文路径" / "多字幕.mkv"
    analysis = MediaAnalyzer().analyze(path)
    assert "中文路径" in str(analysis.path)
    assert analysis.has_embedded_subtitles
    assert len(analysis.subtitle_tracks) == 2
    assert "1280×720" in format_video_section(analysis)


def test_empty_file_raises_clear_error():
    with pytest.raises(MediaError, match="无法读取视频") as exc:
        MediaAnalyzer().analyze(_phase3("空文件.mp4"))
    assert "空" in str(exc.value)


def test_damaged_file_raises_clear_error():
    with pytest.raises(MediaError, match="无法读取视频") as exc:
        MediaAnalyzer().analyze(_phase3("损坏.mp4"))
    assert "损坏.mp4" in str(exc.value)


def test_missing_file_raises_clear_error():
    missing = _phase3("不存在的文件.mp4")
    with pytest.raises(MediaError, match="无法读取视频") as exc:
        MediaAnalyzer().analyze(missing)
    assert "不存在" in str(exc.value)


def test_ui_shows_media_info(qt_app, main_window):
    path = _phase3("多字幕.mkv")
    main_window.add_video_path(path)
    qt_app.processEvents()
    video_text = main_window.side_panel.media_info.video_info.toPlainText()
    audio_text = main_window.side_panel.media_info.audio_info.toPlainText()
    subtitle_text = main_window.side_panel.media_info.subtitle_info.toPlainText()
    assert "1280×720" in video_text
    assert "h264" in video_text.lower()
    assert "30" in video_text
    assert "aac" in audio_text.lower()
    assert "44100" in audio_text
    assert "是否存在内嵌字幕：是" in subtitle_text
    assert "字幕轨道数：2" in subtitle_text
    assert main_window.side_panel.tabs.tabText(0) == "媒体"


def test_ui_shows_error_for_unreadable_video(qt_app, main_window):
    main_window.add_video_path(_phase3("损坏.mp4"))
    qt_app.processEvents()
    video_text = main_window.side_panel.media_info.video_info.toPlainText()
    assert "无法读取视频" in video_text
    assert not main_window.timeline.play_button.isEnabled()
