from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout, QWidget

from localvideoai.release.uninstaller import UNINSTALL_MODES


class UninstallDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("uninstallDialog")
        self.setWindowTitle("卸载 LocalVideoAI")
        self.resize(460, 280)
        layout = QVBoxLayout(self)
        hint = QLabel("卸载程序。请选择是否保留本机模型和项目。不会上传任何文件。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.program = QRadioButton("删除程序（保留模型和项目）")
        self.program.setObjectName("uninstallProgramRadio")
        self.keep_models = QRadioButton("保留模型（删除程序和项目）")
        self.keep_models.setObjectName("uninstallKeepModelsRadio")
        self.keep_projects = QRadioButton("保留项目（删除程序和模型）")
        self.keep_projects.setObjectName("uninstallKeepProjectsRadio")
        self.wipe = QRadioButton("删除全部（程序、模型、项目、缓存）")
        self.wipe.setObjectName("uninstallWipeRadio")
        self.program.setChecked(True)
        for button in (self.program, self.keep_models, self.keep_projects, self.wipe):
            layout.addWidget(button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mode(self) -> str:
        if self.keep_models.isChecked():
            return "keep_models"
        if self.keep_projects.isChecked():
            return "keep_projects"
        if self.wipe.isChecked():
            return "wipe"
        return "program"


assert set(UNINSTALL_MODES) == {"program", "keep_models", "keep_projects", "wipe"}
