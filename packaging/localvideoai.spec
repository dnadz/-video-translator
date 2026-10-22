# PyInstaller spec. Run from repo root via scripts/build_release.py
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all, collect_data_files

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

datas = [
    (str(ROOT / "config"), "config"),
    (str(ROOT / "vendor" / "ffmpeg"), "vendor/ffmpeg"),
]
if (ROOT / "assets").is_dir():
    datas.append((str(ROOT / "assets"), "assets"))

binaries = []
hiddenimports = [
    "localvideoai",
    "localvideoai.app",
    "localvideoai.__main__",
    "localvideoai.inpaint.temporal",
    "localvideoai.release.license",
    "localvideoai.release.updater",
    "localvideoai.release.diagnostics",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "shiboken6",
    "simplecaption",
    "simplecaption.app",
    "simplecaption.window",
    "simplecaption.guided_ui",
    "simplecaption.export_worker",
    "simplecaption.ui_check",
    "simplecaption.cover",
    "simplecaption.cover_worker",
    "simplecaption.runtime",
    "simplecaption.srtio",
    "simplecaption.check",
    "simplecaption.smoke",
]

for package in (
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "rapidocr",
    "av",
    "tokenizers",
    "huggingface_hub",
    "sentencepiece",
):
    try:
        collected_datas, collected_binaries, collected_hidden = collect_all(package)
    except Exception:
        continue
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

try:
    datas += collect_data_files("rapidocr")
except Exception:
    pass

try:
    import nvidia
except Exception:
    nvidia = None
if nvidia is not None:
    nvidia_roots = [Path(item) for item in getattr(nvidia, "__path__", [])]
    nvidia_file = getattr(nvidia, "__file__", None)
    if nvidia_file:
        nvidia_roots.append(Path(nvidia_file).resolve().parent)
    seen_roots: set[Path] = set()
    for nvidia_root in nvidia_roots:
        try:
            nvidia_root = nvidia_root.resolve()
        except OSError:
            continue
        if nvidia_root in seen_roots or not nvidia_root.is_dir():
            continue
        seen_roots.add(nvidia_root)
        parent = nvidia_root.parent
        for dll in nvidia_root.rglob("*.dll"):
            binaries.append((str(dll), str(dll.parent.relative_to(parent))))

block_cipher = None
a = Analysis(
    [str(SRC / "localvideoai" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalVideoAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LocalVideoAI",
)
