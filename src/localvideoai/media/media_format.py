from __future__ import annotations

from localvideoai.core.types import AudioTrackInfo, MediaAnalysis, SubtitleTrackInfo, VideoTrackInfo


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{size} {unit}"
    return f"{value:.2f} {unit}（{size} 字节）"


def format_duration_ms(ms: int) -> str:
    total = max(0, int(ms))
    hours, rem = divmod(total // 1000, 3600)
    minutes, seconds = divmod(rem, 60)
    millis = total % 1000
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def format_language(value: str | None) -> str:
    if not value:
        return "未标明"
    lowered = value.strip().lower()
    if lowered in {"und", "unknown", "unk"}:
        return f"{value}（未标明）"
    return value


def format_fps(fps: float | None) -> str:
    if fps is None:
        return "未知"
    if abs(fps - round(fps)) < 0.01:
        return f"{int(round(fps))} fps"
        text = f"{fps:.3f}".rstrip("0").rstrip(".")
        return f"{text} fps"


def format_video_section(analysis: MediaAnalysis) -> str:
    video = analysis.primary_video
    lines = [
        f"文件：{analysis.path.name}",
        f"路径：{analysis.path}",
        f"大小：{format_bytes(analysis.size_bytes)}",
        f"时长：{format_duration_ms(analysis.duration_ms)}",
        f"容器：{analysis.format_name}",
    ]
    if video is None:
        lines.append("未检测到视频轨道。")
        return "\n".join(lines)
    resolution = "未知"
    if video.width and video.height:
        resolution = f"{video.width}×{video.height}"
    lines.extend(
        [
            f"分辨率：{resolution}",
            f"帧率：{format_fps(video.fps)}",
            f"视频编码：{video.codec}",
            f"视频轨道编号：{video.index}",
        ]
    )
    if len(analysis.video_tracks) > 1:
        lines.append(f"视频轨道数：{len(analysis.video_tracks)}")
        for track in analysis.video_tracks[1:]:
            lines.append(_format_extra_video(track))
    return "\n".join(lines)


def format_audio_section(analysis: MediaAnalysis) -> str:
    if not analysis.audio_tracks:
        return "未检测到音频轨道。"
    blocks = [f"音频轨道数：{len(analysis.audio_tracks)}"]
    for track in analysis.audio_tracks:
        blocks.append(_format_audio_track(track))
    return "\n\n".join(blocks)


def format_subtitle_section(analysis: MediaAnalysis) -> str:
    if not analysis.has_embedded_subtitles:
        return "是否存在内嵌字幕：否\n未检测到内嵌字幕轨道。"
    lines = [
        "是否存在内嵌字幕：是",
        f"字幕轨道数：{len(analysis.subtitle_tracks)}",
    ]
    for ordinal, track in enumerate(analysis.subtitle_tracks):
        lines.append(_format_subtitle_track(ordinal, track))
    return "\n".join(lines)


def _format_extra_video(track: VideoTrackInfo) -> str:
    size = f"{track.width}×{track.height}" if track.width and track.height else "未知分辨率"
    return f"  额外视频轨道 {track.index}：{track.codec} {size} {format_fps(track.fps)}"


def _format_audio_track(track: AudioTrackInfo) -> str:
    layout = track.channel_layout or (f"{track.channels} 声道" if track.channels is not None else "未知")
    sample = f"{track.sample_rate} Hz" if track.sample_rate else "未知"
    channels = str(track.channels) if track.channels is not None else "未知"
    return "\n".join(
        [
            f"轨道编号：{track.index}",
            f"音频编码：{track.codec}",
            f"采样率：{sample}",
            f"声道：{channels}（{layout}）",
            f"语言：{format_language(track.language)}",
        ]
    )


def _format_subtitle_track(ordinal: int, track: SubtitleTrackInfo) -> str:
    title = f"  标题：{track.title}" if track.title else None
    default = "  默认轨道：是" if track.is_default else None
    lines = [
        f"字幕轨道 {ordinal}",
        f"  编号：{track.index}",
        f"  语言：{format_language(track.language)}",
        f"  格式：{track.format_name}",
        f"  编码：{track.codec}",
    ]
    if title:
        lines.append(title)
    if default:
        lines.append(default)
    return "\n".join(lines)
