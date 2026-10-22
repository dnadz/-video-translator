from localvideoai.core.paths import (
    assets_dir,
    bundled_models_dir,
    default_config_path,
    install_root,
    models_dir,
    user_config_path,
    user_data_dir,
)


def test_project_root_is_current_tree():
    root = install_root()
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "localvideoai").is_dir()
    assert (root / "config" / "default.json").is_file()


def test_user_paths_honor_environment(isolated_env):
    assert user_data_dir() == (isolated_env / "data").resolve()
    assert user_config_path() == (isolated_env / "settings.json").resolve()
    assert models_dir() == (isolated_env / "data" / "models").resolve()
    assert bundled_models_dir() == install_root() / "models"
    assert models_dir() != bundled_models_dir()
    assert assets_dir() == install_root() / "assets"
    assert default_config_path().is_file()


def test_source_has_no_machine_specific_paths():
    root = install_root() / "src"
    forbidden = ("E:\\AI\\", "E:/AI/", "C:\\Users\\Administrator", "C:/Users/Administrator")
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}: {token}")
    assert offenders == []
