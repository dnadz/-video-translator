from __future__ import annotations

from pathlib import Path

from localvideoai.core.types import ExportRequest, SubtitleSegment
from localvideoai.export.subtitles import build_tracks
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.speech.selector import select_speech_model
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.store import find_translation_model_dir
from localvideoai.translation.tokenizer import load_tokenizer, source_affixes
from localvideoai.ui.dialogs.export_dialog import ExportDialog
from localvideoai.ui import strings

from tests.conftest import make_report


def _gpu_report():
    report = make_report()
    from localvideoai.hardware.hardware_manager import GpuInfo

    report.gpus = [
        GpuInfo(
            name="NVIDIA GeForce RTX 3060 Ti",
            vram_mb=8192,
            driver="551.76",
            cuda_driver_version="12.4",
            source="nvidia-smi",
        )
    ]
    return report


def test_gpu_falls_back_to_medium_before_small():
    report = _gpu_report()
    choice = select_speech_model(report, prefer_gpu=True, available={"tiny", "small", "medium"})
    assert choice.model_id == "medium"
    assert choice.device == "cuda"


def test_export_dialog_defaults_to_embed(qt_app):
    dialog = ExportDialog()
    assert dialog.mode_combo.currentData() == "embed"
    assert dialog.values()["mode"] == "embed"
    assert dialog.mode_combo.itemData(0) == "embed"
    assert strings.EXPORT_EMBED.startswith("视频+中文字幕")


def test_settings_default_export_mode_is_embed(isolated_env):
    settings = SettingsManager()
    assert settings.get("export.mode") == "embed"
    assert settings.get("export.burn_in") is False


def test_embed_export_uses_chinese_translation():
    document = SubtitleDocument(
        segments=[
            SubtitleSegment(
                id=1,
                start_time=0,
                end_time=1000,
                source_text="It's a nice day.",
                translated_text="今天天气很好。",
                language="en",
            )
        ],
        format_name="srt",
        detected_language="en",
    )
    request = ExportRequest(
        video_path=Path("src.mp4"),
        subtitle_path=None,
        output_path=Path("out.mp4"),
        mode="embed",
    )
    tracks = build_tracks(request, document)
    assert len(tracks) == 1
    spec, rendered = tracks[0]
    assert spec.text_role == "translated"
    assert spec.language == "chi"
    assert "今天天气很好" in rendered.segments[0].source_text


def test_en_zh_tokenizer_adds_chinese_language_token():
    root = find_translation_model_dir("argos-en-zh")
    assert root is not None
    bos, eos = source_affixes(root)
    assert bos == ">>cmn_Hans<<"
    assert eos == "</s>"
    tokens = load_tokenizer(root).encode("It's a nice day.")
    assert tokens[0] == ">>cmn_Hans<<"
    assert tokens[-1] == "</s>"


def test_english_contraction_variants_prefer_expanded_form():
    from localvideoai.translation.normalize import english_source_variants, expand_english_contractions

    assert expand_english_contractions("It's a nice day.") == "it is a nice day."
    variants = english_source_variants("It's a nice day.")
    assert variants[0] == "it is a nice day."
    assert "It's a nice day." in variants


def test_en_zh_live_quality_is_not_hallucination():
    from localvideoai.core.types import TranslationRequest
    from localvideoai.engines import create_translation_engine
    from localvideoai.translation.store import list_local_translation_models

    if "argos-en-zh" not in set(list_local_translation_models()):
        return
    engine = create_translation_engine(_gpu_report())
    result = engine.translate(
        TranslationRequest("It's a nice day.", "en", "zh", device_preference="cpu")
    )
    text = result.text.strip()
    assert text
    assert result.via_memory is False
    assert "今时善财" not in text
    assert "优婆塞" not in text
    assert any(token in text for token in ("天气", "今天", "好", "晴"))
