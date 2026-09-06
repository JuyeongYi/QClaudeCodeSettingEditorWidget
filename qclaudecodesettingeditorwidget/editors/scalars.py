"""스칼라 편집기: string / enum / boolean / integer / number / const / null."""
from __future__ import annotations

import json
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ..i18n import tr
from ..schema import JsonSchema
from .base import INVALID_STYLE, BaseEditor

INT32_MIN, INT32_MAX = -2_147_483_648, 2_147_483_647


def _mono_font() -> QtGui.QFont:
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)


class StringEditor(BaseEditor):
    """문자열. suggestions 가 있으면 편집 가능한 콤보, multiline 이면 여러 줄 텍스트."""

    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None,
                 suggestions: list[str] | None = None, multiline: bool = False, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        self._multiline = multiline
        self._pattern: QtCore.QRegularExpression | None = None
        if isinstance(schema.get("pattern"), str):
            rx = QtCore.QRegularExpression(schema["pattern"])
            if rx.isValid():
                self._pattern = rx
        self._min_len = int(schema.get("minLength", 0) or 0)
        placeholder = ""
        ex = schema.get("examples")
        if isinstance(ex, list) and ex and isinstance(ex[0], str):
            placeholder = tr("e.g. {value}", value=ex[0])
        elif schema.get("format"):
            placeholder = str(schema["format"])

        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._combo: QtWidgets.QComboBox | None = None
        self._text: QtWidgets.QPlainTextEdit | None = None
        self._line: QtWidgets.QLineEdit | None = None
        if multiline:
            self.compact = False
            self._text = QtWidgets.QPlainTextEdit()
            self._text.setPlaceholderText(placeholder)
            self._text.setMinimumHeight(80)
            self._text.setTabChangesFocus(True)
            self._text.textChanged.connect(self._on_change)
            lay.addWidget(self._text)
        elif suggestions:
            self._combo = QtWidgets.QComboBox()
            self._combo.setEditable(True)
            self._combo.addItems([str(s) for s in suggestions])
            self._combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
            self._combo.setCurrentText("")
            line = self._combo.lineEdit()
            if line is not None:
                line.setPlaceholderText(placeholder)
            self._combo.editTextChanged.connect(self._on_change)
            self._combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
            lay.addWidget(self._combo)
        else:
            self._line = QtWidgets.QLineEdit()
            self._line.setPlaceholderText(placeholder)
            self._line.setClearButtonEnabled(True)
            self._line.textChanged.connect(self._on_change)
            lay.addWidget(self._line)
        self._input_widget().setToolTip(self._hint())

    def _hint(self) -> str:
        parts = []
        if self.schema.get("pattern"):
            parts.append(f"pattern: {self.schema['pattern']}")
        if self._min_len:
            parts.append(f"minLength: {self._min_len}")
        return "\n".join(parts)

    def _input_widget(self) -> QtWidgets.QWidget:
        return self._text or self._combo or self._line  # type: ignore[return-value]

    def _on_change(self, *_: Any) -> None:
        self._apply_validity()
        self._emit()

    def _apply_validity(self) -> None:
        self._input_widget().setStyleSheet("" if self.isValid() else INVALID_STYLE)

    def isValid(self) -> bool:
        v = self.value()
        if len(v) < self._min_len and v != "":
            return False
        if self._pattern is not None and v != "" and not self._pattern.match(v).hasMatch():
            return False
        return True

    def value(self) -> str:
        if self._text is not None:
            return self._text.toPlainText()
        if self._combo is not None:
            return self._combo.currentText()
        return self._line.text()  # type: ignore[union-attr]

    def setValue(self, value: Any) -> None:
        text = "" if value is None else str(value)
        with self.loading():
            if self._text is not None:
                self._text.setPlainText(text)
            elif self._combo is not None:
                self._combo.setCurrentText(text)
            else:
                self._line.setText(text)  # type: ignore[union-attr]
            self._apply_validity()


class EnumEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._combo = QtWidgets.QComboBox()
        for v in schema.get("enum", []):
            self._combo.addItem(json.dumps(v) if not isinstance(v, str) else v, v)
        self._combo.currentIndexChanged.connect(self._emit)
        lay.addWidget(self._combo)
        lay.addStretch(1)

    def value(self) -> Any:
        return self._combo.currentData()

    def setValue(self, value: Any) -> None:
        with self.loading():
            idx = self._combo.findData(value)
            if idx < 0 and isinstance(value, str):
                idx = self._combo.findText(value)
            self._combo.setCurrentIndex(max(idx, 0))


class BoolEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._check = QtWidgets.QCheckBox("false")
        self._check.toggled.connect(self._on_toggle)
        lay.addWidget(self._check)
        lay.addStretch(1)

    def _on_toggle(self, on: bool) -> None:
        self._check.setText("true" if on else "false")
        self._emit()

    def value(self) -> bool:
        return self._check.isChecked()

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._check.setChecked(bool(value))
            self._check.setText("true" if self._check.isChecked() else "false")


class IntEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._spin = QtWidgets.QSpinBox()
        lo, hi = _bounds(schema, INT32_MIN, INT32_MAX, integer=True)
        self._spin.setRange(int(lo), int(hi))
        self._spin.setGroupSeparatorShown(False)
        self._spin.valueChanged.connect(self._emit)
        lay.addWidget(self._spin)
        lay.addStretch(1)

    def value(self) -> int:
        return int(self._spin.value())

    def setValue(self, value: Any) -> None:
        with self.loading():
            try:
                self._spin.setValue(int(value))
            except (TypeError, ValueError):
                self._spin.setValue(0)


class _PlainDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """불필요한 소수점 0 을 표시하지 않는 QDoubleSpinBox (5.0000 → 5)."""

    def textFromValue(self, value: float) -> str:  # noqa: N802
        text = f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")
        return text or "0"


class NumberEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._spin = _PlainDoubleSpinBox()
        lo, hi = _bounds(schema, -1e15, 1e15, integer=False)
        self._spin.setRange(lo, hi)
        self._spin.setDecimals(6)
        self._spin.setSingleStep(0.1 if hi - lo <= 10 else 1.0)
        self._spin.valueChanged.connect(self._emit)
        lay.addWidget(self._spin)
        lay.addStretch(1)

    def value(self) -> float | int:
        v = self._spin.value()
        return int(v) if float(v).is_integer() and abs(v) < 2**53 else v

    def setValue(self, value: Any) -> None:
        with self.loading():
            try:
                self._spin.setValue(float(value))
            except (TypeError, ValueError):
                self._spin.setValue(0.0)


class ConstEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._const = schema.get("const")
        label = QtWidgets.QLabel(json.dumps(self._const, ensure_ascii=False))
        label.setFont(_mono_font())
        label.setToolTip(tr("Fixed value (const)"))
        lay.addWidget(label)
        lay.addStretch(1)

    def value(self) -> Any:
        return self._const

    def setValue(self, value: Any) -> None:  # 고정값이므로 무시
        return None


class NullEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel(tr("null"))
        label.setFont(_mono_font())
        lay.addWidget(label)
        lay.addStretch(1)

    def value(self) -> None:
        return None

    def setValue(self, value: Any) -> None:
        return None


def _bounds(schema: JsonSchema, lo: float, hi: float, integer: bool) -> tuple[float, float]:
    step = 1 if integer else 1e-9
    if isinstance(schema.get("minimum"), (int, float)):
        lo = schema["minimum"]
    if isinstance(schema.get("exclusiveMinimum"), (int, float)):
        lo = schema["exclusiveMinimum"] + step
    if isinstance(schema.get("maximum"), (int, float)):
        hi = schema["maximum"]
    if isinstance(schema.get("exclusiveMaximum"), (int, float)):
        hi = schema["exclusiveMaximum"] - step
    return lo, hi
