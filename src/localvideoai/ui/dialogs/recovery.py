"""Startup choices for an unfinished .vtproj session. No model SDKs."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget

RECOVER = "recover"
ABANDON = "abandon"
SAVE = "save"


def ask_unfinished(parent: QWidget | None = None, detail: str = "") -> str:
    box = QMessageBox(parent)
    box.setObjectName("recoveryDialog")
    box.setWindowTitle("未完成的项目")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText("检测到未完成的项目。上次可能没有正常关闭。")
    if detail:
        box.setInformativeText(detail)
    recover = box.addButton("恢复", QMessageBox.ButtonRole.AcceptRole)
    save = box.addButton("保存", QMessageBox.ButtonRole.ActionRole)
    abandon = box.addButton("放弃", QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(recover)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save:
        return SAVE
    if clicked is abandon:
        return ABANDON
    return RECOVER
