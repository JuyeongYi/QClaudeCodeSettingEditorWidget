"""raw JSON 편집기: 구조를 알 수 없는 노드, anyOf 의 "(raw JSON)" 변형, 폼이 담을 수 없는 값의 보존용."""
from __future__ import annotations

import json
from typing import Any

from PySide6 import QtGui, QtWidgets

from ..constants import INVALID_STYLE
from ..schema import JsonSchema, default_for
from .base import BaseEditor


class RawJsonEditor(BaseEditor):
    """텍스트로 JSON 편집. 파싱 실패 시 마지막 유효값을 유지하고 빨간 테두리로 표시.

    single_line=True 면 한 줄 입력(작은 스칼라 자리에 들어갈 때), 아니면 여러 줄 텍스트.
    """

    def __init__(self, schema: JsonSchema, root: JsonSchema, depth: int = 0, parent=None, path: str = "",
                 single_line: bool = False):
        super().__init__(schema, root, depth, parent, path)
        self.compact = single_line
        self._last_valid: Any = default_for(schema, root)
        self._valid = True
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
        self._line: QtWidgets.QLineEdit | None = None
        self._text: QtWidgets.QPlainTextEdit | None = None
        if single_line:
            self._line = QtWidgets.QLineEdit()
            self._line.setFont(font)
            self._line.setPlaceholderText("JSON")
            self._line.textChanged.connect(self._on_text)
            widget: QtWidgets.QWidget = self._line
        else:
            self._text = QtWidgets.QPlainTextEdit()
            self._text.setFont(font)
            self._text.setMinimumHeight(90)
            self._text.setTabChangesFocus(True)
            self._text.setPlaceholderText("JSON")
            self._text.textChanged.connect(self._on_text)
            widget = self._text
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)

    def _input(self) -> QtWidgets.QWidget:
        return self._line or self._text  # type: ignore[return-value]

    def _raw_text(self) -> str:
        return self._line.text() if self._line is not None else self._text.toPlainText()  # type: ignore[union-attr]

    def _on_text(self, *_: Any) -> None:
        text = self._raw_text().strip()
        try:
            self._last_valid = json.loads(text) if text else None
            self._valid = True
        except ValueError:
            self._valid = False
        self._input().setStyleSheet("" if self._valid else INVALID_STYLE)
        if self._valid:
            self._emit()

    def isValid(self) -> bool:
        return self._valid

    def value(self) -> Any:
        return self._last_valid

    def setValue(self, value: Any) -> None:
        with self.loading():
            self._last_valid = value
            self._valid = True
            if self._line is not None:
                self._line.setText(json.dumps(value, ensure_ascii=False))
            else:
                self._text.setPlainText(json.dumps(value, indent=2, ensure_ascii=False))  # type: ignore[union-attr]
            self._input().setStyleSheet("")
