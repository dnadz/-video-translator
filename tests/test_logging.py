from localvideoai.managers.log_manager import LogManager, get_logger


def test_log_system_writes_file(isolated_env):
    manager = LogManager()
    logger = manager.configure()
    logger.info("phase0-log-probe")
    child = get_logger("tests")
    child.warning("phase0-child-log")
    for handler in logger.handlers:
        handler.flush()
    assert manager.log_file.is_file()
    text = manager.log_file.read_text(encoding="utf-8")
    assert "phase0-log-probe" in text
    assert "phase0-child-log" in text
