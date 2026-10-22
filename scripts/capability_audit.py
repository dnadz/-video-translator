"""Live capability audit against V0.1 / V0.2 / V0.3 checklists."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LOCALVIDEOAI_SKIP_RECOVERY", "1")

from localvideoai import __version__
from localvideoai.core.paths import install_root, model_search_roots
from localvideoai.core.types import ExportRequest, SubtitleSegment, TranslationRequest
from localvideoai.engines import create_export_engine, create_speech_engine, create_translation_engine
from localvideoai.hardware.hardware_manager import HardwareManager
from localvideoai.inpaint.store import is_lama_ready
from localvideoai.media.media_analyzer import MediaAnalyzer
from localvideoai.ocr.store import is_ocr_ready
from localvideoai.speaker.store import is_speaker_model_ready
from localvideoai.speech.store import is_model_present, list_local_models
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.editor import SubtitleEditor
from localvideoai.subtitles.io import load_subtitle, save_subtitle
from localvideoai.translation.store import list_local_translation_models


def _find_video() -> Path:
    root = install_root()
    preferred = root / "test_assets" / "videos" / "10秒_测试.mp4"
    if preferred.is_file() and preferred.stat().st_size > 1000:
        return preferred
    zh = root / "test_assets" / "audio" / "phase6" / "zh_normal.mp4"
    if zh.is_file():
        return zh
    videos = [p for p in (root / "test_assets").rglob("*.mp4") if p.stat().st_size > 50_000]
    if not videos:
        raise FileNotFoundError("no usable test video")
    return sorted(videos, key=lambda p: p.stat().st_size)[0]


def main() -> int:
    started = time.time()
    root = install_root()
    out_dir = root / "logs" / "capability_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = HardwareManager().detect()
    gpu = report.gpus[0] if report.gpus else None
    result: dict[str, object] = {
        "version": __version__,
        "hardware": {
            "cpu": report.cpu_name,
            "ram_gb": report.ram_total_gb,
            "gpu": gpu.name if gpu else None,
            "vram_mb": gpu.vram_mb if gpu else None,
        },
        "models": {
            "speech": list_local_models(),
            "tiny": is_model_present("tiny"),
            "small": is_model_present("small"),
            "medium": is_model_present("medium"),
            "large_v3": is_model_present("large-v3"),
            "large_v3_turbo": is_model_present("large-v3-turbo"),
            "ocr": is_ocr_ready(),
            "translation": list_local_translation_models(),
            "speaker": is_speaker_model_ready(),
            "lama": is_lama_ready(),
            "search_roots": [str(p) for p in model_search_roots()],
        },
        "exe": {
            "app": (root / "release" / "app" / "LocalVideoAI.exe").is_file(),
            "setup": (root / "release" / "LocalVideoAI_Setup.exe").is_file(),
            "portable": (root / "release" / "LocalVideoAI_Portable.exe").is_file(),
        },
        "v01": {},
        "errors": [],
    }
    video = _find_video()
    result["video"] = {"path": str(video), "size": video.stat().st_size}

    try:
        analysis = MediaAnalyzer().analyze(video)
        result["v01"]["analyze"] = {
            "ok": True,
            "duration_ms": analysis.duration_ms,
            "video_tracks": len(analysis.video_tracks),
            "audio_tracks": len(analysis.audio_tracks),
        }
    except Exception as exc:
        result["errors"].append(f"analyze: {exc}")
        result["v01"]["analyze"] = {"ok": False, "error": str(exc)}

    srt_in = out_dir / "seed.srt"
    srt_in.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world.\n", encoding="utf-8")
    try:
        loaded = load_subtitle(srt_in)
        result["v01"]["subtitle_read"] = {
            "ok": bool(loaded.segments),
            "text": loaded.segments[0].source_text if loaded.segments else "",
        }
    except Exception as exc:
        result["errors"].append(f"subtitle_read: {exc}")
        result["v01"]["subtitle_read"] = {"ok": False, "error": str(exc)}

    asr_text = "今天天气很好。"
    try:
        speech = create_speech_engine(report)
        transcript = speech.transcribe_media(video, language="zh")
        asr_text = " ".join(seg.text for seg in transcript.segments).strip() or asr_text
        result["v01"]["asr"] = {
            "ok": bool(transcript.segments),
            "device": transcript.device,
            "model": transcript.model_id,
            "segments": len(transcript.segments),
            "text": asr_text[:240],
        }
    except Exception as exc:
        result["errors"].append(f"asr: {exc}")
        result["v01"]["asr"] = {"ok": False, "error": str(exc)}

    zh_text = "今天天气很好。"
    en_text = "It's a nice day."
    try:
        engine = create_translation_engine(report)
        en = engine.translate(TranslationRequest(text=asr_text, source_lang="zh", target_lang="en"))
        zh = engine.translate(TranslationRequest(text="It's a nice day.", source_lang="en", target_lang="zh"))
        en_text = en.text
        zh_text = zh.text
        result["v01"]["translate"] = {
            "ok": bool(en.text and zh.text),
            "device": en.device,
            "model": en.model_id,
            "zh_en": en.text,
            "en_zh": zh.text,
        }
    except Exception as exc:
        result["errors"].append(f"translate: {exc}")
        result["v01"]["translate"] = {"ok": False, "error": str(exc)}

    chinese = SubtitleDocument(
        segments=[
            SubtitleSegment(1, 0, 2500, source_text=asr_text, translated_text=zh_text),
            SubtitleSegment(2, 2500, 5000, source_text="第二句。", translated_text="Second sentence."),
        ],
        format_name="srt",
    )
    try:
        editor = SubtitleEditor()
        editor.bind(chinese)
        editor.modify(1, "translated_text", en_text)
        editor.split(1, 3800)
        srt_out = save_subtitle(chinese, out_dir / "out.srt", "srt")
        ass_out = save_subtitle(chinese, out_dir / "out.ass", "ass")
        srt_body = srt_out.read_text(encoding="utf-8")
        result["v01"]["edit_export_subs"] = {
            "ok": srt_out.is_file() and ass_out.is_file(),
            "srt": srt_body[:220],
            "ass_has_dialogue": "Dialogue:" in ass_out.read_text(encoding="utf-8"),
            "editor_cues": len(editor.document.segments) if editor.document else 0,
            "has_cjk": any("\u4e00" <= ch <= "\u9fff" for ch in srt_body),
        }
    except Exception as exc:
        result["errors"].append(f"edit: {exc}")
        result["v01"]["edit_export_subs"] = {"ok": False, "error": str(exc)}

    try:
        mp4 = create_export_engine().export(
            ExportRequest(
                video_path=video,
                subtitle_path=out_dir / "out.srt",
                output_path=out_dir / "out.mp4",
                mode="sidecar",
                container="mp4",
                video_codec="copy",
                burn_in=False,
            )
        )
        result["v01"]["mp4_export"] = {"ok": mp4.is_file() and mp4.stat().st_size > 1000, "path": str(mp4), "size": mp4.stat().st_size}
    except Exception as exc:
        result["errors"].append(f"mp4: {exc}")
        result["v01"]["mp4_export"] = {"ok": False, "error": str(exc)}

    result["seconds"] = round(time.time() - started, 2)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    (out_dir / "report.json").write_text(payload, encoding="utf-8")
    print(payload)
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
