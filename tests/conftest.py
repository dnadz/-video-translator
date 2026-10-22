from __future__ import annotations

import os

import pytest

from localvideoai.app import create_application
from localvideoai.hardware.hardware_manager import EnvironmentReport
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ui.main_window import MainWindow
from localvideoai.ui.theme import apply_theme


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    config = tmp_path / "settings.json"
    monkeypatch.setenv("LOCALVIDEOAI_DATA_DIR", str(data))
    monkeypatch.setenv("LOCALVIDEOAI_LOG_DIR", str(logs))
    monkeypatch.setenv("LOCALVIDEOAI_CONFIG_PATH", str(config))
    return tmp_path


def make_report() -> EnvironmentReport:
    return EnvironmentReport(
        os_caption="Windows 11 Test",
        os_version="10.0.22000",
        os_build="22000",
        os_arch="AMD64",
        python_version="3.12.13",
        python_executable="python",
        cpu_name="test-cpu",
        cpu_cores=6,
        cpu_logical=12,
        ram_total_gb=32.0,
        ram_available_gb=16.0,
        disks=[{"drive": "E:", "total_gb": 100.0, "free_gb": 50.0}],
        gpus=[],
        tools=[],
        project_root=".",
    )


@pytest.fixture
def qt_app(isolated_env, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    app = create_application(["localvideoai-test"])
    apply_theme(app, "light")
    return app


@pytest.fixture
def main_window(qt_app, isolated_env):
    settings = SettingsManager()
    window = MainWindow(settings, make_report())
    window.show()
    qt_app.processEvents()
    yield window
    window.close()
    qt_app.processEvents()
