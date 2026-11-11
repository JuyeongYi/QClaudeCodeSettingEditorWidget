"""env 설정 전용 편집기: 알려진 환경변수 전체(스키마+문서)를 표로 나열하고 값을 설정/해제한다.

값은 문자열이 원칙이지만, 파일·API 로 문자열이 아닌 값(숫자·불리언 등)이 들어오면 바꾸지 않고 보존한다
(셀에는 JSON 으로 보이고, 사용자가 그 셀을 고치면 그때부터 문자열). 문제는 검증이 셀 테두리·툴팁으로 알린다.
"""
from __future__ import annotations

import json
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from .constants import ENV_KEY, INVALID_STYLE, MUTED, SUSPECT_STYLE, Severity
from .editors.base import BaseEditor
from .editors.row import precedence_label
from .i18n import describe, tr
from .keys import EnvVar
from .schema import EnvVarInfo, JsonSchema, first_sentence
from .validation import Issue

COL_SET, COL_NAME, COL_VALUE, COL_DESC = range(4)


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

    def setProblem(self, message: str, severity: Severity | None) -> None:
        """검증 문제 표시(severity 가 None 이면 해제)."""
        widget = self._combo if self._combo is not None else self._line
        style = {Severity.ERROR: INVALID_STYLE, Severity.WARNING: SUSPECT_STYLE}[severity] if severity else ""
        widget.setStyleSheet(style)  # type: ignore[union-attr]
        widget.setToolTip(message)  # type: ignore[union-attr]


class EnvEditor(BaseEditor):
    """settings.env 객체 편집기. value() 는 체크된 행만 {NAME: value} 로 반환한다."""

    def __init__(self, schema: JsonSchema, root: JsonSchema, registry: dict[str, EnvVarInfo], parent=None,
                 related: dict[str, list[tuple[str, str]]] | None = None):
        super().__init__(schema, root, 0, parent, path=ENV_KEY)
        self._registry = registry
        self._related = related or {}  # env 이름 → [(settingKey, precedence)]
        self._rows: dict[str, int] = {}
        self._names: dict[int, str] = {}       # 행 → 이름
        self._non_string: dict[str, Any] = {}  # 문자열이 아닌 채로 로드된 값(사용자가 고치기 전까지 그대로 출력)
        self._marked: set[str] = set()         # 문제 표시 중인 변수
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
            tip += "\n" + tr("Related setting:") + " " + ", ".join(f"{k} ({precedence_label(p)})" for k, p in rel)
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
        self._names[r] = info.name
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
        self._non_string.pop(self._names.get(row, ""), None)  # 사용자가 고친 값은 문자열
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
    def ensureVariable(self, name: str | EnvVar) -> int:
        """이름(문자열 또는 EnvVar)의 행 인덱스를 돌려주고, 없으면 사용자 변수 행을 만든다."""
        name = EnvVar.coerce(name)
        if name in self._rows:
            return self._rows[name]
        return self._append_row(EnvVarInfo(name=name), custom=True)

    def setVariable(self, name: str | EnvVar, value: Any) -> None:
        """value 가 None 이면 해제, 아니면 설정. 문자열이 아닌 값도 바꾸지 않고 보존한다."""
        row = self.ensureVariable(name)
        with self.loading():
            if value is None:
                self._set_checked(row, False)
            else:
                self._put(self._names[row], row, value)
                self._set_checked(row, True)
        self._update_count()
        self._emit()

    def setFilterText(self, text: str) -> None:
        self._filter.setText(text)

    def isSet(self, name: str | EnvVar) -> bool:
        name = EnvVar.coerce(name)
        return name in self._rows and self._is_set(self._rows[name])

    def variable(self, name: str | EnvVar) -> Any:
        """설정된 값, 해제 상태면 None."""
        name = EnvVar.coerce(name)
        return self._value_of(name, self._rows[name]) if self.isSet(name) else None

    def setIssues(self, issues: dict[str, list[Issue]]) -> None:
        """변수 이름 → 검증 문제. 해당 값 셀에 테두리·툴팁으로 표시하고, 목록에 없는 변수는 표시를 지운다."""
        for name in self._marked - set(issues):
            if name in self._rows:
                self._cell(self._rows[name]).setProblem("", None)
        for name, found in issues.items():
            if name in self._rows and found:
                worst = Severity.ERROR if any(i.severity is Severity.ERROR for i in found) else Severity.WARNING
                self._cell(self._rows[name]).setProblem("\n".join(i.message for i in found), worst)
        self._marked = set(issues)

    def _put(self, name: str, row: int, value: Any) -> None:
        if isinstance(value, str):
            self._non_string.pop(name, None)
            self._cell(row).setText(value)
        else:
            self._non_string[name] = value
            self._cell(row).setText(json.dumps(value, ensure_ascii=False))

    def _value_of(self, name: str, row: int) -> Any:
        return self._non_string[name] if name in self._non_string else self._cell(row).text()

    # ---- BaseEditor
    def value(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, row in self._rows.items():
            if self._is_set(row):
                out[name] = self._value_of(name, row)
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
                    self._put(self._names[row], row, v)
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
