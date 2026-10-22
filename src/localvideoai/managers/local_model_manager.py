from __future__ import annotations

from pathlib import Path

from localvideoai.core.exceptions import ModelError, SpeechError
from localvideoai.core.paths import (
    managed_models_dir,
    models_dir,
    ocr_models_dir,
    set_managed_models_dir,
    speaker_models_dir,
    speech_models_dir,
    translation_models_dir,
)
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.inpaint.store import find_lama_model, is_lama_ready
from localvideoai.managers.model_manager import ModelManager, Progress
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.models.catalog import load_model_catalog
from localvideoai.models.ops import (
    delete_managed,
    directory_size,
    import_local as import_into_managed,
    install as install_into_managed,
    is_under,
    managed_destination,
    normalize_model_id,
)
from localvideoai.models.recommend import recommend_model_ids, recommend_reason
from localvideoai.models.records import EMPTY_MODELS_HINT, ModelRecord
from localvideoai.models.state import disable_model, enable_model, is_disabled, load_model_state, set_active_model
from localvideoai.ocr.store import find_ocr_root, ocr_files_present
from localvideoai.speaker.store import find_embedding_model
from localvideoai.speech.store import find_model_dir, is_model_present, is_model_ready, resolve_model_path
from localvideoai.translation.store import find_translation_model_dir, resolve_translation_model_dir


class LocalModelManager(ModelManager):
    """Resolve, import, install, and switch models already on this machine."""

    def __init__(
        self,
        settings: SettingsManager | None = None,
        report: EnvironmentReport | None = None,
    ) -> None:
        self._settings = settings
        self._report = report
        self._apply_settings_root()
        state = load_model_state()
        self._active: dict[str, str] = dict(state["active"])

    def _apply_settings_root(self) -> None:
        if self._settings is None:
            return
        raw = self._settings.get("paths.models_dir")
        if isinstance(raw, str) and raw.strip():
            path = Path(raw)
            if path.is_absolute():
                set_managed_models_dir(path)

    def list_local(self) -> list[str]:
        return [record.id for record in self.list_records() if record.installed]

    def list_records(self) -> list[ModelRecord]:
        recommended = recommend_model_ids(self._report) if self._report is not None else set()
        records = [self._record_from_catalog(entry, recommended) for entry in load_model_catalog()]
        known = {record.id for record in records}
        for extra_id, path in self._discover_extras():
            if extra_id in known:
                continue
            records.append(self._record_discovered(extra_id, path, recommended))
        records.sort(
            key=lambda item: (
                0 if item.recommended else 1,
                0 if item.installed else 1,
                item.type,
                item.name,
            )
        )
        return records

    def resolve(self, model_id: str) -> Path:
        full = normalize_model_id(model_id)
        capability, local_id = full.split("/", 1)
        if capability == "ocr":
            root = find_ocr_root()
            if root is None:
                raise SpeechError(f"本地没有 OCR 模型（目录 {ocr_models_dir()}）")
            return root
        if capability == "translation":
            return resolve_translation_model_dir(local_id)
        if capability == "speaker":
            found = find_embedding_model()
            if found is None:
                raise SpeechError(f"本地没有说话人模型：{model_id}（目录 {speaker_models_dir()}）")
            return found
        if capability == "inpaint":
            found = find_lama_model()
            if found is None:
                raise SpeechError(f"本地没有修复模型：{model_id}")
            return found
        if is_model_ready(local_id):
            return resolve_model_path(local_id)
        path = models_dir() / model_id
        if path.exists():
            return path
        raise SpeechError(f"本地没有模型：{model_id}（目录 {speech_models_dir()} / {translation_models_dir()}）")

    def set_active(self, capability: str, model_id: str) -> None:
        full = normalize_model_id(model_id)
        enable_model(full)
        self.resolve(full)
        state = set_active_model(capability, full)
        self._active = dict(state["active"])

    def active(self) -> dict[str, str]:
        return dict(self._active)

    def install(self, model_id: str, progress: Progress | None = None) -> Path:
        path = install_into_managed(model_id, progress)
        self._persist_models_dir()
        return path

    def import_local(self, source: Path, model_id: str | None = None, progress: Progress | None = None) -> Path:
        path = import_into_managed(source, model_id, progress)
        self._persist_models_dir()
        return path

    def delete(self, model_id: str) -> None:
        full = normalize_model_id(model_id)
        delete_managed(full)
        if self._active.get(full.split("/", 1)[0]) == full:
            self._active.pop(full.split("/", 1)[0], None)
            state = load_model_state()
            state["active"] = dict(self._active)
            from localvideoai.models.state import save_model_state

            save_model_state(state)

    def enable(self, model_id: str) -> None:
        enable_model(normalize_model_id(model_id))

    def disable(self, model_id: str) -> None:
        disable_model(normalize_model_id(model_id))

    def set_models_root(self, path: Path) -> Path:
        resolved = set_managed_models_dir(path)
        self._persist_models_dir(resolved)
        return resolved

    def models_root(self) -> Path:
        return managed_models_dir()

    def empty_hint(self) -> str:
        return EMPTY_MODELS_HINT

    def has_installed(self) -> bool:
        return any(record.installed for record in self.list_records())

    def recommend_reason(self) -> str:
        if self._report is None:
            return "尚未检测硬件，无法按 CPU/GPU/RAM/VRAM 推荐。"
        return recommend_reason(self._report)

    def _persist_models_dir(self, path: Path | None = None) -> None:
        if self._settings is None:
            return
        self._settings.set("paths.models_dir", str((path or managed_models_dir()).resolve()))

    def _record_from_catalog(self, entry, recommended: set[str]) -> ModelRecord:
        path, location = self._locate(entry.id, entry.capability, entry.local_id)
        installed = path is not None
        enabled = installed and not is_disabled(entry.id)
        active = self._active.get(entry.capability) == entry.id
        size = directory_size(path) if path is not None else entry.size_bytes
        return ModelRecord(
            id=entry.id,
            name=entry.name,
            type=entry.type,
            languages=entry.languages,
            size_bytes=size,
            quantization=entry.quantization,
            ram_gb=entry.ram_gb,
            vram_gb=entry.vram_gb,
            status=self._status_text(installed, enabled, active, entry.id in recommended, location),
            installed=installed,
            enabled=enabled,
            recommended=entry.id in recommended,
            active=active,
            location=location,
            path=path,
            capability=entry.capability,
            local_id=entry.local_id,
        )

    def _record_discovered(self, model_id: str, path: Path, recommended: set[str]) -> ModelRecord:
        if "/" in model_id:
            capability, local_id = model_id.split("/", 1)
        else:
            capability, local_id = "imported", model_id
        location = "managed" if is_under(path, managed_models_dir()) else "bundled"
        enabled = not is_disabled(model_id)
        active = self._active.get(capability) == model_id
        return ModelRecord(
            id=model_id,
            name=local_id,
            type=capability,
            languages="未知",
            size_bytes=directory_size(path),
            quantization="未知",
            ram_gb=0,
            vram_gb=0,
            status=self._status_text(True, enabled, active, model_id in recommended, location),
            installed=True,
            enabled=enabled,
            recommended=model_id in recommended,
            active=active,
            location=location,
            path=path,
            capability=capability,
            local_id=local_id,
        )

    def _locate(self, model_id: str, capability: str, local_id: str) -> tuple[Path | None, str]:
        managed = managed_models_dir()
        if capability == "speech":
            managed_path = managed / "speech" / local_id
            if is_model_present(local_id, roots=[managed]):
                return managed_path if (managed_path / "model.bin").is_file() else find_model_dir(local_id, roots=[managed]), "managed"
            found = find_model_dir(local_id)
            return (found, "bundled") if found is not None else (None, "missing")
        if capability == "ocr":
            managed_ocr = managed / "ocr"
            if ocr_files_present(managed_ocr):
                return managed_ocr, "managed"
            found = find_ocr_root()
            return (found, "bundled") if found is not None else (None, "missing")
        if capability == "translation":
            managed_path = managed / "translation" / local_id
            from localvideoai.translation.store import is_translation_model_ready

            if is_translation_model_ready(managed_path):
                return managed_path, "managed"
            found = find_translation_model_dir(local_id)
            return (found, "bundled") if found is not None else (None, "missing")
        if capability == "speaker":
            found = find_embedding_model()
            if found is None:
                return None, "missing"
            return found, "managed" if is_under(found, managed) else "bundled"
        if capability == "inpaint":
            found = find_lama_model()
            if found is None:
                return None, "missing"
            return found, "managed" if is_under(found, managed) else "bundled"
        return None, "missing"

    def _discover_extras(self) -> list[tuple[str, Path]]:
        extras: list[tuple[str, Path]] = []
        if is_lama_ready() or find_lama_model() is not None:
            found = find_lama_model()
            if found is not None:
                extras.append(("inpaint/carve-lama-onnx-fp32", found))
        root = models_dir()
        if root.is_dir():
            reserved = {"speech", "ocr", "translation", "speaker", "inpaint"}
            for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                if not child.is_dir():
                    continue
                if child.name.startswith(".") or child.name in {".gitkeep", *reserved}:
                    continue
                extras.append((f"imported/{child.name}", child))
        return extras

    def _status_text(self, installed: bool, enabled: bool, active: bool, recommended: bool, location: str) -> str:
        parts: list[str] = []
        if not installed:
            parts.append("未安装")
        elif not enabled:
            parts.append("已禁用")
        else:
            parts.append("已启用")
        if installed and location == "bundled":
            parts.append("已部署")
        elif installed and location == "managed":
            parts.append("已安装")
        if active:
            parts.append("当前")
        if recommended:
            parts.append("推荐")
        return " · ".join(parts)
