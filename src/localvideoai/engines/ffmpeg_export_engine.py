"""Local FFmpeg export. UI talks to this engine, not to an encoder SDK."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from localvideoai.core.exceptions import ExportError
from localvideoai.core.types import ExportRequest
from localvideoai.engines.export_engine import ExportEngine
from localvideoai.export.compat import check_player_compatibility
from localvideoai.export.ffmpeg_cmd import remux_or_encode
from localvideoai.export.planner import plan_export
from localvideoai.export.project_bundle import write_project_bundle
from localvideoai.export.subtitles import build_tracks, write_sidecars, write_subtitle_file
from localvideoai.export.types import ExportResult
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.subtitles.io import load_subtitle

Progress = Callable[[int, int, str], None]


class FFmpegExportEngine(ExportEngine):
    def __init__(self, analyzer: MediaAnalyzer | None = None) -> None:
        self._analyzer = analyzer or MediaAnalyzer()

    @property
    def engine_id(self) -> str:
        return "ffmpeg-export"

    @property
    def display_name(self) -> str:
        return "FFmpeg Export Engine"

    def export(self, request: ExportRequest) -> Path:
        return self.export_detailed(request).output_path

    def export_detailed(self, request: ExportRequest, progress: Progress | None = None) -> ExportResult:
        video = request.video_path.expanduser().resolve()
        if not video.is_file():
            raise ExportError(f"没有可导出的视频：{video}")
        document = None
        if request.subtitle_path and request.subtitle_path.is_file():
            document = load_subtitle(request.subtitle_path)
        analysis = self._analyzer.analyze(video)
        plan = plan_export(request, analysis)
        tracks = build_tracks(request, document)
        output = self._output_path(request, plan.container)
        work = output.parent / f".{output.stem}_export_tmp"
        try:
            work.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"无法创建导出临时目录（磁盘可能已满或无权限）：{work}") from exc
        notes = [plan.reason]
        try:
            temp_subs = self._materialize_tracks(tracks, work, request.subtitle_format)
            sidecar_paths = write_sidecars(tracks, output.with_suffix(""), request.subtitle_format)
            if plan.mode == "sidecar":
                remux_or_encode(
                    video,
                    output,
                    plan,
                    [],
                    duration_ms=analysis.duration_ms,
                    progress=progress,
                    work_dir=work,
                )
            elif plan.mode == "burn_in":
                if not temp_subs:
                    raise ExportError("烧录导出需要字幕")
                remux_or_encode(
                    video,
                    output,
                    plan,
                    [],
                    burn_file=temp_subs[0][0],
                    duration_ms=analysis.duration_ms,
                    progress=progress,
                    work_dir=work,
                )
            else:
                if plan.mode in {"embed", "multilingual", "project"} and not temp_subs:
                    raise ExportError("内嵌/多语言导出需要字幕")
                remux_or_encode(
                    video,
                    output,
                    plan,
                    temp_subs if plan.mode != "sidecar" else [],
                    duration_ms=analysis.duration_ms,
                    progress=progress,
                    work_dir=work,
                )
            project_file = None
            if plan.mode == "project":
                bundle_dir = output.parent if output.suffix else output
                if output.suffix:
                    bundle_dir = output.parent
                name = request.output_path.stem or video.stem
                project_file = write_project_bundle(bundle_dir, request.project_payload or {"name": name}, name)
                extra_dir = bundle_dir / "subtitles"
                extra_dir.mkdir(parents=True, exist_ok=True)
                for fmt in ("srt", "ass", "ssa", "vtt"):
                    if tracks:
                        sidecar_paths.append(write_subtitle_file(tracks[0][1], extra_dir / f"{video.stem}.{fmt}", fmt))
            compat = check_player_compatibility(output, self._analyzer)
            notes.extend(compat.notes)
            result = ExportResult(
                output_path=output,
                sidecar_paths=sidecar_paths,
                mode=plan.mode,
                encode_mode=plan.encode_mode,
                container=plan.container,
                video_codec=compat.video_codec or plan.video_codec,
                subtitle_tracks=len(compat.subtitle_codecs),
                compatibility=compat.to_dict(),
                notes=notes,
            )
            if project_file is not None:
                result.sidecar_paths.append(project_file)
            return result
        finally:
            self._cleanup(work)

    def _output_path(self, request: ExportRequest, container: str) -> Path:
        dest = request.output_path.expanduser()
        if request.mode == "project" and not dest.suffix:
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ExportError(f"无法写入导出目录（磁盘可能已满或无权限）：{dest}") from exc
            return dest / f"{dest.name}.{container}"
        if dest.suffix.lower() != f".{container}":
            dest = dest.with_suffix(f".{container}")
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"无法写入导出目录（磁盘可能已满或无权限）：{dest.parent}") from exc
        return dest

    def _materialize_tracks(self, tracks, work: Path, fmt: str) -> list[tuple[Path, str, str]]:
        files: list[tuple[Path, str, str]] = []
        embed_fmt = "vtt" if fmt == "vtt" else "srt"
        if fmt in {"ass", "ssa"}:
            embed_fmt = fmt
        for index, (spec, document) in enumerate(tracks):
            path = write_subtitle_file(document, work / f"track_{index}.{embed_fmt}", embed_fmt)
            files.append((path, spec.language or "und", spec.title or spec.language))
        return files

    def _cleanup(self, work: Path) -> None:
        if not work.is_dir():
            return
        for child in work.glob("*"):
            try:
                child.unlink()
            except OSError:
                pass
        try:
            work.rmdir()
        except OSError:
            pass
