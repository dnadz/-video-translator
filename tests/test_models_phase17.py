import inspect
from pathlib import Path

from localvideoai import __version__
from localvideoai.core.paths import bundled_models_dir, managed_models_dir, models_dir
from localvideoai.hardware.hardware_manager import EnvironmentReport, GpuInfo
from localvideoai.managers.local_model_manager import LocalModelManager
from localvideoai.managers.model_manager import ModelManager
from localvideoai.models.catalog import load_model_catalog
from localvideoai.models.recommend import recommend_model_ids
from localvideoai.models.records import EMPTY_MODELS_HINT
from localvideoai.speech.store import is_model_present
from tests.conftest import make_report


def test_version_is_phase17():
    major, minor, *_ = (int(part) for part in __version__.split("."))
    assert (major, minor) >= (0, 18)


def test_model_manager_stays_abstract_and_local_is_concrete():
    assert inspect.isabstract(ModelManager)
    manager = LocalModelManager()
    assert isinstance(manager, ModelManager)
    assert not inspect.isabstract(LocalModelManager)


def test_catalog_has_required_display_fields():
    entries = load_model_catalog()
    assert entries
    required = {"id", "name", "type", "languages", "size_bytes", "quantization", "ram_gb", "vram_gb"}
    for entry in entries:
        fields = entry.required_fields()
        assert required <= set(fields)
        assert entry.id.count("/") == 1


def test_recommend_uses_hardware_not_random():
    cpu = make_report()
    cpu_ids = recommend_model_ids(cpu)
    assert "speech/small" in cpu_ids
    low = EnvironmentReport(
        os_caption="Windows 11 Test",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12.13",
        python_executable="python",
        cpu_name="low-ram-cpu",
        cpu_cores=2,
        cpu_logical=4,
        ram_total_gb=4.0,
        ram_available_gb=2.0,
        disks=[{"drive": "E:", "total_gb": 100.0, "free_gb": 50.0}],
        gpus=[],
        tools=[],
        project_root=".",
    )
    low_ids = recommend_model_ids(low)
    assert "speech/tiny" in low_ids
    gpu = EnvironmentReport(
        os_caption=cpu.os_caption,
        os_version=cpu.os_version,
        os_build=cpu.os_build,
        os_arch=cpu.os_arch,
        python_version=cpu.python_version,
        python_executable=cpu.python_executable,
        cpu_name=cpu.cpu_name,
        cpu_cores=cpu.cpu_cores,
        cpu_logical=cpu.cpu_logical,
        ram_total_gb=32.0,
        ram_available_gb=16.0,
        disks=cpu.disks,
        gpus=[
            GpuInfo(
                name="NVIDIA GeForce RTX 3060 Ti",
                vram_mb=8192,
                driver="test",
                cuda_driver_version="12.4",
                source="test",
            )
        ],
        tools=[],
        project_root=".",
    )
    gpu_ids = recommend_model_ids(gpu)
    assert "speech/large-v3-turbo" in gpu_ids
    assert cpu_ids != gpu_ids


def test_managed_dir_is_not_software_tree(isolated_env):
    assert models_dir() == (isolated_env / "data" / "models").resolve()
    assert managed_models_dir() == models_dir()
    assert models_dir() != bundled_models_dir()


def test_bundled_models_are_visible_without_copy(isolated_env):
    manager = LocalModelManager(report=make_report())
    records = {item.id: item for item in manager.list_records()}
    assert records["speech/tiny"].installed
    assert records["speech/tiny"].location == "bundled"
    assert "已部署" in records["speech/tiny"].status
    assert is_model_present("tiny")


def test_empty_state_hint(isolated_env, monkeypatch):
    monkeypatch.setenv("LOCALVIDEOAI_SKIP_BUNDLED_MODELS", "1")
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(isolated_env / "empty_models"))
    manager = LocalModelManager(report=make_report())
    assert not manager.has_installed()
    assert "还没有可用模型" in manager.empty_hint()
    assert manager.empty_hint() == EMPTY_MODELS_HINT


def test_import_switch_disable_delete_reinstall_tiny(isolated_env, monkeypatch):
    managed = isolated_env / "managed_models"
    monkeypatch.setenv("LOCALVIDEOAI_SKIP_BUNDLED_MODELS", "1")
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(managed))
    manager = LocalModelManager(report=make_report())
    assert not manager.has_installed()
    source = bundled_models_dir() / "speech" / "tiny"
    copied = manager.import_local(source, "speech/tiny")
    assert copied.is_dir()
    assert (copied / "model.bin").is_file()
    assert is_under_managed(copied, managed)
    tiny = _record(manager, "speech/tiny")
    assert tiny.installed
    assert tiny.location == "managed"
    assert "已安装" in tiny.status
    manager.set_active("speech", "speech/tiny")
    assert manager.active()["speech"] == "speech/tiny"
    assert _record(manager, "speech/tiny").active
    manager.disable("speech/tiny")
    assert not _record(manager, "speech/tiny").enabled
    assert "已禁用" in _record(manager, "speech/tiny").status
    manager.enable("speech/tiny")
    assert _record(manager, "speech/tiny").enabled
    manager.delete("speech/tiny")
    assert not (managed / "speech" / "tiny" / "model.bin").is_file()
    assert (source / "model.bin").is_file()
    assert not _record(manager, "speech/tiny").installed
    reinstalled = manager.install("speech/tiny")
    assert (reinstalled / "model.bin").is_file()
    assert _record(manager, "speech/tiny").installed


def test_user_can_change_models_directory(isolated_env):
    manager = LocalModelManager()
    first = manager.models_root()
    changed = isolated_env / "custom_models"
    result = manager.set_models_root(changed)
    assert result == changed.resolve()
    assert manager.models_root() == changed.resolve()
    assert manager.models_root() != first
    assert manager.models_root() != bundled_models_dir()


def test_ui_model_center_columns_and_install_enabled(main_window):
    page = main_window.models_page
    assert page.download_button.isEnabled()
    assert page.install_button.isEnabled()
    assert page.import_button.isEnabled()
    assert page.delete_button.isEnabled()
    assert page.switch_button.isEnabled()
    assert page.enable_button.isEnabled()
    assert page.disable_button.isEnabled()
    headers = [page.table.horizontalHeaderItem(index).text() for index in range(page.table.columnCount())]
    assert headers == ["模型名称", "类型", "语言", "大小", "量化", "推荐RAM", "推荐显存", "状态"]
    assert page.table.rowCount() >= 1
    names = [page.table.item(row, 0).text() for row in range(page.table.rowCount())]
    assert any("Tiny" in name or "tiny" in name.lower() for name in names)


def test_ui_empty_models_hint(qt_app, isolated_env, monkeypatch):
    from localvideoai.managers.settings_manager import SettingsManager
    from localvideoai.ui.main_window import MainWindow

    monkeypatch.setenv("LOCALVIDEOAI_SKIP_BUNDLED_MODELS", "1")
    monkeypatch.setenv("LOCALVIDEOAI_MODELS_DIR", str(isolated_env / "ui_empty_models"))
    window = MainWindow(SettingsManager(), make_report())
    window.show()
    window.switch_page("models")
    qt_app.processEvents()
    try:
        assert not window.model_manager.has_installed()
        assert window.models_page.empty_label.isVisible()
        assert "还没有可用模型" in window.models_page.empty_label.text()
    finally:
        window.close()
        qt_app.processEvents()


def _record(manager: LocalModelManager, model_id: str):
    for item in manager.list_records():
        if item.id == model_id:
            return item
    raise AssertionError(f"missing {model_id}")


def is_under_managed(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())
