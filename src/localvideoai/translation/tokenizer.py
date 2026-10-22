"""Local SentencePiece wrappers. No Transformers in the translation hot path."""

from __future__ import annotations

import json
from pathlib import Path

from localvideoai.core.exceptions import TranslationError
from localvideoai.translation.store import tokenizer_kind


class LocalTokenizer:
    def encode(self, sentence: str) -> list[str]:
        raise NotImplementedError

    def decode(self, tokens: list[str]) -> str:
        raise NotImplementedError


class SharedSentencePieceTokenizer(LocalTokenizer):
    def __init__(self, model_file: Path) -> None:
        self._sp = _load_sentencepiece(model_file)

    def encode(self, sentence: str) -> list[str]:
        return list(self._sp.encode(sentence, out_type=str))

    def decode(self, tokens: list[str]) -> str:
        cleaned = [token for token in tokens if not _is_special_token(token)]
        text = self._sp.decode_pieces(cleaned)
        return text.replace("▁", " ").replace("_", " ").strip()


class DualSentencePieceTokenizer(LocalTokenizer):
    def __init__(self, source_file: Path, target_file: Path, append_eos: bool = True) -> None:
        self._source = _load_sentencepiece(source_file)
        self._target = _load_sentencepiece(target_file)
        self.append_eos = append_eos

    def encode(self, sentence: str) -> list[str]:
        tokens = list(self._source.encode(sentence, out_type=str))
        if self.append_eos and (not tokens or tokens[-1] != "</s>"):
            tokens.append("</s>")
        return tokens

    def decode(self, tokens: list[str]) -> str:
        cleaned = [token for token in tokens if not _is_special_token(token)]
        return self._target.decode(cleaned).strip()


def _load_sentencepiece(model_file: Path):
    """Load SentencePiece from bytes so Windows Unicode install paths work."""
    try:
        import sentencepiece as spm
    except ImportError as exc:
        raise TranslationError("未安装 sentencepiece，无法分词。请在项目虚拟环境中安装依赖。") from exc
    if not model_file.is_file():
        raise TranslationError(f"翻译模型缺少 SentencePiece 文件：{model_file}")
    processor = spm.SentencePieceProcessor()
    try:
        ok = processor.LoadFromSerializedProto(model_file.read_bytes())
    except Exception as exc:
        raise TranslationError(f"无法读取 SentencePiece 词表：{model_file}") from exc
    if not ok:
        raise TranslationError(f"SentencePiece 词表无效：{model_file}")
    return processor


def source_affixes(root: Path) -> tuple[str | None, str | None]:
    """Read CTranslate2/Argos source BOS/EOS from the model config, if present."""
    for candidate in (root / "model" / "config.json", root / "config.json"):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        bos = str(data.get("bos_token") or "").strip() if data.get("add_source_bos") else ""
        eos = str(data.get("eos_token") or "").strip() if data.get("add_source_eos") else ""
        return (bos or None, eos or None)
    return None, None


def _is_special_token(token: str) -> bool:
    text = token or ""
    if text in {"</s>", "<unk>", "<s>", "<pad>"}:
        return True
    return text.startswith(">>") and text.endswith("<<")


class AffixedTokenizer(LocalTokenizer):
    """Prepend/append model-required source tokens without changing the SPM files."""

    def __init__(self, inner: LocalTokenizer, bos: str | None, eos: str | None) -> None:
        self._inner = inner
        self.bos = bos
        self.eos = eos

    def encode(self, sentence: str) -> list[str]:
        tokens = list(self._inner.encode(sentence))
        if self.bos and (not tokens or tokens[0] != self.bos):
            tokens = [self.bos, *tokens]
        if self.eos and (not tokens or tokens[-1] != self.eos):
            tokens.append(self.eos)
        return tokens

    def decode(self, tokens: list[str]) -> str:
        return self._inner.decode(tokens)


def load_tokenizer(root: Path) -> LocalTokenizer:
    kind = tokenizer_kind(root)
    if kind == "shared_spm":
        tokenizer: LocalTokenizer = SharedSentencePieceTokenizer(root / "sentencepiece.model")
    elif kind == "dual_spm":
        tokenizer = DualSentencePieceTokenizer(root / "source.spm", root / "target.spm")
    else:
        raise TranslationError(f"翻译模型缺少 SentencePiece 词表：{root}")
    bos, eos = source_affixes(root)
    if bos or eos:
        return AffixedTokenizer(tokenizer, bos, eos)
    return tokenizer
