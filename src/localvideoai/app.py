from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from localvideoai import APP_DISPLAY_NAME, APP_NAME, __version__
from localvideoai.db.database import Database
from localvideoai.hardware.hardware_manager import HardwareManager
from localvideoai.managers.log_manager import LogManager, get_logger
from localvideoai.managers.settings_manager import SettingsManager
from localvideoai.ui.main_window import MainWindow
from localvideoai.ui.theme import apply_theme


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="localvideoai", description=APP_DISPLAY_NAME)
    parser.add_argument("--check", action="store_true", help="Start, verify subsystems, then exit.")
    parser.add_argument("--guided-ui-check", action="store_true", help="Open the guided window, check its controls, then exit.")
    parser.add_argument("--guided-screenshot", metavar="PATH", help="Save the guided UI check screenshot.")
    parser.add_argument("--ui-smoke", action="store_true", help="Run Phase 1 UI smoke sequence and exit.")
    parser.add_argument("--player-smoke", action="store_true", help="Run Phase 2 player smoke sequence and exit.")
    parser.add_argument("--version", action="store_true", help="Print version and exit.")
    parser.add_argument(
        "--write-environment",
        metavar="PATH",
        help="Write HardwareManager environment markdown and exit.",
    )
    parser.add_argument("--uninstall", action="store_true", help="Choose uninstall data policy and exit.")
    parser.add_argument(
        "--uninstall-mode",
        choices=("program", "keep_models", "keep_projects", "wipe"),
        help="Uninstall without a dialog: program / keep_models / keep_projects / wipe.",
    )
    parser.add_argument("--release-smoke", action="store_true", help="Import a local video, analyze, export, then exit.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Open the full workstation. The default window is the simple subtitle flow.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_high_dpi() -> None:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing  # type: ignore[return-value]
    os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")
    configure_high_dpi()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    return app


def _bootstrap() -> tuple[SettingsManager, Database, object]:
    settings = SettingsManager()
    log_manager = LogManager(level=str(settings.get("logging.level", "INFO")))
    logger = log_manager.configure()
    logger.info("Starting %s %s", APP_DISPLAY_NAME, __version__)
    database = Database()
    database.connect()
    if not database.ping():
        raise RuntimeError("Database ping failed.")
    logger.info("Database ready at %s (schema %s)", database.path, database.schema_version())
    hardware = HardwareManager()
    report = hardware.detect()
    logger.info("Hardware detected: os=%s gpu=%s", report.os_caption, [g.name for g in report.gpus])
    return settings, database, report


def _create_window(settings: SettingsManager, report: object) -> MainWindow:
    app = QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication is not running")
    apply_theme(app, str(settings.get("app.theme", "system")))
    return MainWindow(settings, report)


def run_uninstall_cmd(mode: str | None) -> int:
    from localvideoai.release.uninstaller import run_uninstall, write_choice

    chosen = mode
    if not chosen:
        os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "windows"))
        app = create_application(["localvideoai", "--uninstall"])
        from localvideoai.ui.dialogs.uninstall_dialog import UninstallDialog

        dialog = UninstallDialog()
        if dialog.exec() != dialog.DialogCode.Accepted:
            return 1
        chosen = dialog.mode()
    plan = run_uninstall(chosen, include_program=False)
    write_choice(chosen)
    print(plan.mode)
    return 0


def run_release_smoke_cmd() -> int:
    from localvideoai.core.paths import install_root, user_data_dir
    from localvideoai.release.smoke import find_smoke_video, run_release_smoke

    video = find_smoke_video(install_root())
    notes = run_release_smoke(user_data_dir(), video)
    print(notes)
    return 0


def run_check() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("LOCALVIDEOAI_SKIP_RECOVERY", "1")
    settings, database, report = _bootstrap()
    app = create_application(["localvideoai", "--check"])
    window = _create_window(settings, report)
    window.show()
    app.processEvents()
    if not window.isVisible():
        if window.windowTitle() == "":
            raise RuntimeError("Main window failed to start.")
    if window.menu_titles() != ["文件", "编辑", "项目", "工具", "AI", "设置", "帮助"]:
        raise RuntimeError(f"Unexpected menus: {window.menu_titles()}")
    settings.set("app.last_check_ok", True)
    settings.save()
    window.close()
    database.close()
    get_logger("app").info("Startup check succeeded.")
    return 0


def run_player_smoke_cmd() -> int:
    os.environ.setdefault("LOCALVIDEOAI_SKIP_RECOVERY", "1")
    settings, database, report = _bootstrap()
    app = create_application(["localvideoai", "--player-smoke"])
    apply_theme(app, str(settings.get("app.theme", "system")))
    from localvideoai.ui.player_smoke import run_player_smoke

    notes = run_player_smoke(settings, report)
    database.close()
    get_logger("app").info("Player smoke succeeded: %s", notes)
    print(notes)
    return 0


def run_smoke() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("LOCALVIDEOAI_SKIP_RECOVERY", "1")
    settings, database, report = _bootstrap()
    app = create_application(["localvideoai", "--ui-smoke"])
    apply_theme(app, str(settings.get("app.theme", "system")))
    from localvideoai.ui.smoke import run_ui_smoke

    notes = run_ui_smoke(settings, report)
    database.close()
    get_logger("app").info("UI smoke succeeded: %s", notes)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.guided_ui_check:
        from simplecaption.ui_check import run_ui_check
        return run_ui_check(args.guided_screenshot)
    if args.version:
        print(__version__)
        return 0
    if args.write_environment:
        LogManager().configure()
        path = HardwareManager().write_markdown(Path(args.write_environment))
        print(path)
        return 0
    if args.uninstall or args.uninstall_mode:
        return run_uninstall_cmd(args.uninstall_mode)
    if args.release_smoke:
        return run_release_smoke_cmd()
    if args.check:
        try:
            return run_check()
        except Exception:
            get_logger("app").exception("Startup check failed.")
            raise
    if args.ui_smoke:
        try:
            return run_smoke()
        except Exception:
            get_logger("app").exception("UI smoke failed.")
            raise
    if args.player_smoke:
        try:
            return run_player_smoke_cmd()
        except Exception:
            get_logger("app").exception("Player smoke failed.")
            raise
    settings, database, report = _bootstrap()
    app = create_application()
    if args.full:
        window = _create_window(settings, report)
        window.show()
        window.prompt_unfinished_if_needed()
    else:
        from simplecaption.window import SimpleWindow

        window = SimpleWindow(settings, report)
        window.show()

    def _cleanup() -> None:
        database.close()

    app.aboutToQuit.connect(_cleanup)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
