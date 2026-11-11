"""ValueSlot: 폼 편집기가 담을 수 없는 값을 바꾸지 않고 raw JSON 으로 보존하는 래퍼.

PropertyRow·DictEditor 값·ListEditor 항목이 모두 이 슬롯을 거쳐 값을 넣는다. 그래서 허용 목록 밖 enum,
범위 밖 숫자, 다른 타입의 값이 와도 기본값으로 바뀌거나 잘리지 않고, 페이지 구축 전후의 출력이 같다.
"""
from __future__ import annotations

from typing import Any

from PySide6 import QtWidgets

from ..constants import WARNING_LABEL_STYLE
from ..i18n import tr
from .base import BaseEditor
from .raw import RawJsonEditor


class ValueSlot(BaseEditor):
    """form(폼 편집기) + 필요할 때만 만드는 raw JSON 대체 편집기.

    setValue(v): form.canRepresent(v) 이면 폼에, 아니면 경고와 함께 raw JSON 에 그대로 담는다.
    「폼으로 편집」을 누르면 그 값을 버리고 폼의 기본값에서 시작한다.
    """

    def __init__(self, form: BaseEditor, parent: QtWidgets.QWidget | None = None):
        super().__init__(form.schema, form.root, form.level, parent, form.path)
        self.form = form
        self.compact = form.compact
        self._raw: RawJsonEditor | None = None
        self._fallback: QtWidgets.QWidget | None = None
        self._raw_mode = False
        form.changed.connect(self._emit)
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(2)
        self._lay.addWidget(form)

    # ---- 상태
    def isRawFallback(self) -> bool:  # noqa: N802
        """폼이 담을 수 없는 값을 raw JSON 으로 보존 중인지."""
        return self._raw_mode

    def _ensure_fallback(self) -> RawJsonEditor:
        if self._raw is None:
            box = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(box)
            lay.setContentsMargins(0, 0, 0, 0)
            icon = QtWidgets.QLabel("⚠")
            icon.setStyleSheet(WARNING_LABEL_STYLE)
            icon.setToolTip(tr("The form cannot show this value (not an allowed value, out of range or a different "
                               "type), so it is kept exactly as loaded. Edit it as JSON or switch to the form."))
            raw = RawJsonEditor(self.schema, self.root, self.level, path=self.path, single_line=self.compact)
            raw.changed.connect(self._emit)
            to_form = QtWidgets.QToolButton()
            to_form.setText(tr("Use form"))
            to_form.setToolTip(tr("Discard this value and edit it with the form (starts from the default)"))
            to_form.clicked.connect(self._to_form)
            lay.addWidget(icon, 0)
            lay.addWidget(raw, 1)
            lay.addWidget(to_form, 0)
            box.hide()
            self._lay.addWidget(box)
            self._fallback = box
            self._raw = raw
        return self._raw

    def _set_mode(self, raw: bool) -> None:
        self._raw_mode = raw
        self.form.setVisible(not raw)
        if self._fallback is not None:
            self._fallback.setVisible(raw)

    def _to_form(self) -> None:
        with self.loading():
            self.form.reset()
            self._set_mode(False)
        self._emit()

    # ---- BaseEditor
    def value(self) -> Any:
        return self._raw.value() if self._raw_mode and self._raw is not None else self.form.value()

    def setValue(self, value: Any) -> None:
        with self.loading():
            if self.form.canRepresent(value):
                self.form.setValue(value)
                self._set_mode(False)
            else:
                self._ensure_fallback().setValue(value)
                self._set_mode(True)

    def reset(self) -> None:
        with self.loading():
            self.form.reset()
            self._set_mode(False)

    def isValid(self) -> bool:
        return self._raw.isValid() if self._raw_mode and self._raw is not None else self.form.isValid()
