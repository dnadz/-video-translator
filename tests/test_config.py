from localvideoai.managers.settings_manager import SettingsManager


def test_config_read_defaults(isolated_env):
    settings = SettingsManager()
    assert settings.get("app.name") == "LocalVideoAI"
    assert settings.get("privacy.upload_media") is False
    assert settings.get("privacy.allow_network") is False


def test_config_save_and_reload(isolated_env):
    settings = SettingsManager()
    settings.set("app.language", "en-US")
    saved = settings.save()
    assert saved.is_file()
    reloaded = SettingsManager()
    assert reloaded.get("app.language") == "en-US"
    assert reloaded.get("app.name") == "LocalVideoAI"
    assert reloaded.get("privacy.upload_media") is False
