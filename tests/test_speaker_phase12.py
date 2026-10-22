from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from localvideoai import __version__
from localvideoai.core.paths import install_root
from localvideoai.core.types import SubtitleSegment
from localvideoai.engines import create_speaker_engine
from localvideoai.engines.speaker_engine import SpeakerEngine
from localvideoai.speaker.labels import apply_speaker_rename
from localvideoai.speaker.pipeline import FALLBACK_NO_MODEL
from localvideoai.speaker.store import embedding_model_path, is_speaker_model_ready
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.subtitles.io import load_subtitle, save_subtitle

AUDIO = install_root() / "test_assets" / "audio" / "phase12"
SUBS = install_root() / "test_assets" / "subtitles" / "phase12"


def _require_model() -> None:
    if not is_speaker_model_ready():
        pytest.fail(f"missing speaker model {embedding_model_path()}; run scripts/prepare_phase12_models.py")


def _require_audio(*names: str) -> None:
    missing = [name for name in names if not (AUDIO / name).is_file()]
    if missing:
        pytest.fail(f"missing {missing}; run scripts/prepare_phase12_audio.py")


def _document_from_meta(name: str) -> tuple[SubtitleDocument, dict]:
    meta = json.loads((AUDIO / f"{name}.json").read_text(encoding="utf-8"))
    document = load_subtitle(Path(meta["srt"]))
    return document, meta


def test_version_is_phase12():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 13)


def test_speaker_engine_stays_abstract_and_factory_is_concrete():
    assert inspect.isabstract(SpeakerEngine)
    engine = create_speaker_engine()
    assert isinstance(engine, SpeakerEngine)
    assert engine.engine_id
    assert hasattr(engine, "label_document")


def test_fallback_when_model_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("localvideoai.speaker.pipeline.is_speaker_model_ready", lambda: False)
    monkeypatch.setattr("localvideoai.engines.local_speaker_engine.is_speaker_model_ready", lambda: False)
    engine = create_speaker_engine()
    document = SubtitleDocument(
        format_name="srt",
        segments=[SubtitleSegment(1, 0, 1000, source_text="你好")],
    )
    fake_audio = tmp_path / "empty.wav"
    fake_audio.write_bytes(b"RIFF" + b"\x00" * 40)
    result = engine.label_document(document, fake_audio)
    assert result.fallback is True
    assert FALLBACK_NO_MODEL in result.fallback_reason
    assert document.segments[0].speaker == ""


def test_two_person_dialogue_assigns_speakers():
    _require_model()
    _require_audio("two_person.wav")
    document, meta = _document_from_meta("two_person")
    result = create_speaker_engine().label_document(document, Path(meta["audio"]))
    assert result.fallback is False
    labels = [item.speaker for item in document.segments]
    assert all(item.startswith("Speaker ") for item in labels)
    expected = [cue["speaker"] for cue in meta["cues"]]
    a_ids = {labels[index] for index, who in enumerate(expected) if who == "A"}
    b_ids = {labels[index] for index, who in enumerate(expected) if who == "B"}
    assert len(a_ids) == 1
    assert len(b_ids) == 1
    assert a_ids != b_ids
    assert len(set(labels)) == 2


def test_three_person_dialogue_assigns_three_speakers():
    _require_model()
    _require_audio("three_person.wav")
    document, meta = _document_from_meta("three_person")
    if meta["voices"].get("A") == meta["voices"].get("C"):
        pytest.skip("本机不足 3 种 SAPI 音色，无法测三人对话")
    result = create_speaker_engine().label_document(document, Path(meta["audio"]))
    assert result.fallback is False
    labels = [str(item.extra.get("speaker_id") or item.speaker) for item in document.segments]
    expected = [cue["speaker"] for cue in meta["cues"]]
    groups = {}
    for who, label in zip(expected, labels, strict=True):
        groups.setdefault(who, set()).add(label)
    assert all(len(value) == 1 for value in groups.values())
    assert len({next(iter(value)) for value in groups.values()}) == 3


def test_different_timbre_embeddings_are_not_identical():
    _require_model()
    _require_audio("two_person.wav")
    from localvideoai.audio.window import extract_pcm_window
    from localvideoai.speaker.cluster import cosine
    from localvideoai.speaker.embed import SpeakerEmbedder

    meta = json.loads((AUDIO / "two_person.json").read_text(encoding="utf-8"))
    first = meta["cues"][0]
    second = next(item for item in meta["cues"] if item["speaker"] != first["speaker"])
    embedder = SpeakerEmbedder()
    left = embedder.embed_pcm(extract_pcm_window(Path(meta["audio"]), first["start_ms"], first["end_ms"], accurate_seek=True).pcm_s16le)
    right = embedder.embed_pcm(extract_pcm_window(Path(meta["audio"]), second["start_ms"], second["end_ms"], accurate_seek=True).pcm_s16le)
    assert left is not None and right is not None
    assert cosine(left, right) < 0.92


def test_rename_save_reopen_keeps_mapping(tmp_path):
    document = SubtitleDocument(
        format_name="srt",
        segments=[
            SubtitleSegment(1, 0, 1000, source_text="甲", speaker="Speaker 1", style_id="Speaker1", extra={"speaker_id": "Speaker 1"}),
            SubtitleSegment(2, 1000, 2000, source_text="乙", speaker="Speaker 2", style_id="Speaker2", extra={"speaker_id": "Speaker 2"}),
        ],
    )
    apply_speaker_rename(document, "Speaker 1", "张三", "Speaker1")
    apply_speaker_rename(document, "Speaker 2", "李四", "Speaker2")
    assert document.segments[0].speaker == "张三"
    assert document.speaker_map["Speaker 1"] == "张三"
    dest = tmp_path / "speakers.srt"
    save_subtitle(document, dest, "srt")
    loaded = load_subtitle(dest)
    assert loaded.segments[0].speaker == "张三"
    assert loaded.segments[1].speaker == "李四"
    assert loaded.speaker_map["Speaker 1"] == "张三"
    assert loaded.segments[0].style_id == "Speaker1"
    assert loaded.segments[1].style_id == "Speaker2"


def test_styles_written_for_speakers():
    document = SubtitleDocument(
        format_name="ass",
        segments=[
            SubtitleSegment(1, 0, 1000, source_text="甲", extra={"speaker_id": "Speaker 1"}),
        ],
    )
    apply_speaker_rename(document, "Speaker 1", "张三", "Speaker1")
    assert "Style: Speaker1" in document.style_section
    assert document.segments[0].style_id == "Speaker1"


def test_ui_source_has_no_model_sdk():
    ui_dir = install_root() / "src" / "localvideoai" / "ui"
    forbidden = {"onnxruntime", "faster_whisper", "ctranslate2", "sentencepiece", "torch"}
    offenders: list[str] = []
    for path in ui_dir.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in forbidden:
                    offenders.append(f"{path.name} imports {name}")
    assert offenders == []


def test_side_panel_has_diarize_controls(main_window):
    assert main_window.side_panel.diarize_button.isEnabled()
    assert main_window.side_panel.speaker_map_button.isEnabled()
    assert main_window.side_panel.diarize_button.text() == "说话人分离"
