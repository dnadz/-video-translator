"""Download the local speaker-embedding ONNX into models/speaker/."""

from __future__ import annotations

import os
import shutil
import time
import urllib.request
from pathlib import Path

from localvideoai.core.paths import ensure_directory, speaker_models_dir
from localvideoai.speaker.store import embedding_model_path, is_speaker_model_ready, model_filename, model_urls

_UA = "LocalVideoAI/0.13 (speaker-model-fetch)"


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


def main() -> int:
    ensure_directory(speaker_models_dir())
    dest = embedding_model_path()
    if is_speaker_model_ready():
        print(f"already ready: {dest} ({dest.stat().st_size} bytes)")
        return 0
    urls = model_urls()
    if not urls:
        raise SystemExit("config/speaker_catalog.json has no urls")
    _download(urls, dest)
    print(f"saved {dest} ({dest.stat().st_size} bytes) as {model_filename()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
