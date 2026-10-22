from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from localvideoai.core.exceptions import ConfigurationError
from localvideoai.core.paths import logs_dir
from PySide6.QtGui import QAction

from localvideoai.inpaint.pipeline import _encode
from localvideoai.inpaint.temporal import temporal_inpaint
from localvideoai.inpaint.types import MODE_SMART, TimedRegion
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.release.diagnostics import export_crash_bundle
from localvideoai.release.license import issue_license, load_license, save_license, unsigned_local
from localvideoai.release.updater import check_for_update, parse_version
from localvideoai.ui import strings


def test_temporal_inpaint_uses_future_and_past():
    background = np.zeros((40, 80, 3), dtype=np.uint8)
    background[:, :] = (12, 90, 210)
    current = background.copy()
    current[28:36, 8:72] = (255, 255, 255)
    mask = np.zeros((40, 80), dtype=np.uint8)
    mask[28:36, 8:72] = 255
    clean = (background.copy(), np.zeros_like(mask))
    filled, remain = temporal_inpaint(current, mask, past=[clean], future=[clean], use_flow=False)
    assert int(remain.max()) == 0
    assert tuple(int(v) for v in filled[32, 40]) == (12, 90, 210)


def test_temporal_inpaint_prefers_future_when_past_is_also_masked():
    background = np.zeros((24, 48, 3), dtype=np.uint8)
    background[:, :] = (30, 30, 30)
    current = background.copy()
    current[16:22, 4:44] = (250, 10, 10)
    mask = np.zeros((24, 48), dtype=np.uint8)
    mask[16:22, 4:44] = 255
    past = (current.copy(), mask.copy())
    future_rgb = background.copy()
    future_rgb[:, :] = (8, 200, 8)
    future = (future_rgb, np.zeros_like(mask))
    filled, remain = temporal_inpaint(current, mask, past=[past], future=[future], use_flow=False)
    assert int(remain.max()) == 0
    assert tuple(int(v) for v in filled[18, 24]) == (8, 200, 8)


def test_license_default_is_usable_local_edition(isolated_env):
    info = load_license()
    assert info.valid is True
    assert info.edition == "local"
    assert unsigned_local().valid is True


def test_license_signature_rejects_tamper(isolated_env):
    payload = issue_license(issued_to="工作室")
    path = save_license(payload)
    assert load_license(path).valid is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["issued_to"] = "篡改"
    path.write_text(json.dumps(raw), encoding="utf-8")
    bad = load_license(path)
    assert bad.valid is False
    assert "签名" in bad.reason


def test_expired_license_is_invalid_but_does_not_block_local_default(isolated_env):
    save_license(issue_license(issued_to="过期", expires="2020-01-01"))
    expired = load_license()
    assert expired.valid is False
    assert "过期" in expired.reason


def test_local_update_manifest_and_network_guard(tmp_path):
    assert parse_version("0.22.4") > parse_version("0.22.3")
    manifest = tmp_path / "update-manifest.json"
    manifest.write_text(json.dumps({"version": "9.9.9", "notes": "测试新版本"}, ensure_ascii=False), encoding="utf-8")
    newer = check_for_update(str(manifest), current="0.22.3", allow_network=False)
    assert newer.available is True
    assert newer.latest == "9.9.9"
    same = check_for_update(str(manifest), current="9.9.9", allow_network=False)
    assert same.available is False
    with pytest.raises(ConfigurationError, match="允许联网"):
        check_for_update("https://example.invalid/update.json", allow_network=False)


def test_default_update_source_is_local_manifest():
    info = check_for_update("", current="0.22.3", allow_network=False)
    assert info.source
    assert Path(info.source).name == "update-manifest.json"
    assert "http" not in info.source.lower()


def test_crash_bundle_stays_local(isolated_env):
    root = logs_dir()
    root.mkdir(parents=True, exist_ok=True)
    (root / "sample.log").write_text("local only\n", encoding="utf-8")
    bundle = export_crash_bundle()
    assert bundle.is_file()
    assert bundle.suffix == ".zip"
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        assert "README.txt" in names
        assert any(name.endswith("sample.log") for name in names)
        readme = archive.read("README.txt").decode("utf-8")
        assert "未上传" in readme


def test_settings_defaults_keep_network_off(isolated_env):
    settings = SettingsManager()
    assert settings.get("privacy.allow_network") is False
    assert settings.get("privacy.upload_media") is False
    assert settings.get("update.source") == ""


def test_settings_page_has_update_and_license_controls(main_window):
    page = main_window.settings_page
    assert page.allow_network.isChecked() is False
    assert page.check_update_button.text() == strings.CHECK_UPDATE
    assert page.import_license_button.isEnabled()
    assert page.export_diag_button.isEnabled()
    assert "个人版" in page.license_status.text()
    actions = [item for item in main_window.findChildren(QAction) if item.objectName() == "action_checkUpdate"]
    assert actions and actions[0].text() == strings.CHECK_UPDATE


def test_smart_inpaint_uses_temporal_neighbors(tmp_path):
    clip = _hardsub_clip(tmp_path / "band.mp4")
    dest = tmp_path / "cleaned.mp4"
    tracks = [TimedRegion(500, 1500, "HARD SUB", 0.05, 0.70, 0.90, 0.22)]
    frames, used_temporal = _encode(clip, dest, 80, 48, 8.0, 2000, tracks, MODE_SMART, False, None)
    assert dest.is_file() and dest.stat().st_size > 200
    assert used_temporal is True
    assert frames >= 8


def _hardsub_clip(path: Path) -> Path:
    from localvideoai.media.ffmpeg_runtime import find_ffmpeg
    import subprocess

    ffmpeg = find_ffmpeg()
    completed = subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x1048B4:s=80x48:d=2:r=8",
            "-vf",
            "drawbox=x=6:y=34:w=68:h=12:color=white:t=fill:enable='between(t,0.5,1.5)'",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0 or not path.is_file():
        pytest.fail(f"cannot write temporal test clip: {completed.stderr}")
    return path
