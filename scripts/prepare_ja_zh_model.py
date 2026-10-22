"""Install a direct ja→zh OPUS-MT CTranslate2 package. Argos has no ja_zh pair."""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from localvideoai.core.paths import ensure_directory, install_root
from localvideoai.translation.store import is_translation_model_ready


DEST_NAME = "opus-mt-ja-zh"
HF_REPO = "Helsinki-NLP/opus-mt-ja-zh"
OPUS_URLS = (
    "https://object.pouta.csc.fi/OPUS-MT-models/ja-zh/opus-2020-01-29.zip",
    "https://object.pouta.csc.fi/OPUS-MT-models/ja-zh/opus-2020-01-16.zip",
)


def _dest() -> Path:
    os.environ.setdefault("LOCALVIDEOAI_MODELS_DIR", str(install_root() / "models"))
    return ensure_directory(install_root() / "models" / "translation" / DEST_NAME)


def _convert_transformers(src: Path, dest: Path) -> None:
    from ctranslate2.converters.transformers import TransformersConverter

    converter = TransformersConverter(str(src), copy_files=["source.spm", "target.spm", "sentencepiece.bpe.model"])
    converter.convert(str(dest), quantization="int8", force=True)
    for name in ("source.spm", "target.spm", "sentencepiece.model"):
        candidate = src / name
        if candidate.is_file() and not (dest / name).is_file():
            shutil.copy2(candidate, dest / name)


def _convert_opus(src: Path, dest: Path) -> None:
    from ctranslate2.converters.opus_mt import OpusMTConverter

    converter = OpusMTConverter(str(src))
    converter.convert(str(dest), quantization="int8", force=True)
    for name in ("source.spm", "target.spm"):
        matches = list(src.rglob(name))
        if matches and not (dest / name).is_file():
            shutil.copy2(matches[0], dest / name)


def _download_hf(workspace: Path) -> Path:
    from huggingface_hub import snapshot_download

    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        os.environ.pop(key, None)
    target = workspace / "hf"
    snapshot_download(repo_id=HF_REPO, local_dir=str(target), max_workers=4, token=False)
    return target


def _download_opus(workspace: Path) -> Path:
    import urllib.request

    archive = workspace / "opus-ja-zh.zip"
    last_error: Exception | None = None
    for url in OPUS_URLS:
        try:
            print(f"download {url}", flush=True)
            request = urllib.request.Request(url, headers={"User-Agent": "LocalVideoAI/0.22"})
            import ssl

            context = ssl._create_unverified_context()
            with urllib.request.urlopen(request, timeout=180, context=context) as response, archive.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            if archive.stat().st_size > 1024 and zipfile.is_zipfile(archive):
                extracted = workspace / "opus"
                extracted.mkdir(exist_ok=True)
                with zipfile.ZipFile(archive) as zipped:
                    zipped.extractall(extracted)
                return extracted
        except Exception as exc:
            last_error = exc
            print(f"failed {url}: {exc}", flush=True)
    raise RuntimeError(f"OPUS-MT ja-zh download failed: {last_error}")


def main() -> int:
    dest = _dest()
    if is_translation_model_ready(dest):
        print(f"already present: {dest}")
        return 0
    workspace = ensure_directory(install_root() / "models" / "translation" / "_downloads" / "ja-zh")
    errors: list[str] = []
    try:
        src = _download_hf(workspace)
        _convert_transformers(src, dest)
    except Exception as exc:
        errors.append(f"transformers: {exc}")
        try:
            src = _download_opus(workspace)
            _convert_opus(src, dest)
        except Exception as inner:
            errors.append(f"opus: {inner}")
    if not is_translation_model_ready(dest):
        raise SystemExit("ja→zh model incomplete: " + " | ".join(errors))
    print(f"installed {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
