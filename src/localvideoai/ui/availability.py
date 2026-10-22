from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QWidget


def phase_lock_reason(capability: str, phase: str) -> str:
    return f"未启用：{capability} 将在{phase}提供。当前不可点击，不是假功能。"


def lock_widget(widget: QWidget, capability: str, phase: str) -> None:
    reason = phase_lock_reason(capability, phase)
    widget.setEnabled(False)
    widget.setToolTip(reason)
    widget.setStatusTip(reason)
    widget.setProperty("phaseLocked", True)
    widget.setAccessibleDescription(reason)


def lock_action(action: QAction, capability: str, phase: str) -> None:
    reason = phase_lock_reason(capability, phase)
    action.setEnabled(False)
    action.setToolTip(reason)
    action.setStatusTip(reason)
    action.setProperty("phaseLocked", True)


def unlock_widget(widget: QWidget, tooltip: str = "") -> None:
    widget.setEnabled(True)
    widget.setProperty("phaseLocked", False)
    widget.setToolTip(tooltip)
    widget.setStatusTip(tooltip)
    widget.setAccessibleDescription(tooltip)


def unlock_action(action: QAction, tooltip: str = "") -> None:
    action.setEnabled(True)
    action.setProperty("phaseLocked", False)
    action.setToolTip(tooltip)
    action.setStatusTip(tooltip)
