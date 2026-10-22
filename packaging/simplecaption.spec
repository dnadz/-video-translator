# PyInstaller spec for the minimal subtitle app. Run via scripts/build_simplecaption.py
from pathlib import Path

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"

datas = [(str(ROOT / "config"), "config")]
ffmpeg = ROOT / "vendor" / "ffmpeg"
if ffmpeg.is_dir():
    datas.append((str(ffmpeg), "vendor/ffmpeg"))

binaries = []
hiddenimports = [
    "simplecaption",
    "simplecaption.app",
    "simplecaption.window",
    "simplecaption.runtime",
    "simplecaption.check",
    "simplecaption.smoke",
    "simplecaption.srtio",
    "localvideoai.engines.faster_whisper_engine",
    "localvideoai.engines.ctranslate2_translation_engine",
    "localvideoai.ui.workers.transcribe_worker",
    "localvideoai.ui.workers.translate_worker",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "imageio_ffmpeg",
    "sentencepiece",
]

for package in (
    "PySide6",
    "shiboken6",
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "av",
    "tokenizers",
    "sentencepiece",
    "imageio_ffmpeg",
    "numpy",
):
    try:
        collected_datas, collected_binaries, collected_hidden = collect_all(package)
    except Exception:
        continue
    datas += collected_datas
    binaries += collected_binaries
    hiddenimports += collected_hidden

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
    [str(SRC / "simplecaption" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "rapidocr", "pandas"],
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
    name="SimpleCaption",
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
    name="SimpleCaption",
)
