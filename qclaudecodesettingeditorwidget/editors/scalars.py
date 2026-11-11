"""스칼라 편집기: string / enum / boolean / integer / number / const / null.

각 편집기의 canRepresent() 는 값을 **바꾸지 않고** 담을 수 있는지 판단한다. 담을 수 없는 값(허용 목록 밖 enum,
불리언이 아닌 값, 스핀박스 범위 밖 정수 …)은 setValue 가 무시하고, 상위의 ValueSlot 이 raw JSON 으로 보존한다.
"""
from __future__ import annotations

import json
import math
from typing import Any

from PySide6 import QtGui, QtWidgets

from ..constants import INVALID_STYLE
from ..i18n import tr
from ..schema import JsonSchema, json_equal, json_in
from ..validation import is_valid
from .base import BaseEditor

INT32_MIN, INT32_MAX = -2_147_483_648, 2_147_483_647
NUMBER_DECIMALS = 6
NUMBER_LIMIT = 1e15


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _mono_font() -> QtGui.QFont:
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)


class StringEditor(BaseEditor):
    """문자열. suggestions 가 있으면 편집 가능한 콤보, multiline 이면 여러 줄 텍스트."""

    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None,
                 suggestions: list[str] | None = None, multiline: bool = False, path: str = "",
                 check_schema: JsonSchema | None = None):
        """check_schema: 검증에 쓸 원래 스키마(문자열 anyOf 를 제안 콤보로 합친 경우 원래 anyOf). 기본은 schema."""
        super().__init__(schema, root, depth, parent, path)
        self._multiline = multiline
        self._check_schema = check_schema if check_schema is not None else schema
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
        return "\n".join(f"{k}: {self.schema[k]}" for k in ("pattern", "format", "minLength", "maxLength")
                         if self.schema.get(k) not in (None, ""))

    def _input_widget(self) -> QtWidgets.QWidget:
        return self._text or self._combo or self._line  # type: ignore[return-value]

    def _on_change(self, *_: Any) -> None:
        self._apply_validity()
        self._emit()

    def _apply_validity(self) -> None:
        self._input_widget().setStyleSheet("" if self.isValid() else INVALID_STYLE)

    def isValid(self) -> bool:
        v = self.value()
        return v == "" or is_valid(self._check_schema, v, self.root)  # 빈 칸은 아직 입력 전이므로 빨갛게 하지 않는다

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, str)

    def value(self) -> str:
        if self._text is not None:
            return self._text.toPlainText()
        if self._combo is not None:
            return self._combo.currentText()
        return self._line.text()  # type: ignore[union-attr]

    def setValue(self, value: Any) -> None:
        if not isinstance(value, str):
            return  # 숫자·null 을 문자열로 바꾸지 않는다(ValueSlot 이 보존)
        text = value
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
        self._values: list[Any] = list(schema.get("enum", []))
        self._combo = QtWidgets.QComboBox()
        for v in self._values:
            self._combo.addItem(json.dumps(v) if not isinstance(v, str) else v)
        self._combo.currentIndexChanged.connect(self._emit)
        lay.addWidget(self._combo)
        lay.addStretch(1)

    def value(self) -> Any:
        idx = self._combo.currentIndex()
        return self._values[idx] if 0 <= idx < len(self._values) else None

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return json_in(value, self._values)

    def setValue(self, value: Any) -> None:
        idx = next((i for i, v in enumerate(self._values) if json_equal(v, value)), -1)
        if idx < 0:
            return  # 허용 목록 밖 값을 첫 항목으로 바꾸지 않는다(ValueSlot 이 보존)
        with self.loading():
            self._combo.setCurrentIndex(idx)


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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return isinstance(value, bool)

    def setValue(self, value: Any) -> None:
        if not isinstance(value, bool):
            return  # "false"·0 같은 값을 불리언으로 바꾸지 않는다
        with self.loading():
            self._check.setChecked(value)
            self._check.setText("true" if self._check.isChecked() else "false")


class IntEditor(BaseEditor):
    compact = True

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = ""):
        super().__init__(schema, root, depth, parent, path)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._spin = QtWidgets.QSpinBox()
        lo, hi = _bounds(schema, INT32_MIN, INT32_MAX, step=1)
        # QSpinBox 는 int32 — 스키마 범위가 더 넓어도 그 밖의 값은 canRepresent 가 거절해 raw JSON 으로 보존된다
        self._lo, self._hi = max(math.ceil(lo), INT32_MIN), min(math.floor(hi), INT32_MAX)
        self._spin.setRange(self._lo, max(self._lo, self._hi))
        self._spin.setGroupSeparatorShown(False)
        self._spin.valueChanged.connect(self._emit)
        lay.addWidget(self._spin)
        lay.addStretch(1)

    def value(self) -> int:
        return int(self._spin.value())

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        if not _is_number(value) or (isinstance(value, float) and not value.is_integer()):
            return False
        return self._lo <= value <= self._hi

    def setValue(self, value: Any) -> None:
        if not self.canRepresent(value):
            return  # 범위 밖·소수·문자열 값을 잘라 내거나 0 으로 바꾸지 않는다(int32 초과 OverflowError 도 방지)
        with self.loading():
            self._spin.setValue(int(value))


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
        self._lo, self._hi = _bounds(schema, -NUMBER_LIMIT, NUMBER_LIMIT, step=10 ** -NUMBER_DECIMALS)
        self._spin.setDecimals(NUMBER_DECIMALS)  # 범위보다 먼저: setRange 는 현재 소수 자릿수로 경계를 반올림한다
        self._spin.setRange(self._lo, self._hi)
        self._spin.setSingleStep(0.1 if self._hi - self._lo <= 10 else 1.0)
        self._spin.valueChanged.connect(self._emit)
        lay.addWidget(self._spin)
        lay.addStretch(1)

    def value(self) -> float | int:
        v = self._spin.value()
        return int(v) if float(v).is_integer() and abs(v) < 2**53 else v

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        if not _is_number(value) or not math.isfinite(value) or not self._lo <= value <= self._hi:
            return False
        return math.isclose(round(value, NUMBER_DECIMALS), value, rel_tol=0, abs_tol=1e-12)

    def setValue(self, value: Any) -> None:
        if not self.canRepresent(value):
            return  # 범위 밖·자릿수 초과 값을 잘라 내지 않는다(ValueSlot 이 보존)
        with self.loading():
            self._spin.setValue(float(value))


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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return json_equal(value, self._const)

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

    def canRepresent(self, value: Any) -> bool:  # noqa: N802
        return value is None

    def setValue(self, value: Any) -> None:
        return None


def _bounds(schema: JsonSchema, lo: float, hi: float, step: float) -> tuple[float, float]:
    """스키마 범위 → 스핀박스 범위. exclusive 경계는 한 단계(정수 1, 실수는 표시 자릿수 1칸) 안쪽."""
    if _is_number(schema.get("minimum")):
        lo = max(lo, schema["minimum"])
    if _is_number(schema.get("exclusiveMinimum")):
        lo = max(lo, schema["exclusiveMinimum"] + step)
    if _is_number(schema.get("maximum")):
        hi = min(hi, schema["maximum"])
    if _is_number(schema.get("exclusiveMaximum")):
        hi = min(hi, schema["exclusiveMaximum"] - step)
    return lo, hi
