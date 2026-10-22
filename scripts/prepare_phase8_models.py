"""Download OPUS-MT CTranslate2 packages listed in config/translation_catalog.json."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from localvideoai.core.paths import ensure_directory, translation_models_dir
from localvideoai.translation.catalog import load_catalog
from localvideoai.translation.store import is_translation_model_ready

_UA = "LocalVideoAI/0.9 (translation-model-fetch)"


def _replace(src: Path, dest: Path) -> None:
    last_error: Exception | None = None
    for _ in range(12):
        try:
            if dest.exists():
                dest.unlink()
            src.replace(dest)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    shutil.copy2(src, dest)
    try:
        src.unlink()
    except OSError:
        pass
    if last_error and not dest.is_file():
        raise last_error


def _download(urls: list[str], destination: Path) -> Path:
    last_error: Exception | None = None
    destination.parent.mkdir(parents=True, exist_ok=True)
    for url in urls:
        tmp = destination.with_name(destination.name + f".{os.getpid()}.part")
        try:
            print(f"download {url}")
            request = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(request, timeout=180) as response:
                total = int(response.headers.get("Content-Length") or 0)
                read = 0
                with tmp.open("wb") as handle:
                    while True:
                        chunk = response.read(256 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        read += len(chunk)
                        if total:
                            print(f"\r  {read / 1e6:.1f}/{total / 1e6:.1f} MB", end="", flush=True)
                        else:
                            print(f"\r  {read / 1e6:.1f} MB", end="", flush=True)
            print()
            if tmp.stat().st_size < 1024:
                raise RuntimeError("downloaded file is empty")
            _replace(tmp, destination)
            return destination
        except Exception as exc:
            last_error = exc
            print(f"\nfailed {url}: {exc}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
    raise SystemExit(f"download failed: {last_error}")


def _install_argos(archive: Path, destination: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="localvideoai-mt-") as raw:
        temp = Path(raw)
        with zipfile.ZipFile(archive) as zipped:
            zipped.extractall(temp)
        metadata = next(temp.rglob("metadata.json"), None)
        if metadata is None:
            raise SystemExit(f"archive has no metadata.json: {archive}")
        package = metadata.parent
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(package, destination)
    if not is_translation_model_ready(destination):
        raise SystemExit(f"extracted model is incomplete: {destination}")
    return destination


def main() -> int:
    socket.setdefaulttimeout(180)
    catalog = load_catalog()
    root = ensure_directory(translation_models_dir())
    downloads = ensure_directory(root / "_downloads")
    print(f"model root: {root}")
    print(f"catalog: {catalog.source_path}")
    for model in catalog.models.values():
        dest = model.directory()
        if is_translation_model_ready(dest):
            print(f"already present: {model.id} -> {dest}")
            continue
        info = model.download or {}
        filename = str(info.get("filename") or f"{model.id}.zip")
        urls = [str(item) for item in info.get("urls") or []]
        if not filename.endswith(".argosmodel"):
            print(f"skip {model.id}: not an Argos package (use scripts/prepare_ja_zh_model.py)")
            continue
        if not urls:
            raise SystemExit(f"catalog model {model.id} has no download urls")
        archive = downloads / filename
        if archive.is_file() and zipfile.is_zipfile(archive):
            print(f"reuse archive {archive} ({archive.stat().st_size} bytes)")
        else:
            if archive.is_file():
                print(f"discard incomplete archive {archive} ({archive.stat().st_size} bytes)")
                archive.unlink()
            _download(urls, archive)
            if not zipfile.is_zipfile(archive):
                raise SystemExit(f"downloaded file is not a zip: {archive}")
        path = _install_argos(archive, dest)
        print(f"installed {model.id} -> {path}")
    missing = [item.id for item in catalog.models.values() if not is_translation_model_ready(item.directory())]
    if missing:
        raise SystemExit(f"models still missing: {missing}")
    overlay = root / "catalog.json"
    bundled = catalog.source_path
    if bundled.name == "translation_catalog.json":
        shutil.copy2(bundled, overlay)
        print(f"copied catalog overlay to {overlay}")
    print("phase 8 translation models ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
