"""Download LaMa ONNX into models/inpaint/. Not packed into the EXE."""

from __future__ import annotations

import os
import shutil
import time
import urllib.request
from pathlib import Path

from localvideoai.core.paths import ensure_directory
from localvideoai.inpaint.store import MODEL_URLS, is_lama_ready, lama_model_path, require_model_dir

_UA = "LocalVideoAI/0.15 (lama-model-fetch)"


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


def _download(urls: tuple[str, ...], destination: Path) -> Path:
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
    require_model_dir()
    dest = lama_model_path()
    if is_lama_ready():
        print(f"already ready: {dest} ({dest.stat().st_size} bytes)")
        return 0
    _download(MODEL_URLS, dest)
    if not is_lama_ready():
        raise SystemExit(f"model incomplete: {dest}")
    print(f"ready: {dest} ({dest.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
