from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from localvideoai.core.exceptions import TranslationError
from localvideoai.core.types import TranslationRequest, TranslationResult
from localvideoai.engines.translation_engine import TranslationEngine
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.speech.cuda_runtime import is_cuda_runtime_error, prepare_cuda_dlls
from localvideoai.subtitles.document import SubtitleDocument
from localvideoai.translation.catalog import CatalogModel, CatalogRoute, load_catalog
from localvideoai.translation.device import resolve_translation_device
from localvideoai.translation.document import translate_document
from localvideoai.translation.language import detect_source_language, normalize_translation_language
from localvideoai.translation.protect import protect_terms, restore_terms
from localvideoai.translation.quality import beam_size_for, normalize_quality
from localvideoai.translation.resources import ResourceEntry, TranslationResources
from localvideoai.translation.store import ctranslate2_model_path
from localvideoai.performance.cache import get_model_cache
from localvideoai.translation.tokenizer import load_tokenizer
from localvideoai.translation.normalize import english_source_variants, looks_broken_zh

ProgressCallback = Callable[[int, int, str], None]
_BATCH_LIMIT = 32


@dataclass
class _Pending:
    source: str
    target: str
    quality: str
    beam: int
    device: str
    compute: str
    context_used: bool
    protected_text: str
    mapping: dict[str, str]
    glossary_hits: int
    character_hits: int
    route: CatalogRoute
    preference_key: tuple[str, bool]


class CTranslate2TranslationEngine(TranslationEngine):
    """Local CTranslate2 machine translation. Model IDs come from the catalog, not this class."""

    def __init__(
        self,
        report: EnvironmentReport | None = None,
        resources: TranslationResources | None = None,
    ) -> None:
        from localvideoai.managers.log_manager import get_logger

        self._logger = get_logger("translation")
        self._report = report
        self._resources = resources or TranslationResources()
        self._catalog = load_catalog()
        self._translators: dict[tuple[str, str, str], object] = {}
        self._tokenizers: dict[str, object] = {}
        self._device_cache: dict[tuple[str, bool], tuple[str, str]] = {}

    @property
    def engine_id(self) -> str:
        return "ctranslate2-catalog"

    @property
    def display_name(self) -> str:
        return "CTranslate2 Catalog Translation Engine"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return self.translate_many([request])[0]

    def translate_many(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        """Translate several lines with one model load. At most 8 lines share one forward pass."""
        results: list[TranslationResult | None] = [None] * len(requests)
        groups: dict[tuple, list[tuple[int, _Pending]]] = {}
        for index, request in enumerate(requests):
            begun = self._begin(request)
            if isinstance(begun, TranslationResult):
                results[index] = begun
                continue
            key = (begun.route.hop_ids, begun.beam, begun.device, begun.compute)
            groups.setdefault(key, []).append((index, begun))
        for group in groups.values():
            for start in range(0, len(group), _BATCH_LIMIT):
                piece = group[start : start + _BATCH_LIMIT]
                finished = self._finish_many([item for _, item in piece])
                for (index, _), result in zip(piece, finished, strict=True):
                    results[index] = result
        if any(item is None for item in results):
            raise TranslationError("批量翻译没有返回全部结果")
        return [item for item in results if item is not None]

    def _begin(self, request: TranslationRequest) -> TranslationResult | _Pending:
        text = (request.text or "").strip()
        quality = normalize_quality(request.quality)
        beam = beam_size_for(quality)
        source = self._resolve_source(text, request.source_lang)
        target = normalize_translation_language(request.target_lang) or (request.target_lang or "").strip().lower()
        if not target:
            raise TranslationError("没有目标语言")
        preference_key = ((request.device_preference or "auto").strip().lower(), bool(request.prefer_gpu))
        device, compute = self._resolve_device(request.device_preference, request.prefer_gpu)
        context_used = bool(request.context or request.force_terms or request.session_memory)
        if not text:
            return TranslationResult(
                text="",
                source_lang=source,
                target_lang=target,
                model_id="empty",
                device=device,
                quality=quality,
                beam_size=beam,
                context_used=context_used,
            )
        if source == target:
            return TranslationResult(
                text=request.text,
                source_lang=source,
                target_lang=target,
                model_id="identity",
                device=device,
                quality=quality,
                beam_size=beam,
                context_used=context_used,
            )
        session_hit = _lookup_pairs(request.session_memory, text)
        if session_hit is not None:
            return TranslationResult(
                text=session_hit,
                source_lang=source,
                target_lang=target,
                model_id="session-translation-memory",
                device=device,
                quality=quality,
                beam_size=beam,
                via_memory=True,
                context_used=True,
            )
        memory = self._resources.lookup_memory(text, source, target)
        if memory is not None:
            return TranslationResult(
                text=memory.target,
                source_lang=source,
                target_lang=target,
                model_id="translation-memory",
                device=device,
                quality=quality,
                beam_size=beam,
                via_memory=True,
                context_used=context_used,
            )
        characters = self._resources.matching("character_dictionary", source, target)
        glossary = self._resources.matching("glossary", source, target)
        extra_terms = [
            ResourceEntry(source=src, target=tgt, note="session", origin="session")
            for src, tgt in request.force_terms
            if src and tgt
        ]
        protected_chars = protect_terms(text, characters, "C")
        protected = protect_terms(protected_chars.text, glossary + extra_terms, "G")
        return _Pending(
            source=source,
            target=target,
            quality=quality,
            beam=beam,
            device=device,
            compute=compute,
            context_used=context_used,
            protected_text=protected.text,
            mapping={**protected_chars.mapping, **protected.mapping},
            glossary_hits=protected.hits,
            character_hits=protected_chars.hits,
            route=self._catalog.resolve_route(source, target),
            preference_key=preference_key,
        )

    def _resolve_device(self, device_preference: str, prefer_gpu: bool) -> tuple[str, str]:
        key = ((device_preference or "auto").strip().lower(), bool(prefer_gpu))
        cached = self._device_cache.get(key)
        if cached is not None:
            return cached
        device, compute = resolve_translation_device(
            self._report,
            device_preference=device_preference,
            prefer_gpu=prefer_gpu,
        )
        self._device_cache[key] = (device, compute)
        return device, compute

    def _finish_many(self, pendings: list[_Pending]) -> list[TranslationResult]:
        if not pendings:
            return []
        currents = [item.protected_text for item in pendings]
        device = pendings[0].device
        compute = pendings[0].compute
        beam = pendings[0].beam
        hop_ids: list[str] = []
        used_device = device
        for hop_id in pendings[0].route.hop_ids:
            model = self._catalog.model(hop_id)
            try:
                currents, used_device = self._run_hop_many(model, currents, beam, device, compute)
            except TranslationError as exc:
                if device != "cuda" or not is_cuda_runtime_error(exc):
                    raise
                self._logger.warning("CUDA 翻译失败，改用 CPU：%s", exc)
                device, compute = "cpu", "int8"
                for item in pendings:
                    self._device_cache[item.preference_key] = ("cpu", "int8")
                currents, used_device = self._run_hop_many(model, currents, beam, device, compute)
            hop_ids.append(model.id)
        model_id = "+".join(hop_ids) if hop_ids else "identity"
        finished: list[TranslationResult] = []
        for pending, text in zip(pendings, currents, strict=True):
            finished.append(
                TranslationResult(
                    text=restore_terms(text, pending.mapping),
                    source_lang=pending.source,
                    target_lang=pending.target,
                    model_id=model_id,
                    device=used_device,
                    quality=pending.quality,
                    beam_size=pending.beam,
                    via_memory=False,
                    glossary_hits=pending.glossary_hits,
                    character_hits=pending.character_hits,
                    route=pending.route.hop_ids,
                    context_used=pending.context_used,
                )
            )
        return finished

    def translate_document(
        self,
        document: SubtitleDocument,
        source_lang: str,
        target_langs: list[str],
        *,
        quality: str = "standard",
        device_preference: str = "auto",
        prefer_gpu: bool = True,
        progress: ProgressCallback | None = None,
        context_manager=None,
        use_context: bool = True,
        batch_size: int = 1,
    ) -> list[TranslationResult]:
        return translate_document(
            self,
            document,
            source_lang,
            target_langs,
            quality=quality,
            device_preference=device_preference,
            prefer_gpu=prefer_gpu,
            progress=progress,
            context_manager=context_manager,
            use_context=use_context,
            batch_size=batch_size,
        )

    def _resolve_source(self, text: str, source_lang: str) -> str:
        raw = (source_lang or "auto").strip()
        if raw.lower() in {"", "auto", "und", "unknown", "none"}:
            detected = detect_source_language(text)
            if detected == "und":
                raise TranslationError("无法自动检测源语言，请手动选择中文、英文或日文")
            return detected
        normalized = normalize_translation_language(raw) or raw.lower()
        return normalized

    def _run_hop(
        self,
        model: CatalogModel,
        text: str,
        beam: int,
        device: str,
        compute: str,
    ) -> tuple[str, str]:
        texts, used_device = self._run_hop_many(model, [text], beam, device, compute)
        return texts[0], used_device

    def _run_hop_many(
        self,
        model: CatalogModel,
        texts: list[str],
        beam: int,
        device: str,
        compute: str,
    ) -> tuple[list[str], str]:
        translator, tokenizer, used_device = self._load(model, device, compute)
        owners: list[int] = []
        sentences: list[str] = []
        for index, text in enumerate(texts):
            parts = _split_sentences(text) or ([text] if text else [])
            if not parts:
                continue
            for part in parts:
                owners.append(index)
                sentences.append(part)
        decoded = self._decode_many(translator, tokenizer, model, sentences, beam) if sentences else []
        grouped: list[list[str]] = [[] for _ in texts]
        for owner, text in zip(owners, decoded, strict=True):
            grouped[owner].append(text)
        joined = [" ".join(part for part in parts if part).strip() for parts in grouped]
        return joined, used_device

    def _decode_many(self, translator, tokenizer, model: CatalogModel, sentences: list[str], beam: int) -> list[str]:
        if not sentences:
            return []
        if model.source_lang != "en":
            return self._forward(translator, tokenizer, model, sentences, beam)
        first_variants = [english_source_variants(sentence)[0] for sentence in sentences]
        decoded = self._forward(translator, tokenizer, model, first_variants, beam)
        if model.target_lang != "zh":
            return decoded
        fixed: list[str] = []
        for sentence, text in zip(sentences, decoded, strict=True):
            if not looks_broken_zh(text):
                fixed.append(text)
                continue
            fixed.append(self._decode_sentence(translator, tokenizer, model, sentence, beam))
        return fixed

    def _forward(self, translator, tokenizer, model: CatalogModel, sentences: list[str], beam: int) -> list[str]:
        token_rows: list[list[str] | None] = []
        payload: list[list[str]] = []
        for sentence in sentences:
            tokens = tokenizer.encode(sentence)
            if not tokens:
                token_rows.append(None)
                continue
            token_rows.append(tokens)
            payload.append(tokens)
        if not payload:
            return [""] * len(sentences)
        try:
            results = translator.translate_batch(
                payload,
                beam_size=max(1, beam),
                replace_unknowns=True,
                max_decoding_length=512,
            )
        except Exception as exc:
            raise TranslationError(f"本地翻译失败（{model.id}）：{exc}") from exc
        decoded: list[str] = []
        cursor = 0
        for tokens in token_rows:
            if not tokens:
                decoded.append("")
                continue
            hypotheses = results[cursor].hypotheses if cursor < len(results) else []
            hypothesis = hypotheses[0] if hypotheses else []
            decoded.append(tokenizer.decode(list(hypothesis)))
            cursor += 1
        return decoded

    def _decode_sentence(self, translator, tokenizer, model: CatalogModel, sentence: str, beam: int) -> str:
        variants = english_source_variants(sentence) if model.source_lang == "en" else [sentence]
        last = ""
        for variant in variants:
            decoded = self._forward(translator, tokenizer, model, [variant], beam)
            last = decoded[0] if decoded else ""
            if not last:
                continue
            if model.target_lang != "zh" or not looks_broken_zh(last):
                return last
        return last

    def _load(self, model: CatalogModel, device: str, compute: str):
        key = (model.id, device, compute)
        if key in self._translators:
            return self._translators[key], self._tokenizers[model.id], device
        cache_key = ("translation", model.id, device, compute)
        cached = get_model_cache().get(cache_key)
        if cached is not None:
            translator, tokenizer = cached
            self._translators[key] = translator
            self._tokenizers[model.id] = tokenizer
            return translator, tokenizer, device
        root = model.directory()
        model_path = ctranslate2_model_path(root)
        tokenizer = load_tokenizer(root)
        try:
            import ctranslate2
        except ImportError as exc:
            raise TranslationError("未安装 ctranslate2，无法本地翻译。") from exc
        used_device = device
        if device == "cuda":
            prepare_cuda_dlls()
        try:
            translator = ctranslate2.Translator(
                str(model_path),
                device=device,
                compute_type=compute,
            )
        except Exception as exc:
            if device != "cuda":
                raise TranslationError(f"无法加载本地翻译模型 {model.id}：{exc}") from exc
            self._logger.warning("CUDA 加载翻译模型失败，回退 CPU：%s", exc)
            translator = ctranslate2.Translator(str(model_path), device="cpu", compute_type="int8")
            used_device = "cpu"
            key = (model.id, "cpu", "int8")
            cache_key = ("translation", model.id, "cpu", "int8")
        self._translators[key] = translator
        self._tokenizers[model.id] = tokenizer
        get_model_cache().put(cache_key, (translator, tokenizer))
        return translator, tokenizer, used_device


def _lookup_pairs(pairs: tuple[tuple[str, str], ...], text: str) -> str | None:
    needle = (text or "").strip()
    if not needle or not pairs:
        return None
    folded = needle.casefold()
    loose: str | None = None
    for source, target in pairs:
        candidate = (source or "").strip()
        if not candidate or not target:
            continue
        if candidate == needle:
            return target
        if candidate.casefold() == folded:
            loose = loose or target
    return loose


def _split_sentences(text: str) -> list[str]:
    blob = (text or "").strip()
    if not blob:
        return []
    if len(blob) <= 400:
        return [blob]
    parts: list[str] = []
    current: list[str] = []
    for char in blob:
        current.append(char)
        if char in "。！？!?":
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts or [blob]
