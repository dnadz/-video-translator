from __future__ import annotations

import sys

from simplecaption.runtime import prepare_runtime


def main(argv: list[str] | None = None) -> int:
    prepare_runtime()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--check" in args:
        from simplecaption.check import run_check

        return run_check()
    if "--smoke" in args:
        from simplecaption.smoke import run_smoke

        index = args.index("--smoke")
        if index + 1 >= len(args):
            print("用法: SimpleCaption.exe --smoke 媒体文件")
            return 2
        return run_smoke(args[index + 1])
    from PySide6.QtWidgets import QApplication

    from localvideoai.ui.theme import apply_theme
    from simplecaption.window import SimpleWindow

    qt_argv = sys.argv if argv is None else ["simplecaption", *argv]
    app = QApplication(qt_argv)
    apply_theme(app, "light")
    window = SimpleWindow()
    window.show()
    return app.exec()
