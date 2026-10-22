from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from localvideoai.translation.resources import Kind, ResourceEntry, TranslationResources

COLUMNS = ("source", "target", "source_lang", "target_lang", "note")
HEADERS = ("原文", "译文", "源语言", "目标语言", "备注")
KINDS: tuple[tuple[Kind, str], ...] = (
    ("glossary", "术语表 Glossary"),
    ("translation_memory", "翻译记忆 Translation Memory"),
    ("character_dictionary", "人名字典 Character Dictionary"),
)


class TranslationResourcesDialog(QDialog):
    """Edit local glossary / TM / character dictionary. User rows override bundled ones."""

    def __init__(self, resources: TranslationResources | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("translationResourcesDialog")
        self.setWindowTitle("翻译词表")
        self.resize(720, 480)
        self._resources = resources or TranslationResources()
        self._tables: dict[Kind, QTableWidget] = {}
        layout = QVBoxLayout(self)
        hint = QLabel(
            "用户词表保存在本机数据目录。与内置条目冲突时以用户修改为准。"
            "翻译记忆命中则跳过模型；术语和人名会在进模型前保护，译完再写回目标写法。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        tabs = QTabWidget()
        tabs.setObjectName("translationResourceTabs")
        for kind, title in KINDS:
            page, table = self._build_tab(kind)
            self._tables[kind] = table
            tabs.addTab(page, title)
        layout.addWidget(tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._load()

    def _build_tab(self, kind: Kind) -> tuple[QWidget, QTableWidget]:
        page = QWidget()
        box = QVBoxLayout(page)
        table = QTableWidget(0, len(COLUMNS))
        table.setObjectName(f"resourceTable_{kind}")
        table.setHorizontalHeaderLabels(list(HEADERS))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        row_buttons = QHBoxLayout()
        add_button = QPushButton("添加")
        add_button.setObjectName(f"addResource_{kind}")
        remove_button = QPushButton("删除所选")
        remove_button.setObjectName(f"removeResource_{kind}")
        add_button.clicked.connect(lambda _checked=False, k=kind: self._add_row(k))
        remove_button.clicked.connect(lambda _checked=False, k=kind: self._remove_row(k))
        row_buttons.addWidget(add_button)
        row_buttons.addWidget(remove_button)
        row_buttons.addStretch(1)
        box.addWidget(table, 1)
        box.addLayout(row_buttons)
        return page, table

    def _load(self) -> None:
        for kind, table in self._tables.items():
            entries = self._resources.merged(kind)
            table.setRowCount(0)
            table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                values = [entry.source, entry.target, entry.source_lang, entry.target_lang, entry.note]
                for column, value in enumerate(values):
                    table.setItem(row, column, QTableWidgetItem(value))

    def _add_row(self, kind: Kind) -> None:
        table = self._tables[kind]
        row = table.rowCount()
        table.insertRow(row)
        for column in range(len(COLUMNS)):
            table.setItem(row, column, QTableWidgetItem(""))
        table.selectRow(row)

    def _remove_row(self, kind: Kind) -> None:
        table = self._tables[kind]
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    def _save(self) -> None:
        for kind, table in self._tables.items():
            entries: list[ResourceEntry] = []
            for row in range(table.rowCount()):
                source = _cell(table, row, 0)
                if not source:
                    continue
                entries.append(
                    ResourceEntry(
                        source=source,
                        target=_cell(table, row, 1),
                        source_lang=_cell(table, row, 2),
                        target_lang=_cell(table, row, 3),
                        note=_cell(table, row, 4),
                        origin="user",
                    )
                )
            self._resources.save_user(kind, entries)
        self.accept()


def _cell(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    return item.text().strip() if item is not None else ""
