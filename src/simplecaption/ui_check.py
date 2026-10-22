"""Exercise the real guided Qt window, including the packaged entry point."""
from pathlib import Path
from PySide6.QtCore import QTimer


def run_ui_check(screenshot=None):
    from localvideoai.app import create_application
    from localvideoai.ui.theme import apply_theme
    from simplecaption.window import SimpleWindow
    app = create_application(["guided-ui-check"])
    apply_theme(app, "light")
    window = SimpleWindow()
    window.show()
    errors = []

    def check():
        try:
            assert window.isVisible()
            assert window.start_button.isVisible()
            assert not window.start_button.isEnabled()
            assert not window.advanced_panel.isVisible()
            assert not window.blur_checkbox.isChecked()
            if screenshot:
                path = Path(screenshot)
                path.parent.mkdir(parents=True, exist_ok=True)
                assert window.grab().save(str(path))
            window.advanced_toggle.setChecked(True)
            assert window.advanced_panel.isVisible()
        except Exception as exc:
            errors.append(str(exc))
        finally:
            window.close()
            app.quit()

    QTimer.singleShot(800, check)
    app.exec()
    if errors:
        raise RuntimeError("guided UI check failed: " + "; ".join(errors))
    print("Guided UI check passed")
    return 0
