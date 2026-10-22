from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EMPTY_MODELS_HINT = (
    "本地还没有可用模型。\n"
    "请把本机已部署的模型目录导入到独立模型目录，或安装较小的 speech/tiny。\n"
    "软件安装目录不会写入大量模型。"
)


def format_bytes(size_bytes: int) -> str:
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.0f} MB"
    if size_bytes >= 1000:
        return f"{size_bytes / 1000:.0f} KB"
    return f"{size_bytes} B"


def format_gb(value: float) -> str:
    if value <= 0:
        return "CPU 即可"
    if value == int(value):
        return f"{int(value)} GB"
    return f"{value:.1f} GB"


@dataclass
class ModelRecord:
    id: str
    name: str
    type: str
    languages: str
    size_bytes: int
    quantization: str
    ram_gb: float
    vram_gb: float
    status: str
    installed: bool
    enabled: bool
    recommended: bool
    active: bool
    location: str
    path: Path | None
    capability: str
    local_id: str

    def size_text(self) -> str:
        return format_bytes(self.size_bytes)

    def ram_text(self) -> str:
        return format_gb(self.ram_gb)

    def vram_text(self) -> str:
        return format_gb(self.vram_gb)
