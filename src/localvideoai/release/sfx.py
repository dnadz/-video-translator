"""Build self-extracting Setup/Portable EXEs without requiring Inno Setup."""

from __future__ import annotations

import os
import struct
import subprocess
import zipfile
from pathlib import Path

MAGIC = b"LVAIPAYLOADV1.0!"
FOOTER_SIZE = 32
if len(MAGIC) != 16:
    raise RuntimeError("SFX magic must be exactly 16 bytes")
STUB_NAME = "LocalVideoAI_InstallerStub.exe"


class SfxError(RuntimeError):
    pass


def zip_folder(source: Path, zip_path: Path) -> Path:
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for file in source.rglob("*"):
            if file.is_file():
                archive.write(file, file.relative_to(source).as_posix())
    return zip_path


def attach_payload(stub: Path, payload_zip: Path, output: Path) -> Path:
    if not stub.is_file():
        raise SfxError(f"missing installer stub: {stub}")
    if not payload_zip.is_file():
        raise SfxError(f"missing payload zip: {payload_zip}")
    stub_data = stub.read_bytes()
    zip_data = payload_zip.read_bytes()
    offset = len(stub_data)
    footer = struct.pack("<QQ", offset, len(zip_data)) + MAGIC
    if len(footer) != FOOTER_SIZE:
        raise SfxError("installer footer size mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(stub_data + zip_data + footer)
    return output


def read_payload_footer(sfx: Path) -> tuple[int, int]:
    data = sfx.read_bytes()
    if len(data) < FOOTER_SIZE or data[-16:] != MAGIC:
        raise SfxError(f"not a LocalVideoAI SFX: {sfx}")
    offset, size = struct.unpack("<QQ", data[-FOOTER_SIZE:-16])
    if offset < 0 or size < 0 or offset + size > len(data) - FOOTER_SIZE:
        raise SfxError(f"corrupt SFX footer: {sfx}")
    return offset, size


def extract_payload_zip(sfx: Path, dest_zip: Path) -> Path:
    offset, size = read_payload_footer(sfx)
    data = sfx.read_bytes()
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    dest_zip.write_bytes(data[offset : offset + size])
    return dest_zip


def find_csc() -> Path:
    override = os.environ.get("LOCALVIDEOAI_CSC", "").strip()
    if override and Path(override).is_file():
        return Path(override)
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SfxError("未找到 csc.exe，无法编译安装程序。Windows 11 应自带 .NET Framework 4.x。")


def compile_stub(source: Path, output: Path) -> Path:
    csc = find_csc()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/platform:anycpu",
        "/optimize+",
        "/codepage:65001",
        "/r:System.Windows.Forms.dll",
        "/r:System.Drawing.dll",
        "/r:System.IO.Compression.dll",
        "/r:System.IO.Compression.FileSystem.dll",
        f"/out:{output}",
        str(source),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0 or not output.is_file():
        raise SfxError(
            "编译安装程序失败：\n"
            f"{completed.stdout}\n{completed.stderr}"
        )
    return output


def build_stub(root: Path, dest: Path | None = None) -> Path:
    source = root / "packaging" / "installer" / "SetupStub.cs"
    target = dest or (root / "release" / "tools" / STUB_NAME)
    return compile_stub(source, target)


def build_setup_and_portable(root: Path, app_dir: Path, release: Path) -> dict[str, Path]:
    stub = build_stub(root, release / "tools" / STUB_NAME)
    payload = zip_folder(app_dir, release / "tools" / "app_payload.zip")
    setup = attach_payload(stub, payload, release / "LocalVideoAI_Setup.exe")
    portable = attach_payload(stub, payload, release / "LocalVideoAI_Portable.exe")
    return {"stub": stub, "payload": payload, "setup": setup, "portable": portable}
