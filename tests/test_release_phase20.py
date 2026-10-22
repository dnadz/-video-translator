from __future__ import annotations

from pathlib import Path

from localvideoai import __version__
from localvideoai.core.paths import (
    cache_dir,
    install_root,
    is_portable,
    load_install_paths,
    projects_dir,
    set_cache_dir,
    set_projects_dir,
    write_install_paths,
)
from localvideoai.release.uninstaller import plan_uninstall, run_uninstall
from localvideoai.release.smoke import find_smoke_video, run_release_smoke


def test_version_is_phase20():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 21)


def test_projects_and_cache_dirs_are_configurable(isolated_env, tmp_path):
    projects = set_projects_dir(tmp_path / "proj")
    cache = set_cache_dir(tmp_path / "cache")
    assert projects.is_dir()
    assert cache.is_dir()
    assert projects_dir() == projects
    assert cache_dir() == cache
    mapped = load_install_paths()
    assert Path(mapped["projects_dir"]) == projects
    assert Path(mapped["cache_dir"]) == cache


def test_portable_flag_uses_local_data(tmp_path, monkeypatch):
    monkeypatch.delenv("LOCALVIDEOAI_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCALVIDEOAI_PORTABLE", raising=False)
    (tmp_path / "portable.flag").write_text("1\n", encoding="utf-8")
    monkeypatch.setenv("LOCALVIDEOAI_ROOT", str(tmp_path))
    monkeypatch.delenv("LOCALVIDEOAI_CONFIG_PATH", raising=False)
    assert is_portable()
    from localvideoai.core.paths import user_data_dir

    assert user_data_dir() == (tmp_path / "data").resolve()


def test_uninstall_keeps_models_or_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALVIDEOAI_DATA_DIR", str(tmp_path / "data"))
    models = tmp_path / "models"
    projects = tmp_path / "projects"
    cache = tmp_path / "cache"
    models.mkdir()
    projects.mkdir()
    cache.mkdir()
    (models / "keep.bin").write_bytes(b"m")
    (projects / "film.vtproj").write_text("{}", encoding="utf-8")
    write_install_paths({"models_dir": models, "projects_dir": projects, "cache_dir": cache})
    keep_models = plan_uninstall("keep_models")
    assert keep_models.remove_projects is True
    assert keep_models.remove_models is False
    keep_projects = plan_uninstall("keep_projects")
    assert keep_projects.remove_models is True
    assert keep_projects.remove_projects is False
    wipe = plan_uninstall("wipe")
    assert wipe.remove_models and wipe.remove_projects
    run_uninstall("keep_models")
    assert (models / "keep.bin").is_file()
    assert not (projects / "film.vtproj").exists()


def test_uninstall_program_keeps_user_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALVIDEOAI_DATA_DIR", str(tmp_path / "data"))
    models = tmp_path / "models"
    projects = tmp_path / "projects"
    models.mkdir()
    projects.mkdir()
    (models / "m.bin").write_bytes(b"1")
    (projects / "p.vtproj").write_text("{}", encoding="utf-8")
    write_install_paths({"models_dir": models, "projects_dir": projects, "cache_dir": tmp_path / "cache"})
    run_uninstall("program")
    assert (models / "m.bin").is_file()
    assert (projects / "p.vtproj").is_file()


def test_settings_page_has_directory_controls(main_window):
    assert main_window.settings_page.models_dir_edit is not None
    assert main_window.settings_page.projects_dir_edit is not None
    assert main_window.settings_page.cache_dir_edit is not None
    assert main_window.settings_page.projects_dir_browse.isEnabled()
    assert main_window.settings_page.cache_dir_browse.isEnabled()


def test_uninstall_dialog_modes(qt_app):
    from localvideoai.ui.dialogs.uninstall_dialog import UninstallDialog

    dialog = UninstallDialog()
    assert dialog.mode() == "program"
    dialog.wipe.setChecked(True)
    assert dialog.mode() == "wipe"
    dialog.keep_models.setChecked(True)
    assert dialog.mode() == "keep_models"
    dialog.keep_projects.setChecked(True)
    assert dialog.mode() == "keep_projects"


def test_release_smoke_imports_and_exports(tmp_path):
    video = find_smoke_video(install_root())
    notes = run_release_smoke(tmp_path, video)
    assert Path(notes["export"]).is_file()
    assert notes["encode_mode"] == "remux"
    assert int(notes["duration_ms"]) > 0


def test_packaging_files_exist():
    root = install_root()
    assert (root / "packaging" / "localvideoai.spec").is_file()
    assert (root / "packaging" / "LocalVideoAI.iss").is_file()
    assert (root / "packaging" / "LocalVideoAI_Portable.iss").is_file()
    assert (root / "packaging" / "installer" / "SetupStub.cs").is_file()
    assert (root / "scripts" / "build_release.py").is_file()
    assert (root / "scripts" / "phase20_isolated_test.py").is_file()


def test_model_listing_ignores_loose_files(isolated_env, tmp_path, monkeypatch):
    from localvideoai.core.paths import set_managed_models_dir
    from localvideoai.managers.local_model_manager import LocalModelManager

    models = set_managed_models_dir(tmp_path / "models")
    (models / "keep.bin").write_bytes(b"not-a-model")
    (models / "extra_bundle").mkdir()
    (models / "extra_bundle" / "readme.txt").write_text("imported", encoding="utf-8")
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(models))
    records = LocalModelManager().list_records()
    ids = {item.id for item in records}
    assert "keep.bin" not in ids
    assert "imported/extra_bundle" in ids


def test_sfx_payload_roundtrip(tmp_path):
    from localvideoai.release.sfx import attach_payload, extract_payload_zip, read_payload_footer, zip_folder

    source = tmp_path / "app"
    source.mkdir()
    (source / "LocalVideoAI.exe").write_bytes(b"demo-exe")
    (source / "readme.txt").write_text("portable", encoding="utf-8")
    stub = tmp_path / "stub.exe"
    stub.write_bytes(b"MZ-STUB" + (b"\x00" * 64))
    payload = zip_folder(source, tmp_path / "payload.zip")
    sfx = attach_payload(stub, payload, tmp_path / "LocalVideoAI_Setup.exe")
    offset, size = read_payload_footer(sfx)
    assert offset == stub.stat().st_size
    assert size == payload.stat().st_size
    extracted = extract_payload_zip(sfx, tmp_path / "out.zip")
    assert extracted.read_bytes() == payload.read_bytes()
