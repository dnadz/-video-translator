"""Load replaceable translation catalog. Pairs live here, not in the engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from localvideoai.core.exceptions import TranslationError
from localvideoai.core.paths import model_search_roots, translation_models_dir
from localvideoai.translation.language import normalize_translation_language


@dataclass(frozen=True)
class CatalogLanguage:
    code: str
    name: str


@dataclass(frozen=True)
class CatalogModel:
    id: str
    source_lang: str
    target_lang: str
    dir_name: str
    family: str = "opus-mt"
    tokenizer: str = "sentencepiece"
    download: dict[str, Any] = field(default_factory=dict)

    def directory(self) -> Path:
        from localvideoai.translation.store import find_translation_model_dir

        found = find_translation_model_dir(self.dir_name)
        return found if found is not None else translation_models_dir() / self.dir_name


@dataclass(frozen=True)
class CatalogRoute:
    source_lang: str
    target_lang: str
    hop_ids: tuple[str, ...]


@dataclass
class TranslationCatalog:
    engine: str
    languages: list[CatalogLanguage]
    models: dict[str, CatalogModel]
    routes: list[CatalogRoute]
    source_path: Path

    def language_codes(self) -> list[str]:
        return [item.code for item in self.languages]

    def model(self, model_id: str) -> CatalogModel:
        if model_id not in self.models:
            raise TranslationError(f"翻译目录里没有模型 {model_id}")
        return self.models[model_id]

    def direct_model(self, source_lang: str, target_lang: str) -> CatalogModel | None:
        for item in self.models.values():
            if item.source_lang == source_lang and item.target_lang == target_lang:
                return item
        return None

    def resolve_route(self, source_lang: str, target_lang: str) -> CatalogRoute:
        src = normalize_translation_language(source_lang) or source_lang
        tgt = normalize_translation_language(target_lang) or target_lang
        if src == tgt:
            return CatalogRoute(src, tgt, ())
        matching = [
            route
            for route in self.routes
            if route.source_lang == src and route.target_lang == tgt
        ]
        ready: list[CatalogRoute] = []
        for route in matching:
            if all(_model_ready(self.model(hop_id)) for hop_id in route.hop_ids):
                ready.append(route)
        if ready:
            ready.sort(key=lambda item: len(item.hop_ids))
            return ready[0]
        if matching:
            missing = []
            for hop_id in matching[0].hop_ids:
                model = self.model(hop_id)
                if not _model_ready(model):
                    missing.append(str(model.directory()))
            raise TranslationError(
                "本地没有翻译模型。"
                f"请先运行 scripts/prepare_phase8_models.py 下载到 {translation_models_dir()}"
                + (f"（缺少：{', '.join(missing)}）" if missing else "")
            )
        direct = self.direct_model(src, tgt)
        if direct is not None:
            if not _model_ready(direct):
                raise TranslationError(
                    f"本地没有翻译模型 {direct.id}。请先运行 scripts/prepare_phase8_models.py "
                    f"下载到 {direct.directory()}"
                )
            return CatalogRoute(src, tgt, (direct.id,))
        supported = ", ".join(f"{r.source_lang}->{r.target_lang}" for r in self.routes) or "无"
        raise TranslationError(
            f"目录不支持 {src}→{tgt}。当前已配置：{supported}。增加语言请编辑 config/translation_catalog.json。"
        )


def _model_ready(model: CatalogModel) -> bool:
    from localvideoai.translation.store import find_translation_model_dir

    return find_translation_model_dir(model.dir_name) is not None


def bundled_catalog_path() -> Path:
    from localvideoai.core.paths import config_file

    return config_file("translation_catalog.json")


def overlay_catalog_path() -> Path:
    for root in model_search_roots():
        path = root / "translation" / "catalog.json"
        if path.is_file():
            return path
    return translation_models_dir() / "catalog.json"


def load_catalog() -> TranslationCatalog:
    path = bundled_catalog_path()
    if not path.is_file():
        raise TranslationError(f"缺少翻译目录文件：{path}")
    payload = _read_json(path)
    overlay = overlay_catalog_path()
    if overlay.is_file():
        payload = _merge_catalog(payload, _read_json(overlay))
    return _parse_catalog(payload, overlay if overlay.is_file() else path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranslationError(f"翻译目录不是有效 JSON：{path}") from exc
    if not isinstance(data, dict):
        raise TranslationError(f"翻译目录格式错误：{path}")
    return data


def _merge_catalog(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    if overlay.get("engine"):
        merged["engine"] = overlay["engine"]
    languages = {item.get("code"): item for item in base.get("languages") or [] if item.get("code")}
    for item in overlay.get("languages") or []:
        if item.get("code"):
            languages[item["code"]] = item
    merged["languages"] = list(languages.values())
    models = {item.get("id"): item for item in base.get("models") or [] if item.get("id")}
    for item in overlay.get("models") or []:
        if item.get("id"):
            models[item["id"]] = item
    merged["models"] = list(models.values())
    routes: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in list(base.get("routes") or []) + list(overlay.get("routes") or []):
        key = (item.get("from"), item.get("to"), tuple(item.get("hops") or []))
        routes[key] = item
    merged["routes"] = list(routes.values())
    return merged


def _parse_catalog(payload: dict[str, Any], source: Path) -> TranslationCatalog:
    languages = [
        CatalogLanguage(
            code=str(item.get("code") or ""),
            name=str(item.get("name") or item.get("code") or ""),
        )
        for item in payload.get("languages") or []
        if item.get("code")
    ]
    models: dict[str, CatalogModel] = {}
    for item in payload.get("models") or []:
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        src = normalize_translation_language(str(item.get("from") or "")) or str(item.get("from") or "")
        tgt = normalize_translation_language(str(item.get("to") or "")) or str(item.get("to") or "")
        models[model_id] = CatalogModel(
            id=model_id,
            source_lang=src,
            target_lang=tgt,
            dir_name=str(item.get("dir") or model_id),
            family=str(item.get("family") or "opus-mt"),
            tokenizer=str(item.get("tokenizer") or "sentencepiece"),
            download=dict(item.get("download") or {}),
        )
    routes = [
        CatalogRoute(
            source_lang=normalize_translation_language(str(item.get("from") or "")) or str(item.get("from") or ""),
            target_lang=normalize_translation_language(str(item.get("to") or "")) or str(item.get("to") or ""),
            hop_ids=tuple(str(hop) for hop in item.get("hops") or []),
        )
        for item in payload.get("routes") or []
    ]
    return TranslationCatalog(
        engine=str(payload.get("engine") or "ctranslate2"),
        languages=languages,
        models=models,
        routes=routes,
        source_path=source,
    )
