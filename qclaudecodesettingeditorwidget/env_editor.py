"""env 설정 전용 편집기: 알려진 환경변수 전체(스키마+문서)를 표로 나열하고 값을 설정/해제한다."""
from __future__ import annotations

from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .editors.base import BaseEditor
from .i18n import describe, tr
from .schema import EnvVarInfo, JsonSchema, first_sentence

COL_SET, COL_NAME, COL_VALUE, COL_DESC = range(4)
MUTED = "color: #8a8a8a;"


class _ValueCell(QtWidgets.QWidget):
    """값 셀: 후보값이 있으면 편집 가능한 콤보, 없으면 라인 에디트."""

    edited = QtCore.Signal()

    def __init__(self, info: EnvVarInfo, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        self._combo: QtWidgets.QComboBox | None = None
        self._line: QtWidgets.QLineEdit | None = None
        if info.values:
            self._combo = QtWidgets.QComboBox()
            self._combo.setEditable(True)
            self._combo.addItems(info.values)
            self._combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            self._combo.setCurrentText("")
            line = self._combo.lineEdit()
            if line is not None:
                hint = tr("e.g. {values}", values="/".join(info.values)) if info.values_are_hints else tr("value")
                line.setPlaceholderText(hint)
            self._combo.editTextChanged.connect(self.edited)
            lay.addWidget(self._combo)
        else:
            self._line = QtWidgets.QLineEdit()
            self._line.setPlaceholderText(tr("value"))
            self._line.textChanged.connect(self.edited)
            lay.addWidget(self._line)

    def text(self) -> str:
        return self._combo.currentText() if self._combo is not None else self._line.text()  # type: ignore[union-attr]

    def setText(self, text: str) -> None:
        if self._combo is not None:
            self._combo.setCurrentText(text)
        else:
            self._line.setText(text)  # type: ignore[union-attr]


class EnvEditor(BaseEditor):
    """settings.env 객체 편집기. value() 는 체크된 행만 {NAME: value} 로 반환한다."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, registry: dict[str, EnvVarInfo], parent=None,
                 related: dict[str, list[tuple[str, str]]] | None = None):
        super().__init__(schema, root, 0, parent, path="env")
        self._registry = registry
        self._related = related or {}  # env 이름 → [(settingKey, precedence)]
        self._rows: dict[str, int] = {}
        self._mono = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)

        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText(tr("Search variable names and descriptions…"))
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        self._only_set = QtWidgets.QCheckBox(tr("Set only"))
        self._only_set.toggled.connect(self._apply_filter)
        add_btn = QtWidgets.QPushButton(tr("+ Custom variable"))
        add_btn.setToolTip(tr("Add an environment variable that is not in the list"))
        add_btn.clicked.connect(self._prompt_add)
        self._count = QtWidgets.QLabel()
        self._count.setStyleSheet(MUTED)
        self._count.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Preferred)
        self._count.setMinimumWidth(self._count.fontMetrics().horizontalAdvance(tr("000 set / 000 variables")) + 8)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(self._filter, 1)
        top.addWidget(self._only_set)
        top.addWidget(add_btn)
        top.addWidget(self._count)

        self._table = QtWidgets.QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", tr("Variable"), tr("Value"), tr("Description")])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(COL_SET, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(COL_NAME, QtWidgets.QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_VALUE, QtWidgets.QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(COL_DESC, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hh.resizeSection(COL_NAME, 330)
        hh.resizeSection(COL_VALUE, 200)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.itemChanged.connect(self._on_item_changed)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(top)
        lay.addWidget(self._table, 1)

        self._table.setUpdatesEnabled(False)
        for info in registry.values():
            self._append_row(info)
        self._table.setUpdatesEnabled(True)
        self._update_count()

    # ---- rows
    def _append_row(self, info: EnvVarInfo, custom: bool = False) -> int:
        r = self._table.rowCount()
        self._table.insertRow(r)
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self._table.setItem(r, COL_SET, chk)

        description = describe(f"env.{info.name}", info.description)
        name_item = QtWidgets.QTableWidgetItem(info.name)
        name_item.setFont(self._mono)
        name_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
        tip = description or info.name
        rel = self._related.get(info.name, [])
        if rel:
            tip += "\n" + tr("Related setting:") + " " + ", ".join(
                f"{k} ({ {'env': tr('env wins'), 'setting': tr('setting wins')}.get(p, tr('related')) })" for k, p in rel)
        if custom:
            tip += "\n" + tr("(custom variable: not in schema or docs)")
        elif not info.in_schema:
            tip += "\n" + tr("(documented only, not in schema)")
        name_item.setToolTip(tip)
        if custom:
            name_item.setForeground(QtGui.QColor("#b26a00"))
        self._table.setItem(r, COL_NAME, name_item)

        cell = _ValueCell(info)
        cell.edited.connect(lambda r=r: self._on_value_edited(r))
        self._table.setCellWidget(r, COL_VALUE, cell)

        desc_text = first_sentence(description, 200)
        if rel:
            desc_text = "↔ " + ", ".join(k for k, _ in rel) + " · " + desc_text
        desc_item = QtWidgets.QTableWidgetItem(desc_text)
        desc_item.setToolTip(tip if rel else description)
        desc_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
        self._table.setItem(r, COL_DESC, desc_item)
        self._rows[info.name] = r
        return r

    def _cell(self, row: int) -> _ValueCell:
        return self._table.cellWidget(row, COL_VALUE)  # type: ignore[return-value]

    def _check_item(self, row: int) -> QtWidgets.QTableWidgetItem:
        return self._table.item(row, COL_SET)  # type: ignore[return-value]

    def _is_set(self, row: int) -> bool:
        return self._check_item(row).checkState() == QtCore.Qt.CheckState.Checked

    def _set_checked(self, row: int, on: bool) -> None:
        self._check_item(row).setCheckState(QtCore.Qt.CheckState.Checked if on else QtCore.Qt.CheckState.Unchecked)

    def _on_value_edited(self, row: int) -> None:
        if self._loading:
            return
        if not self._is_set(row):
            self._set_checked(row, True)  # itemChanged → _on_item_changed 가 emit
        else:
            self._emit()

    def _on_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if item.column() == COL_SET and not self._loading:
            self._update_count()
            self._emit()
            if self._only_set.isChecked():
                self._apply_filter()

    def _prompt_add(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(self, tr("Add environment variable"), tr("Variable name:"))
        name = name.strip()
        if ok and name:
            row = self.ensureVariable(name)
            self._set_checked(row, True)
            self._table.scrollToItem(self._table.item(row, COL_NAME))  # type: ignore[arg-type]
            self._cell(row).setFocus()

    # ---- public helpers
    def ensureVariable(self, name: str) -> int:
        """이름의 행 인덱스를 돌려주고, 없으면 사용자 변수 행을 만든다."""
        if name in self._rows:
            return self._rows[name]
        return self._append_row(EnvVarInfo(name=name), custom=True)

    def setVariable(self, name: str, value: str | None) -> None:
        """value 가 None 이면 해제, 아니면 설정."""
        row = self.ensureVariable(name)
        with self.loading():
            if value is None:
                self._set_checked(row, False)
            else:
                self._cell(row).setText(str(value))
                self._set_checked(row, True)
        self._update_count()
        self._emit()

    def setFilterText(self, text: str) -> None:
        self._filter.setText(text)

    def isSet(self, name: str) -> bool:
        return name in self._rows and self._is_set(self._rows[name])

    # ---- BaseEditor
    def value(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, row in self._rows.items():
            if self._is_set(row):
                out[name] = self._cell(row).text()
        return out

    def setValue(self, value: Any) -> None:
        data = value if isinstance(value, dict) else {}
        with self.loading():
            self._table.setUpdatesEnabled(False)
            try:
                for name, row in list(self._rows.items()):
                    if name not in data:
                        self._set_checked(row, False)
                for name, v in data.items():
                    row = self.ensureVariable(str(name))
                    self._cell(row).setText("" if v is None else str(v))
                    self._set_checked(row, True)
            finally:
                self._table.setUpdatesEnabled(True)
        self._update_count()
        self._apply_filter()

    # ---- filter
    def _apply_filter(self, *_: Any) -> None:
        text = self._filter.text().strip().lower()
        only = self._only_set.isChecked()
        for name, row in self._rows.items():
            show = True
            if only and not self._is_set(row):
                show = False
            if show and text:
                desc_item = self._table.item(row, COL_DESC)
                desc = desc_item.toolTip().lower() if desc_item is not None else ""
                show = text in name.lower() or text in desc or any(text in k.lower() for k, _ in self._related.get(name, []))
            self._table.setRowHidden(row, not show)

    def _update_count(self) -> None:
        n = sum(1 for r in self._rows.values() if self._is_set(r))
        self._count.setText(tr("{set} set / {total} variables", set=n, total=len(self._rows)))
