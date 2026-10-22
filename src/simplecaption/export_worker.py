"""Export only on request; publish the output only after encoding succeeds."""
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QThread, Signal


def export_captioned_video(video: Path, subtitle: Path, destination: Path, *, blur=False, progress=None) -> Path:
    from localvideoai.export.ffmpeg_cmd import remux_or_encode
    from localvideoai.export.planner import ExportPlan
    from localvideoai.media.media_analyzer import MediaAnalyzer
    from simplecaption.cover import cover_burned_subtitles

    destination = destination.resolve()
    if destination == video.resolve():
        raise ValueError("不能覆盖原视频")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="video-export-", dir=destination.parent) as temp:
        temporary = Path(temp) / "translated.mp4"
        if blur:
            cover_burned_subtitles(video, subtitle, temporary, progress=progress)
        else:
            analysis = MediaAnalyzer().analyze(video)
            plan = ExportPlan("burn_in", "mp4", "encode", "h264", "aac", "", "烧录译文，保留原画面")
            remux_or_encode(video, temporary, plan, [], burn_file=subtitle,
                            duration_ms=analysis.duration_ms, progress=progress, work_dir=Path(temp))
        temporary.replace(destination)
    return destination


class VideoExportWorker(QThread):
    progressChanged = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, video, subtitle, destination, *, blur=False, parent=None):
        super().__init__(parent)
        self.video, self.subtitle, self.destination = video, subtitle, destination
        self.blur = blur

    def run(self):
        try:
            path = export_captioned_video(self.video, self.subtitle, self.destination,
                blur=self.blur, progress=lambda a, b, c: self.progressChanged.emit(a, b, c))
        except Exception as exc:
            self.failed.emit(f"视频导出失败（原视频未修改）：{exc}")
            return
        self.succeeded.emit(path)
