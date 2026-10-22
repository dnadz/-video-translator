from localvideoai.app import run_check
from localvideoai.core.paths import user_config_path
from localvideoai.managers.settings_manager import SettingsManager


def test_program_starts(isolated_env):
    assert run_check() == 0
    settings = SettingsManager()
    assert settings.get("app.last_check_ok") is True
    assert user_config_path().is_file()
